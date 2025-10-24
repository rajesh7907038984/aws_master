"""
Teams Integration Admin Configuration
"""

from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone
from .models import (
    TeamsSyncLog,
    TeamsMeetingSync,
    EntraGroupMapping,
    TeamsUserSync
)


@admin.register(TeamsSyncLog)
class TeamsSyncLogAdmin(admin.ModelAdmin):
    """Admin interface for Teams sync logs"""
    
    list_display = [
        'integration_name',
        'sync_type',
        'status',
        'started_at',
        'duration_display',
        'items_processed',
        'items_created',
        'items_updated',
        'items_failed'
    ]
    
    list_filter = [
        'sync_type',
        'status',
        'sync_direction',
        'started_at',
        'integration__branch'
    ]
    
    search_fields = [
        'integration__name',
        'error_message',
        'initiated_by__username'
    ]
    
    readonly_fields = [
        'started_at',
        'completed_at',
        'duration_seconds',
        'sync_metadata',
        'api_response'
    ]
    
    fieldsets = (
        ('Sync Information', {
            'fields': (
                'integration',
                'sync_type',
                'status',
                'sync_direction',
                'initiated_by'
            )
        }),
        ('Timing', {
            'fields': (
                'started_at',
                'completed_at',
                'duration_seconds'
            )
        }),
        ('Statistics', {
            'fields': (
                'items_processed',
                'items_created',
                'items_updated',
                'items_failed'
            )
        }),
        ('Error Information', {
            'fields': (
                'error_message',
                'error_details'
            ),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': (
                'sync_metadata',
                'api_response'
            ),
            'classes': ('collapse',)
        })
    )
    
    def integration_name(self, obj):
        """Display integration name with link"""
        if obj.integration:
            url = reverse('admin:account_settings_teamsintegration_change', args=[obj.integration.id])
            return format_html('<a href="{}">{}</a>', url, obj.integration.name)
        return '-'
    integration_name.short_description = 'Integration'
    
    def duration_display(self, obj):
        """Display duration in human-readable format"""
        if obj.duration_seconds:
            minutes = obj.duration_seconds // 60
            seconds = obj.duration_seconds % 60
            return f"{minutes}m {seconds}s"
        return '-'
    duration_display.short_description = 'Duration'
    
    def get_queryset(self, request):
        """Optimize queryset"""
        return super().get_queryset(request).select_related(
            'integration',
            'initiated_by'
        )


@admin.register(TeamsMeetingSync)
class TeamsMeetingSyncAdmin(admin.ModelAdmin):
    """Admin interface for Teams meeting sync"""
    
    list_display = [
        'conference_title',
        'teams_meeting_id',
        'meeting_status',
        'attendance_synced',
        'recordings_synced',
        'chat_synced',
        'files_synced',
        'total_participants',
        'last_sync'
    ]
    
    list_filter = [
        'meeting_status',
        'attendance_synced',
        'recordings_synced',
        'chat_synced',
        'files_synced',
        'created_at'
    ]
    
    search_fields = [
        'conference__title',
        'teams_meeting_id',
        'last_error'
    ]
    
    readonly_fields = [
        'created_at',
        'updated_at',
        'sync_errors',
        'retry_count'
    ]
    
    fieldsets = (
        ('Meeting Information', {
            'fields': (
                'conference',
                'teams_meeting_id',
                'teams_meeting_url',
                'meeting_status',
                'meeting_duration_minutes',
                'total_participants'
            )
        }),
        ('Sync Status', {
            'fields': (
                'attendance_synced',
                'recordings_synced',
                'chat_synced',
                'files_synced'
            )
        }),
        ('Sync Timestamps', {
            'fields': (
                'last_attendance_sync',
                'last_recording_sync',
                'last_chat_sync',
                'last_file_sync'
            )
        }),
        ('Error Information', {
            'fields': (
                'sync_errors',
                'retry_count',
                'last_error'
            ),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': (
                'created_at',
                'updated_at'
            )
        })
    )
    
    def conference_title(self, obj):
        """Display conference title with link"""
        if obj.conference:
            url = reverse('admin:conferences_conference_change', args=[obj.conference.id])
            return format_html('<a href="{}">{}</a>', url, obj.conference.title)
        return '-'
    conference_title.short_description = 'Conference'
    
    def last_sync(self, obj):
        """Display last sync time"""
        sync_times = [
            obj.last_attendance_sync,
            obj.last_recording_sync,
            obj.last_chat_sync,
            obj.last_file_sync
        ]
        sync_times = [t for t in sync_times if t]
        if sync_times:
            latest = max(sync_times)
            return latest.strftime('%Y-%m-%d %H:%M:%S')
        return 'Never'
    last_sync.short_description = 'Last Sync'


