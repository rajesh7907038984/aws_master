"""
Enrollment Management Service
Provides atomic and consistent enrollment operations to prevent race conditions
"""

import logging
from typing import Optional, Tuple, List, Dict, Any
from django.db import transaction, IntegrityError
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal

logger = logging.getLogger(__name__)

class EnrollmentService:
    """Centralized service for safe enrollment operations"""
    
    @classmethod
    @transaction.atomic
    def create_or_get_enrollment(cls, user, course, source='manual', source_course=None) -> Tuple[Any, bool, str]:
        """
        Safely create or get enrollment with proper locking to prevent race conditions
        
        Args:
            user: User to enroll
            course: Course to enroll in
            source: Source of enrollment ('manual', 'bulk', 'auto_prerequisite', etc.)
            source_course: Source course if auto-enrolled
            
        Returns:
            Tuple of (enrollment, created, message)
        """
        from courses.models import CourseEnrollment
        
        try:
            # Use select_for_update to prevent race conditions
            existing_enrollment = CourseEnrollment.objects.select_for_update().filter(
                user=user,
                course=course
            ).first()
            
            if existing_enrollment:
                return existing_enrollment, False, f"User {user.username} already enrolled in {course.title}"
            
            # Create new enrollment
            enrollment = CourseEnrollment.objects.create(
                user=user,
                course=course,
                enrolled_at=timezone.now(),
                enrollment_source=source,
                source_course=source_course,
                completed=False
            )
            
            logger.info(f"Created enrollment: {user.username} -> {course.title} (source: {source})")
            return enrollment, True, f"Successfully enrolled {user.username} in {course.title}"
            
        except IntegrityError as e:
            # Handle the case where enrollment was created between our check and create
            logger.warning(f"Enrollment race condition handled for {user.username} in {course.title}: {e}")
            existing_enrollment = CourseEnrollment.objects.filter(
                user=user,
                course=course
            ).first()
            
            if existing_enrollment:
                return existing_enrollment, False, f"User {user.username} already enrolled in {course.title}"
            else:
                raise ValidationError(f"Failed to create enrollment for {user.username} in {course.title}")
        
        except Exception as e:
            logger.error(f"Enrollment creation failed for {user.username} in {course.title}: {e}")
            raise ValidationError(f"Enrollment creation failed: {str(e)}")
    
    @classmethod
    @transaction.atomic
    def bulk_create_enrollments(cls, users: List[Any], course, source='bulk') -> Dict[str, Any]:
        """
        Safely create multiple enrollments in a single transaction
        
        Args:
            users: List of users to enroll
            course: Course to enroll in
            source: Source of enrollment
            
        Returns:
            Dictionary with results
        """
        from courses.models import CourseEnrollment
        
        results = {
            'created': 0,
            'already_enrolled': 0,
            'errors': [],
            'enrollments': []
        }
        
        try:
            # Get existing enrollments to avoid duplicates
            existing_user_ids = set(
                CourseEnrollment.objects.filter(
                    course=course,
                    user__in=users
                ).values_list('user_id', flat=True)
            )
            
            # Filter out users already enrolled
            users_to_enroll = [user for user in users if user.id not in existing_user_ids]
            results['already_enrolled'] = len(users) - len(users_to_enroll)
            
            logger.info(f"Bulk enrollment: {len(users_to_enroll)} new users, {results['already_enrolled']} already enrolled")
            
            # Create enrollments in batch
            enrollments_to_create = []
            for user in users_to_enroll:
                enrollments_to_create.append(
                    CourseEnrollment(
                        user=user,
                        course=course,
                        enrolled_at=timezone.now(),
                        enrollment_source=source,
                        completed=False
                    )
                )
            
            if enrollments_to_create:
                created_enrollments = CourseEnrollment.objects.bulk_create(
                    enrollments_to_create,
                    ignore_conflicts=True
                )
                results['created'] = len(created_enrollments)
                results['enrollments'] = created_enrollments
                
                logger.info(f"Bulk enrolled {len(created_enrollments)} users in {course.title}")
            
            return results
            
        except Exception as e:
            logger.error(f"Bulk enrollment failed for course {course.title}: {e}")
            results['errors'].append(f"Bulk enrollment failed: {str(e)}")
            raise ValidationError(f"Bulk enrollment failed: {str(e)}")
    
    @classmethod
    @transaction.atomic
    def update_enrollment_progress(cls, enrollment, progress_percentage: float, 
                                 force_completion: bool = False) -> bool:
        """
        Safely update enrollment progress with proper validation
        
        Args:
            enrollment: CourseEnrollment instance
            progress_percentage: Progress percentage (0-100)
            force_completion: Force completion regardless of percentage
            
        Returns:
            True if progress was updated
        """
        try:
            from core.utils.scoring import ScoreCalculationService
            
            # Normalize progress percentage
            normalized_progress = ScoreCalculationService.normalize_score(
                progress_percentage, Decimal('100.00')
            )
            
            if normalized_progress is None:
                logger.error(f"Invalid progress percentage: {progress_percentage}")
                return False
            
            progress_percentage = float(normalized_progress)
            
            # Use select_for_update to prevent race conditions
            enrollment = enrollment.__class__.objects.select_for_update().get(
                pk=enrollment.pk
            )
            
            # Update completion status
            was_completed = enrollment.completed
            
            if force_completion or progress_percentage >= 100.0:
                enrollment.completed = True
                if not enrollment.completion_date:
                    enrollment.completion_date = timezone.now()
            else:
                enrollment.completed = False
                enrollment.completion_date = None
            
            enrollment.save(update_fields=['completed', 'completion_date', 'last_accessed'])
            
            if enrollment.completed and not was_completed:
                logger.info(f"Enrollment completed: {enrollment.user.username} -> {enrollment.course.title}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to update enrollment progress: {e}")
            return False
    
    @classmethod
    @transaction.atomic
    def create_or_update_topic_progress(cls, user, topic, **kwargs) -> Tuple[Any, bool]:
        """
        Safely create or update topic progress with proper locking
        
        Args:
            user: User
            topic: Topic
            **kwargs: Additional fields for TopicProgress
            
        Returns:
            Tuple of (progress, created)
        """
        from courses.models import TopicProgress
        
        try:
            # Use get_or_create with select_for_update on the query
            progress, created = TopicProgress.objects.select_for_update().get_or_create(
                user=user,
                topic=topic,
                defaults={
                    'completed': kwargs.get('completed', False),
                    'progress_data': kwargs.get('progress_data', {}),
                    'attempts': kwargs.get('attempts', 0),
                    **kwargs
                }
            )
            
            if created:
                # Initialize progress data if not provided
                progress.init_progress_data()
                logger.info(f"Created topic progress: {user.username} -> {topic.title}")
            
            return progress, created
            
        except Exception as e:
            logger.error(f"Failed to create/update topic progress for {user.username}, topic {topic.id}: {e}")
            raise ValidationError(f"Topic progress operation failed: {str(e)}")
    
    @classmethod
    def validate_enrollment_eligibility(cls, user, course) -> Tuple[bool, List[str]]:
        """
        Validate if user is eligible for enrollment
        
        Args:
            user: User to validate
            course: Course to enroll in
            
        Returns:
            Tuple of (is_eligible, error_messages)
        """
        errors = []
        
        try:
            # Check if user is active
            if not user.is_active:
                errors.append("User account is not active")
            
            # Check if course is active
            if not course.is_active:
                errors.append("Course is not active")
            
            # Check enrollment limits if configured
            if hasattr(course, 'max_enrollments') and course.max_enrollments:
                current_enrollments = course.enrolled_users.count()
                if current_enrollments >= course.max_enrollments:
                    errors.append("Course enrollment limit reached")
            
            # Check prerequisites (if any)
            if course.prerequisites.exists():
                from courses.models import CourseEnrollment
                
                for prerequisite in course.prerequisites.all():
                    prerequisite_enrollment = CourseEnrollment.objects.filter(
                        user=user,
                        course=prerequisite,
                        completed=True
                    ).first()
                    
                    if not prerequisite_enrollment:
                        errors.append(f"Prerequisite course not completed: {prerequisite.title}")
            
            # Check branch restrictions
            if course.branch and hasattr(user, 'branch'):
                if user.branch != course.branch and user.role not in ['superadmin']:
                    errors.append("User branch does not match course branch")
            
            return len(errors) == 0, errors
            
        except Exception as e:
            logger.error(f"Enrollment eligibility validation failed: {e}")
            return False, [f"Validation error: {str(e)}"]
    
    @classmethod
    @transaction.atomic  
    def handle_prerequisite_enrollments(cls, user, course) -> List[str]:
        """
        Handle automatic prerequisite enrollments
        
        Args:
            user: User to enroll
            course: Course that requires prerequisites
            
        Returns:
            List of messages about prerequisite enrollments
        """
        messages = []
        
        try:
            # Check for circular dependencies first
            def has_circular_dependency(course_to_check, visited_courses=None, depth=0):
                if visited_courses is None:
                    visited_courses = set()
                
                if depth > 10:  # Prevent infinite recursion
                    logger.warning(f"Possible circular dependency detected at depth {depth}")
                    return True
                
                if course_to_check.id in visited_courses:
                    return True
                
                visited_courses.add(course_to_check.id)
                
                for prereq in course_to_check.prerequisites.all():
                    if has_circular_dependency(prereq, visited_courses.copy(), depth + 1):
                        return True
                
                return False
            
            if has_circular_dependency(course):
                messages.append("Warning: Circular dependency detected in prerequisites")
                return messages
            
            # Auto-enroll in prerequisites
            for prerequisite in course.prerequisites.all():
                prereq_enrollment, created, message = cls.create_or_get_enrollment(
                    user, prerequisite, source='auto_prerequisite', source_course=course
                )
                
                if created:
                    messages.append(f"Auto-enrolled in prerequisite: {prerequisite.title}")
                    
                    # Recursively handle prerequisites of prerequisites
                    nested_messages = cls.handle_prerequisite_enrollments(user, prerequisite)
                    messages.extend(nested_messages)
            
            return messages
            
        except Exception as e:
            logger.error(f"Prerequisite enrollment handling failed: {e}")
            messages.append(f"Prerequisite enrollment error: {str(e)}")
            return messages

# Backward compatibility functions
def safe_enroll_user(user, course, source='manual'):
    """Backward compatibility function"""
    enrollment, created, message = EnrollmentService.create_or_get_enrollment(user, course, source)
    return enrollment, created

def update_progress_safely(enrollment, progress):
    """Backward compatibility function"""
    return EnrollmentService.update_enrollment_progress(enrollment, progress)
