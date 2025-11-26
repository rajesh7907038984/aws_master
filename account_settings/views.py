import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.urls import reverse, NoReverseMatch
from django.contrib import messages
from django.http import HttpResponseForbidden, JsonResponse, FileResponse, Http404
from django.db.models import Count, Prefetch, Q, Sum
from django.core.cache import cache
from smtplib import SMTPException
from socket import timeout as SocketTimeout
from .models import TeamsIntegration, ZoomIntegration, StripeIntegration, PayPalIntegration, SharePointIntegration, PortalSettings, ExportJob, ImportJob, DataBackup, GlobalAdminSettings, MenuControlSettings
from django.contrib.auth import get_user_model
from branches.models import Branch, BranchUserLimits
from business.models import Business, BusinessLimits
import json
import pytz
import os
import subprocess
import threading
import glob
from django.conf import settings
from django.utils import timezone
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
import sys
from core.rbac_validators import ConditionalAccessValidator
from core.rbac_decorators import require_globaladmin
from .zoom import get_zoom_client
# Import AI token models
from tinymce_editor.models import BranchAITokenLimit, AITokenUsage

logger = logging.getLogger(__name__)

def validate_global_admin_branch_access(user, branch_id):
    """
    Validate that a global admin can access and modify a specific branch.
    
    Args:
        user: The user making the request
        branch_id: The ID of the branch to validate
        
    Returns:
        tuple: (is_valid, branch_object, error_message)
    """
    try:
        # Check if user is global admin
        if user.role != 'globaladmin':
            return False, None, "Only global administrators can perform this action"
        
        # Get the branch
        branch = Branch.objects.get(id=branch_id)
        
        # Check if branch is active
        if not branch.is_active:
            return False, None, "Cannot modify inactive branch"
        
        # Global admins can access all active branches
        return True, branch, None
        
    except Branch.DoesNotExist:
        return False, None, "Branch not found"
    except Exception as e:
        logger.error(f"Error validating global admin branch access: {str(e)}")
        return False, None, f"Error validating branch access: {str(e)}"

