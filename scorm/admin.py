"""
Admin interface for SCORM packages
"""
from django.contrib import admin
from .models import ScormPackage


@admin.register(ScormPackage)
class ScormPackageAdmin(admin.ModelAdmin):
    list_display = ('title', 'version', 'authoring_tool', 'primary_resource_scorm_type', 'processing_status', 'created_by', 'created_at')
    list_filter = ('processing_status', 'version', 'authoring_tool', 'primary_resource_scorm_type', 'primary_resource_type', 'created_at')
    search_fields = ('title', 'primary_resource_identifier', 'primary_resource_href')
    readonly_fields = ('created_at', 'updated_at', 'manifest_data', 'resources', 'extracted_path', 'launch_url', 'primary_resource_identifier', 'primary_resource_type', 'primary_resource_scorm_type', 'primary_resource_href')
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('title', 'version', 'authoring_tool', 'processing_status')
        }),
        ('Primary Resource', {
            'fields': ('primary_resource_identifier', 'primary_resource_type', 'primary_resource_scorm_type', 'primary_resource_href')
        }),
        ('Launch Information', {
            'fields': ('launch_url',)
        }),
        ('Files', {
            'fields': ('package_zip', 'extracted_path')
        }),
        ('Manifest Data', {
            'fields': ('manifest_data',),
            'classes': ('collapse',)
        }),
        ('Resources Data', {
            'fields': ('resources',),
            'classes': ('collapse',)
        }),
        ('Processing', {
            'fields': ('processing_error',)
        }),
        ('Metadata', {
            'fields': ('created_by', 'created_at', 'updated_at')
        }),
    )

