from django.contrib import admin
from django.contrib import messages
from django.utils.html import format_html
from .models import ScormPackage, ScormAttempt
# from .storyline_completion_fixer import ScormCompletionFixer  # Removed - file doesn't exist


@admin.action(description='Fix Storyline completion issues')
def fix_storyline_completion(modeladmin, request, queryset):
    """
    Admin action to fix Storyline completion issues for selected attempts
    """
    fixer = StorylineCompletionFixer()
    fixed_count = 0
    
    for attempt in queryset:
        if attempt.lesson_status == 'incomplete' and attempt.suspend_data:
            success, reason = fixer.fix_attempt(attempt)
            if success:
                fixed_count += 1
    
    if fixed_count > 0:
        messages.success(
            request, 
            f'Successfully fixed {fixed_count} Storyline completion issues!'
        )
    else:
        messages.info(
            request, 
            'No Storyline completion issues found in selected attempts.'
        )


@admin.register(ScormPackage)
class ScormPackageAdmin(admin.ModelAdmin):
    list_display = ['title', 'version', 'status', 'extract_status', 'topic', 'created_at', 'version_indicator']
    list_filter = ['version', 'status', 'extract_status', 'runtime_api', 'lms_launch_type', 'created_at']
    search_fields = ['title', 'identifier', 'topic__title', 'organization']
    readonly_fields = ['created_at', 'updated_at', 'extracted_path', 'identifier', 'size']
    
    def version_indicator(self, obj):
        """Show SCORM version with Storyline indicator"""
        version = getattr(obj, 'version', 'Unknown')
        if version == 'storyline':
            return format_html('<span style="color: blue;">📚 Storyline</span>')
        else:
            return version
    
    version_indicator.short_description = 'SCORM Type'
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('topic', 'title', 'description', 'status')
        }),
        ('Package Details', {
            'fields': ('version', 'identifier', 'organization', 'entry_point', 'launch_url')
        }),
        ('File Management', {
            'fields': ('package_file', 'extracted_path', 'size', 'extract_status')
        }),
        ('Technical Settings', {
            'fields': ('runtime_api', 'lms_launch_type', 'is_multi_sco', 'mastery_score', 'has_score_requirement')
        }),
        ('Metadata', {
            'fields': ('metadata', 'duration_estimate'),
            'classes': ('collapse',)
        }),
        ('Audit Information', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(ScormAttempt)
class ScormAttemptAdmin(admin.ModelAdmin):
    list_display = [
        'user', 'scorm_package', 'attempt_number', 'lesson_status', 
        'completion_status', 'score_raw', 'started_at', 'completion_indicator'
    ]
    list_filter = ['lesson_status', 'completion_status', 'started_at']
    search_fields = ['user__username', 'user__email', 'scorm_package__title']
    readonly_fields = ['started_at', 'last_accessed', 'completed_at']
    actions = [fix_storyline_completion]
    
    def completion_indicator(self, obj):
        """Show completion status using proper SCORM CMI data"""
        if not obj.suspend_data:
            return "No suspend data"
        
        # Use CMI completion status instead of custom calculations
        if obj.completion_status in ['completed', 'passed']:
            return format_html('<span style="color: green;">✅ Complete (CMI)</span>')
        elif obj.completion_status == 'failed':
            return format_html('<span style="color: red;">❌ Failed (CMI)</span>')
        elif obj.lesson_status in ['completed', 'passed']:
            return format_html('<span style="color: green;">✅ Complete (Lesson)</span>')
        elif obj.success_status == 'passed':
            return format_html('<span style="color: green;">✅ Passed (Success)</span>')
        elif obj.success_status == 'failed':
            return format_html('<span style="color: red;">❌ Failed (Success)</span>')
        else:
            return format_html('<span style="color: orange;">⚠️ Incomplete</span>')
    
    completion_indicator.short_description = 'Slide Progress'
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('user', 'scorm_package', 'attempt_number')
        }),
        ('Status', {
            'fields': ('lesson_status', 'completion_status', 'success_status', 'entry', 'exit_mode')
        }),
        ('Score', {
            'fields': ('score_raw', 'score_min', 'score_max', 'score_scaled')
        }),
        ('Time Tracking', {
            'fields': ('total_time', 'session_time', 'time_spent_seconds', 'session_start_time', 'session_end_time')
        }),
        ('Location & Suspend Data', {
            'fields': ('lesson_location', 'suspend_data')
        }),
        ('SCORM 1.2 Data', {
            'fields': ('cmi_student_preferences', 'cmi_objectives_12', 'cmi_interactions_12'),
            'classes': ('collapse',)
        }),
        ('SCORM 2004 Data', {
            'fields': ('cmi_comments_from_learner', 'cmi_comments_from_lms', 'cmi_objectives_2004', 'cmi_interactions_2004'),
            'classes': ('collapse',)
        }),
        ('xAPI Event Data', {
            'fields': ('xapi_events', 'xapi_actor', 'xapi_verb', 'xapi_object', 'xapi_result', 'xapi_context', 'xapi_timestamp', 'xapi_stored', 'xapi_authority', 'xapi_version', 'xapi_attachments'),
            'classes': ('collapse',)
        }),
        ('CMI Data Storage', {
            'fields': ('cmi_data', 'cmi_data_history'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('started_at', 'last_accessed', 'completed_at')
        }),
    )