@login_required
def account_settings(request):
    """Render the account settings page with multiple accordion sections."""
    try:
        active_section = request.GET.get('tab', 'portal')
        active_integration = request.GET.get('integration', 'zoom')
        
        # Define breadcrumbs for navigation
        # Get dashboard URL based on user role
        role_dashboard_urls = {
            'globaladmin': reverse('dashboard_globaladmin'),
            'superadmin': reverse('dashboard_superadmin'),
            'admin': reverse('dashboard_admin'),
            'instructor': reverse('dashboard_instructor'),
            'learner': reverse('dashboard_learner'),
        }
        dashboard_url = role_dashboard_urls.get(request.user.role, reverse('users:role_based_redirect'))
        
        breadcrumbs = [
            {'url': dashboard_url, 'label': 'Dashboard', 'icon': 'fa-tachometer-alt'},
            {'label': 'Account & Settings', 'icon': 'fa-cog'}
        ]
        
        # Check if user is a global admin (highest level)
        is_globaladmin = request.user.role == 'globaladmin'
        # Check if user is a super admin
        is_superadmin = request.user.role in ['globaladmin', 'superadmin']
        # Check if user is a branch admin
        is_branch_admin = request.user.role == 'admin'
        
        # Initialize data for accordion sections
        notification_settings = None
        api_settings = None
        
        # Get or create 2FA settings for the user
        from users.models import TwoFactorAuth
        user_2fa, created = TwoFactorAuth.objects.get_or_create(user=request.user)
        user_2fa_enabled = user_2fa.is_enabled
        oauth_2fa_enabled = user_2fa.oauth_enabled
        totp_2fa_enabled = user_2fa.totp_enabled
        
        # For notification settings section
        if active_section == 'notifications':
            # Here you would fetch notification settings from the database
            # For now, we'll use dummy data
            notification_settings = {
                'email_notifications': {
                    'course_completion': True,
                    'assignment_submission': True,
                    'course_enrollment': True
                },
                'in_app_notifications': {
                    'messages': True,
                    'announcements': True,
                    'due_dates': True
                }
            }
        
        # For API settings section
        if active_section == 'api':
            # Here you would fetch API settings from the database
            # For now, we'll use dummy data
            api_settings = {
                'api_key': 'api_key_12345678',
                'last_generated': 'May 15, 2025',
                'webhook_url': '',
                'webhook_events': {
                    'user_enrollment': False,
                    'course_completion': False,
                    'assignment_submission': False,
                    'quiz_completion': False
                }
            }
        
        # Get or create portal settings if the user is an admin or superadmin
        portal_settings = None
        timezone_choices = [(tz, tz) for tz in pytz.common_timezones]
        
        # Global Admin Settings (for globaladmin and superadmin)
        global_admin_settings = None
        menu_control_settings = None
        
        if is_globaladmin or is_superadmin:
            # Get or create global admin settings
            global_admin_settings = GlobalAdminSettings.get_settings()
            
            # Handle Google OAuth settings form submission
            if request.method == 'POST' and request.POST.get('form_type') == 'google_oauth_settings':
                google_client_id = request.POST.get('google_client_id', '').strip()
                google_client_secret = request.POST.get('google_client_secret', '').strip()
                
                # Google OAuth is always enabled, so we always set it to True
                global_admin_settings.google_oauth_enabled = True
                global_admin_settings.google_client_id = google_client_id
                global_admin_settings.google_client_secret = google_client_secret
                global_admin_settings.google_oauth_domains = request.POST.get('google_oauth_domains', '')
                
                global_admin_settings.updated_by = request.user
                global_admin_settings.save()
                
                if google_client_id and google_client_secret:
                    messages.success(request, 'Google OAuth settings updated successfully. Google Sign-In is now active.')
                else:
                    messages.success(request, 'Google OAuth settings updated successfully.')
                    
                return redirect(f"{reverse('account_settings:settings')}?tab=google_oauth")
            
            # Handle Microsoft OAuth settings form submission
            if request.method == 'POST' and request.POST.get('form_type') == 'microsoft_oauth_settings':
                from .utils import validate_microsoft_oauth_config
                
                microsoft_client_id = request.POST.get('microsoft_client_id', '').strip()
                microsoft_client_secret = request.POST.get('microsoft_client_secret', '').strip()
                microsoft_tenant_id = request.POST.get('microsoft_tenant_id', '').strip()
                
                # Validate the configuration
                if microsoft_client_id and microsoft_client_secret:
                    is_valid, validation_messages = validate_microsoft_oauth_config(
                        microsoft_client_id, 
                        microsoft_client_secret, 
                        microsoft_tenant_id
                    )
                    
                    if not is_valid:
                        for msg in validation_messages:
                            messages.error(request, msg)
                        return redirect(f"{reverse('account_settings:settings')}?tab=microsoft_oauth")
                
                # Microsoft OAuth is always enabled, so we always set it to True
                global_admin_settings.microsoft_oauth_enabled = True
                global_admin_settings.microsoft_client_id = microsoft_client_id
                global_admin_settings.microsoft_client_secret = microsoft_client_secret
                global_admin_settings.microsoft_tenant_id = microsoft_tenant_id if microsoft_tenant_id else 'common'
                global_admin_settings.microsoft_oauth_domains = request.POST.get('microsoft_oauth_domains', '')
                
                global_admin_settings.updated_by = request.user
                global_admin_settings.save()
                
                if microsoft_client_id and microsoft_client_secret:
                    messages.success(request, 'Microsoft OAuth settings updated successfully. Microsoft Sign-In is now active.')
                else:
                    messages.success(request, 'Microsoft OAuth settings updated successfully.')
                    
                return redirect(f"{reverse('account_settings:settings')}?tab=microsoft_oauth")
            
            # Handle GitHub OAuth settings form submission
            if request.method == 'POST' and request.POST.get('form_type') == 'github_oauth_settings':
                github_client_id = request.POST.get('github_client_id', '').strip()
                github_client_secret = request.POST.get('github_client_secret', '').strip()
                
                # GitHub OAuth is enabled if both client_id and client_secret are provided
                github_oauth_enabled = bool(github_client_id and github_client_secret)
                
                global_admin_settings.github_oauth_enabled = github_oauth_enabled
                global_admin_settings.github_client_id = github_client_id
                global_admin_settings.github_client_secret = github_client_secret
                
                global_admin_settings.updated_by = request.user
                global_admin_settings.save()
                
                if github_oauth_enabled:
                    messages.success(request, 'GitHub OAuth settings updated successfully. GitHub Sign-In is now active.')
                else:
                    messages.success(request, 'GitHub OAuth settings cleared successfully.')
                    
                return redirect(f"{reverse('account_settings:settings')}?tab=github_oauth")
            
            # Handle LinkedIn OAuth settings form submission
            if request.method == 'POST' and request.POST.get('form_type') == 'linkedin_oauth_settings':
                linkedin_client_id = request.POST.get('linkedin_client_id', '').strip()
                linkedin_client_secret = request.POST.get('linkedin_client_secret', '').strip()
                
                # LinkedIn OAuth is enabled if both client_id and client_secret are provided
                linkedin_oauth_enabled = bool(linkedin_client_id and linkedin_client_secret)
                
                global_admin_settings.linkedin_oauth_enabled = linkedin_oauth_enabled
                global_admin_settings.linkedin_client_id = linkedin_client_id
                global_admin_settings.linkedin_client_secret = linkedin_client_secret
                
                global_admin_settings.updated_by = request.user
                global_admin_settings.save()
                
                if linkedin_oauth_enabled:
                    messages.success(request, 'LinkedIn OAuth settings updated successfully. LinkedIn Sign-In is now active.')
                else:
                    messages.success(request, 'LinkedIn OAuth settings cleared successfully.')
                    
                return redirect(f"{reverse('account_settings:settings')}?tab=linkedin_oauth")
            
            # Handle Microsoft OAuth settings form submission
            if request.method == 'POST' and request.POST.get('form_type') == 'microsoft_oauth_settings':
                microsoft_client_id = request.POST.get('microsoft_client_id', '').strip()
                microsoft_client_secret = request.POST.get('microsoft_client_secret', '').strip()
                microsoft_tenant_id = request.POST.get('microsoft_tenant_id', '').strip()
                
                # Microsoft OAuth is enabled if all required fields are provided
                microsoft_oauth_enabled = bool(microsoft_client_id and microsoft_client_secret and microsoft_tenant_id)
                
                global_admin_settings.microsoft_oauth_enabled = microsoft_oauth_enabled
                global_admin_settings.microsoft_client_id = microsoft_client_id
                global_admin_settings.microsoft_client_secret = microsoft_client_secret
                global_admin_settings.microsoft_tenant_id = microsoft_tenant_id
                
                global_admin_settings.updated_by = request.user
                global_admin_settings.save()
                
                if microsoft_oauth_enabled:
                    messages.success(request, 'Microsoft OAuth settings updated successfully. Microsoft Sign-In is now active.')
                else:
                    messages.success(request, 'Microsoft OAuth settings cleared successfully.')
                    
                return redirect(f"{reverse('account_settings:settings')}?tab=microsoft_oauth")
            
            # Handle SAML settings form submission
            if request.method == 'POST' and request.POST.get('form_type') == 'saml_settings':
                saml_enabled = request.POST.get('saml_enabled') == 'on'
                entity_id = request.POST.get('saml_entity_id', '').strip()
                sso_url = request.POST.get('saml_sso_url', '').strip()
                x509_cert = request.POST.get('saml_x509_cert', '').strip()
                attribute_mapping = request.POST.get('saml_attribute_mapping', '').strip()
                
                global_admin_settings.saml_enabled = saml_enabled
                global_admin_settings.saml_entity_id = entity_id
                global_admin_settings.saml_sso_url = sso_url
                global_admin_settings.saml_x509_cert = x509_cert
                global_admin_settings.saml_attribute_mapping = attribute_mapping
                
                global_admin_settings.updated_by = request.user
                global_admin_settings.save()
                
                if saml_enabled:
                    messages.success(request, 'SAML settings updated successfully. SAML authentication is now active.')
                else:
                    messages.success(request, 'SAML settings updated successfully.')
                    
                return redirect(f"{reverse('account_settings:settings')}?tab=saml")
            
            # Handle LDAP settings form submission
            if request.method == 'POST' and request.POST.get('form_type') == 'ldap_settings':
                ldap_enabled = request.POST.get('ldap_enabled') == 'on'
                ldap_server_uri = request.POST.get('ldap_server_uri', '').strip()
                ldap_bind_dn = request.POST.get('ldap_bind_dn', '').strip()
                ldap_bind_password = request.POST.get('ldap_bind_password', '').strip()
                ldap_user_search = request.POST.get('ldap_user_search', '').strip()
                ldap_group_search = request.POST.get('ldap_group_search', '').strip()
                ldap_user_attr_map = request.POST.get('ldap_user_attr_map', '').strip()
                
                global_admin_settings.ldap_enabled = ldap_enabled
                global_admin_settings.ldap_server_uri = ldap_server_uri
                global_admin_settings.ldap_bind_dn = ldap_bind_dn
                global_admin_settings.ldap_bind_password = ldap_bind_password
                global_admin_settings.ldap_user_search = ldap_user_search
                global_admin_settings.ldap_group_search = ldap_group_search
                global_admin_settings.ldap_user_attr_map = ldap_user_attr_map
                
                global_admin_settings.updated_by = request.user
                global_admin_settings.save()
                
                if ldap_enabled:
                    messages.success(request, 'LDAP settings updated successfully. LDAP authentication is now active.')
                else:
                    messages.success(request, 'LDAP settings updated successfully.')
                    
                return redirect(f"{reverse('account_settings:settings')}?tab=ldap")
            
            # Handle SMTP settings form submission
            if request.method == 'POST' and request.POST.get('form_type') == 'smtp_settings':
                smtp_enabled = request.POST.get('smtp_enabled') == 'on'
                smtp_host = request.POST.get('smtp_host', '').strip()
                smtp_port = request.POST.get('smtp_port', '587')
                smtp_username = request.POST.get('smtp_username', '').strip()
                smtp_password = request.POST.get('smtp_password', '').strip()
                smtp_use_tls = request.POST.get('smtp_use_tls') == 'on'
                smtp_use_ssl = request.POST.get('smtp_use_ssl') == 'on'
                smtp_from_email = request.POST.get('smtp_from_email', '').strip()
                smtp_from_name = request.POST.get('smtp_from_name', 'LMS Notifications').strip()
                smtp_reply_to_email = request.POST.get('smtp_reply_to_email', '').strip()
                test_smtp_email = request.POST.get('test_smtp_email', '').strip()
                
                # Update SMTP settings
                global_admin_settings.smtp_enabled = smtp_enabled
                if smtp_host:
                    global_admin_settings.smtp_host = smtp_host
                try:
                    global_admin_settings.smtp_port = int(smtp_port)
                except ValueError:
                    global_admin_settings.smtp_port = 587
                if smtp_username:
                    global_admin_settings.smtp_username = smtp_username
                if smtp_password:  # Only update password if provided
                    global_admin_settings.smtp_password = smtp_password
                global_admin_settings.smtp_use_tls = smtp_use_tls
                global_admin_settings.smtp_use_ssl = smtp_use_ssl
                if smtp_from_email:
                    global_admin_settings.smtp_from_email = smtp_from_email
                global_admin_settings.smtp_from_name = smtp_from_name
                if smtp_reply_to_email:
                    global_admin_settings.smtp_reply_to_email = smtp_reply_to_email
                
                global_admin_settings.updated_by = request.user
                global_admin_settings.save()
                
                # Test SMTP connection if requested
                if smtp_enabled and test_smtp_email:
                    try:
                        test_success, test_message = global_admin_settings.test_smtp_connection()
                        if test_success:
                            # Send actual test email
                            from django.core.mail import EmailMessage
                            backend = global_admin_settings.get_email_backend()
                            from_email = global_admin_settings.get_from_email()
                            
                            test_email = EmailMessage(
                                subject=' LMS SMTP Test - Configuration Successful',
                                body=f'''Hello,

This is a test email from your LMS system to confirm that the SMTP configuration is working correctly.

SMTP Configuration Details:
• Host: {smtp_host}
• Port: {smtp_port}
• Username: {smtp_username}
• Encryption: {'TLS' if smtp_use_tls else 'SSL' if smtp_use_ssl else 'None'}
• From Email: {smtp_from_email}

Your email notifications should now be delivered successfully.

Best regards,
LMS System''',
                                from_email=from_email,
                                to=[test_smtp_email],
                                connection=backend
                            )
                            test_email.send()
                            messages.success(request, f'SMTP settings saved and test email sent successfully to {test_smtp_email}')
                        else:
                            messages.warning(request, f'SMTP settings saved but test failed: {test_message}')
                    except (SMTPException, ConnectionError, TimeoutError) as e:
                        messages.warning(request, f'SMTP settings saved but test email failed: {str(e)}')
                    except Exception as e:
                        logger.error(f"Unexpected error in SMTP test: {str(e)}")
                        messages.warning(request, f'SMTP settings saved but test email failed: {str(e)}')
                else:
                    if smtp_enabled:
                        messages.success(request, 'SMTP settings saved successfully. Email notifications are now enabled.')
                    else:
                        messages.success(request, 'SMTP settings saved. Email notifications are disabled.')
                
                return redirect(f"{reverse('account_settings:settings')}?tab=smtp_configuration")
            
            # Handle Anthropic AI settings form submission  
            if request.method == 'POST' and request.POST.get('form_type') == 'anthropic_ai_settings':
                anthropic_ai_enabled = request.POST.get('anthropic_ai_enabled') == 'on'
                anthropic_api_key = request.POST.get('anthropic_api_key', '').strip()
                anthropic_model = request.POST.get('anthropic_model', 'claude-3-5-sonnet-20241022').strip()
                try:
                    anthropic_max_tokens = int(request.POST.get('anthropic_max_tokens', '1000'))
                except ValueError:
                    anthropic_max_tokens = 1000
                
                test_anthropic_ai = request.POST.get('test_anthropic_ai') == 'on'
                
                # Update Anthropic AI settings
                global_admin_settings.anthropic_ai_enabled = anthropic_ai_enabled
                if anthropic_api_key:
                    global_admin_settings.anthropic_api_key = anthropic_api_key
                global_admin_settings.anthropic_model = anthropic_model
                global_admin_settings.anthropic_max_tokens = anthropic_max_tokens
                
                global_admin_settings.updated_by = request.user
                global_admin_settings.save()
                
                # Test Anthropic AI connection if requested
                if anthropic_ai_enabled and test_anthropic_ai and anthropic_api_key:
                    try:
                        test_success, test_message = global_admin_settings.test_anthropic_ai_connection()
                        if test_success:
                            messages.success(request, f'Anthropic AI settings saved and connection tested successfully: {test_message}')
                        else:
                            messages.warning(request, f'Anthropic AI settings saved but connection test failed: {test_message}')
                    except (ConnectionError, TimeoutError, ValueError) as e:
                        messages.warning(request, f'Anthropic AI settings saved but connection test failed: {str(e)}')
                    except Exception as e:
                        logger.error(f"Unexpected error in Anthropic AI test: {str(e)}")
                        messages.warning(request, f'Anthropic AI settings saved but connection test failed: {str(e)}')
                else:
                    if anthropic_ai_enabled and anthropic_api_key:
                        messages.success(request, 'Anthropic AI settings saved successfully. AI content generation is now enabled for TinyMCE editors.')
                    else:
                        messages.success(request, 'Anthropic AI settings saved. AI content generation is disabled.')
                
                return redirect(f"{reverse('account_settings:settings')}?tab=anthropic_ai_configuration")
            
            
            # Get menu control settings - only load when needed
            if active_section == 'menu_control' or request.method == 'POST':
                menu_control_settings = MenuControlSettings.objects.all().order_by('menu_section')
            
            # Handle menu control form submission
            if request.method == 'POST' and request.POST.get('form_type') == 'menu_control':
                for setting in menu_control_settings:
                    setting_key = f"menu_{setting.id}"
                    setting.visible_to_globaladmin = f"{setting_key}_globaladmin" in request.POST
                    setting.visible_to_superadmin = f"{setting_key}_superadmin" in request.POST
                    setting.visible_to_admin = f"{setting_key}_admin" in request.POST
                    setting.visible_to_instructor = f"{setting_key}_instructor" in request.POST
                    setting.visible_to_learner = f"{setting_key}_learner" in request.POST
                    setting.is_active = f"{setting_key}_active" in request.POST
                    setting.updated_by = request.user
                    setting.save()
                
                messages.success(request, 'Menu control settings updated successfully.')
                return redirect(f"{reverse('account_settings:settings')}?tab=menu_control")
            


        # Business data will be loaded via AJAX for better performance
        businesses_with_limits = []
        businesses = []
        
        # Load business and branch data for SharePoint and Order Management sections (Global Admin and Super Admin)
        if is_superadmin and (active_section in ['sharepoint_system', 'order_management_system'] or request.method == 'POST'):
            from business.models import Business
            from branches.models import Branch
            
            # Get all businesses with their branches
            all_businesses = Business.objects.filter(is_active=True).prefetch_related('branches').order_by('name')
            
            for business in all_businesses:
                active_branches = business.branches.filter(is_active=True).order_by('name')
                if active_branches.exists():  # Only include businesses that have active branches
                    # Set the filtered branches directly on the business object for template access
                    business.filtered_branches = active_branches
                    businesses_with_limits.append({
                        'business': business,
                        'branches': active_branches
                    })

        # For superadmin, get portal settings for branches within their business scope
        branch_portal_settings = {}
        branches = None
        if is_superadmin or is_globaladmin:
            from core.utils.business_filtering import filter_branches_by_business
            branches = filter_branches_by_business(request.user).select_related('business').order_by('name')
            
            # Get branch user limits for each branch efficiently
            if active_section in ['portal', 'branches'] or request.method == 'POST':
                branch_settings_dict = {
                    ps.branch_id: ps for ps in PortalSettings.objects.filter(branch__in=branches)
                }
                
                for branch in branches:
                    branch_settings = branch_settings_dict.get(branch.id)
                    if not branch_settings:
                        branch_settings = PortalSettings.objects.create(
                            branch=branch,
                            timezone='UTC'
                        )
                    
                    # Get or create user limits
                    user_limits, created = BranchUserLimits.objects.get_or_create(
                        branch=branch,
                        defaults={
                            'admin_limit': 5,
                            'instructor_limit': 20,
                            'learner_limit': 100
                        }
                    )
                    
                    branch_portal_settings[branch.id] = branch_settings
        
        if is_branch_admin and request.user.branch:
            # Get or create portal settings for the branch with error handling
            try:
                portal_settings, created = PortalSettings.objects.get_or_create(
                    branch=request.user.branch,
                    defaults={
                        'timezone': 'UTC'
                    }
                )
                
                # Handle portal settings form submission
                if request.method == 'POST' and request.POST.get('form_type') == 'portal_settings':
                    timezone_value = request.POST.get('timezone')
                    
                    # Update portal settings with error handling
                    try:
                        portal_settings.timezone = timezone_value
                        portal_settings.save()
                        messages.success(request, 'Portal settings updated successfully.')
                    except Exception as save_error:
                        logger.error(f"Error saving portal settings: {str(save_error)}")
                        messages.error(request, 'Failed to update portal settings. Please try again.')
                    
                    return redirect(f"{reverse('account_settings:settings')}?tab=portal")
                    
            except Exception as portal_error:
                logger.error(f"Error accessing portal settings: {str(portal_error)}")
                messages.warning(request, 'Portal settings temporarily unavailable. Database migration may be in progress.')
                portal_settings = None  # Set to None so template can handle gracefully

        # Initialize integration data structures - provide empty structure for template
        all_admin_integrations = {
            'teams': [],
            'zoom': [],
            'stripe': [],
            'paypal': []
        }
        all_branch_users_integrations = {}
        branch_admin_integrations = {
            'teams': [],
            'zoom': [],
            'stripe': [],
            'paypal': []
        }
        
        # Only load integration data when needed (integrations, payments, or admin_users tab)
        if is_superadmin and active_section in ['integrations', 'payments', 'admin_users']:
            User = get_user_model()
            
            # Optimize admin integrations query
            admin_users = User.objects.filter(role='admin').select_related('branch')
            
            # Prefetch all integrations at once
            teams_integrations = {ti.user_id: ti for ti in TeamsIntegration.objects.filter(user__in=admin_users).select_related('user')}
            stripe_integrations = {si.user_id: si for si in StripeIntegration.objects.filter(user__in=admin_users).select_related('user')}
            paypal_integrations = {pi.user_id: pi for pi in PayPalIntegration.objects.filter(user__in=admin_users).select_related('user')}
            sharepoint_integrations = {si.user_id: si for si in SharePointIntegration.objects.filter(user__in=admin_users).select_related('user')}
            
            all_admin_integrations = {
                'teams': [],
                'zoom': [],  # Empty - we only show user's own zoom integration
                'stripe': [],
                'paypal': [],
                'sharepoint': []
            }
            
            for admin in admin_users:
                # Get integrations for each admin
                if admin.id in teams_integrations:
                    all_admin_integrations['teams'].append({
                        'integration': teams_integrations[admin.id],
                        'admin': admin
                    })
                
                if admin.id in stripe_integrations:
                    all_admin_integrations['stripe'].append({
                        'integration': stripe_integrations[admin.id],
                        'admin': admin
                    })
                
                if admin.id in paypal_integrations:
                    all_admin_integrations['paypal'].append({
                        'integration': paypal_integrations[admin.id],
                        'admin': admin
                    })
                
                if admin.id in sharepoint_integrations:
                    all_admin_integrations['sharepoint'].append({
                        'integration': sharepoint_integrations[admin.id],
                        'admin': admin
                    })
            
            # Get users with their integrations organized by branch (business-scoped for Super Admin)
            from core.utils.business_filtering import filter_branches_by_business
            all_branches = filter_branches_by_business(request.user)
            all_branch_users_integrations = {}
            
            for branch in all_branches:
                branch_users = User.objects.filter(branch=branch).select_related('branch').order_by('role', 'first_name', 'last_name')
                branch_integrations = {
                    'branch': branch,
                    'users': []
                }
                
                # Get all integrations for branch users at once
                user_ids = [user.id for user in branch_users]
                teams_dict = {ti.user_id: ti for ti in TeamsIntegration.objects.filter(user_id__in=user_ids)}
                # Zoom integration only for branch admins - skip for global/super admins
                zoom_dict = {}
                stripe_dict = {si.user_id: si for si in StripeIntegration.objects.filter(user_id__in=user_ids)}
                paypal_dict = {pi.user_id: pi for pi in PayPalIntegration.objects.filter(user_id__in=user_ids)}
                sharepoint_dict = {si.user_id: si for si in SharePointIntegration.objects.filter(user_id__in=user_ids)}
                
                for user in branch_users:
                    user_integrations = {
                        'user': user,
                        'teams': [teams_dict[user.id]] if user.id in teams_dict else [],
                        'zoom': [zoom_dict[user.id]] if user.id in zoom_dict else [],
                        'stripe': [stripe_dict[user.id]] if user.id in stripe_dict else [],
                        'paypal': [paypal_dict[user.id]] if user.id in paypal_dict else [],
                        'sharepoint': [sharepoint_dict[user.id]] if user.id in sharepoint_dict else [],
                    }
                    
                    # Only include users who have at least one integration
                    has_integrations = any([
                        user_integrations['teams'],
                        user_integrations['zoom'],
                        user_integrations['stripe'],
                        user_integrations['paypal'],
                        user_integrations['sharepoint']
                    ])
                    
                    if has_integrations:
                        branch_integrations['users'].append(user_integrations)
                
                # Only include branches that have users with integrations
                if branch_integrations['users']:
                    all_branch_users_integrations[branch.id] = branch_integrations
            
            # Also include users without branches (if any have integrations)
            users_without_branch = User.objects.filter(branch__isnull=True).order_by('role', 'first_name', 'last_name')
            no_branch_integrations = {
                'branch': None,
                'users': []
            }
            
            user_ids = [user.id for user in users_without_branch]
            if user_ids:
                teams_dict = {ti.user_id: ti for ti in TeamsIntegration.objects.filter(user_id__in=user_ids)}
                # Zoom integration only for branch admins - skip for global/super admins
                zoom_dict = {}
                stripe_dict = {si.user_id: si for si in StripeIntegration.objects.filter(user_id__in=user_ids)}
                paypal_dict = {pi.user_id: pi for pi in PayPalIntegration.objects.filter(user_id__in=user_ids)}
                
                for user in users_without_branch:
                    user_integrations = {
                        'user': user,
                        'teams': [teams_dict[user.id]] if user.id in teams_dict else [],
                        'zoom': [zoom_dict[user.id]] if user.id in zoom_dict else [],
                        'stripe': [stripe_dict[user.id]] if user.id in stripe_dict else [],
                        'paypal': [paypal_dict[user.id]] if user.id in paypal_dict else [],
                    }
                    
                    has_integrations = any([
                        user_integrations['teams'],
                        user_integrations['zoom'],
                        user_integrations['stripe'],
                        user_integrations['paypal']
                    ])
                    
                    if has_integrations:
                        no_branch_integrations['users'].append(user_integrations)
                
                if no_branch_integrations['users']:
                    all_branch_users_integrations[None] = no_branch_integrations

        # Branch admin integrations - only load when needed
        if not is_superadmin and request.user.branch and active_section in ['integrations', 'payments', 'admin_users']:
            User = get_user_model()
            # Get admin users from the same branch
            branch_admins = User.objects.filter(role='admin', branch=request.user.branch)
            
            # Prefetch integrations
            teams_dict = {ti.user_id: ti for ti in TeamsIntegration.objects.filter(user__in=branch_admins, is_active=True)}
            # Zoom integration only for branch admins - skip for global/super admins
            zoom_dict = {}
            stripe_dict = {si.user_id: si for si in StripeIntegration.objects.filter(user__in=branch_admins, is_active=True)}
            paypal_dict = {pi.user_id: pi for pi in PayPalIntegration.objects.filter(user__in=branch_admins, is_active=True)}
            sharepoint_dict = {si.user_id: si for si in SharePointIntegration.objects.filter(user__in=branch_admins, is_active=True)}
            
            branch_admin_integrations = {
                'teams': [],
                'zoom': [],
                'stripe': [],
                'paypal': [],
                'sharepoint': []
            }
            
            for admin in branch_admins:
                if admin.id in teams_dict:
                    branch_admin_integrations['teams'].append({
                        'integration': teams_dict[admin.id],
                        'admin': admin
                    })
                
                if admin.id in zoom_dict:
                    branch_admin_integrations['zoom'].append({
                        'integration': zoom_dict[admin.id],
                        'admin': admin
                    })
                
                if admin.id in stripe_dict:
                    branch_admin_integrations['stripe'].append({
                        'integration': stripe_dict[admin.id],
                        'admin': admin
                    })
                
                if admin.id in paypal_dict:
                    branch_admin_integrations['paypal'].append({
                        'integration': paypal_dict[admin.id],
                        'admin': admin
                    })
                
                if admin.id in sharepoint_dict:
                    branch_admin_integrations['sharepoint'].append({
                        'integration': sharepoint_dict[admin.id],
                        'admin': admin
                    })
                
        
        # Initialize variables to store user's own integrations
        teams_integration = None
        zoom_integration = None
        stripe_integration = None
        paypal_integration = None
        sharepoint_integration = None
        
        # Always load user's own integrations for proper template rendering
        teams_integration = TeamsIntegration.objects.filter(user=request.user).first()
        # Zoom integration only for branch admins
        zoom_integration = ZoomIntegration.objects.filter(user=request.user).first() if is_branch_admin else None
        stripe_integration = StripeIntegration.objects.filter(user=request.user).first()
        paypal_integration = PayPalIntegration.objects.filter(user=request.user).first()
        sharepoint_integration = SharePointIntegration.objects.filter(user=request.user).first()
        
        
        # Get SharePoint sync mode status
        sharepoint_sync_status = None
        if sharepoint_integration and sharepoint_integration.is_active:
            try:
                from sharepoint_integration.utils import get_sync_mode
                sharepoint_sync_status = get_sync_mode()
            except Exception as e:
                # If there's any error, set a default status
                sharepoint_sync_status = {
                    'mode': 'sync',
                    'description': 'Synchronous processing',
                    'performance': 'Standard - operations run immediately',
                    'celery_status': {
                        'available': False,
                        'status': 'error',
                        'message': f'Error checking status: {str(e)}'
                    }
                }
        
        # Load branches data if accessing branches section or if it's a superadmin/globaladmin
        branches_with_limits = []
        businesses_with_branches = []
        if is_superadmin or is_globaladmin:
            # Always load branches data for admin users (needed for SharePoint Integration section)
            # The condition is simplified to always load for better UX
            from core.utils.business_filtering import filter_branches_by_business
            from business.models import Business
            
            branches_query = filter_branches_by_business(request.user).select_related('business').annotate(
                admin_count=Count('users', filter=Q(users__role='admin', users__is_active=True)),
                instructor_count=Count('users', filter=Q(users__role='instructor', users__is_active=True)),
                learner_count=Count('users', filter=Q(users__role='learner', users__is_active=True)),
                total_users=Count('users', filter=Q(users__is_active=True))
            ).order_by('business__name', 'name')
            
            # Get user limits efficiently
            user_limits_dict = {
                ul.branch_id: ul for ul in BranchUserLimits.objects.filter(branch__in=branches_query)
                        }
            
            # Group branches by business for better organization
            businesses_dict = {}
            
            for branch in branches_query:
                # Get or create user limits for this branch
                user_limits = user_limits_dict.get(branch.id)
                if not user_limits:
                    user_limits = BranchUserLimits.objects.create(
                        branch=branch,
                        admin_limit=5,
                        instructor_limit=20,
                        learner_limit=100,
                        user_limit=125
                    )
                
                branch_data = {
                    'branch': branch,
                    'user_limits': user_limits,
                    'usage_data': {
                        'total': {
                            'current': branch.total_users,
                            'limit': user_limits.user_limit,
                            'remaining': max(0, user_limits.user_limit - branch.total_users),
                            'percentage': min(100, (branch.total_users / user_limits.user_limit) * 100) if user_limits.user_limit > 0 else 0
                        },
                        'admin': {
                            'current': branch.admin_count,
                            'limit': user_limits.admin_limit,
                            'remaining': max(0, user_limits.admin_limit - branch.admin_count)
                        },
                        'instructor': {
                            'current': branch.instructor_count,
                            'limit': user_limits.instructor_limit,
                            'remaining': max(0, user_limits.instructor_limit - branch.instructor_count)
                        },
                        'learner': {
                            'current': branch.learner_count,
                            'limit': user_limits.learner_limit,
                            'remaining': max(0, user_limits.learner_limit - branch.learner_count)
                        }
                    }
                }
                
                branches_with_limits.append(branch_data)
                
                # Group by business
                business_name = branch.business.name if branch.business else 'No Business'
                if business_name not in businesses_dict:
                    businesses_dict[business_name] = {
                        'business': branch.business,
                        'branches': []
                    }
                businesses_dict[business_name]['branches'].append(branch_data)
            
            # Convert to list for template
            businesses_with_branches = list(businesses_dict.values())

        # Handle integration saves
        if request.method == 'POST':
            form_type = request.POST.get('form_type')
            
            # Handle integration forms (zoom, stripe, paypal, teams)
            if form_type in ['teams_integration', 'zoom_integration', 'stripe_integration', 'paypal_integration', 'sharepoint_integration', 'enable_branch_sharepoint', 'sharepoint_system_settings', 'teams_system_settings', 'enable_branch_teams', 'order_management_system_settings']:
                
                # Teams Integration Form
                if form_type == 'teams_integration':
                    if not request.user.branch or request.user.role not in ['admin', 'superadmin', 'globaladmin']:
                        messages.error(request, 'Permission denied.')
                        return redirect('account_settings:settings')
                    
                    name = request.POST.get('teams_name')
                    client_id = request.POST.get('teams_client_id')
                    client_secret = request.POST.get('teams_client_secret')
                    tenant_id = request.POST.get('teams_tenant_id')
                    service_account_email = request.POST.get('teams_service_account_email', '').strip()
                    
                    # Check if integration already exists for this branch
                    existing_integration = TeamsIntegration.objects.filter(branch=request.user.branch).first()
                    
                    # Validate required fields
                    if existing_integration:
                        # For updates, client_secret is optional
                        if not all([name, client_id, tenant_id]):
                            messages.error(request, 'Integration Name, Client ID, and Tenant ID are required.')
                            return redirect(reverse('account_settings:settings') + '?tab=integrations&integration=teams')
                    else:
                        # For new integrations, all fields are required
                        if not all([name, client_id, client_secret, tenant_id]):
                            messages.error(request, 'All fields are required for Teams integration.')
                            return redirect(reverse('account_settings:settings') + '?tab=integrations&integration=teams')
                    
                    # Get or create Teams integration for this branch
                    integration, created = TeamsIntegration.objects.get_or_create(
                        branch=request.user.branch,
                        defaults={
                            'name': name,
                            'client_id': client_id,
                            'client_secret': client_secret,
                            'tenant_id': tenant_id,
                            'service_account_email': service_account_email if service_account_email else None,
                            'user': request.user
                        }
                    )
                    
                    if not created:
                        # Update existing integration
                        integration.name = name
                        integration.client_id = client_id
                        if client_secret:  # Only update if new secret provided
                            integration.client_secret = client_secret
                        integration.tenant_id = tenant_id
                        integration.service_account_email = service_account_email if service_account_email else None
                        integration.save()
                        messages.success(request, 'Microsoft Teams integration updated successfully.')
                    else:
                        messages.success(request, 'Microsoft Teams integration created successfully.')
                    
                    return redirect(reverse('account_settings:settings') + '?tab=integrations&integration=teams')
                
                # Zoom Integration Form (only for branch admins)
                elif form_type == 'zoom_integration':
                    if not is_branch_admin:
                        messages.error(request, 'Access denied. Only branch admins can configure Zoom integration.')
                        return redirect('account_settings:settings')
                    
                    name = request.POST.get('zoom_name')
                    api_key = request.POST.get('zoom_api_key')
                    api_secret = request.POST.get('zoom_api_secret')
                    account_id = request.POST.get('zoom_account_id', '')
                    is_active = request.POST.get('zoom_is_active') == 'on'
                    
                    if zoom_integration:
                        zoom_integration.name = name
                        zoom_integration.api_key = api_key
                        zoom_integration.api_secret = api_secret
                        zoom_integration.account_id = account_id
                        zoom_integration.is_active = is_active
                        zoom_integration.save()
                        messages.success(request, 'Zoom integration updated successfully.')
                    else:
                        zoom_integration = ZoomIntegration.objects.create(
                            user=request.user,
                            name=name,
                            api_key=api_key,
                            api_secret=api_secret,
                            account_id=account_id,
                            is_active=is_active,
                            branch=request.user.branch
                        )
                        messages.success(request, 'Zoom integration created successfully.')
                    
                    return redirect(reverse('account_settings:settings') + '?tab=integrations&integration=zoom')
                
                # Stripe Integration Form
                elif form_type == 'stripe_integration' and is_branch_admin:
                    name = request.POST.get('stripe_name')
                    publishable_key = request.POST.get('stripe_publishable_key')
                    secret_key = request.POST.get('stripe_secret_key')
                    webhook_secret = request.POST.get('stripe_webhook_secret', '')
                    is_test_mode = request.POST.get('stripe_is_test_mode') == 'on'
                    is_active = request.POST.get('stripe_is_active') == 'on'
                    
                    if stripe_integration:
                        stripe_integration.name = name
                        stripe_integration.publishable_key = publishable_key
                        stripe_integration.secret_key = secret_key
                        stripe_integration.webhook_secret = webhook_secret
                        stripe_integration.is_test_mode = is_test_mode
                        stripe_integration.is_active = is_active
                        stripe_integration.save()
                        messages.success(request, 'Stripe integration updated successfully.')
                    else:
                        stripe_integration = StripeIntegration.objects.create(
                            user=request.user,
                            name=name,
                            publishable_key=publishable_key,
                            secret_key=secret_key,
                            webhook_secret=webhook_secret,
                            is_test_mode=is_test_mode,
                            is_active=is_active,
                            branch=request.user.branch
                        )
                        messages.success(request, 'Stripe integration created successfully.')
                    
                    return redirect(reverse('account_settings:settings') + '?tab=payments&integration=stripe')
                
                # PayPal Integration Form
                elif form_type == 'paypal_integration' and is_branch_admin:
                    name = request.POST.get('paypal_name')
                    client_id = request.POST.get('paypal_client_id')
                    client_secret = request.POST.get('paypal_client_secret')
                    is_sandbox = request.POST.get('paypal_is_sandbox') == 'on'
                    is_active = request.POST.get('paypal_is_active') == 'on'
                    
                    if paypal_integration:
                        paypal_integration.name = name
                        paypal_integration.client_id = client_id
                        paypal_integration.client_secret = client_secret
                        paypal_integration.is_sandbox = is_sandbox
                        paypal_integration.is_active = is_active
                        paypal_integration.save()
                        messages.success(request, 'PayPal integration updated successfully.')
                    else:
                        paypal_integration = PayPalIntegration.objects.create(
                            user=request.user,
                            name=name,
                            client_id=client_id,
                            client_secret=client_secret,
                            is_sandbox=is_sandbox,
                            is_active=is_active,
                            branch=request.user.branch
                        )
                        messages.success(request, 'PayPal integration created successfully.')
                    
                    return redirect(reverse('account_settings:settings') + '?tab=payments&integration=paypal')
                
                # SharePoint Integration Form
                elif form_type == 'sharepoint_integration':
                    name = request.POST.get('sharepoint_name')
                    tenant_id = request.POST.get('sharepoint_tenant_id')
                    client_id = request.POST.get('sharepoint_client_id')
                    client_secret = request.POST.get('sharepoint_client_secret')
                    site_url = request.POST.get('sharepoint_site_url')
                    is_active = request.POST.get('sharepoint_is_active') == 'on'
                    
                    # Optional fields
                    user_list_name = request.POST.get('sharepoint_user_list_name', 'LMS Users')
                    enrollment_list_name = request.POST.get('sharepoint_enrollment_list_name', 'Course Enrollments')
                    progress_list_name = request.POST.get('sharepoint_progress_list_name', 'Learning Progress')
                    certificate_library_name = request.POST.get('sharepoint_certificate_library_name', 'Certificates')
                    reports_library_name = request.POST.get('sharepoint_reports_library_name', 'Reports')
                    assessment_library_name = request.POST.get('sharepoint_assessment_library_name', 'Assessments')
                    
                    # Power BI fields
                    powerbi_workspace_id = request.POST.get('sharepoint_powerbi_workspace_id', '')
                    powerbi_dataset_id = request.POST.get('sharepoint_powerbi_dataset_id', '')
                    
                    # Sync configuration
                    enable_user_sync = request.POST.get('sharepoint_enable_user_sync') == 'on'
                    enable_enrollment_sync = request.POST.get('sharepoint_enable_enrollment_sync') == 'on'
                    enable_progress_sync = request.POST.get('sharepoint_enable_progress_sync') == 'on'
                    enable_certificate_sync = request.POST.get('sharepoint_enable_certificate_sync') == 'on'
                    enable_reports_sync = request.POST.get('sharepoint_enable_reports_sync') == 'on'
                    enable_assessment_sync = request.POST.get('sharepoint_enable_assessment_sync') == 'on'
                    
                    # Update existing or create new
                    sharepoint_integration = SharePointIntegration.objects.filter(user=request.user).first()
                    
                    if sharepoint_integration:
                        sharepoint_integration.name = name
                        sharepoint_integration.tenant_id = tenant_id
                        sharepoint_integration.client_id = client_id
                        sharepoint_integration.client_secret = client_secret
                        sharepoint_integration.site_url = site_url
                        sharepoint_integration.is_active = is_active
                        sharepoint_integration.user_list_name = user_list_name
                        sharepoint_integration.enrollment_list_name = enrollment_list_name
                        sharepoint_integration.progress_list_name = progress_list_name
                        sharepoint_integration.certificate_library_name = certificate_library_name
                        sharepoint_integration.reports_library_name = reports_library_name
                        sharepoint_integration.assessment_library_name = assessment_library_name
                        sharepoint_integration.powerbi_workspace_id = powerbi_workspace_id
                        sharepoint_integration.powerbi_dataset_id = powerbi_dataset_id
                        sharepoint_integration.enable_user_sync = enable_user_sync
                        sharepoint_integration.enable_enrollment_sync = enable_enrollment_sync
                        sharepoint_integration.enable_progress_sync = enable_progress_sync
                        sharepoint_integration.enable_certificate_sync = enable_certificate_sync
                        sharepoint_integration.enable_reports_sync = enable_reports_sync
                        sharepoint_integration.enable_assessment_sync = enable_assessment_sync
                        sharepoint_integration.save()
                        messages.success(request, 'SharePoint integration updated successfully.')
                    else:
                        sharepoint_integration = SharePointIntegration.objects.create(
                            user=request.user,
                            name=name,
                            tenant_id=tenant_id,
                            client_id=client_id,
                            client_secret=client_secret,
                            site_url=site_url,
                            is_active=is_active,
                            user_list_name=user_list_name,
                            enrollment_list_name=enrollment_list_name,
                            progress_list_name=progress_list_name,
                            certificate_library_name=certificate_library_name,
                            reports_library_name=reports_library_name,
                            assessment_library_name=assessment_library_name,
                            powerbi_workspace_id=powerbi_workspace_id,
                            powerbi_dataset_id=powerbi_dataset_id,
                            enable_user_sync=enable_user_sync,
                            enable_enrollment_sync=enable_enrollment_sync,
                            enable_progress_sync=enable_progress_sync,
                            enable_certificate_sync=enable_certificate_sync,
                            enable_reports_sync=enable_reports_sync,
                            enable_assessment_sync=enable_assessment_sync,
                            branch=request.user.branch
                        )
                        messages.success(request, 'SharePoint integration created successfully.')
                    
                    return redirect(reverse('account_settings:settings') + '?tab=integrations&integration=sharepoint')
                
                
                # Enable SharePoint Integration for Branch Form
                elif form_type == 'enable_branch_sharepoint':
                    branch_id = request.POST.get('branch_id')
                    if branch_id:
                        # Use the validation function
                        is_valid, branch, error_msg = validate_global_admin_branch_access(request.user, branch_id)
                        
                        if not is_valid:
                            messages.error(request, error_msg)
                        else:
                            # Check if integration is already enabled
                            if branch.sharepoint_integration_enabled:
                                messages.warning(request, f'SharePoint integration is already enabled for {branch.name}.')
                            else:
                                branch.sharepoint_integration_enabled = True
                                branch.save()
                                messages.success(request, f'SharePoint integration enabled for {branch.name}.')
                    else:
                        messages.error(request, 'Branch ID not provided.')
                    
                    return redirect(reverse('account_settings:settings') + '?tab=integrations&integration=sharepoint')
                
                # SharePoint System Settings Form (Global Admin only)
                elif form_type == 'sharepoint_system_settings':
                    if request.user.role == 'globaladmin':
                        try:
                            from branches.models import Branch
                            
                            # Update global SharePoint integration setting
                            sharepoint_integration_enabled = request.POST.get('sharepoint_integration_enabled') == 'on'
                            global_admin_settings.sharepoint_integration_enabled = sharepoint_integration_enabled
                            global_admin_settings.save()
                            
                            # Update branch-level SharePoint integration settings
                            all_branches = Branch.objects.all()
                            updated_branches = []
                            
                            # Use bulk update to avoid model validation issues
                            enabled_branch_ids = []
                            for branch in all_branches:
                                branch_enabled = request.POST.get(f'branch_sharepoint_{branch.id}') == 'on'
                                if branch_enabled:
                                    enabled_branch_ids.append(branch.id)
                            
                            # Disable SharePoint integration for all branches first
                            Branch.objects.all().update(sharepoint_integration_enabled=False)
                            
                            # Enable SharePoint integration for selected branches
                            if enabled_branch_ids:
                                Branch.objects.filter(id__in=enabled_branch_ids).update(sharepoint_integration_enabled=True)
                                updated_branches = list(Branch.objects.filter(id__in=enabled_branch_ids).values_list('name', flat=True))
                            
                            # If no branches were selected, all branches are disabled
                            if not enabled_branch_ids:
                                updated_branches = ['All branches disabled']
                            
                            success_message = 'SharePoint system settings updated successfully.'
                            if updated_branches:
                                success_message += f' Updated branches: {", ".join(updated_branches)}'
                            
                            messages.success(request, success_message)
                            
                        except Exception as e:
                            logger.error(f"Error updating SharePoint system settings: {str(e)}")
                            messages.error(request, f'Error updating SharePoint system settings: {str(e)}')
                    else:
                        messages.error(request, 'Only global administrators can modify SharePoint system settings.')
                    
                    return redirect(f"{reverse('account_settings:settings')}?tab=sharepoint_system")
                
                # Teams System Settings Form (Global Admin only)
                elif form_type == 'teams_system_settings':
                    if request.user.role == 'globaladmin':
                        try:
                            from branches.models import Branch
                            
                            # Update global Teams integration setting
                            teams_integration_enabled = request.POST.get('teams_integration_enabled') == 'on'
                            teams_sync_entra_groups = request.POST.get('teams_sync_entra_groups') == 'on'
                            teams_sync_meetings = request.POST.get('teams_sync_meetings') == 'on'
                            teams_sync_attendance = request.POST.get('teams_sync_attendance') == 'on'
                            
                            global_admin_settings.teams_integration_enabled = teams_integration_enabled
                            global_admin_settings.teams_sync_entra_groups = teams_sync_entra_groups
                            global_admin_settings.teams_sync_meetings = teams_sync_meetings
                            global_admin_settings.teams_sync_attendance = teams_sync_attendance
                            global_admin_settings.save()
                            
                            # Update branch-level Teams integration settings
                            all_branches = Branch.objects.all()
                            updated_branches = []
                            
                            # Use bulk update to avoid model validation issues
                            enabled_branch_ids = []
                            for branch in all_branches:
                                branch_enabled = request.POST.get(f'teams_enabled_branches') and str(branch.id) in request.POST.getlist('teams_enabled_branches')
                                if branch_enabled:
                                    enabled_branch_ids.append(branch.id)
                            
                            # Disable Teams integration for all branches first
                            Branch.objects.all().update(teams_integration_enabled=False)
                            
                            # Enable Teams integration for selected branches
                            if enabled_branch_ids:
                                Branch.objects.filter(id__in=enabled_branch_ids).update(teams_integration_enabled=True)
                                updated_branches = list(Branch.objects.filter(id__in=enabled_branch_ids).values_list('name', flat=True))
                            
                            # If no branches were selected, all branches are disabled
                            if not enabled_branch_ids:
                                updated_branches = ['All branches disabled']
                            
                            success_message = 'Teams system settings updated successfully.'
                            if updated_branches:
                                success_message += f' Updated branches: {", ".join(updated_branches)}'
                            
                            messages.success(request, success_message)
                            
                        except Exception as e:
                            logger.error(f"Error updating Teams system settings: {str(e)}")
                            messages.error(request, f'Error updating Teams system settings: {str(e)}')
                    else:
                        messages.error(request, 'Only global administrators can modify Teams system settings.')
                    
                    return redirect(f"{reverse('account_settings:settings')}?tab=teams_system")
                
                # Enable Branch Teams Integration (Global Admin only)
                elif form_type == 'enable_branch_teams':
                    branch_id = request.POST.get('branch_id')
                    if branch_id:
                        # Use the validation function
                        is_valid, branch, error_msg = validate_global_admin_branch_access(request.user, branch_id)
                        
                        if not is_valid:
                            messages.error(request, error_msg)
                        else:
                            # Check if integration is already enabled
                            if branch.teams_integration_enabled:
                                messages.warning(request, f'Teams integration is already enabled for {branch.name}.')
                            else:
                                branch.teams_integration_enabled = True
                                branch.save()
                                messages.success(request, f'Teams integration enabled for {branch.name}.')
                    else:
                        messages.error(request, 'Branch ID not provided.')
                    
                    return redirect(reverse('account_settings:settings') + '?tab=integrations&integration=teams')
                
                # Order Management System Settings Form (Global Admin and Super Admin)
                elif form_type == 'order_management_system_settings':
                    if request.user.role in ['globaladmin', 'superadmin']:
                        try:
                            from branches.models import Branch
                            
                            # Update global order management setting
                            order_management_enabled = request.POST.get('order_management_enabled') == 'on'
                            global_admin_settings.order_management_enabled = order_management_enabled
                            global_admin_settings.save()
                            
                            # Update branch-level order management settings
                            branch_order_management_values = request.POST.getlist('branch_order_management')
                            all_branches = Branch.objects.all()
                            updated_branches = []
                            
                            # Use bulk update to avoid model validation issues
                            enabled_branch_ids = [int(bid) for bid in branch_order_management_values if bid.isdigit()]
                            
                            # Disable order management for all branches first
                            Branch.objects.all().update(order_management_enabled=False)
                            
                            # Enable order management for selected branches
                            if enabled_branch_ids:
                                Branch.objects.filter(id__in=enabled_branch_ids).update(order_management_enabled=True)
                                updated_branches = list(Branch.objects.filter(id__in=enabled_branch_ids).values_list('name', flat=True))
                            
                            # If no branches were selected, all branches are disabled
                            if not enabled_branch_ids:
                                updated_branches = ['All branches disabled']
                            
                            success_message = 'Order Management system settings updated successfully.'
                            if updated_branches:
                                success_message += f' Updated branches: {", ".join(updated_branches)}'
                            
                            messages.success(request, success_message)
                            
                        except Exception as e:
                            logger.error(f"Error updating Order Management system settings: {str(e)}")
                            messages.error(request, f'Error updating Order Management system settings: {str(e)}')
                    else:
                        messages.error(request, 'Only global administrators and super administrators can modify Order Management system settings.')
                    
                    return redirect(f"{reverse('account_settings:settings')}?tab=order_management_system")
                

                
                # Redirect to same page to prevent form resubmission
                return redirect(f"{reverse('account_settings:settings')}?tab=integrations&integration={form_type}")
        
        # Convert single integrations to lists with one item for template compatibility
        teams_integrations = [teams_integration] if teams_integration else []
        zoom_integrations = [zoom_integration] if zoom_integration else []
        sharepoint_integrations = [sharepoint_integration] if sharepoint_integration else []
        
        # Debug information
        if zoom_integration:
            logger.info(f"Zoom integration found for user {request.user.id}: ID={zoom_integration.id}, active={zoom_integration.is_active}, name={zoom_integration.name}")
        else:
            logger.info(f"No existing zoom integration for user {request.user.id}")
            
        # If we still have a None ID, fix the template context manually
        if zoom_integration and zoom_integration.id is None:
            logger.warning(f"Still have a None ID for Zoom integration, setting to -1 for template rendering")
            zoom_integration.id = -1  # Set a temporary ID to make template render correctly
            
        # Define available Zoom meeting templates (for future implementation of template selection)
        available_zoom_meeting_templates = []
        
        # Generate Google OAuth redirect URIs for display
        google_oauth_redirect_uri = None
        microsoft_oauth_redirect_uri = None
        if is_globaladmin:
            google_oauth_redirect_uri = request.build_absolute_uri(reverse('users:google_callback'))
            microsoft_oauth_redirect_uri = request.build_absolute_uri(reverse('users:microsoft_callback'))
        

        # AI Token Management data (for Global Admins and Branch Admins)
        ai_token_data = None
        
        # Storage Management data (for Global Admins and Branch Admins)
        storage_data = None
        if is_globaladmin or is_branch_admin:
            try:
                from branches.models import Branch  # Local import to avoid scoping issues
                if is_globaladmin:
                    # Global Admin: Show all branches with AI token data
                    branches = Branch.objects.all().select_related('business').prefetch_related('ai_token_limits')
                    ai_branches_data = []
                    
                    for branch in branches:
                        # Get or create token limits for this branch
                        token_limits, created = BranchAITokenLimit.objects.get_or_create(
                            branch=branch,
                            defaults={'monthly_token_limit': 10000, 'is_unlimited': False}
                        )
                        
                        # Get current month usage
                        current_usage = token_limits.get_current_month_usage()
                        usage_percentage = token_limits.get_usage_percentage()
                        
                        # Get user count for this branch
                        user_count = branch.users.filter(is_active=True).count()
                        
                        ai_branches_data.append({
                            'branch': branch,
                            'token_limits': token_limits,
                            'current_usage': current_usage,
                            'usage_percentage': usage_percentage,
                            'user_count': user_count,
                            'status': 'unlimited' if token_limits.is_unlimited else (
                                'exceeded' if usage_percentage >= 100 else (
                                    'warning' if usage_percentage >= 80 else 'normal'
                                )
                            ),
                        })
                    
                    ai_token_data = {
                        'branches': ai_branches_data,
                        'is_global_admin': True
                    }
                
                elif is_branch_admin and request.user.branch:
                    # Branch Admin: Show only their branch data
                    branch = request.user.branch
                    
                    # Get or create token limits for this branch
                    token_limits, created = BranchAITokenLimit.objects.get_or_create(
                        branch=branch,
                        defaults={'monthly_token_limit': 10000, 'is_unlimited': False}
                    )
                    
                    # Get current month usage and user count
                    current_usage = token_limits.get_current_month_usage()
                    usage_percentage = token_limits.get_usage_percentage()
                    user_count = branch.users.filter(is_active=True).count()
                    
                    # Get recent usage activity (last 10 records)
                    recent_usage = AITokenUsage.objects.filter(
                        user__branch=branch
                    ).select_related('user').order_by('-created_at')[:10]
                    
                    # Get top users this month  
                    now = timezone.now()
                    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                    
                    top_users = AITokenUsage.objects.filter(
                        user__branch=branch,
                        created_at__gte=start_of_month
                    ).values(
                        'user__username', 'user__email'
                    ).annotate(
                        total_tokens=Sum('tokens_used'),
                        request_count=Count('id')
                    ).order_by('-total_tokens')[:5]
                    
                    ai_token_data = {
                        'branch': branch,
                        'token_limits': token_limits,
                        'current_usage': current_usage,
                        'usage_percentage': usage_percentage,
                        'user_count': user_count,
                        'recent_usage': recent_usage,
                        'top_users': top_users,
                        'is_global_admin': False
                    }
                    
            except Exception as e:
                logger.error(f"Error loading AI token data: {str(e)}")
                ai_token_data = None

        # Storage Management data (for Global Admins and Branch Admins)
        storage_data = None
        if is_globaladmin or is_branch_admin:
            try:
                from core.models import BranchStorageLimit, FileStorageUsage
                from core.utils.storage_manager import StorageManager
                from branches.models import Branch
                
                if is_globaladmin:
                    # Global Admin: Show all branches with storage data
                    branches = Branch.objects.all().select_related('business').prefetch_related('storage_limits')
                    storage_branches_data = []
                    
                    for branch in branches:
                        storage_info = StorageManager.get_branch_storage_info(branch)
                        
                        # Get file count for this branch
                        file_count = FileStorageUsage.objects.filter(
                            user__branch=branch,
                            is_deleted=False
                        ).count()
                        
                        status = (
                            'exceeded' if storage_info['is_limit_exceeded'] else
                            'warning' if storage_info['is_warning_threshold_exceeded'] else
                            'normal'
                        )
                        
                        storage_branches_data.append({
                            'branch': branch,
                            'storage_limits': storage_info['storage_limit'],
                            'current_usage_bytes': storage_info['current_usage_bytes'],
                            'current_usage_display': storage_info['current_usage_display'],
                            'limit_display': storage_info['limit_display'],
                            'usage_percentage': round(storage_info['usage_percentage'], 1),
                            'remaining_bytes': storage_info['remaining_bytes'],
                            'remaining_display': storage_info['remaining_display'],
                            'is_unlimited': storage_info['is_unlimited'],
                            'file_count': file_count,
                            'status': status,
                        })
                    
                    # Count branches by status for dashboard stats
                    status_counts = {'normal': 0, 'warning': 0, 'exceeded': 0}
                    for branch_data in storage_branches_data:
                        status_counts[branch_data['status']] += 1
                    
                    storage_data = {
                        'branches': storage_branches_data,
                        'is_global_admin': True,
                        'status_counts': status_counts
                    }
                
                elif is_branch_admin and request.user.branch:
                    # Branch Admin: Show only their branch data
                    branch = request.user.branch
                    storage_info = StorageManager.get_branch_storage_info(branch)
                    
                    # Get file count and recent uploads for this branch
                    file_count = FileStorageUsage.objects.filter(
                        user__branch=branch,
                        is_deleted=False
                    ).count()
                    
                    recent_uploads = FileStorageUsage.objects.filter(
                        user__branch=branch,
                        is_deleted=False
                    ).select_related('user').order_by('-created_at')[:10]
                    
                    # Get top uploaders
                    top_uploaders = FileStorageUsage.objects.filter(
                        user__branch=branch,
                        is_deleted=False
                    ).values(
                        'user__username', 'user__first_name', 'user__last_name'
                    ).annotate(
                        total_bytes=Sum('file_size_bytes'),
                        file_count=Count('id')
                    ).order_by('-total_bytes')[:5]
                    
                    storage_data = {
                        'branch': branch,
                        'storage_limits': storage_info['storage_limit'],
                        'current_usage_bytes': storage_info['current_usage_bytes'],
                        'current_usage_display': storage_info['current_usage_display'],
                        'limit_display': storage_info['limit_display'],
                        'usage_percentage': round(storage_info['usage_percentage'], 1),
                        'remaining_bytes': storage_info['remaining_bytes'],
                        'remaining_display': storage_info['remaining_display'],
                        'is_unlimited': storage_info['is_unlimited'],
                        'file_count': file_count,
                        'recent_uploads': recent_uploads,
                        'top_uploaders': top_uploaders,
                        'is_global_admin': False
                    }
                    
            except Exception as e:
                logger.error(f"Error loading storage data: {str(e)}")
                storage_data = None

        # Final context dictionary for the template
        context = {
            'title': 'Account & Settings',
            'breadcrumbs': breadcrumbs,
            'is_globaladmin': is_globaladmin,
            'is_superadmin': is_superadmin,
            'is_branch_admin': is_branch_admin,
            'user_2fa_enabled': user_2fa_enabled,
            'oauth_2fa_enabled': oauth_2fa_enabled,
            'totp_2fa_enabled': totp_2fa_enabled,
            'active_tab': active_section,
            'active_section': active_section,
            'active_integration': active_integration,
            'portal_settings': portal_settings,
            'timezone_choices': timezone_choices,

            'notification_settings': notification_settings,
            'api_settings': api_settings,
            'teams_integrations': teams_integrations,
            'zoom_integrations': zoom_integrations,
            'sharepoint_integrations': sharepoint_integrations,
            'teams_integration': teams_integration,
            'zoom_integration': zoom_integration,
            'stripe_integration': stripe_integration,
            'paypal_integration': paypal_integration,
            'sharepoint_integration': sharepoint_integration,
            'sharepoint_sync_status': sharepoint_sync_status,
            'branches': branches_with_limits,
            'businesses_with_branches': businesses_with_branches,
            'all_admin_integrations': all_admin_integrations,
            'all_branch_users_integrations': all_branch_users_integrations,
            'branch_admin_integrations': branch_admin_integrations if not is_superadmin and request.user.branch else None,
            'available_zoom_meeting_templates': available_zoom_meeting_templates,
            # Global Admin specific context
            'global_admin_settings': global_admin_settings,
            'menu_control_settings': menu_control_settings,
            'google_oauth_redirect_uri': google_oauth_redirect_uri,
            'microsoft_oauth_redirect_uri': microsoft_oauth_redirect_uri,
            # Business Settings context  
            'businesses': [],
            'businesses_with_limits': businesses_with_limits,
            # AI Token Management context
            'ai_token_data': ai_token_data,
            # Storage Management context
            'storage_data': storage_data,
        }
        
        return render(request, 'account_settings/settings.html', context)
    except NoReverseMatch as e:
        logger.error(f"URL reverse error in account settings page: {str(e)}")
        return render(request, 'core/error.html', {
            'error_message': f'An error occurred with URL generation: {str(e)}. Please ensure all integration IDs are valid.'
        }, status=400)
    except Exception as e:
        logger.exception("Error in account_settings view")
        messages.error(request, f"An error occurred: {str(e)}")
        return redirect('users:role_based_redirect')


