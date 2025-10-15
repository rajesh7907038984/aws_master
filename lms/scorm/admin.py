"""
SCORM Admin Interface
"""
from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from .models import (
    SCORMPackage, SCORMAttempt, SCORMInteraction, 
    SCORMObjective, SCORMEvent
)


@admin.register(SCORMPackage)
class SCORMPackageAdmin(admin.ModelAdmin):
    """Admin interface for SCORM Packages"""
    list_display = [
        'title', 'package_type_badge', 'topic_link', 'file_size_display',
        'is_processed', 'created_by', 'created_at'
    ]
    list_filter = ['package_type', 'is_active', 'is_processed', 'created_at']
    search_fields = ['title', 'description', 'identifier']
    readonly_fields = [
        'id', 'created_at', 'updated_at', 'file_size', 'extracted_path',
        'manifest_data_display', 'launch_url_display'
    ]
    fieldsets = (
        ('Basic Information', {
            'fields': ('title', 'description', 'package_type', 'version')
        }),
        ('Files', {
            'fields': ('package_file', 'file_size', 'extracted_path', 'launch_file')
        }),
        ('Manifest Data', {
            'fields': ('identifier', 'manifest_data_display'),
            'classes': ('collapse',)
        }),
        ('Relationships', {
            'fields': ('topic', 'created_by')
        }),
        ('Status', {
            'fields': ('is_active', 'is_processed', 'processing_error')
        }),
        ('Metadata', {
            'fields': ('id', 'created_at', 'updated_at', 'launch_url_display'),
            'classes': ('collapse',)
        }),
    )
    
    def package_type_badge(self, obj):
        """Display package type with color badge"""
        colors = {
            'SCORM_12': 'blue',
            'SCORM_2004': 'green',
            'XAPI': 'purple',
            'ARTICULATE_RISE': 'orange',
            'ARTICULATE_STORYLINE': 'orange',
            'ADOBE_CAPTIVATE': 'red',
            'ISPRING': 'teal',
            'LECTORA': 'indigo',
            'HTML5': 'gray',
            'AUTO': 'lightgray',
        }
        color = colors.get(obj.package_type, 'gray')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-size: 11px;">{}</span>',
            color,
            obj.get_package_type_display()
        )
    package_type_badge.short_description = 'Type'
    
    def topic_link(self, obj):
        """Display link to topic"""
        if obj.topic:
            url = reverse('admin:courses_topic_change', args=[obj.topic.id])
            return format_html('<a href="{}">{}</a>', url, obj.topic.title)
        return '-'
    topic_link.short_description = 'Topic'
    
    def file_size_display(self, obj):
        """Display file size in human-readable format"""
        size = obj.file_size
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"
    file_size_display.short_description = 'File Size'
    
    def manifest_data_display(self, obj):
        """Display formatted manifest data"""
        import json
        if obj.manifest_data:
            formatted = json.dumps(obj.manifest_data, indent=2)
            return format_html('<pre style="background: #f5f5f5; padding: 10px;">{}</pre>', formatted)
        return '-'
    manifest_data_display.short_description = 'Manifest Data'
    
    def launch_url_display(self, obj):
        """Display launch URL"""
        url = obj.get_launch_url()
        if url:
            return format_html('<a href="{}" target="_blank">{}</a>', url, url)
        return '-'
    launch_url_display.short_description = 'Launch URL'