@admin.register(EntraGroupMapping)
class EntraGroupMappingAdmin(admin.ModelAdmin):
    """Admin interface for Entra group mappings"""
    
    list_display = [
        'entra_group_name',
        'lms_group_name',
        'target_group_type',
        'target_course',
        'integration_name',
        'is_active',
        'auto_sync_enabled',
        'last_sync_status',
        'last_sync_at',
        'total_users_synced'
    ]
    
    list_filter = [
        'is_active',
        'auto_sync_enabled',
        'target_group_type',
        'last_sync_status',
        'integration__branch',
        'created_at'
    ]
    
    search_fields = [
        'entra_group_name',
        'entra_group_email',
        'lms_group__name',
        'integration__name'
    ]
    
    readonly_fields = [
        'created_at',
        'updated_at',
        'sync_error',
        'retry_count'
    ]
    
    fieldsets = (
        ('Group Mapping', {
            'fields': (
                'integration',
                'entra_group_id',
                'entra_group_name',
                'entra_group_email',
                'lms_group',
                'target_group_type',
                'target_course'
            )
        }),
        ('Sync Configuration', {
            'fields': (
                'is_active',
                'auto_sync_enabled',
                'sync_frequency_minutes'
            )
        }),
        ('Sync Status', {
            'fields': (
                'last_sync_at',
                'last_sync_status',
                'total_users_synced',
                'last_sync_users_count'
            )
        }),
        ('Error Information', {
            'fields': (
                'sync_error',
                'retry_count'
            ),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': (
                'created_at',
                'updated_at'
            )
        })
    )
    
    def integration_name(self, obj):
        """Display integration name"""
        return obj.integration.name if obj.integration else '-'
    integration_name.short_description = 'Integration'
    
    def lms_group_name(self, obj):
        """Display LMS group name with link"""
        if obj.lms_group:
            url = reverse('admin:groups_branchgroup_change', args=[obj.lms_group.id])
            return format_html('<a href="{}">{}</a>', url, obj.lms_group.name)
        return '-'
    lms_group_name.short_description = 'LMS Group'
    
    def target_course(self, obj):
        """Display target course with link"""
        if obj.target_course:
            url = reverse('admin:courses_course_change', args=[obj.target_course.id])
            return format_html('<a href="{}">{}</a>', url, obj.target_course.title)
        return '-'
    target_course.short_description = 'Target Course'
    
    def get_queryset(self, request):
        """Optimize queryset"""
        return super().get_queryset(request).select_related(
            'integration',
            'lms_group',
            'target_course'
        )


@admin.register(TeamsUserSync)
class TeamsUserSyncAdmin(admin.ModelAdmin):
    """Admin interface for Teams user sync"""
    
    list_display = [
        'user_username',
        'entra_email',
        'entra_display_name',
        'sync_status',
        'last_sync_at',
        'entra_groups_count',
        'lms_groups_count'
    ]
    
    list_filter = [
        'sync_status',
        'last_sync_at',
        'user__branch'
    ]
    
    search_fields = [
        'user__username',
        'user__email',
        'entra_email',
        'entra_display_name',
        'entra_user_id'
    ]
    
    readonly_fields = [
        'created_at',
        'updated_at',
        'sync_metadata'
    ]
    
    fieldsets = (
        ('User Information', {
            'fields': (
                'user',
                'entra_user_id',
                'entra_email',
                'entra_display_name'
            )
        }),
        ('Sync Status', {
            'fields': (
                'sync_status',
                'last_sync_at',
                'sync_error'
            )
        }),
        ('Group Memberships', {
            'fields': (
                'entra_groups',
                'lms_groups'
            )
        }),
        ('Metadata', {
            'fields': (
                'sync_metadata',
            ),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': (
                'created_at',
                'updated_at'
            )
        })
    )
    
    def user_username(self, obj):
        """Display user username with link"""
        if obj.user:
            url = reverse('admin:users_customuser_change', args=[obj.user.id])
            return format_html('<a href="{}">{}</a>', url, obj.user.username)
        return '-'
    user_username.short_description = 'User'
    
    def entra_groups_count(self, obj):
        """Display number of Entra groups"""
        if obj.entra_groups:
            return len(obj.entra_groups)
        return 0
    entra_groups_count.short_description = 'Entra Groups'
    
    def lms_groups_count(self, obj):
        """Display number of LMS groups"""
        if obj.lms_groups:
            return len(obj.lms_groups)
        return 0
    lms_groups_count.short_description = 'LMS Groups'
    
    def get_queryset(self, request):
        """Optimize queryset"""
        return super().get_queryset(request).select_related('user')
