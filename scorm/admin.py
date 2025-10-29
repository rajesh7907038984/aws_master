"""
Admin interface for SCORM packages
"""
from django.contrib import admin
from .models import ScormPackage


@admin.register(ScormPackage)
class ScormPackageAdmin(admin.ModelAdmin):
    list_display = ('title', 'version', 'processing_status', 'created_by', 'created_at')
    list_filter = ('processing_status', 'version', 'created_at')
    search_fields = ('title',)
    readonly_fields = ('created_at', 'updated_at', 'manifest_data', 'extracted_path')
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('title', 'version', 'processing_status')
        }),
        ('Files', {
            'fields': ('package_zip', 'extracted_path')
        }),
        ('Manifest Data', {
            'fields': ('manifest_data',),
            'classes': ('collapse',)
        }),
        ('Processing', {
            'fields': ('processing_error',)
        }),
        ('Metadata', {
            'fields': ('created_by', 'created_at', 'updated_at')
        }),
    )

