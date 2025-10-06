from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponseForbidden, HttpResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.utils.dateparse import parse_date
from django.core.paginator import Paginator
from django.urls import reverse
from django.contrib import messages
from django.views.decorators.csrf import csrf_protect, csrf_exempt, requires_csrf_token
from django.utils import timezone
from django.contrib.auth import get_user_model
from urllib.parse import quote_plus, urlparse, parse_qs, urlencode, urlunparse
import json
import datetime
import uuid
import requests
import time
import hashlib
import base64
import jwt
import hmac
import logging
from django.db.models import Q
import re
import random
from django.utils.html import strip_tags
from django.utils.safestring import mark_safe
from django.core.exceptions import PermissionDenied
from django.db.models import Count, F, Avg, Sum
from django.template.loader import render_to_string

from .models import Conference
from courses.models import Course
from account_settings.models import (
    TeamsIntegration, 
    
    ZoomIntegration
)
from lms_rubrics.models import Rubric, RubricOverallFeedback
from .models import (
    ConferenceAttendance, 
    ConferenceRecording, 
    ConferenceFile, 
    ConferenceChat, 
    ConferenceSyncLog,
    GuestParticipant,
    ConferenceParticipant,
    ParticipantTrackingData,
    ConferenceRubricEvaluation
)

# Import the form
from .forms import ConferenceForm, ConferenceFileUploadForm
from core.rbac_validators import ConditionalAccessValidator

User = get_user_model()

logger = logging.getLogger(__name__)

@login_required
def conference_list(request):
    """View to display list of conferences with role-based access control"""
    user = request.user
    
    # Role-based filtering
    if user.role == 'globaladmin' or user.is_superuser:
        # Global Admin: Can view all conferences from all branches
        conferences_list = Conference.objects.all().order_by('-date', '-start_time')
        can_create = True
        can_edit = True
        can_manage_all = True
        
    elif user.role == 'superadmin':
        # Super Admin: CONDITIONAL access (business-scoped conferences)
        from core.utils.business_filtering import filter_queryset_by_business
        conferences_list = filter_queryset_by_business(
            Conference.objects.all(), 
            user, 
            business_field_path='created_by__branch__business'
        ).order_by('-date', '-start_time')
        can_create = True
        can_edit = True
        can_manage_all = False
        
    elif user.role == 'admin':
        # Branch Admin: Can view all conferences from their branch
        if user.branch:
            conferences_list = Conference.objects.filter(
                created_by__branch=user.branch
            ).order_by('-date', '-start_time')
        else:
            conferences_list = Conference.objects.none()
        can_create = True
        can_edit = True
        can_manage_all = False
        
    elif user.role == 'instructor':
        # Instructor: Can view conferences they created and published conferences they can join
        created_conferences = Conference.objects.filter(created_by=user)
        
        # Include conferences from assigned courses, enrolled courses, and group-assigned courses
        enrolled_courses = Course.objects.filter(enrolled_users=user).values_list('id', flat=True)
        assigned_courses = Course.objects.filter(instructor=user).values_list('id', flat=True)
        
        # Add group-assigned courses
        group_assigned_courses = Course.objects.filter(
            accessible_groups__memberships__user=user,
            accessible_groups__memberships__is_active=True,
            accessible_groups__memberships__custom_role__name__icontains='instructor'
        ).values_list('id', flat=True)
        
        accessible_course_ids = set(enrolled_courses) | set(assigned_courses) | set(group_assigned_courses)
        
        if user.branch:
            accessible_conferences = Conference.objects.filter(
                Q(status='published') & (
                    Q(created_by__branch=user.branch) |
                    Q(course__in=accessible_course_ids) |  # Direct course relationships
                    Q(topics__coursetopic__course__in=accessible_course_ids)  # Topic-based relationships
                )
            ).exclude(created_by=user).distinct()
        else:
            accessible_conferences = Conference.objects.filter(
                Q(status='published') & (
                    Q(course__in=accessible_course_ids) |  # Direct course relationships
                    Q(topics__coursetopic__course__in=accessible_course_ids)  # Topic-based relationships
                )
            ).exclude(created_by=user).distinct()
        
        conferences_list = created_conferences.union(accessible_conferences).order_by('-date', '-start_time')
        can_create = True
        can_edit = True  # Can edit only their own conferences
        can_manage_all = False
        
    else:  # learner
        # Learner: Can view published conferences from courses they're enrolled in or same branch
        enrolled_courses = Course.objects.filter(enrolled_users=user).values_list('id', flat=True)
        
        # Get conferences linked to enrolled courses or from same branch
        conferences_queryset = Conference.objects.filter(
            Q(status='published') & (
                Q(course__in=enrolled_courses) |  # Direct course link
                Q(topics__coursetopic__course__in=enrolled_courses) |  # Through topics
                Q(created_by__branch=user.branch) if user.branch else Q()  # Same branch
            )
        ).distinct().order_by('-date', '-start_time')
        
        conferences_list = conferences_queryset
        can_create = False
        can_edit = False
        can_manage_all = False
    
    # Get date range filters from request, if provided
    from_date_str = request.GET.get('from_date')
    to_date_str = request.GET.get('to_date')
    
    # Apply date range filters if provided
    if from_date_str:
        try:
            from_date = parse_date(from_date_str)
            conferences_list = conferences_list.filter(date__gte=from_date)
        except (ValueError, TypeError):
            pass
    
    if to_date_str:
        try:
            to_date = parse_date(to_date_str)
            conferences_list = conferences_list.filter(date__lte=to_date)
        except (ValueError, TypeError):
            pass
    
    # Pagination
    paginator = Paginator(conferences_list, 10)  # Show 10 conferences per page
    page = request.GET.get('page')
    conferences = paginator.get_page(page)
    
    # Define breadcrumbs
    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'label': 'Conferences', 'icon': 'fa-video'}
    ]
    
    # Get available Zoom integrations for current user based on role
    available_zoom_integrations = []
    if user.role in ['instructor', 'admin', 'superadmin'] or user.is_superuser:
        # User's own integrations
        user_integrations = ZoomIntegration.objects.filter(user=user, is_active=True)
        available_zoom_integrations.extend(user_integrations)
        
        # Branch-level integrations (if user has a branch)
        if user.branch:
            branch_integrations = ZoomIntegration.objects.filter(
                user__branch=user.branch,
                is_active=True
            ).exclude(user=user)
            available_zoom_integrations.extend(branch_integrations)
    
    context = {
        'conferences': conferences,
        'title': 'Conferences',
        'breadcrumbs': breadcrumbs,
        'from_date': from_date_str,
        'to_date': to_date_str,
        'can_create': can_create,
        'can_edit': can_edit,
        'can_manage_all': can_manage_all,
        'user_role': user.role,
        'user_branch': user.branch,
        'available_zoom_integrations': available_zoom_integrations,
    }
    return render(request, 'conferences/conferences.html', context)

@login_required
def new_conference(request, course_id=None):
    """View to create a new conference"""
    # RBAC v0.1 Compliant Access Control - Enhanced for RBAC v0.1
    user = request.user
    
    # Role-based conference creation access
    can_create = False
    if user.role == 'globaladmin':
        can_create = True  # FULL access
    elif user.role == 'superadmin':
        can_create = True  # CONDITIONAL access (business-scoped)
    elif user.role == 'admin':
        can_create = True  # CONDITIONAL access (branch-scoped)
    elif user.role == 'instructor':
        can_create = True  # CONDITIONAL access (branch-scoped)
    
    if not can_create:
        return HttpResponseForbidden("You don't have permission to create conferences")
    
    # Get the course
    course = None
    if course_id:
        course = get_object_or_404(Course, id=course_id)
        
        # Additional validation for course access
        from core.rbac_validators import ConditionalAccessValidator
        if not ConditionalAccessValidator.validate_branch_access(user, course.branch if hasattr(course, 'branch') else None):
            return HttpResponseForbidden("You don't have permission to create conferences for this course")
    
    # Define breadcrumbs
    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': reverse('conferences:conference_list'), 'label': 'Conferences', 'icon': 'fa-video'},
        {'label': 'New Conference', 'icon': 'fa-plus-circle'}
    ]
    
    # Get available platform integrations for current user based on role and branch
    zoom_integrations = []
    teams_integrations = []
    user = request.user
    
    # RBAC v0.1 Compliant Integration Access
    if user.role == 'globaladmin':
        # Global Admin: FULL access to all integrations
        zoom_integrations = list(ZoomIntegration.objects.filter(is_active=True))
        teams_integrations = list(TeamsIntegration.objects.filter(is_active=True))
        
    elif user.role == 'superadmin':
        # Super Admin: CONDITIONAL access (business-scoped integrations)
        if hasattr(user, 'business_assignments'):
            assigned_businesses = user.business_assignments.filter(is_active=True).values_list('business', flat=True)
            zoom_integrations = list(ZoomIntegration.objects.filter(
                user__branch__business__in=assigned_businesses, is_active=True
            ))
            teams_integrations = list(TeamsIntegration.objects.filter(
                user__branch__business__in=assigned_businesses, is_active=True
            ))
        
    elif user.role in ['admin', 'instructor']:
        # Branch Admin/Instructor: CONDITIONAL access (branch-scoped integrations)
        if user.branch:
            # User's own integrations
            user_zoom_integrations = ZoomIntegration.objects.filter(user=user, is_active=True)
            zoom_integrations.extend(user_zoom_integrations)
            
            user_teams_integrations = TeamsIntegration.objects.filter(user=user, is_active=True)
            teams_integrations.extend(user_teams_integrations)
            
            # Branch-level integrations
            branch_zoom_integrations = ZoomIntegration.objects.filter(
                user__branch=user.branch, is_active=True
            ).exclude(user=user)
            zoom_integrations.extend(branch_zoom_integrations)
            
            branch_teams_integrations = TeamsIntegration.objects.filter(
                user__branch=user.branch, is_active=True
            ).exclude(user=user)
            teams_integrations.extend(branch_teams_integrations)
    
    if request.method == 'POST':
        form = ConferenceForm(request.POST, user=request.user)
        if form.is_valid():
            conference = form.save(commit=False)
            conference.default_join_type = 'registered'  # Course registered users only
            conference.join_experience = 'standard'  # Standard guest form (name + email)
            conference.course = course
            conference.created_by = request.user
            conference.visibility = 'public'  # Always force visibility to be public
            
            # Set meeting platform to 'other' if not provided (fallback)
            if not conference.meeting_platform:
                conference.meeting_platform = 'other'
            
            conference.save()
            # Attempt to disable registration on Zoom meeting if platform is Zoom
            if conference.meeting_platform == 'zoom':
                update_meeting_to_disable_registration(conference)
            messages.success(request, 'Conference created successfully with direct join enabled.')
            return redirect('conferences:conference_list')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = ConferenceForm(user=request.user)
    
    # Get available rubrics based on user role using centralized function
    from lms_rubrics.utils import get_filtered_rubrics_for_user
    available_rubrics = get_filtered_rubrics_for_user(user, course)
    
    context = {
        'title': 'New Conference',
        'description': 'Create a new conference',
        'breadcrumbs': breadcrumbs,
        'teams_integrations': teams_integrations,
        'zoom_integrations': zoom_integrations,
        'available_rubrics': available_rubrics,
        'form': form,
    }
    return render(request, 'conferences/new_conference.html', context)

@login_required
def edit_conference(request, conference_id):
    """View to edit an existing conference"""
    try:
        conference = get_object_or_404(Conference, id=conference_id)
    except:
        messages.error(request, f'Conference with ID {conference_id} does not exist or has been deleted.')
        return redirect('conferences:conference_list')
    
    # Check if user has permission to edit this conference
    if not (request.user.is_superuser or 
            request.user.role in ['instructor', 'admin', 'superadmin'] and request.user == conference.created_by):
        messages.error(request, 'You do not have permission to edit this conference.')
        return redirect('conferences:conference_list')
    
    # Define breadcrumbs
    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': reverse('conferences:conference_list'), 'label': 'Conferences', 'icon': 'fa-video'},
        {'label': conference.title, 'icon': 'fa-file-alt'},
        {'label': 'Edit', 'icon': 'fa-edit'}
    ]
    
    # Get available platform integrations for current user based on role and branch
    zoom_integrations = []
    teams_integrations = []
    user = request.user
    
    if user.role in ['instructor', 'admin', 'superadmin'] or user.is_superuser:
        # For admin+ roles, include their own integrations
        if user.role in ['admin', 'superadmin'] or user.is_superuser:
            # User's own Zoom integrations
            user_zoom_integrations = ZoomIntegration.objects.filter(user=user, is_active=True)
            zoom_integrations.extend(user_zoom_integrations)
            
            # User's own Teams integrations
            user_teams_integrations = TeamsIntegration.objects.filter(user=user, is_active=True)
            teams_integrations.extend(user_teams_integrations)
        
        # Branch-level integrations (available to instructors and admins)
        if user.branch:
            # Branch Zoom integrations
            branch_zoom_integrations = ZoomIntegration.objects.filter(
                user__branch=user.branch,
                is_active=True
            )
            # For instructors, exclude their own integrations (if any)
            if user.role == 'instructor':
                branch_zoom_integrations = branch_zoom_integrations.exclude(user=user)
            zoom_integrations.extend(branch_zoom_integrations)
            
            # Branch Teams integrations
            branch_teams_integrations = TeamsIntegration.objects.filter(
                user__branch=user.branch, is_active=True
            ).exclude(user=user)
            # For instructors, exclude their own integrations (if any)
            if user.role == 'instructor':
                branch_teams_integrations = branch_teams_integrations.exclude(user=user)
            teams_integrations.extend(branch_teams_integrations)
    
    if request.method == 'POST':
        form = ConferenceForm(request.POST, instance=conference, user=request.user)
        if form.is_valid():
            conference = form.save(commit=False)
            conference.visibility = 'public'  # Always force visibility to be public
            conference.save()
            # Attempt to disable registration on Zoom meeting if platform is Zoom
            if conference.meeting_platform == 'zoom':
                update_meeting_to_disable_registration(conference)
            messages.success(request, 'Conference updated successfully.')
            return redirect('conferences:conference_list')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = ConferenceForm(instance=conference, user=request.user)
    
    # Get available rubrics based on user role using centralized function
    user = request.user
    from lms_rubrics.utils import get_filtered_rubrics_for_user
    course = conference.course if hasattr(conference, 'course') else None
    available_rubrics = get_filtered_rubrics_for_user(user, course)
    
    return render(request, 'conferences/edit_conference.html', {
        'conference': conference,
        'title': f'Edit Conference: {conference.title}',
        'description': 'Update conference details',
        'breadcrumbs': breadcrumbs,
        'teams_integrations': teams_integrations,
        'zoom_integrations': zoom_integrations,
        'available_rubrics': available_rubrics,
        'form': form,
    })

@login_required
def delete_conference(request, conference_id):
    try:
        conference = get_object_or_404(Conference, id=conference_id)
    except:
        messages.error(request, f'Conference with ID {conference_id} does not exist or has been deleted.')
        return redirect('conferences:conference_list')
    
    # Define breadcrumbs
    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': reverse('conferences:conference_list'), 'label': 'Conferences', 'icon': 'fa-video'},
        {'label': conference.title, 'icon': 'fa-file-alt'},
        {'label': 'Delete', 'icon': 'fa-trash'}
    ]
    
    # Check if user has permission to delete this conference (same logic as edit)
    if not (request.user.is_superuser or request.user.role in ['instructor', 'admin', 'superadmin'] or 
            request.user == conference.created_by):
        messages.error(request, 'You do not have permission to delete this conference.')
        return redirect('conferences:conference_list')
    
    if request.method == 'POST':
        # If this is a Zoom meeting, try to delete it from Zoom first
        if conference.meeting_platform == 'zoom' and conference.meeting_id:
            logger.info(f"Attempting to delete Zoom meeting {conference.meeting_id} for conference {conference.id}")
            try:
                # Try to find an active Zoom integration
                integration = ZoomIntegration.objects.filter(user=conference.created_by, is_active=True).first()
                
                # If none on user, try branch-level integration
                if not integration and hasattr(conference.created_by, 'branch') and conference.created_by.branch:
                    integration = ZoomIntegration.objects.filter(
                        user__branch=conference.created_by.branch,
                        is_active=True
                    ).exclude(user=conference.created_by).first()
                
                # Fallback to any active integration
                if not integration:
                    integration = ZoomIntegration.objects.filter(is_active=True).first()
                
                if integration:
                    # Import zoom module
                    from account_settings.zoom import get_zoom_client
                    
                    # Get Zoom client and delete the meeting
                    client = get_zoom_client(integration)
                    result = client.delete_meeting(conference.meeting_id)
                    
                    if result.get('success'):
                        logger.info(f"Successfully deleted Zoom meeting {conference.meeting_id}")
                        messages.success(request, 'Zoom meeting deleted successfully.')
                    else:
                        error_msg = result.get('error', 'Unknown error')
                        logger.error(f"Failed to delete Zoom meeting {conference.meeting_id}: {error_msg}")
                        messages.warning(request, f'Conference will be deleted, but Zoom meeting could not be removed: {error_msg}')
                else:
                    logger.warning(f"No active Zoom integration found to delete meeting {conference.meeting_id}")
                    messages.warning(request, 'Conference will be deleted, but no Zoom integration found to remove the meeting.')
                    
            except Exception as e:
                logger.exception(f"Error deleting Zoom meeting {conference.meeting_id}: {str(e)}")
                messages.warning(request, f'Conference will be deleted, but an error occurred removing the Zoom meeting: {str(e)}')
        
        # Delete the conference (this will also trigger the post_delete signal as a backup)
        conference_title = conference.title
        conference.delete()
        messages.success(request, f'Conference "{conference_title}" deleted successfully.')
        return redirect('conferences:conference_list')
    
    return render(request, 'conferences/delete_conference.html', {
        'conference': conference,
        'title': f'Delete: {conference.title}',
        'description': 'Delete conference',
        'breadcrumbs': breadcrumbs
    })

@login_required
@csrf_protect
def create_meeting_api(request):
    """API endpoint to create meetings via different platforms"""
    if request.method == 'POST':
        try:
            # Parse request data - handle both JSON and form data
            data = json.loads(request.body) if request.content_type == 'application/json' else request.POST
            
            platform = data.get('platform')
            integration_id = data.get('integration_id')
            title = data.get('title')
            description = data.get('description', '')
            start_datetime_str = data.get('start_datetime')
            end_datetime_str = data.get('end_datetime')
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False, 
                'error': 'Invalid JSON in request body'
            }, status=400)
        
        # Validate required fields
        if not all([platform, integration_id, title, start_datetime_str, end_datetime_str]):
            return JsonResponse({
                'success': False, 
                'error': 'Missing required fields: platform, integration_id, title, start_datetime, end_datetime'
            }, status=400)
        
        try:
            start_datetime = datetime.datetime.fromisoformat(start_datetime_str.replace('Z', '+00:00'))
            end_datetime = datetime.datetime.fromisoformat(end_datetime_str.replace('Z', '+00:00'))
        except (ValueError, AttributeError) as e:
            return JsonResponse({'success': False, 'error': f'Invalid datetime format: {str(e)}'}, status=400)
        
        if platform == 'teams':
            return create_teams_meeting(request.user, integration_id, title, description, start_datetime, end_datetime)
        elif platform == 'zoom':
            return create_zoom_meeting(request.user, integration_id, title, description, start_datetime, end_datetime)
        else:
            return JsonResponse({'success': False, 'error': 'Unsupported platform'}, status=400)
            
    return JsonResponse({'success': False, 'error': 'Only POST method allowed'}, status=405)

@login_required
@csrf_protect
def create_direct_join_meeting_api(request):
    """
    API endpoint specifically for creating DIRECT JOIN Zoom meetings
    This endpoint guarantees meetings that can be joined immediately without registration
    """
    if request.method == 'POST':
        try:
            # Parse request data
            data = json.loads(request.body) if request.content_type == 'application/json' else request.POST
            
            integration_id = data.get('integration_id')
            title = data.get('title')
            description = data.get('description', '')
            start_datetime_str = data.get('start_datetime')
            end_datetime_str = data.get('end_datetime')
            
            # Validate required fields
            if not all([integration_id, title, start_datetime_str, end_datetime_str]):
                return JsonResponse({
                    'success': False, 
                    'error': 'Missing required fields: integration_id, title, start_datetime, end_datetime'
                }, status=400)
            
            # Parse datetime strings
            try:
                start_datetime = datetime.datetime.fromisoformat(start_datetime_str.replace('Z', '+00:00'))
                end_datetime = datetime.datetime.fromisoformat(end_datetime_str.replace('Z', '+00:00'))
            except (ValueError, AttributeError) as e:
                return JsonResponse({
                    'success': False, 
                    'error': f'Invalid datetime format: {str(e)}'
                }, status=400)
            
            # Validate datetime logic
            if start_datetime >= end_datetime:
                return JsonResponse({
                    'success': False, 
                    'error': 'Start time must be before end time'
                }, status=400)
            
            # Create the direct join meeting
            result = create_direct_join_zoom_meeting(
                user=request.user,
                integration_id=integration_id,
                title=title,
                description=description,
                start_datetime=start_datetime,
                end_datetime=end_datetime
            )
            
            # Return the result
            if result['success']:
                logger.info(f"Successfully created direct join meeting for user {request.user.id}: {result['meeting_id']}")
                return JsonResponse(result)
            else:
                logger.error(f"Failed to create direct join meeting for user {request.user.id}: {result['error']}")
                return JsonResponse(result, status=400)
                
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False, 
                'error': 'Invalid JSON in request body'
            }, status=400)
        except Exception as e:
            logger.exception(f"Unexpected error in create_direct_join_meeting_api: {str(e)}")
            return JsonResponse({
                'success': False, 
                'error': f'Unexpected error: {str(e)}'
            }, status=500)
    
    return JsonResponse({'success': False, 'error': 'Only POST method allowed'}, status=405)

def create_teams_meeting(user, integration_id, title, description, start_datetime, end_datetime):
    """Create a Microsoft Teams meeting using the Microsoft Graph API"""
    try:
        # Get the integration - allow access to user's own integrations or branch integrations
        try:
            # First try to get user's own integration
            integration = TeamsIntegration.objects.get(id=integration_id, user=user)
        except TeamsIntegration.DoesNotExist:
            # If not found, try to get integration from same branch (excluding superadmin)
            if hasattr(user, 'branch') and user.branch:
                integration = TeamsIntegration.objects.exclude(user__role='superadmin').get(
                    id=integration_id, 
                    user__branch=user.branch, 
                    is_active=True
                )
            else:
                raise TeamsIntegration.DoesNotExist("Integration not found")
        
        # For testing, return a fake Teams meeting link
        # In production, this would call the Microsoft Graph API
        meeting_id = str(uuid.uuid4())
        return JsonResponse({
            'success': True,
            'meeting_link': f"https://teams.microsoft.com/l/meetup-join/{meeting_id}/0",
            'meeting_id': meeting_id,
        })
        
    except TeamsIntegration.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Integration not found'}, status=404)
    except Exception as e:
        logger.exception("Error creating Teams meeting")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)





