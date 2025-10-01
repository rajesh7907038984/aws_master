from django.utils import timezone
from django.db import transaction
import logging

logger = logging.getLogger(__name__)

def check_prerequisites_completion(user, course):
    """
    Check if user has completed all prerequisite courses for the given course.
    
    Args:
        user: The user to check prerequisites for
        course: The course to check prerequisites for
        
    Returns:
        dict: {
            'can_access': bool,
            'missing_prerequisites': list of Course objects,
            'completed_prerequisites': list of Course objects
        }
    """
    from .models import Course, CourseEnrollment
    
    # Get all prerequisites for the course
    prerequisites = course.prerequisites.all()
    
    # If no prerequisites, user can access
    if not prerequisites.exists():
        return {
            'can_access': True,
            'missing_prerequisites': [],
            'completed_prerequisites': []
        }
    
    completed_prerequisites = []
    missing_prerequisites = []
    
    for prereq_course in prerequisites:
        # Check if user is enrolled and has completed the prerequisite course
        enrollment = CourseEnrollment.objects.filter(
            user=user,
            course=prereq_course,
            completed=True
        ).first()
        
        if enrollment:
            completed_prerequisites.append(prereq_course)
        else:
            missing_prerequisites.append(prereq_course)
    
    can_access = len(missing_prerequisites) == 0
    
    return {
        'can_access': can_access,
        'missing_prerequisites': missing_prerequisites,
        'completed_prerequisites': completed_prerequisites
    }

def handle_prerequisite_changes(course, old_prerequisite_ids, new_prerequisite_ids):
    """
    Handle auto-enrollment and unenrollment when course prerequisites change.
    
    Args:
        course: The course whose prerequisites are being changed
        old_prerequisite_ids: Set of prerequisite IDs before the change
        new_prerequisite_ids: Set of prerequisite IDs after the change
    """
    from .models import Course, CourseEnrollment
    
    removed_prereq_ids = old_prerequisite_ids - new_prerequisite_ids
    added_prereq_ids = new_prerequisite_ids - old_prerequisite_ids
    
    enrolled_users_count = 0
    unenrolled_users_count = 0
    
    # Handle removed prerequisites - auto-unenroll users
    if removed_prereq_ids:
        logger.info(f"Processing {len(removed_prereq_ids)} removed prerequisites for course {course.title}")
        
        for removed_prereq_id in removed_prereq_ids:
            try:
                removed_prereq_course = Course.objects.get(id=removed_prereq_id)
                logger.info(f"Processing removed prerequisite: {removed_prereq_course.title}")
                
                # Get users enrolled in the main course
                main_course_users = course.enrolled_users.all()
                
                for user in main_course_users:
                    # Check if user is enrolled in the removed prerequisite
                    enrollment = CourseEnrollment.objects.filter(
                        user=user, 
                        course=removed_prereq_course
                    ).first()
                    
                    if enrollment:
                        # Only unenroll users who were auto-enrolled for prerequisites
                        # and specifically auto-enrolled from this course
                        should_unenroll = False
                        
                        if (enrollment.enrollment_source == 'auto_prerequisite' and 
                            enrollment.source_course and enrollment.source_course.id == course.id):
                            # This user was auto-enrolled specifically because of this course
                            should_unenroll = True
                            logger.info(f"User {user.username} was auto-enrolled from {course.title}, considering for unenrollment")
                        else:
                            # User was manually enrolled or enrolled for other reasons
                            logger.info(f"User {user.username} was not auto-enrolled from {course.title} (source: {enrollment.enrollment_source}), keeping enrolled")
                        
                        # Check if there are other courses that still require this prerequisite
                        other_courses_needing_prereq = Course.objects.filter(
                            prerequisites=removed_prereq_course,
                            enrolled_users=user
                        ).exclude(id=course.id)
                        
                        if other_courses_needing_prereq.exists():
                            logger.info(f"User {user.username} still needs {removed_prereq_course.title} for other courses: {list(other_courses_needing_prereq.values_list('title', flat=True))}")
                            should_unenroll = False
                        
                        if should_unenroll:
                            enrollment.delete()
                            unenrolled_users_count += 1
                            logger.info(f"Auto-unenrolled user {user.username} from removed prerequisite {removed_prereq_course.title}")
                            print(f"DEBUG: Auto-unenrolled user {user.username} from removed prerequisite {removed_prereq_course.title}")
                        
            except Course.DoesNotExist:
                logger.error(f"Removed prerequisite course with ID {removed_prereq_id} not found")
    
    # Handle added prerequisites - auto-enroll users
    if added_prereq_ids:
        logger.info(f"Processing {len(added_prereq_ids)} added prerequisites for course {course.title}")
        
        for added_prereq_id in added_prereq_ids:
            try:
                added_prereq_course = Course.objects.get(id=added_prereq_id)
                logger.info(f"Processing added prerequisite: {added_prereq_course.title}")
                
                # Auto-enroll users from main course to new prerequisite course
                main_course_users = course.enrolled_users.all()
                
                for user in main_course_users:
                    # Check if user is not already enrolled in the new prerequisite
                    if not CourseEnrollment.objects.filter(user=user, course=added_prereq_course).exists():
                        # Create enrollment in new prerequisite course with tracking
                        CourseEnrollment.objects.create(
                            user=user,
                            course=added_prereq_course,
                            enrolled_at=timezone.now(),
                            enrollment_source='auto_prerequisite',
                            source_course=course
                        )
                        enrolled_users_count += 1
                        logger.info(f"Auto-enrolled user {user.username} in new prerequisite {added_prereq_course.title}")
                        print(f"DEBUG: Auto-enrolled user {user.username} in new prerequisite {added_prereq_course.title} from course {course.title}")
                        
            except Course.DoesNotExist:
                logger.error(f"Added prerequisite course with ID {added_prereq_id} not found")
    
    return enrolled_users_count, unenrolled_users_count 