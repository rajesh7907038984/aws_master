from django.contrib import admin
from .models import Report, ReportAttachment, Event

@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ('title', 'report_type', 'status', 'created_by', 'created_at')
    list_filter = ('report_type', 'status', 'created_at')
    search_fields = ('title', 'description', 'created_by__username')
    readonly_fields = ('created_at', 'updated_at')
    filter_horizontal = ('shared_with',)
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('title', 'description', 'report_type', 'status')
        }),
        ('Configuration', {
            'fields': ('rules', 'output_fields'),
            'classes': ('collapse',)
        }),
        ('Sharing', {
            'fields': ('created_by', 'shared_with'),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

@admin.register(ReportAttachment)
class ReportAttachmentAdmin(admin.ModelAdmin):
    list_display = ('filename', 'report', 'file_type', 'uploaded_at')
    list_filter = ('file_type', 'uploaded_at')
    search_fields = ('filename', 'report__title')
    readonly_fields = ('uploaded_at',)

@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ('type', 'user', 'course', 'created_at')
    list_filter = ('type', 'created_at')
    search_fields = ('user__username', 'course__title', 'description')
    readonly_fields = ('created_at',)
    
    def has_add_permission(self, request):
        # Events are created automatically, prevent manual creation
        return False