@login_required
def toggle_2fa(request):
    """Toggle two-factor authentication for the user"""
    if request.method != 'POST':
        messages.error(request, "Invalid request method.")
        return redirect('account_settings:settings')
    
    try:
        from users.models import TwoFactorAuth
        
        # Get or create 2FA settings for the user
        user_2fa, created = TwoFactorAuth.objects.get_or_create(user=request.user)
        
        # Toggle the setting
        user_2fa.is_enabled = not user_2fa.is_enabled
        user_2fa.save()
        
        # Show success message
        if user_2fa.is_enabled:
            messages.success(request, "Two-factor authentication for regular login has been enabled successfully. You will receive a verification code via email during username/password login.")
        else:
            messages.success(request, "Two-factor authentication for regular login has been disabled.")
            
    except Exception as e:
        logger.exception("Error toggling regular 2FA")
        messages.error(request, f"An error occurred while updating your Session settings: {str(e)}")
    
    # Redirect back to Session section
    return redirect(f"{reverse('account_settings:settings')}?tab=Session")


@login_required
def toggle_oauth_2fa(request):
    """Toggle OAuth two-factor authentication for the user"""
    if request.method != 'POST':
        messages.error(request, "Invalid request method.")
        return redirect('account_settings:settings')
    
    try:
        from users.models import TwoFactorAuth
        
        # Get or create 2FA settings for the user
        user_2fa, created = TwoFactorAuth.objects.get_or_create(user=request.user)
        
        # Toggle the OAuth setting
        user_2fa.oauth_enabled = not user_2fa.oauth_enabled
        user_2fa.save()
        
        # Show success message
        if user_2fa.oauth_enabled:
            messages.success(request, "Two-factor authentication for OAuth login has been enabled successfully. You will receive a verification code via email during Google/Microsoft login.")
        else:
            messages.success(request, "Two-factor authentication for OAuth login has been disabled.")
            
    except Exception as e:
        logger.exception("Error toggling OAuth 2FA")
        messages.error(request, f"An error occurred while updating your OAuth Session settings: {str(e)}")
    
    # Redirect back to Session section
    return redirect(f"{reverse('account_settings:settings')}?tab=Session")