def get_zoom_oauth_token(client_id, client_secret, account_id=None):
    """Get OAuth token for Zoom API using server-to-server OAuth"""
    try:
        # Encode credentials for Basic Auth
        credentials = f"{client_id}:{client_secret}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        
        # Set up the request
        url = "https://zoom.us/oauth/token"
        headers = {
            "Authorization": f"Basic {encoded_credentials}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        # For server-to-server OAuth, use account_credentials grant type
        data = {
            "grant_type": "account_credentials",
            "account_id": account_id or client_id.split("_")[0]  # Use provided account ID or try to extract from client ID
        }
        
        # Log the request details (without sensitive data)
        logger.info(f"Making OAuth token request to: {url}")
        logger.info(f"Using grant_type: {data['grant_type']}")
        logger.info(f"Using account_id: {data['account_id']}")
        
        # Make the request
        response = requests.post(url, headers=headers, data=data)
        
        # Log response
        logger.info(f"OAuth token response status: {response.status_code}")
        
        if response.status_code != 200:
            logger.error(f"Failed to get OAuth token: {response.status_code} - {response.text}")
            return None
             
        # Extract the token
        token_data = response.json()
        if 'access_token' not in token_data:
            logger.error(f"No access token in response: {response.text[:200]}")
            return None
             
        return token_data.get("access_token")
    except Exception as e:
        logger.exception(f"Error getting Zoom OAuth token: {str(e)}")
        return None

def create_zoom_meeting(user, integration_id, title, description, start_datetime, end_datetime):
    """Create a Zoom meeting using the Zoom API with direct join (no registration required)"""
    try:
        # Get the integration - allow access to user's own integrations or branch integrations
        try:
            # First try to get user's own integration
            integration = ZoomIntegration.objects.get(id=integration_id, user=user)
        except ZoomIntegration.DoesNotExist:
            # If not found, try to get integration from same branch (excluding superadmin)
            if hasattr(user, 'branch') and user.branch:
                integration = ZoomIntegration.objects.exclude(user__role='superadmin').get(
                    id=integration_id, 
                    user__branch=user.branch, 
                    is_active=True
                )
            else:
                raise ZoomIntegration.DoesNotExist("Integration not found")
        
        # Calculate meeting duration in minutes
        duration = int((end_datetime - start_datetime).total_seconds() / 60)
        
        # Format the start time for Zoom API (ISO format)
        # Use timezone-aware format without Z suffix (Zoom prefers this format)
        start_time = start_datetime.strftime('%Y-%m-%dT%H:%M:%S')
        
        # Log the integration details for debugging (without exposing sensitive data)
        logger.info(f"Using Zoom integration: id={integration.id}, account_id={integration.account_id}")
        
        # Check if using default credentials
        if integration.api_key == "your_zoom_api_key" or integration.api_secret == "your_zoom_api_secret":
            logger.error("Default Zoom credentials detected. Cannot create real meeting.")
            return JsonResponse({
                'success': False,
                'error': 'Please update your Zoom integration with valid API credentials in Account Settings.'
            }, status=400)
        
        # Generate OAuth token for Zoom API authentication
        # For server-to-server OAuth apps
        auth_token = get_zoom_oauth_token(integration.api_key, integration.api_secret, integration.account_id)
        if not auth_token:
            logger.error("Failed to obtain Zoom OAuth token")
            return JsonResponse({
                'success': False,
                'error': 'Could not authenticate with Zoom API. Please check your credentials in Account Settings.'
            }, status=401)
        
        # Determine the correct endpoint based on account_id
        # The account_id is crucial for the API to work properly
        account_id = integration.account_id
        
        # Try different account ID formats depending on what's available
        if not account_id or account_id.lower() == 'me':
            account_id = 'me'  # Default option
            logger.info("Using 'me' as the account ID")
        elif '@' in account_id:
            # It's an email address, which is valid
            logger.info(f"Using email {account_id} as account ID")
        else:
            # If not an email and not 'me', assume it's a user ID
            logger.info(f"Using {account_id} as account ID (assumed to be user ID)")
        
        # Zoom API endpoint
        api_url = f'https://api.zoom.us/v2/users/{account_id}/meetings'
        logger.info(f"Using Zoom API URL: {api_url}")
        
        # Prepare request headers
        headers = {
            'Authorization': f'Bearer {auth_token}',
            'Content-Type': 'application/json'
        }
        
        # Prepare request payload with enhanced settings for direct join WITHOUT registration
        # Type 3 = Recurring meeting with no fixed time (unlimited duration for Pro accounts)
        payload = {
            'topic': title,
            'type': 3,  # Recurring meeting with no fixed time (unlimited duration)
            'start_time': start_time,
            'duration': duration,  # Duration is for reference only, meeting won't auto-stop
            'timezone': 'UTC',
            'agenda': description,
            'password': f"{random.randint(100000, 999999)}",  # Generate 6-digit meeting passcode
            'recurrence': {
                'type': 1,  # Daily
                'repeat_interval': 1,  # Every day
                'end_times': 1  # Only one occurrence (makes it "no fixed time")
            },
            'settings': {
                # Basic video/audio settings
                'host_video': True,
                'participant_video': True,
                'join_before_host': True,
                'mute_upon_entry': False,
                'audio': 'both',
                
                #  CRITICAL: Direct join settings (NO REGISTRATION)
                'approval_type': 2,  # No registration required (2 = no registration)
                'registration_type': 0,  # No registration required
                'meeting_authentication': False,  # Allow guests without Zoom account
                'enforce_login': False,  # Don't require Zoom login
                'enforce_login_domains': '',  # No domain restrictions
                'waiting_room': False,  # Disable waiting room for immediate join
                
                #  Guest access settings
                'allow_multiple_devices': True,  # Allow multiple devices per participant
                'alternative_hosts': '',  # No alternative hosts restrictions
                'close_registration': False,  # Keep open (though registration is disabled)
                'show_share_button': True,  # Show share button for easy link sharing
                
                #  Cloud recording settings
                'auto_recording': 'cloud',  # Enable automatic cloud recording
                'cloud_recording': True,     # Explicit cloud recording
                'record_play_own_voice': True,  # Record participant audio
                'record_repeat_caller': True,   # Record all callers
                'recording_authentication': False,  # No auth required for recording access
                'recording_disclaimer': True,  # Show recording notice
                'auto_recording_local': False,  # Disable local recording
                'auto_recording_cloud': True,   # Enable cloud recording
                
                #  Additional accessibility settings
                'use_pmi': False,  # Don't use Personal Meeting ID
                'encryption_type': 'enhanced_encryption',  # Use enhanced encryption
                'breakout_room': False,  # Disable breakout rooms by default
                'global_dial_in_countries': ['US'],  # Allow dial-in from US
                
                #  Enhanced direct join settings
                'jbh_time': 10,  # Allow joining 10 minutes before host
                'cn_meeting': False,  # Don't restrict to China
                'in_meeting': False,  # Don't restrict to India
                'participant_video': True,  # Enable participant video by default
                'host_video': True,  # Enable host video by default
                
                #  Meeting controls that enhance accessibility
                'auto_recording': 'cloud',  # Ensure cloud recording
                'alternative_hosts_email_notification': False,  # Don't send notifications
                'focus_mode': False,  # Disable focus mode
                'private_meeting': False,  # Make meeting discoverable
                'internal_meeting': False,  # Not internal only
                
                #  Additional settings for easy access
                'contact_name': '',  # No contact name required
                'contact_email': '',  # No contact email required
                'registrants_confirmation_email': False,  # Don't send confirmation emails
                'registrants_email_notification': False,  # Don't send email notifications
                'request_permission_to_unmute_participants': False,
                'global_dial_in_numbers': [],  # Basic dial-in numbers
                'registrants_restriction_type': 0,  # No registration restrictions
                
                #  CHAT AND FILE SHARING SETTINGS
                'allow_participants_chat_with': 1,  # 1 = Everyone publicly and privately
                'allow_users_save_chats': 2,  # 2 = Everyone can save
                'chat_etiquette_tool': {
                    'enable': False,  # Don't restrict chat
                    'policies': []
                },
                'file_transfer': {
                    'enable': True,  # Enable file transfers in chat
                    'allow_all_file_types': True  # Allow all file types
                }
            }
        }
        
        # Make the API request to Zoom
        logger.info(f"Sending request to Zoom API for direct-join meeting with payload: {json.dumps(payload)}")
        response = requests.post(api_url, headers=headers, json=payload)
        
        # Log the response for debugging
        logger.info(f"Zoom API response status: {response.status_code}")
        logger.info(f"Zoom API response headers: {response.headers}")
        logger.info(f"Zoom API response content: {response.text[:500]}")  # Limit response text to 500 chars
        
        # Handle rate limiting
        if response.status_code == 429:
            logger.warning("Zoom API rate limit exceeded")
            return JsonResponse({
                'success': False, 
                'error': 'Zoom API rate limit exceeded. Please try again later.'
            }, status=429)
            
        # If unauthorized, try with different account ID formats
        if response.status_code == 401 or response.status_code == 404:
            logger.error(f"Authorization/Not Found error with account ID {account_id}: {response.text}")
            
            # Try alternative account IDs if we're not already using 'me'
            if account_id != 'me':
                logger.info("Trying alternative account ID: me")
                alt_api_url = 'https://api.zoom.us/v2/users/me/meetings'
                
                # Make alternative request
                alt_response = requests.post(alt_api_url, headers=headers, json=payload)
                logger.info(f"Alternative API call response: {alt_response.status_code}")
                
                if alt_response.status_code == 201 or alt_response.status_code == 200:
                    # If successful, use this response instead
                    response = alt_response
                    logger.info("Alternative API call successful")
                else:
                    logger.error(f"Alternative API call also failed: {alt_response.text}")
            
            # If still not successful, return error
            if response.status_code == 401 or response.status_code == 404:
                return JsonResponse({
                    'success': False,
                    'error': f'Unauthorized access to Zoom API or user not found. Please check your Zoom integration settings and verify your account ID and credentials.'
                }, status=401)
            
        # Handle other error responses
        if response.status_code >= 400:
            error_msg = f"Zoom API error (HTTP {response.status_code})"
            try:
                error_data = response.json()
                if 'message' in error_data:
                    error_msg = f"Zoom API: {error_data['message']}"
            except:
                pass
            
            logger.error(f"Zoom API error: {error_msg} - {response.text}")
            return JsonResponse({
                'success': False,
                'error': error_msg
            }, status=response.status_code)
        
        # Parse the JSON response
        meeting_data = response.json()
        
        # Ensure the join_url is a direct join URL (not registration URL)
        join_url = meeting_data.get('join_url')
        if join_url:
            # If it's a registration URL, convert it to direct join
            if 'register' in join_url:
                logger.info(f"Converting registration URL to direct join: {join_url}")
                join_url = convert_zoom_registration_to_direct_join(join_url)
                logger.info(f"Converted to direct join URL: {join_url}")
        
        # Return the meeting data with direct join URL
        result = {
            'success': True,
            'meeting_link': join_url,
            'meeting_id': meeting_data.get('id'),
            'password': meeting_data.get('password', ''),  # May be empty for no-password meetings
            'host_url': meeting_data.get('start_url'),
            'direct_join': True,  # Flag to indicate this is a direct join meeting
            'registration_required': False  # Flag to indicate no registration needed
        }
        
        logger.info(f"Successfully created direct-join Zoom meeting: ID={result['meeting_id']}, Join URL={result['meeting_link']}")
        return JsonResponse(result)
        
    except ZoomIntegration.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Integration not found'}, status=404)
    except requests.exceptions.RequestException as e:
        logger.exception(f"Error making Zoom API request: {str(e)}")
        if hasattr(e, 'response') and e.response:
            logger.error(f"Response from Zoom API: {e.response.text}")
        return JsonResponse({'success': False, 'error': f'Error connecting to Zoom API: {str(e)}'}, status=500)
    except Exception as e:
        logger.exception(f"Error creating Zoom meeting: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@login_required
@require_POST
def sync_conference_data(request, conference_id):
    """API endpoint to trigger conference data synchronization"""
    if request.user.role not in ['instructor', 'admin', 'superadmin', 'globaladmin'] and not request.user.is_superuser:
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)
    
    try:
        conference = get_object_or_404(Conference, id=conference_id)
    except:
        return JsonResponse({
            'success': False,
            'error': f'Conference with ID {conference_id} does not exist or has been deleted.'
        }, status=404)
    
    try:
        # Update sync status
        conference.data_sync_status = 'in_progress'
        conference.save()
        
        # Create sync log
        sync_log = ConferenceSyncLog.objects.create(
            conference=conference,
            sync_type='full',
            status='started'
        )
        
        # Sync data based on platform
        if conference.meeting_platform == 'zoom':
            result = sync_zoom_meeting_data(conference)
        elif conference.meeting_platform == 'teams':
            result = sync_teams_meeting_data(conference)
        else:
            result = {'success': False, 'error': 'Unsupported platform'}
        
        # Update sync log
        sync_log.status = 'completed' if result.get('success') else 'failed'
        sync_log.items_processed = result.get('items_processed', 0)
        sync_log.items_failed = result.get('items_failed', 0)
        sync_log.error_message = result.get('error')
        sync_log.platform_response = result.get('platform_response', {})
        sync_log.completed_at = timezone.now()
        sync_log.save()
        
        # Update conference sync status
        conference.data_sync_status = 'completed' if result.get('success') else 'failed'
        conference.last_sync_at = timezone.now()
        conference.save()
        
        return JsonResponse(result)
        
    except Exception as e:
        logger.exception(f"Error syncing conference data: {str(e)}")
        conference.data_sync_status = 'failed'
        conference.save()
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

def extract_meeting_id_from_any_zoom_url(url):
    """Extract meeting ID from any Zoom URL format"""
    if not url:
        return None
    
    # Common Zoom URL patterns
    patterns = [
        r'zoom\.us/j/(\d+)',  # Direct join: https://us06web.zoom.us/j/82984116776
        r'zoom\.us/w/(\d+)',  # Webinar: https://us06web.zoom.us/w/83995564187
        r'zoom\.us/wc/(\d+)',  # Web client: https://app.zoom.us/wc/81726154632/join
        r'zoom\.us/meeting/(\d+)',  # Alternative format
        r'/j/(\d+)',  # Just the /j/ part
        r'/w/(\d+)',  # Just the /w/ part (webinar)
        r'/wc/(\d+)',  # Just the /wc/ part (web client)
        r'meeting_id=(\d+)',  # Query parameter format
        r'(\d{10,12})',  # Any long number (meeting ID) - fallback
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    
    return None

def get_meeting_id_from_registration_url(registration_url):
    """Get meeting ID from Zoom registration URL by making API call"""
    # Extract registration ID from URL
    reg_match = re.search(r'zoom\.us/meeting/register/([A-Za-z0-9_-]+)', registration_url)
    if not reg_match:
        return None
    
    registration_id = reg_match.group(1)
    
    # For now, we'll try to extract from URL patterns or return None
    # In the future, this could make API calls to get meeting details
    logger.info(f"Found registration ID: {registration_id} - attempting alternative extraction")
    
    # Try to extract from query parameters in the URL
    meeting_id_match = re.search(r'meeting_id=(\d+)', registration_url)
    if meeting_id_match:
        return meeting_id_match.group(1)
    
    # If no meeting ID found, we'll need to use a different approach
    return None

def convert_zoom_registration_to_direct_join(registration_url):
    """Convert Zoom registration URL to direct join URL with enhanced handling"""
    if not registration_url or 'zoom.us' not in registration_url:
        return registration_url
    
    # Extract the domain from the original URL
    domain_match = re.search(r'(https?://[^/]+)', registration_url)
    domain = domain_match.group(1) if domain_match else 'https://zoom.us'
    
    logger.info(f"Starting conversion of registration URL: {registration_url}")
    
    # Try different methods to get meeting ID
    meeting_id = None
    
    # Method 1: Extract from URL patterns (existing numeric meeting IDs)
    meeting_id = extract_meeting_id_from_any_zoom_url(registration_url)
    if meeting_id:
        logger.info(f"Method 1 - Found meeting ID from URL patterns: {meeting_id}")
    
    # Method 2: Try to get from registration URL query parameters
    if not meeting_id:
        meeting_id = get_meeting_id_from_registration_url(registration_url)
        if meeting_id:
            logger.info(f"Method 2 - Found meeting ID from query parameters: {meeting_id}")
    
    # Method 3: Extract registration ID and try advanced decoding
    registration_id = None
    if not meeting_id:
        reg_match = re.search(r'zoom\.us/meeting/register/([A-Za-z0-9_-]+)', registration_url)
        if reg_match:
            registration_id = reg_match.group(1)
            logger.info(f"Found registration ID: {registration_id}")
            
            # Method 3a: Try base64 decoding with URL-safe characters
            try:
                import base64
                # Try different base64 variations
                for padding in ['', '=', '==', '===']:
                    try:
                        # Add URL-safe base64 decoding
                        decoded = base64.urlsafe_b64decode(registration_id + padding)
                        decoded_str = decoded.decode('utf-8', errors='ignore')
                        
                        # Look for numeric patterns in decoded data
                        numeric_match = re.search(r'(\d{9,12})', decoded_str)
                        if numeric_match:
                            meeting_id = numeric_match.group(1)
                            logger.info(f"Method 3a - Extracted meeting ID from URL-safe base64: {meeting_id}")
                            break
                            
                        # Also try standard base64
                        decoded = base64.b64decode(registration_id + padding)
                        decoded_str = decoded.decode('utf-8', errors='ignore')
                        numeric_match = re.search(r'(\d{9,12})', decoded_str)
                        if numeric_match:
                            meeting_id = numeric_match.group(1)
                            logger.info(f"Method 3a - Extracted meeting ID from standard base64: {meeting_id}")
                            break
                    except:
                        continue
            except Exception as e:
                logger.debug(f"Base64 decoding failed: {e}")
            
            # Method 3b: For complex registration IDs like "j8PvlJtOR7aAhUhdyYw-Cw"
            # Try to use the registration ID as meeting ID for direct join
            if not meeting_id:
                meeting_id = registration_id
                logger.info(f"Method 3b - Using registration ID directly as meeting ID: {meeting_id}")
    
    # Create simple direct join URL format
    if meeting_id:
        # Determine if this is a webinar or meeting based on registration URL and ID format
        is_webinar = ('webinar/register' in registration_url or 
                     (len(meeting_id) > 15 and not meeting_id.isdigit()))  # Non-numeric IDs are often webinars
        
        # Build simple direct join URL
        if is_webinar:
            direct_url = f"{domain}/w/{meeting_id}"  # Webinar format
            logger.info(f"Creating webinar join URL: {direct_url}")
        else:
            direct_url = f"{domain}/j/{meeting_id}"  # Meeting format
        
        # Extract password from the original URL if present
        password = None
        pwd_match = re.search(r'pwd=([^&]+)', registration_url)
        if pwd_match:
            password = pwd_match.group(1)
            logger.info(f"Found password in original URL: {password}")
        
        # Only add password parameter if we have one
        if password:
            direct_url += f"?pwd={password}"
        
        logger.info(f"SUCCESS: Converted registration URL to simple direct join: {registration_url} -> {direct_url}")
        return direct_url
    
    # Enhanced fallback methods for complex registration URLs
    if 'meeting/register' in registration_url:
        # Method 4: Extract registration ID and create simple URL
        reg_match = re.search(r'meeting/register/([A-Za-z0-9_-]+)', registration_url)
        if reg_match:
            reg_id = reg_match.group(1)
            logger.info(f"Method 4 - Using registration ID for fallback: {reg_id}")
            
            # Try simple conversion patterns
            conversion_attempts = [
                f"{domain}/j/{reg_id}",  # Direct join format
                f"{domain}/w/{reg_id}",  # Webinar format (if applicable)
            ]
            
            # Extract password from original URL if present
            password = None
            pwd_match = re.search(r'pwd=([^&]+)', registration_url)
            if pwd_match:
                password = pwd_match.group(1)
            
            for attempt_url in conversion_attempts:
                # Only add password if we have one
                if password:
                    attempt_url += f"?pwd={password}"
                
                logger.info(f"Method 4 - Trying simple conversion: {registration_url} -> {attempt_url}")
                return attempt_url  # Return first attempt
    
    # Method 5: Try to clean up existing URL by removing extra parameters
    if 'zoom.us/j/' in registration_url:
        # Extract meeting ID and password only
        meeting_id_match = re.search(r'/j/(\d+)', registration_url)
        password_match = re.search(r'pwd=([^&]+)', registration_url)
        
        if meeting_id_match:
            clean_url = f"{domain}/j/{meeting_id_match.group(1)}"
            if password_match:
                clean_url += f"?pwd={password_match.group(1)}"
            
            logger.info(f"Method 5 - Cleaned existing URL: {registration_url} -> {clean_url}")
            return clean_url
    
    # Method 6: Last resort - replace 'register' with 'join' in URL
    if '/meeting/register/' in registration_url:
        fallback_url = registration_url.replace('/meeting/register/', '/j/')
        # Extract only password parameter if present
        password_match = re.search(r'pwd=([^&]+)', registration_url)
        if password_match:
            # Clean URL and add only password
            base_url = fallback_url.split('?')[0]  # Remove all query parameters
            fallback_url = f"{base_url}?pwd={password_match.group(1)}"
        else:
            # Remove all query parameters for clean URL
            fallback_url = fallback_url.split('?')[0]
        
        logger.info(f"Method 6 - Last resort URL replacement: {registration_url} -> {fallback_url}")
        return fallback_url
    
    # If all else fails, return original URL with warning
    logger.warning(f"FAILED: Could not convert registration URL to direct join: {registration_url}")
    return registration_url

def parse_zoom_chat_content(chat_content, conference):
    """Parse Zoom chat file content and create chat message records"""
    import re  # Import at function level
    
    messages_processed = 0
    files_processed = 0
    
    try:
        chat_lines = chat_content.strip().split('\n')
        
        for line in chat_lines:
            line = line.strip()
            if not line or ':' not in line:
                continue
                
            try:
                # Parse Zoom chat format - handle multiple formats
                # Format 1: "HH:MM:SS From Sender Name to Everyone: Message content"
                # Format 2: "HH:MM:SS        Sender Name:    Message"
                
                # Check if it's the complex format with "From" and "to"
                if ' From ' in line and ' to ' in line:
                    # Original parsing logic for complex format
                    if ': ' in line:
                        timestamp_sender_part, message_text = line.split(': ', 1)
                    else:
                        continue
                    
                    # Extract timestamp (first part before "From")
                    timestamp_str = timestamp_sender_part.split(' From ')[0].strip()
                    
                    # Extract sender and recipient
                    from_to_part = timestamp_sender_part.split(' From ')[1]
                    if ' to ' in from_to_part:
                        sender_name = from_to_part.split(' to ')[0].strip()
                        recipient = from_to_part.split(' to ')[1].strip()
                    else:
                        continue
                        
                else:
                    # Simple format: "HH:MM:SS        Sender Name:    Message"
                    
                    # Match timestamp at the beginning
                    timestamp_match = re.match(r'^(\d{2}:\d{2}:\d{2})\s+', line)
                    if timestamp_match:
                        timestamp_str = timestamp_match.group(1)
                        # Remove timestamp from line
                        content_after_timestamp = line[len(timestamp_match.group(0)):]
                        
                        # Now split by colon to separate sender and message
                        if ':' in content_after_timestamp:
                            sender_name, message_text = content_after_timestamp.split(':', 1)
                            sender_name = sender_name.strip()
                            message_text = message_text.strip()
                            recipient = "Everyone"  # Default for simple format
                        else:
                            continue
                    else:
                        continue
                
                # Skip empty messages
                if not message_text or not sender_name:
                    continue
                
                # Check if this is a file share
                is_file_share = False
                filename = None
                file_url = None
                
                # Pattern 1: "File: filename.ext" or "Shared file: filename.ext"
                file_match = re.match(r'^(?:File|Shared file):\s*(.+)$', message_text, re.IGNORECASE)
                if file_match:
                    is_file_share = True
                    filename = file_match.group(1).strip()
                
                # Pattern 2: Message contains [filename.ext] 
                elif re.search(r'\[([^\]]+\.[a-zA-Z0-9]+)\]', message_text):
                    bracket_match = re.search(r'\[([^\]]+\.[a-zA-Z0-9]+)\]', message_text)
                    is_file_share = True
                    filename = bracket_match.group(1)
                
                # Pattern 3: Common file sharing phrases with filename
                elif any(phrase in message_text.lower() for phrase in ['uploaded', 'shared', 'sent a file', 'sent an image']):
                    # Try to extract filename from the message
                    filename_match = re.search(r'([^\s]+\.[a-zA-Z0-9]{2,4})(?:\s|$)', message_text)
                    if filename_match:
                        is_file_share = True
                        filename = filename_match.group(1)
                        
                # Pattern 4: Detect actual file uploads from Zoom chat export
                # Zoom often exports file uploads with specific formats
                elif re.search(r'(.*\.(jpg|jpeg|png|gif|bmp|pdf|doc|docx|ppt|pptx|xls|xlsx|txt|zip|rar))', message_text, re.IGNORECASE):
                    # Extract filename from message that contains file extensions
                    file_match = re.search(r'([^\s/\\]+\.(jpg|jpeg|png|gif|bmp|pdf|doc|docx|ppt|pptx|xls|xlsx|txt|zip|rar))', message_text, re.IGNORECASE)
                    if file_match:
                        is_file_share = True
                        filename = file_match.group(1)
                
                # Pattern 5: Detect file URLs or paths in messages
                elif re.search(r'(https?://[^\s]+\.(jpg|jpeg|png|gif|bmp|pdf|doc|docx|ppt|pptx|xls|xlsx|txt|zip|rar))', message_text, re.IGNORECASE):
                    url_match = re.search(r'(https?://[^\s]+\.(jpg|jpeg|png|gif|bmp|pdf|doc|docx|ppt|pptx|xls|xlsx|txt|zip|rar))', message_text, re.IGNORECASE)
                    if url_match:
                        is_file_share = True
                        file_url = url_match.group(1)
                        filename = file_url.split('/')[-1]  # Extract filename from URL
                
                # Pattern 6: Detect empty or minimal messages that might be file uploads
                # Sometimes Zoom exports file uploads with minimal text content
                elif len(message_text.strip()) < 10 and any(ext in message_text.lower() for ext in ['.jpg', '.jpeg', '.png', '.gif', '.pdf', '.doc', '.docx']):
                    is_file_share = True
                    filename = f"uploaded_file_{timestamp_str.replace(':', '')}.unknown"
                    
                # Pattern 7: Check if message text is very short and might be a file upload indicator
                elif message_text.strip() in ['', 'File', 'Image', 'Document', 'Upload'] or len(message_text.strip()) < 3:
                    # This might be a file upload with minimal text description
                    # Generate a filename based on timestamp and sender
                    is_file_share = True
                    filename = f"shared_file_{sender_name.replace(' ', '_')}_{timestamp_str.replace(':', '')}.unknown"
                    
                # Enhanced sender matching with LMS user
                sender_user = None
                if sender_name and len(sender_name) > 2:
                    # Method 0: Check if this is the instructor
                    instructor = conference.created_by
                    instructor_full_name = instructor.get_full_name()
                    instructor_variations = [
                        instructor_full_name,
                        f"{instructor.first_name} {instructor.last_name}",
                        instructor.username,
                        instructor.first_name,
                        instructor.last_name
                    ]
                    
                    # Check if this might be the instructor with EXACT matching only
                    for variation in instructor_variations:
                        if variation and len(variation) > 3:  # Only match if variation is longer than 3 chars
                            # Use EXACT matching only to avoid false positives
                            if variation.lower().strip() == sender_name.lower().strip():
                                sender_user = instructor
                                logger.info(f"Matched chat sender {sender_name} as INSTRUCTOR: {instructor.username}")
                                break
                    
                    if not sender_user:
                        # Method 1: Try exact full name match first (prioritize branch users)
                        name_parts = sender_name.split()
                        if len(name_parts) >= 2:
                            # First try within the same branch
                            exact_match = User.objects.filter(
                                Q(first_name__iexact=name_parts[0]) & 
                                Q(last_name__iexact=name_parts[-1]),
                                branch=conference.created_by.branch
                            ).first()
                            
                            # If no match in branch, try globally
                            if not exact_match:
                                exact_match = User.objects.filter(
                                    Q(first_name__iexact=name_parts[0]) & 
                                    Q(last_name__iexact=name_parts[-1])
                                ).first()
                            
                            if exact_match:
                                sender_user = exact_match
                                logger.info(f"Matched chat sender {sender_name} via exact name: {exact_match.username}")
                        
                        # Method 1.5: Try exact display name match for common patterns
                        if not sender_user:
                            # Check for patterns like "Instructor1 Branch1", "Learner1 Branch1"
                            potential_users = User.objects.filter(branch=conference.created_by.branch)
                            for user in potential_users:
                                user_full_name = user.get_full_name()
                                if user_full_name and user_full_name.lower().strip() == sender_name.lower().strip():
                                    sender_user = user
                                    logger.info(f"Matched chat sender {sender_name} via exact display name: {user.username}")
                                    break
                        
                        if not sender_user:
                            # Method 2: Try matching with attendees of this conference
                            conference_attendees = User.objects.filter(
                                conference_attendances__conference=conference
                            )
                            
                            # Check if sender name matches any attendee's stored name
                            for attendee in conference_attendees:
                                attendee_full_name = attendee.get_full_name()
                                if attendee_full_name and sender_name.lower() == attendee_full_name.lower():
                                    sender_user = attendee
                                    break
                            
                            # Method 3: Fallback to partial matching
                            if not sender_user and len(name_parts) >= 2:
                                potential_users = User.objects.filter(
                                    Q(first_name__icontains=name_parts[0]) |
                                    Q(last_name__icontains=name_parts[-1]) |
                                    Q(username__icontains=sender_name.replace(' ', ''))
                                )
                                
                                if potential_users.count() == 1:
                                    sender_user = potential_users.first()
                
                # Handle file shares
                if is_file_share and filename:
                    # Create chat message of type 'file'
                    chat_message, created = ConferenceChat.objects.get_or_create(
                        conference=conference,
                        sender_name=sender_name,
                        message_text=f"Shared file: {filename}",
                        defaults={
                            'sender': sender_user,
                            'sent_at': conference.created_at,  # Fallback timestamp
                            'message_type': 'file',  # Mark as file type
                            'metadata': {
                                'filename': filename,
                                'recipient': recipient,
                                'timestamp_str': timestamp_str,
                                'original_message': message_text,
                                'parse_source': 'zoom_chat_file'
                            }
                        }
                    )
                    
                    if created:
                        messages_processed += 1
                        logger.info(f"Created file share chat message for: {filename}")
                    
                    # Create ConferenceFile record
                    # Extract file extension
                    file_parts = filename.rsplit('.', 1)
                    file_extension = file_parts[1].lower() if len(file_parts) > 1 else 'unknown'
                    
                    # Determine MIME type based on extension
                    mime_types = {
                        'jpg': 'image/jpeg', 'jpeg': 'image/jpeg',
                        'png': 'image/png', 'gif': 'image/gif',
                        'pdf': 'application/pdf',
                        'doc': 'application/msword', 'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                        'xls': 'application/vnd.ms-excel', 'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                        'ppt': 'application/vnd.ms-powerpoint', 'pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
                        'txt': 'text/plain', 'csv': 'text/csv',
                        'zip': 'application/zip', 'rar': 'application/x-rar-compressed'
                    }
                    mime_type = mime_types.get(file_extension, 'application/octet-stream')
                    
                    conference_file, file_created = ConferenceFile.objects.get_or_create(
                        conference=conference,
                        filename=filename,
                        shared_by=sender_user or conference.created_by,  # Default to meeting creator
                        defaults={
                            'original_filename': filename,
                            'file_type': file_extension,
                            'mime_type': mime_type,
                            'shared_at': conference.created_at,  # Use conference time as fallback
                            'file_size': 0,  # Unknown from chat
                            'file_url': file_url,  # Use extracted URL if available
                        }
                    )
                    
                    if file_created:
                        files_processed += 1
                        logger.info(f"Created ConferenceFile record for: {filename}")
                
                else:
                    # Regular text message
                    chat_message, created = ConferenceChat.objects.get_or_create(
                        conference=conference,
                        sender_name=sender_name,
                        message_text=message_text,
                        defaults={
                            'sender': sender_user,
                            'sent_at': conference.created_at,  # Fallback timestamp
                            'message_type': 'text',
                            'metadata': {
                                'recipient': recipient,
                                'timestamp_str': timestamp_str,
                                'parse_source': 'zoom_chat_file'
                            }
                        }
                    )
                    
                    if created:
                        messages_processed += 1
                        logger.info(f"Created chat message from {sender_name}: {message_text[:50]}...")
                        
            except Exception as line_error:
                logger.warning(f"Could not parse chat line: {line[:100]}... - {line_error}")
                continue
                
    except Exception as e:
        logger.error(f"Error parsing chat content: {str(e)}")
    
    # Log summary
    logger.info(f"Chat parsing complete - Messages: {messages_processed}, Files: {files_processed}")
    return messages_processed + files_processed


def sync_zoom_meeting_data(conference):
    """Sync meeting data from Zoom API"""
    try:
        # Get user's Zoom integration (first check user's own integrations)
        zoom_integration = ZoomIntegration.objects.filter(
            user=conference.created_by,
            is_active=True
        ).first()
        
        # If no user integration found, check for branch integrations
        if not zoom_integration and hasattr(conference.created_by, 'branch') and conference.created_by.branch:
            zoom_integration = ZoomIntegration.objects.filter(
                user__branch=conference.created_by.branch,
                is_active=True
            ).exclude(user=conference.created_by).first()
            
            if zoom_integration:
                logger.info(f"Using branch Zoom integration from {zoom_integration.user.username} for conference {conference.id}")
        
        if not zoom_integration:
            return {
                'success': False,
                'error': 'No active Zoom integration found. Please configure and activate your Zoom integration in Account Settings → Integrations → Zoom, or ask your branch admin to set up integration.',
                'items_processed': 0,
                'items_failed': 0
            }
        
        # Extract meeting ID if not present
        if not conference.meeting_id and conference.meeting_link:
            extracted_id = extract_meeting_id_from_any_zoom_url(conference.meeting_link)
            if extracted_id:
                conference.meeting_id = extracted_id
                conference.save(update_fields=['meeting_id'])
                logger.info(f"Extracted and saved meeting ID {extracted_id} for conference {conference.id}")
        
        if not conference.meeting_id:
            return {
                'success': False,
                'error': 'No meeting ID available. Cannot sync data without meeting ID.',
                'items_processed': 0,
                'items_failed': 0
            }
        
        # Get OAuth token
        access_token = get_zoom_oauth_token(
            zoom_integration.api_key, 
            zoom_integration.api_secret, 
            zoom_integration.account_id
        )
        
        if not access_token:
            return {
                'success': False,
                'error': 'Failed to authenticate with Zoom API. Please check your credentials.',
                'items_processed': 0,
                'items_failed': 0
            }
        
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        
        total_items_processed = 0
        total_items_failed = 0
        platform_response = {}
        
        # 1. Sync Recordings
        try:
            recordings_url = f"https://api.zoom.us/v2/meetings/{conference.meeting_id}/recordings"
            logger.info(f"Fetching recordings from: {recordings_url}")
            
            # Use robust API call with retry logic
            from conferences.utils.sync_resilience import robust_api_call
            recordings_response = robust_api_call(recordings_url, headers)
            
            if recordings_response.status_code == 200:
                recordings_data = recordings_response.json()
                recordings_processed = 0
                
                if 'recording_files' in recordings_data:
                    for recording_file in recordings_data['recording_files']:
                        try:
                            # Calculate duration in minutes
                            duration_minutes = 0
                            if recording_file.get('recording_start') and recording_file.get('recording_end'):
                                try:
                                    from dateutil.parser import parse
                                    start_time = parse(recording_file['recording_start'])
                                    end_time = parse(recording_file['recording_end'])
                                    duration_seconds = (end_time - start_time).total_seconds()
                                    duration_minutes = int(duration_seconds // 60)
                                except Exception as e:
                                    logger.warning(f"Could not parse recording duration: {e}")
                                    duration_minutes = 0
                            
                            # Determine recording type based on file type and recording type
                            recording_type = 'cloud'
                            file_type = recording_file.get('file_type', '').upper()
                            zoom_recording_type = recording_file.get('recording_type', '').lower()
                            
                            if file_type == 'M4A' or zoom_recording_type == 'audio_only':
                                recording_type = 'audio_only'
                            elif 'shared_screen' in zoom_recording_type:
                                recording_type = 'shared_screen'
                            # Note: chat_file and other special types will be stored as 'cloud' type
                            # but can be identified by their title/recording_type in the template
                            
                            # Extract recording password - recordings can have different passwords than meetings
                            recording_password = recording_file.get('password') or recording_file.get('play_passcode')
                            
                            # Check if recording is password protected
                            password_protected = bool(recording_password) or recording_file.get('password_protected', False)
                            
                            # Create or update recording
                            recording, created = ConferenceRecording.objects.get_or_create(
                                conference=conference,
                                recording_id=recording_file.get('id', f"zoom_{conference.meeting_id}_{recordings_processed}"),
                                defaults={
                                    'title': recording_file.get('recording_type', 'Meeting Recording'),
                                    'recording_type': recording_type,
                                    'file_url': recording_file.get('download_url'),
                                    'file_size': recording_file.get('file_size', 0),
                                    'duration_minutes': duration_minutes,
                                    'file_format': recording_file.get('file_extension', 'mp4').lower(),
                                    'download_url': recording_file.get('download_url'),
                                    'password_protected': password_protected,
                                    'recording_password': recording_password,
                                    'status': 'available' if recording_file.get('status') == 'completed' else 'processing'
                                }
                            )
                            
                            if not created:
                                # Update existing recording
                                recording.file_url = recording_file.get('download_url')
                                recording.file_size = recording_file.get('file_size', 0)
                                recording.status = 'available' if recording_file.get('status') == 'completed' else 'processing'
                                recording.password_protected = password_protected
                                recording.recording_password = recording_password
                                recording.save()
                            
                            recordings_processed += 1
                            logger.info(f"Processed recording: {recording_file.get('recording_type')} - {recording_file.get('file_size', 0)} bytes")
                            
                            # Special handling for chat files - extract chat data
                            if zoom_recording_type == 'chat_file' and recording_file.get('download_url'):
                                try:
                                    # Attempt to download and parse chat file
                                    chat_response = requests.get(recording_file['download_url'], headers=headers)
                                    if chat_response.status_code == 200:
                                        # Parse chat content (Zoom chat files are typically in text format)
                                        chat_content = chat_response.text
                                        chat_lines = chat_content.strip().split('\n')
                                        
                                        chat_processed = 0
                                        for line in chat_lines:
                                            if line.strip() and ':' in line:
                                                try:
                                                    # Parse format: "HH:MM:SS From Name to Everyone: Message"
                                                    parts = line.split(': ', 1)
                                                    if len(parts) == 2:
                                                        timestamp_sender = parts[0]
                                                        message_text = parts[1]
                                                        
                                                        # Extract sender name (simplified parsing)
                                                        if ' From ' in timestamp_sender and ' to ' in timestamp_sender:
                                                            sender_part = timestamp_sender.split(' From ')[1].split(' to ')[0]
                                                            
                                                            # Create chat message
                                                            ConferenceChat.objects.get_or_create(
                                                                conference=conference,
                                                                sender_name=sender_part,
                                                                message_text=message_text,
                                                                defaults={
                                                                    'sent_at': conference.created_at,  # Fallback timestamp
                                                                    'message_type': 'text'
                                                                }
                                                            )
                                                            chat_processed += 1
                                                except Exception as chat_parse_error:
                                                    logger.warning(f"Could not parse chat line: {line[:50]}... - {chat_parse_error}")
                                        
                                        if chat_processed > 0:
                                            logger.info(f"Extracted {chat_processed} chat messages from chat file")
                                        
                                except Exception as chat_error:
                                    logger.warning(f"Could not process chat file: {chat_error}")
                                
                                # Update platform response to reflect chat processing
                                if 'chat' not in platform_response:
                                    platform_response['chat'] = {'status': 'info', 'items_processed': 0, 'message': ''}
                                platform_response['chat']['status'] = 'success'
                                platform_response['chat']['message'] = f'Extracted chat messages from recording file'
                            
                        except Exception as e:
                            logger.error(f"Error processing recording file: {str(e)}")
                            total_items_failed += 1
                
                total_items_processed += recordings_processed
                platform_response['recordings'] = {
                    'status': 'success',
                    'items_processed': recordings_processed,
                    'message': f'Found {recordings_processed} recordings'
                }
                
            elif recordings_response.status_code == 404:
                platform_response['recordings'] = {
                    'status': 'no_data',
                    'items_processed': 0,
                    'message': 'No recordings found for this meeting'
                }
            else:
                # Try to parse response even if not 200, sometimes recordings are there
                try:
                    recordings_data = recordings_response.json()
                    if 'recording_files' in recordings_data and recordings_data['recording_files']:
                        # Process recordings even if status code is not 200
                        recordings_processed = 0
                        for recording_file in recordings_data['recording_files']:
                            try:
                                # Simple duration calculation
                                duration_minutes = 0
                                if recording_file.get('recording_start') and recording_file.get('recording_end'):
                                    try:
                                        from dateutil.parser import parse
                                        start_time = parse(recording_file['recording_start'])
                                        end_time = parse(recording_file['recording_end'])
                                        duration_seconds = (end_time - start_time).total_seconds()
                                        duration_minutes = int(duration_seconds // 60)
                                    except:
                                        duration_minutes = 0
                                
                                # Simple recording type detection
                                recording_type = 'cloud'
                                zoom_recording_type = recording_file.get('recording_type', '').lower()
                                if 'audio' in zoom_recording_type:
                                    recording_type = 'audio_only'
                                elif 'shared' in zoom_recording_type:
                                    recording_type = 'shared_screen'
                                
                                # Create recording record
                                recording, created = ConferenceRecording.objects.get_or_create(
                                    conference=conference,
                                    recording_id=recording_file.get('id', f"zoom_{conference.meeting_id}_{recordings_processed}"),
                                    defaults={
                                        'title': recording_file.get('recording_type', 'Meeting Recording'),
                                        'recording_type': recording_type,
                                        'file_url': recording_file.get('download_url'),
                                        'file_size': recording_file.get('file_size', 0),
                                        'duration_minutes': duration_minutes,
                                        'file_format': recording_file.get('file_extension', 'mp4').lower(),
                                        'download_url': recording_file.get('download_url'),
                                        'password_protected': bool(recording_file.get('password') or recording_file.get('play_passcode')),
                                        'recording_password': recording_file.get('password') or recording_file.get('play_passcode'),
                                        'status': 'available' if recording_file.get('status') == 'completed' else 'processing'
                                    }
                                )
                                
                                if not created:
                                    recording.file_url = recording_file.get('download_url')
                                    recording.file_size = recording_file.get('file_size', 0)
                                    recording.status = 'available' if recording_file.get('status') == 'completed' else 'processing'
                                    recording.save()
                                
                                recordings_processed += 1
                                
                                # Handle chat files
                                if zoom_recording_type == 'chat_file' and recording_file.get('download_url'):
                                    try:
                                        chat_response = requests.get(recording_file['download_url'], headers=headers)
                                        if chat_response.status_code == 200:
                                            chat_content = chat_response.text
                                            parsed_messages = parse_zoom_chat_content(chat_content, conference)
                                            logger.info(f"Processed {parsed_messages} chat messages from chat file")
                                    except Exception as e:
                                        logger.warning(f"Could not process chat file: {e}")
                                
                            except Exception as e:
                                logger.error(f"Error processing recording file: {str(e)}")
                        
                        total_items_processed += recordings_processed
                        platform_response['recordings'] = {
                            'status': 'success',
                            'items_processed': recordings_processed,
                            'message': f'Found {recordings_processed} recordings'
                        }
                    else:
                        platform_response['recordings'] = {
                            'status': 'no_data',
                            'items_processed': 0,
                            'message': 'No recordings found for this meeting'
                        }
                except Exception as e:
                    logger.error(f"Error parsing recordings response: {str(e)}")
                    platform_response['recordings'] = {
                        'status': 'error',
                        'items_processed': 0,
                        'message': f'API Error: {recordings_response.status_code}'
                    }
                    total_items_failed += 1
                
        except Exception as e:
            logger.error(f"Exception while syncing recordings: {str(e)}")
            platform_response['recordings'] = {
                'status': 'error',
                'items_processed': 0,
                'message': f'Exception: {str(e)}'
            }
            total_items_failed += 1
        
        # 2. Sync Participants (for attendance) - Enhanced participant matching
        try:
            # Use the report API for better participant data with multiple sessions
            participants_url = f"https://api.zoom.us/v2/report/meetings/{conference.meeting_id}/participants"
            logger.info(f"Fetching detailed participants from: {participants_url}")
            
            # Use robust API call with retry logic
            participants_response = robust_api_call(participants_url, headers)
            
            if participants_response.status_code == 200:
                participants_data = participants_response.json()
                participants_processed = 0
                
                if 'participants' in participants_data:
                    for participant in participants_data['participants']:
                        try:
                            # Enhanced user matching logic
                            user = None
                            zoom_participant_id = participant.get('id', '')
                            participant_name = participant.get('name', '').strip()
                            participant_email = participant.get('user_email', '').strip()
                            
                            # Method 1: Check if we have a ConferenceParticipant record with matching Zoom participant ID
                            if zoom_participant_id:
                                try:
                                    conference_participant = ConferenceParticipant.objects.filter(
                                        conference=conference,
                                        platform_participant_id=zoom_participant_id
                                    ).first()
                                    if conference_participant and conference_participant.user:
                                        user = conference_participant.user
                                        logger.info(f"Matched participant {participant_name} via platform participant ID -> User: {user.username}")
                                except Exception as e:
                                    logger.warning(f"Error matching via platform participant ID: {str(e)}")
                            
                            # Method 1.5: Check if this is the instructor with a different name
                            if not user and participant_name:
                                instructor = conference.created_by
                                instructor_full_name = instructor.get_full_name()
                                instructor_variations = [
                                    instructor_full_name,
                                    f"{instructor.first_name} {instructor.last_name}",
                                    instructor.username,
                                    instructor.first_name,
                                    instructor.last_name
                                ]
                                
                                # Check if this might be the instructor with a variation
                                for variation in instructor_variations:
                                    if variation and (
                                        variation.lower() in participant_name.lower() or 
                                        participant_name.lower() in variation.lower() or
                                        (len(variation) > 3 and variation.lower()[:4] in participant_name.lower())
                                    ):
                                        user = instructor
                                        logger.info(f"Matched participant {participant_name} as INSTRUCTOR: {user.username}")
                                        break
                            
                            # Method 2: Try to extract LMS username from participant name if it contains it
                            if not user and participant_name:
                                # Check if name contains LMS username pattern (e.g., "John Doe (jdoe)")
                                import re
                                username_match = re.search(r'\(([a-zA-Z0-9_.-]+)\)$', participant_name)
                                if username_match:
                                    potential_username = username_match.group(1)
                                    try:
                                        user = User.objects.get(username=potential_username, branch=conference.created_by.branch)
                                        logger.info(f"Matched participant {participant_name} via username in name -> User: {user.username}")
                                    except User.DoesNotExist:
                                        pass
                            
                            # Method 3: Try to match by email
                            if not user and participant_email:
                                user = User.objects.filter(email__iexact=participant_email).first()
                                if user:
                                    logger.info(f"Matched participant {participant_name} via email: {participant_email} -> User: {user.username}")
                            
                            # Method 4: If no email match, try existing attendance records with pre-registration data
                            if not user:
                                # Check if we have a pre-registered attendance record that matches
                                # Use database-agnostic approach for JSON field lookup
                                existing_attendances = ConferenceAttendance.objects.filter(
                                    conference=conference
                                )
                                
                                # Filter in Python to avoid database-specific JSON operations
                                matching_attendances = []
                                first_name_part = participant_name.split()[0] if participant_name else ''
                                
                                for attendance in existing_attendances:
                                    device_info = attendance.device_info or {}
                                    lms_full_name = device_info.get('lms_full_name', '')
                                    if first_name_part and first_name_part.lower() in lms_full_name.lower():
                                        matching_attendances.append(attendance)
                                
                                for attendance in matching_attendances:
                                    stored_name = attendance.device_info.get('lms_full_name', '')
                                    stored_email = attendance.device_info.get('lms_email', '')
                                    
                                    # Match by stored email or name similarity
                                    if (participant_email and stored_email.lower() == participant_email.lower()) or \
                                       (participant_name and stored_name.lower() in participant_name.lower()):
                                        user = attendance.user
                                        logger.info(f"Matched participant {participant_name} via pre-registration data -> User: {user.username}")
                                        break
                            
                            # Method 5: Enhanced fuzzy name matching for existing users
                            if not user and participant_name:
                                name_parts = participant_name.split()
                                if len(name_parts) >= 2:
                                    first_name = name_parts[0]
                                    last_name = name_parts[-1]
                                    
                                    # Method 5a: Exact first + last name match within branch
                                    if conference.created_by.branch:
                                        branch_users = User.objects.filter(
                                            branch=conference.created_by.branch,
                                            first_name__iexact=first_name,
                                            last_name__iexact=last_name
                                        )
                                        if branch_users.count() == 1:
                                            user = branch_users.first()
                                            logger.info(f"Matched participant {participant_name} via exact branch name match -> User: {user.username}")
                                    
                                    # Method 5b: Partial match within branch (prioritize learners)
                                    if not user and conference.created_by.branch:
                                        branch_learners = User.objects.filter(
                                            branch=conference.created_by.branch,
                                            role='learner',
                                            first_name__icontains=first_name,
                                            last_name__icontains=last_name
                                        )
                                        if branch_learners.count() == 1:
                                            user = branch_learners.first()
                                            logger.info(f"Matched participant {participant_name} via branch learner match -> User: {user.username}")
                                        elif branch_learners.count() > 1:
                                            # Try more specific matching for multiple matches
                                            for learner in branch_learners:
                                                learner_full = f"{learner.first_name} {learner.last_name}"
                                                if learner_full.lower() == participant_name.lower():
                                                    user = learner
                                                    logger.info(f"Matched participant {participant_name} via exact learner name -> User: {user.username}")
                                                    break
                                    
                                    # Method 5c: Try common name variations
                                    if not user:
                                        name_variations = []
                                        # Common first name variations
                                        first_variations = [first_name]
                                        if first_name.lower() in ['mike', 'michael']:
                                            first_variations.extend(['Mike', 'Michael'])
                                        elif first_name.lower() in ['tom', 'thomas']:
                                            first_variations.extend(['Tom', 'Thomas'])
                                        elif first_name.lower() in ['bob', 'robert']:
                                            first_variations.extend(['Bob', 'Robert'])
                                        elif first_name.lower() in ['jim', 'james']:
                                            first_variations.extend(['Jim', 'James'])
                                        elif first_name.lower() in ['bill', 'william']:
                                            first_variations.extend(['Bill', 'William'])
                                        elif first_name.lower() in ['dave', 'david']:
                                            first_variations.extend(['Dave', 'David'])
                                        elif first_name.lower() in ['steve', 'steven']:
                                            first_variations.extend(['Steve', 'Steven'])
                                        
                                        for first_var in first_variations:
                                            potential_users = User.objects.filter(
                                                branch=conference.created_by.branch if conference.created_by.branch else None,
                                                first_name__iexact=first_var,
                                                last_name__iexact=last_name
                                            )
                                            if potential_users.count() == 1:
                                                user = potential_users.first()
                                                logger.info(f"Matched participant {participant_name} via name variation ({first_var}) -> User: {user.username}")
                                                break
                                    
                                    # Method 5d: Enhanced fuzzy matching with similarity scoring
                                    if not user:
                                        potential_users = User.objects.filter(
                                            first_name__icontains=first_name,
                                            last_name__icontains=last_name
                                        )
                                        if conference.created_by.branch:
                                            potential_users = potential_users.filter(branch=conference.created_by.branch)
                                        
                                        if potential_users.count() == 1:
                                            user = potential_users.first()
                                            logger.info(f" FIX #2: Matched participant {participant_name} via enhanced fuzzy match -> User: {user.username}")
                                        elif potential_users.count() > 1:
                                            # Use similarity scoring to find best match
                                            best_match = None
                                            best_score = 0
                                            for potential_user in potential_users:
                                                full_name = f"{potential_user.first_name} {potential_user.last_name}"
                                                # Simple similarity scoring
                                                score = 0
                                                if potential_user.first_name.lower() == first_name.lower():
                                                    score += 50
                                                if potential_user.last_name.lower() == last_name.lower():
                                                    score += 50
                                                # Check if participant email matches user email
                                                if participant_email and potential_user.email.lower() == participant_email.lower():
                                                    score += 100  # Email match is strongest indicator
                                                # Bonus for exact full name match
                                                if full_name.lower() == participant_name.lower():
                                                    score += 75
                                                
                                                if score > best_score:
                                                    best_score = score
                                                    best_match = potential_user
                                            
                                            if best_match and best_score >= 100:  # Require high confidence match
                                                user = best_match
                                                logger.info(f" FIX #2: Matched participant {participant_name} via similarity scoring (score: {best_score}) -> User: {user.username}")
                                    
                                    # Method 5e: Try matching by display name patterns (handles "FirstName LastName (email)")
                                    if not user and '(' in participant_name and ')' in participant_name:
                                        # Extract name from "FirstName LastName (email@domain.com)" format
                                        name_part = participant_name.split('(')[0].strip()
                                        if name_part:
                                            name_parts = name_part.split()
                                            if len(name_parts) >= 2:
                                                clean_first = name_parts[0]
                                                clean_last = name_parts[-1]
                                                
                                                potential_users = User.objects.filter(
                                                    first_name__iexact=clean_first,
                                                    last_name__iexact=clean_last
                                                )
                                                if conference.created_by.branch:
                                                    potential_users = potential_users.filter(branch=conference.created_by.branch)
                                                
                                                if potential_users.count() == 1:
                                                    user = potential_users.first()
                                                    logger.info(f" FIX #2: Matched participant via parenthetical name pattern -> User: {user.username}")
                            
                            # Method 6: Try matching by initials (e.g., "J. Smith" -> "John Smith")
                            if not user and participant_name:
                                import re
                                initial_pattern = re.match(r'^([A-Z])\.\s+(.+)$', participant_name)
                                if initial_pattern:
                                    initial = initial_pattern.group(1)
                                    last_name = initial_pattern.group(2)
                                    
                                    potential_users = User.objects.filter(
                                        first_name__istartswith=initial,
                                        last_name__iexact=last_name
                                    )
                                    if conference.created_by.branch:
                                        potential_users = potential_users.filter(branch=conference.created_by.branch)
                                    
                                    if potential_users.count() == 1:
                                        user = potential_users.first()
                                        logger.info(f"Matched participant {participant_name} via initial pattern -> User: {user.username}")
                            
                            # Method 7: Try reverse name order (e.g., "Smith, John" -> "John Smith")
                            if not user and participant_name and ',' in participant_name:
                                parts = participant_name.split(',')
                                if len(parts) == 2:
                                    last_name = parts[0].strip()
                                    first_name = parts[1].strip()
                                    
                                    potential_users = User.objects.filter(
                                        first_name__iexact=first_name,
                                        last_name__iexact=last_name
                                    )
                                    if conference.created_by.branch:
                                        potential_users = potential_users.filter(branch=conference.created_by.branch)
                                    
                                    if potential_users.count() == 1:
                                        user = potential_users.first()
                                        logger.info(f"Matched participant {participant_name} via reverse name order -> User: {user.username}")
                            
                            # Process the participant data
                            if user:
                                # Parse timestamps with proper timezone handling
                                join_time = None
                                leave_time = None
                                
                                if participant.get('join_time'):
                                    try:
                                        join_time = timezone.datetime.fromisoformat(participant['join_time'].replace('Z', '+00:00'))
                                    except:
                                        logger.warning(f"Could not parse join_time: {participant.get('join_time')}")
                                
                                if participant.get('leave_time'):
                                    try:
                                        leave_time = timezone.datetime.fromisoformat(participant['leave_time'].replace('Z', '+00:00'))
                                    except:
                                        logger.warning(f"Could not parse leave_time: {participant.get('leave_time')}")
                                
                                # Calculate attendance status based on join/leave times and duration
                                duration_minutes = participant.get('duration', 0) // 60 if participant.get('duration') else 0
                                
                                # Determine attendance status
                                attendance_status = 'present'
                                if duration_minutes < 5:  # Less than 5 minutes
                                    attendance_status = 'absent'
                                elif join_time and conference.start_time:
                                    # Check if joined late (more than 15 minutes after start)
                                    conference_start = timezone.datetime.combine(conference.date, conference.start_time)
                                    if conference_start.tzinfo is None:
                                        conference_start = timezone.make_aware(conference_start)
                                    
                                    if join_time > conference_start + timezone.timedelta(minutes=15):
                                        attendance_status = 'late'
                                
                                # Enhanced logging for learner matching success
                                logger.info(f" LEARNER SYNC SUCCESS: {participant_name} -> {user.username} ({user.role}) | Duration: {duration_minutes}min | Status: {attendance_status}")
                                if user.role == 'learner':
                                    logger.info(f"🎯 LEARNER DETAILS: User ID={user.id}, Email={user.email}, Join={join_time}, Leave={leave_time}")
                                
                                # Create or update ConferenceAttendance record
                                attendance, created = ConferenceAttendance.objects.get_or_create(
                                    conference=conference,
                                    user=user,
                                    defaults={
                                        'participant_id': zoom_participant_id,
                                        'join_time': join_time,
                                        'leave_time': leave_time,
                                        'duration_minutes': duration_minutes,
                                        'attendance_status': attendance_status,
                                        'device_info': {
                                            'zoom_participant_id': zoom_participant_id,
                                            'zoom_participant_name': participant_name,
                                            'zoom_participant_email': participant_email,
                                            'user_type': participant.get('user_type', ''),
                                            'customer_key': participant.get('customer_key', ''),
                                            'registrant_id': participant.get('registrant_id', ''),
                                            'sync_source': 'zoom_api_report',
                                            'sync_timestamp': timezone.now().isoformat()
                                        }
                                    }
                                )
                                
                                if not created:
                                    # Update existing attendance with Zoom API data
                                    attendance.participant_id = zoom_participant_id
                                    attendance.join_time = join_time or attendance.join_time
                                    attendance.leave_time = leave_time or attendance.leave_time
                                    attendance.duration_minutes = max(duration_minutes, attendance.duration_minutes)
                                    attendance.attendance_status = attendance_status
                                    
                                    # Merge device info
                                    attendance.device_info.update({
                                        'zoom_participant_id': zoom_participant_id,
                                        'zoom_participant_name': participant_name,
                                        'zoom_participant_email': participant_email,
                                        'user_type': participant.get('user_type', ''),
                                        'customer_key': participant.get('customer_key', ''),
                                        'registrant_id': participant.get('registrant_id', ''),
                                        'sync_source': 'zoom_api_report',
                                        'sync_timestamp': timezone.now().isoformat()
                                    })
                                    attendance.save()
                                
                                participants_processed += 1
                                logger.info(f"Processed participant: {participant_name} ({participant_email}) -> {user.username} | Duration: {duration_minutes}min | Status: {attendance_status}")
                            
                            else:
                                # Enhanced logging for unmatched participants (especially learners)
                                logger.warning(f" UNMATCHED PARTICIPANT: {participant_name} ({participant_email}) | Duration: {participant.get('duration', 0)//60}min")
                                
                                # Provide detailed suggestions for manual mapping
                                if participant_name:
                                    # Find potential matches for better debugging
                                    suggestions = []
                                    
                                    # Check for exact name matches across all branches
                                    name_parts = participant_name.split()
                                    if len(name_parts) >= 2:
                                        first_name = name_parts[0]
                                        last_name = name_parts[-1]
                                        
                                        exact_matches = User.objects.filter(
                                            first_name__iexact=first_name,
                                            last_name__iexact=last_name
                                        ).values('username', 'first_name', 'last_name', 'email', 'branch__name', 'role')
                                        
                                        for match in exact_matches[:3]:  # Top 3 matches
                                            suggestions.append(f"{match['username']} ({match['first_name']} {match['last_name']}) - {match['email']} - Branch: {match['branch__name']} - Role: {match['role']}")
                                    
                                    # Check for partial matches within the same branch
                                    if conference.created_by.branch and len(name_parts) >= 2:
                                        partial_matches = User.objects.filter(
                                            branch=conference.created_by.branch,
                                            role='learner'
                                        ).filter(
                                            Q(first_name__icontains=name_parts[0]) |
                                            Q(last_name__icontains=name_parts[-1]) |
                                            Q(username__icontains=participant_name.replace(' ', '').lower())
                                        ).values('username', 'first_name', 'last_name', 'email', 'role')[:3]
                                        
                                        for match in partial_matches:
                                            suggestions.append(f"PARTIAL: {match['username']} ({match['first_name']} {match['last_name']}) - {match['email']} - Role: {match['role']}")
                                    
                                    # Check for email domain matches
                                    if participant_email and '@' in participant_email:
                                        email_domain = participant_email.split('@')[1]
                                        domain_matches = User.objects.filter(
                                            email__iendswith=f"@{email_domain}",
                                            branch=conference.created_by.branch if conference.created_by.branch else None
                                        ).values('username', 'first_name', 'last_name', 'email', 'role')[:2]
                                        
                                        for match in domain_matches:
                                            suggestions.append(f"EMAIL_DOMAIN: {match['username']} ({match['first_name']} {match['last_name']}) - {match['email']} - Role: {match['role']}")
                                    
                                    logger.info(f"🔍 MATCHING SUGGESTIONS for '{participant_name}' ({participant_email}):")
                                    if suggestions:
                                        for i, suggestion in enumerate(suggestions, 1):
                                            logger.info(f"   {i}. {suggestion}")
                                    else:
                                        logger.info(f"   No potential matches found in branch: {conference.created_by.branch.name if conference.created_by.branch else 'No branch'}")
                                        
                                        # Show all learners in the branch for reference
                                        if conference.created_by.branch:
                                            all_learners = User.objects.filter(
                                                role='learner',
                                                branch=conference.created_by.branch
                                            ).values_list('username', 'first_name', 'last_name', 'email')[:5]
                                            logger.info(f"   Available learners in branch: {list(all_learners)}")
                                    
                                    # Log what we tried to match against
                                    logger.info(f"🔍 ATTEMPTED MATCHES: Name='{participant_name}', Email='{participant_email}', Zoom_ID='{zoom_participant_id}'")
                                
                                # Create ConferenceParticipant record for unmatched/guest participants
                                try:
                                    # Parse timestamps
                                    join_time = None
                                    leave_time = None
                                    
                                    if participant.get('join_time'):
                                        try:
                                            join_time = timezone.datetime.fromisoformat(participant['join_time'].replace('Z', '+00:00'))
                                        except:
                                            logger.warning(f"Could not parse join_time: {participant.get('join_time')}")
                                    
                                    if participant.get('leave_time'):
                                        try:
                                            leave_time = timezone.datetime.fromisoformat(participant['leave_time'].replace('Z', '+00:00'))
                                        except:
                                            logger.warning(f"Could not parse leave_time: {participant.get('leave_time')}")
                                    
                                    # Calculate duration
                                    duration_minutes = participant.get('duration', 0) // 60 if participant.get('duration') else 0
                                    
                                    #  FIX #1: Prevent duplicate sync data by using get_or_create
                                    unique_participant_id = f"zoom_{zoom_participant_id or f'sync_{uuid.uuid4().hex[:8]}'}"
                                    
                                    guest_participant, created = ConferenceParticipant.objects.get_or_create(
                                        conference=conference,
                                        platform_participant_id=zoom_participant_id,
                                        defaults={
                                            'user': None,  # No matched user
                                            'participant_id': unique_participant_id,
                                            'session_token': str(uuid.uuid4()),
                                            'display_name': participant_name or 'Unknown Guest',
                                            'email_address': participant_email,
                                            'participation_status': 'sync_completed',
                                            'join_timestamp': join_time,
                                            'leave_timestamp': leave_time,
                                            'total_duration_minutes': duration_minutes,
                                            'tracking_data': {
                                                'source': 'zoom_sync',
                                                'zoom_participant_id': zoom_participant_id,
                                                'zoom_participant_name': participant_name,
                                                'zoom_participant_email': participant_email,
                                                'user_type': participant.get('user_type'),
                                                'customer_key': participant.get('customer_key'),
                                                'sync_timestamp': timezone.now().isoformat(),
                                                'is_guest': True
                                            },
                                            'sync_status': 'completed'
                                        }
                                    )
                                    
                                    if created:
                                        participants_processed += 1
                                        logger.info(f" Created new guest participant: {participant_name} ({participant_email})")
                                    else:
                                        # Update existing record to prevent stale data
                                        guest_participant.display_name = participant_name or guest_participant.display_name
                                        guest_participant.email_address = participant_email or guest_participant.email_address
                                        guest_participant.join_timestamp = join_time or guest_participant.join_timestamp
                                        guest_participant.leave_timestamp = leave_time or guest_participant.leave_timestamp
                                        guest_participant.total_duration_minutes = duration_minutes
                                        guest_participant.tracking_data.update({
                                            'last_sync_update': timezone.now().isoformat(),
                                            'sync_count': guest_participant.tracking_data.get('sync_count', 0) + 1
                                        })
                                        guest_participant.save()
                                        logger.info(f" Updated existing guest participant: {participant_name} ({participant_email})")
                                    
                                except Exception as e:
                                    logger.error(f"Error creating guest participant record: {str(e)}")
                            
                        except Exception as e:
                            logger.error(f"Error processing participant {participant.get('name', 'Unknown')}: {str(e)}")
                            total_items_failed += 1
                
                total_items_processed += participants_processed
                platform_response['attendance'] = {
                    'status': 'success',
                    'items_processed': participants_processed,
                    'message': f'Found {participants_processed} participants'
                }
                
            elif participants_response.status_code == 404:
                platform_response['attendance'] = {
                    'status': 'no_data',
                    'items_processed': 0,
                    'message': 'No participant data found for this meeting'
                }
            else:
                error_text = participants_response.text
                logger.error(f"Error fetching participants: {participants_response.status_code} - {error_text}")
                
                # Provide user-friendly error messages for common issues
                if participants_response.status_code == 400:
                    if 'scopes' in error_text.lower():
                        error_message = 'Missing API permissions. Your Zoom app needs the "report:read:list_meeting_participants:admin" scope. Please check the Zoom API Scopes Fix Guide for instructions.'
                    elif 'invalid meeting id' in error_text.lower():
                        error_message = 'Invalid meeting ID. Please check that the meeting ID is correct and the meeting has occurred.'
                    else:
                        error_message = f'API Error: {participants_response.status_code} - The meeting may not have occurred yet or may not be accessible.'
                elif participants_response.status_code == 401:
                    error_message = 'Authentication failed. Please check your Zoom API credentials in Account Settings.'
                elif participants_response.status_code == 404:
                    error_message = 'Meeting not found. The meeting may not have occurred yet or the meeting ID is incorrect.'
                else:
                    error_message = f'API Error: {participants_response.status_code} - {error_text[:100]}'
                
                platform_response['attendance'] = {
                    'status': 'error',
                    'items_processed': 0,
                    'message': error_message
                }
                total_items_failed += 1
                
        except Exception as e:
            logger.error(f"Exception while syncing participants: {str(e)}")
            platform_response['attendance'] = {
                'status': 'error',
                'items_processed': 0,
                'message': f'Exception: {str(e)}'
            }
            total_items_failed += 1
        
        # 3. Enhanced Chat Messages Sync
        try:
            chat_processed = 0
            
            # Method 1: Try to get chat from recording files (already processed above)
            # Chat messages are often available in recording files as 'chat_file' type
            
            # Method 2: Try dashboard/report API for chat data (some plans support this)
            try:
                # Check for meeting dashboard data which sometimes includes chat
                dashboard_url = f"https://api.zoom.us/v2/report/meetings/{conference.meeting_id}"
                dashboard_response = requests.get(dashboard_url, headers=headers)
                
                if dashboard_response.status_code == 200:
                    dashboard_data = dashboard_response.json()
                    logger.info(f"Retrieved meeting dashboard data for chat analysis")
                    
                    # Some Zoom APIs provide limited chat data in dashboard reports
                    # This varies by Zoom plan and configuration
                    
            except Exception as dashboard_error:
                logger.warning(f"Dashboard API not available for chat data: {dashboard_error}")
            
            # Method 3: Check for existing chat data from recording processing above
            existing_chat_count = conference.chat_messages.count()
            if existing_chat_count > 0:
                chat_processed = existing_chat_count
                logger.info(f"Found {existing_chat_count} existing chat messages from previous sync")
            
            # Method 4: Parse any additional chat files in recordings
            chat_recordings = conference.recordings.filter(
                title__icontains='chat',
                status='available'
            )
            
            for chat_recording in chat_recordings:
                if chat_recording.file_url and chat_recording.file_url not in [
                    rec.get('processed_chat_url') for rec in platform_response.get('recordings_processed', [])
                ]:
                    try:
                        # Download and parse chat file
                        chat_response = requests.get(chat_recording.file_url, headers=headers)
                        if chat_response.status_code == 200:
                            # Parse chat content
                            chat_content = chat_response.text
                            parsed_messages = parse_zoom_chat_content(chat_content, conference)
                            chat_processed += parsed_messages
                            
                            logger.info(f"Processed {parsed_messages} chat messages from recording file")
                            
                    except Exception as chat_file_error:
                        logger.warning(f"Could not process chat recording file: {chat_file_error}")
            
            # Update platform response for chat
            if chat_processed > 0:
                platform_response['chat'] = {
                    'status': 'success',
                    'items_processed': chat_processed,
                    'message': f'Retrieved {chat_processed} chat messages from available sources'
                }
            else:
                platform_response['chat'] = {
                    'status': 'info',
                    'items_processed': 0,
                    'message': 'No chat messages found. Chat data may require webhook configuration or may not be available for this meeting type.'
                }
                
        except Exception as e:
            logger.error(f"Exception while syncing chat: {str(e)}")
            platform_response['chat'] = {
                'status': 'error',
                'items_processed': 0,
                'message': f'Exception: {str(e)}'
            }
        
        # 4. Enhanced Shared Files Sync
        try:
            files_processed = 0
            
            # Method 1: Check for file-type recordings (some plans include shared files as recordings)
            file_recordings = conference.recordings.filter(
                recording_type__in=['shared_screen', 'audio_only'],
                status='available'
            ).exclude(title__icontains='chat')
            
            for file_recording in file_recordings:
                try:
                    # Check if this looks like a shared file rather than a video recording
                    file_title = file_recording.title.lower()
                    file_format = file_recording.file_format.lower()
                    
                    # Look for file-like recordings (documents, presentations, etc.)
                    if any(keyword in file_title for keyword in ['document', 'presentation', 'file', 'shared']) or \
                       file_format in ['pdf', 'doc', 'docx', 'ppt', 'pptx', 'xls', 'xlsx']:
                        
                        # Create or update shared file record
                        shared_file, created = ConferenceFile.objects.get_or_create(
                            conference=conference,
                            filename=file_recording.title,
                            defaults={
                                'shared_by': conference.created_by,  # Default to conference creator
                                'original_filename': file_recording.title,
                                'file_url': file_recording.download_url or file_recording.file_url,
                                'file_size': file_recording.file_size,
                                'file_type': file_recording.file_format,
                                'shared_at': file_recording.created_at,
                                'mime_type': f'application/{file_recording.file_format}'
                            }
                        )
                        
                        if created:
                            files_processed += 1
                            logger.info(f"Processed shared file from recording: {file_recording.title}")
                        
                except Exception as file_error:
                    logger.warning(f"Could not process file recording {file_recording.title}: {file_error}")
            
            # Method 2: Check for files in meeting dashboard/report data
            try:
                # Some Zoom plans provide file sharing data in reports
                dashboard_url = f"https://api.zoom.us/v2/report/meetings/{conference.meeting_id}"
                dashboard_response = requests.get(dashboard_url, headers=headers)
                
                if dashboard_response.status_code == 200:
                    dashboard_data = dashboard_response.json()
                    
                    # Look for file-related data in the dashboard response
                    # This varies significantly by Zoom plan and configuration
                    if 'file_downloads' in dashboard_data or 'shared_files' in dashboard_data:
                        logger.info("Found potential file sharing data in meeting dashboard")
                        # Process file data if available (implementation depends on exact API response format)
                        
            except Exception as dashboard_error:
                logger.warning(f"Dashboard API not available for file data: {dashboard_error}")
            
            # Method 3: Check existing shared files
            existing_files_count = conference.shared_files.count()
            if existing_files_count > 0:
                files_processed += existing_files_count
                logger.info(f"Found {existing_files_count} existing shared files")
            
            # Update platform response for shared files
            if files_processed > 0:
                platform_response['shared_files'] = {
                    'status': 'success',
                    'items_processed': files_processed,
                    'message': f'Found {files_processed} shared files from available sources'
                }
            else:
                platform_response['shared_files'] = {
                    'status': 'info',
                    'items_processed': 0,
                    'message': 'No shared files found. File sharing data may not be available via API for this meeting type or Zoom plan.'
                }
                
        except Exception as e:
            logger.error(f"Exception while syncing shared files: {str(e)}")
            platform_response['shared_files'] = {
                'status': 'error',
                'items_processed': 0,
                'message': f'Exception: {str(e)}'
            }
        
        # Update conference sync status
        conference.data_sync_status = 'completed'
        conference.last_sync_at = timezone.now()
        conference.save(update_fields=['data_sync_status', 'last_sync_at'])
        
        # Create sync log
        ConferenceSyncLog.objects.create(
            conference=conference,
            sync_type='full',
            status='completed' if total_items_failed == 0 else 'partial',
            items_processed=total_items_processed,
            items_failed=total_items_failed,
            platform_response=platform_response
        )
        
        return {
            'success': True,
            'message': f'Zoom data sync completed successfully. Processed {total_items_processed} items.',
            'items_processed': total_items_processed,
            'items_failed': total_items_failed,
            'platform_response': platform_response
        }
        
    except Exception as e:
        logger.error(f"Error syncing Zoom meeting data: {str(e)}")
        
        # Update conference sync status
        conference.data_sync_status = 'failed'
        conference.save(update_fields=['data_sync_status'])
        
        # Create sync log
        ConferenceSyncLog.objects.create(
            conference=conference,
            sync_type='full',
            status='failed',
            items_processed=0,
            items_failed=1,
            error_message=str(e)
        )
        
        return {
            'success': False,
            'error': str(e),
            'items_processed': 0,
            'items_failed': 1
        }

def sync_teams_meeting_data(conference):
    """Sync meeting data from Microsoft Teams"""
    return {
        'success': True,
        'message': 'Teams data sync not yet implemented',
        'items_processed': 0,
        'items_failed': 0,
        'platform_response': {}
    }



def ensure_meeting_recording_enabled(conference):
    """Ensure that the meeting has recording enabled via Zoom API with comprehensive settings"""
    if conference.meeting_platform != 'zoom':
        logger.info(f"Conference {conference.id} is not a Zoom meeting, skipping recording setup")
        return False
    
    # Extract meeting ID if not present
    if not conference.meeting_id and conference.meeting_link:
        extracted_id = extract_meeting_id_from_any_zoom_url(conference.meeting_link)
        if extracted_id:
            conference.meeting_id = extracted_id
            conference.save(update_fields=['meeting_id'])
            logger.info(f"Extracted and saved meeting ID {extracted_id} for conference {conference.id}")
    
    if not conference.meeting_id:
        logger.warning(f"No meeting ID available for conference {conference.id}, cannot enable recording")
        return False
    
    try:
        # Get user's Zoom integration (first check user's own integrations)
        zoom_integration = ZoomIntegration.objects.filter(
            user=conference.created_by,
            is_active=True
        ).first()
        
        # If no user integration found, check for branch integrations
        if not zoom_integration and hasattr(conference.created_by, 'branch') and conference.created_by.branch:
            zoom_integration = ZoomIntegration.objects.filter(
                user__branch=conference.created_by.branch,
                is_active=True
            ).exclude(user=conference.created_by).first()
            
            if zoom_integration:
                logger.info(f"Using branch Zoom integration from {zoom_integration.user.username} for recording setup of conference {conference.id}")
        
        if not zoom_integration:
            logger.warning(f"No active Zoom integration found for conference {conference.id}")
            # Mark conference as requiring recording setup
            conference.auto_recording_status = 'failed_no_integration'
            conference.save(update_fields=['auto_recording_status'])
            return False
        
        # Check if using default/test credentials
        if (zoom_integration.api_key == "your_zoom_api_key" or 
            zoom_integration.api_secret == "your_zoom_api_secret"):
            logger.warning(f"Default Zoom credentials detected for conference {conference.id}")
            conference.auto_recording_status = 'failed_invalid_credentials'
            conference.save(update_fields=['auto_recording_status'])
            return False
        
        # Get OAuth token
        access_token = get_zoom_oauth_token(
            zoom_integration.api_key, 
            zoom_integration.api_secret, 
            zoom_integration.account_id
        )
        
        if not access_token:
            logger.error(f"Failed to get Zoom token for recording setup for conference {conference.id}")
            conference.auto_recording_status = 'failed_auth'
            conference.save(update_fields=['auto_recording_status'])
            return False
        
        # Comprehensive recording settings
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        
        # Enhanced recording settings for maximum capture
        recording_settings = {
            "auto_recording": "cloud",  # Enable cloud recording
            "cloud_recording": True,    # Ensure cloud recording is on
            "record_play_own_voice": True,
            "record_repeat_caller": True,
            "recording_authentication": False,  # Allow access without authentication
            "auto_recording_local": False,      # Disable local recording to focus on cloud
            "auto_recording_cloud": True,       # Explicit cloud recording
            "recording_disclaimer": True,       # Show recording disclaimer
            "host_save_video_order": True,      # Save in gallery view if possible
            "alternative_host_update_polls": True
        }
        
        # Update meeting settings
        settings_url = f"https://api.zoom.us/v2/meetings/{conference.meeting_id}"
        
        # First, update the main meeting settings
        meeting_update = {
            "settings": {
                "auto_recording": "cloud",
                "cloud_recording": True,
                "record_play_own_voice": True,
                "record_repeat_caller": True,
                "recording_authentication": False,
                "use_pmi": False,  # Don't use PMI to ensure specific meeting
                "approval_type": 0,  # Auto-approve participants
                "join_before_host": True,  # Allow participants to join before host
                "mute_upon_entry": False,
                "participant_video": True,
                "host_video": True,
                "waiting_room": False,  # Disable waiting room for smoother experience
                "meeting_authentication": False,  # Allow guests
                "enforce_login": False,
                "show_share_button": True,
                "allow_multiple_devices": True,
                "encryption_type": "enhanced_encryption"
            }
        }
        
        # Update the meeting
        update_response = requests.patch(settings_url, headers=headers, json=meeting_update)
        
        if update_response.status_code in [200, 204]:
            logger.info(f" Successfully enabled comprehensive cloud recording for meeting {conference.meeting_id}")
            conference.auto_recording_status = 'enabled'
            conference.auto_recording_enabled_at = timezone.now()
            conference.save(update_fields=['auto_recording_status', 'auto_recording_enabled_at'])
            return True
        else:
            logger.error(f" Failed to enable recording for meeting {conference.meeting_id}: {update_response.status_code} - {update_response.text}")
            conference.auto_recording_status = 'failed_api_error'
            conference.save(update_fields=['auto_recording_status'])
            return False
            
    except Exception as e:
        logger.error(f" Error enabling recording for conference {conference.id}: {str(e)}")
        conference.auto_recording_status = 'failed_exception'
        conference.save(update_fields=['auto_recording_status'])
        return False

def register_user_on_zoom_platform(conference, user):
    """Register a user on the Zoom platform for automatic attendance tracking"""
    try:
        # Only register if meeting platform is Zoom
        if conference.meeting_platform != 'zoom':
            return {'success': True, 'message': 'Non-Zoom platform, skipping registration'}
        
        # Get the meeting ID from the conference
        meeting_id = conference.meeting_id
        if not meeting_id:
            meeting_id = extract_meeting_id_from_any_zoom_url(conference.meeting_link)
            if meeting_id:
                conference.meeting_id = meeting_id
                conference.save(update_fields=['meeting_id'])
        
        if not meeting_id:
            logger.warning(f"Cannot register user {user.username} - no meeting ID found for conference {conference.id}")
            return {'success': False, 'error': 'No meeting ID found'}
        
        # Get Zoom integration for the conference creator
        try:
            integration = ZoomIntegration.objects.filter(
                user=conference.created_by,
                is_active=True
            ).first()
            
            if not integration:
                # Try to get any active integration from the same branch
                if hasattr(conference.created_by, 'branch') and conference.created_by.branch:
                    integration = ZoomIntegration.objects.filter(
                        user__branch=conference.created_by.branch,
                        is_active=True
                    ).first()
            
            if not integration:
                logger.warning(f"No Zoom integration found for conference {conference.id}")
                return {'success': False, 'error': 'No Zoom integration found'}
                
        except Exception as e:
            logger.error(f"Error getting Zoom integration: {str(e)}")
            return {'success': False, 'error': 'Error accessing Zoom integration'}
        
        # Get OAuth token
        auth_token = get_zoom_oauth_token(integration.api_key, integration.api_secret, integration.account_id)
        if not auth_token:
            logger.error("Failed to obtain Zoom OAuth token for registration")
            return {'success': False, 'error': 'Failed to authenticate with Zoom'}
        
        # Prepare user data for registration
        user_data = {
            'first_name': user.first_name or user.username,
            'last_name': user.last_name or '',
            'address': getattr(user, 'address', ''),
            'city': getattr(user, 'city', ''),
            'state': getattr(user, 'state', ''),
            'zip': getattr(user, 'postal_code', ''),
            'country': getattr(user, 'country', 'US'),
            'phone': getattr(user, 'phone', ''),
            'industry': getattr(user, 'industry', ''),
            'org': getattr(user, 'organization', ''),
            'job_title': getattr(user, 'job_title', ''),
            'purchasing_time_frame': 'No_Timeframe',
            'role_in_purchase_process': 'Not_Applicable',
            'no_of_employees': '1-20',
            'comments': f'LMS User: {user.username}',
            'custom_questions': [
                {
                    'title': 'LMS User ID',
                    'value': str(user.id)
                },
                {
                    'title': 'LMS Username', 
                    'value': user.username
                }
            ]
        }
        
        # API endpoint for meeting registration
        api_url = f'https://api.zoom.us/v2/meetings/{meeting_id}/registrants'
        
        headers = {
            'Authorization': f'Bearer {auth_token}',
            'Content-Type': 'application/json'
        }
        
        logger.info(f"Registering user {user.username} for Zoom meeting {meeting_id}")
        
        # Make registration API call
        response = requests.post(api_url, headers=headers, json=user_data)
        
        if response.status_code == 201:
            # Registration successful
            registration_data = response.json()
            logger.info(f"Successfully registered user {user.username} for meeting {meeting_id}")
            
            return {
                'success': True,
                'registrant_id': registration_data.get('registrant_id'),
                'join_url': registration_data.get('join_url'),
                'registration_data': registration_data
            }
        elif response.status_code == 409:
            # User already registered - this is okay
            logger.info(f"User {user.username} already registered for meeting {meeting_id}")
            return {
                'success': True,
                'message': 'User already registered',
                'already_registered': True
            }
        else:
            # Registration failed
            logger.error(f"Failed to register user {user.username}: {response.status_code} - {response.text}")
            return {
                'success': False,
                'error': f'Registration failed: {response.status_code}',
                'response': response.text
            }
            
    except Exception as e:
        logger.exception(f"Error registering user {user.username} on Zoom platform: {str(e)}")
        return {'success': False, 'error': str(e)}

def update_meeting_to_disable_registration(conference):
    """Update a Zoom meeting to disable registration requirement"""
    try:
        if conference.meeting_platform != 'zoom':
            return {'success': True, 'message': 'Non-Zoom platform, skipping update'}
        
        # Get the meeting ID
        meeting_id = conference.meeting_id
        if not meeting_id:
            meeting_id = extract_meeting_id_from_any_zoom_url(conference.meeting_link)
            if meeting_id:
                conference.meeting_id = meeting_id
                conference.save(update_fields=['meeting_id'])
        
        if not meeting_id:
            logger.warning(f"Cannot update meeting - no meeting ID found for conference {conference.id}")
            return {'success': False, 'error': 'No meeting ID found'}
        
        # Get Zoom integration
        try:
            integration = ZoomIntegration.objects.filter(
                user=conference.created_by,
                is_active=True
            ).first()
            
            if not integration:
                # Try to get any active integration from the same branch
                if hasattr(conference.created_by, 'branch') and conference.created_by.branch:
                    integration = ZoomIntegration.objects.filter(
                        user__branch=conference.created_by.branch,
                        is_active=True
                    ).first()
            
            if not integration:
                logger.warning(f"No Zoom integration found for conference {conference.id}")
                return {'success': False, 'error': 'No Zoom integration found'}
                
        except Exception as e:
            logger.error(f"Error getting Zoom integration: {str(e)}")
            return {'success': False, 'error': 'Error accessing Zoom integration'}
        
        # Get OAuth token
        auth_token = get_zoom_oauth_token(integration.api_key, integration.api_secret, integration.account_id)
        if not auth_token:
            logger.error("Failed to obtain Zoom OAuth token for meeting update")
            return {'success': False, 'error': 'Failed to authenticate with Zoom'}
        
        # Update meeting settings to disable registration
        meeting_update_data = {
            'settings': {
                'approval_type': 2,  # No registration required
                'registration_type': 0,  # No registration required
                'meeting_authentication': False,  # Allow guests
                'enforce_login': False,  # No login required
                'waiting_room': False,  # No waiting room
                'join_before_host': True,  # Allow joining before host
            }
        }
        
        # API endpoint for updating meeting
        api_url = f'https://api.zoom.us/v2/meetings/{meeting_id}'
        
        headers = {
            'Authorization': f'Bearer {auth_token}',
            'Content-Type': 'application/json'
        }
        
        logger.info(f"Updating meeting {meeting_id} to disable registration")
        
        # Make update API call
        response = requests.patch(api_url, headers=headers, json=meeting_update_data)
        
        if response.status_code == 204:
            # Update successful (204 No Content is success for PATCH)
            logger.info(f"Successfully updated meeting {meeting_id} to disable registration")
            return {'success': True, 'message': 'Meeting updated to disable registration'}
        elif response.status_code == 404:
            logger.warning(f"Meeting {meeting_id} not found - may have expired or been deleted")
            return {'success': False, 'error': 'Meeting not found'}
        else:
            logger.error(f"Failed to update meeting {meeting_id}: {response.status_code} - {response.text}")
            return {'success': False, 'error': f'Update failed: {response.status_code}'}
            
    except Exception as e:
        logger.exception(f"Error updating meeting to disable registration: {str(e)}")
        return {'success': False, 'error': str(e)}

@login_required
def join_conference(request, conference_id):
    """
    Redirect all join requests to auto-registered join method
    All users now use auto-registered join method
    """
    logger.info(f"Redirecting join request to auto-registered join for conference {conference_id}")
    return redirect('conferences:auto_register_and_join', conference_id=conference_id)




@login_required
@csrf_protect
def generate_simple_zoom_link(request):
    """Generate a Zoom meeting link with automatic recording enabled"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)
    
    if request.user.role not in ['instructor', 'admin', 'superadmin', 'globaladmin'] and not request.user.is_superuser:
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)
    
    try:
        data = json.loads(request.body)
        title = data.get('title', 'Conference Meeting')
        
        # Try to use Zoom API to create a real meeting with recording enabled
        zoom_integration = ZoomIntegration.objects.filter(
            user=request.user,
            is_active=True
        ).first()
        
        if zoom_integration:
            # Create real Zoom meeting with API
            try:
                access_token = get_zoom_oauth_token(
                    zoom_integration.api_key, 
                    zoom_integration.api_secret, 
                    zoom_integration.account_id
                )
                
                if access_token:
                    
                    # Create meeting with recording enabled
                    headers = {
                        'Authorization': f'Bearer {access_token}',
                        'Content-Type': 'application/json'
                    }
                    
                    meeting_data = {
                        "topic": title,
                        "type": 2,  # Scheduled meeting
                        "start_time": timezone.now().isoformat(),
                        "duration": 60,  # Default 1 hour
                        "settings": {
                            "join_before_host": True,
                            "auto_recording": "cloud",  #  FORCE CLOUD RECORDING
                            "cloud_recording": True,     #  EXPLICIT CLOUD RECORDING
                            "allow_multiple_devices": True,
                            "participant_video": True,
                            "host_video": True,
                            "mute_upon_entry": False,
                            "waiting_room": False,
                            "meeting_authentication": False,  #  ALLOW GUESTS
                            "enforce_login": False,           #  NO LOGIN REQUIRED
                            "approval_type": 2,               #  NO REGISTRATION REQUIRED
                            "record_play_own_voice": True,    #  RECORD AUDIO
                            "record_repeat_caller": True,     #  RECORD REPEAT CALLERS
                            "recording_authentication": False, #  NO AUTH FOR RECORDING ACCESS
                            "recording_disclaimer": True,     #  SHOW RECORDING NOTICE
                            "auto_recording_local": False,    #  DISABLE LOCAL RECORDING
                            "auto_recording_cloud": True,     #  ENABLE CLOUD RECORDING
                            "show_share_button": True,        #  SHOW SHARE BUTTON
                            "use_pmi": False,                 #  DON'T USE PMI
                            
                            #  CHAT AND FILE SHARING SETTINGS
                            "allow_participants_chat_with": 1,  # 1 = Everyone publicly and privately
                            "allow_users_save_chats": 2,  # 2 = Everyone can save
                            "chat_etiquette_tool": {
                                "enable": False,  # Don't restrict chat
                                "policies": []
                            },
                            "file_transfer": {
                                "enable": True,  # Enable file transfers in chat
                                "allow_all_file_types": True  # Allow all file types
                            }
                        }
                    }
                    
                    create_url = "https://api.zoom.us/v2/users/me/meetings"
                    response = requests.post(create_url, headers=headers, json=meeting_data)
                    
                    if response.status_code == 201:
                        meeting_info = response.json()
                        return JsonResponse({
                            'success': True,
                            'meeting_link': meeting_info['join_url'],
                            'meeting_id': meeting_info['id'],
                            'password': meeting_info.get('password', ''),
                            'host_url': meeting_info.get('start_url', ''),
                            'message': 'Zoom meeting created successfully with cloud recording enabled!'
                        })
                    else:
                        logger.error(f"Zoom API error: {response.status_code} - {response.text}")
                        # Fall back to simulated link if API fails
                        
            except Exception as e:
                logger.error(f"Error creating Zoom meeting via API: {str(e)}")
                # Fall back to simulated link
        
        # Fallback: Generate a realistic Zoom meeting link (for demo/testing)
        meeting_id = f"{random.randint(100, 999)}{random.randint(10, 99)}{random.randint(100000, 999999)}"
        
        # Generate a 6-digit meeting passcode (more user-friendly than long token)
        meeting_passcode = f"{random.randint(100000, 999999)}"
        
        # Generate password token for URL (encoded version of passcode)
        import string
        password_chars = string.ascii_letters + string.digits
        password_token = ''.join(random.choice(password_chars) for _ in range(32))
        
        # Choose random Zoom server subdomain
        zoom_servers = ['us02web', 'us04web', 'us05web', 'us06web']
        server = random.choice(zoom_servers)
        
        # Create a realistic Zoom meeting URL with password parameter
        meeting_link = f"https://{server}.zoom.us/j/{meeting_id}?pwd={password_token}"
        
        logger.info(f"Generated simulated Zoom link with auto-recording: {meeting_link}")
        
        return JsonResponse({
            'success': True,
            'meeting_link': meeting_link,
            'meeting_id': meeting_id,
            'password': meeting_passcode,  # Return the 6-digit passcode
            'password_token': password_token,  # Return the URL token
            'message': 'Zoom meeting link generated with passcode and automatic cloud recording enabled!'
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON data'}, status=400)
    except Exception as e:
        logger.exception(f"Error generating Zoom meeting: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

def conference_public_access(request, conference_id):
    """Handle public access to conferences (no authentication required)"""
    try:
        conference = get_object_or_404(Conference, id=conference_id)
    except:
        # For public access, we should show a proper error template
        context = {
            'message': f'Conference with ID {conference_id} does not exist or has been deleted.'
        }
        return render(request, 'conferences/guest_access_denied.html', context)
    
    # Check if conference allows guest access
    if conference.default_join_type not in ['guest'] or conference.status != 'published':
        context = {
            'conference': conference,
            'message': 'This conference requires authentication or is not available for public access.'
        }
        return render(request, 'conferences/guest_access_denied.html', context)
    
    # Check if user is already authenticated
    if request.user.is_authenticated:
        # Redirect authenticated users to the normal join flow
        return redirect('conferences:join_conference', conference_id=conference.id)
    
    # Determine which guest access template to use based on join_experience
    if conference.join_experience == 'direct':
        template_name = 'conferences/direct_join.html'
    else:
        template_name = 'conferences/guest_conference_access.html'
    
    context = {
        'conference': conference,
        'title': f'Join: {conference.title}',
        'description': 'Join conference as guest'
    }
    
    return render(request, template_name, context)


@login_required
def conference_detail(request, conference_id):
    """Display detailed conference information based on user role"""
    from .models import ConferenceAttendance, ConferenceRubricEvaluation  # Import at top
    
    # Handle non-existent conference gracefully
    try:
        conference = get_object_or_404(Conference, id=conference_id)
    except:
        messages.error(request, f'Conference with ID {conference_id} does not exist or has been deleted.')
        return redirect('conferences:conference_list')
    
    user = request.user
    
    # Check if user has access to view this conference
    if user.role == 'learner':
        # Learners can only view published conferences with active topics from courses they're enrolled in
        if not conference.is_available_for_user(user):
            messages.error(request, 'You do not have permission to view this conference.')
            return redirect('conferences:conference_list')
    elif user.role == 'instructor':
        # Instructors can view conferences they created or in their courses (including group-assigned)
        if conference.created_by != user:
            # Check if instructor has any course access (direct or group-based)
            has_access = False
            
            if conference.course:
                # Check direct instructor assignment
                if conference.course.instructor == user:
                    has_access = True
                
                # Check group-based instructor access
                if not has_access:
                    has_access = conference.course.accessible_groups.filter(
                        memberships__user=user,
                        memberships__is_active=True,
                        memberships__custom_role__name__icontains='instructor'
                    ).exists()
            
            if not has_access:
                messages.error(request, 'You do not have permission to view this conference.')
                return redirect('conferences:conference_list')
    
    # Define breadcrumbs
    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': reverse('conferences:conference_list'), 'label': 'Conferences', 'icon': 'fa-video'},
        {'label': conference.title, 'icon': 'fa-info-circle'}
    ]
    
    # Prepare context based on user role
    context = {
        'conference': conference,
        'breadcrumbs': breadcrumbs,
        'title': conference.title,
    }
    
    if user.role == 'learner':
        # Enhanced view for learners with sync status information
        template_name = 'conferences/conference_detail_learner.html'
        
        # Check if learner has already joined or participated
        participant = ConferenceParticipant.objects.filter(
            conference=conference,
            user=user
        ).first()
        
        # Get learner's own rubric evaluation data if conference has a rubric
        learner_rubric_data = None
        if conference.rubric:
            try:
                # Get learner's attendance record
                attendance = ConferenceAttendance.objects.filter(
                    conference=conference,
                    user=user
                ).first()
                
                if attendance:
                    # Get the learner's rubric evaluations
                    evaluations = ConferenceRubricEvaluation.objects.filter(
                        conference=conference,
                        attendance=attendance
                    ).select_related('criterion', 'rating', 'evaluated_by')
                    
                    total_score = sum(eval.points for eval in evaluations)
                    
                    learner_rubric_data = {
                        'evaluations': evaluations,
                        'total_score': total_score,
                        'max_score': conference.rubric.total_points,
                        'attendance': attendance
                    }
            except Exception as e:
                logger.error(f"Error getting rubric data for learner {user.id} in conference {conference.id}: {str(e)}")
        
        context.update({
            'participant': participant,
            'learner_rubric_data': learner_rubric_data,
        })
    
    elif user.role in ['instructor', 'admin', 'superadmin']:
        # Enhanced view for instructors with rubric evaluations
        template_name = 'conferences/conference_detail_instructor.html'
        
        #  FIX #4: Only show registered users - exclude unmatched guests
        participants = ConferenceParticipant.objects.filter(
            conference=conference,
            user__isnull=False  # Only show participants with matched LMS users
        ).select_related('user').order_by('-click_timestamp')
        
        attendances = ConferenceAttendance.objects.filter(
            conference=conference,
            user__isnull=False  # Only show attendances with matched LMS users
        ).select_related('user').order_by('-join_time')
        
        # Get recordings - only show chat_file and shared_screen_with_speaker_view
        recordings = ConferenceRecording.objects.filter(
            conference=conference,
            title__in=['chat_file', 'shared_screen_with_speaker_view']
        ).order_by('-created_at')
        
        # Get shared files
        shared_files = ConferenceFile.objects.filter(
            conference=conference
        ).select_related('shared_by').order_by('-shared_at')
        
        #  FIX #4: Only show chat messages from registered users - exclude guest messages
        chat_messages = ConferenceChat.objects.filter(
            conference=conference,
            sender__isnull=False  # Only show messages from matched LMS users
        ).select_related('sender').order_by('sent_at')
        
        # Determine sync and evaluation permissions
        can_sync = user.role in ['instructor', 'admin', 'superadmin'] or user.is_superuser
        can_evaluate = user.role in ['instructor', 'admin', 'superadmin'] or user.is_superuser
        
        # Prepare rubric data and evaluations for template
        rubric_data = None
        rubric_evaluations = []
        if conference.rubric:
            # Get all evaluations for this conference
            evaluations = ConferenceRubricEvaluation.objects.filter(
                conference=conference
            ).select_related('attendance', 'attendance__user', 'criterion', 'evaluated_by')
            
            # Group evaluations by participant
            evaluations_by_participant = {}
            for evaluation in evaluations:
                participant_key = evaluation.attendance.user.id if evaluation.attendance.user else f"guest_{evaluation.attendance.id}"
                if participant_key not in evaluations_by_participant:
                    evaluations_by_participant[participant_key] = {}
                evaluations_by_participant[participant_key][evaluation.criterion.id] = evaluation
            
            # Get learner attendances for evaluation
            participant_user_ids = conference.participants.filter(
                user__role='learner',
                user__isnull=False,  # Exclude guest participants
            ).values_list('user_id', flat=True)
            
            attendance_user_ids = conference.attendances.filter(
                user__role='learner',
                user__isnull=False,
            ).values_list('user_id', flat=True)
            
            all_learner_ids = set(participant_user_ids) | set(attendance_user_ids)
            
            learner_attendances = ConferenceAttendance.objects.filter(
                conference=conference,
                user_id__in=all_learner_ids
            ).select_related('user')
            
            # Create attendance records for learners who participated but don't have attendance records
            for learner_id in all_learner_ids:
                if not learner_attendances.filter(user_id=learner_id).exists():
                    participant = ConferenceParticipant.objects.filter(
                        conference=conference,
                        user_id=learner_id
                    ).first()
                    
                    if participant:
                        attendance = ConferenceAttendance.objects.create(
                            conference=conference,
                            user_id=learner_id,
                            join_time=participant.click_timestamp,
                            attendance_status='present'
                        )
                        learner_attendances = learner_attendances | ConferenceAttendance.objects.filter(id=attendance.id)
            
            # Get overall feedback data from RubricOverallFeedback model
            overall_feedback_data = {}
            for attendance in learner_attendances:
                if attendance.user:
                    user_key = attendance.user.id
                    try:
                        overall_feedback = RubricOverallFeedback.objects.get(
                            conference=conference,
                            student=attendance.user
                        )
                        overall_feedback_data[user_key] = overall_feedback.feedback
                    except RubricOverallFeedback.DoesNotExist:
                        overall_feedback_data[user_key] = None
            
            # Calculate total evaluated count
            total_evaluated = len(set(eval.attendance.user.id for eval in evaluations if eval.attendance.user))
            
            # Prepare rubric data for template
            rubric_data = {
                'rubric': conference.rubric,
                'criteria': conference.rubric.criteria.all().order_by('position'),
                'evaluations_by_participant': evaluations_by_participant,
                'learner_attendances': learner_attendances,
                'overall_feedback_data': overall_feedback_data,
                'total_evaluated': total_evaluated,
            }
            
            # Process evaluations for template
            for attendance in learner_attendances:
                participant_key = attendance.user.id
                user_evaluations = evaluations_by_participant.get(participant_key, {})
            
                # Calculate total score
                total_score = sum(eval.points for eval in user_evaluations.values())
                
                rubric_evaluations.append({
                    'attendance': attendance,
                    'user': attendance.user,
                    'evaluations': user_evaluations,
                    'total_score': total_score,
                    'max_score': conference.rubric.total_points,
                    'percentage': (total_score / conference.rubric.total_points * 100) if conference.rubric.total_points > 0 else 0
                })
        
        # Prepare participant data for template
        participant_data = []
        for participant in participants:
            # Generate join URL using the participant's tracking URL method
            join_url = participant.generate_tracking_url(conference.meeting_link) if conference.meeting_link else None
            
            # Calculate session data
            join_sessions = []
            if participant.join_timestamp and participant.leave_timestamp:
                join_sessions.append({
                    'join_time': participant.join_timestamp,
                    'leave_time': participant.leave_timestamp,
                    'duration_minutes': participant.total_duration_minutes or 0
                })
            
            participant_data.append({
                'participant': participant,  # This is what the template expects
                'user': participant.user,
                'click_timestamp': participant.click_timestamp,
                'join_url': join_url,
                'platform_user_id': participant.platform_user_id,
                'registration_id': participant.platform_participant_id,  # Use platform_participant_id instead of registration_id
                'total_joins': 1 if participant.join_timestamp else 0,  # Number of times joined
                'total_time': participant.total_duration_minutes or 0,  # Total time in minutes
                'join_sessions': join_sessions,  # Session data for template
                'user_role': participant.user.role if participant.user else 'guest'  # User role
            })
        
        context.update({
            'participants': participants,
            'attendances': attendances,
            'recordings': recordings,
            'shared_files': shared_files,
            'chat_messages': chat_messages,
            'rubric_evaluations': rubric_evaluations,
            'can_sync': can_sync,
            'can_evaluate': can_evaluate,
            'rubric_data': rubric_data,
            'participant_data': participant_data,
        })
    
    else:
        # Default view for other roles
        template_name = 'conferences/conference_detail.html'
    
    return render(request, template_name, context)


@login_required
def conference_detailed_report(request, conference_id):
    """Comprehensive detailed report for a specific student's conference participation with complete timeline"""
    conference = get_object_or_404(Conference, id=conference_id)
    
    # Check permissions - only instructors, admins, and superadmins can access
    if not (request.user.role in ['instructor', 'admin', 'superadmin'] or request.user.is_superuser):
        messages.error(request, "You don't have permission to access this report.")
        return redirect('conferences:conference_detail', conference_id=conference_id)
    
    # Get student_id from query parameters
    student_id = request.GET.get('student_id')
    if not student_id:
        messages.error(request, "Student ID is required.")
        return redirect('conferences:conference_detail', conference_id=conference_id)
    
    # Get the specific student
    from django.contrib.auth import get_user_model
    User = get_user_model()
    student = get_object_or_404(User, id=student_id)
    
    #  FIX #4: Get attendance record for this student (registered users only)
    attendance = ConferenceAttendance.objects.filter(
        conference=conference,
        user=student,
        user__isnull=False  # Only registered users
    ).first()
    
    #  FIX #4: Get participation record for this student (registered users only)
    participation = ConferenceParticipant.objects.filter(
        conference=conference,
        user=student,
        user__isnull=False  # Only registered users
    ).first()
        
    # Get rubric evaluations if conference has rubric
    rubric_evaluations = []
    rubric_total_score = 0
    if conference.rubric and attendance:
        rubric_evaluations = ConferenceRubricEvaluation.objects.filter(
            conference=conference,
            attendance=attendance
        ).select_related('criterion', 'rating', 'evaluated_by').order_by('criterion__position')
        
        # Calculate total score
        rubric_total_score = sum(eval.points for eval in rubric_evaluations)
    
    # Get chat conversation between instructor and this student
    instructor = conference.created_by  # Conference creator (instructor)
    chat_messages = ConferenceChat.objects.filter(
        conference=conference,
        sender__in=[student, instructor]  # Messages from both student and instructor
    ).order_by('sent_at')
            
    # Get files shared by this student
    shared_files = ConferenceFile.objects.filter(
                            conference=conference,
        shared_by=student
    ).order_by('shared_at')
    
    # Get conference recordings (available to all) - only show chat_file and shared_screen_with_speaker_view
    recordings = ConferenceRecording.objects.filter(
        conference=conference,
        title__in=['chat_file', 'shared_screen_with_speaker_view']
    ).order_by('-created_at')
    

            

    
    # === BUILD COMPREHENSIVE TIMELINE ===
    timeline_events = []
    
    # Add participation click event
    if participation:
        timeline_events.append({
            'type': 'participation_click',
            'timestamp': participation.click_timestamp,
            'actor': participation.user,
            'title': 'Clicked Join Conference',
            'description': f'Student clicked join button for {conference.title}',
            'data': {
                'join_method': participation.join_method,
                'participant_id': participation.participant_id,
                'ip_address': participation.ip_address,
                'user_agent': participation.user_agent[:100] if participation.user_agent else None
            }
        })
        
        # Add actual join event if available
        if participation.join_timestamp:
            timeline_events.append({
                'type': 'meeting_join',
                'timestamp': participation.join_timestamp,
                'actor': participation.user,
                'title': 'Joined Meeting',
                'description': f'Student joined the meeting platform',
                'data': {
                    'platform_participant_id': participation.platform_participant_id,
                    'platform_user_id': participation.platform_user_id,
                    'participation_status': participation.participation_status
                }
            })
        
        # Add leave event if available
        if participation.leave_timestamp:
            timeline_events.append({
                'type': 'meeting_leave',
                'timestamp': participation.leave_timestamp,
                'actor': participation.user,
                'title': 'Left Meeting',
                'description': f'Student left the meeting',
                'data': {
                    'duration_minutes': participation.total_duration_minutes,
                    'attendance_percentage': participation.attendance_percentage
                }
            })
    
    # Add attendance event
    if attendance:
        if attendance.join_time:
            timeline_events.append({
                'type': 'attendance_join',
                'timestamp': attendance.join_time,
                'actor': attendance.user,
                'title': 'Attendance Recorded - Join',
                'description': f'Attendance join time recorded by platform',
                'data': {
                    'attendance_status': attendance.attendance_status
                }
            })
        
        if attendance.leave_time:
            timeline_events.append({
                'type': 'attendance_leave',
                'timestamp': attendance.leave_time,
                'actor': attendance.user,
                'title': 'Attendance Recorded - Leave',
                'description': f'Attendance leave time recorded by platform',
                'data': {
                    'duration_minutes': attendance.duration_minutes,
                    'attendance_status': attendance.attendance_status
                }
            })
    
    # Add rubric evaluation events
    for evaluation in rubric_evaluations:
        timeline_events.append({
            'type': 'rubric_evaluation',
            'timestamp': evaluation.created_at,
            'actor': evaluation.evaluated_by,
            'title': 'Rubric Evaluation',
            'description': f'Evaluated {evaluation.criterion.description}',
            'data': {
                'criterion': evaluation.criterion.description,
                'points': evaluation.points,
                'max_points': evaluation.criterion.points,
                'rating': evaluation.rating.title if evaluation.rating else None,
                'comments': evaluation.comments
            }
        })
    
    # Add chat messages
    for message in chat_messages:
        timeline_events.append({
            'type': 'chat_message',
            'timestamp': message.sent_at,
            'actor': message.sender,
            'title': 'Chat Message',
            'description': f'Sent chat message in conference',
            'data': {
                'message_text': message.message_text[:200] + ('...' if len(message.message_text) > 200 else ''),
                'message_type': message.message_type,
                'platform_message_id': message.platform_message_id
            }
        })
    
    # Add file sharing events
    for file in shared_files:
        timeline_events.append({
            'type': 'file_share',
            'timestamp': file.shared_at,
            'actor': file.shared_by,
            'title': 'File Shared',
            'description': f'Shared file: {file.filename}',
            'data': {
                'filename': file.filename,
                'original_filename': file.original_filename,
                'file_size': file.file_size,
                'file_type': file.file_type,
                'mime_type': file.mime_type
            }
        })
    
    # Sort timeline events by timestamp (most recent first)
    timeline_events.sort(key=lambda x: x['timestamp'], reverse=True)
    
    # Build breadcrumbs
    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': reverse('conferences:conference_list'), 'label': 'Conferences', 'icon': 'fa-video'},
        {'url': reverse('conferences:conference_detail', args=[conference.id]), 'label': conference.title[:30] + ('...' if len(conference.title) > 30 else ''), 'icon': 'fa-info-circle'},
        {'label': f'Report: {student.get_full_name()}', 'icon': 'fa-user'}
    ]
    
    context = {
        'conference': conference,
        'student': student,
        'attendance': attendance,
        'participation': participation,
        'rubric_evaluations': rubric_evaluations,
        'rubric_total_score': rubric_total_score,
        'chat_messages': chat_messages,
        'shared_files': shared_files,
        'recordings': recordings,
        'timeline_events': timeline_events,
        'breadcrumbs': breadcrumbs,
    }
    
    return render(request, 'conferences/detailed_report_comprehensive.html', context)

@login_required
def download_conference_recording(request, conference_id, recording_id):
    """
     FIX #3: Secure conference recording download with password authentication
    """
    try:
        conference = get_object_or_404(Conference, id=conference_id)
        recording = get_object_or_404(ConferenceRecording, id=recording_id, conference=conference)
        
        # Check if user has access to this conference
        if not conference.is_available_for_user(request.user):
            logger.warning(f"Access denied: User {request.user.username} tried to download recording from conference {conference_id}")
            return JsonResponse({
                'success': False, 
                'error': 'You do not have access to this conference recording.'
            }, status=403)
        
        #  FIX #5: Allow direct download for cloud recordings without password restrictions
        # Skip password authentication for cloud recordings - allow direct access
        
        #  FIX #5: Provide direct download access for cloud recordings
        if recording.download_url:
            # Log successful download
            logger.info(f" Direct download granted: User {request.user.username} downloading '{recording.title}' from conference {conference.title}")
            
            # Always redirect directly to the download URL
            return redirect(recording.download_url)
        else:
            # For JSON requests or when no download URL is available
            return JsonResponse({
                'success': False,
                'error': 'Download URL not available for this recording.'
            }, status=404)
            
    except Conference.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Conference not found.'}, status=404)
    except ConferenceRecording.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Recording not found.'}, status=404)
    except Exception as e:
        logger.error(f"Error in download_conference_recording: {str(e)}")
        return JsonResponse({'success': False, 'error': 'An error occurred while processing the download request.'}, status=500)


@csrf_protect
def guest_join_conference(request, conference_id):
    """Handle guest conference joining without authentication
    
    This view is ONLY for unauthenticated guests. Authenticated users 
    (including learners) should use the join_conference view instead.
    """
    try:
        conference = get_object_or_404(Conference, id=conference_id)
    except:
        # For guest access, we should show a proper error template
        context = {
            'message': f'Conference with ID {conference_id} does not exist or has been deleted.'
        }
        return render(request, 'conferences/guest_access_denied.html', context)
    
    # Check if conference allows guest access
    if conference.default_join_type not in ['guest'] or conference.status != 'published':
        context = {
            'conference': conference,
            'message': 'This conference requires authentication or is not available for public access.'
        }
        return render(request, 'conferences/guest_access_denied.html', context)
    
    # Check if user is already authenticated
    if request.user.is_authenticated:
        # Redirect authenticated users to the normal join flow
        return redirect('conferences:join_conference', conference_id=conference.id)
    
    if request.method != 'POST':
        # If GET request, redirect to public access page
        return redirect('conferences:conference_public_access', conference_id=conference.id)
    
    # Handle guest join submission
    guest_name = request.POST.get('guest_name', '').strip()
    guest_email = request.POST.get('guest_email', '').strip()
    
    # Generate guest name if not provided
    if not guest_name:
        guest_name = f"Guest-{random.randint(1000, 9999)}"
    
    # Check if we have a meeting link
    if not conference.meeting_link:
        context = {
            'conference': conference,
            'message': 'This conference does not have a meeting link configured.'
        }
        return render(request, 'conferences/guest_access_denied.html', context)
    
    # Create guest participant record for tracking
    try:
        guest_participant = GuestParticipant.objects.create(
            conference=conference,
            participation_id=str(uuid.uuid4()),
            guest_name=guest_name,
            guest_email=guest_email,
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            device_info={
                'join_timestamp': timezone.now().isoformat(),
                'guest_name': guest_name,
                'guest_email': guest_email,
                'join_method': 'guest_access',
                'conference_id': conference.id,
                'conference_title': conference.title
            }
        )
        
        logger.info(f"Guest {guest_name} joining conference: {conference.title}")
        
    except Exception as e:
        logger.error(f"Error creating guest participant: {str(e)}")
        # Continue anyway - don't block the join process
    
    # Build simple direct join URL for guest
    zoom_url = build_simple_zoom_url_for_guest(conference, guest_name, guest_email)
    
    # Update conference status to started if needed
    if conference.meeting_status == 'scheduled':
        conference.meeting_status = 'started'
        conference.save(update_fields=['meeting_status'])
    
    logger.info(f"Redirecting guest {guest_name} to: {zoom_url}")
    return redirect(zoom_url)


def build_simple_zoom_url_for_guest(conference, guest_name, guest_email):
    """
    Build a simple Zoom direct join URL for guest users
    """
    # Extract meeting ID from any Zoom URL format
    meeting_id = extract_meeting_id_from_any_zoom_url(conference.meeting_link)
    
    if not meeting_id:
        # If we can't extract meeting ID, use original link
        base_url = conference.meeting_link
    else:
        # Build clean direct join URL
        base_url = f"https://zoom.us/j/{meeting_id}"
    
    # Extract encoded password from original URL if available
    encoded_pwd = None
    if 'pwd=' in conference.meeting_link:
        from urllib.parse import urlparse, parse_qs
        parsed_url = urlparse(conference.meeting_link)
        query_params = parse_qs(parsed_url.query)
        if 'pwd' in query_params:
            encoded_pwd = query_params['pwd'][0]
    
    # Add URL parameters
    params = {}
    
    # Add password - prefer encoded password from URL, fallback to meeting_password
    if encoded_pwd:
        params['pwd'] = encoded_pwd
    elif conference.meeting_password:
        params['pwd'] = conference.meeting_password
    
    # Add guest name
    params['uname'] = guest_name
    
    # Add email if provided
    if guest_email:
        params['email'] = guest_email
    
    # Build final URL
    if params:
        from urllib.parse import urlencode
        param_string = urlencode(params)
        zoom_url = f"{base_url}?{param_string}"
    else:
        zoom_url = base_url
    
    return zoom_url

def create_direct_join_zoom_meeting(user, integration_id, title, description, start_datetime, end_datetime):
    """
    Create a Zoom meeting specifically configured for DIRECT JOIN without any registration
    This function guarantees that the generated meeting link allows immediate joining
    """
    try:
        # Get the integration - allow access to user's own integrations or branch integrations
        try:
            # First try to get user's own integration
            integration = ZoomIntegration.objects.get(id=integration_id, user=user)
        except ZoomIntegration.DoesNotExist:
            # If not found, try to get integration from same branch (excluding superadmin)
            if hasattr(user, 'branch') and user.branch:
                integration = ZoomIntegration.objects.exclude(user__role='superadmin').get(
                    id=integration_id, 
                    user__branch=user.branch, 
                    is_active=True
                )
            else:
                raise ZoomIntegration.DoesNotExist("Integration not found")
        
        # Calculate meeting duration in minutes
        duration = int((end_datetime - start_datetime).total_seconds() / 60)
        
        # Format the start time for Zoom API (ISO format)
        start_time = start_datetime.strftime('%Y-%m-%dT%H:%M:%S')
        
        logger.info(f"Creating DIRECT JOIN Zoom meeting: integration_id={integration.id}")
        
        # Check if using default credentials
        if integration.api_key == "your_zoom_api_key" or integration.api_secret == "your_zoom_api_secret":
            logger.error("Default Zoom credentials detected. Cannot create real meeting.")
            return {
                'success': False,
                'error': 'Please update your Zoom integration with valid API credentials in Account Settings.'
            }
        
        # Generate OAuth token for Zoom API authentication
        auth_token = get_zoom_oauth_token(integration.api_key, integration.api_secret, integration.account_id)
        if not auth_token:
            logger.error("Failed to obtain Zoom OAuth token")
            return {
                'success': False,
                'error': 'Could not authenticate with Zoom API. Please check your credentials in Account Settings.'
            }
        
        # Determine account ID
        account_id = integration.account_id or 'me'
        
        # Zoom API endpoint
        api_url = f'https://api.zoom.us/v2/users/{account_id}/meetings'
        
        # Prepare request headers
        headers = {
            'Authorization': f'Bearer {auth_token}',
            'Content-Type': 'application/json'
        }
        
        # ULTIMATE DIRECT JOIN PAYLOAD - No registration whatsoever
        payload = {
            'topic': title,
            'type': 2,  # Scheduled meeting
            'start_time': start_time,
            'duration': duration,
            'timezone': 'UTC',
            'agenda': description,
            'password': f"{random.randint(100000, 999999)}",  # Generate 6-digit meeting passcode
            'settings': {
                # ===== CORE DIRECT JOIN SETTINGS =====
                'approval_type': 2,  # No registration required (2 = no registration)
                'registration_type': 0,  # NO REGISTRATION REQUIRED
                'meeting_authentication': False,  # Allow guests (no Zoom account needed)
                'enforce_login': False,  # NO login required
                'enforce_login_domains': '',  # No domain restrictions
                'waiting_room': False,  # NO waiting room (direct entry)
                
                # ===== GUEST ACCESS MAXIMIZATION =====
                'join_before_host': True,  # Allow joining before host arrives
                'jbh_time': 10,  # Allow joining 10 minutes before scheduled time
                'use_pmi': False,  # Don't use Personal Meeting ID
                'alternative_hosts': '',  # No alternative host restrictions
                'close_registration': False,  # Keep registration "open" (though disabled)
                
                # ===== ACCESSIBILITY & EASE OF USE =====
                'allow_multiple_devices': True,  # Multiple devices per participant
                'show_share_button': True,  # Enable easy link sharing
                'mute_upon_entry': False,  # Don't auto-mute participants
                'host_video': True,  # Host video enabled
                'participant_video': True,  # Participant video enabled
                'audio': 'both',  # Allow both audio types
                
                # ===== Session SETTINGS (Minimal restrictions) =====
                'encryption_type': 'enhanced_encryption',  # Enhanced Session
                'private_meeting': False,  # Make meeting discoverable
                'internal_meeting': False,  # Not internal-only
                'cn_meeting': False,  # Not China-restricted
                'in_meeting': False,  # Not India-restricted
                
                # ===== RECORDING SETTINGS =====
                'auto_recording': 'cloud',  # Enable automatic cloud recording
                'cloud_recording': True,  # Explicit cloud recording
                'auto_recording_cloud': True,  # Force cloud recording
                'auto_recording_local': False,  # Disable local recording
                'record_play_own_voice': True,  # Record participant audio
                'record_repeat_caller': True,  # Record all participants
                'recording_authentication': False,  # No auth for recording access
                'recording_disclaimer': True,  # Show recording notice
                
                # ===== ADVANCED DIRECT ACCESS SETTINGS =====
                'focus_mode': False,  # Disable focus mode
                'breakout_room': False,  # No breakout rooms by default
                'global_dial_in_countries': ['US'],  # Allow phone dial-in
                'alternative_hosts_email_notification': False,  # No email notifications
                'registrants_confirmation_email': False,  # No confirmation emails
                'registrants_email_notification': False,  # No email notifications
                'request_permission_to_unmute_participants': False,  # Auto-allow unmute
                'registrants_restriction_type': 0,  # No registration restrictions
                
                # ===== ADDITIONAL BYPASS SETTINGS =====
                'contact_name': '',  # No contact required
                'contact_email': '',  # No contact email required
                'approval_type': 2,  # Re-emphasize no registration required
                'registration_type': 0,  # Re-emphasize no registration
                'global_dial_in_numbers': [],  # Basic dial-in access
                'pstn_password': '',  # No PSTN password
                
                # ===== ENHANCED ACCESSIBILITY =====
                'auto_recording': 'cloud',  # Ensure cloud recording
                'meeting_invitees': [],  # No specific invitees (open to all)
                'participant_video': True,  # Default video on
                'host_video': True,  # Host video on
                
                # ===== CHAT AND FILE SHARING SETTINGS =====
                'allow_participants_chat_with': 1,  # 1 = Everyone publicly and privately
                'allow_users_save_chats': 2,  # 2 = Everyone can save
                'chat_etiquette_tool': {
                    'enable': False,  # Don't restrict chat
                    'policies': []
                },
                'file_transfer': {
                    'enable': True,  # Enable file transfers in chat
                    'allow_all_file_types': True  # Allow all file types
                }
            }
        }
        
        # Make the API request to Zoom
        logger.info(f"Creating DIRECT JOIN meeting with enhanced payload")
        response = requests.post(api_url, headers=headers, json=payload)
        
        # Log response for debugging
        logger.info(f"Zoom API response: Status={response.status_code}")
        
        # Handle rate limiting
        if response.status_code == 429:
            logger.warning("Zoom API rate limit exceeded")
            return {
                'success': False, 
                'error': 'Zoom API rate limit exceeded. Please try again later.'
            }
            
        # Try alternative account ID if initial request fails
        if response.status_code in [401, 404] and account_id != 'me':
            logger.info("Trying alternative account ID: me")
            alt_api_url = 'https://api.zoom.us/v2/users/me/meetings'
            response = requests.post(alt_api_url, headers=headers, json=payload)
            logger.info(f"Alternative API response: Status={response.status_code}")
        
        # Handle error responses
        if response.status_code >= 400:
            error_msg = f"Zoom API error (HTTP {response.status_code})"
            try:
                error_data = response.json()
                if 'message' in error_data:
                    error_msg = f"Zoom API: {error_data['message']}"
            except:
                pass
            
            logger.error(f"Zoom API error: {error_msg}")
            return {
                'success': False,
                'error': error_msg
            }
        
        # Parse successful response
        meeting_data = response.json()
        
        # Get the join URL and ensure it's direct
        join_url = meeting_data.get('join_url')
        meeting_id = meeting_data.get('id')
        
        # Log meeting creation success
        logger.info(f"Successfully created DIRECT JOIN meeting: ID={meeting_id}, URL={join_url}")
        
        # Create simple direct join URL
        if join_url and meeting_id:
            # Ensure we have a proper direct join URL
            if 'register' in join_url:
                logger.warning(f"Registration URL detected, converting: {join_url}")
                join_url = force_convert_registration_url_to_direct_join(join_url)
                logger.info(f"Converted to direct join: {join_url}")
            
            # Create simple URL format with only meeting ID and password
            meeting_password = meeting_data.get('password', '')
            if meeting_password:
                # Extract domain and meeting ID
                domain_match = re.search(r'(https?://[^/]+)', join_url)
                domain = domain_match.group(1) if domain_match else 'https://zoom.us'
                
                # Extract meeting ID from URL
                meeting_id_match = re.search(r'/j/(\d+)', join_url)
                if meeting_id_match:
                    extracted_meeting_id = meeting_id_match.group(1)
                    simple_url = f"{domain}/j/{extracted_meeting_id}?pwd={meeting_password}"
                    
                    logger.info(f"Created simple direct join URL: {simple_url}")
                    
                    return {
                        'success': True,
                        'meeting_link': simple_url,
                        'original_join_url': join_url,  # Keep original for reference
                        'meeting_id': meeting_id,
                        'password': meeting_password,
                        'host_url': meeting_data.get('start_url'),
                        'direct_join': True,
                        'registration_required': False,
                        'simple_format': True  # Flag indicating simple format
                    }
            
            # If no password or couldn't extract meeting ID, use original URL
            logger.info(f"Using original direct join URL: {join_url}")
            
            return {
                'success': True,
                'meeting_link': join_url,
                'meeting_id': meeting_id,
                'password': meeting_data.get('password', ''),
                'host_url': meeting_data.get('start_url'),
                'direct_join': True,
                'registration_required': False
            }
        
        # Fallback return
        return {
            'success': True,
            'meeting_link': join_url,
            'meeting_id': meeting_id,
            'password': meeting_data.get('password', ''),
            'host_url': meeting_data.get('start_url'),
            'direct_join': True,
            'registration_required': False
        }
        
    except ZoomIntegration.DoesNotExist:
        return {'success': False, 'error': 'Integration not found'}
    except requests.exceptions.RequestException as e:
        logger.exception(f"Error making Zoom API request: {str(e)}")
        return {'success': False, 'error': f'Error connecting to Zoom API: {str(e)}'}
    except Exception as e:
        logger.exception(f"Error creating direct join Zoom meeting: {str(e)}")
        return {'success': False, 'error': str(e)}

def clean_zoom_url_format(conference):
    """Convert any Zoom URL to simple format: domain/j/meeting_id?pwd=password"""
    if not conference.meeting_link or 'zoom.us' not in conference.meeting_link:
        return conference.meeting_link
    
    # Extract the domain from the original URL
    domain_match = re.search(r'(https?://[^/]+)', conference.meeting_link)
    domain = domain_match.group(1) if domain_match else 'https://zoom.us'
    
    # Get meeting ID - try from stored field first, then extract from URL
    meeting_id = conference.meeting_id
    if not meeting_id:
        meeting_id = extract_meeting_id_from_any_zoom_url(conference.meeting_link)
    
    if not meeting_id:
        logger.warning(f"Could not extract meeting ID from conference {conference.id}")
        return conference.meeting_link
    
    # Check if this is a webinar (has /w/ in URL)
    is_webinar = '/w/' in conference.meeting_link
    
    # Build clean URL
    if is_webinar:
        clean_url = f"{domain}/w/{meeting_id}"
    else:
        clean_url = f"{domain}/j/{meeting_id}"
    
    # Add password if available
    password = conference.meeting_password
    if not password:
        # Try to extract password from current URL
        pwd_match = re.search(r'pwd=([^&]+)', conference.meeting_link)
        if pwd_match:
            password = pwd_match.group(1)
    
    if password:
        clean_url += f"?pwd={password}"
    
    logger.info(f"Cleaned Zoom URL for conference {conference.id}: {conference.meeting_link} -> {clean_url}")
    return clean_url



@login_required 
@require_POST
def evaluate_conference_rubric(request, conference_id):
    """Evaluate conference attendance using a rubric"""
    conference = get_object_or_404(Conference, id=conference_id)
    
    # Permission check - only instructors, admins, and superadmins can evaluate
    if request.user.role not in ['instructor', 'admin', 'superadmin', 'globaladmin'] and not request.user.is_superuser:
        return HttpResponseForbidden("You don't have permission to evaluate rubrics")
    
    # Check if the conference has a rubric
    if not conference.rubric:
        messages.error(request, 'This conference does not have a rubric attached.')
        return redirect('conferences:conference_detail', conference_id=conference.id)
    
    # Get the attendance record being evaluated
    attendance_id = request.POST.get('attendance_id')
    if not attendance_id:
        messages.error(request, 'No attendance record specified for evaluation.')
        return redirect('conferences:conference_detail', conference_id=conference.id)
    
    try:
        attendance = ConferenceAttendance.objects.get(id=attendance_id, conference=conference)
        # Ensure we're only evaluating learners
        if attendance.user.role != 'learner':
            messages.error(request, 'Only learner participants can be evaluated.')
            return redirect('conferences:conference_detail', conference_id=conference.id)
    except ConferenceAttendance.DoesNotExist:
        messages.error(request, 'Attendance record not found.')
        return redirect('conferences:conference_detail', conference_id=conference.id)
    
    # Import here to avoid circular imports
    from .models import ConferenceRubricEvaluation
    from lms_rubrics.models import RubricRating
    
    # Process each criterion evaluation
    for criterion in conference.rubric.criteria.all():
        criterion_id = criterion.id
        
        # Get form data for this criterion
        rating_id = request.POST.get(f'rating_{criterion_id}_{attendance.id}')
        points_str = request.POST.get(f'points_{criterion_id}_{attendance.id}', '0')
        comments = request.POST.get(f'comments_{criterion_id}_{attendance.id}', '')
        
        # Validate points
        try:
            points = float(points_str)
            if points < 0:
                points = 0
            if points > criterion.points:
                points = criterion.points
        except (ValueError, TypeError):
            points = 0
        
        # Delete any existing evaluation to ensure clean state
        ConferenceRubricEvaluation.objects.filter(
            conference=conference, 
            attendance=attendance, 
            criterion=criterion
        ).delete()
        
        # Create a new evaluation
        evaluation = ConferenceRubricEvaluation.objects.create(
            conference=conference,
            attendance=attendance,
            criterion=criterion,
            points=points,
            comments=comments,
            evaluated_by=request.user
        )
        
        # Set the rating if one was selected
        if rating_id:
            try:
                rating = RubricRating.objects.get(id=rating_id, criterion=criterion)
                evaluation.rating = rating
                # Keep the instructor-entered points, don't overwrite with rating points
                # This allows instructors to select a rating but adjust points as needed
                evaluation.save()
            except RubricRating.DoesNotExist:
                pass
    
    # Handle overall feedback for conference
    overall_feedback = request.POST.get('overall_feedback', '').strip()
    audio_feedback = request.FILES.get('audio_feedback')
    video_feedback = request.FILES.get('video_feedback')
    
    # Create or update overall feedback if provided
    if overall_feedback or audio_feedback or video_feedback:
        if conference.rubric and attendance.user:
            feedback_data = {
                'feedback': overall_feedback,
                'is_private': False,
                'created_by': request.user,
                'student': attendance.user,
                'rubric': conference.rubric,
                'conference': conference
            }
            
            # Add files if provided
            if audio_feedback:
                feedback_data['audio_feedback'] = audio_feedback
            if video_feedback:
                feedback_data['video_feedback'] = video_feedback
            
            # Update or create feedback
            overall_feedback_obj, created = RubricOverallFeedback.objects.update_or_create(
                conference=conference,
                student=attendance.user,
                defaults=feedback_data
            )
    
    messages.success(request, f'Rubric evaluation saved successfully for {attendance.user.get_full_name()}.')
    return redirect('conferences:conference_detail', conference_id=conference.id)


@login_required
def bulk_evaluate_conference(request, conference_id):
    """Bulk evaluate multiple conference attendees using rubric"""
    from .models import ConferenceAttendance  # Import at top
    conference = get_object_or_404(Conference, id=conference_id)
    
    # Permission check
    if request.user.role not in ['instructor', 'admin', 'superadmin', 'globaladmin'] and not request.user.is_superuser:
        return HttpResponseForbidden("You don't have permission to evaluate rubrics")
    
    # Check if the conference has a rubric
    if not conference.rubric:
        messages.error(request, 'This conference does not have a rubric attached.')
        return redirect('conferences:conference_detail', conference_id=conference.id)
    
        # Get all attendances for this conference (filter for learners only)
    # Include learners who have evidence of participation - More inclusive approach
    
    # First, get all learners with ConferenceParticipant records
    participant_user_ids = conference.participants.filter(
        user__role='learner',
        user__isnull=False,  # Exclude guest participants
    ).values_list('user_id', flat=True)
    
    # Create attendance records for participants who don't have them
    for user_id in participant_user_ids:
        if not conference.attendances.filter(user_id=user_id).exists():
            # Create a basic attendance record for this participant
            participant = conference.participants.filter(user_id=user_id).first()
            if participant:
                ConferenceAttendance.objects.get_or_create(
                    conference=conference,
                    user=participant.user,
                    defaults={
                        'participant_id': participant.participant_id,
                        'join_time': participant.join_timestamp,
                        'leave_time': participant.leave_timestamp,
                        'duration_minutes': participant.total_duration_minutes or 0,
                        'attendance_status': 'present',  # Set to present since they participated
                        'device_info': participant.tracking_data or {}
                    }
                )
    
    # More inclusive filtering for learner attendances
    # Include learners who have ANY evidence of participation:
    # 1. They have a ConferenceParticipant record (regardless of duration)
    # 2. They have a ConferenceAttendance record with any join time or duration
    # 3. They have been marked as present or late in attendance
    attendances = conference.attendances.select_related('user').filter(
        user__role='learner'
    ).filter(
        Q(user_id__in=participant_user_ids) |  # Has participant record
        Q(join_time__isnull=False) |  # Has join time
        Q(duration_minutes__gt=0) |  # Has duration > 0
        Q(attendance_status__in=['present', 'late'])  # Marked as present/late
    ).distinct().order_by('user__first_name', 'user__last_name')
    
    if request.method == 'POST':
        # Import here to avoid circular imports
        from .models import ConferenceRubricEvaluation
        from lms_rubrics.models import RubricRating
        
        # Process bulk evaluation
        for attendance in attendances:
            for criterion in conference.rubric.criteria.all():
                criterion_id = criterion.id
                
                # Get form data for this criterion and attendance
                rating_id = request.POST.get(f'rating_{criterion_id}_{attendance.id}')
                points_str = request.POST.get(f'points_{criterion_id}_{attendance.id}', '0')
                comments = request.POST.get(f'comments_{criterion_id}_{attendance.id}', '')
                
                # Validate points
                try:
                    points = float(points_str)
                    if points < 0:
                        points = 0
                    if points > criterion.points:
                        points = criterion.points
                except (ValueError, TypeError):
                    points = 0
                
                # Delete any existing evaluation
                ConferenceRubricEvaluation.objects.filter(
                    conference=conference, 
                    attendance=attendance,
                    criterion=criterion
                ).delete()
                
                # Create a new evaluation
                evaluation = ConferenceRubricEvaluation.objects.create(
                    conference=conference,
                    attendance=attendance,
                    criterion=criterion,
                    points=points,
                    comments=comments,
                    evaluated_by=request.user
                )
                
                # Set the rating if one was selected
                if rating_id:
                    try:
                        rating = RubricRating.objects.get(id=rating_id, criterion=criterion)
                        evaluation.rating = rating
                        # Keep the instructor-entered points, don't overwrite with rating points
                        # This allows instructors to select a rating but adjust points as needed
                        evaluation.save()
                    except RubricRating.DoesNotExist:
                        pass
        
        messages.success(request, f'Bulk evaluation saved successfully for {len(attendances)} attendees.')
        return redirect('conferences:conference_scores', conference_id=conference_id)
    
    # Get existing evaluations for this conference
    from .models import ConferenceRubricEvaluation
    evaluations = ConferenceRubricEvaluation.objects.filter(
        conference=conference,
        attendance__in=attendances
    ).select_related('attendance', 'attendance__user', 'criterion', 'rating', 'evaluated_by')
    
    # Group evaluations by attendance and criterion
    evaluations_by_attendance = {}
    for evaluation in evaluations:
        attendance_key = evaluation.attendance.id
        if attendance_key not in evaluations_by_attendance:
            evaluations_by_attendance[attendance_key] = {}
        evaluations_by_attendance[attendance_key][evaluation.criterion.id] = evaluation
    
    # Define breadcrumbs
    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': reverse('conferences:conference_list'), 'label': 'Conferences', 'icon': 'fa-video'},
        {'label': conference.title, 'icon': 'fa-file-alt'},
        {'label': 'Bulk Evaluate', 'icon': 'fa-check-circle'}
    ]
    
    context = {
        'conference': conference,
        'rubric': conference.rubric,
        'attendances': attendances,
        'evaluations_by_attendance': evaluations_by_attendance,
        'title': f'Bulk Evaluate: {conference.title}',
        'description': 'Evaluate multiple attendees at once',
        'breadcrumbs': breadcrumbs
    }
    
    return render(request, 'conferences/bulk_evaluate.html', context)


@login_required
def conference_scores(request, conference_id):
    """View all rubric scores for conference attendees"""
    conference = get_object_or_404(Conference, id=conference_id)
    
    # Permission check
    if request.user.role not in ['instructor', 'admin', 'superadmin', 'globaladmin'] and not request.user.is_superuser:
        return HttpResponseForbidden("You don't have permission to view scores")
    
    # Check if the conference has a rubric
    if not conference.rubric:
        messages.error(request, 'This conference does not have a rubric attached.')
        return redirect('conferences:conference_detail', conference_id=conference.id)
    
    # Import here to avoid circular imports
    from .models import ConferenceRubricEvaluation
    
    # Get all evaluations for this conference (filter for learners only)
    evaluations = ConferenceRubricEvaluation.objects.filter(
        conference=conference,
        attendance__user__role='learner'  # Only show evaluations for learners
    ).select_related('attendance', 'attendance__user', 'criterion', 'evaluated_by').order_by(
        'attendance__user__first_name', 'attendance__user__last_name', 'criterion__position'
    )
    
    # Group evaluations by attendance
    attendance_scores = {}
    for evaluation in evaluations:
        attendance_id = evaluation.attendance.id
        if attendance_id not in attendance_scores:
            attendance_scores[attendance_id] = {
                'attendance': evaluation.attendance,
                'evaluations': [],
                'total_points': 0
            }
        attendance_scores[attendance_id]['evaluations'].append(evaluation)
        attendance_scores[attendance_id]['total_points'] += evaluation.points
    
    # Define breadcrumbs
    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': reverse('conferences:conference_list'), 'label': 'Conferences', 'icon': 'fa-video'},
        {'label': conference.title, 'icon': 'fa-file-alt'},
        {'label': 'Rubric Scores', 'icon': 'fa-chart-bar'}
    ]
    
    context = {
        'conference': conference,
        'rubric': conference.rubric,
        'attendance_scores': attendance_scores.values(),
        'title': f'Rubric Scores: {conference.title}',
        'description': 'View all attendee rubric evaluations',
        'breadcrumbs': breadcrumbs
    }
    
    return render(request, 'conferences/conference_scores.html', context)

def force_convert_registration_url_to_direct_join(registration_url):
    """Aggressively convert any Zoom registration URL to direct join format"""
    if not registration_url or 'zoom.us' not in registration_url:
        return registration_url
    
    logger.info(f"FORCE CONVERSION: Starting with URL: {registration_url}")
    
    # Extract the domain from the original URL
    domain_match = re.search(r'(https?://[^/]+)', registration_url)
    domain = domain_match.group(1) if domain_match else 'https://zoom.us'
    
    # Method 1: Check if it's already a direct join URL
    if '/j/' in registration_url and 'register' not in registration_url:
        logger.info(f"FORCE CONVERSION: Already a direct join URL: {registration_url}")
        return registration_url
    
    # Method 2: Extract registration ID from URL like j8PvlJtOR7aAhUhdyYw-Cw
    registration_id = None
    reg_match = re.search(r'zoom\.us/meeting/register/([A-Za-z0-9_-]+)', registration_url)
    if reg_match:
        registration_id = reg_match.group(1)
        logger.info(f"FORCE CONVERSION: Found registration ID: {registration_id}")
        
        # For registration IDs like "j8PvlJtOR7aAhUhdyYw-Cw", try multiple approaches
        conversion_attempts = [
            # Attempt 1: Use registration ID directly as meeting ID
            f"{domain}/j/{registration_id}",
            # Attempt 2: Try webinar format
            f"{domain}/w/{registration_id}",
            # Attempt 3: Try removing first character if it starts with 'j'
            f"{domain}/j/{registration_id[1:]}" if registration_id.startswith('j') else None,
        ]
        
        # Try each conversion attempt
        for attempt in conversion_attempts:
            if attempt:
                # Extract password from original URL if present
                password_match = re.search(r'pwd=([^&]+)', registration_url)
                if password_match:
                    attempt += f"?pwd={password_match.group(1)}"
                
                logger.info(f"FORCE CONVERSION: Attempting: {registration_url} -> {attempt}")
                return attempt
    
    # Method 3: Try to extract numeric meeting ID from URL
    numeric_id = extract_meeting_id_from_any_zoom_url(registration_url)
    if numeric_id:
        direct_url = f"{domain}/j/{numeric_id}"
        
        # Add password if present
        password_match = re.search(r'pwd=([^&]+)', registration_url)
        if password_match:
            direct_url += f"?pwd={password_match.group(1)}"
            
        logger.info(f"FORCE CONVERSION: Using numeric ID: {registration_url} -> {direct_url}")
        return direct_url
    
    # Method 4: Last resort - simple string replacement
    if '/meeting/register/' in registration_url:
        fallback_url = registration_url.replace('/meeting/register/', '/j/')
        
        # Clean up query parameters, keep only pwd
        if '?' in fallback_url:
            base_url, query_string = fallback_url.split('?', 1)
            password_match = re.search(r'pwd=([^&]+)', query_string)
            if password_match:
                fallback_url = f"{base_url}?pwd={password_match.group(1)}"
            else:
                fallback_url = base_url
        
        logger.info(f"FORCE CONVERSION: Fallback replacement: {registration_url} -> {fallback_url}")
        return fallback_url
    
    # If all else fails, return original URL with warning
    logger.warning(f"FORCE CONVERSION: Could not convert registration URL: {registration_url}")
    return registration_url

@csrf_protect
def auto_register_and_join(request, conference_id):
    """
    Auto-register authenticated users to Zoom and provide direct join link
    No guest participation allowed - only authenticated users
    """
    try:
        conference = get_object_or_404(Conference, id=conference_id)
    except:
        messages.error(request, f'Conference with ID {conference_id} does not exist or has been deleted.')
        return redirect('conferences:conference_list')
    
    # Check if user is authenticated - return JSON for AJAX requests
    if not request.user.is_authenticated:
        if request.headers.get('Content-Type') == 'application/json' or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False,
                'error': 'Authentication required to join conferences.',
                'redirect_url': f"/login/?next=/conferences/{conference_id}/"
            }, status=401)
        else:
            return redirect('login')
    
    user = request.user
    
    # Handle GET requests - redirect to conference detail page
    if request.method == 'GET':
        return redirect('conferences:conference_detail', conference_id=conference.id)
    
    # Only allow POST requests for actual join attempts
    if request.method != 'POST':
        return JsonResponse({
            'success': False,
            'error': 'Only POST requests are allowed for joining conferences.'
        }, status=405)
    
    # Check if conference is available for user
    if user.role == 'learner':
        if not conference.is_available_for_user(user):
            return JsonResponse({
                'success': False,
                'error': 'You do not have permission to access this conference.'
            }, status=403)
    
    # Create participant tracking record
    try:
        # Check if participant already exists for this user and conference
        existing_participant = ConferenceParticipant.objects.filter(
            conference=conference,
            user=user
        ).first()
        
        if existing_participant:
            # Update existing participant
            participant = existing_participant
            participant.join_timestamp = timezone.now()
            participant.join_method = 'auto_registered'
            participant.ip_address = request.META.get('REMOTE_ADDR')
            participant.user_agent = request.META.get('HTTP_USER_AGENT', '')
            participant.participation_status = 'clicked_join'
            participant.sync_status = 'pending'
            
            # Safely update tracking_data
            if not participant.tracking_data:
                participant.tracking_data = {}
            
            participant.tracking_data.update({
                'user_id': user.id,
                'username': user.username,
                'role': user.role,
                'branch': user.branch.name if user.branch else None,
                'join_timestamp': timezone.now().isoformat(),
                'join_method': 'auto_registered',
                'rejoin': True
            })
            participant.save()
            created = False
        else:
            # Create new participant
            participant_id = f"lms_{conference.id}_{user.username}_{uuid.uuid4().hex[:8]}"
            
            participant = ConferenceParticipant.objects.create(
                conference=conference,
                user=user,
                participant_id=participant_id,
                session_token=uuid.uuid4().hex,
                display_name=user.get_full_name() or user.username,
                email_address=user.email,
                join_timestamp=timezone.now(),
                join_method='auto_registered',
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                participation_status='clicked_join',
                sync_status='pending',
                tracking_data={
                    'user_id': user.id,
                    'username': user.username,
                    'role': user.role,
                    'branch': user.branch.name if user.branch else None,
                    'join_timestamp': timezone.now().isoformat(),
                    'join_method': 'auto_registered'
                }
            )
            created = True
        
        logger.info(f"User {user.username} initiated auto-registration for conference: {conference.title}")
        
    except Exception as e:
        logger.error(f"Error creating participant record: {str(e)}")
        logger.error(f"Error type: {type(e).__name__}")
        logger.error(f"Conference ID: {conference.id}, User: {user.username}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return JsonResponse({
            'success': False,
            'error': 'Failed to track participation.'
        }, status=500)
    
    # Check if meeting platform is Zoom
    if conference.meeting_platform != 'zoom':
        # For non-Zoom platforms, return the regular meeting link
        return JsonResponse({
            'success': True,
            'join_url': conference.meeting_link,
            'message': 'Direct join link ready.',
            'platform': conference.meeting_platform
        })
    
    # For Zoom meetings, attempt auto-registration
    registration_result = register_user_on_zoom_with_direct_join(conference, user)
    
    if registration_result.get('success'):
        # Update participant status
        participant.participation_status = 'redirected_to_platform'
        participant.tracking_data.update({
            'platform_metadata': {
                'registration_id': registration_result.get('registrant_id'),
                'registration_time': timezone.now().isoformat()
            }
        })
        participant.save()
        
        # Get the join URL (either from registration or build it)
        if registration_result.get('join_url'):
            join_url = registration_result['join_url']
        else:
            # Build direct join URL with user info
            join_url = build_direct_zoom_url_for_registered_user(conference, user, registration_result)
        
        return JsonResponse({
            'success': True,
            'join_url': join_url,
            'message': 'You have been registered for the meeting. Click to join directly.',
            'registration_data': {
                'registrant_id': registration_result.get('registrant_id'),
                'registered': True
            }
        })
    else:
        # Registration failed - but still provide a direct join link
        logger.warning(f"Zoom registration failed for user {user.username}: {registration_result.get('error')}")
        
        # Build fallback direct join URL using the correct function
        join_url = build_direct_zoom_url_for_registered_user(conference, user, registration_result)
        
        return JsonResponse({
            'success': True,
            'join_url': join_url,
            'message': 'Direct join link ready.',
            'warning': 'Auto-registration unavailable, but you can still join the meeting.',
            'registration_data': {
                'registered': False,
                'fallback': True
            }
        })


