"""
AI assistant for the GITC Portal chat.

Implements a lightweight RAG flow:
  1. Build / refresh an in-memory knowledge base from all GeoNode resources.
  2. Retrieve the top-k resources matching the user question (Vietnamese-aware).
  3. Call the Google Gemini API (REST, no extra pip dependencies).
"""

import json
import os
import re
import threading
import time
import unicodedata
import urllib.error
import urllib.request

from django.conf import settings

SYSTEM_PROMPT = """Bạn là "Trợ lý GITC Portal", trợ lý ảo thân thiện, chuyên nghiệp của nền tảng chia sẻ dữ liệu không gian GIS (GeoNode).
Nguyên tắc hoạt động:
1. Bạn có thể trò chuyện tự nhiên về mọi chủ đề (chào hỏi, giới thiệu, kiến thức GIS, địa lý...) như một trợ lý thông minh.
2. Khi được hỏi về DỮ LIỆU, LAYER, BẢN ĐỒ, TÀI LIỆU hoặc tính năng của hệ thống, hãy dựa CHỈ vào phần "THÔNG TIN HỆ THỐNG (context)" được cung cấp. Không bịa thông tin, không bịa tài liệu hay layer không có thật.
3. Khi kể về một tài nguyên, nhắc rõ: tên, loại (Raster/Vector/Bản đồ/Tài liệu), mô tả, người quản lý, đường dẫn chi tiết.
4. Trả lời bằng tiếng Việt, rõ ràng, có cấu trúc, gọn gàng (5-15 dòng), dùng dấu đầu dòng/bullet nếu hợp lý.
5. Khi câu hỏi yêu cầu thông tin nhạy cảm, bất hợp pháp, gây hại hoặc nằm ngoài khả năng của bạn, hãy từ chối khéo léo bằng tiếng Việt và gợi ý hướng khác."""

# Mô tả tổng quan toàn bộ dự án để AI trả lời được các câu hỏi "chuyên sâu về project".
PROJECT_PROFILE = """THÔNG TIN VỀ DỰ ÁN GITC PORTAL:
- Tên dự án: GITC Portal - cổng thông tin chia sẻ dữ liệu không gian địa lý (WebGIS) dựa trên nền tảng GeoNode 4.x + MapStore, chạy bằng Docker Compose trên máy local (http://localhost).
- Công nghệ: Django (Python), GeoNode, MapStore 2, GeoServer, PostgreSQL/PostGIS, Nginx, Bootstrap 5 + Arsha template, Docker.
- Các trang chính:
  * Trang chủ (/): hero + tìm kiếm, 4 chỉ số thống kê (số bản đồ/layer/tài liệu/người dùng), 6 tính năng chính, mục "Layers nổi bật" hiển thị các layer raster nổi bật, CTA, footer.
  * Trang Layers (/datasets/): danh sách layer, tìm kiếm, lọc Raster/Vector, phân trang, bấm vào để xem chi tiết.
  * Trang Maps (/maps/): danh sách bản đồ.
  * Trang Documents (/documents/): danh sách tài liệu.
  * Viewer bản đồ: mở layer/bản đồ để xem trên bản đồ tương tác (MapStore).
- Chatbot: widget chat góc phải dưới, có AI trợ lý trả lời về dữ liệu và tính năng của hệ thống. CHỈ người ĐĂNG NHẬP mới được chat.
- Nhân vật AI: "Trợ lý GITC Portal", trả lời tiếng Việt.
- Mỗi tài nguyên dữ liệu là một "resource" và có trang chi tiết tại các URL dạng: /catalogue/#/dataset/<id>, /catalogue/#/map/<id>, /catalogue/#/document/<id>.
- Người dùng có thể đăng ký, đăng nhập, xem và tải dữ liệu, upload dữ liệu mới, mở bản đồ, xem tài liệu."""

_MODEL = getattr(settings, "CHAT_GEMINI_MODEL", "gemini-3.6-flash")
_TIMEOUT = getattr(settings, "CHAT_GEMINI_TIMEOUT", 40)
_KB_TTL = 300  # seconds
_cache = {}
_cache_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Vietnamese-normalization helpers (remove diacritics, lowercase)
# ---------------------------------------------------------------------------
def _normalize(text):
    if not text:
        return ""
    text = unicodedata.normalize("NFD", str(text))
    chars = [c for c in text if unicodedata.category(c) != "Mn"]
    return "".join(chars).lower()


