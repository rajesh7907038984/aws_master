from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from .models import (
    Conference, 
    ConferenceAttendance, 
    ConferenceRecording, 
    ConferenceFile, 
    ConferenceChat, 
    ConferenceSyncLog,
    BranchZoomAccess,
    GuestParticipant,
    ConferenceRubricEvaluation,
    ConferenceParticipant,
    ParticipantTrackingData,
    ConferenceTimeSlot,
    ConferenceTimeSlotSelection
)
from django.db.models import Q


@admin.register(Conference)
class ConferenceAdmin(admin.ModelAdmin):
    list_display = ['title', 'date', 'start_time', 'timezone', 'meeting_platform', 'meeting_status', 'allowed_join_methods', 'data_sync_status', 'created_by', 'get_branch', 'participant_count']
    list_filter = ['meeting_platform', 'meeting_status', 'allowed_join_methods', 'data_sync_status', 'status', 'date', 'timezone', 'created_by__branch']
    search_fields = ['title', 'description', 'meeting_id', 'created_by__username', 'created_by__branch__name']
    readonly_fields = ['created_at', 'updated_at', 'last_sync_at']
    
    def get_branch(self, obj):
        return obj.created_by.branch.name if obj.created_by.branch else 'No Branch'
    get_branch.short_description = 'Branch'
    get_branch.admin_order_field = 'created_by__branch__name'
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.role in ['globaladmin', 'superadmin'] or request.user.is_superuser:
            return qs
        elif request.user.role == 'admin':
            # Branch admins see only their branch conferences
            return qs.filter(created_by__branch=request.user.branch)
        elif request.user.role == 'instructor':
            # Instructors see conferences they created or are assigned to
            return qs.filter(created_by=request.user)
        else:
            # Learners have no admin access
            return qs.none()
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('title', 'description', 'course', 'rubric')
        }),
        ('Schedule', {
            'fields': ('date', 'start_time', 'end_time', 'timezone', 'status', 'visibility')
        }),
        ('Access Control', {
            'fields': ('default_join_type', 'join_experience', 'allowed_join_methods'),
            'classes': ['collapse'],
            'description': 'Configure who can access this conference and which join methods are allowed.'
        }),
        ('Meeting Details', {
            'fields': ('meeting_platform', 'meeting_link', 'meeting_id', 'meeting_password', 'host_url')
        }),
        ('Status Tracking', {
            'fields': ('meeting_status', 'data_sync_status', 'last_sync_at', 'auto_recording_status', 'auto_recording_enabled_at')
        }),
        ('Metadata', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ['collapse']
        })
    )

    def participant_count(self, obj):
        return obj.participants.count()
    participant_count.short_description = 'Participants'


@admin.register(BranchZoomAccess)
class BranchZoomAccessAdmin(admin.ModelAdmin):
    list_display = ['branch', 'zoom_integration', 'permission_level', 'can_create_meetings', 'can_view_recordings', 'created_at']
    list_filter = ['permission_level', 'can_create_meetings', 'can_view_recordings', 'created_at']
    search_fields = ['branch__name', 'zoom_integration__user__username', 'zoom_integration__user__first_name', 'zoom_integration__user__last_name']
    readonly_fields = ['created_at', 'updated_at']
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.role in ['globaladmin', 'superadmin'] or request.user.is_superuser:
            return qs
        elif request.user.role == 'admin':
            # Branch admins see access permissions for their branch
            return qs.filter(branch=request.user.branch)
        else:
            return qs.none()
    
    fieldsets = (
        ('Access Configuration', {
            'fields': ('branch', 'zoom_integration', 'permission_level')
        }),
        ('Granular Permissions', {
            'fields': ('can_create_meetings', 'can_view_recordings', 'can_view_attendance', 'can_view_chat_logs', 'can_download_files'),
            'classes': ['collapse']
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ['collapse']
        })
    )


