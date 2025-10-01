"""
Enhanced Trackable SCORM Launch System
=====================================

This module provides a comprehensive solution for trackable SCORM launch URLs
with automatic completion tracking and report integration.

Key Features:
1. Trackable launch URLs with unique registration IDs
2. Automatic completion status updates from SCORM Cloud
3. Real-time progress tracking and reporting
4. Seamless integration with existing LMS system
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from django.http import JsonResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone as django_timezone
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.db import transaction

from .models import SCORMCloudContent, SCORMPackage, SCORMRegistration
from .utils.api import get_scorm_client
from courses.models import Topic, TopicProgress
from courses.views import get_topic_course

logger = logging.getLogger(__name__)

class TrackableSCORMLauncher:
    """
    Enhanced SCORM launcher with comprehensive tracking capabilities
    """
    
    def __init__(self, user, topic_id):
        self.user = user
        self.topic_id = topic_id
        self.topic = None
        self.scorm_content = None
        self.registration = None
        self.progress = None
        
    def initialize(self):
        """Initialize the launcher with all required data"""
        try:
            # Get topic
            self.topic = get_object_or_404(Topic, id=self.topic_id)
            
            # Get SCORM content
            self.scorm_content = SCORMCloudContent.objects.filter(
                content_type='topic',
                content_id=str(self.topic.id)
            ).first()
            
            if not self.scorm_content:
                raise ValueError(f"No SCORM content found for topic {self.topic_id}")
            
            # Get or create progress record
            self.progress, created = TopicProgress.objects.get_or_create(
                user=self.user,
                topic=self.topic
            )
            
            if created:
                self.progress.init_progress_data()
                self.progress.save()
            
            return True
            
        except Exception as e:
            logger.error(f"Error initializing trackable launcher: {str(e)}")
            return False
    
    def create_trackable_registration(self):
        """Create a trackable registration with unique ID"""
        try:
            # Generate unique registration ID
            registration_id = f"LMS_{self.topic.id}_{self.user.id}_{uuid.uuid4().hex[:8]}"
            
            # Create registration in database
            self.registration = SCORMRegistration.objects.create(
                registration_id=registration_id,
                user=self.user,
                package=self.scorm_content.package
            )
            
            # Update progress with registration ID
            self.progress.scorm_registration = registration_id
            self.progress.save()
            
            logger.info(f"Created trackable registration: {registration_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error creating trackable registration: {str(e)}")
            return False
    
    def get_trackable_launch_url(self, redirect_url=None):
        """Get trackable launch URL with completion tracking"""
        try:
            # Get SCORM client
            scorm_client = get_scorm_client(
                user=self.user, 
                branch=getattr(self.user, 'branch', None)
            )
            
            if not scorm_client or not scorm_client.is_configured:
                raise ValueError("SCORM Cloud not configured")
            
            # Build redirect URL for completion tracking
            if not redirect_url:
                redirect_url = f"/scorm/topic/{self.topic.id}/completion/"
            
            # Create registration in SCORM Cloud
            scorm_client.create_registration(
                self.scorm_content.package.cloud_id,
                str(self.user.id),
                registration_id=self.registration.registration_id
            )
            
            # Get launch URL with tracking parameters
            launch_url = scorm_client.get_launch_url(
                self.registration.registration_id,
                redirect_url=redirect_url,
                additional_settings={
                    'api': True,
                    'initializeApi': True,
                    'commitOnUnload': True,
                    'apiCommitFrequency': 'auto',
                    'apiLogFrequency': '1',
                    'apiPostbackTimeout': 30000,
                    'apiPostbackAttempts': 3,
                    'preventFrameBust': True,
                    'launchMode': 'OwnWindow',
                    'postbackUrl': f"/scorm/api/postback/{self.registration.registration_id}/",
                    'completionTracking': True,
                    'progressTracking': True
                }
            )
            
            return launch_url
            
        except Exception as e:
            logger.error(f"Error getting trackable launch URL: {str(e)}")
            return None

@login_required
def enhanced_scorm_launch(request, topic_id):
    """
    Enhanced SCORM launch with comprehensive tracking
    """
    try:
        # Initialize launcher
        launcher = TrackableSCORMLauncher(request.user, topic_id)
        if not launcher.initialize():
            return JsonResponse({
                'error': 'Failed to initialize SCORM launcher'
            }, status=400)
        
        # Create trackable registration
        if not launcher.create_trackable_registration():
            return JsonResponse({
                'error': 'Failed to create trackable registration'
            }, status=400)
        
        # Get trackable launch URL
        launch_url = launcher.get_trackable_launch_url()
        if not launch_url:
            return JsonResponse({
                'error': 'Failed to generate trackable launch URL'
            }, status=400)
        
        # Log launch event
        logger.info(f"Enhanced SCORM launch initiated for topic {topic_id} by user {request.user.username}")
        
        return HttpResponseRedirect(launch_url)
        
    except Exception as e:
        logger.error(f"Error in enhanced SCORM launch: {str(e)}")
        return JsonResponse({
            'error': f'Launch failed: {str(e)}'
        }, status=500)

@csrf_protect
@require_http_methods(["POST"])
def scorm_completion_webhook(request, registration_id):
    """
    Handle SCORM completion webhook from SCORM Cloud
    """
    try:
        # Get registration
        registration = get_object_or_404(SCORMRegistration, registration_id=registration_id)
        
        # Parse webhook data
        data = json.loads(request.body)
        
        # Update registration with completion data
        registration.completion_status = data.get('completionStatus', 'incomplete')
        registration.success_status = data.get('successStatus', 'unknown')
        registration.score = data.get('score', 0)
        registration.total_time = data.get('totalTime', 0)
        registration.last_accessed = django_timezone.now()
        
        # Store detailed progress data
        registration.progress_data.update({
            'completion_status': registration.completion_status,
            'success_status': registration.success_status,
            'score': registration.score,
            'total_time': registration.total_time,
            'completion_date': django_timezone.now().isoformat(),
            'webhook_data': data
        })
        
        registration.save()
        
        # Update topic progress
        progress = TopicProgress.objects.filter(
            user=registration.user,
            topic__scorm_content__package=registration.package
        ).first()
        
        if progress:
            # Mark as completed if SCORM reports completion
            if registration.completion_status in ['completed', 'passed']:
                progress.completed = True
                progress.completion_date = django_timezone.now()
                
                # Update completion data
                progress.completion_data.update({
                    'scorm_completion': True,
                    'completion_status': registration.completion_status,
                    'success_status': registration.success_status,
                    'scorm_score': registration.score,
                    'completion_date': django_timezone.now().isoformat()
                })
                
                progress.save()
                
                # Trigger course completion check
                progress._check_course_completion()
                
                logger.info(f"Topic {progress.topic.id} marked as completed via SCORM webhook")
        
        return JsonResponse({'status': 'success'})
        
    except Exception as e:
        logger.error(f"Error processing SCORM completion webhook: {str(e)}")
        return JsonResponse({
            'error': f'Webhook processing failed: {str(e)}'
        }, status=500)

@login_required
def scorm_completion_redirect(request, topic_id):
    """
    Handle completion redirect and update progress
    """
    try:
        # Get progress record
        progress = get_object_or_404(TopicProgress, user=request.user, topic_id=topic_id)
        
        # Sync with SCORM Cloud
        if progress.scorm_registration:
            registration = SCORMRegistration.objects.filter(
                registration_id=progress.scorm_registration
            ).first()
            
            if registration:
                # Sync completion status
                registration.sync_completion_status()
                
                # Update progress if completed
                if registration.completion_status in ['completed', 'passed']:
                    progress.completed = True
                    progress.completion_date = django_timezone.now()
                    progress.save()
                    
                    # Trigger course completion check
                    progress._check_course_completion()
        
        # Redirect to topic view
        return HttpResponseRedirect(
            reverse('courses:topic_view', kwargs={'topic_id': topic_id})
        )
        
    except Exception as e:
        logger.error(f"Error in completion redirect: {str(e)}")
        return HttpResponseRedirect('/')

@login_required
def scorm_progress_tracking(request, topic_id):
    """
    Real-time progress tracking endpoint
    """
    try:
        progress = get_object_or_404(TopicProgress, user=request.user, topic_id=topic_id)
        
        # Get registration data
        registration_data = {}
        if progress.scorm_registration:
            registration = SCORMRegistration.objects.filter(
                registration_id=progress.scorm_registration
            ).first()
            
            if registration:
                # Sync with SCORM Cloud
                registration.sync_completion_status()
                
                registration_data = {
                    'completion_status': registration.completion_status,
                    'success_status': registration.success_status,
                    'score': float(registration.score) if registration.score else None,
                    'total_time': registration.total_time,
                    'progress_percentage': registration.get_progress_percentage(),
                    'last_accessed': registration.last_accessed.isoformat() if registration.last_accessed else None
                }
        
        return JsonResponse({
            'status': 'success',
            'progress': registration_data,
            'topic_completed': progress.completed,
            'completion_date': progress.completion_date.isoformat() if progress.completion_date else None
        })
        
    except Exception as e:
        logger.error(f"Error in progress tracking: {str(e)}")
        return JsonResponse({
            'error': f'Progress tracking failed: {str(e)}'
        }, status=500)

@login_required
def scorm_report_data(request, topic_id):
    """
    Get SCORM data for report pages
    """
    try:
        progress = get_object_or_404(TopicProgress, user=request.user, topic_id=topic_id)
        
        report_data = {
            'topic_id': topic_id,
            'topic_title': progress.topic.title,
            'user_id': request.user.id,
            'user_name': request.user.username,
            'completed': progress.completed,
            'completion_date': progress.completion_date.isoformat() if progress.completion_date else None,
            'scorm_data': {}
        }
        
        if progress.scorm_registration:
            registration = SCORMRegistration.objects.filter(
                registration_id=progress.scorm_registration
            ).first()
            
            if registration:
                # Sync latest data
                registration.sync_completion_status()
                
                report_data['scorm_data'] = {
                    'registration_id': registration.registration_id,
                    'completion_status': registration.completion_status,
                    'success_status': registration.success_status,
                    'score': float(registration.score) if registration.score else None,
                    'total_time': registration.total_time,
                    'progress_percentage': registration.get_progress_percentage(),
                    'last_accessed': registration.last_accessed.isoformat() if registration.last_accessed else None,
                    'progress_data': registration.progress_data
                }
        
        return JsonResponse({
            'status': 'success',
            'data': report_data
        })
        
    except Exception as e:
        logger.error(f"Error getting report data: {str(e)}")
        return JsonResponse({
            'error': f'Report data retrieval failed: {str(e)}'
        }, status=500)