def _tokens(text):
    return set(re.findall(r"[\w]+", _normalize(text)))


# ---------------------------------------------------------------------------
# Knowledge base builder
# ---------------------------------------------------------------------------
def _resource_document(resource):
    """Return a dict describing a single GeoNode resource."""
    abstract = resource.abstract or ""
    supplemental = resource.supplemental_information or ""
    keywords = [k.name for k in resource.keywords.all()[:10]]
    owner = resource.owner.username if resource.owner else None
    links = {}
    for link in resource.link_set.all()[:40]:
        name = getattr(link, "name", None) or "Link"
        if name not in links:
            links[name] = getattr(link, "url", "")
    return {
        "id": resource.pk,
        "name": getattr(resource, "name", None) or resource.title,
        "title": resource.title or "",
        "type": resource.resource_type,
        "subtype": getattr(resource, "subtype", None),
        "abstract": abstract,
        "supplemental_information": supplemental,
        "keywords": keywords,
        "owner": owner,
        "category": getattr(getattr(resource, "category", None), "name", None),
        "detail_url": resource.get_absolute_url(),
        "thumbnail_url": getattr(resource, "thumbnail_url", None),
        "links": links,
        "bbox": (resource.bbox_x0, resource.bbox_y0, resource.bbox_x1, resource.bbox_y1)
        if resource.bbox_x0 is not None
        else None,
    }


def _load_document_content(resource):
    """Try to get the actual text content of a document resource."""
    try:
        from geonode.documents.models import Document

        doc = Document.objects.get(pk=resource.pk)
        content_parts = []
        if doc.abstract:
            content_parts.append(doc.abstract)
        if doc.doc_url:
            content_parts.append(f"Link nguồn: {doc.doc_url}")
        doc_file = getattr(doc, "doc_file", None)
        if doc_file:
            path = doc_file.path
            ext = os.path.splitext(path)[1].lower()
            if ext in (".txt", ".md", ".html", ".htm", ".csv", ".json"):
                with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                    content_parts.append(fh.read(20000))
        return "\n".join(content_parts)
    except Exception as exc:  # noqa: BLE001
        return f"(Không đọc được nội dung tài liệu: {exc})"


def _build_knowledge_base():
    from geonode.base.models import ResourceBase

    items = []
    qs = (
        ResourceBase.objects.select_related("owner", "category")
        .prefetch_related("keywords", "link_set")
        .order_by("pk")
    )
    for resource in qs:
        doc = _resource_document(resource)
        if resource.resource_type == "document":
            doc["document_content"] = _load_document_content(resource)
        items.append(doc)
    return items


def get_knowledge_base(force=False):
    global _cache
    now = time.time()
    if force:
        with _cache_lock:
            _cache.clear()
    if _cache and (now - _cache.get("ts", 0)) < _KB_TTL:
        return _cache["items"]
    items = _build_knowledge_base()
    with _cache_lock:
        _cache = {"ts": now, "items": items}
    return items


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------
def _score(question_tokens, doc):
    hay = " ".join(
        [
            doc.get("title", ""),
            doc.get("name", ""),
            " ".join(doc.get("keywords", []) or []),
            str(doc.get("category", "") or ""),
            str(doc.get("type", "")),
            str(doc.get("subtype", "") or ""),
        ]
    )
    hay_tokens = _tokens(hay)
    score = len(question_tokens & hay_tokens)
    if score:
        # small bonus for exact title match
        if _normalize(doc.get("title", "")) == _normalize(" ".join(sorted(question_tokens))):
            score += 2
    return score