@login_required
def setup_totp(request):
    """Setup TOTP authenticator app"""
    from users.models import TwoFactorAuth
    import qrcode
    import io
    import base64
    
    # Get or create 2FA settings
    user_2fa, created = TwoFactorAuth.objects.get_or_create(user=request.user)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'generate':
            # Generate new secret and QR code
            user_2fa.generate_totp_secret()
            user_2fa.save()
            
        elif action == 'verify':
            # Verify TOTP token and enable
            token = request.POST.get('totp_token', '').strip()
            if len(token) == 6 and token.isdigit():
                if user_2fa.verify_totp(token):
                    user_2fa.totp_enabled = True
                    backup_tokens = user_2fa.generate_backup_tokens()
                    user_2fa.save()
                    
                    messages.success(request, "Authenticator app has been successfully setup! Save your backup codes safely.")
                    
                    # Store backup tokens in session for display
                    request.session['backup_tokens'] = backup_tokens
                    return redirect('account_settings:totp_backup_codes')
                else:
                    messages.error(request, "Invalid verification code. Please try again.")
            else:
                messages.error(request, "Please enter a valid 6-digit code from your authenticator app.")
        
        elif action == 'disable':
            # Disable TOTP
            user_2fa.totp_enabled = False
            user_2fa.totp_secret = None
            user_2fa.backup_tokens = []
            user_2fa.save()
            messages.success(request, "Authenticator app has been disabled.")
            return redirect(f"{reverse('account_settings:settings')}?tab=Session")
    
    # Generate QR code if secret exists
    qr_code_data = None
    if user_2fa.totp_secret:
        try:
            totp_uri = user_2fa.get_totp_uri()
            
            # Generate QR code
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(totp_uri)
            qr.make(fit=True)
            
            # Create QR code image
            img = qr.make_image(fill_color="black", back_color="white")
            
            # Convert to base64 for embedding in HTML
            buffer = io.BytesIO()
            img.save(buffer, format='PNG')
            buffer.seek(0)
            qr_code_data = base64.b64encode(buffer.getvalue()).decode()
            
        except Exception as e:
            logger.error(f"Error generating QR code: {str(e)}")
            messages.error(request, "Error generating QR code. Please try again.")
    
    # Build breadcrumbs
    breadcrumbs = [
        {'label': 'Dashboard', 'url': reverse('users:role_based_redirect'), 'icon': 'fa-home'},
        {'label': 'Account Settings', 'url': reverse('account_settings:settings'), 'icon': 'fa-cog'},
        {'label': 'Session', 'url': reverse('account_settings:settings') + '?tab=Session', 'icon': 'fa-shield-alt'},
        {'label': 'Setup Authenticator App', 'icon': 'fa-mobile-alt'}
    ]
    
    context = {
        'title': 'Setup Authenticator App',
        'breadcrumbs': breadcrumbs,
        'user_2fa': user_2fa,
        'qr_code_data': qr_code_data,
        'totp_secret': user_2fa.totp_secret,
    }
    
    return render(request, 'account_settings/setup_totp.html', context)


@login_required
def totp_backup_codes(request):
    """Display backup codes"""
    backup_tokens = request.session.get('backup_tokens')
    if not backup_tokens:
        messages.error(request, "No backup codes found. Please setup authenticator app first.")
        return redirect(f"{reverse('account_settings:settings')}?tab=Session")
    
    # Clear from session after displaying
    if 'backup_tokens' in request.session:
        del request.session['backup_tokens']
    
    # Build breadcrumbs
    breadcrumbs = [
        {'label': 'Dashboard', 'url': reverse('users:role_based_redirect'), 'icon': 'fa-home'},
        {'label': 'Account Settings', 'url': reverse('account_settings:settings'), 'icon': 'fa-cog'},
        {'label': 'Session', 'url': reverse('account_settings:settings') + '?tab=Session', 'icon': 'fa-shield-alt'},
        {'label': 'Backup Codes', 'icon': 'fa-key'}
    ]
    
    context = {
        'title': 'Backup Codes',
        'breadcrumbs': breadcrumbs,
        'backup_tokens': backup_tokens,
    }
    
    return render(request, 'account_settings/totp_backup_codes.html', context)


@login_required
def toggle_totp_2fa(request):
    """Toggle TOTP two-factor authentication"""
    if request.method != 'POST':
        messages.error(request, "Invalid request method.")
        return redirect('account_settings:settings')
    
    try:
        from users.models import TwoFactorAuth
        
        # Get 2FA settings
        user_2fa, created = TwoFactorAuth.objects.get_or_create(user=request.user)
        
        if user_2fa.totp_enabled:
            # Disable TOTP
            user_2fa.totp_enabled = False
            user_2fa.totp_secret = None
            user_2fa.backup_tokens = []
            user_2fa.save()
            messages.success(request, "Authenticator app two-factor authentication has been disabled.")
        else:
            # Redirect to setup page
            return redirect('account_settings:setup_totp')
            
    except Exception as e:
        logger.exception("Error toggling TOTP 2FA")
        messages.error(request, f"An error occurred while updating your authenticator app settings: {str(e)}")
    
    # Redirect back to Session section
    return redirect(f"{reverse('account_settings:settings')}?tab=Session")


@login_required
def delete_integration(request, integration_type, integration_id):
    """Delete an integration."""
    if request.method != 'POST':
        messages.error(request, "Invalid request method.")
        return redirect('account_settings:settings')
    
    try:
        # Get the right model based on integration type
        if integration_type == 'teams':
            integration = TeamsIntegration.objects.get(id=integration_id)
        elif integration_type == 'zoom':
            integration = ZoomIntegration.objects.get(id=integration_id)
        elif integration_type == 'stripe':
            integration = StripeIntegration.objects.get(id=integration_id)
        elif integration_type == 'paypal':
            integration = PayPalIntegration.objects.get(id=integration_id)
        elif integration_type == 'sharepoint':
            integration = SharePointIntegration.objects.get(id=integration_id)
        else:
            messages.error(request, f"Unknown integration type: {integration_type}")
            return redirect('account_settings:settings')
        
        # Check permissions - only the owner or a superadmin can delete
        if integration.user != request.user and request.user.role != 'superadmin':
            messages.error(request, "You don't have permission to delete this integration.")
            return redirect('account_settings:settings')
        
        # Delete the integration
        integration_name = integration.name
        integration.delete()
        messages.success(request, f"{integration_name} integration was deleted successfully.")
        
        # Return to the appropriate tab
        if integration_type in ['stripe', 'paypal']:
            return redirect(reverse('account_settings:settings') + f'?tab=payments&integration={integration_type}')
        else:
            return redirect(reverse('account_settings:settings') + f'?tab=integrations&integration={integration_type}')
        
    except (TeamsIntegration.DoesNotExist, ZoomIntegration.DoesNotExist, 
           StripeIntegration.DoesNotExist, PayPalIntegration.DoesNotExist):
        messages.error(request, "Integration not found.")
        return redirect('account_settings:settings')
    except Exception as e:
        logger.error(f"Error deleting integration: {str(e)}")
        messages.error(request, f"An error occurred: {str(e)}")
        return redirect('account_settings:settings')

@login_required
def toggle_integration(request, integration_type, integration_id):
    """Toggle the active status of an integration."""
    if request.method != 'POST':
        messages.error(request, "Invalid request method.")
        return redirect('account_settings:settings')
    
    try:
        # Get the right model based on integration type
        if integration_type == 'teams':
            integration = TeamsIntegration.objects.get(id=integration_id)
        elif integration_type == 'zoom':
            integration = ZoomIntegration.objects.get(id=integration_id)
        elif integration_type == 'stripe':
            integration = StripeIntegration.objects.get(id=integration_id)
        elif integration_type == 'paypal':
            integration = PayPalIntegration.objects.get(id=integration_id)
        elif integration_type == 'sharepoint':
            integration = SharePointIntegration.objects.get(id=integration_id)
        else:
            messages.error(request, f"Unknown integration type: {integration_type}")
            return redirect('account_settings:settings')
        
        # Check permissions - only the owner or a superadmin can toggle
        if integration.user != request.user and request.user.role != 'superadmin':
            messages.error(request, "You don't have permission to modify this integration.")
            return redirect('account_settings:settings')
        
        # Toggle the active status
        integration.is_active = not integration.is_active
        integration.save()
        
        status = "enabled" if integration.is_active else "disabled"
        messages.success(request, f"{integration.name} integration was {status} successfully.")
        
        # Return to the appropriate tab
        if integration_type in ['stripe', 'paypal']:
            return redirect(reverse('account_settings:settings') + f'?tab=payments&integration={integration_type}')
        else:
            return redirect(reverse('account_settings:settings') + f'?tab=integrations&integration={integration_type}')
        
    except (TeamsIntegration.DoesNotExist, ZoomIntegration.DoesNotExist, 
           StripeIntegration.DoesNotExist, PayPalIntegration.DoesNotExist,
           SharePointIntegration.DoesNotExist):
        messages.error(request, "Integration not found.")
        return redirect('account_settings:settings')
    except Exception as e:
        logger.error(f"Error toggling integration: {str(e)}")
        messages.error(request, f"An error occurred: {str(e)}")
        return redirect('account_settings:settings')