@admin.register(ConferenceAttendance)
class ConferenceAttendanceAdmin(admin.ModelAdmin):
    list_display = ['conference', 'user', 'attendance_status', 'duration_minutes', 'join_time', 'get_branch']
    list_filter = ['attendance_status', 'conference__meeting_platform', 'join_time', 'user__branch']
    search_fields = ['conference__title', 'user__username', 'user__first_name', 'user__last_name', 'user__branch__name']
    readonly_fields = ['created_at', 'updated_at']
    
    def get_branch(self, obj):
        return obj.user.branch.name if obj.user.branch else 'No Branch'
    get_branch.short_description = 'User Branch'
    get_branch.admin_order_field = 'user__branch__name'
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.role in ['globaladmin', 'superadmin'] or request.user.is_superuser:
            return qs
        elif request.user.role == 'admin':
            # Branch admins see attendance for their branch users
            return qs.filter(user__branch=request.user.branch)
        elif request.user.role == 'instructor':
            # Instructors see attendance for conferences they created
            return qs.filter(conference__created_by=request.user)
        else:
            return qs.none()
    

@admin.register(ConferenceRecording)
class ConferenceRecordingAdmin(admin.ModelAdmin):
    list_display = ['title', 'conference', 'recording_type', 'status', 'duration_minutes', 'file_size', 'get_branch']
    list_filter = ['recording_type', 'status', 'file_format', 'created_at', 'conference__created_by__branch']
    search_fields = ['title', 'conference__title', 'recording_id', 'conference__created_by__branch__name']
    readonly_fields = ['created_at', 'updated_at']
    
    def get_branch(self, obj):
        return obj.conference.created_by.branch.name if obj.conference.created_by.branch else 'No Branch'
    get_branch.short_description = 'Conference Branch'
    get_branch.admin_order_field = 'conference__created_by__branch__name'
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.role in ['globaladmin', 'superadmin'] or request.user.is_superuser:
            return qs
        elif request.user.role == 'admin':
            # Branch admins see recordings for their branch conferences
            return qs.filter(conference__created_by__branch=request.user.branch)
        elif request.user.role == 'instructor':
            # Instructors see recordings for conferences they created
            return qs.filter(conference__created_by=request.user)
        else:
            return qs.none()


@admin.register(ConferenceFile)
class ConferenceFileAdmin(admin.ModelAdmin):
    list_display = ['filename', 'conference', 'shared_by', 'file_type', 'file_size', 'shared_at', 'get_branch']
    list_filter = ['file_type', 'shared_at', 'conference__meeting_platform', 'shared_by__branch']
    search_fields = ['filename', 'original_filename', 'conference__title', 'shared_by__branch__name']
    readonly_fields = ['created_at', 'updated_at']
    
    def get_branch(self, obj):
        return obj.shared_by.branch.name if obj.shared_by.branch else 'No Branch'
    get_branch.short_description = 'Shared By Branch'
    get_branch.admin_order_field = 'shared_by__branch__name'
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.role in ['globaladmin', 'superadmin'] or request.user.is_superuser:
            return qs
        elif request.user.role == 'admin':
            # Branch admins see files for their branch conferences
            return qs.filter(conference__created_by__branch=request.user.branch)
        elif request.user.role == 'instructor':
            # Instructors see files for conferences they created
            return qs.filter(conference__created_by=request.user)
        else:
            return qs.none()


@admin.register(ConferenceChat)
class ConferenceChatAdmin(admin.ModelAdmin):
    list_display = ['conference', 'sender_name', 'message_type', 'sent_at', 'get_branch']
    list_filter = ['message_type', 'sent_at', 'conference__meeting_platform']
    search_fields = ['conference__title', 'sender_name', 'message_text']
    readonly_fields = ['created_at']
    
    def get_branch(self, obj):
        if obj.sender and obj.sender.branch:
            return obj.sender.branch.name
        return obj.conference.created_by.branch.name if obj.conference.created_by.branch else 'No Branch'
    get_branch.short_description = 'Branch'
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.role in ['globaladmin', 'superadmin'] or request.user.is_superuser:
            return qs
        elif request.user.role == 'admin':
            # Branch admins see chat for conferences in their branch
            return qs.filter(conference__created_by__branch=request.user.branch)
        elif request.user.role == 'instructor':
            # Instructors see chat for conferences they created
            return qs.filter(conference__created_by=request.user)
        else:
            return qs.none()


