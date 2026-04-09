"""
Social media scheduler models: ScheduledPost and ScheduledPlatform.
"""
from django.db import models
from core.models import Client


class ScheduledPost(models.Model):
    """A social media post scheduled for publishing"""

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('scheduled', 'Scheduled'),
        ('published', 'Published'),
        ('failed', 'Failed'),
    ]

    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name='scheduled_posts'
    )
    content = models.TextField()
    media_urls = models.JSONField(
        default=list,
        blank=True,
        help_text='List of media URLs (images, videos)'
    )
    link_url = models.URLField(blank=True, help_text='URL to include in post')
    scheduled_time = models.DateTimeField(
        null=True,
        blank=True,
        help_text='When to publish. Null if draft.'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='draft'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-scheduled_time']

    def __str__(self):
        preview = self.content[:50] + ('...' if len(self.content) > 50 else '')
        return f"Post {self.id}: {preview}"


class ScheduledPlatform(models.Model):
    """Platform-specific status for a scheduled post"""

    PLATFORM_CHOICES = [
        ('facebook', 'Facebook'),
        ('instagram', 'Instagram'),
        ('linkedin', 'LinkedIn'),
        ('pinterest', 'Pinterest'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('posted', 'Posted'),
        ('failed', 'Failed'),
    ]

    post = models.ForeignKey(
        ScheduledPost,
        on_delete=models.CASCADE,
        related_name='platform_posts'
    )
    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES)
    platform_post_id = models.CharField(
        max_length=255,
        blank=True,
        help_text='Post ID returned by the platform API after publishing'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['post', 'platform']
        ordering = ['platform']

    def __str__(self):
        return f"{self.post.id} - {self.platform} ({self.status})"