@login_required
def manage_branch_integrations(request):
    """View for super admins to manage Zoom integrations for different branches"""
    if request.user.role != 'superadmin':
        messages.error(request, 'Access denied. Only super admins can manage branch integrations.')
        return redirect('account_settings:settings')
    
    # Get breadcrumbs
    breadcrumbs = [
                    {'url': reverse('dashboard_superadmin'), 'label': 'Dashboard', 'icon': 'fa-tachometer-alt'},
        {'url': reverse('account_settings:settings'), 'label': 'Account Settings', 'icon': 'fa-cog'},
        {'label': 'Branch Integrations', 'icon': 'fa-building'}
    ]
    
    # Get branches with their integrations (business-scoped for Super Admin)
    from core.utils.business_filtering import filter_branches_by_business
    branches = filter_branches_by_business(request.user).order_by('name')
    branch_data = []
    
    for branch in branches:
        # Get branch admin users
        branch_admins = get_user_model().objects.filter(role='admin', branch=branch)
        
        # Get existing Zoom integrations for this branch
        zoom_integrations = ZoomIntegration.objects.filter(
            user__branch=branch,
            user__role__in=['admin', 'instructor']
        ).select_related('user')
        
        branch_data.append({
            'branch': branch,
            'admins': branch_admins,
            'zoom_integrations': zoom_integrations,
            'admin_count': branch_admins.count(),
            'integration_count': zoom_integrations.count()
        })
    
    # Handle POST requests for creating/editing integrations
    if request.method == 'POST':
        action = request.POST.get('action')
        branch_id = request.POST.get('branch_id')
        
        try:
            branch = Branch.objects.get(id=branch_id)
        except Branch.DoesNotExist:
            messages.error(request, 'Invalid branch selected.')
            return redirect('account_settings:manage_branch_integrations')
        
        if action == 'create_zoom_integration':
            # Get a suitable admin user for this branch
            admin_user = get_user_model().objects.filter(role='admin', branch=branch).first()
            
            if not admin_user:
                messages.error(request, f'No admin user found for branch {branch.name}. Please create an admin user first.')
                return redirect('account_settings:manage_branch_integrations')
            
            name = request.POST.get('name', f'Zoom Integration - {branch.name}')
            api_key = request.POST.get('client_id')
            api_secret = request.POST.get('client_secret')
            account_id = request.POST.get('account_id')
            is_active = request.POST.get('is_active') == 'on'
            
            if api_key and api_secret and account_id:
                # Create the integration for the branch admin
                integration = ZoomIntegration.objects.create(
                    user=admin_user,
                    name=name,
                    api_key=api_key,
                    api_secret=api_secret,
                    account_id=account_id,
                    branch=branch,
                    is_active=is_active
                )
                
                logger.info(f"Super admin {request.user.id} created Zoom integration {integration.id} for branch {branch.name}")
                messages.success(request, f'Zoom integration created successfully for {branch.name}')
            else:
                messages.error(request, 'Please fill in all required fields (Client ID, Client Secret, Account ID)')
        
        elif action == 'update_zoom_integration':
            integration_id = request.POST.get('integration_id')
            
            try:
                integration = ZoomIntegration.objects.get(id=integration_id, user__branch=branch)
                
                integration.name = request.POST.get('name', integration.name)
                integration.api_key = request.POST.get('client_id')
                integration.api_secret = request.POST.get('client_secret')
                integration.account_id = request.POST.get('account_id')
                integration.is_active = request.POST.get('is_active') == 'on'
                integration.save()
                
                logger.info(f"Super admin {request.user.id} updated Zoom integration {integration.id} for branch {branch.name}")
                messages.success(request, f'Zoom integration updated successfully for {branch.name}')
                
            except ZoomIntegration.DoesNotExist:
                messages.error(request, 'Integration not found.')
        
        elif action == 'delete_zoom_integration':
            integration_id = request.POST.get('integration_id')
            
            try:
                integration = ZoomIntegration.objects.get(id=integration_id, user__branch=branch)
                integration_name = integration.name
                integration.delete()
                
                logger.info(f"Super admin {request.user.id} deleted Zoom integration {integration_id} for branch {branch.name}")
                messages.success(request, f'Zoom integration "{integration_name}" deleted successfully from {branch.name}')
                
            except ZoomIntegration.DoesNotExist:
                messages.error(request, 'Integration not found.')
        
        return redirect('account_settings:manage_branch_integrations')
    
    context = {
        'title': 'Branch Integration Management',
        'breadcrumbs': breadcrumbs,
        'branch_data': branch_data,
        'is_superadmin': True,
    }
    
    return render(request, 'account_settings/manage_branch_integrations.html', context)

@login_required
def update_branch_limits(request, branch_id):
    """Update user limits for a specific branch"""
    logger.info(f"Branch limits update requested for branch {branch_id} by user {request.user.email}")
    
    # Only superadmin and globaladmin can update branch limits
    if request.user.role not in ['superadmin', 'globaladmin']:
        logger.warning(f"Permission denied for user {request.user.email} with role {request.user.role}")
        return HttpResponseForbidden("You don't have permission to update branch limits")
    
    # For Super Admin, ensure they can only update branches within their assigned businesses
    if request.user.role == 'superadmin':
        from core.utils.business_filtering import get_superadmin_business_filter
        assigned_businesses = get_superadmin_business_filter(request.user)
        branch = get_object_or_404(Branch, id=branch_id)
        if not branch.business or branch.business.id not in assigned_businesses:
            logger.warning(f"Super Admin {request.user.email} attempted to update branch {branch_id} outside their business scope")
            return HttpResponseForbidden("You can only update branches within your assigned businesses")
    else:
        branch = get_object_or_404(Branch, id=branch_id)
    
    if request.method != 'POST':
        logger.warning(f"Invalid request method: {request.method}")
        return JsonResponse({'success': False, 'message': 'Invalid request method'})
    
    logger.info(f"POST data: {dict(request.POST)}")
    logger.info(f"Found branch: {branch.name}")
    
    # Get or create user limits for this branch
    user_limits, created = BranchUserLimits.objects.get_or_create(branch=branch)
    logger.info(f"User limits {'created' if created else 'found'} for branch {branch.name}")
    
    # Update the total limit from the form
    total_limit = request.POST.get('total_limit')
    logger.info(f"Received total_limit: {total_limit}")
    
    if total_limit is not None:
        try:
            total_limit_int = int(total_limit)
            logger.info(f"Parsed total_limit as integer: {total_limit_int}")
            
            # Validate that the new limit is not less than current usage
            current_users = branch.get_branch_users().count()
            logger.info(f"Current users in branch: {current_users}")
            
            if total_limit_int < current_users:
                logger.warning(f"Total limit ({total_limit_int}) is less than current users ({current_users})")
                return JsonResponse({
                    'success': False, 
                    'message': f'Total limit ({total_limit_int}) cannot be less than current users ({current_users})'
                })
            user_limits.user_limit = total_limit_int
            logger.info(f"Set user_limits.user_limit to {total_limit_int}")
        except ValueError as e:
            logger.error(f"ValueError parsing total_limit: {e}")
            return JsonResponse({'success': False, 'message': 'Invalid total limit value'})
    else:
        logger.warning("total_limit is None")
        return JsonResponse({'success': False, 'message': 'Total limit value is required'})
    
    # Set the updated_by field
    user_limits.updated_by = request.user
    logger.info(f"Set updated_by to {request.user.email}")
    
    try:
        user_limits.save()
        logger.info("Successfully saved user_limits")
    except Exception as e:
        logger.error(f"Error saving user_limits: {e}")
        return JsonResponse({'success': False, 'message': f'Error saving branch limits: {str(e)}'})
    
    # Get updated usage data
    usage_data = user_limits.get_role_usage_data()
    logger.info(f"Retrieved usage data: {usage_data}")
    
    return JsonResponse({
        'success': True, 
        'message': f'User limits for {branch.name} updated successfully',
        'usage_data': usage_data
    })


@login_required
def update_business_limits(request, business_id):
    """Update user and branch limits for a specific business"""
    logger.info(f"Business limits update requested for business {business_id} by user {request.user.email}")
    
    # Only globaladmin can update business limits
    if request.user.role != 'globaladmin':
        logger.warning(f"Permission denied for user {request.user.email} with role {request.user.role}")
        return HttpResponseForbidden("You don't have permission to update business limits")
    
    if request.method != 'POST':
        logger.warning(f"Invalid request method: {request.method}")
        return JsonResponse({'success': False, 'message': 'Invalid request method'})
    
    logger.info(f"POST data: {dict(request.POST)}")
    
    business = get_object_or_404(Business, id=business_id)
    logger.info(f"Found business: {business.name}")
    
    # Get or create business limits for this business
    business_limits, created = BusinessLimits.objects.get_or_create(
        business=business,
        defaults={'updated_by': request.user}
    )
    logger.info(f"Business limits {'created' if created else 'found'} for business {business.name}")
    
    # Update the limits from the form
    total_user_limit = request.POST.get('total_user_limit')
    branch_creation_limit = request.POST.get('branch_creation_limit')
    
    logger.info(f"Received total_user_limit: {total_user_limit}")
    logger.info(f"Received branch_creation_limit: {branch_creation_limit}")
    
    if total_user_limit is not None:
        try:
            total_user_limit_int = int(total_user_limit)
            logger.info(f"Parsed total_user_limit as integer: {total_user_limit_int}")
            
            # Validate that the new limit is not less than current usage
            current_users = business.get_total_users_count()
            logger.info(f"Current users in business: {current_users}")
            
            if total_user_limit_int < current_users:
                logger.warning(f"Total user limit ({total_user_limit_int}) is less than current users ({current_users})")
                return JsonResponse({
                    'success': False, 
                    'message': f'Total user limit ({total_user_limit_int}) cannot be less than current users ({current_users})'
                })
            business_limits.total_user_limit = total_user_limit_int
            logger.info(f"Set business_limits.total_user_limit to {total_user_limit_int}")
        except ValueError as e:
            logger.error(f"ValueError parsing total_user_limit: {e}")
            return JsonResponse({'success': False, 'message': 'Invalid total user limit value'})
    
    if branch_creation_limit is not None:
        try:
            branch_creation_limit_int = int(branch_creation_limit)
            logger.info(f"Parsed branch_creation_limit as integer: {branch_creation_limit_int}")
            
            # Validate that the new limit is not less than current branches
            current_branches = business.get_business_branch_count()
            logger.info(f"Current branches in business: {current_branches}")
            
            if branch_creation_limit_int < current_branches:
                logger.warning(f"Branch creation limit ({branch_creation_limit_int}) is less than current branches ({current_branches})")
                return JsonResponse({
                    'success': False, 
                    'message': f'Branch creation limit ({branch_creation_limit_int}) cannot be less than current branches ({current_branches})'
                })
            business_limits.branch_creation_limit = branch_creation_limit_int
            logger.info(f"Set business_limits.branch_creation_limit to {branch_creation_limit_int}")
        except ValueError as e:
            logger.error(f"ValueError parsing branch_creation_limit: {e}")
            return JsonResponse({'success': False, 'message': 'Invalid branch creation limit value'})
    
    # Ensure at least one limit was provided
    if total_user_limit is None and branch_creation_limit is None:
        logger.warning("No limits provided in request")
        return JsonResponse({'success': False, 'message': 'At least one limit value is required'})
    
    business_limits.updated_by = request.user
    logger.info(f"Set updated_by to {request.user.email}")
    
    try:
        business_limits.save()
        logger.info("Successfully saved business_limits")
    except Exception as e:
        logger.error(f"Error saving business_limits: {e}")
        return JsonResponse({'success': False, 'message': f'Error saving business limits: {str(e)}'})
    
    # Get updated usage data
    usage_data = business_limits.get_usage_data()
    logger.info(f"Retrieved usage data: {usage_data}")
    
    return JsonResponse({
        'success': True, 
        'message': f'Business limits for {business.name} updated successfully',
        'usage_data': usage_data
    })

@login_required
def edit_integration(request, integration_type, integration_id):
    """Edit an integration."""
    # Check if user is authorized
    if not (request.user.role == 'admin' or request.user.role in ['globaladmin', 'superadmin']):
        return HttpResponseForbidden("You don't have permission to edit integrations.")
    
    # Get the integration based on type
    integration = None
    if integration_type == 'teams':
        integration = get_object_or_404(TeamsIntegration, id=integration_id)
    elif integration_type == 'zoom':
        integration = get_object_or_404(ZoomIntegration, id=integration_id)
    elif integration_type == 'stripe':
        integration = get_object_or_404(StripeIntegration, id=integration_id)
    elif integration_type == 'paypal':
        integration = get_object_or_404(PayPalIntegration, id=integration_id)
    else:
        messages.error(request, f"Unknown integration type: {integration_type}")
        return redirect('account_settings:settings')
    
    # Check if user owns this integration or is superadmin
    if not (request.user.role in ['globaladmin', 'superadmin'] or integration.user == request.user):
        return HttpResponseForbidden("You don't have permission to edit this integration.")
    
    # Handle form submission
    if request.method == 'POST':
        # Common fields
        name = request.POST.get('name')
        is_active = request.POST.get('is_active') == 'on'
        
        # Update integration
        integration.name = name
        integration.is_active = is_active
        
        # Type-specific fields
        if integration_type == 'teams':
            client_id = request.POST.get('client_id')
            client_secret = request.POST.get('client_secret')
            tenant_id = request.POST.get('tenant_id')
            service_account_email = request.POST.get('service_account_email', '').strip()
            
            if client_id:
                integration.client_id = client_id
            if client_secret:  # Only update if new secret provided
                integration.client_secret = client_secret
            if tenant_id:
                integration.tenant_id = tenant_id
            # Always update service account email (can be set to None/empty)
            integration.service_account_email = service_account_email if service_account_email else None
                
        elif integration_type == 'zoom':
            api_key = request.POST.get('api_key')
            api_secret = request.POST.get('api_secret')
            account_id = request.POST.get('account_id')
            
            if api_key:
                integration.api_key = api_key
            if api_secret:
                integration.api_secret = api_secret
            if account_id:
                integration.account_id = account_id
                
        # Save changes
        integration.save()
        
        messages.success(request, f"{integration_type.title()} integration updated successfully.")
        return redirect(f"{reverse('account_settings:settings')}?tab=integrations&integration={integration_type}")
    
    # If not POST, redirect to settings page
    return redirect('account_settings:settings')

@login_required
def start_export(request):
    """Start a data export job"""
    # RBAC v0.1 Compliant Access Control - Only Global Admin has FULL export access
    if request.user.role != 'globaladmin':
        return JsonResponse({'success': False, 'error': 'Permission denied - Global Admin access required'})
    
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request method'})
    
    export_type = request.POST.get('export_type')
    include_files = request.POST.get('include_files') == 'true'
    
    if not export_type:
        return JsonResponse({'success': False, 'error': 'Export type is required'})
    
    # Create export job
    job = ExportJob.objects.create(
        user=request.user,
        export_type=export_type,
        include_files=include_files,
        status='pending'
    )
    
    # Start export in background
    def run_export():
        import tempfile
        import shutil
        temp_dir_used = False
        try:
            # Determine output directory - use temp if S3, otherwise use MEDIA_ROOT
            if settings.MEDIA_ROOT:
                output_dir = os.path.join(settings.MEDIA_ROOT, 'exports')
                os.makedirs(output_dir, exist_ok=True)
            else:
                # Using S3 - create temp directory for export
                output_dir = tempfile.mkdtemp(prefix='export_')
                temp_dir_used = True
                logger.info(f"Using temp directory for export: {output_dir}")
            
            # Use sys.executable to get the current Python interpreter path
            cmd = [
                sys.executable, 'manage.py', 'export_data',
                '--type', export_type,
                '--output', output_dir,
                '--job-id', str(job.id)
            ]
            
            if include_files:
                cmd.append('--include-files')
            
            # Capture output for better error reporting
            result = subprocess.run(
                cmd, 
                cwd=settings.BASE_DIR, 
                check=True, 
                capture_output=True, 
                text=True
            )
            
            # If using temp directory, upload exported files to S3
            if temp_dir_used:
                exported_files = glob.glob(os.path.join(output_dir, '*'))
                uploaded_count = 0
                for file_path in exported_files:
                    if os.path.isfile(file_path):
                        # Upload to S3
                        s3_key = f'exports/{os.path.basename(file_path)}'
                        try:
                            with open(file_path, 'rb') as f:
                                default_storage.save(s3_key, ContentFile(f.read()))
                            uploaded_count += 1
                            logger.info(f"Uploaded export file to S3: {s3_key}")
                        except Exception as e:
                            logger.error(f"Failed to upload {file_path} to S3: {str(e)}")
                
                # Clean up temp directory
                try:
                    shutil.rmtree(output_dir, ignore_errors=True)
                    logger.info(f"Cleaned up temp export directory")
                except Exception as e:
                    logger.warning(f"Failed to clean up temp directory: {str(e)}")
                
                if uploaded_count > 0:
                    job.status = 'completed'
                    job.error_message = f'Export completed. {uploaded_count} file(s) uploaded to S3.'
                    job.save()
            
        except subprocess.CalledProcessError as e:
            job.status = 'failed'
            error_msg = f'Export command failed with exit code {e.returncode}'
            if e.stdout:
                error_msg += f'\nStdout: {e.stdout}'
            if e.stderr:
                error_msg += f'\nStderr: {e.stderr}'
            job.error_message = error_msg
            job.save()
            # Clean up temp directory on error
            if temp_dir_used:
                try:
                    shutil.rmtree(output_dir, ignore_errors=True)
                except:
                    pass
        except Exception as e:
            job.status = 'failed'
            job.error_message = f'Unexpected error: {str(e)}'
            job.save()
            # Clean up temp directory on error
            if temp_dir_used:
                try:
                    shutil.rmtree(output_dir, ignore_errors=True)
                except:
                    pass
    
    # Run export in background thread
    thread = threading.Thread(target=run_export)
    thread.daemon = True
    thread.start()
    
    return JsonResponse({
        'success': True,
        'job_id': job.id,
        'message': f'Export started for {export_type}'
    })

@login_required
def start_import(request):
    """Start a data import job"""
    # RBAC v0.1 Compliant Access Control - Only Global Admin has FULL import access
    if request.user.role != 'globaladmin':
        return JsonResponse({'success': False, 'error': 'Permission denied - Global Admin access required'})
    
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request method'})
    
    import_type = request.POST.get('import_type')
    replace_existing = request.POST.get('replace_existing') == 'true'
    
    if not import_type:
        return JsonResponse({'success': False, 'error': 'Import type is required'})
    
    # Handle file upload
    if 'import_file' not in request.FILES:
        return JsonResponse({'success': False, 'error': 'Import file is required'})
    
    import_file = request.FILES['import_file']
    
    # Validate file type
    if not import_file.name.endswith('.zip'):
        return JsonResponse({'success': False, 'error': 'Import file must be a ZIP archive'})
    
    # Save uploaded file - use temp file if S3, otherwise use MEDIA_ROOT
    import tempfile
    if settings.MEDIA_ROOT:
        import_dir = os.path.join(settings.MEDIA_ROOT, 'imports')
        os.makedirs(import_dir, exist_ok=True)
        file_path = os.path.join(import_dir, f'{timezone.now().strftime("%Y%m%d_%H%M%S")}_{import_file.name}')
        with open(file_path, 'wb+') as destination:
            for chunk in import_file.chunks():
                destination.write(chunk)
    else:
        # Using S3 - save to temp file first
        fd, file_path = tempfile.mkstemp(prefix='import_', suffix='.zip')
        try:
            with os.fdopen(fd, 'wb') as destination:
                for chunk in import_file.chunks():
                    destination.write(chunk)
            logger.info(f"Saved import file to temp location: {file_path}")
        except Exception as e:
            os.close(fd)
            os.unlink(file_path)
            raise e
    
    # Create import job
    job = ImportJob.objects.create(
        user=request.user,
        import_type=import_type,
        file_path=file_path,
        replace_existing=replace_existing,
        status='pending'
    )
    
    # Start import in background
    def run_import():
        temp_file_used = not settings.MEDIA_ROOT
        try:
            cmd = [
                sys.executable, 'manage.py', 'import_data',
                '--type', import_type,
                '--file', file_path,
                '--job-id', str(job.id)
            ]
            
            if replace_existing:
                cmd.append('--replace')
            
            # Capture output for better error reporting
            result = subprocess.run(
                cmd, 
                cwd=settings.BASE_DIR, 
                check=True, 
                capture_output=True, 
                text=True
            )
            
        except subprocess.CalledProcessError as e:
            job.status = 'failed'
            error_msg = f'Import command failed with exit code {e.returncode}'
            if e.stdout:
                error_msg += f'\nStdout: {e.stdout}'
            if e.stderr:
                error_msg += f'\nStderr: {e.stderr}'
            job.error_message = error_msg
            job.save()
        except Exception as e:
            job.status = 'failed'
            job.error_message = f'Unexpected error: {str(e)}'
            job.save()
        finally:
            # Clean up temp file if using S3
            if temp_file_used and os.path.exists(file_path):
                try:
                    os.unlink(file_path)
                    logger.info(f"Cleaned up temp import file: {file_path}")
                except Exception as e:
                    logger.warning(f"Failed to clean up temp import file: {str(e)}")
    
    # Run import in background thread
    thread = threading.Thread(target=run_import)
    thread.daemon = True
    thread.start()
    
    return JsonResponse({
        'success': True,
        'job_id': job.id,
        'message': f'Import started for {import_type}'
    })

