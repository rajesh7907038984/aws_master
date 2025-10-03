"""

"""

import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.urls import reverse, NoReverseMatch
from django.contrib import messages
from django.http import HttpResponseForbidden, JsonResponse, FileResponse, Http404
from django.db.models import Count, Prefetch, Q, Sum
from django.core.cache import cache

from .models import (
    TeamsIntegration, ZoomIntegration, StripeIntegration, PayPalIntegration, 
    SharePointIntegration, PortalSettings, ExportJob, ImportJob, DataBackup, 
    GlobalAdminSettings, MenuControlSettings
)

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
                    'grade_update': False
                }
            }

        # Get integrations based on user role and branch
        integrations = {}
        
        if is_branch_admin or is_superadmin:
            # Branch admin can manage integrations for their branch
            branch = request.user.branch
            if branch:
                integrations = {
                    'teams': TeamsIntegration.objects.filter(branch=branch).first(),
                    'zoom': ZoomIntegration.objects.filter(branch=branch).first(),
                    'stripe': StripeIntegration.objects.filter(branch=branch).first(),
                    'paypal': PayPalIntegration.objects.filter(branch=branch).first(),
                    'sharepoint': SharePointIntegration.objects.filter(branch=branch).first(),
                }
        
        # Get portal settings for the branch
        portal_settings = None
        if request.user.branch:
            portal_settings, created = PortalSettings.objects.get_or_create(
                branch=request.user.branch,
                defaults={'timezone': 'UTC'}
            )
        
        # Get branch limits and usage information
        branch_limits = None
        branch_usage = None
        if request.user.branch:
            try:
                branch_limits = BranchUserLimits.objects.get(branch=request.user.branch)
            except BranchUserLimits.DoesNotExist:
                branch_limits = None
            
            # Calculate current usage
            branch_usage = {
                'users': request.user.branch.users.count(),
                'courses': request.user.branch.courses.count() if hasattr(request.user.branch, 'courses') else 0,
                'storage_used': 0,  # You might want to calculate actual storage usage
            }
        
        # Get AI token limits and usage
        ai_token_data = None
        if request.user.branch:
            try:
                ai_limits = BranchAITokenLimit.objects.get(branch=request.user.branch)
                current_month_usage = AITokenUsage.get_monthly_usage(request.user.branch)
                
                ai_token_data = {
                    'limits': ai_limits,
                    'usage': current_month_usage,
                    'usage_percentage': (current_month_usage / ai_limits.monthly_token_limit * 100) if ai_limits.monthly_token_limit > 0 else 0
                }
            except BranchAITokenLimit.DoesNotExist:
                ai_token_data = None
        
        # Get menu control settings
        menu_settings = None
        if request.user.branch:
            menu_settings, created = MenuControlSettings.objects.get_or_create(
                branch=request.user.branch,
                defaults={
                    'updated_by': request.user
                }
            )
        
        context = {
            'title': 'Account & Settings',
            'breadcrumbs': breadcrumbs,
            'active_section': active_section,
            'active_integration': active_integration,
            'is_globaladmin': is_globaladmin,
            'is_superadmin': is_superadmin,
            'is_branch_admin': is_branch_admin,
            'user_2fa_enabled': user_2fa_enabled,
            'oauth_2fa_enabled': oauth_2fa_enabled,
            'totp_2fa_enabled': totp_2fa_enabled,
            'notification_settings': notification_settings,
            'api_settings': api_settings,
            'portal_settings': portal_settings,
            'branch_limits': branch_limits,
            'branch_usage': branch_usage,
            'ai_token_data': ai_token_data,
            'menu_settings': menu_settings,
            'available_timezones': [(tz, tz) for tz in pytz.common_timezones],
            
            'teams_integration': integrations.get('teams'),
            'zoom_integration': integrations.get('zoom'),
            'stripe_integration': integrations.get('stripe'),
            'paypal_integration': integrations.get('paypal'),
            'sharepoint_integration': integrations.get('sharepoint'),
        }
        
        # Handle POST requests for various forms
        if request.method == 'POST':
            return handle_settings_post(request, context)
        
        return render(request, 'account_settings/settings.html', context)
        
    except NoReverseMatch as e:
        logger.error(f"NoReverseMatch error in account_settings: {str(e)}")
        messages.error(request, 'Navigation error occurred. Please try again.')
        return redirect('users:role_based_redirect')
    except Exception as e:
        logger.error(f"Error in account_settings view: {str(e)}")
        messages.error(request, 'An error occurred while loading settings.')
        return redirect('users:role_based_redirect')