def register_user_on_zoom_with_direct_join(conference, user):
    """
    Register user on Zoom platform and get direct join URL
    Enhanced version that ensures direct joining without forms
    """
    try:
        # Get meeting ID
        meeting_id = conference.meeting_id
        if not meeting_id:
            meeting_id = extract_meeting_id_from_any_zoom_url(conference.meeting_link)
            if meeting_id:
                conference.meeting_id = meeting_id
                conference.save(update_fields=['meeting_id'])
        
        if not meeting_id:
            return {'success': False, 'error': 'No meeting ID found'}
        
        # Get Zoom integration
        integration = None
        if hasattr(conference.created_by, 'zoom_integrations'):
            integration = conference.created_by.zoom_integrations.filter(is_active=True).first()
        
        if not integration and hasattr(conference.created_by, 'branch') and conference.created_by.branch:
            integration = ZoomIntegration.objects.filter(
                user__branch=conference.created_by.branch,
                is_active=True
            ).first()
        
        if not integration:
            return {'success': False, 'error': 'No Zoom integration found'}
        
        # Get OAuth token
        auth_token = get_zoom_oauth_token(integration.api_key, integration.api_secret, integration.account_id)
        if not auth_token:
            return {'success': False, 'error': 'Failed to authenticate with Zoom'}
        
        # Check meeting settings first
        check_url = f'https://api.zoom.us/v2/meetings/{meeting_id}'
        headers = {
            'Authorization': f'Bearer {auth_token}',
            'Content-Type': 'application/json'
        }
        
        meeting_response = requests.get(check_url, headers=headers)
        
        if meeting_response.status_code == 200:
            meeting_data = meeting_response.json()
            
            # If meeting doesn't require registration, return direct join
            if not meeting_data.get('settings', {}).get('approval_type', 0) == 1:
                return {
                    'success': True,
                    'message': 'Meeting does not require registration',
                    'no_registration_needed': True,
                    'meeting_data': meeting_data
                }
        
        # Prepare registration data
        registration_data = {
            'first_name': user.first_name or user.username,
            'last_name': user.last_name or 'User',
            'email': user.email,
            'auto_approve': True,  # Request auto-approval
        }
        
        # API endpoint for registration
        api_url = f'https://api.zoom.us/v2/meetings/{meeting_id}/registrants'
        
        logger.info(f"Auto-registering user {user.username} for Zoom meeting {meeting_id}")
        
        # Make registration API call
        response = requests.post(api_url, headers=headers, json=registration_data)
        
        if response.status_code == 201:
            # Registration successful
            registration_response = response.json()
            logger.info(f"Successfully registered user {user.username} for meeting {meeting_id}")
            
            return {
                'success': True,
                'registrant_id': registration_response.get('registrant_id'),
                'join_url': registration_response.get('join_url'),
                'registration_data': registration_response
            }
        elif response.status_code == 404:
            # Meeting not found or registration not enabled
            return {
                'success': False,
                'error': 'Meeting registration not available',
                'no_registration': True
            }
        else:
            logger.error(f"Failed to register user: {response.status_code} - {response.text}")
            return {
                'success': False,
                'error': f'Registration failed: {response.status_code}'
            }
            
    except Exception as e:
        logger.exception(f"Error in auto-registration: {str(e)}")
        return {'success': False, 'error': str(e)}


