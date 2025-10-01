from django.contrib import admin
from django.utils.html import format_html
from .models import (
    SCORMPackage, 
    SCORMRegistration, 
    SCORMCloudContent,
    SCORMDestination,
    SCORMDispatch
)
from django.core.exceptions import ValidationError
from django.contrib import messages
from .utils.api import SCORMCloudError
import uuid
import logging
from django.db import models
from django.contrib.admin import SimpleListFilter
from django.urls import reverse
from django.utils.http import urlencode
import urllib.parse
import time
import hmac
import hashlib
import base64

logger = logging.getLogger(__name__)

# Custom filter for content_type
class ContentTypeFilter(SimpleListFilter):
    title = 'Content Type'
    parameter_name = 'content_type'
    
    def lookups(self, request, model_admin):
        # Get all unique content types from the database
        content_types = SCORMCloudContent.objects.values_list('content_type', flat=True).distinct()
        return [(ct, ct) for ct in content_types]
    
    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(content_type=self.value())
        return queryset

@admin.register(SCORMDestination)
class SCORMDestinationAdmin(admin.ModelAdmin):
    list_display = (
        'name', 
        'cloud_id', 
        'auth_type',
        'hash_user_info',
        'status',
        'created_at'
    )
    list_filter = ('auth_type', 'hash_user_info', 'created_at')
    search_fields = ('name', 'cloud_id', 'description')
    readonly_fields = ('cloud_id', 'created_at', 'updated_at', 'status')
    
    fieldsets = (
        (None, {
            'fields': ('name', 'description')
        }),
        ('SCORM Cloud Settings', {
            'fields': ('cloud_id', 'auth_type', 'hash_user_info'),
            'description': 'Configure how this destination interacts with SCORM Cloud'
        }),
        ('Advanced Settings', {
            'fields': ('settings',),
            'classes': ('collapse',),
            'description': 'Additional configuration options for the destination'
        }),
        ('Status Information', {
            'fields': ('status', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    def status(self, obj):
        """Check and display destination status"""
        from .utils.api import get_scorm_client
        try:
            if not obj.cloud_id:
                return format_html(
                    '<span style="color: orange;">? Not Created Yet</span>'
                )
            dest = scorm_cloud.get_destination(obj.cloud_id)
            if dest:
                return format_html(
                    '<span style="color: green;">✓ Active</span>'
                )
            return format_html(
                '<span style="color: red;">✗ Not Found in SCORM Cloud</span>'
            )
        except Exception as e:
            logger.error(f"Error checking destination status: {str(e)}")
            return format_html(
                '<span style="color: orange;">? Status Unknown</span>'
            )
    status.short_description = 'SCORM Cloud Status'

    def save_model(self, request, obj, form, change):
        """Enhanced save with better validation and error handling"""
        try:
            # Clean and validate the name
            if not obj.name or not obj.name.strip():
                raise ValidationError("Destination name is required")
            
            obj.name = obj.name.strip()
            if len(obj.name) < 3:
                raise ValidationError("Destination name must be at least 3 characters long")
            
            # For new destinations, generate cloud_id if not set
            if not change and not obj.cloud_id:
                obj.cloud_id = f"d_{uuid.uuid4().hex[:8]}"
            
            # Ensure cloud_id format
            if obj.cloud_id and not obj.cloud_id.startswith('d_'):
                obj.cloud_id = f"d_{obj.cloud_id}"
            
            # Save to database
            super().save_model(request, obj, form, change)
            
            action = 'updated' if change else 'created'
            self.message_user(
                request,
                f"Successfully {action} destination in SCORM Cloud",
                level=messages.SUCCESS
            )

        except ValidationError as e:
            logger.error(f"Validation error saving destination {obj.name}: {str(e)}")
            self.message_user(
                request,
                str(e),
                level=messages.ERROR
            )
            raise
            
        except Exception as e:
            logger.error(f"Error saving destination {obj.name}: {str(e)}")
            error_msg = "Unable to save the destination due to a system error. Please verify your input and try again, or contact support if the problem persists."
            self.message_user(
                request,
                error_msg,
                level=messages.ERROR
            )
            raise ValidationError(error_msg)

    def delete_model(self, request, obj):
        """Enhanced delete with SCORM Cloud cleanup"""
        from .utils.api import get_scorm_client
        try:
            # Delete from SCORM Cloud first
            scorm_cloud.delete_destination(obj.cloud_id)
            super().delete_model(request, obj)
            self.message_user(
                request,
                "Successfully deleted destination from SCORM Cloud",
                level=messages.SUCCESS
            )
        except Exception as e:
            self.message_user(
                request,
                f"Error deleting destination: {str(e)}",
                level=messages.ERROR
            )
            raise

    actions = ['sync_with_cloud', 'verify_destinations', 'reset_destinations']

    def sync_with_cloud(self, request, queryset):
        """Sync selected destinations with SCORM Cloud"""
        success = 0
        for dest in queryset:
            if dest.sync_with_cloud():
                success += 1
        
        self.message_user(
            request,
            f"Successfully synced {success} of {queryset.count()} destinations with SCORM Cloud",
            level=messages.SUCCESS if success == queryset.count() else messages.WARNING
        )
    sync_with_cloud.short_description = "Sync selected destinations with SCORM Cloud"

    def verify_destinations(self, request, queryset):
        """Verify destinations exist in SCORM Cloud"""
        from .utils.api import get_scorm_client
        valid = 0
        invalid = []
        
        for dest in queryset:
            try:
                if scorm_cloud.get_destination(dest.cloud_id):
                    valid += 1
                else:
                    invalid.append(dest.name)
            except Exception:
                invalid.append(dest.name)
        
        if invalid:
            self.message_user(
                request,
                f"Found {valid} valid destinations. Invalid destinations: {', '.join(invalid)}",
                level=messages.WARNING
            )
        else:
            self.message_user(
                request,
                f"All {valid} destinations are valid in SCORM Cloud",
                level=messages.SUCCESS
            )
    verify_destinations.short_description = "Verify destinations in SCORM Cloud"

    def reset_destinations(self, request, queryset):
        """Reset destinations in SCORM Cloud"""
        from .utils.api import get_scorm_client
        success = 0
        
        for dest in queryset:
            try:
                # Delete from SCORM Cloud
                scorm_cloud.delete_destination(dest.cloud_id)
                
                # Create new destination data
                destination_data = {
                    "destinations": [{
                        "id": dest.cloud_id,
                        "name": dest.name,
                        "data": {
                            "name": dest.name,
                            "launchAuth": {
                                "type": dest.auth_type,
                                "options": {}
                            },
                            "hashUserInfo": dest.hash_user_info,
                            "tags": []
                        }
                    }]
                }
                
                # Recreate in SCORM Cloud
                response = scorm_cloud._make_request(
                    'POST',
                    'dispatch/destinations',
                    data=destination_data
                )
                
                if response and isinstance(response.get('destinations'), list):
                    success += 1
                    
            except Exception as e:
                logger.error(f"Error resetting destination {dest.name}: {str(e)}")
                self.message_user(
                    request,
                    f"Error resetting destination {dest.name}: {str(e)}",
                    level=messages.ERROR
                )
        
        self.message_user(
            request,
            f"Successfully reset {success} of {queryset.count()} destinations",
            level=messages.SUCCESS if success == queryset.count() else messages.WARNING
        )
    reset_destinations.short_description = "Reset destinations in SCORM Cloud"

@admin.register(SCORMDispatch)
class SCORMDispatchAdmin(admin.ModelAdmin):
    list_display = (
        'cloud_id', 
        'destination', 
        'package', 
        'enabled',
        'registration_count', 
        'created_at'
    )
    list_filter = (
        'enabled', 
        'allow_new_registrations', 
        'instanced',
        'destination'
    )
    search_fields = (
        'cloud_id', 
        'package__title', 
        'destination__name'
    )
    readonly_fields = (
        'cloud_id', 
        'registration_count', 
        'last_reset_date',
        'created_at', 
        'updated_at'
    )
    raw_id_fields = ('destination', 'package')
    
    fieldsets = (
        (None, {
            'fields': ('destination', 'package', 'cloud_id', 'notes')
        }),
        ('Status', {
            'fields': (
                'enabled', 
                'allow_new_registrations', 
                'registration_cap',
                'expiration_date'
            )
        }),
        ('Registration Management', {
            'fields': (
                'registration_count', 
                'last_reset_date', 
                'instanced'
            ),
            'classes': ('collapse',)
        }),
        ('Advanced', {
            'fields': ('tracking_data',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    def get_registration_status(self, obj):
        if obj.registration_cap:
            return f"{obj.registration_count}/{obj.registration_cap}"
        return obj.registration_count
    get_registration_status.short_description = 'Registrations'

    actions = ['reset_registration_count', 'enable_dispatches', 'disable_dispatches']

    def reset_registration_count(self, request, queryset):
        success_count = 0
        for dispatch in queryset:
            if dispatch.reset_registration_count():
                success_count += 1
        self.message_user(
            request,
            f"Successfully reset registration count for {success_count} of {queryset.count()} dispatches."
        )
    reset_registration_count.short_description = "Reset registration count"

    def enable_dispatches(self, request, queryset):
        updated = queryset.update(enabled=True)
        self.message_user(request, f"Enabled {updated} dispatches.")
    enable_dispatches.short_description = "Enable selected dispatches"

    def disable_dispatches(self, request, queryset):
        updated = queryset.update(enabled=False)
        self.message_user(request, f"Disabled {updated} dispatches.")
    disable_dispatches.short_description = "Disable selected dispatches"

    def save_model(self, request, obj, form, change):
        """Enhanced save with SCORM Cloud sync"""
        from .utils.api import get_scorm_client
        try:
            if not change:  # New dispatch
                # Ensure destination exists
                if not scorm_cloud.get_destination(obj.destination.cloud_id):
                    raise ValidationError("Destination does not exist in SCORM Cloud")

                # Create dispatch data
                dispatch_data = {
                    "courseId": obj.package.cloud_id,
                    "destinationId": obj.destination.cloud_id,
                    "enabled": obj.enabled,
                    "allowNewRegistrations": obj.allow_new_registrations
                }

                if obj.registration_cap:
                    dispatch_data["registrationCap"] = obj.registration_cap

                # Create in SCORM Cloud
                response = scorm_cloud._make_request(
                    'POST',
                    'dispatch/dispatches',
                    data=dispatch_data
                )

                if response and response.get('id'):
                    obj.cloud_id = response['id']
                else:
                    raise ValidationError("Failed to create dispatch in SCORM Cloud")

            else:  # Update existing
                # Update in SCORM Cloud
                update_data = {
                    "enabled": obj.enabled,
                    "allowNewRegistrations": obj.allow_new_registrations
                }

                if obj.registration_cap:
                    update_data["registrationCap"] = obj.registration_cap

                scorm_cloud._make_request(
                    'PUT',
                    f'dispatch/dispatches/{obj.cloud_id}',
                    data=update_data
                )

            super().save_model(request, obj, form, change)
            
            action = 'updated' if change else 'created'
            self.message_user(
                request,
                f"Successfully {action} dispatch in SCORM Cloud",
                level=messages.SUCCESS
            )

        except Exception as e:
            logger.error(f"Error saving dispatch: {str(e)}")
            self.message_user(
                request,
                f"Error saving dispatch: {str(e)}",
                level=messages.ERROR
            )
            raise ValidationError(f"Failed to save dispatch: {str(e)}")

    def delete_model(self, request, obj):
        """Enhanced delete with SCORM Cloud cleanup"""
        from .utils.api import get_scorm_client
        try:
            # Delete from SCORM Cloud first
            scorm_cloud._make_request('DELETE', f'dispatch/dispatches/{obj.cloud_id}')
            super().delete_model(request, obj)
            self.message_user(
                request,
                "Successfully deleted dispatch from SCORM Cloud",
                level=messages.SUCCESS
            )
        except Exception as e:
            logger.error(f"Error deleting dispatch: {str(e)}")
            self.message_user(
                request,
                f"Error deleting dispatch: {str(e)}",
                level=messages.ERROR
            )
            raise

@admin.register(SCORMPackage)
class SCORMPackageAdmin(admin.ModelAdmin):
    list_display = (
        'title', 
        'version', 
        'cloud_id', 
        'upload_date', 
        'last_updated', 
        'launch_link',
        'default_destination'
    )
    list_filter = ('version', 'upload_date', 'default_destination')
    search_fields = ('title', 'cloud_id')
    readonly_fields = (
        'cloud_id', 
        'upload_date', 
        'last_updated', 
        'launch_url', 
        'entry_url'
    )
    raw_id_fields = ('default_destination',)

    def launch_link(self, obj):
        """Get launch link with proper SCORM API initialization"""
        launch_url = obj.get_launch_url()
        if launch_url:
            return format_html(
                '<a href="{}" target="_blank" class="viewlink">Launch</a>',
                launch_url
            )
        return format_html('<span class="error">No launch URL available</span>')
    launch_link.short_description = 'Launch'

    def save_model(self, request, obj, form, change):
        """Enhanced save with validation"""
        try:
            if not change:  # New package
                if not obj.cloud_id:
                    raise ValidationError("SCORM Cloud ID is required")
                if not obj.launch_url:
                    raise ValidationError("Launch URL is required")

            super().save_model(request, obj, form, change)
            
            action = 'updated' if change else 'created'
            self.message_user(
                request,
                f"Successfully {action} SCORM package",
                level=messages.SUCCESS
            )

        except Exception as e:
            logger.error(f"Error saving SCORM package: {str(e)}")
            self.message_user(
                request,
                f"Error saving SCORM package: {str(e)}",
                level=messages.ERROR
            )
            raise ValidationError(f"Failed to save SCORM package: {str(e)}")

    def delete_model(self, request, obj):
        """Enhanced delete with SCORM Cloud cleanup and improved error handling"""
        from .utils.api import get_scorm_client
        try:
            # Delete from SCORM Cloud first with improved error handling
            scorm_client = get_scorm_client(user=request.user)
            deletion_result = scorm_client.delete_course(obj.cloud_id) if scorm_client else None
            
            # Always delete locally regardless of cloud deletion result
            super().delete_model(request, obj)
            
            if deletion_result and isinstance(deletion_result, dict):
                status = deletion_result.get('status')
                message = deletion_result.get('message', 'Unknown result')
                
                if status == 'deletion_disabled':
                    self.message_user(
                        request,
                        f"SCORM package deleted locally. Cloud deletion not available: {message}",
                        level=messages.WARNING
                    )
                elif status == 'already_deleted':
                    self.message_user(
                        request,
                        f"SCORM package deleted locally. {message}",
                        level=messages.SUCCESS
                    )
                elif status == 'error':
                    self.message_user(
                        request,
                        f"SCORM package deleted locally. Cloud deletion failed: {message}",
                        level=messages.WARNING
                    )
                else:
                    self.message_user(
                        request,
                        level=messages.SUCCESS
                    )
            else:
                self.message_user(
                    request,
                    level=messages.SUCCESS
                )
        except Exception as e:
            logger.error(f"Error deleting SCORM package: {str(e)}")
            # Try to delete locally even if cloud deletion failed completely
            try:
                super().delete_model(request, obj)
                self.message_user(
                    request,
                    f"SCORM package deleted locally only. Cloud deletion error: {str(e)}",
                    level=messages.WARNING
                )
            except Exception as local_error:
                logger.error(f"Failed to delete SCORM package locally: {local_error}")
                self.message_user(
                    request,
                    f"Failed to delete SCORM package: {str(e)}",
                    level=messages.ERROR
                )
                raise

@admin.register(SCORMRegistration)
class SCORMRegistrationAdmin(admin.ModelAdmin):
    list_display = ('registration_id', 'user', 'package', 'completion_status', 'success_status', 'score')
    list_filter = ('completion_status', 'success_status', 'package')
    search_fields = ('registration_id', 'user__username', 'package__title')
    raw_id_fields = ('user', 'package')
    readonly_fields = ('registration_id', 'created_at', 'updated_at', 'last_accessed')

    def launch_link(self, obj):
        launch_url = obj.get_launch_url()
        if launch_url:
            return format_html('<a href="{}" target="_blank">Launch</a>', launch_url)
        return "-"
    launch_link.short_description = 'Launch'

    def get_queryset(self, request):
        """Override to sync registration status when viewing list"""
        queryset = super().get_queryset(request)
        if request.GET.get('auto_sync') != 'false':
            for registration in queryset[:10]:  # Limit to first 10 for performance
                registration.sync_completion_status()
        return queryset

    def change_view(self, request, object_id, form_url='', extra_context=None):
        """Override to sync registration status when viewing details"""
        obj = self.get_object(request, object_id)
        if obj and request.GET.get('auto_sync') != 'false':
            obj.sync_completion_status()
        return super().change_view(
            request, object_id, form_url, extra_context=extra_context
        )

    actions = ['sync_status', 'sync_all_registrations']

    def sync_status(self, request, queryset):
        success_count = 0
        for registration in queryset:
            if registration.sync_completion_status():
                success_count += 1
        self.message_user(
            request,
            f"Successfully synced {success_count} of {queryset.count()} registrations."
        )
    sync_status.short_description = "Sync selected registrations"

    def sync_all_registrations(self, request, queryset):
        """Sync all registrations in the queryset"""
        success_count = 0
        for registration in queryset:
            if registration.sync_completion_status():
                success_count += 1
        self.message_user(
            request,
            f"Successfully synced {success_count} of {queryset.count()} registrations."
        )
    sync_all_registrations.short_description = "Sync all selected registrations with SCORM Cloud"

@admin.register(SCORMCloudContent)
class SCORMCloudContentAdmin(admin.ModelAdmin):
    list_display = ('title', 'content_type', 'content_id', 'package', 'direct_launch_url')
    search_fields = ('title', 'content_id', 'package__title')
    raw_id_fields = ('package',)
    list_filter = (ContentTypeFilter,)
    
    def direct_launch_url(self, obj):
        """Generate a direct SCORM Cloud content URL that doesn't require registration.
        
        This uses the application's direct_scorm_launch view to handle the launch properly.
        """
        try:
            # Check for valid package
            if not obj.package:
                logger.warning(f"No package associated with content {obj.id}")
                return format_html('<span style="color: red;">No package</span>')
                
            if not obj.package.cloud_id:
                logger.warning(f"No cloud_id for package {obj.package.id}")
                return format_html('<span style="color: red;">Invalid package (no cloud ID)</span>')
            
            # Get SCORM Cloud client - try branch-specific first, fallback for admin
            from .utils.api import get_scorm_client
            from django.conf import settings
            
            # For admin interface, we don't have user context, so use global settings as fallback
            try:
                scorm_client = get_scorm_client()  # Will use fallback settings
                app_id = scorm_client.app_id
            except Exception as e:
                logger.warning(f"Could not get SCORM client: {e}")
                app_id = ''  # Branch-specific SCORM configuration
            
            if not app_id:
                logger.warning("No SCORM Cloud APP_ID configured")
                return format_html('<span style="color: red;">Missing SCORM Cloud APP_ID</span>')
            
            # Use the Django application's direct_scorm_launch view for proper handling
            from django.urls import reverse
            direct_url = reverse('scorm_cloud:direct_scorm_launch', kwargs={'content_id': obj.id})
            
            # Log the URL being generated
            logger.info(f"Generated internal direct launch URL for content {obj.id}: {direct_url}")
            
            # Return as HTML button
            return format_html('<a href="{}" target="_blank" class="button">Launch</a>', direct_url)
            
        except Exception as e:
            # Log the error
            logger.error(f"Error generating direct launch URL for content {obj.id}: {str(e)}", exc_info=True)
            
            # Try to generate a fallback URL to the direct_scorm_launch view
            try:
                from django.urls import reverse
                fallback_url = reverse('scorm_cloud:direct_scorm_launch', kwargs={'content_id': obj.id})
                return format_html(
                    '<span style="color: orange;">Error: {}</span><br/>'
                    '<a href="{}" target="_blank" class="button">Direct Launch</a>', 
                    str(e)[:50], fallback_url
                )
            except Exception as url_error:
                logger.error(f"Error generating fallback URL: {str(url_error)}")
                
            # If we can still generate a direct URL to SCORM Cloud as a last resort
            if hasattr(obj, 'package') and obj.package and obj.package.cloud_id:
                try:
                    # Regenerate the direct launch URL for the package
                    cloud_id = obj.package.cloud_id
                    if cloud_id:
                        from django.conf import settings
                        import time
                        import hmac
                        import hashlib
                        import base64
                        
                        # Get credentials from branch-specific client or fallback to global settings
                        from ..utils.api import get_scorm_client
                        try:
                            scorm_client = get_scorm_client()  # Will use fallback settings
                            app_id = scorm_client.app_id
                            secret_key = scorm_client.secret_key
                        except Exception as e:
                            logger.warning(f"Could not get SCORM client: {e}")
                            app_id = ''  # Branch-specific SCORM configuration
                            secret_key = ''  # Branch-specific SCORM configuration
                        
                        # Generate authentication parameters
                        timestamp = int(time.time())
                        string_to_sign = f"{app_id}{cloud_id}{timestamp}"
                        signature = hmac.new(
                            secret_key.encode('utf-8'),
                            string_to_sign.encode('utf-8'),
                            hashlib.sha256
                        ).digest()
                        encoded_signature = base64.b64encode(signature).decode('utf-8')
                        
                        # Build authenticated direct URL
                        direct_url = (
                            f"https://cloud.scorm.com/content/courses/{app_id}/{cloud_id}/0/scormdriver/indexAPI.html"
                            f"?appId={app_id}&timestamp={timestamp}&signature={urllib.parse.quote(encoded_signature)}"
                            f"&Key-Pair-Id={app_id}"
                        )
                        
                        # Update the package
                        obj.package.launch_url = direct_url
                        obj.package.save()
                        
                        logger.info(f"Generated and saved direct launch URL: {direct_url}")
                        return format_html('<a href="{}" target="_blank" class="button">Launch</a>', direct_url)
                except Exception:
                    pass
                    
            # If all else fails, just show the error
            return format_html('<span style="color: red;">Error: {}</span>', str(e)[:100])
    direct_launch_url.short_description = 'Launch'
    
    def get_launch_url(self, obj):
        """Display launch URL with improved error handling - uses direct package launch URL by default"""
        if not obj.package:
            logger.warning(f"No package associated with content {obj.id}")
            return format_html('<span style="color: red;">No package</span>')
            
        from django.apps import apps
        User = apps.get_model('users', 'CustomUser')
        
        # Get the first superuser or admin to generate launch URL
        user = User.objects.filter(is_superuser=True).first() or User.objects.filter(role='admin').first()
        
        if not user:
            logger.warning(f"No admin user found to generate launch URL for content {obj.id}")
            return format_html('<span style="color: orange;">No admin user found</span>')
        
        # Check if package has a direct launch URL
        if obj.package.launch_url:
            logger.info(f"Using direct launch URL for content {obj.id}: {obj.package.launch_url}")
            return format_html('<a href="{}" target="_blank" class="button">Launch</a>', obj.package.launch_url)
        
        # If no direct launch URL, try to get one via registration
        try:
            # Check configuration first
            from .utils.api import get_scorm_client
            if not scorm_cloud.is_configured:
                logger.error("SCORM Cloud API not configured")
                return format_html('<span style="color: red;">SCORM Cloud not configured</span>')
                
            # Try to get launch URL
            launch_url = obj.get_launch_url(user)
            if launch_url:
                logger.info(f"Launch URL for content {obj.id}: {launch_url}")
                return format_html('<a href="{}" target="_blank" class="button">Launch</a>', launch_url)
            else:
                logger.error(f"Failed to get launch URL for content {obj.id}")
                
                # Regenerate the direct launch URL for the package
                cloud_id = obj.package.cloud_id
                if cloud_id:
                    from django.conf import settings
                    import time
                    import hmac
                    import hashlib
                    import base64
                    
                    # Get credentials from branch-specific client or fallback to global settings
                    from .utils.api import get_scorm_client
                    try:
                        scorm_client = get_scorm_client()  # Will use fallback settings
                        app_id = scorm_client.app_id
                        secret_key = scorm_client.secret_key
                    except Exception as e:
                        logger.warning(f"Could not get SCORM client: {e}")
                        app_id = ''  # Branch-specific SCORM configuration
                        secret_key = ''  # Branch-specific SCORM configuration
                    
                    # Generate authentication parameters
                    timestamp = int(time.time())
                    string_to_sign = f"{app_id}{cloud_id}{timestamp}"
                    signature = hmac.new(
                        secret_key.encode('utf-8'),
                        string_to_sign.encode('utf-8'),
                        hashlib.sha256
                    ).digest()
                    encoded_signature = base64.b64encode(signature).decode('utf-8')
                    
                    # Build authenticated direct URL
                    direct_url = (
                        f"https://cloud.scorm.com/content/courses/{app_id}/{cloud_id}/0/scormdriver/indexAPI.html"
                        f"?appId={app_id}&timestamp={timestamp}&signature={urllib.parse.quote(encoded_signature)}"
                        f"&Key-Pair-Id={app_id}"
                    )
                    
                    # Update the package
                    obj.package.launch_url = direct_url
                    obj.package.save()
                    
                    logger.info(f"Generated and saved direct launch URL: {direct_url}")
                    return format_html('<a href="{}" target="_blank" class="button">Launch</a>', direct_url)
                
                return format_html('<span style="color: red;">Launch URL generation failed</span>')
                
        except Exception as e:
            logger.error(f"Error getting launch URL for content {obj.id}: {str(e)}", exc_info=True)
            error_msg = str(e)[:50] + '...' if len(str(e)) > 50 else str(e)
            
            # Generate direct launch URL as fallback
            if obj.package and obj.package.cloud_id:
                from django.conf import settings
                import time
                import hmac
                import hashlib
                import base64
                
                app_id = ''  # Branch-specific SCORM configuration
                secret_key = ''  # Branch-specific SCORM configuration
                cloud_id = obj.package.cloud_id
                
                # Generate authentication parameters
                timestamp = int(time.time())
                string_to_sign = f"{app_id}{cloud_id}{timestamp}"
                signature = hmac.new(
                    secret_key.encode('utf-8'),
                    string_to_sign.encode('utf-8'),
                    hashlib.sha256
                ).digest()
                encoded_signature = base64.b64encode(signature).decode('utf-8')
                
                # Build authenticated direct URL
                direct_url = (
                    f"https://cloud.scorm.com/content/courses/{app_id}/{cloud_id}/0/scormdriver/indexAPI.html"
                    f"?appId={app_id}&timestamp={timestamp}&signature={urllib.parse.quote(encoded_signature)}"
                    f"&Key-Pair-Id={app_id}"
                )
                
                # Update the package
                obj.package.launch_url = direct_url
                obj.package.save()
                
                logger.info(f"Generated and saved direct launch URL as fallback: {direct_url}")
                return format_html(
                    '<span style="color: orange;">Error: {}</span><br/>'
                    '<a href="{}" target="_blank" class="button">Direct Launch</a>', 
                    error_msg, direct_url
                )
                
            return format_html('<span style="color: orange;">Error: {}</span>', error_msg)
    get_launch_url.short_description = 'Launch'
    
    # Add admin actions
    from .admin_actions import sync_all_scorm_content
    actions = [sync_all_scorm_content]
    
    def get_queryset(self, request):
        """Get all SCORMCloudContent items"""
        # Return the base queryset without any filtering
        qs = super().get_queryset(request)
        return qs

    def has_change_permission(self, request, obj=None):
        if not obj:
            return True
        if request.user.is_superuser:
            return True
        if obj.content_type != 'topic':
            return False
            
        from django.apps import apps
        Topic = apps.get_model('courses', 'Topic')
        Course = apps.get_model('courses', 'Course')
        
        try:
            topic = Topic.objects.get(id=obj.content_id)
            if request.user.role == 'admin':
                course = Course.objects.filter(coursetopic__topic=topic).first()
                return course and course.branch == request.user.branch
            if request.user.role == 'instructor':
                course = Course.objects.filter(coursetopic__topic=topic).first()
                return course and (course.instructor == request.user or
                                  course.accessible_groups.filter(
                                      memberships__user=request.user,
                                      memberships__is_active=True
                                  ).exists())
        except Topic.DoesNotExist:
            return False
        return False
