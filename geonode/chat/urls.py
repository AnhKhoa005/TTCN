from django.urls import re_path

from .views import chat_messages, send_message

urlpatterns = [
    re_path(r"^messages/?$", chat_messages, name="chat-messages"),
    re_path(r"^send/?$", send_message, name="chat-send"),
]