def build_direct_zoom_url_for_registered_user(conference, user, registration_result):
    """
    Build a direct Zoom join URL for registered users
    Uses Zoom Web Client SDK format to bypass entry screens
    """
    meeting_id = conference.meeting_id or extract_meeting_id_from_any_zoom_url(conference.meeting_link)
    
    if not meeting_id:
        return conference.meeting_link
    
    # Extract password from various sources
    password = None
    
    # Method 1: Check if password is in the original URL
    if 'pwd=' in conference.meeting_link:
        parsed_url = urlparse(conference.meeting_link)
        query_params = parse_qs(parsed_url.query)
        if 'pwd' in query_params:
            password = query_params['pwd'][0]
            logger.info(f"Found password in URL: {password[:4]}...")
    
    # Method 2: Use stored meeting password
    if not password and conference.meeting_password:
        password = conference.meeting_password
        logger.info(f"Using stored password: {password[:4]}...")
    
    # Method 3: Try to extract from meeting data if available
    if not password and registration_result.get('meeting_data'):
        meeting_data = registration_result.get('meeting_data', {})
        if 'password' in meeting_data:
            password = meeting_data['password']
        elif 'encrypted_password' in meeting_data:
            password = meeting_data['encrypted_password']
    
    # Use Zoom Web Client SDK format for DIRECT joining (bypasses entry screen)
    # This format skips the meeting entry form entirely
    if password:
        # URL format that bypasses the entry screen
        base_url = f"https://zoom.us/wc/join/{meeting_id}"
        
        params = {
            'pwd': password,
            'uname': user.get_full_name() or user.username,
            'email': user.email
        }
        
        # Add registration token if available
        if registration_result.get('registrant_id'):
            params['tk'] = registration_result['registrant_id']
        
        # Add return URL for proper redirection after meeting
        from django.urls import reverse
        from django.conf import settings
        # Use a safer approach to construct the absolute URL
        base_url_setting = getattr(settings, 'BASE_URL', f"https://{getattr(settings, 'PRIMARY_DOMAIN', 'localhost')}")
        return_url = f"{base_url_setting}{reverse('conferences:conference_redirect_handler', args=[conference.id])}"
        params['return_url'] = return_url
        
        # Add LMS tracking parameters
        params['lms_user_id'] = str(user.id)
        params['lms_conference_id'] = str(conference.id)
        params['lms_return_handler'] = 'true'
        
        param_string = urlencode(params)
        # Use the correct Zoom base URL, not the LMS base URL
        zoom_base_url = f"https://zoom.us/wc/join/{meeting_id}"
        direct_url = f"{zoom_base_url}?{param_string}"
        
        logger.info(f"Generated direct bypass URL for user {user.username}")
        return direct_url
    else:
        # Fallback to standard format if no password found
        logger.warning(f"No password found for meeting {meeting_id}, using standard URL")
        base_url = f"https://zoom.us/j/{meeting_id}"
        
        params = {
            'uname': user.get_full_name() or user.username,
            'email': user.email
        }
        
        if registration_result.get('registrant_id'):
            params['tk'] = registration_result['registrant_id']
        
        # Add return URL for proper redirection after meeting
        from django.urls import reverse
        from django.conf import settings
        # Use a safer approach to construct the absolute URL
        base_url_setting = getattr(settings, 'BASE_URL', f"https://{getattr(settings, 'PRIMARY_DOMAIN', 'localhost')}")
        return_url = f"{base_url_setting}{reverse('conferences:conference_redirect_handler', args=[conference.id])}"
        params['return_url'] = return_url
        
        # Add LMS tracking parameters
        params['lms_user_id'] = str(user.id)
        params['lms_conference_id'] = str(conference.id)
        params['lms_return_handler'] = 'true'
        
        param_string = urlencode(params)
        # Use the correct Zoom base URL, not the LMS base URL
        zoom_base_url = f"https://zoom.us/j/{meeting_id}"
        return f"{zoom_base_url}?{param_string}"

