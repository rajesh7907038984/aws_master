from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from .models import ELearningPackage, ELearningTracking, SCORMReport, SCORMPackage, SCORMTracking

@admin.register(ELearningPackage)
class ELearningPackageAdmin(admin.ModelAdmin):
    list_display = [
        'topic', 'package_type', 'title', 'version', 'is_extracted', 
        'created_at', 'launch_url_link'
    ]
    list_filter = ['package_type', 'is_extracted', 'created_at', 'version']
    search_fields = ['title', 'topic__title', 'description']
    readonly_fields = [
        'extracted_path', 'manifest_path', 'launch_file',
        'created_at', 'updated_at', 'extraction_error'
    ]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('topic', 'package_file', 'package_type', 'title', 'description')
        }),
        ('Package Metadata', {
            'fields': ('version', 'organization')
        }),
        ('xAPI Settings', {
            'fields': ('xapi_endpoint', 'xapi_actor'),
            'classes': ('collapse',)
        }),
        ('cmi5 Settings', {
            'fields': ('cmi5_au_id', 'cmi5_launch_url'),
            'classes': ('collapse',)
        }),
        ('Extraction Details', {
            'fields': (
                'is_extracted', 'extracted_path', 'manifest_path', 
                'launch_file', 'extraction_error'
            ),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def launch_url_link(self, obj):
        if obj.is_extracted:
            url = obj.get_launch_url()
            return format_html('<a href="{}" target="_blank">Launch {}</a>', url, obj.get_package_type_display())
        return "Not extracted"
    launch_url_link.short_description = "Launch URL"
    
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if obj.package_file and not obj.is_extracted:
            # Auto-detect package type if not set
            if not obj.package_type:
                detected_type = obj.detect_package_type()
                if detected_type:
                    obj.package_type = detected_type
                    obj.save()
            # Auto-extract the package
            obj.extract_package()

# SCORMPackage is now an alias for ELearningPackage, so we don't need a separate admin

@admin.register(ELearningTracking)
class ELearningTrackingAdmin(admin.ModelAdmin):
    list_display = [
        'user', 'elearning_package', 'completion_status', 
        'success_status', 'score_display', 'progress_display',
        'last_launch'
    ]
    list_filter = [
        'completion_status', 'success_status', 'created_at',
        'elearning_package__topic'
    ]
    search_fields = [
        'user__username', 'user__email', 
        'elearning_package__title', 'elearning_package__topic__title'
    ]
    readonly_fields = [
        'created_at', 'updated_at', 'first_launch', 
        'last_launch', 'completion_date', 'raw_data_display'
    ]
    
    fieldsets = (
        ('Learner Information', {
            'fields': ('user', 'elearning_package')
        }),
        ('Progress Status', {
            'fields': ('completion_status', 'success_status', 'progress_measure')
        }),
        ('Scores', {
            'fields': ('score_raw', 'score_min', 'score_max', 'score_scaled')
        }),
        ('Time Tracking', {
            'fields': ('total_time', 'session_time')
        }),
        ('Timestamps', {
            'fields': ('first_launch', 'last_launch', 'completion_date', 'created_at', 'updated_at')
        }),
        ('Raw Data', {
            'fields': ('raw_data_display',),
            'classes': ('collapse',)
        })
    )
    
    def score_display(self, obj):
        if obj.score_raw is not None:
            return "{:.1f}".format(obj.score_raw)
        return "-"
    score_display.short_description = "Score"
    
    def progress_display(self, obj):
        progress = obj.get_progress_percentage()
        return "{:.1f}%".format(progress)
    progress_display.short_description = "Progress"
    
    def raw_data_display(self, obj):
        if obj.raw_data:
            return format_html('<pre>{}</pre>', str(obj.raw_data))
        return "No data"
    raw_data_display.short_description = "Raw SCORM Data"

@admin.register(SCORMReport)
class SCORMReportAdmin(admin.ModelAdmin):
    list_display = [
        'course', 'report_type', 'generated_by', 
        'generated_at', 'data_summary'
    ]
    list_filter = ['report_type', 'generated_at', 'course']
    search_fields = ['course__title', 'generated_by__username']
    readonly_fields = ['generated_at', 'report_data_display']
    
    def data_summary(self, obj):
        if obj.report_data:
            return "{} records".format(len(obj.report_data))
        return "No data"
    data_summary.short_description = "Data Summary"
    
    def report_data_display(self, obj):
        if obj.report_data:
            return format_html('<pre>{}</pre>', str(obj.report_data))
        return "No data"
    report_data_display.short_description = "Report Data"