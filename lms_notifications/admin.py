from django.contrib import admin
from django.utils.html import format_html
from django.urls import path, reverse
from django.shortcuts import redirect
from django.contrib import messages
from django.utils import timezone
from .models import (
    NotificationType, NotificationSettings, NotificationTypeSettings,
    Notification, BulkNotification, NotificationTemplate, NotificationLog
)


@admin.register(NotificationType)
class NotificationTypeAdmin(admin.ModelAdmin):
    list_display = ['name', 'display_name', 'is_active', 'can_be_disabled', 'default_email_enabled', 'default_web_enabled', 'created_at']
    list_filter = ['is_active', 'can_be_disabled', 'default_email_enabled', 'default_web_enabled', 'created_at']
    search_fields = ['name', 'display_name', 'description']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'display_name', 'description', 'is_active')
        }),
        ('Settings', {
            'fields': ('can_be_disabled', 'available_to_roles', 'default_email_enabled', 'default_web_enabled')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(NotificationSettings)
class NotificationSettingsAdmin(admin.ModelAdmin):
    list_display = ['user', 'email_notifications_enabled', 'web_notifications_enabled', 'daily_digest_enabled', 'weekly_digest_enabled']
    list_filter = ['email_notifications_enabled', 'web_notifications_enabled', 'daily_digest_enabled', 'weekly_digest_enabled']
    search_fields = ['user__username', 'user__email', 'user__first_name', 'user__last_name']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('User', {
            'fields': ('user',)
        }),
        ('Global Settings', {
            'fields': ('email_notifications_enabled', 'web_notifications_enabled')
        }),
        ('Digest Settings', {
            'fields': ('daily_digest_enabled', 'weekly_digest_enabled')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(NotificationTypeSettings)
class NotificationTypeSettingsAdmin(admin.ModelAdmin):
    list_display = ['user', 'notification_type', 'email_enabled', 'web_enabled']
    list_filter = ['email_enabled', 'web_enabled', 'notification_type', 'created_at']
    search_fields = ['user__username', 'user__email', 'notification_type__name']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['title', 'recipient', 'sender', 'notification_type', 'priority', 'is_read', 'email_sent', 'created_at']
    list_filter = ['notification_type', 'priority', 'is_read', 'email_sent', 'created_at', 'sender__role']
    search_fields = ['title', 'recipient__username', 'sender__username', 'short_message']
    readonly_fields = ['created_at', 'read_at', 'email_sent_at', 'email_error']
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('notification_type', 'title', 'short_message', 'message')
        }),
        ('Recipients & Sender', {
            'fields': ('recipient', 'sender')
        }),
        ('Settings', {
            'fields': ('priority', 'action_url', 'action_text', 'expires_at')
        }),
        ('Status', {
            'fields': ('is_read', 'read_at', 'email_sent', 'email_sent_at', 'email_error')
        }),
        ('Related Objects', {
            'fields': ('related_course', 'related_assignment'),
            'classes': ('collapse',)
        }),
        ('Context Data', {
            'fields': ('context_data',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['mark_as_read', 'send_email_notifications']
    
    def mark_as_read(self, request, queryset):
        count = 0
        for notification in queryset:
            if not notification.is_read:
                notification.mark_as_read()
                count += 1
        self.message_user(request, f'Marked {count} notifications as read.')
    mark_as_read.short_description = "Mark selected notifications as read"
    
    def send_email_notifications(self, request, queryset):
        count = 0
        for notification in queryset:
            if not notification.email_sent:
                if notification.send_email():
                    count += 1
        self.message_user(request, f'Sent {count} email notifications.')
    send_email_notifications.short_description = "Send email for selected notifications"


@admin.register(BulkNotification)
class BulkNotificationAdmin(admin.ModelAdmin):
    list_display = ['title', 'sender', 'recipient_type', 'status', 'total_recipients', 'sent_count', 'failed_count', 'created_at']
    list_filter = ['recipient_type', 'status', 'notification_type', 'priority', 'created_at']
    search_fields = ['title', 'sender__username', 'short_message']
    readonly_fields = ['status', 'total_recipients', 'sent_count', 'failed_count', 'started_at', 'completed_at', 'created_at']
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('title', 'short_message', 'message', 'notification_type', 'sender')
        }),
        ('Recipients', {
            'fields': ('recipient_type', 'target_roles', 'target_branches', 'target_groups', 'target_courses', 'custom_recipients')
        }),
        ('Settings', {
            'fields': ('priority', 'action_url', 'action_text', 'scheduled_for')
        }),
        ('Status', {
            'fields': ('status', 'total_recipients', 'sent_count', 'failed_count', 'started_at', 'completed_at')
        }),
        ('Timestamps', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['send_bulk_notifications', 'duplicate_bulk_notification']
    
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                '<int:bulk_id>/send/',
                self.admin_site.admin_view(self.send_bulk_notification),
                name='lms_notifications_bulknotification_send'
            ),
        ]
        return custom_urls + urls
    
    def send_bulk_notification(self, request, bulk_id):
        bulk_notification = BulkNotification.objects.get(id=bulk_id)
        if bulk_notification.status == 'draft':
            bulk_notification.send_notifications()
            messages.success(request, f'Bulk notification "{bulk_notification.title}" has been sent.')
        else:
            messages.error(request, 'This bulk notification has already been sent or is in progress.')
        
        return redirect('admin:lms_notifications_bulknotification_changelist')
    
    def send_bulk_notifications(self, request, queryset):
        count = 0
        for bulk_notification in queryset:
            if bulk_notification.status == 'draft':
                bulk_notification.send_notifications()
                count += 1
        self.message_user(request, f'Sent {count} bulk notifications.')
    send_bulk_notifications.short_description = "Send selected bulk notifications"
    
    def duplicate_bulk_notification(self, request, queryset):
        count = 0
        for bulk_notification in queryset:
            # Create a copy
            new_bulk = BulkNotification.objects.create(
                title=f"Copy of {bulk_notification.title}",
                message=bulk_notification.message,
                short_message=bulk_notification.short_message,
                notification_type=bulk_notification.notification_type,
                sender=request.user,
                recipient_type=bulk_notification.recipient_type,
                target_roles=bulk_notification.target_roles,
                priority=bulk_notification.priority,
                action_url=bulk_notification.action_url,
                action_text=bulk_notification.action_text,
            )
            # Copy ManyToMany relationships
            new_bulk.target_branches.set(bulk_notification.target_branches.all())
            new_bulk.target_groups.set(bulk_notification.target_groups.all())
            new_bulk.target_courses.set(bulk_notification.target_courses.all())
            new_bulk.custom_recipients.set(bulk_notification.custom_recipients.all())
            count += 1
        self.message_user(request, f'Created {count} duplicated bulk notifications.')
    duplicate_bulk_notification.short_description = "Duplicate selected bulk notifications"


@admin.register(NotificationTemplate)
class NotificationTemplateAdmin(admin.ModelAdmin):
    list_display = ['name', 'notification_type', 'created_by', 'is_active', 'created_at']
    list_filter = ['notification_type', 'is_active', 'created_at', 'created_by']
    search_fields = ['name', 'description', 'title_template']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'description', 'notification_type', 'is_active')
        }),
        ('Template Content', {
            'fields': ('title_template', 'message_template', 'short_message_template')
        }),
        ('Default Settings', {
            'fields': ('default_priority', 'default_action_url', 'default_action_text')
        }),
        ('Template Variables', {
            'fields': ('available_variables',),
            'description': 'List the available variables for this template (e.g., ["user_name", "course_name", "deadline"])'
        }),
        ('Metadata', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def save_model(self, request, obj, form, change):
        if not change:  # If creating new object
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = ['action', 'user', 'notification', 'bulk_notification', 'timestamp']
    list_filter = ['action', 'timestamp', 'user__role']
    search_fields = ['user__username', 'notification__title', 'bulk_notification__title']
    readonly_fields = ['timestamp']
    date_hierarchy = 'timestamp'
    
    def has_add_permission(self, request):
        return False  # Don't allow manual creation of logs
    
    def has_change_permission(self, request, obj=None):
        return False  # Don't allow editing of logs