@admin.register(ConferenceSyncLog)
class ConferenceSyncLogAdmin(admin.ModelAdmin):
    list_display = ['conference', 'sync_type', 'status', 'items_processed', 'items_failed', 'started_at', 'sync_duration_seconds']
    list_filter = ['sync_type', 'status', 'started_at', 'conference__meeting_platform']
    search_fields = ['conference__title']
    readonly_fields = ['started_at', 'completed_at']
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.role in ['globaladmin', 'superadmin'] or request.user.is_superuser:
            return qs
        elif request.user.role == 'admin':
            # Branch admins see sync logs for conferences in their branch
            return qs.filter(conference__created_by__branch=request.user.branch)
        elif request.user.role == 'instructor':
            # Instructors see sync logs for conferences they created
            return qs.filter(conference__created_by=request.user)
        else:
            return qs.none()


@admin.register(GuestParticipant)
class GuestParticipantAdmin(admin.ModelAdmin):
    list_display = ['conference', 'participation_id', 'guest_name', 'guest_email', 'participation_status', 'join_time', 'session_duration_minutes']
    list_filter = ['participation_status', 'join_time', 'conference__meeting_platform']
    search_fields = ['conference__title', 'guest_name', 'guest_email', 'participation_id']
    readonly_fields = ['created_at', 'updated_at']
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.role in ['globaladmin', 'superadmin'] or request.user.is_superuser:
            return qs
        elif request.user.role == 'admin':
            # Branch admins see guest participants for conferences in their branch
            return qs.filter(conference__created_by__branch=request.user.branch)
        elif request.user.role == 'instructor':
            # Instructors see guest participants for conferences they created
            return qs.filter(conference__created_by=request.user)
        else:
            return qs.none()


from .models import ConferenceRubricEvaluation

@admin.register(ConferenceRubricEvaluation)
class ConferenceRubricEvaluationAdmin(admin.ModelAdmin):
    list_display = ['conference', 'get_student', 'criterion', 'points', 'evaluated_by', 'created_at']
    list_filter = ['conference', 'criterion__rubric', 'evaluated_by', 'created_at']
    search_fields = ['conference__title', 'attendance__user__username', 'attendance__user__first_name', 'attendance__user__last_name', 'criterion__description']
    readonly_fields = ['created_at', 'updated_at']
    
    def get_student(self, obj):
        return obj.attendance.user.get_full_name() if obj.attendance.user else 'Unknown'
    get_student.short_description = 'Student'
    get_student.admin_order_field = 'attendance__user__first_name'
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.role in ['globaladmin', 'superadmin'] or request.user.is_superuser:
            return qs
        elif request.user.role == 'admin':
            # Branch admins see evaluations for conferences in their branch
            return qs.filter(conference__created_by__branch=request.user.branch)
        elif request.user.role == 'instructor':
            # Instructors see evaluations for conferences they created or evaluated
            return qs.filter(
                Q(conference__created_by=request.user) | Q(evaluated_by=request.user)
            )
        else:
            return qs.none()