@login_required
def export_status(request, job_id):
    """Get export job status"""
    # RBAC v0.1 Compliant Access Control - Only Global Admin has FULL export access
    if request.user.role != 'globaladmin':
        return JsonResponse({'success': False, 'error': 'Permission denied - Global Admin access required'})
    
    try:
        job = ExportJob.objects.get(id=job_id, user=request.user)
        
        response_data = {
            'success': True,
            'status': job.status,
            'export_type': job.export_type,
            'created_at': job.created_at.isoformat(),
            'record_count': job.record_count,
        }
        
        if job.status == 'completed':
            response_data.update({
                'completed_at': job.completed_at.isoformat() if job.completed_at else None,
                'file_size': job.file_size,
                'download_url': reverse('account_settings:download_export', args=[job.id])
            })
        elif job.status == 'failed':
            response_data['error_message'] = job.error_message
        
        return JsonResponse(response_data)
        
    except ExportJob.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Export job not found'})

@login_required
def import_status(request, job_id):
    """Get import job status"""
    # RBAC v0.1 Compliant Access Control - Only Global Admin has FULL import access
    if request.user.role != 'globaladmin':
        return JsonResponse({'success': False, 'error': 'Permission denied - Global Admin access required'})
    
    try:
        job = ImportJob.objects.get(id=job_id, user=request.user)
        
        response_data = {
            'success': True,
            'status': job.status,
            'import_type': job.import_type,
            'created_at': job.created_at.isoformat(),
            'records_processed': job.records_processed,
            'records_created': job.records_created,
            'records_updated': job.records_updated,
            'records_failed': job.records_failed,
        }
        
        if job.status in ['completed', 'partial', 'failed']:
            response_data.update({
                'completed_at': job.completed_at.isoformat() if job.completed_at else None,
                'validation_errors': job.validation_errors
            })
            
            if job.status == 'failed':
                response_data['error_message'] = job.error_message
        
        return JsonResponse(response_data)
        
    except ImportJob.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Import job not found'})

@login_required
def download_export(request, job_id):
    """Download export file"""
    # RBAC v0.1 Compliant Access Control - Only Global Admin has FULL export access
    if request.user.role != 'globaladmin':
        return HttpResponseForbidden("Permission denied - Global Admin access required")
    
    try:
        job = ExportJob.objects.get(id=job_id, user=request.user)
        
        if job.status != 'completed' or not job.file_path:
            raise Http404("Export file not available")
        
        if not os.path.exists(job.file_path):
            raise Http404("Export file not found")
        
        response = FileResponse(
            open(job.file_path, 'rb'),
            as_attachment=True,
            filename=os.path.basename(job.file_path)
        )
        
        return response
        
    except ExportJob.DoesNotExist:
        raise Http404("Export job not found")

@login_required
def get_export_jobs(request):
    """Get list of export jobs for the user"""
    # RBAC v0.1 Compliant Access Control - Only Global Admin has FULL export access
    if request.user.role != 'globaladmin':
        return JsonResponse({'success': False, 'error': 'Permission denied - Global Admin access required'})
    
    jobs = ExportJob.objects.filter(user=request.user)[:20]  # Last 20 jobs
    
    jobs_data = []
    for job in jobs:
        job_data = {
            'id': job.id,
            'export_type': job.export_type,
            'status': job.status,
            'created_at': job.created_at.isoformat(),
            'record_count': job.record_count,
            'include_files': job.include_files,
        }
        
        if job.status == 'completed':
            job_data.update({
                'completed_at': job.completed_at.isoformat() if job.completed_at else None,
                'file_size': job.file_size,
                'download_url': reverse('account_settings:download_export', args=[job.id])
            })
        elif job.status == 'failed':
            job_data['error_message'] = job.error_message
        
        jobs_data.append(job_data)
    
    return JsonResponse({'success': True, 'jobs': jobs_data})

@login_required
def get_import_jobs(request):
    """Get list of import jobs for the user"""
    # RBAC v0.1 Compliant Access Control - Only Global Admin has FULL import access
    if request.user.role != 'globaladmin':
        return JsonResponse({'success': False, 'error': 'Permission denied - Global Admin access required'})
    
    jobs = ImportJob.objects.filter(user=request.user)[:20]  # Last 20 jobs
    
    jobs_data = []
    for job in jobs:
        job_data = {
            'id': job.id,
            'import_type': job.import_type,
            'status': job.status,
            'created_at': job.created_at.isoformat(),
            'records_processed': job.records_processed,
            'records_created': job.records_created,
            'records_updated': job.records_updated,
            'records_failed': job.records_failed,
            'replace_existing': job.replace_existing,
        }
        
        if job.status in ['completed', 'partial', 'failed']:
            job_data.update({
                'completed_at': job.completed_at.isoformat() if job.completed_at else None,
                'validation_errors': job.validation_errors
            })
            
            if job.status == 'failed':
                job_data['error_message'] = job.error_message
        
        jobs_data.append(job_data)
    
    return JsonResponse({'success': True, 'jobs': jobs_data})

@login_required
def create_backup(request):
    """Create a manual system backup"""
    # RBAC v0.1 Compliant Access Control - Only Global Admin has FULL backup access
    if request.user.role != 'globaladmin':
        return JsonResponse({'success': False, 'error': 'Permission denied - Global Admin access required'})
    
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request method'})
    
    description = request.POST.get('description', 'Manual backup')
    
    import tempfile
    import shutil
    temp_dir_used = False
    try:
        # Determine backup directory - use temp if S3, otherwise use MEDIA_ROOT
        if settings.MEDIA_ROOT:
            backup_dir = os.path.join(settings.MEDIA_ROOT, 'backups')
            os.makedirs(backup_dir, exist_ok=True)
        else:
            # Using S3 - create temp directory for backup
            backup_dir = tempfile.mkdtemp(prefix='backup_')
            temp_dir_used = True
            logger.info(f"Using temp directory for backup: {backup_dir}")
        
        # Generate backup filename with timestamp
        timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
        backup_filename = f'full_backup_{timestamp}.zip'
        
        # Start backup export using sys.executable (same fix as export/import)
        cmd = [
            sys.executable, 'manage.py', 'export_data',
            '--type', 'all',
            '--output', backup_dir,
            '--include-files'
        ]
        
        # Run backup command with better error handling
        result = subprocess.run(
            cmd, 
            cwd=settings.BASE_DIR, 
            capture_output=True, 
            text=True, 
            check=True
        )
        
        # Find the generated backup file (the export command creates a timestamped zip)
        pattern = os.path.join(backup_dir, 'all_export_*.zip')
        backup_files = glob.glob(pattern)
        
        if backup_files:
            # Use the most recent backup file
            actual_backup_path = max(backup_files, key=os.path.getctime)
            file_size = os.path.getsize(actual_backup_path)
            
            # Rename the file to our backup naming convention
            final_backup_path = os.path.join(backup_dir, backup_filename)
            if actual_backup_path != final_backup_path:
                os.rename(actual_backup_path, final_backup_path)
                actual_backup_path = final_backup_path
            
            # If using S3, upload backup file to S3 and update file_path
            if temp_dir_used:
                s3_key = f'backups/{backup_filename}'
                try:
                    with open(actual_backup_path, 'rb') as f:
                        default_storage.save(s3_key, ContentFile(f.read()))
                    # Update file_path to S3 key for database record
                    actual_backup_path = s3_key
                    logger.info(f"Uploaded backup file to S3: {s3_key}")
                except Exception as e:
                    logger.error(f"Failed to upload backup to S3: {str(e)}")
                    return JsonResponse({'success': False, 'error': f'Failed to upload backup to S3: {str(e)}'})
            
            # Create backup record
            backup = DataBackup.objects.create(
                backup_type='manual',
                file_path=actual_backup_path,
                file_size=file_size,
                created_by=request.user,
                description=description
            )
            
            # Clean up temp directory if using S3
            if temp_dir_used:
                try:
                    shutil.rmtree(backup_dir, ignore_errors=True)
                    logger.info(f"Cleaned up temp backup directory")
                except Exception as e:
                    logger.warning(f"Failed to clean up temp backup directory: {str(e)}")
            
            return JsonResponse({
                'success': True,
                'backup_id': backup.id,
                'message': 'Full backup created successfully',
                'file_size': file_size,
                'file_name': os.path.basename(actual_backup_path),
                'created_at': backup.created_at.isoformat()
            })
        else:
            # Clean up temp directory if no backup file found
            if temp_dir_used:
                try:
                    shutil.rmtree(backup_dir, ignore_errors=True)
                except:
                    pass
            return JsonResponse({'success': False, 'error': 'Backup file not found after export'})
            
    except subprocess.CalledProcessError as e:
        error_msg = f'Backup command failed with exit code {e.returncode}'
        if e.stdout:
            error_msg += f'\nStdout: {e.stdout}'
        if e.stderr:
            error_msg += f'\nStderr: {e.stderr}'
        return JsonResponse({'success': False, 'error': error_msg})
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Unexpected error: {str(e)}'})

@login_required
def get_backups(request):
    """Get list of system backups"""
    # RBAC v0.1 Compliant Access Control - Only Global Admin has FULL backup access
    if request.user.role != 'globaladmin':
        return JsonResponse({'success': False, 'error': 'Permission denied - Global Admin access required'})
    
    backups = DataBackup.objects.all()[:20]  # Last 20 backups
    
    backups_data = []
    for backup in backups:
        backup_data = {
            'id': backup.id,
            'backup_type': backup.backup_type,
            'description': backup.description,
            'file_size': backup.file_size,
            'created_at': backup.created_at.isoformat(),
            'created_by': backup.created_by.username if backup.created_by else 'System',
            'file_exists': os.path.exists(backup.file_path) if backup.file_path else False,
            'file_name': os.path.basename(backup.file_path) if backup.file_path else 'Unknown'
        }
        
        # Add download URL if file exists
        if backup_data['file_exists']:
            backup_data['download_url'] = reverse('account_settings:download_backup', args=[backup.id])
        
        backups_data.append(backup_data)
    
    return JsonResponse({'success': True, 'backups': backups_data})

@login_required
def download_backup(request, backup_id):
    """Download backup file"""
    # RBAC v0.1 Compliant Access Control - Only Global Admin has FULL backup access
    if request.user.role != 'globaladmin':
        return HttpResponseForbidden("Permission denied - Global Admin access required")
    
    try:
        backup = DataBackup.objects.get(id=backup_id)
        
        if not backup.file_path or not os.path.exists(backup.file_path):
            raise Http404("Backup file not found")
        
        response = FileResponse(
            open(backup.file_path, 'rb'),
            as_attachment=True,
            filename=os.path.basename(backup.file_path)
        )
        
        return response
        
    except DataBackup.DoesNotExist:
        raise Http404("Backup not found")

@login_required
def delete_backup(request, backup_id):
    """Delete a backup file and record"""
    # RBAC v0.1 Compliant Access Control - Only Global Admin has FULL backup access
    if request.user.role != 'globaladmin':
        return JsonResponse({'success': False, 'error': 'Permission denied - Global Admin access required'})
    
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request method'})
    
    try:
        backup = DataBackup.objects.get(id=backup_id)
        
        # Delete the physical file if it exists
        if backup.file_path and os.path.exists(backup.file_path):
            os.remove(backup.file_path)
        
        # Delete the database record
        backup.delete()
        
        return JsonResponse({
            'success': True,
            'message': 'Backup deleted successfully'
        })
        
    except DataBackup.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Backup not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Error deleting backup: {str(e)}'})


@login_required
def test_teams_connection(request):
    """Test Microsoft Teams integration connection"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request method'})
    
    # Check user permissions
    if not hasattr(request.user, 'role') or request.user.role not in ['admin', 'superadmin', 'globaladmin']:
        return JsonResponse({'success': False, 'error': 'Access denied. Only administrators can test Teams integration.'})
    
    try:
        # Get Teams integration for user's branch
        teams_integration = TeamsIntegration.objects.filter(branch=request.user.branch).first()
        
        if not teams_integration:
            return JsonResponse({'success': False, 'error': 'No Teams integration found for your branch'})
        
        if not teams_integration.is_active:
            return JsonResponse({'success': False, 'error': 'Teams integration is not active'})
        
        # Test the connection using Teams API client
        try:
            from teams_integration.utils.teams_api import TeamsAPIClient, TeamsAPIError
            
            api_client = TeamsAPIClient(teams_integration)
            test_result = api_client.test_connection()
            
            if test_result['success']:
                # Update integration to mark successful test
                teams_integration.token_expiry = timezone.now()
                teams_integration.save(update_fields=['token_expiry'])
                
                details = test_result.get('details', {})
                return JsonResponse({
                    'success': True,
                    'message': test_result['message'],
                    'tenant_id': details.get('tenant_id', teams_integration.tenant_id),
                    'connection_status': 'Authenticated',
                    'last_tested': timezone.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'token_expires': details.get('token_expires', 'N/A')
                })
            else:
                return JsonResponse({
                    'success': False,
                    'error': test_result.get('error', 'Connection test failed')
                })
                
        except TeamsAPIError as e:
            logger.error(f"Teams API error during connection test: {str(e)}")
            return JsonResponse({'success': False, 'error': f'Teams API Error: {str(e)}'})
            
    except ImportError:
        return JsonResponse({
            'success': False, 
            'error': 'Teams integration module not available. Please ensure the teams_integration app is properly configured.'
        })
    except Exception as e:
        logger.error(f"Error testing Teams connection for user {request.user.id}: {str(e)}")
        return JsonResponse({'success': False, 'error': f'Error testing connection: {str(e)}'})


@login_required
def validate_teams_permissions(request):
    """Validate Microsoft Teams integration permissions"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request method'})
    
    # Check user permissions
    if not hasattr(request.user, 'role') or request.user.role not in ['admin', 'superadmin', 'globaladmin']:
        return JsonResponse({'success': False, 'error': 'Access denied. Only administrators can validate Teams permissions.'})
    
    try:
        # Get Teams integration for user's branch
        teams_integration = TeamsIntegration.objects.filter(branch=request.user.branch).first()
        
        if not teams_integration:
            return JsonResponse({'success': False, 'error': 'No Teams integration found for your branch'})
        
        if not teams_integration.is_active:
            return JsonResponse({'success': False, 'error': 'Teams integration is not active'})
        
        # Validate permissions using Teams API client
        try:
            from teams_integration.utils.teams_api import TeamsAPIClient, TeamsAPIError
            
            api_client = TeamsAPIClient(teams_integration)
            validation_result = api_client.validate_permissions()
            
            # Check specifically for Calendars.ReadWrite permission (needed for auto-registration)
            calendar_permission = validation_result.get('permissions', {}).get('calendar', {})
            calendar_granted = calendar_permission.get('granted', False)
            
            # Handle 'unknown' status - if we couldn't test, assume not granted for safety
            if calendar_permission.get('granted') == 'unknown':
                calendar_granted = False
                if not calendar_permission.get('error'):
                    calendar_permission['error'] = calendar_permission.get('error', 'Could not test permission - organizer email may be missing')
            
            missing_permissions = validation_result.get('missing_permissions', [])
            all_granted = validation_result.get('all_granted', False)
            
            # Build response with detailed permission status
            response_data = {
                'success': True,
                'all_granted': all_granted,
                'calendar_permission': {
                    'granted': calendar_granted,
                    'name': calendar_permission.get('permission_name', 'Calendars.ReadWrite'),
                    'description': calendar_permission.get('description', 'Create and manage calendar events'),
                    'error': calendar_permission.get('error')
                },
                'missing_permissions': missing_permissions,
                'available_features': validation_result.get('available_features', []),
                'unavailable_features': validation_result.get('unavailable_features', []),
                'message': validation_result.get('message', 'Permission validation complete')
            }
            
            # Add specific guidance for auto-registration
            if not calendar_granted:
                response_data['auto_registration_available'] = False
                response_data['auto_registration_guidance'] = (
                    'Auto-registration requires Calendars.ReadWrite application permission. '
                    'To enable auto-registration:\n'
                    '1. Go to Azure Portal → Azure AD → App registrations\n'
                    '2. Find your app (Client ID: ' + teams_integration.client_id[:8] + '...)\n'
                    '3. Go to API permissions → Add permission → Microsoft Graph → Application permissions\n'
                    '4. Add Calendars.ReadWrite permission\n'
                    '5. Click "Grant admin consent for [Your Organization]"\n'
                    '6. Wait 5-10 minutes for permissions to propagate'
                )
            else:
                response_data['auto_registration_available'] = True
                response_data['auto_registration_guidance'] = 'Auto-registration is available. Users will be automatically added to Teams meetings.'
            
            return JsonResponse(response_data)
                
        except TeamsAPIError as e:
            logger.error(f"Teams API error during permission validation: {str(e)}")
            return JsonResponse({'success': False, 'error': f'Teams API Error: {str(e)}'})
            
    except ImportError:
        return JsonResponse({
            'success': False, 
            'error': 'Teams integration module not available. Please ensure the teams_integration app is properly configured.'
        })
    except Exception as e:
        import traceback
        error_traceback = traceback.format_exc()
        logger.error(f"Error validating Teams permissions for user {request.user.id}: {str(e)}")
        logger.error(f"Traceback: {error_traceback}")
        return JsonResponse({
            'success': False, 
            'error': f'Error validating permissions: {str(e)}',
            'details': error_traceback if settings.DEBUG else None
        })