def handle_settings_post(request, context):
    """Handle POST requests for different settings forms"""
    form_type = request.POST.get('form_type')
    
    try:
        if form_type == 'portal_settings':
            return handle_portal_settings(request)
        elif form_type == 'teams_integration':
            return handle_teams_integration(request)
        elif form_type == 'zoom_integration':
            return handle_zoom_integration(request)
        elif form_type == 'stripe_integration':
            return handle_stripe_integration(request)
        elif form_type == 'paypal_integration':
            return handle_paypal_integration(request)
        elif form_type == 'sharepoint_integration':
            return handle_sharepoint_integration(request)
        elif form_type == 'branch_limits':
            return handle_branch_limits(request)
        elif form_type == 'ai_token_limits':
            return handle_ai_token_limits(request)
        elif form_type == 'menu_settings':
            return handle_menu_settings(request)
        else:
            messages.error(request, 'Invalid form submission.')
            return redirect('account_settings:settings')
            
    except Exception as e:
        logger.error(f"Error handling {form_type} form: {str(e)}")
        messages.error(request, f'Error updating {form_type.replace("_", " ").title()}.')
        return redirect('account_settings:settings')
def handle_portal_settings(request):
    """Handle portal settings form submission"""
    if not request.user.branch:
        messages.error(request, 'No branch associated with your account.')
        return redirect('account_settings:settings')
    
    timezone_value = request.POST.get('timezone')
    
    if timezone_value not in pytz.all_timezones:
        messages.error(request, 'Invalid timezone selected.')
        return redirect('account_settings:settings')
    
    portal_settings, created = PortalSettings.objects.get_or_create(
        branch=request.user.branch,
        defaults={'timezone': timezone_value}
    )
    
    if not created:
        portal_settings.timezone = timezone_value
        portal_settings.save()
    
    messages.success(request, 'Portal settings updated successfully.')
    return redirect('account_settings:settings?tab=portal')

def handle_teams_integration(request):
    """Handle Microsoft Teams integration form submission"""
    if not request.user.branch or request.user.role not in ['admin', 'superadmin', 'globaladmin']:
        messages.error(request, 'Permission denied.')
        return redirect('account_settings:settings')
    
    name = request.POST.get('teams_name')
    client_id = request.POST.get('teams_client_id')
    client_secret = request.POST.get('teams_client_secret')
    tenant_id = request.POST.get('teams_tenant_id')
    
    if not all([name, client_id, client_secret, tenant_id]):
        messages.error(request, 'All fields are required for Teams integration.')
        return redirect('account_settings:settings?tab=integrations&integration=teams')
    
    integration, created = TeamsIntegration.objects.get_or_create(
        branch=request.user.branch,
        defaults={
            'name': name,
            'client_id': client_id,
            'client_secret': client_secret,
            'tenant_id': tenant_id,
            'user': request.user
        }
    )
    
    if not created:
        integration.name = name
        integration.client_id = client_id
        if client_secret:  # Only update if new secret provided
            integration.client_secret = client_secret
        integration.tenant_id = tenant_id
        integration.save()
    
    messages.success(request, 'Microsoft Teams integration updated successfully.')
    return redirect('account_settings:settings?tab=integrations&integration=teams')

# Continue with other integration handlers...
# (Similar pattern for zoom, stripe, paypal, sharepoint integrations)

# ... rest of the view functions remain the same ...
