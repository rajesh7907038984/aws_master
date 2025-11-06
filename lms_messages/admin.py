from django.contrib import admin
from .models import Message, MessageReadStatus, MessageAttachment


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    """Admin interface for Message model"""
    list_display = ['subject', 'sender', 'created_at', 'branch', 'is_course_message']
    list_filter = ['created_at', 'branch', 'is_course_message', 'sent_to_group']
    search_fields = ['subject', 'content', 'sender__username', 'sender__email']
    readonly_fields = ['created_at', 'updated_at', 'external_id', 'external_source']
    filter_horizontal = ['recipients']
    
    fieldsets = (
        ('Message Details', {
            'fields': ('sender', 'recipients', 'subject', 'content')
        }),
        ('Threading & Context', {
            'fields': ('parent_message', 'branch', 'sent_to_group')
        }),
        ('Course Information', {
            'fields': ('is_course_message', 'related_course')
        }),
        ('External Integration', {
            'fields': ('external_id', 'external_source'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def get_queryset(self, request):
        """Optimize queryset with select_related"""
        qs = super().get_queryset(request)
        return qs.select_related('sender', 'branch', 'sent_to_group', 'related_course', 'parent_message')


@admin.register(MessageReadStatus)
class MessageReadStatusAdmin(admin.ModelAdmin):
    """Admin interface for MessageReadStatus model"""
    list_display = ['message_subject', 'user', 'is_read', 'read_at']
    list_filter = ['is_read', 'read_at']
    search_fields = ['message__subject', 'user__username', 'user__email']
    readonly_fields = ['read_at']
    
    def message_subject(self, obj):
        """Display message subject in list view"""
        return obj.message.subject
    message_subject.short_description = 'Message'
    
    def get_queryset(self, request):
        """Optimize queryset with select_related"""
        qs = super().get_queryset(request)
        return qs.select_related('message', 'user')


@admin.register(MessageAttachment)
class MessageAttachmentAdmin(admin.ModelAdmin):
    """Admin interface for MessageAttachment model"""
    list_display = ['filename', 'message_subject', 'file_type', 'uploaded_at']
    list_filter = ['file_type', 'uploaded_at']
    search_fields = ['filename', 'message__subject']
    readonly_fields = ['uploaded_at']
    
    def message_subject(self, obj):
        """Display message subject in list view"""
        return obj.message.subject
    message_subject.short_description = 'Message'
    
    def get_queryset(self, request):
        """Optimize queryset with select_related"""
        qs = super().get_queryset(request)
        return qs.select_related('message')
