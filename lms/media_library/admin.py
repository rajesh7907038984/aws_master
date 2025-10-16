from django.contrib import admin
from .models import MediaFile, StorageStatistics


@admin.register(MediaFile)
class MediaFileAdmin(admin.ModelAdmin):
    list_display = [
        'filename', 'file_type', 'storage_type', 'file_size_mb', 
        'uploaded_by', 'uploaded_at', 'is_active'
    ]
    list_filter = [
        'storage_type', 'file_type', 'is_active', 'is_public', 
        'uploaded_at', 'source_app'
    ]
    search_fields = [
        'filename', 'original_filename', 'description', 'tags',
        'uploaded_by__username', 'uploaded_by__email'
    ]
    readonly_fields = [
        'file_size_mb', 'file_extension', 'access_count', 
        'last_accessed', 'uploaded_at'
    ]
    list_per_page = 50
    
    fieldsets = (
        ('File Information', {
            'fields': (
                'filename', 'original_filename', 'file_path', 'file_url',
                'file_size', 'file_size_mb', 'file_extension', 'file_type', 'mime_type'
            )
        }),
        ('Storage', {
            'fields': ('storage_type', 'is_active', 'is_public')
        }),
        ('Metadata', {
            'fields': (
                'uploaded_by', 'uploaded_at', 'last_accessed', 'access_count',
                'description', 'tags'
            )
        }),
        ('Source Tracking', {
            'fields': ('source_app', 'source_model', 'source_id'),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('uploaded_by')


@admin.register(StorageStatistics)
class StorageStatisticsAdmin(admin.ModelAdmin):
    list_display = [
        'storage_type', 'total_files', 'total_size_mb', 'total_size_gb',
        'last_updated'
    ]
    readonly_fields = [
        'storage_type', 'total_files', 'total_size_bytes', 'total_size_mb', 
        'total_size_gb', 'last_updated', 'image_count', 'video_count', 
        'audio_count', 'document_count', 'archive_count', 'other_count'
    ]
    
    def has_add_permission(self, request):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return False