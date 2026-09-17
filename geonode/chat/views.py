from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.utils import timezone

from .models import ChatMessage
from .ai import answer_question

MESSAGE_LIMIT = 2000


def _unauthorized():
    return JsonResponse(
        {"error": "Bạn cần đăng nhập để sử dụng chat.", "login_required": True},
        status=401,
    )


def _msg_dict(m):
    return {
        "id": m.pk,
        "user_id": m.user_id,
        "username": m.username,
        "message": m.message,
        "created_at": m.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        "is_ai": m.username == "Trợ lý GITC Portal",
    }


def chat_messages(request):
    """Return last N chat messages as JSON (login required)."""
    if not request.user.is_authenticated:
        return _unauthorized()
    limit = int(request.GET.get("limit", 50))
    limit = max(1, min(limit, 200))
    messages = ChatMessage.objects.select_related("user").order_by("-created_at")[:limit]
    messages = list(reversed(messages))
    data = [_msg_dict(m) for m in messages]
    return JsonResponse({"messages": data})


@csrf_exempt
@require_POST
def send_message(request):
    """Create a new chat message (login required)."""
    if not request.user.is_authenticated:
        return _unauthorized()
    text = (request.POST.get("message") or "").strip()
    if not text:
        return JsonResponse({"error": "Tin nhắn trống"}, status=400)
    if len(text) > MESSAGE_LIMIT:
        return JsonResponse({"error": "Tin nhắn quá dài"}, status=400)

    msg = ChatMessage.objects.create(user=request.user, message=text)
    return JsonResponse({"ok": True, **_msg_dict(msg)})


@csrf_exempt
@require_POST
def ask_question(request):
    """Create a chat message and have the AI assistant reply (login required)."""
    if not request.user.is_authenticated:
        return _unauthorized()
    text = (request.POST.get("message") or "").strip()
    if not text:
        return JsonResponse({"error": "Tin nhắn trống"}, status=400)
    if len(text) > MESSAGE_LIMIT:
        return JsonResponse({"error": "Tin nhắn quá dài"}, status=400)

    msg = ChatMessage.objects.create(user=request.user, message=text)

    ai_reply = answer_question(text)
    ai_msg = ChatMessage.objects.create(
        user=None, username="Trợ lý GITC Portal", message=ai_reply
    )

    return JsonResponse(
        {
            "ok": True,
            "user": _msg_dict(msg),
            "ai": _msg_dict(ai_msg),
        }
    )