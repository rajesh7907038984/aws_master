"""
Teams Integration Views

Views for managing Teams integration, testing connections,
and monitoring sync operations.
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_protect
from django.utils import timezone
from django.core.paginator import Paginator
import logging

from .models import TeamsSyncLog, TeamsMeetingSync, EntraGroupMapping
from .utils.teams_api import TeamsAPIClient, TeamsAPIError
# from .tasks import sync_teams_data, sync_entra_groups, sync_meeting_data

logger = logging.getLogger(__name__)


@login_required
def teams_integration_dashboard(request):
    """Teams integration dashboard"""
    if request.user.role not in ['admin', 'superadmin', 'globaladmin']:
        return HttpResponseForbidden("You don't have permission to access this page")
    
    # Get Teams integrations for the user's branch
    from account_settings.models import TeamsIntegration
    
    if request.user.role == 'globaladmin':
        integrations = TeamsIntegration.objects.all()
    elif request.user.role == 'superadmin':
        integrations = TeamsIntegration.objects.filter(
            user__branch__in=request.user.assigned_branches.all()
        )
    else:
        integrations = TeamsIntegration.objects.filter(
            branch=request.user.branch
        )
    
    # Get recent sync logs
    recent_logs = TeamsSyncLog.objects.filter(
        integration__in=integrations
    ).order_by('-started_at')[:10]
    
    # Get sync statistics
    sync_stats = {
        'total_syncs': TeamsSyncLog.objects.filter(integration__in=integrations).count(),
        'successful_syncs': TeamsSyncLog.objects.filter(
            integration__in=integrations,
            status='completed'
        ).count(),
        'failed_syncs': TeamsSyncLog.objects.filter(
            integration__in=integrations,
            status='failed'
        ).count(),
        'active_integrations': integrations.filter(is_active=True).count()
    }
    
    context = {
        'integrations': integrations,
        'recent_logs': recent_logs,
        'sync_stats': sync_stats,
        'breadcrumbs': [
            {'url': '/', 'label': 'Home', 'icon': 'fa-home'},
            {'label': 'Teams Integration', 'icon': 'fa-microsoft'}
        ]
    }
    
    return render(request, 'teams_integration/dashboard.html', context)


@login_required
@require_POST
@csrf_protect
def test_teams_connection(request, integration_id):
    """Test Teams API connection"""
    if request.user.role not in ['admin', 'superadmin', 'globaladmin']:
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)
    
    try:
        from account_settings.models import TeamsIntegration
        integration = get_object_or_404(TeamsIntegration, id=integration_id)
        
        # Test the connection
        api_client = TeamsAPIClient(integration)
        test_result = api_client.test_connection()
        
        if test_result['success']:
            messages.success(request, f"Teams connection test successful: {test_result['message']}")
            return JsonResponse({
                'success': True,
                'message': test_result['message'],
                'user_info': test_result.get('user_info', {})
            })
        else:
            messages.error(request, f"Teams connection test failed: {test_result['error']}")
            return JsonResponse({
                'success': False,
                'error': test_result['error']
            })
            
    except TeamsAPIError as e:
        logger.error(f"Teams API error during connection test: {str(e)}")
        messages.error(request, f"Teams API error: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        })
    except Exception as e:
        logger.error(f"Error testing Teams connection: {str(e)}")
        messages.error(request, f"Connection test failed: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


@login_required
@require_POST
@csrf_protect
def sync_entra_groups_manual(request, integration_id):
    """Manually trigger Entra ID groups sync"""
    if request.user.role not in ['admin', 'superadmin', 'globaladmin']:
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)
    
    try:
        from account_settings.models import TeamsIntegration
        integration = get_object_or_404(TeamsIntegration, id=integration_id)
        
        # Start async sync task
        task = sync_entra_groups.delay(integration_id)
        
        messages.success(request, "Entra ID groups sync started. Check the sync logs for progress.")
        return JsonResponse({
            'success': True,
            'message': 'Entra groups sync started',
            'task_id': task.id
        })
        
    except Exception as e:
        logger.error(f"Error starting Entra groups sync: {str(e)}")
        messages.error(request, f"Failed to start sync: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


@login_required
@require_POST
@csrf_protect
def sync_meeting_data_manual(request, conference_id):
    """Manually trigger meeting data sync"""
    if request.user.role not in ['instructor', 'admin', 'superadmin', 'globaladmin']:
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)
    
    try:
        from conferences.models import Conference
        conference = get_object_or_404(Conference, id=conference_id)
        
        # Check if user has permission to sync this conference
        if not (request.user.role in ['admin', 'superadmin', 'globaladmin'] or 
                conference.created_by == request.user):
            return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)
        
        # Start async sync task
        task = sync_meeting_data.delay(conference_id)
        
        messages.success(request, "Meeting data sync started. Check the sync logs for progress.")
        return JsonResponse({
            'success': True,
            'message': 'Meeting data sync started',
            'task_id': task.id
        })
        
    except Exception as e:
        logger.error(f"Error starting meeting data sync: {str(e)}")
        messages.error(request, f"Failed to start sync: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


@login_required
def sync_logs(request):
    """View sync logs"""
    if request.user.role not in ['admin', 'superadmin', 'globaladmin']:
        return HttpResponseForbidden("You don't have permission to access this page")
    
    # Get sync logs for the user's integrations
    from account_settings.models import TeamsIntegration
    
    if request.user.role == 'globaladmin':
        integrations = TeamsIntegration.objects.all()
    elif request.user.role == 'superadmin':
        integrations = TeamsIntegration.objects.filter(
            user__branch__in=request.user.assigned_branches.all()
        )
    else:
        integrations = TeamsIntegration.objects.filter(
            branch=request.user.branch
        )
    
    logs = TeamsSyncLog.objects.filter(
        integration__in=integrations
    ).order_by('-started_at')
    
    # Pagination
    paginator = Paginator(logs, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'breadcrumbs': [
            {'url': '/', 'label': 'Home', 'icon': 'fa-home'},
            {'url': '/teams-integration/', 'label': 'Teams Integration', 'icon': 'fa-microsoft'},
            {'label': 'Sync Logs', 'icon': 'fa-list'}
        ]
    }
    
    return render(request, 'teams_integration/sync_logs.html', context)


@login_required
def sync_log_detail(request, log_id):
    """View detailed sync log"""
    if request.user.role not in ['admin', 'superadmin', 'globaladmin']:
        return HttpResponseForbidden("You don't have permission to access this page")
    
    log = get_object_or_404(TeamsSyncLog, id=log_id)
    
    # Check if user has permission to view this log
    if request.user.role == 'admin' and log.integration.branch != request.user.branch:
        return HttpResponseForbidden("You don't have permission to view this log")
    
    context = {
        'log': log,
        'breadcrumbs': [
            {'url': '/', 'label': 'Home', 'icon': 'fa-home'},
            {'url': '/teams-integration/', 'label': 'Teams Integration', 'icon': 'fa-microsoft'},
            {'url': '/teams-integration/sync-logs/', 'label': 'Sync Logs', 'icon': 'fa-list'},
            {'label': f'Log #{log.id}', 'icon': 'fa-info-circle'}
        ]
    }
    
    return render(request, 'teams_integration/sync_log_detail.html', context)


@login_required
def meeting_syncs(request):
    """View meeting sync records"""
    if request.user.role not in ['instructor', 'admin', 'superadmin', 'globaladmin']:
        return HttpResponseForbidden("You don't have permission to access this page")
    
    # Get meeting syncs for conferences the user can access
    from conferences.models import Conference
    
    if request.user.role in ['admin', 'superadmin', 'globaladmin']:
        meeting_syncs = TeamsMeetingSync.objects.all()
    else:
        # Instructors can only see their own conferences
        meeting_syncs = TeamsMeetingSync.objects.filter(
            conference__created_by=request.user
        )
    
    # Pagination
    paginator = Paginator(meeting_syncs, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'breadcrumbs': [
            {'url': '/', 'label': 'Home', 'icon': 'fa-home'},
            {'url': '/teams-integration/', 'label': 'Teams Integration', 'icon': 'fa-microsoft'},
            {'label': 'Meeting Syncs', 'icon': 'fa-video'}
        ]
    }
    
    return render(request, 'teams_integration/meeting_syncs.html', context)


@login_required
def entra_group_mappings(request):
    """View Entra group mappings"""
    if request.user.role not in ['admin', 'superadmin', 'globaladmin']:
        return HttpResponseForbidden("You don't have permission to access this page")
    
    # Get mappings for the user's integrations
    from account_settings.models import TeamsIntegration
    
    if request.user.role == 'globaladmin':
        integrations = TeamsIntegration.objects.all()
    elif request.user.role == 'superadmin':
        integrations = TeamsIntegration.objects.filter(
            user__branch__in=request.user.assigned_branches.all()
        )
    else:
        integrations = TeamsIntegration.objects.filter(
            branch=request.user.branch
        )
    
    mappings = EntraGroupMapping.objects.filter(
        integration__in=integrations
    ).order_by('entra_group_name')
    
    # Pagination
    paginator = Paginator(mappings, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'breadcrumbs': [
            {'url': '/', 'label': 'Home', 'icon': 'fa-home'},
            {'url': '/teams-integration/', 'label': 'Teams Integration', 'icon': 'fa-microsoft'},
            {'label': 'Entra Group Mappings', 'icon': 'fa-users'}
        ]
    }
    
    return render(request, 'teams_integration/entra_mappings.html', context)


@login_required
@require_POST
@csrf_protect
def toggle_group_mapping(request, mapping_id):
    """Toggle Entra group mapping active status"""
    if request.user.role not in ['admin', 'superadmin', 'globaladmin']:
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)
    
    try:
        mapping = get_object_or_404(EntraGroupMapping, id=mapping_id)
        
        # Check if user has permission to modify this mapping
        if request.user.role == 'admin' and mapping.integration.branch != request.user.branch:
            return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)
        
        # Toggle active status
        mapping.is_active = not mapping.is_active
        mapping.save()
        
        status = 'activated' if mapping.is_active else 'deactivated'
        messages.success(request, f"Group mapping {status} successfully.")
        
        return JsonResponse({
            'success': True,
            'message': f'Group mapping {status}',
            'is_active': mapping.is_active
        })
        
    except Exception as e:
        logger.error(f"Error toggling group mapping: {str(e)}")
        messages.error(request, f"Failed to toggle mapping: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


@login_required
def health_check(request):
    """Teams integrations health check"""
    if request.user.role not in ['admin', 'superadmin', 'globaladmin']:
        return HttpResponseForbidden("You don't have permission to access this page")
    
    try:
        from .tasks import health_check_teams_integrations
        
        # Start health check task
        task = health_check_teams_integrations.delay()
        
        messages.info(request, "Health check started. Results will be available shortly.")
        return JsonResponse({
            'success': True,
            'message': 'Health check started',
            'task_id': task.id
        })
        
    except Exception as e:
        logger.error(f"Error starting health check: {str(e)}")
        messages.error(request, f"Failed to start health check: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        })