@login_required
def upload_conference_file(request, conference_id):
    """Handle file uploads from conference participants"""
    conference = get_object_or_404(Conference, id=conference_id)
    
    # Check if user has access to this conference
    if request.user.role == 'learner':
        if not conference.is_available_for_user(request.user):
            return JsonResponse({
                'success': False,
                'error': 'You do not have permission to access this conference.'
            }, status=403)
    
    if request.method == 'POST':
        form = ConferenceFileUploadForm(request.POST, request.FILES)
        if form.is_valid():
            file = form.cleaned_data['file']
            description = form.cleaned_data.get('description', '')
            
            # Create ConferenceFile record
            import os
            from django.core.files.storage import default_storage
            from django.core.files.base import ContentFile
            
            # Generate unique filename
            import uuid
            file_extension = os.path.splitext(file.name)[1]
            unique_filename = f"{uuid.uuid4().hex}{file_extension}"
            
            # Save file
            file_path = f"conference_files/{conference.id}/{unique_filename}"
            saved_path = default_storage.save(file_path, ContentFile(file.read()))
            
            # Get file URL
            file_url = request.build_absolute_uri(default_storage.url(saved_path))
            
            # Create ConferenceFile record
            conference_file = ConferenceFile.objects.create(
                conference=conference,
                shared_by=request.user,
                filename=file.name,
                original_filename=file.name,
                file_url=file_url,
                file_size=file.size,
                file_type=file_extension.lower().replace('.', ''),
                mime_type=file.content_type,
                local_file=saved_path,
                shared_at=timezone.now()
            )
            
            # Register file in media database for tracking
            try:
                from lms_media.utils import register_media_file
                register_media_file(
                    file_path=saved_path,
                    uploaded_by=request.user,
                    source_type='conference_file',
                    source_model='ConferenceFile',
                    source_object_id=conference_file.id,
                    course=getattr(conference, 'course', None),
                    filename=file.name,
                    description=f'Conference file for: {conference.title}'
                )
            except Exception as e:
                logger.error(f"Error registering conference file in media database: {str(e)}")
            
            # Return success response
            return JsonResponse({
                'success': True,
                'message': 'File uploaded successfully',
                'file': {
                    'id': conference_file.id,
                    'filename': conference_file.filename,
                    'file_url': conference_file.file_url,
                    'shared_by': conference_file.shared_by.get_full_name(),
                    'shared_at': conference_file.shared_at.strftime('%Y-%m-%d %H:%M:%S'),
                    'file_size': conference_file.file_size,
                    'description': description
                }
            })
        else:
            # Return form errors
            errors = {}
            for field, error_list in form.errors.items():
                errors[field] = error_list[0] if error_list else 'Invalid field'
            
            return JsonResponse({
                'success': False,
                'errors': errors
            }, status=400)
    
    # GET request - return upload form HTML
    form = ConferenceFileUploadForm()
    html = render_to_string('conferences/partials/file_upload_form.html', {
        'form': form,
        'conference': conference
    }, request=request)
    
    return JsonResponse({
        'success': True,
        'html': html
    })

