from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.utils import timezone

from .models import ChatMessage


def chat_messages(request):
    """Return last N chat messages as JSON"""
    limit = int(request.GET.get("limit", 50))
    limit = max(1, min(limit, 200))
    messages = ChatMessage.objects.select_related("user").order_by("-created_at")[:limit]
    messages = list(reversed(messages))
    data = [
        {
            "id": m.pk,
            "username": m.username,
            "message": m.message,
            "created_at": m.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        }
        for m in messages
    ]
    return JsonResponse({"messages": data})


@csrf_exempt
@require_POST
def send_message(request):
    """Create a new chat message"""
    text = (request.POST.get("message") or "").strip()
    if not text:
        return JsonResponse({"error": "Tin nhắn trống"}, status=400)
    if len(text) > 2000:
        return JsonResponse({"error": "Tin nhắn quá dài"}, status=400)

    user = request.user if request.user.is_authenticated else None
    username = user.username if user else "Khách"
    msg = ChatMessage.objects.create(user=user, username=username, message=text)
    return JsonResponse(
        {
            "ok": True,
            "id": msg.pk,
            "username": msg.username,
            "message": msg.message,
            "created_at": msg.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        }
    )