@admin.register(SCORMAttempt)
class SCORMAttemptAdmin(admin.ModelAdmin):
    """Admin interface for SCORM Attempts"""
    list_display = [
        'user', 'package', 'attempt_number', 'status_badge',
        'score_display', 'progress_display', 'started_at', 'time_spent'
    ]
    list_filter = ['lesson_status', 'completion_status', 'success_status', 'is_active', 'started_at']
    search_fields = ['user__username', 'user__email', 'package__title']
    readonly_fields = [
        'id', 'started_at', 'last_accessed', 'completed_at',
        'progress_display', 'cmi_data_display'
    ]
    fieldsets = (
        ('Basic Information', {
            'fields': ('package', 'user', 'topic', 'attempt_number', 'is_active')
        }),
        ('Status', {
            'fields': ('lesson_status', 'completion_status', 'success_status')
        }),
        ('Score', {
            'fields': ('score_raw', 'score_min', 'score_max', 'score_scaled')
        }),
        ('Progress', {
            'fields': ('lesson_location', 'suspend_data', 'progress_display')
        }),
        ('Time Tracking', {
            'fields': ('total_time', 'session_time', 'started_at', 'last_accessed', 'completed_at')
        }),
        ('Additional Data', {
            'fields': ('learner_response', 'learner_comments', 'exit_type'),
            'classes': ('collapse',)
        }),
        ('CMI Data', {
            'fields': ('cmi_data_display',),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('id',),
            'classes': ('collapse',)
        }),
    )
    
    def status_badge(self, obj):
        """Display status with color badge"""
        status = obj.lesson_status
        colors = {
            'completed': 'green',
            'passed': 'green',
            'incomplete': 'orange',
            'failed': 'red',
            'browsed': 'blue',
            'not attempted': 'gray',
        }
        color = colors.get(status, 'gray')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-size: 11px;">{}</span>',
            color,
            status.title()
        )
    status_badge.short_description = 'Status'
    
    def score_display(self, obj):
        """Display score information"""
        if obj.score_raw is not None:
            if obj.score_max is not None:
                return f"{obj.score_raw}/{obj.score_max}"
            return f"{obj.score_raw}"
        return '-'
    score_display.short_description = 'Score'
    
    def progress_display(self, obj):
        """Display progress percentage"""
        progress = obj.get_progress_percentage()
        return f"{progress}%"
    progress_display.short_description = 'Progress'
    
    def time_spent(self, obj):
        """Display time spent"""
        return obj.total_time if obj.total_time else '-'
    time_spent.short_description = 'Time'
    
    def cmi_data_display(self, obj):
        """Display formatted CMI data"""
        import json
        if obj.cmi_data:
            formatted = json.dumps(obj.cmi_data, indent=2)
            return format_html('<pre style="background: #f5f5f5; padding: 10px;">{}</pre>', formatted)
        return '-'
    cmi_data_display.short_description = 'CMI Data'


@admin.register(SCORMInteraction)
class SCORMInteractionAdmin(admin.ModelAdmin):
    """Admin interface for SCORM Interactions"""
    list_display = [
        'interaction_id', 'attempt', 'interaction_type',
        'result', 'timestamp'
    ]
    list_filter = ['interaction_type', 'result', 'timestamp']
    search_fields = ['interaction_id', 'description', 'attempt__user__username']
    readonly_fields = ['id', 'timestamp', 'raw_data_display']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('attempt', 'interaction_id', 'interaction_type', 'timestamp')
        }),
        ('Response', {
            'fields': ('learner_response', 'result', 'correct_response')
        }),
        ('Objectives', {
            'fields': ('objectives',)
        }),
        ('Additional Data', {
            'fields': ('weighting', 'latency', 'description'),
            'classes': ('collapse',)
        }),
        ('Raw Data', {
            'fields': ('raw_data_display',),
            'classes': ('collapse',)
        }),
    )
    
    def raw_data_display(self, obj):
        """Display formatted raw data"""
        import json
        if obj.raw_data:
            formatted = json.dumps(obj.raw_data, indent=2)
            return format_html('<pre style="background: #f5f5f5; padding: 10px;">{}</pre>', formatted)
        return '-'
    raw_data_display.short_description = 'Raw Data'


@admin.register(SCORMObjective)
class SCORMObjectiveAdmin(admin.ModelAdmin):
    """Admin interface for SCORM Objectives"""
    list_display = [
        'objective_id', 'attempt', 'status',
        'score_display', 'progress_measure', 'updated_at'
    ]
    list_filter = ['status', 'success_status', 'completion_status']
    search_fields = ['objective_id', 'description', 'attempt__user__username']
    readonly_fields = ['id', 'created_at', 'updated_at']
    
    def score_display(self, obj):
        """Display score information"""
        if obj.score_raw is not None:
            if obj.score_max is not None:
                return f"{obj.score_raw}/{obj.score_max}"
            return f"{obj.score_raw}"
        return '-'
    score_display.short_description = 'Score'


@admin.register(SCORMEvent)
class SCORMEventAdmin(admin.ModelAdmin):
    """Admin interface for SCORM Events"""
    list_display = [
        'event_type', 'attempt', 'element', 'result',
        'error_code', 'timestamp'
    ]
    list_filter = ['event_type', 'result', 'error_code', 'timestamp']
    search_fields = ['element', 'value', 'attempt__user__username']
    readonly_fields = ['id', 'timestamp', 'request_data_display']
    
    fieldsets = (
        ('Event Information', {
            'fields': ('attempt', 'event_type', 'element', 'value', 'timestamp')
        }),
        ('Result', {
            'fields': ('result', 'error_code', 'error_message')
        }),
        ('Session', {
            'fields': ('session_id',)
        }),
        ('Request Data', {
            'fields': ('request_data_display',),
            'classes': ('collapse',)
        }),
    )
    
    def request_data_display(self, obj):
        """Display formatted request data"""
        import json
        if obj.request_data:
            formatted = json.dumps(obj.request_data, indent=2)
            return format_html('<pre style="background: #f5f5f5; padding: 10px;">{}</pre>', formatted)
        return '-'
    request_data_display.short_description = 'Request Data'