def rematch_unmatched_chat_messages(conference):
    """Re-match unmatched chat messages to LMS users, with improved learner matching"""
    from django.contrib.auth import get_user_model
    import logging
    
    User = get_user_model()
    logger = logging.getLogger(__name__)
    
    # Get all unmatched chat messages for this conference
    unmatched_messages = ConferenceChat.objects.filter(
        conference=conference,
        sender__isnull=True
    )
    
    if not unmatched_messages.exists():
        return 0
    
    # Get all users who have participated in this conference (learners, instructors, etc.)
    # Use a different approach to avoid queryset combination issues
    potential_user_ids = set()
    
    # Get user IDs from participants
    participant_user_ids = ConferenceParticipant.objects.filter(
        conference=conference,
        user__isnull=False
    ).values_list('user_id', flat=True)
    potential_user_ids.update(participant_user_ids)
    
    # Get user IDs from attendance
    attendance_user_ids = ConferenceAttendance.objects.filter(
        conference=conference
    ).values_list('user_id', flat=True)
    potential_user_ids.update(attendance_user_ids)
    
    # Get user IDs from same branch
    if conference.created_by.branch:
        branch_user_ids = User.objects.filter(
            branch=conference.created_by.branch
        ).values_list('id', flat=True)
        potential_user_ids.update(branch_user_ids)
    
    # Get all potential users in one query
    potential_users = User.objects.filter(id__in=potential_user_ids)
    
    matched_count = 0
    
    for message in unmatched_messages:
        sender_name = message.sender_name.strip()
        if not sender_name or len(sender_name) < 2:
            continue
            
        matched_user = None
        
        # Method 1: Exact full name match (case insensitive) - MOST RELIABLE
        for user in potential_users:
            user_full_name = user.get_full_name()
            if user_full_name and user_full_name.lower().strip() == sender_name.lower().strip():
                matched_user = user
                logger.info(f"Exact match: {sender_name} -> {user.username} ({user.role})")
                break
        
        # Method 2: Try first name + last name combinations (more precise than instructor variations)
        if not matched_user:
            name_parts = sender_name.split()
            if len(name_parts) >= 2:
                first_name = name_parts[0]
                last_name = name_parts[-1]
                
                for user in potential_users:
                    if (user.first_name.lower() == first_name.lower() and 
                        user.last_name.lower() == last_name.lower()):
                        matched_user = user
                        logger.info(f"First+Last match: {sender_name} -> {user.username} ({user.role})")
                        break
        
        # Method 3: Try username-based matching (exact username match)
        if not matched_user:
            clean_sender_name = sender_name.replace(' ', '').lower()
            for user in potential_users:
                if user.username.lower() == clean_sender_name:
                    matched_user = user
                    logger.info(f"Username match: {sender_name} -> {user.username} ({user.role})")
                    break
        

        
        # Update the message if we found a match
        if matched_user:
            message.sender = matched_user
            message.save(update_fields=['sender'])
            matched_count += 1
            logger.info(f" Matched chat message: '{sender_name}' -> {matched_user.username} ({matched_user.role})")
    
    logger.info(f"Re-matched {matched_count} out of {unmatched_messages.count()} unmatched chat messages")
    return matched_count


