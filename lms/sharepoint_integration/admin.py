"""
Admin interface for SharePoint Integration
"""

from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone
from account_settings.models import SharePointIntegration


@admin.register(SharePointIntegration)
class SharePointIntegrationAdmin(admin.ModelAdmin):
    """Admin interface for SharePoint Integration"""
    
    list_display = [
        'name',
        'branch',
        'is_active',
        'site_url_display',
        'last_sync_status_display',
        'last_sync_datetime',
        'sync_actions'
    ]
    
    list_filter = [
        'is_active',
        'last_sync_status',
        'branch',
        'enable_user_sync',
        'enable_enrollment_sync',
        'enable_progress_sync',
        'enable_certificate_sync',
        'enable_reports_sync',
        'enable_assessment_sync'
    ]
    
    search_fields = [
        'name',
        'site_url',
        'user_list_name',
        'enrollment_list_name',
        'branch__name'
    ]
    
    readonly_fields = [
        'access_token',
        'token_expiry',
        'refresh_token',
        'last_sync_datetime',
        'last_sync_status',
        'sync_error_message',
        'total_synced_users',
        'total_synced_enrollments',
        'created_at',
        'updated_at'
    ]
    
    fieldsets = [
        ('Basic Information', {
            'fields': ['name', 'is_active', 'user', 'branch']
        }),
        ('SharePoint Configuration', {
            'fields': [
                'tenant_id',
                'client_id',
                'client_secret',
                'site_url'
            ]
        }),
        ('SharePoint Lists & Libraries', {
            'fields': [
                'user_list_name',
                'enrollment_list_name',
                'progress_list_name',
                'certificate_library_name',
                'reports_library_name',
                'assessment_library_name'
            ],
            'classes': ['collapse']
        }),
        ('Power BI Integration', {
            'fields': [
                'powerbi_workspace_id',
                'powerbi_dataset_id'
            ],
            'classes': ['collapse']
        }),
        ('Sync Configuration', {
            'fields': [
                'enable_user_sync',
                'enable_enrollment_sync',
                'enable_progress_sync',
                'enable_certificate_sync',
                'enable_reports_sync',
                'enable_assessment_sync'
            ]
        }),
        ('Authentication & Tokens', {
            'fields': [
                'access_token',
                'token_expiry',
                'refresh_token'
            ],
            'classes': ['collapse']
        }),
        ('Sync Status & Statistics', {
            'fields': [
                'last_sync_datetime',
                'last_sync_status',
                'sync_error_message',
                'total_synced_users',
                'total_synced_enrollments'
            ],
            'classes': ['collapse']
        }),
        ('Timestamps', {
            'fields': ['created_at', 'updated_at'],
            'classes': ['collapse']
        })
    ]
    
    actions = [
        'test_connection',
        'sync_users',
        'sync_enrollments',
        'sync_progress',
        'sync_all_data',
        'activate_integrations',
        'deactivate_integrations'
    ]
    
    def site_url_display(self, obj):
        """Display SharePoint site URL with link"""
        if obj.site_url:
            return format_html(
                '<a href="{}" target="_blank">{}</a>',
                obj.site_url,
                obj.site_url[:50] + '...' if len(obj.site_url) > 50 else obj.site_url
            )
        return '-'
    site_url_display.short_description = 'SharePoint Site'
    
    def last_sync_status_display(self, obj):
        """Display last sync status with color coding"""
        if obj.last_sync_status == 'success':
            return format_html(
                '<span style="color: green; font-weight: bold;">✓ Success</span>'
            )
        elif obj.last_sync_status == 'error':
            return format_html(
                '<span style="color: red; font-weight: bold;">✗ Error</span>'
            )
        elif obj.last_sync_status == 'never':
            return format_html(
                '<span style="color: gray;">Never synced</span>'
            )
        else:
            return obj.last_sync_status
    last_sync_status_display.short_description = 'Sync Status'
    
    def sync_actions(self, obj):
        """Display sync action buttons"""
        if obj.pk:
            return format_html(
                '<a class="button" href="{}">Test Connection</a>&nbsp;'
                '<a class="button" href="{}">Sync Now</a>',
                reverse('admin:sharepoint_test_connection', args=[obj.pk]),
                reverse('admin:sharepoint_sync_now', args=[obj.pk])
            )
        return '-'
    sync_actions.short_description = 'Actions'
    
    def test_connection(self, request, queryset):
        """Test SharePoint connection for selected integrations"""
        from sharepoint_integration.utils.sharepoint_api import SharePointAPI
        
        results = []
        for integration in queryset:
            try:
                api = SharePointAPI(integration)
                success, message = api.test_connection()
                
                if success:
                    self.message_user(
                        request,
                        f"✓ Connection test passed for {integration.name}: {message}"
                    )
                    results.append(f"✓ {integration.name}: {message}")
                else:
                    self.message_user(
                        request,
                        f"✗ Connection test failed for {integration.name}: {message}",
                        level='ERROR'
                    )
                    results.append(f"✗ {integration.name}: {message}")
                    
            except Exception as e:
                error_msg = f"Connection test error for {integration.name}: {str(e)}"
                self.message_user(request, error_msg, level='ERROR')
                results.append(f"✗ {integration.name}: {str(e)}")
        
        # Display summary
        self.message_user(
            request,
            f"Connection test completed for {len(queryset)} integration(s)"
        )
    
    test_connection.short_description = "Test SharePoint connection"
    
    def sync_users(self, request, queryset):
        """Sync users for selected integrations"""
        from sharepoint_integration.tasks import sync_user_data_to_sharepoint
        
        count = 0
        for integration in queryset:
            if integration.is_active and integration.enable_user_sync:
                sync_user_data_to_sharepoint.delay(integration.id)
                count += 1
        
        self.message_user(
            request,
            f"User sync started for {count} integration(s). Check sync status in a few minutes."
        )
    
    sync_users.short_description = "Sync users to SharePoint"
    
    def sync_enrollments(self, request, queryset):
        """Sync enrollments for selected integrations"""
        from sharepoint_integration.tasks import sync_enrollment_data_to_sharepoint
        
        count = 0
        for integration in queryset:
            if integration.is_active and integration.enable_enrollment_sync:
                sync_enrollment_data_to_sharepoint.delay(integration.id)
                count += 1
        
        self.message_user(
            request,
            f"Enrollment sync started for {count} integration(s). Check sync status in a few minutes."
        )
    
    sync_enrollments.short_description = "Sync enrollments to SharePoint"
    
    def sync_progress(self, request, queryset):
        """Sync progress for selected integrations"""
        from sharepoint_integration.tasks import sync_progress_data_to_sharepoint
        
        count = 0
        for integration in queryset:
            if integration.is_active and integration.enable_progress_sync:
                sync_progress_data_to_sharepoint.delay(integration.id)
                count += 1
        
        self.message_user(
            request,
            f"Progress sync started for {count} integration(s). Check sync status in a few minutes."
        )
    
    sync_progress.short_description = "Sync progress to SharePoint"
    
    def sync_all_data(self, request, queryset):
        """Sync all data types for selected integrations"""
        from sharepoint_integration.tasks import sync_sharepoint_data
        
        count = 0
        for integration in queryset:
            if integration.is_active:
                sync_sharepoint_data.delay(integration.id, sync_type='all')
                count += 1
        
        self.message_user(
            request,
            f"Full sync started for {count} integration(s). Check sync status in a few minutes."
        )
    
    sync_all_data.short_description = "Sync all data to SharePoint"
    
    def activate_integrations(self, request, queryset):
        """Activate selected integrations"""
        updated = queryset.update(is_active=True)
        self.message_user(
            request,
            f"Successfully activated {updated} integration(s)."
        )
    
    activate_integrations.short_description = "Activate selected integrations"
    
    def deactivate_integrations(self, request, queryset):
        """Deactivate selected integrations"""
        updated = queryset.update(is_active=False)
        self.message_user(
            request,
            f"Successfully deactivated {updated} integration(s)."
        )
    
    deactivate_integrations.short_description = "Deactivate selected integrations"
    
    def get_queryset(self, request):
        """Filter queryset based on user permissions"""
        qs = super().get_queryset(request)
        
        # Global admins can see all integrations
        if request.user.role == 'globaladmin':
            return qs
        
        # Super admins can see integrations in their assigned businesses
        elif request.user.role == 'superadmin':
            if hasattr(request.user, 'assigned_businesses'):
                business_ids = request.user.assigned_businesses.values_list('id', flat=True)
                return qs.filter(branch__business_id__in=business_ids)
            return qs.filter(branch__isnull=True)
        
        # Branch admins can only see their branch integrations
        elif request.user.role == 'admin' and request.user.branch:
            return qs.filter(branch=request.user.branch)
        
        # Other users cannot manage integrations
        else:
            return qs.none()
    
    def has_add_permission(self, request):
        """Check if user can add SharePoint integrations"""
        return request.user.role in ['globaladmin', 'superadmin', 'admin']
    
    def has_change_permission(self, request, obj=None):
        """Check if user can change SharePoint integrations"""
        if not request.user.role in ['globaladmin', 'superadmin', 'admin']:
            return False
        
        if obj and request.user.role == 'admin':
            # Branch admins can only modify their branch integrations
            return obj.branch == request.user.branch
        
        return True
    
    def has_delete_permission(self, request, obj=None):
        """Check if user can delete SharePoint integrations"""
        if not request.user.role in ['globaladmin', 'superadmin']:
            return False
        
        return True
