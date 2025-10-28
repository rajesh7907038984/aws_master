from django.contrib import admin
from django.contrib import messages
from django.utils.html import format_html
from .models import ScormPackage, ScormAttempt
from .storyline_completion_fixer import StorylineCompletionFixer


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
    list_display = ['title', 'version', 'topic', 'created_at', 'version_indicator']
    list_filter = ['version', 'created_at']
    search_fields = ['title', 'identifier', 'topic__title']
    readonly_fields = ['created_at', 'updated_at', 'extracted_path', 'identifier']
    
    def version_indicator(self, obj):
        """Show SCORM version with Storyline indicator"""
        version = getattr(obj, 'version', 'Unknown')
        if version == 'storyline':
            return format_html('<span style="color: blue;">📚 Storyline</span>')
        else:
            return version
    
    version_indicator.short_description = 'SCORM Type'


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
        """Show completion indicators from suspend data"""
        if not obj.suspend_data:
            return "No suspend data"
        
        visited_count = obj.suspend_data.count('Visited')
        has_100 = '100' in obj.suspend_data
        
        if visited_count >= 3 and has_100:
            return format_html(
                '<span style="color: green;">✅ Complete ({})</span>', 
                visited_count
            )
        elif visited_count >= 3:
            return format_html(
                '<span style="color: orange;">⚠️ Partial ({})</span>', 
                visited_count
            )
        else:
            return format_html(
                '<span style="color: red;">❌ Incomplete ({})</span>', 
                visited_count
            )
    
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
            'fields': ('total_time', 'session_time')
        }),
        ('Location & Suspend Data', {
            'fields': ('lesson_location', 'suspend_data')
        }),
        ('Timestamps', {
            'fields': ('started_at', 'last_accessed', 'completed_at')
        }),
    )

