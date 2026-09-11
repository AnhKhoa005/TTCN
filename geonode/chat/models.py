from django.db import models
from django.conf import settings
from django.utils import timezone


class ChatMessage(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="chat_messages",
        null=True,
        blank=True,
    )
    username = models.CharField(max_length=150, default="Khách")
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def save(self, *args, **kwargs):
        if self.user_id:
            self.username = self.user.username
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.username}: {self.message[:50]}"