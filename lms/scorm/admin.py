from django.contrib import admin
from .models import ScormPackage, ScormAttempt


@admin.register(ScormPackage)
class ScormPackageAdmin(admin.ModelAdmin):
    list_display = ['title', 'version', 'topic', 'created_at']
    list_filter = ['version', 'created_at']
    search_fields = ['title', 'identifier', 'topic__title']
    readonly_fields = ['created_at', 'updated_at', 'extracted_path', 'identifier']


@admin.register(ScormAttempt)
class ScormAttemptAdmin(admin.ModelAdmin):
    list_display = ['user', 'scorm_package', 'attempt_number', 'lesson_status', 'score_raw', 'started_at']
    list_filter = ['lesson_status', 'completion_status', 'started_at']
    search_fields = ['user__username', 'user__email', 'scorm_package__title']
    readonly_fields = ['started_at', 'last_accessed', 'completed_at']
    
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
            'fields': ('total_time', 'session_time')
        }),
        ('Location & Suspend Data', {
            'fields': ('lesson_location', 'suspend_data')
        }),
        ('Timestamps', {
            'fields': ('started_at', 'last_accessed', 'completed_at')
        }),
    )