def retrieve(question, k=5):
    """Return top-k resources most relevant to the question.

    For aggregate questions ("bao nhiêu", "danh sách tất cả", "tổng cộng"),
    broaden the selection so counting/listing answers are complete."""
    q_tokens = _tokens(question)
    normalized_q = _normalize(question)

    aggregate_markers = ["bao nhiêu", "bao nhieu", "danh sách", "danh sach",
                         "tất cả", "tat ca", "tổng cộng", "tong cong",
                         "liệt kê", "liet ke", "kể tên", "ke ten", "danh mục"]
    is_aggregate = any(m in normalized_q for m in aggregate_markers)

    items = get_knowledge_base()
    scored = sorted(
        items,
        key=lambda d: (_score(q_tokens, d), -(d.get("id") or 0)),
        reverse=True,
    )
    # only keep items with at least one overlapping token
    relevant = [d for d in scored if _score(q_tokens, d) > 0]

    if is_aggregate:
        # broaden: include every resource of the mentioned type(s)
        aliases = {
            "dataset": ["dataset", "layer", "lop", "du lieu", "dữ liệu", "raster", "vector"],
            "map": ["map", "ban do", "bản đồ"],
            "document": ["document", "tai lieu", "tài liệu", "doc"],
            "dashboard": ["dashboard", "bang dieu khien", "bảng điều khiển"],
        }
        mentioned_types = [
            t for t, words in aliases.items()
            if any(w in normalized_q for w in words)
        ]
        if mentioned_types:
            type_relevant = [d for d in scored if d["type"] in mentioned_types]
            if type_relevant:
                relevant = type_relevant
        if not relevant:
            relevant = scored

    if not relevant:
        # fallback: newest few
        relevant = scored[:k]
    return relevant[: max(k, 20)] if is_aggregate else relevant[:k]


def format_context(items):
    """Render retrieved resources into a compact context block for the prompt."""
    sections = []
    for i, d in enumerate(items, 1):
        lines = [f"{i}. {d['title']} ({d['type'].upper()} - id {d['id']})"]
        if d.get("subtype"):
            lines.append(f"   Phân loại: {d['subtype']}")
        if d.get("abstract"):
            lines.append(f"   Mô tả: {d['abstract'][:600]}")
        if d.get("supplemental_information"):
            lines.append(f"   Thông tin bổ sung: {d['supplemental_information'][:1500]}")
        if d.get("keywords"):
            lines.append(f"   Từ khóa: {', '.join(d['keywords'][:8])}")
        if d.get("category"):
            lines.append(f"   Danh mục: {d['category']}")
        if d.get("owner"):
            lines.append(f"   Người quản lý: {d['owner']}")
        if d.get("links"):
            lines.append(f"   Liên kết: {', '.join(f'{n}({u})' for n, u in list(d['links'].items())[:4])}")
        if d.get("detail_url"):
            lines.append(f"   Chi tiết: {d['detail_url']}")
        if d.get("document_content"):
            lines.append(f"   Nội dung tài liệu: {d['document_content'][:1500]}")
        if d.get("bbox"):
            lines.append(f"   Phạm vi (bbox): {d['bbox']}")
        sections.append("\n".join(lines))
    return "\n\n".join(sections)


# ---------------------------------------------------------------------------
# Gemini call (REST)
# ---------------------------------------------------------------------------
def ask_gemini(question, context_text):
    api_key = getattr(settings, "GOOGLE_API_KEY", None)
    if not api_key:
        return "Chưa cấu hình khóa API AI. Vui lòng đặt GOOGLE_API_KEY trong file .env rồi khởi động lại hệ thống."

    model = getattr(settings, "CHAT_GEMINI_MODEL", _MODEL)
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )
    user_prompt = (
        "THÔNG TIN HỆ THỐNG (context):\n"
        f"{context_text}\n\n\n"
        f"{PROJECT_PROFILE}\n\n"
        "CÂU HỎI CỦA NGƯỜI DÙNG:\n"
        f"{question}\n\n"
        "Hãy trả lời bằng tiếng Việt. Nếu câu hỏi về dữ liệu/tính năng hệ thống, dùng context ở trên; "
        "nếu là trò chuyện thông thường, trả lời tự nhiên; nếu quá giới hạn, từ chối khéo."
    )
    payload = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "generationConfig": {"temperature": 0.4, "maxOutputTokens": 1024},
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        candidates = data.get("candidates") or []
        if not candidates:
            return "AI không trả được câu trả lời cho câu hỏi này, bạn thử diễn đạt khác nhé."
        parts = candidates[0].get("content", {}).get("parts", [])
        return "".join(p.get("text", "") for p in parts).strip() or "AI trả lời trống."
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = json.loads(exc.read().decode("utf-8")).get("error", {}).get("message", "")
        except Exception:  # noqa: BLE001
            pass
        return f"Lỗi AI (HTTP {exc.code}): {detail or exc.reason}"
    except Exception as exc:  # noqa: BLE001
        return f"Lỗi kết nối AI: {exc}"


def answer_question(question):
    """Full RAG pipeline: retrieve -> call Gemini -> return text answer."""
    items = retrieve(question, k=5)
    context_text = format_context(items)
    return ask_gemini(question, context_text)