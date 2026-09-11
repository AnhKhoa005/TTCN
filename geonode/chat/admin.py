from django.contrib import admin

from .models import ChatMessage


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ("id", "username", "message", "created_at")
    list_filter = ("created_at",)
    search_fields = ("username", "message")
    readonly_fields = ("created_at",)