@login_required
def test_zoom_connection(request):
    """Test Zoom integration connection (only for branch admins)"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request method'})
    
    # Check if user is branch admin
    if not hasattr(request.user, 'role') or request.user.role != 'admin' or not request.user.branch:
        return JsonResponse({'success': False, 'error': 'Access denied. Only branch admins can test Zoom integration.'})
    
    try:
        # Get user's Zoom integration
        zoom_integration = ZoomIntegration.objects.filter(user=request.user).first()
        
        if not zoom_integration:
            return JsonResponse({'success': False, 'error': 'No Zoom integration found'})
        
        if not zoom_integration.is_active:
            return JsonResponse({'success': False, 'error': 'Zoom integration is not active'})
        
        # Test the connection
        zoom_client = get_zoom_client(zoom_integration)
        result = zoom_client.test_connection()
        
        if result['success']:
            # Update integration to mark it as tested
            zoom_integration.oauth_token = 'tested'  # Use this field to indicate successful test
            zoom_integration.token_expiry = timezone.now()
            zoom_integration.save()
            
            return JsonResponse({
                'success': True,
                'message': result['message'],
                'user_email': result['user_email'],
                'user_type': result['user_type'],
                'account_id': result['account_id']
            })
        else:
            return JsonResponse({
                'success': False,
                'error': result['error']
            })
            
    except Exception as e:
        logger.error(f"Error testing Zoom connection for user {request.user.id}: {str(e)}")
        return JsonResponse({'success': False, 'error': f'Error testing connection: {str(e)}'})


@login_required
def test_sharepoint_connection(request):
    """Test SharePoint integration connection"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request method'})
    
    try:
        import json
        from sharepoint_integration.utils.sharepoint_api import SharePointAPI, SharePointAPIError
        
        # Check if testing with form data or existing integration
        if request.content_type == 'application/json' and request.body:
            # Testing with form data from modal
            try:
                data = json.loads(request.body)
                tenant_id = data.get('tenant_id')
                client_id = data.get('client_id')
                client_secret = data.get('client_secret')
                site_url = data.get('site_url')
                
                if not all([tenant_id, client_id, client_secret, site_url]):
                    return JsonResponse({'success': False, 'error': 'Missing required fields for testing'})
                
                # Create a temporary SharePoint integration object for testing
                from account_settings.models import SharePointIntegration
                temp_integration = SharePointIntegration(
                    tenant_id=tenant_id,
                    client_id=client_id,
                    client_secret=client_secret,
                    site_url=site_url,
                    name="Test Integration"
                )
            except json.JSONDecodeError as e:
                return JsonResponse({'success': False, 'error': f'Invalid JSON data: {str(e)}'})
        else:
            # Testing with existing integration
            from account_settings.models import SharePointIntegration
            sharepoint_integration = SharePointIntegration.objects.filter(user=request.user).first()
            
            if not sharepoint_integration:
                return JsonResponse({'success': False, 'error': 'No SharePoint integration found'})
            
            if not sharepoint_integration.is_active:
                return JsonResponse({'success': False, 'error': 'SharePoint integration is not active'})
            
            temp_integration = sharepoint_integration
        
        # Test the connection using SharePointAPI
        try:
            if (temp_integration.tenant_id == 'test' or 
                temp_integration.client_id == 'test' or
                'test' in temp_integration.site_url.lower()
            ):
                # Mock test for development
                return JsonResponse({
                    'success': True,
                    'message': 'SharePoint connection test successful (Mock)',
                    'site_title': 'Test SharePoint Site',
                    'site_id': 'mock-site-id-12345',
                    'connection_status': 'Connected (Development Mode)',
                    'last_tested': timezone.now().isoformat()
                })
            
            sharepoint_api = SharePointAPI(temp_integration)
            
            # Test authentication by getting an access token
            access_token = sharepoint_api.get_access_token(force_refresh=True)
            
            if not access_token:
                return JsonResponse({
                    'success': False, 
                    'error': 'Failed to authenticate with Azure AD. Please check your Tenant ID, Client ID, and Client Secret.'
                })
            
            # Test site access by getting site information
            site_info = sharepoint_api.get_site_info()
            
            if site_info:
                # Update integration to mark successful test if it's an existing integration
                if hasattr(temp_integration, 'pk') and temp_integration.pk:
                    temp_integration.last_sync_status = 'connection_tested'
                    temp_integration.last_sync_datetime = timezone.now()
                    temp_integration.save()
                
                return JsonResponse({
                    'success': True,
                    'message': 'SharePoint connection successful - Ready for manual setup',
                    'site_title': site_info.get('title', 'Unknown'),
                    'site_id': site_info.get('id', 'Unknown'),
                    'connection_status': 'Connected',
                    'last_tested': timezone.now().isoformat(),
                    'manual_setup_required': True
                })
            else:
                return JsonResponse({
                    'success': False,
                    'error': 'Authentication successful but unable to access SharePoint site. Please verify the Site URL and ensure the app has proper permissions.'
                })
                
        except SharePointAPIError as e:
            logger.error(f"SharePoint API error during connection test: {str(e)}")
            return JsonResponse({
                'success': False,
                'error': f'SharePoint API Error: {str(e)}'
            })
            
    except ImportError:
        return JsonResponse({
            'success': False, 
            'error': 'SharePoint integration module not available. Please ensure the sharepoint_integration app is properly configured.'
        })
    except Exception as e:
        logger.error(f"Error testing SharePoint connection for user {request.user.id}: {str(e)}")
        return JsonResponse({'success': False, 'error': f'Error testing connection: {str(e)}'}) 

