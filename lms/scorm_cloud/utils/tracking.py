import logging
from datetime import datetime
from django.utils import timezone
from .api import get_scorm_client
from courses.models import Course, TopicProgress, CourseEnrollment

logger = logging.getLogger(__name__)

def sync_registration_data(registration):
    """Sync registration data from SCORM Cloud"""
    try:
        # Get branch-specific SCORM client
        branch = None
        try:
            # Try to get branch from registration's package/content/topic
            if hasattr(registration, 'package') and registration.package:
                content = getattr(registration.package, 'scormcontent', None)
                if content and hasattr(content, 'topic'):
                    topic = content.topic
                    if hasattr(topic, 'section') and topic.section:
                        if hasattr(topic.section, 'course') and topic.section.course:
                            branch = getattr(topic.section.course, 'branch', None)
        except Exception as e:
            logger.warning(f"Could not get branch context for registration {registration.registration_id}: {str(e)}")
        
        scorm_client = get_scorm_client(branch=branch)
        data = scorm_client.get_registration_status(registration.registration_id)
        
        # Update completion status
        registration.completion_status = data.get('completionStatus', 'unknown')
        registration.success_status = data.get('successStatus', 'unknown')
        
        # Update score if available
        if 'score' in data:
            registration.score = data['score'].get('scaled', None)
            
        # Update time tracking
        if 'totalTime' in data:
            registration.total_time = data['totalTime']
            
        # Handle completion
        if registration.completion_status == 'completed':
            registration.completion_date = timezone.now()
            
        # Store raw progress data
        registration.progress_data.update({
            'last_sync': timezone.now().isoformat(),
            'raw_data': data
        })
        
        registration.save()
        
        # Update associated course progress
        update_course_progress(registration)
        
        return True
        
    except Exception as e:
        logger.error(f"Error syncing registration {registration.registration_id}: {str(e)}")
        return False

def update_course_progress(registration):
    """Update course completion status based on topic progress"""
    try:
        # Get topic associated with registration
        topic = registration.package.scormcontent.topic
        
        # Get topic progress
        topic_progress = TopicProgress.objects.filter(
            topic=topic,
            user=registration.user
        ).first()
        
        if not topic_progress:
            return
            
        # Update progress based on registration status
        topic_progress.update_from_scorm(registration)
        topic_progress.save()
        
        # Find courses associated with this topic through CourseTopic
        courses = Course.objects.filter(coursetopic__topic=topic)
        
        for course in courses:
            total_topics = course.topics.count()
            completed_topics = TopicProgress.objects.filter(
                user=registration.user,
                topic__coursetopic__course=course,
                completed=True
            ).count()
            
            if total_topics == completed_topics:
                enrollment = CourseEnrollment.objects.filter(
                    user=registration.user,
                    course=course
                ).first()
                
                if enrollment:
                    enrollment.completed = True
                    enrollment.completion_date = timezone.now()
                    enrollment.save()
            
    except Exception as e:
        logger.error(f"Error updating course progress: {str(e)}")

def process_xapi_statement(statement_data):
    """Process xAPI statement from SCORM Cloud"""
    try:
        registration_id = statement_data.get('registration')
        if not registration_id:
            return False
            
        from ..models import SCORMRegistration
        registration = SCORMRegistration.objects.get(registration_id=registration_id)
        
        # Store statement
        registration.progress_data.setdefault('xapi_statements', []).append(statement_data)
        registration.save()
        
        # Sync latest status
        sync_registration_data(registration)
        
        return True
        
    except Exception as e:
        logger.error(f"Error processing xAPI statement: {str(e)}")
        return False

def auto_sync_scorm_progress(registration_id):
    """
    Automatically sync SCORM progress from SCORM Cloud without requiring admin page visit.
    This function should be called when a SCORM launch session ends or by a scheduled task.
    """
    from ..models import SCORMRegistration
    from django.utils import timezone
    import logging
    
    logger = logging.getLogger(__name__)
    
    try:
        # Get the registration
        registration = SCORMRegistration.objects.filter(registration_id=registration_id).first()
        if not registration:
            logger.error(f"Registration not found: {registration_id}")
            return False
            
        # Get associated topic progress
        from courses.models import TopicProgress
        progress = TopicProgress.objects.filter(scorm_registration=registration_id).first()
        if not progress:
            logger.error(f"No topic progress found for registration: {registration_id}")
            return False
            
        # Get branch-specific SCORM client
        branch = None
        try:
            # Try to get branch from progress topic
            if progress and hasattr(progress, 'topic'):
                topic = progress.topic
                if hasattr(topic, 'section') and topic.section:
                    if hasattr(topic.section, 'course') and topic.section.course:
                        branch = getattr(topic.section.course, 'branch', None)
        except Exception as e:
            logger.warning(f"Could not get branch context for registration {registration_id}: {str(e)}")
        
        # Import SCORM Cloud utilities
        from scorm_cloud.utils.api import get_scorm_client
        
        # Get the latest data from SCORM Cloud
        scorm_client = get_scorm_client(branch=branch)
        registration_report = scorm_client.get_registration_progress(registration_id)
        
        if not registration_report:
            logger.error(f"No registration report returned for {registration_id}")
            return False
            
        # Update progress based on report
        logger.info(f"Auto-syncing SCORM progress for registration {registration_id}. Current completed status: {progress.completed}")
        progress.update_scorm_progress(registration_report)
        
        # Explicitly save and refresh to get the latest status
        progress.save()
        progress.refresh_from_db()
        
        logger.info(f"Auto-sync completed. New completed status: {progress.completed}")
        return True
        
    except Exception as e:
        logger.error(f"Error in auto_sync_scorm_progress for {registration_id}: {str(e)}")
        return False