@login_required
def return_from_meeting(request, conference_id):
    """
    Handle users returning from external meeting platforms (Zoom, Teams, etc.)
    Redirect them to the conference detail page with a welcome back message
    """
    conference = get_object_or_404(Conference, id=conference_id)
    
    # Update participant status to indicate they've returned
    try:
        participant = ConferenceParticipant.objects.filter(
            conference=conference,
            user=request.user
        ).first()
        
        if participant:
            # Update the leave timestamp if it's not already set
            if not participant.leave_timestamp:
                participant.leave_timestamp = timezone.now()
                participant.participation_status = 'left_meeting'
                participant.save(update_fields=['leave_timestamp', 'participation_status'])
                logger.info(f"Updated participant {request.user.username} return status for conference {conference.id}")
    except Exception as e:
        logger.error(f"Error updating participant return status: {str(e)}")
    
    # Add a welcome back message
    messages.success(request, f'Welcome back! You have returned from the "{conference.title}" meeting.')
    
    # Redirect to conference detail page
    return redirect('conferences:conference_detail', conference_id=conference.id)


@login_required
def conference_redirect_handler(request, conference_id):
    """
    Enhanced redirect handler for conference returns with better error handling
    and multiple fallback options
    """
    try:
        conference = get_object_or_404(Conference, id=conference_id)
    except:
        messages.error(request, f'Conference with ID {conference_id} does not exist or has been deleted.')
        return redirect('conferences:conference_list')
    
    user = request.user
    
    # Check if user has permission to access this conference
    if not conference.is_available_for_user(user):
        messages.error(request, 'You do not have permission to access this conference.')
        return redirect('conferences:conference_list')
    
    # Update participant status
    try:
        participant = ConferenceParticipant.objects.filter(
            conference=conference,
            user=user
        ).first()
        
        if participant:
            # Mark as returned from meeting
            participant.participation_status = 'left_meeting'
            if not participant.leave_timestamp:
                participant.leave_timestamp = timezone.now()
            participant.save(update_fields=['participation_status', 'leave_timestamp'])
            
            # Add tracking data for analytics
            if not participant.tracking_data:
                participant.tracking_data = {}
            participant.tracking_data.update({
                'returned_at': timezone.now().isoformat(),
                'return_method': 'direct_url',
                'user_agent': request.META.get('HTTP_USER_AGENT', ''),
                'ip_address': request.META.get('REMOTE_ADDR')
            })
            participant.save(update_fields=['tracking_data'])
            
    except Exception as e:
        logger.error(f"Error updating participant return status: {str(e)}")
    
    # Determine the best redirect destination based on user role
    if user.role == 'learner':
        # For learners, redirect to their dashboard or the conference detail
        next_url = request.GET.get('next', 'conferences:conference_detail')
        if next_url == 'dashboard':
            return redirect('dashboard_learner')
        else:
            return redirect('conferences:conference_detail', conference_id=conference.id)
    elif user.role in ['instructor', 'admin', 'superadmin']:
        # For instructors/admins, redirect to conference detail for management
        return redirect('conferences:conference_detail', conference_id=conference.id)
    else:
        # Fallback to conference list
        return redirect('conferences:conference_list')