@login_required
def manual_sharepoint_sync(request):
    """Manual SharePoint synchronization endpoint"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request method'})
    
    try:
        import json
        
        # Get sync parameters
        data = json.loads(request.body)
        sync_direction = data.get('direction', 'to_sharepoint')  # 'to_sharepoint', 'from_sharepoint'
        sync_type = data.get('sync_type', 'all')  # 'all', 'users', 'enrollments', etc.
        
        # Get user's SharePoint integration
        sharepoint_integration = SharePointIntegration.objects.filter(user=request.user).first()
        
        if not sharepoint_integration:
            return JsonResponse({'success': False, 'error': 'No SharePoint integration found'})
        
        if not sharepoint_integration.is_active:
            return JsonResponse({'success': False, 'error': 'SharePoint integration is not active'})
        
        # Validate sync direction
        if sync_direction not in ['to_sharepoint', 'from_sharepoint']:
            return JsonResponse({'success': False, 'error': 'Invalid sync direction'})
        
        # Determine sync direction label for response
        direction_label = "LMS → SharePoint" if sync_direction == 'to_sharepoint' else "SharePoint → LMS"
        
        # Try async first, fall back to sync if Celery is not available
        try:
            from sharepoint_integration.tasks import sync_sharepoint_data
            from celery.exceptions import WorkerLostError
            
            # Check if Celery is available by trying to start a task
            task = sync_sharepoint_data.delay(
                integration_id=sharepoint_integration.id,
                sync_type=sync_type,
                direction=sync_direction
            )
            
            return JsonResponse({
                'success': True,
                'message': f'{direction_label} sync started successfully',
                'task_id': task.id,
                'direction': sync_direction,
                'sync_type': sync_type,
                'is_async': True
            })
            
        except (ConnectionError, WorkerLostError, Exception) as e:
            # Celery is not available, fall back to synchronous sync
            logger.warning(f"Celery not available ({str(e)}), falling back to synchronous sync")
            
            try:
                # Import sync services for direct execution
                from sharepoint_integration.utils.sync_services import (
                    UserSyncService, EnrollmentSyncService, ProgressSyncService, 
                    CertificateSyncService, ReportsSyncService
                )
                
                results = {
                    'success': True,
                    'processed': 0,
                    'created': 0,
                    'updated': 0,
                    'errors': 0,
                    'error_messages': []
                }
                
                # Execute sync directly (synchronously)
                logger.info(f"Starting synchronous {direction_label} sync for integration {sharepoint_integration.name}")
                
                # User synchronization
                if sync_type in ['all', 'users']:
                    logger.info("Starting user synchronization...")
                    user_service = UserSyncService(sharepoint_integration)
                    
                    if sync_direction in ['to_sharepoint', 'bidirectional']:
                        user_results = user_service.sync_users_to_sharepoint()
                        _merge_sync_results(results, user_results)
                    
                    if sync_direction in ['from_sharepoint', 'bidirectional']:
                        user_results = user_service.sync_users_from_sharepoint()
                        _merge_sync_results(results, user_results)
                
                # Enrollment synchronization
                if sync_type in ['all', 'enrollments']:
                    logger.info("Starting enrollment synchronization...")
                    enrollment_service = EnrollmentSyncService(sharepoint_integration)
                    if sync_direction == 'to_sharepoint':
                        enrollment_results = enrollment_service.sync_enrollments_to_sharepoint()
                        _merge_sync_results(results, enrollment_results)
                
                # Progress synchronization
                if sync_type in ['all', 'progress']:
                    logger.info("Starting progress synchronization...")
                    progress_service = ProgressSyncService(sharepoint_integration)
                    if sync_direction == 'to_sharepoint':
                        progress_results = progress_service.sync_progress_to_sharepoint()
                        _merge_sync_results(results, progress_results)
                
                # Certificate synchronization
                if sync_type in ['all', 'certificates']:
                    logger.info("Starting certificate synchronization...")
                    cert_service = CertificateSyncService(sharepoint_integration)
                    if sync_direction == 'to_sharepoint':
                        cert_results = cert_service.sync_certificates_to_sharepoint()
                        _merge_sync_results(results, cert_results)
                
                # Update integration sync status
                sharepoint_integration.last_sync_datetime = timezone.now()
                sharepoint_integration.last_sync_status = 'completed' if results['success'] else 'failed'
                sharepoint_integration.save()
                
                return JsonResponse({
                    'success': True,
                    'message': f'{direction_label} sync completed successfully (synchronous)',
                    'task_id': 'sync_direct',
                    'direction': sync_direction,
                    'sync_type': sync_type,
                    'is_async': False,
                    'result': results
                })
                
            except ImportError as ie:
                logger.error(f"SharePoint sync services not available: {str(ie)}")
                return JsonResponse({
                    'success': False, 
                    'error': 'SharePoint sync services not available. Please ensure the sharepoint_integration app is properly configured.'
                })
            except Exception as sync_error:
                logger.error(f"Synchronous sync failed: {str(sync_error)}")
                return JsonResponse({
                    'success': False,
                    'error': f'Sync failed: {str(sync_error)}'
                })
        
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON data'})
    except Exception as e:
        logger.error(f"Error starting manual SharePoint sync for user {request.user.id}: {str(e)}")
        return JsonResponse({'success': False, 'error': f'Error starting sync: {str(e)}'})


def _merge_sync_results(main_results, new_results):
    """Helper function to merge sync results"""
    if not new_results:
        return
    
    main_results['processed'] += new_results.get('processed', 0)
    main_results['created'] += new_results.get('created', 0) 
    main_results['updated'] += new_results.get('updated', 0)
    main_results['errors'] += new_results.get('errors', 0)
    
    if new_results.get('error_messages'):
        main_results['error_messages'].extend(new_results['error_messages'])
    
    if not new_results.get('success', True):
        main_results['success'] = False


@login_required
def sharepoint_sync_status(request, task_id):
    """Check the status of a SharePoint sync task"""
    try:
        # Handle synchronous sync (direct execution)
        if task_id == 'sync_direct':
            return JsonResponse({
                'task_id': task_id,
                'status': 'SUCCESS',
                'ready': True,
                'success': True,
                'message': 'Sync completed successfully (synchronous)',
                'result': {
                    'processed': 0,
                    'created': 0,
                    'updated': 0,
                    'errors': 0
                }
            })
        
        # Handle async sync (Celery task)
        from celery.result import AsyncResult
        
        # Get task result
        task = AsyncResult(task_id)
        
        response_data = {
            'task_id': task_id,
            'status': task.status,
            'ready': task.ready()
        }
        
        if task.ready():
            if task.successful():
                result = task.result
                response_data.update({
                    'success': True,
                    'result': result,
                    'message': 'Sync completed successfully'
                })
            else:
                response_data.update({
                    'success': False,
                    'error': str(task.result) if task.result else 'Unknown error',
                    'message': 'Sync failed'
                })
        else:
            response_data.update({
                'success': None,
                'message': 'Sync in progress...'
            })
        
        return JsonResponse(response_data)
        
    except Exception as e:
        logger.error(f"Error checking SharePoint sync status for task {task_id}: {str(e)}")
        return JsonResponse({'success': False, 'error': f'Error checking status: {str(e)}'})


# AJAX endpoint views for lazy loading
@login_required
def load_business_data(request):
    """AJAX endpoint to load business data for global admins"""
    if not request.user.role == 'globaladmin':
        return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=403)
    
    try:
        # Use longer cache for business data - 15 minutes
        cache_key = f'business_data_{request.user.id}'
        cached_data = cache.get(cache_key)
        
        if cached_data is None:
            # Simplified query - get basic business data first
            businesses = Business.objects.select_related().only(
                'id', 'name', 'description'
            ).order_by('name')
            
            # Get business limits in one query
            business_limits_dict = {
                bl.business_id: bl for bl in BusinessLimits.objects.select_related('business').only(
                    'id', 'business_id', 'total_user_limit', 'branch_creation_limit'
                )
            }
            
            # Get counts separately for better performance
            User = get_user_model()
            business_stats = {}
            for business in businesses:
                # Get branch count
                branch_count = business.branches.filter(is_active=True).count()
                
                # Get user count more efficiently
                user_count = User.objects.filter(
                    branch__business=business,
                    branch__is_active=True,
                    is_active=True
                ).count()
                
                business_stats[business.id] = {
                    'branch_count': branch_count,
                    'user_count': user_count
                }
            
            businesses_with_limits = []
            for business in businesses:
                # Get or create business limits
                business_limits = business_limits_dict.get(business.id)
                if not business_limits:
                    business_limits = BusinessLimits.objects.create(
                        business=business,
                        total_user_limit=500,
                        branch_creation_limit=10,
                        updated_by=request.user
                    )
                
                stats = business_stats.get(business.id, {'branch_count': 0, 'user_count': 0})
                
                # Calculate usage data
                usage_data = {
                    'users': {
                        'current': stats['user_count'],
                        'limit': business_limits.total_user_limit,
                        'percentage': (stats['user_count'] / business_limits.total_user_limit * 100) if business_limits.total_user_limit > 0 else 0
                    },
                    'branches': {
                        'current': stats['branch_count'],
                        'limit': business_limits.branch_creation_limit,
                        'percentage': (stats['branch_count'] / business_limits.branch_creation_limit * 100) if business_limits.branch_creation_limit > 0 else 0
                    }
                }
                
                businesses_with_limits.append({
                    'business': {
                        'id': business.id,
                        'name': business.name,
                        'description': business.description,
                    },
                    'business_limits': {
                        'id': business_limits.id,
                        'total_user_limit': business_limits.total_user_limit,
                        'branch_creation_limit': business_limits.branch_creation_limit,
                    },
                    'usage_data': usage_data
                })
            
            # Cache for 15 minutes for better performance
            cache.set(cache_key, businesses_with_limits, 900)
        else:
            businesses_with_limits = cached_data
        
        return JsonResponse({'success': True, 'businesses': businesses_with_limits})
    
    except Exception as e:
        logger.exception("Error loading business data")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@login_required
def load_branches_data(request):
    """AJAX endpoint to load branches data for admins"""
    logger.info(f"load_branches_data called by user: {request.user.username} (role: {request.user.role})")
    
    if not request.user.role in ['globaladmin', 'superadmin']:
        logger.warning(f"Unauthorized access attempt by user: {request.user.username} (role: {request.user.role})")
        return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=403)
    
    try:
        # Use longer cache for branches data - 15 minutes
        cache_key = f'branches_data_{request.user.id}'
        cached_branches = cache.get(cache_key)
        
        if cached_branches is None:
            from core.utils.business_filtering import filter_branches_by_business
            
            # Simplified query - get basic branch data first
            branches = filter_branches_by_business(request.user).select_related('business').only(
                'id', 'name', 'business__name', 'sharepoint_integration_enabled', 'created_at'
            ).order_by('name')
            
            logger.info(f"Found {branches.count()} branches for user {request.user.username}")
            
            # Get user limits in one query with only needed fields
            user_limits_dict = {
                ul.branch_id: ul for ul in BranchUserLimits.objects.filter(
                    branch__in=branches
                ).only('id', 'branch_id', 'user_limit', 'admin_limit', 'instructor_limit', 'learner_limit')
            }
            
            # Get user counts separately for better performance
            User = get_user_model()
            branch_stats = {}
            for branch in branches:
                # Get user counts more efficiently
                users_qs = User.objects.filter(branch=branch, is_active=True)
                
                total_users = users_qs.count()
                admin_count = users_qs.filter(role='admin').count()
                instructor_count = users_qs.filter(role='instructor').count()
                learner_count = users_qs.filter(role='learner').count()
                
                branch_stats[branch.id] = {
                    'total_users': total_users,
                    'admin_count': admin_count,
                    'instructor_count': instructor_count,
                    'learner_count': learner_count
                }
            
            branches_with_limits = []
            for branch in branches:
                # Get or create user limits for this branch
                user_limits = user_limits_dict.get(branch.id)
                if not user_limits:
                    user_limits = BranchUserLimits.objects.create(branch=branch)
                
                stats = branch_stats.get(branch.id, {
                    'total_users': 0, 'admin_count': 0, 'instructor_count': 0, 'learner_count': 0
                })
                
                # Calculate usage data
                usage_data = {
                    'total': {
                        'current': stats['total_users'],
                        'limit': user_limits.user_limit,
                        'remaining': max(0, user_limits.user_limit - stats['total_users']),
                        'percentage': min(100, (stats['total_users'] / user_limits.user_limit) * 100) if user_limits.user_limit > 0 else 0
                    },
                    'admin': {
                        'current': stats['admin_count'],
                        'limit': user_limits.admin_limit,
                        'remaining': max(0, user_limits.admin_limit - stats['admin_count'])
                    },
                    'instructor': {
                        'current': stats['instructor_count'],
                        'limit': user_limits.instructor_limit,
                        'remaining': max(0, user_limits.instructor_limit - stats['instructor_count'])
                    },
                    'learner': {
                        'current': stats['learner_count'],
                        'limit': user_limits.learner_limit,
                        'remaining': max(0, user_limits.learner_limit - stats['learner_count'])
                    }
                }
                
                branches_with_limits.append({
                    'branch': {
                        'id': branch.id,
                        'name': branch.name,
                        'business_name': branch.business.name if branch.business else 'No Business',
                        'sharepoint_integration_enabled': branch.sharepoint_integration_enabled,
                        'created_at': branch.created_at.isoformat() if hasattr(branch, 'created_at') and branch.created_at else None,
                    },
                    'user_limits': {
                        'id': user_limits.id,
                        'user_limit': user_limits.user_limit,
                        'admin_limit': user_limits.admin_limit,
                        'instructor_limit': user_limits.instructor_limit,
                        'learner_limit': user_limits.learner_limit,
                    },
                    'usage_data': usage_data
                })
            
            # Cache for 15 minutes for better performance
            cache.set(cache_key, branches_with_limits, 900)
        else:
            branches_with_limits = cached_branches
        
        logger.info(f"Returning {len(branches_with_limits)} branches to user {request.user.username}")
        return JsonResponse({'success': True, 'branches': branches_with_limits})
    
    except Exception as e:
        logger.exception("Error loading branches data")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@login_required
def load_order_management_branches(request):
    """AJAX endpoint to load branches for order management system"""
    logger.info(f"load_order_management_branches called by user: {request.user.username} (role: {request.user.role})")
    
    if not request.user.role in ['globaladmin', 'superadmin']:
        logger.warning(f"Unauthorized access attempt by user: {request.user.username} (role: {request.user.role})")
        return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=403)
    
    try:
        from core.utils.business_filtering import filter_branches_by_business
        from business.models import Business
        
        # Load branches grouped by business
        branches_query = filter_branches_by_business(request.user).select_related('business').order_by('business__name', 'name')
        
        logger.info(f"Found {branches_query.count()} branches for order management")
        
        # Group branches by business
        businesses_dict = {}
        
        for branch in branches_query:
            business_name = branch.business.name if branch.business else 'No Business'
            business_id = branch.business.id if branch.business else 0
            
            if business_name not in businesses_dict:
                businesses_dict[business_name] = {
                    'business': {
                        'id': business_id,
                        'name': business_name
                    },
                    'branches': []
                }
            
            branch_data = {
                'id': branch.id,
                'name': branch.name,
                'order_management_enabled': branch.order_management_enabled
            }
            
            businesses_dict[business_name]['branches'].append(branch_data)
        
        # Convert to list
        businesses_with_branches = list(businesses_dict.values())
        
        logger.info(f"Returning {len(businesses_with_branches)} businesses with branches for order management")
        return JsonResponse({
            'success': True, 
            'businesses_with_branches': businesses_with_branches
        })
    
    except Exception as e:
        logger.exception("Error loading order management branches data")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@login_required
def load_integrations_data(request):
    """AJAX endpoint to load integrations data"""
    try:
        integrations_data = {}
        
        # Check if user is branch admin
        is_branch_admin = hasattr(request.user, 'role') and request.user.role == 'admin' and hasattr(request.user, 'branch') and request.user.branch
        
        # Load user's own integrations
        user_integrations = {
            'teams': TeamsIntegration.objects.filter(user=request.user).first(),
            'zoom': ZoomIntegration.objects.filter(user=request.user).first() if is_branch_admin else None,
            'stripe': StripeIntegration.objects.filter(user=request.user).first(),
            'paypal': PayPalIntegration.objects.filter(user=request.user).first(),
            'sharepoint': SharePointIntegration.objects.filter(user=request.user).first(),
        }
        
        # Serialize user integrations
        for key, integration in user_integrations.items():
            if integration:
                integrations_data[f'user_{key}'] = {
                    'id': integration.id,
                    'name': integration.name,
                    'is_active': integration.is_active,
                }
            else:
                integrations_data[f'user_{key}'] = None
        
        return JsonResponse({'integrations': integrations_data})
    
    except Exception as e:
        logger.exception("Error loading integrations data")
        return JsonResponse({'error': str(e)}, status=500) 

@login_required
def sharepoint_manual_setup_guide(request):
    """Generate dynamic manual setup guide for SharePoint integration"""
    try:
        # Get SharePoint integration config for dynamic names
        from account_settings.models import SharePointIntegration
        sharepoint_integration = SharePointIntegration.objects.filter(user=request.user).first()
        
        # Default names if no integration exists yet
        if sharepoint_integration:
            user_list_name = sharepoint_integration.user_list_name
            enrollment_list_name = sharepoint_integration.enrollment_list_name
            progress_list_name = sharepoint_integration.progress_list_name
            certificate_library_name = sharepoint_integration.certificate_library_name
            reports_library_name = sharepoint_integration.reports_library_name
            assessment_library_name = sharepoint_integration.assessment_library_name
        else:
            user_list_name = "LMS Users"
            enrollment_list_name = "Course Enrollments"
            progress_list_name = "Learning Progress"
            certificate_library_name = "Certificates"
            reports_library_name = "Reports"
            assessment_library_name = "Assessments"
        
        # Get actual field information from LMS models
        setup_data = generate_dynamic_setup_data(
            user_list_name,
            enrollment_list_name,
            progress_list_name,
            certificate_library_name,
            reports_library_name,
            assessment_library_name
        )
        
        return JsonResponse({
            'success': True,
            'setup_data': setup_data,
            'site_url': sharepoint_integration.site_url if sharepoint_integration else '',
            'branch_name': request.user.branch.name if request.user.branch else 'Your Branch'
        })
        
    except Exception as e:
        logger.error(f"Error generating SharePoint manual setup guide: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': f'Error generating setup guide: {str(e)}'
        })

def generate_dynamic_setup_data(user_list_name, enrollment_list_name, progress_list_name, 
                              certificate_library_name, reports_library_name, assessment_library_name):
    """Generate dynamic setup data with actual LMS model field information"""
    
    # Get actual User model fields
    from users.models import CustomUser
    from courses.models import Course, CourseEnrollment, TopicProgress
    from gradebook.models import Grade
    from groups.models import BranchGroup
    
    # Analyze User model fields
    user_fields = []
    for field in CustomUser._meta.get_fields():
        if hasattr(field, 'name') and field.name not in ['password', 'groups', 'user_permissions', 'logentry']:
            field_info = {
                'name': field.name,
                'verbose_name': getattr(field, 'verbose_name', field.name),
                'field_type': field.__class__.__name__,
                'choices': getattr(field, 'choices', None),
                'max_length': getattr(field, 'max_length', None),
                'null': getattr(field, 'null', False),
                'blank': getattr(field, 'blank', False)
            }
            user_fields.append(field_info)
    
    # Analyze Course model fields
    course_fields = []
    for field in Course._meta.get_fields():
        if hasattr(field, 'name') and not field.name.startswith('_'):
            field_info = {
                'name': field.name,
                'verbose_name': getattr(field, 'verbose_name', field.name),
                'field_type': field.__class__.__name__,
                'choices': getattr(field, 'choices', None),
                'max_length': getattr(field, 'max_length', None)
            }
            course_fields.append(field_info)
    
    # Analyze Grade/Assessment fields
    grade_fields = []
    for field in Grade._meta.get_fields():
        if hasattr(field, 'name'):
            field_info = {
                'name': field.name,
                'verbose_name': getattr(field, 'verbose_name', field.name),
                'field_type': field.__class__.__name__,
                'choices': getattr(field, 'choices', None)
            }
            grade_fields.append(field_info)
    
    return {
        'lists': [
            {
                'name': user_list_name,
                'description': 'LMS Users with complete profile information',
                'type': 'Custom List',
                'columns': [
                    {'name': 'LMSUserID', 'type': 'Single line of text', 'required': True, 'description': 'Unique LMS user identifier'},
                    {'name': 'Username', 'type': 'Single line of text', 'required': True, 'description': 'User login name'},
                    {'name': 'Email', 'type': 'Single line of text', 'required': True, 'description': 'Primary email address'},
                    {'name': 'FirstName', 'type': 'Single line of text', 'required': False, 'description': 'User first name'},
                    {'name': 'LastName', 'type': 'Single line of text', 'required': False, 'description': 'User last name'},
                    {'name': 'Role', 'type': 'Choice', 'required': True, 'choices': ['globaladmin', 'superadmin', 'admin', 'instructor', 'learner'], 'description': 'User role in LMS'},
                    {'name': 'Branch', 'type': 'Single line of text', 'required': False, 'description': 'Branch/organization assignment'},
                    {'name': 'DateOfBirth', 'type': 'Date and Time', 'required': False, 'description': 'User date of birth'},
                    {'name': 'Gender', 'type': 'Choice', 'required': False, 'choices': ['Male', 'Female', 'Other', 'Prefer not to say'], 'description': 'User gender'},
                    {'name': 'Phone', 'type': 'Single line of text', 'required': False, 'description': 'Contact phone number'},
                    {'name': 'Address', 'type': 'Multiple lines of text', 'required': False, 'description': 'Home address'},
                    {'name': 'StudyArea', 'type': 'Single line of text', 'required': False, 'description': 'Field of study'},
                    {'name': 'Qualifications', 'type': 'Multiple lines of text', 'required': False, 'description': 'Educational qualifications'},
                    {'name': 'JobRole', 'type': 'Single line of text', 'required': False, 'description': 'Current job title'},
                    {'name': 'Industry', 'type': 'Single line of text', 'required': False, 'description': 'Work industry'},
                    {'name': 'Skills', 'type': 'Multiple lines of text', 'required': False, 'description': 'Professional skills'},
                    {'name': 'LastLogin', 'type': 'Date and Time', 'required': False, 'description': 'Last login timestamp'},
                    {'name': 'IsActive', 'type': 'Yes/No', 'required': True, 'description': 'User account status'},
                    {'name': 'ProfileCompletion', 'type': 'Number', 'required': False, 'description': 'Profile completion percentage'},
                    {'name': 'CreatedDate', 'type': 'Date and Time', 'required': True, 'description': 'Account creation date'},
                    {'name': 'UpdatedDate', 'type': 'Date and Time', 'required': True, 'description': 'Last profile update'}
                ]
            },
            {
                'name': enrollment_list_name,
                'description': 'Course enrollment tracking and progress',
                'type': 'Custom List',
                'columns': [
                    {'name': 'LMSEnrollmentID', 'type': 'Single line of text', 'required': True, 'description': 'Unique enrollment identifier'},
                    {'name': 'UserEmail', 'type': 'Single line of text', 'required': True, 'description': 'Student email address'},
                    {'name': 'UserID', 'type': 'Single line of text', 'required': True, 'description': 'LMS user ID'},
                    {'name': 'CourseID', 'type': 'Single line of text', 'required': True, 'description': 'LMS course identifier'},
                    {'name': 'CourseTitle', 'type': 'Single line of text', 'required': True, 'description': 'Course name'},
                    {'name': 'CourseBranch', 'type': 'Single line of text', 'required': False, 'description': 'Course branch assignment'},
                    {'name': 'EnrollmentDate', 'type': 'Date and Time', 'required': True, 'description': 'Enrollment timestamp'},
                    {'name': 'CompletionDate', 'type': 'Date and Time', 'required': False, 'description': 'Course completion date'},
                    {'name': 'Status', 'type': 'Choice', 'required': True, 'choices': ['enrolled', 'in_progress', 'completed', 'withdrawn', 'expired'], 'description': 'Enrollment status'},
                    {'name': 'ProgressPercentage', 'type': 'Number', 'required': False, 'description': 'Completion percentage'},
                    {'name': 'TimeSpent', 'type': 'Number', 'required': False, 'description': 'Total time spent (minutes)'},
                    {'name': 'LastAccessed', 'type': 'Date and Time', 'required': False, 'description': 'Last course access'},
                    {'name': 'CertificateIssued', 'type': 'Yes/No', 'required': False, 'description': 'Certificate generated'},
                    {'name': 'Grade', 'type': 'Single line of text', 'required': False, 'description': 'Final grade'},
                    {'name': 'PassingScore', 'type': 'Number', 'required': False, 'description': 'Required passing score'},
                    {'name': 'FinalScore', 'type': 'Number', 'required': False, 'description': 'Achieved final score'},
                    {'name': 'UpdatedDate', 'type': 'Date and Time', 'required': True, 'description': 'Last update timestamp'}
                ]
            },
            {
                'name': progress_list_name,
                'description': 'Detailed topic-level learning progress',
                'type': 'Custom List',
                'columns': [
                    {'name': 'LMSProgressID', 'type': 'Single line of text', 'required': True, 'description': 'Unique progress record ID'},
                    {'name': 'UserEmail', 'type': 'Single line of text', 'required': True, 'description': 'Student email'},
                    {'name': 'UserID', 'type': 'Single line of text', 'required': True, 'description': 'LMS user ID'},
                    {'name': 'CourseID', 'type': 'Single line of text', 'required': True, 'description': 'Course identifier'},
                    {'name': 'CourseName', 'type': 'Single line of text', 'required': True, 'description': 'Course title'},
                    {'name': 'TopicID', 'type': 'Single line of text', 'required': True, 'description': 'Topic/module identifier'},
                    {'name': 'TopicName', 'type': 'Single line of text', 'required': True, 'description': 'Topic title'},
                    {'name': 'TopicType', 'type': 'Choice', 'required': True, 'choices': ['video', 'document', 'text', 'audio', 'web', 'quiz', 'assignment', 'discussion'], 'description': 'Content type'},
                    {'name': 'ProgressPercent', 'type': 'Number', 'required': False, 'description': 'Topic completion percentage'},
                    {'name': 'CompletionDate', 'type': 'Date and Time', 'required': False, 'description': 'Topic completion date'},
                    {'name': 'TimeSpent', 'type': 'Number', 'required': False, 'description': 'Time spent on topic (minutes)'},
                    {'name': 'Attempts', 'type': 'Number', 'required': False, 'description': 'Number of attempts'},
                    {'name': 'Score', 'type': 'Number', 'required': False, 'description': 'Achieved score'},
                    {'name': 'MaxScore', 'type': 'Number', 'required': False, 'description': 'Maximum possible score'},
                    {'name': 'LastAccessed', 'type': 'Date and Time', 'required': False, 'description': 'Last access timestamp'},
                    {'name': 'IsCompleted', 'type': 'Yes/No', 'required': False, 'description': 'Completion status'},
                    {'name': 'UpdatedDate', 'type': 'Date and Time', 'required': True, 'description': 'Last update timestamp'}
                ]
            },
            {
                'name': 'LMS Course Groups',
                'description': 'Course information and statistics',
                'type': 'Custom List',
                'columns': [
                    {'name': 'LMSCourseID', 'type': 'Single line of text', 'required': True, 'description': 'Unique course identifier'},
                    {'name': 'CourseTitle', 'type': 'Single line of text', 'required': True, 'description': 'Course name'},
                    {'name': 'CourseDescription', 'type': 'Multiple lines of text', 'required': False, 'description': 'Course description'},
                    {'name': 'Branch', 'type': 'Single line of text', 'required': False, 'description': 'Course branch assignment'},
                    {'name': 'Category', 'type': 'Single line of text', 'required': False, 'description': 'Course category'},
                    {'name': 'Language', 'type': 'Single line of text', 'required': False, 'description': 'Course language'},
                    {'name': 'DurationHours', 'type': 'Number', 'required': False, 'description': 'Estimated duration in hours'},
                    {'name': 'EnrollmentCount', 'type': 'Number', 'required': False, 'description': 'Total enrolled students'},
                    {'name': 'CompletionCount', 'type': 'Number', 'required': False, 'description': 'Students who completed'},
                    {'name': 'Status', 'type': 'Choice', 'required': True, 'choices': ['draft', 'active', 'inactive', 'archived'], 'description': 'Course status'},
                    {'name': 'IsVisible', 'type': 'Yes/No', 'required': False, 'description': 'Course visibility'},
                    {'name': 'HasPrerequisites', 'type': 'Yes/No', 'required': False, 'description': 'Has prerequisite courses'},
                    {'name': 'CreatedDate', 'type': 'Date and Time', 'required': True, 'description': 'Course creation date'},
                    {'name': 'UpdatedDate', 'type': 'Date and Time', 'required': True, 'description': 'Last update timestamp'}
                ]
            },
            {
                'name': 'LMS User Groups',
                'description': 'User group management data',
                'type': 'Custom List',
                'columns': [
                    {'name': 'LMSGroupID', 'type': 'Single line of text', 'required': True, 'description': 'Unique group identifier'},
                    {'name': 'GroupName', 'type': 'Single line of text', 'required': True, 'description': 'Group name'},
                    {'name': 'GroupDescription', 'type': 'Multiple lines of text', 'required': False, 'description': 'Group description'},
                    {'name': 'Branch', 'type': 'Single line of text', 'required': False, 'description': 'Group branch assignment'},
                    {'name': 'GroupType', 'type': 'Choice', 'required': True, 'choices': ['branch_group', 'course_access', 'custom'], 'description': 'Type of group'},
                    {'name': 'MemberCount', 'type': 'Number', 'required': False, 'description': 'Number of members'},
                    {'name': 'CreatedBy', 'type': 'Single line of text', 'required': False, 'description': 'Group creator'},
                    {'name': 'IsActive', 'type': 'Yes/No', 'required': False, 'description': 'Group status'},
                    {'name': 'HasCourseAccess', 'type': 'Yes/No', 'required': False, 'description': 'Can access courses'},
                    {'name': 'CanCreateTopics', 'type': 'Yes/No', 'required': False, 'description': 'Can create content'},
                    {'name': 'CanManageMembers', 'type': 'Yes/No', 'required': False, 'description': 'Can manage members'},
                    {'name': 'CreatedDate', 'type': 'Date and Time', 'required': True, 'description': 'Group creation date'},
                    {'name': 'UpdatedDate', 'type': 'Date and Time', 'required': True, 'description': 'Last update timestamp'}
                ]
            },
            {
                'name': 'LMS Assessment Results',
                'description': 'Assessment and gradebook data',
                'type': 'Custom List',
                'columns': [
                    {'name': 'LMSAssessmentID', 'type': 'Single line of text', 'required': True, 'description': 'Unique assessment identifier'},
                    {'name': 'UserEmail', 'type': 'Single line of text', 'required': True, 'description': 'Student email'},
                    {'name': 'UserID', 'type': 'Single line of text', 'required': True, 'description': 'LMS user ID'},
                    {'name': 'CourseID', 'type': 'Single line of text', 'required': True, 'description': 'Course identifier'},
                    {'name': 'CourseName', 'type': 'Single line of text', 'required': True, 'description': 'Course name'},
                    {'name': 'AssignmentID', 'type': 'Single line of text', 'required': False, 'description': 'Assignment identifier'},
                    {'name': 'AssignmentTitle', 'type': 'Single line of text', 'required': False, 'description': 'Assignment title'},
                    {'name': 'QuizID', 'type': 'Single line of text', 'required': False, 'description': 'Quiz identifier'},
                    {'name': 'QuizTitle', 'type': 'Single line of text', 'required': False, 'description': 'Quiz title'},
                    {'name': 'Score', 'type': 'Number', 'required': False, 'description': 'Achieved score'},
                    {'name': 'MaxScore', 'type': 'Number', 'required': False, 'description': 'Maximum possible score'},
                    {'name': 'Percentage', 'type': 'Number', 'required': False, 'description': 'Score percentage'},
                    {'name': 'Grade', 'type': 'Single line of text', 'required': False, 'description': 'Letter grade'},
                    {'name': 'PassingScore', 'type': 'Number', 'required': False, 'description': 'Required passing score'},
                    {'name': 'IsPassed', 'type': 'Yes/No', 'required': False, 'description': 'Pass/fail status'},
                    {'name': 'Attempts', 'type': 'Number', 'required': False, 'description': 'Number of attempts'},
                    {'name': 'TimeSpent', 'type': 'Number', 'required': False, 'description': 'Time spent (minutes)'},
                    {'name': 'SubmissionDate', 'type': 'Date and Time', 'required': False, 'description': 'Submission timestamp'},
                    {'name': 'GradedDate', 'type': 'Date and Time', 'required': False, 'description': 'Grading timestamp'},
                    {'name': 'Feedback', 'type': 'Multiple lines of text', 'required': False, 'description': 'Instructor feedback'},
                    {'name': 'UpdatedDate', 'type': 'Date and Time', 'required': True, 'description': 'Last update timestamp'}
                ]
            },
            {
                'name': 'LMS Certificate Registry',
                'description': 'Certificate tracking and download management',
                'type': 'Custom List',
                'columns': [
                    {'name': 'LMSCertificateID', 'type': 'Single line of text', 'required': True, 'description': 'Unique certificate identifier'},
                    {'name': 'StudentName', 'type': 'Single line of text', 'required': True, 'description': 'Student full name'},
                    {'name': 'StudentEmail', 'type': 'Single line of text', 'required': True, 'description': 'Student email address'},
                    {'name': 'StudentID', 'type': 'Single line of text', 'required': True, 'description': 'LMS student ID'},
                    {'name': 'CourseID', 'type': 'Single line of text', 'required': True, 'description': 'Course identifier'},
                    {'name': 'CourseName', 'type': 'Single line of text', 'required': True, 'description': 'Course name'},
                    {'name': 'Branch', 'type': 'Single line of text', 'required': False, 'description': 'Student branch'},
                    {'name': 'CertificateNumber', 'type': 'Single line of text', 'required': True, 'description': 'Certificate number'},
                    {'name': 'IssueDate', 'type': 'Date and Time', 'required': True, 'description': 'Certificate issue date'},
                    {'name': 'ExpiryDate', 'type': 'Date and Time', 'required': False, 'description': 'Certificate expiry date'},
                    {'name': 'Status', 'type': 'Choice', 'required': True, 'choices': ['issued', 'revoked', 'expired'], 'description': 'Certificate status'},
                    {'name': 'CertificateLink', 'type': 'Hyperlink or Picture', 'required': True, 'description': 'SharePoint download link'},
                    {'name': 'DownloadCount', 'type': 'Number', 'required': False, 'description': 'Number of downloads'},
                    {'name': 'LastDownloaded', 'type': 'Date and Time', 'required': False, 'description': 'Last download timestamp'},
                    {'name': 'FinalScore', 'type': 'Number', 'required': False, 'description': 'Course final score'},
                    {'name': 'CompletionDate', 'type': 'Date and Time', 'required': False, 'description': 'Course completion date'},
                    {'name': 'UpdatedDate', 'type': 'Date and Time', 'required': True, 'description': 'Last update timestamp'}
                ]
            }
        ],
        'libraries': [
            {
                'name': certificate_library_name,
                'description': 'Document library for storing LMS-generated certificates',
                'type': 'Document Library',
                'features': ['Version history', 'File approval', 'Content types']
            },
            {
                'name': reports_library_name,
                'description': 'Document library for LMS analytics reports and data exports',
                'type': 'Document Library',
                'features': ['Version history', 'Metadata', 'Content types']
            },
            {
                'name': assessment_library_name,
                'description': 'Document library for assessment files and submission documents',
                'type': 'Document Library',
                'features': ['Version history', 'File approval', 'Content types']
            },
            {
                'name': 'LMS Analytics Data',
                'description': 'Document library for raw analytics data files for Power BI integration',
                'type': 'Document Library',
                'features': ['Version history', 'Metadata', 'Large file support']
            }
        ]
    }