@admin.register(ConferenceParticipant)
class ConferenceParticipantAdmin(admin.ModelAdmin):
    list_display = [
        'display_name', 'user', 'conference', 'participation_status', 
        'click_timestamp', 'total_duration_minutes', 'attendance_percentage', 'sync_status'
    ]
    list_filter = [
        'participation_status', 'sync_status', 'conference__meeting_platform',
        'click_timestamp', 'conference'
    ]
    search_fields = [
        'display_name', 'user__username', 'user__email', 'participant_id',
        'conference__title', 'email_address'
    ]
    readonly_fields = [
        'participant_id', 'session_token', 'click_timestamp', 'created_at', 'updated_at',
        'tracking_data_display', 'participant_url'
    ]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('conference', 'user', 'display_name', 'email_address')
        }),
        ('Tracking Identifiers', {
            'fields': ('participant_id', 'session_token', 'participant_url'),
            'classes': ('collapse',)
        }),
        ('Participation Status', {
            'fields': ('participation_status', 'click_timestamp', 'join_timestamp', 'leave_timestamp')
        }),
        ('Platform Data', {
            'fields': ('platform_participant_id', 'platform_user_id', 'platform_session_id'),
            'classes': ('collapse',)
        }),
        ('Device Information', {
            'fields': ('ip_address', 'user_agent', 'device_fingerprint'),
            'classes': ('collapse',)
        }),
        ('Attendance Metrics', {
            'fields': ('total_duration_minutes', 'attendance_percentage')
        }),
        ('Sync Status', {
            'fields': ('sync_status', 'last_sync_at', 'sync_errors')
        }),
        ('Tracking Data', {
            'fields': ('tracking_data_display',),
            'classes': ('collapse',)
        }),
    )
    
    def tracking_data_display(self, obj):
        """Display tracking data in a formatted way"""
        if obj.tracking_data:
            import json
            formatted_data = json.dumps(obj.tracking_data, indent=2)
            return format_html('<pre>{}</pre>', formatted_data)
        return 'No tracking data'
    tracking_data_display.short_description = 'Tracking Data (JSON)'
    
    def participant_url(self, obj):
        """Generate the tracking URL for this participant"""
        if obj.conference and obj.conference.meeting_link:
            tracking_url = obj.generate_tracking_url(obj.conference.meeting_link)
            return format_html('<a href="{}" target="_blank">{}</a>', tracking_url, tracking_url)
        return 'No meeting link'
    participant_url.short_description = 'Tracking URL'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'conference')


@admin.register(ParticipantTrackingData)
class ParticipantTrackingDataAdmin(admin.ModelAdmin):
    list_display = [
        'participant', 'data_type', 'recorded_at', 'synced_at', 
        'data_quality_score', 'has_errors'
    ]
    list_filter = [
        'data_type', 'has_errors', 'recorded_at', 'synced_at',
        'participant__conference', 'data_quality_score'
    ]
    search_fields = [
        'participant__display_name', 'participant__user__username',
        'participant__participant_id', 'error_details'
    ]
    readonly_fields = [
        'synced_at', 'platform_data_display', 'processed_data_display'
    ]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('participant', 'data_type', 'recorded_at')
        }),
        ('Data Quality', {
            'fields': ('data_quality_score', 'has_errors', 'error_details')
        }),
        ('Platform Data', {
            'fields': ('platform_data_display',),
            'classes': ('collapse',)
        }),
        ('Processed Data', {
            'fields': ('processed_data_display',),
            'classes': ('collapse',)
        }),
    )
    
    def platform_data_display(self, obj):
        """Display platform data in a formatted way"""
        if obj.platform_data:
            import json
            formatted_data = json.dumps(obj.platform_data, indent=2)
            return format_html('<pre>{}</pre>', formatted_data)
        return 'No platform data'
    platform_data_display.short_description = 'Platform Data (JSON)'
    
    def processed_data_display(self, obj):
        """Display processed data in a formatted way"""
        if obj.processed_data:
            import json
            formatted_data = json.dumps(obj.processed_data, indent=2)
            return format_html('<pre>{}</pre>', formatted_data)
        return 'No processed data'
    processed_data_display.short_description = 'Processed Data (JSON)'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('participant', 'participant__user', 'participant__conference')