# Health Check API Endpoints for Conference Sync Monitoring
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from conferences.utils.sync_resilience import SyncHealthChecker, SyncRecoveryManager

@csrf_protect
@require_http_methods(["GET"])
def health_check_conference_sync(request, conference_id=None):
    """
    API endpoint for checking conference sync health
    
    GET /conferences/health-check/ - System-wide health
    GET /conferences/health-check/<conference_id>/ - Specific conference health
    """
    try:
        if conference_id:
            # Check specific conference
            health_data = SyncHealthChecker.check_conference_sync_health(conference_id)
            return JsonResponse({
                'status': 'success',
                'conference_health': health_data
            })
        else:
            # System-wide health check
            system_health = SyncHealthChecker.get_system_wide_health()
            
            # Determine overall system status
            total = system_health['total_conferences']
            if total == 0:
                overall_status = 'no_data'
            elif system_health['critical'] > 0:
                overall_status = 'critical'
            elif system_health['warning'] > total * 0.2:  # More than 20% warnings
                overall_status = 'degraded'
            else:
                overall_status = 'healthy'
            
            return JsonResponse({
                'status': 'success',
                'overall_status': overall_status,
                'system_health': system_health,
                'timestamp': timezone.now().isoformat()
            })
            
    except Exception as e:
        logger.error(f"Health check error: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'error': str(e)
        }, status=500)

@csrf_protect
@require_http_methods(["POST"])
def auto_recover_conference_api(request, conference_id):
    """
    API endpoint for triggering automatic recovery of a conference
    
    POST /conferences/auto-recover/<conference_id>/
    """
    try:
        # Check if user has permission (admin or instructor)
        if not request.user.is_authenticated:
            return JsonResponse({
                'status': 'error',
                'error': 'Authentication required'
            }, status=401)
        
        if not request.user.role in ['globaladmin', 'superadmin', 'admin', 'instructor']:
            return JsonResponse({
                'status': 'error',
                'error': 'Insufficient permissions'
            }, status=403)
        
        # Attempt recovery
        recovery_result = SyncRecoveryManager.auto_recover_conference(conference_id)
        
        return JsonResponse({
            'status': 'success',
            'recovery_result': recovery_result
        })
        
    except Exception as e:
        logger.error(f"Auto recovery error: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'error': str(e)
        }, status=500)

@csrf_protect
@require_http_methods(["GET"])
def sync_status_dashboard(request):
    """
    API endpoint for sync status dashboard data
    
    GET /conferences/sync-status/
    """
    try:
        if not request.user.is_authenticated:
            return JsonResponse({
                'status': 'error',
                'error': 'Authentication required'
            }, status=401)
        
        if not request.user.role in ['globaladmin', 'superadmin', 'admin']:
            return JsonResponse({
                'status': 'error',
                'error': 'Admin access required'
            }, status=403)
        
        # Get recent conferences for dashboard
        recent_conferences = Conference.objects.filter(
            date__gte=timezone.now().date() - timezone.timedelta(days=30)
        ).order_by('-date')[:20]
        
        dashboard_data = {
            'recent_conferences': [],
            'system_health': SyncHealthChecker.get_system_wide_health(),
            'sync_trends': {},
            'common_issues': {}
        }
        
        # Collect data for each recent conference
        for conference in recent_conferences:
            health = SyncHealthChecker.check_conference_sync_health(conference.id)
            dashboard_data['recent_conferences'].append({
                'id': conference.id,
                'title': conference.title,
                'date': conference.date.isoformat(),
                'status': health['overall_status'],
                'issues_count': len(health.get('issues', [])),
                'last_sync': health.get('last_sync').isoformat() if health.get('last_sync') else None,
                'recordings_status': health.get('recordings_status'),
                'chat_status': health.get('chat_status')
            })
        
        return JsonResponse({
            'status': 'success',
            'dashboard_data': dashboard_data,
            'timestamp': timezone.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Sync status dashboard error: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'error': str(e)
        }, status=500)




