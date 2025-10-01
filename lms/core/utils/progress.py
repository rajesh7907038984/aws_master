"""
Unified Progress Calculation Service for LMS
Provides consistent progress calculations across all modules
"""

import logging
from typing import Dict, List, Optional, Tuple, Any, Union
from decimal import Decimal, ROUND_HALF_UP
from django.db.models import QuerySet, Q, F, Case, When, Value, IntegerField, Avg, Sum
from django.utils import timezone
from core.utils.scoring import ScoreCalculationService

logger = logging.getLogger(__name__)

class ProgressCalculationService:
    """Centralized service for progress calculations across the LMS"""
    
    @classmethod
    def calculate_topic_progress(cls, user, topic) -> Dict[str, Any]:
        """
        Calculate progress for a specific topic for a user
        
        Args:
            user: User object
            topic: Topic object
            
        Returns:
            Dictionary with progress information
        """
        try:
            from courses.models import TopicProgress
            
            # Get or create progress record
            progress, created = TopicProgress.objects.get_or_create(
                user=user,
                topic=topic,
                defaults={'completed': False, 'progress_data': {}}
            )
            
            result = {
                'topic_id': topic.id,
                'topic_title': topic.title,
                'completed': progress.completed,
                'completion_percentage': 0.0,
                'last_accessed': progress.last_accessed,
                'completed_at': progress.completed_at,
                'total_time_spent': progress.total_time_spent,
                'attempts': progress.attempts,
                'last_score': float(progress.last_score) if progress.last_score else None,
                'best_score': float(progress.best_score) if progress.best_score else None,
                'completion_method': progress.completion_method,
                'manually_completed': progress.manually_completed
            }
            
            # Calculate completion percentage based on topic type
            if topic.topic_type == 'scorm':
                result.update(cls._calculate_scorm_progress(progress, topic))
            elif topic.topic_type == 'quiz':
                result.update(cls._calculate_quiz_progress(user, topic))
            elif topic.topic_type == 'assignment':
                result.update(cls._calculate_assignment_progress(user, topic))
            elif topic.topic_type == 'video':
                result.update(cls._calculate_video_progress(progress, topic))
            elif topic.topic_type == 'text':
                result.update(cls._calculate_text_progress(progress, topic))
            else:
                # Default progress calculation
                result['completion_percentage'] = 100.0 if progress.completed else 0.0
            
            return result
            
        except Exception as e:
            logger.error(f"Error calculating topic progress for topic {topic.id}, user {user.id}: {e}")
            return {
                'topic_id': topic.id,
                'topic_title': getattr(topic, 'title', 'Unknown'),
                'completed': False,
                'completion_percentage': 0.0,
                'error': str(e)
            }
    
    @classmethod
    def _calculate_scorm_progress(cls, progress, topic) -> Dict[str, Any]:
        """Calculate progress for SCORM content"""
        try:
            # Get SCORM registration data
            scorm_content = topic.get_scorm_content() if hasattr(topic, 'get_scorm_content') else None
            
            if not scorm_content:
                return {'completion_percentage': 100.0 if progress.completed else 0.0}
            
            # Check SCORM registration
            from scorm_cloud.models import SCORMRegistration
            registration = SCORMRegistration.objects.filter(
                user=progress.user,
                package=scorm_content.scorm_package
            ).first()
            
            if not registration:
                return {'completion_percentage': 0.0}
            
            # Calculate based on SCORM completion status and score requirements
            completion_percentage = 0.0
            
            if registration.completion_status in ['completed', 'passed']:
                if scorm_content.requires_passing_score and scorm_content.passing_score:
                    # Check if score requirement is met
                    if registration.score and registration.score >= scorm_content.passing_score:
                        completion_percentage = 100.0
                    else:
                        # Partial completion based on score
                        score_progress = (registration.score or 0) / scorm_content.passing_score * 100
                        completion_percentage = min(score_progress, 99.0)  # Cap at 99% if not passed
                else:
                    completion_percentage = 100.0
            elif registration.completion_status == 'incomplete':
                # Calculate partial progress based on available data
                if progress.progress_data.get('completion_percent'):
                    completion_percentage = float(progress.progress_data['completion_percent'])
                elif registration.score:
                    # Estimate progress based on score
                    completion_percentage = min(float(registration.score), 90.0)
            
            return {
                'completion_percentage': completion_percentage,
                'scorm_status': registration.completion_status,
                'scorm_score': float(registration.score) if registration.score else None,
                'scorm_time': registration.total_time
            }
            
        except Exception as e:
            logger.error(f"Error calculating SCORM progress: {e}")
            return {'completion_percentage': 0.0, 'error': str(e)}
    
    @classmethod
    def _calculate_quiz_progress(cls, user, topic) -> Dict[str, Any]:
        """Calculate progress for quiz content"""
        try:
            from quiz.models import Quiz, QuizAttempt
            
            # Get quiz associated with topic
            quiz = Quiz.objects.filter(topic=topic).first()
            if not quiz:
                return {'completion_percentage': 0.0}
            
            # Get latest quiz attempt
            attempt = QuizAttempt.objects.filter(
                user=user,
                quiz=quiz,
                is_completed=True
            ).order_by('-end_time').first()
            
            if not attempt:
                return {'completion_percentage': 0.0}
            
            # Calculate completion based on quiz passing score
            completion_percentage = 0.0
            passed = False
            
            if quiz.passing_score and quiz.passing_score > 0:
                if attempt.score >= quiz.passing_score:
                    completion_percentage = 100.0
                    passed = True
                else:
                    # Partial credit based on score
                    completion_percentage = min((attempt.score / quiz.passing_score) * 100, 99.0)
            else:
                # No passing score requirement - just completion
                completion_percentage = 100.0
                passed = True
            
            return {
                'completion_percentage': completion_percentage,
                'quiz_score': float(attempt.score),
                'quiz_passed': passed,
                'quiz_attempts': QuizAttempt.objects.filter(user=user, quiz=quiz).count(),
                'latest_attempt_date': attempt.end_time
            }
            
        except Exception as e:
            logger.error(f"Error calculating quiz progress: {e}")
            return {'completion_percentage': 0.0, 'error': str(e)}
    
    @classmethod
    def _calculate_assignment_progress(cls, user, topic) -> Dict[str, Any]:
        """Calculate progress for assignment content"""
        try:
            from assignments.models import Assignment, AssignmentSubmission
            
            # Get assignment associated with topic
            assignment = Assignment.objects.filter(topic=topic).first()
            if not assignment:
                return {'completion_percentage': 0.0}
            
            # Get latest submission
            submission = AssignmentSubmission.objects.filter(
                user=user,
                assignment=assignment
            ).order_by('-submitted_at').first()
            
            if not submission:
                return {'completion_percentage': 0.0}
            
            # Calculate completion based on submission and grading
            completion_percentage = 0.0
            
            if submission.is_submitted:
                if submission.grade is not None:
                    # Graded submission
                    if assignment.passing_grade and assignment.passing_grade > 0:
                        if submission.grade >= assignment.passing_grade:
                            completion_percentage = 100.0
                        else:
                            # Partial credit
                            completion_percentage = min((submission.grade / assignment.passing_grade) * 100, 99.0)
                    else:
                        # No passing grade requirement - just completion
                        completion_percentage = 100.0
                else:
                    # Submitted but not graded yet
                    completion_percentage = 90.0  # High but not complete
            else:
                # Draft submission
                completion_percentage = 50.0  # Some progress made
            
            return {
                'completion_percentage': completion_percentage,
                'assignment_submitted': submission.is_submitted,
                'assignment_grade': float(submission.grade) if submission.grade else None,
                'submission_date': submission.submitted_at if submission.is_submitted else None
            }
            
        except Exception as e:
            logger.error(f"Error calculating assignment progress: {e}")
            return {'completion_percentage': 0.0, 'error': str(e)}
    
    @classmethod
    def _calculate_video_progress(cls, progress, topic) -> Dict[str, Any]:
        """Calculate progress for video content"""
        try:
            # Use audio progress tracking if available
            if hasattr(progress, 'audio_progress') and progress.audio_progress:
                completion_percentage = float(progress.audio_progress)
            elif progress.progress_data.get('video_progress'):
                completion_percentage = float(progress.progress_data['video_progress'])
            elif progress.completed:
                completion_percentage = 100.0
            else:
                completion_percentage = 0.0
            
            return {
                'completion_percentage': completion_percentage,
                'video_progress': completion_percentage
            }
            
        except Exception as e:
            logger.error(f"Error calculating video progress: {e}")
            return {'completion_percentage': 0.0, 'error': str(e)}
    
    @classmethod
    def _calculate_text_progress(cls, progress, topic) -> Dict[str, Any]:
        """Calculate progress for text content"""
        try:
            # Text content is typically completed when marked as read
            completion_percentage = 100.0 if progress.completed or progress.manually_completed else 0.0
            
            return {
                'completion_percentage': completion_percentage,
                'text_read': progress.completed or progress.manually_completed
            }
            
        except Exception as e:
            logger.error(f"Error calculating text progress: {e}")
            return {'completion_percentage': 0.0, 'error': str(e)}
    
    @classmethod
    def calculate_course_progress(cls, user, course) -> Dict[str, Any]:
        """
        Calculate overall progress for a course for a user
        
        Args:
            user: User object
            course: Course object
            
        Returns:
            Dictionary with course progress information
        """
        try:
            # Get all topics in the course
            topics = course.topics.filter(is_active=True).order_by('order')
            
            if not topics.exists():
                return {
                    'course_id': course.id,
                    'overall_progress': 0.0,
                    'completed_topics': 0,
                    'total_topics': 0,
                    'topics_progress': []
                }
            
            topic_progress_list = []
            total_progress = 0.0
            completed_topics = 0
            
            # Calculate progress for each topic
            for topic in topics:
                topic_progress = cls.calculate_topic_progress(user, topic)
                topic_progress_list.append(topic_progress)
                
                total_progress += topic_progress.get('completion_percentage', 0.0)
                
                if topic_progress.get('completion_percentage', 0.0) >= 100.0:
                    completed_topics += 1
            
            # Calculate overall course progress
            overall_progress = total_progress / len(topic_progress_list) if topic_progress_list else 0.0
            overall_progress = round(overall_progress, 2)
            
            # Update course enrollment progress
            cls._update_enrollment_progress(user, course, overall_progress)
            
            return {
                'course_id': course.id,
                'course_title': course.title,
                'overall_progress': overall_progress,
                'completed_topics': completed_topics,
                'total_topics': len(topic_progress_list),
                'topics_progress': topic_progress_list,
                'is_completed': overall_progress >= 100.0
            }
            
        except Exception as e:
            logger.error(f"Error calculating course progress for course {course.id}, user {user.id}: {e}")
            return {
                'course_id': course.id,
                'course_title': getattr(course, 'title', 'Unknown'),
                'overall_progress': 0.0,
                'completed_topics': 0,
                'total_topics': 0,
                'topics_progress': [],
                'error': str(e)
            }
    
    @classmethod
    def _update_enrollment_progress(cls, user, course, progress_percentage):
        """Update course enrollment with calculated progress"""
        try:
            from courses.models import CourseEnrollment
            from core.utils.enrollment import EnrollmentService
            
            enrollment = CourseEnrollment.objects.filter(
                user=user,
                course=course
            ).first()
            
            if enrollment:
                # Use the enrollment service for atomic updates
                EnrollmentService.update_enrollment_progress(
                    enrollment, 
                    progress_percentage
                )
            
        except Exception as e:
            logger.error(f"Error updating enrollment progress: {e}")
    
    @classmethod
    def calculate_user_dashboard_progress(cls, user) -> Dict[str, Any]:
        """
        Calculate progress data for user dashboard
        
        Args:
            user: User object
            
        Returns:
            Dictionary with dashboard progress data
        """
        try:
            from courses.models import CourseEnrollment, Course
            
            # Get user's enrolled courses
            enrollments = CourseEnrollment.objects.filter(
                user=user
            ).select_related('course')
            
            if not enrollments.exists():
                return {
                    'total_courses': 0,
                    'completed_courses': 0,
                    'in_progress_courses': 0,
                    'overall_progress': 0.0,
                    'courses_progress': []
                }
            
            courses_progress = []
            total_progress = 0.0
            completed_courses = 0
            in_progress_courses = 0
            
            for enrollment in enrollments:
                course_progress = cls.calculate_course_progress(user, enrollment.course)
                courses_progress.append(course_progress)
                
                progress = course_progress.get('overall_progress', 0.0)
                total_progress += progress
                
                if progress >= 100.0:
                    completed_courses += 1
                elif progress > 0.0:
                    in_progress_courses += 1
            
            overall_progress = total_progress / len(courses_progress) if courses_progress else 0.0
            overall_progress = round(overall_progress, 2)
            
            return {
                'total_courses': len(courses_progress),
                'completed_courses': completed_courses,
                'in_progress_courses': in_progress_courses,
                'not_started_courses': len(courses_progress) - completed_courses - in_progress_courses,
                'overall_progress': overall_progress,
                'courses_progress': courses_progress
            }
            
        except Exception as e:
            logger.error(f"Error calculating user dashboard progress for user {user.id}: {e}")
            return {
                'total_courses': 0,
                'completed_courses': 0,
                'in_progress_courses': 0,
                'overall_progress': 0.0,
                'courses_progress': [],
                'error': str(e)
            }
    
    @classmethod
    def bulk_recalculate_progress(cls, course=None, user=None) -> Dict[str, int]:
        """
        Bulk recalculate progress for efficiency
        
        Args:
            course: Optional course to limit recalculation
            user: Optional user to limit recalculation
            
        Returns:
            Dictionary with recalculation statistics
        """
        try:
            from courses.models import CourseEnrollment
            
            enrollments = CourseEnrollment.objects.all()
            
            if course:
                enrollments = enrollments.filter(course=course)
            if user:
                enrollments = enrollments.filter(user=user)
            
            enrollments = enrollments.select_related('user', 'course')
            
            updated_count = 0
            error_count = 0
            
            for enrollment in enrollments:
                try:
                    progress_data = cls.calculate_course_progress(
                        enrollment.user, 
                        enrollment.course
                    )
                    
                    if 'error' not in progress_data:
                        updated_count += 1
                    else:
                        error_count += 1
                        
                except Exception as e:
                    logger.error(f"Error recalculating progress for enrollment {enrollment.id}: {e}")
                    error_count += 1
            
            return {
                'total_processed': len(enrollments),
                'updated_count': updated_count,
                'error_count': error_count
            }
            
        except Exception as e:
            logger.error(f"Error in bulk progress recalculation: {e}")
            return {
                'total_processed': 0,
                'updated_count': 0,
                'error_count': 1
            }

# Backward compatibility functions
def calculate_course_progress(course, user):
    """Backward compatibility function"""
    result = ProgressCalculationService.calculate_course_progress(user, course)
    return result.get('overall_progress', 0.0)

def calculate_topic_progress(user, topic):
    """Backward compatibility function"""
    result = ProgressCalculationService.calculate_topic_progress(user, topic)
    return result.get('completion_percentage', 0.0)