# Update the existing ConferenceAdmin to show participant count
class ConferenceParticipantInline(admin.TabularInline):
    model = ConferenceParticipant
    extra = 0
    readonly_fields = ['participant_id', 'participation_status', 'click_timestamp', 'total_duration_minutes']
    fields = ['user', 'display_name', 'participation_status', 'click_timestamp', 'total_duration_minutes']
    
    def has_add_permission(self, request, obj=None):
        return False  # Don't allow manual creation through admin


# Add the inline to the existing ConferenceAdmin if it exists
try:
    existing_conference_admin = admin.site._registry[Conference]
    if hasattr(existing_conference_admin, 'inlines'):
        existing_conference_admin.inlines = list(existing_conference_admin.inlines) + [ConferenceParticipantInline]
    else:
        existing_conference_admin.inlines = [ConferenceParticipantInline]
except:
    # If ConferenceAdmin doesn't exist, create a basic one
    @admin.register(Conference)
    class ConferenceAdmin(admin.ModelAdmin):
        list_display = ['title', 'date', 'start_time', 'meeting_platform', 'meeting_status', 'participant_count']
        list_filter = ['meeting_platform', 'meeting_status', 'date']
        search_fields = ['title', 'description']
        inlines = [ConferenceParticipantInline]
        
        def participant_count(self, obj):
            return obj.participants.count()
        participant_count.short_description = 'Participants'


@admin.register(ConferenceTimeSlot)
class ConferenceTimeSlotAdmin(admin.ModelAdmin):
    list_display = ['conference', 'date', 'start_time', 'end_time', 'timezone', 'current_participants', 'max_participants', 'is_available']
    list_filter = ['is_available', 'date', 'conference']
    search_fields = ['conference__title']
    readonly_fields = ['created_at', 'updated_at', 'current_participants']
    
    fieldsets = (
        ('Conference', {
            'fields': ('conference',)
        }),
        ('Time Slot Details', {
            'fields': ('date', 'start_time', 'end_time', 'timezone')
        }),
        ('Capacity', {
            'fields': ('max_participants', 'current_participants', 'is_available')
        }),
        ('Meeting Details', {
            'fields': ('meeting_link', 'meeting_id', 'meeting_password'),
            'classes': ['collapse']
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ['collapse']
        })
    )
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.role in ['globaladmin', 'superadmin'] or request.user.is_superuser:
            return qs
        elif request.user.role == 'admin':
            return qs.filter(conference__created_by__branch=request.user.branch)
        elif request.user.role == 'instructor':
            return qs.filter(conference__created_by=request.user)
        else:
            return qs.none()


@admin.register(ConferenceTimeSlotSelection)
class ConferenceTimeSlotSelectionAdmin(admin.ModelAdmin):
    list_display = ['user', 'conference', 'time_slot', 'selected_at', 'calendar_added', 'get_slot_details']
    list_filter = ['calendar_added', 'selected_at', 'time_slot__date']
    search_fields = ['user__username', 'user__first_name', 'user__last_name', 'conference__title']
    readonly_fields = ['selected_at', 'ip_address', 'outlook_event_id', 'calendar_add_attempted_at']
    
    fieldsets = (
        ('Selection Details', {
            'fields': ('conference', 'time_slot', 'user')
        }),
        ('Outlook Integration', {
            'fields': ('outlook_event_id', 'calendar_added', 'calendar_add_attempted_at', 'calendar_error')
        }),
        ('Metadata', {
            'fields': ('selected_at', 'ip_address'),
            'classes': ['collapse']
        })
    )
    
    def get_slot_details(self, obj):
        return f"{obj.time_slot.date} {obj.time_slot.start_time} - {obj.time_slot.end_time}"
    get_slot_details.short_description = 'Time Slot'
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.role in ['globaladmin', 'superadmin'] or request.user.is_superuser:
            return qs
        elif request.user.role == 'admin':
            return qs.filter(conference__created_by__branch=request.user.branch)
        elif request.user.role == 'instructor':
            return qs.filter(conference__created_by=request.user)
        else:
            # Learners can only see their own selections
            return qs.filter(user=request.user)



