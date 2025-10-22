"""
Query Optimization Utilities
Provides optimized database queries to prevent N+1 problems and improve performance
"""

import logging
from typing import List, Dict, Any, Optional
from django.db.models import Prefetch, Q, F, Count, Sum, Avg, Max, Min
from django.db.models.functions import Coalesce
from django.core.cache import cache
from django.conf import settings

logger = logging.getLogger(__name__)

class QueryOptimizer:
    """Provides optimized database queries for common patterns"""
    
    @staticmethod
    def get_optimized_course_queryset():
        """Get optimized course queryset with all necessary prefetches"""
        from courses.models import Course
        
        return Course.objects.select_related(
            'instructor',
            'branch',
            'category'
        ).prefetch_related(
            'topics',
            'prerequisites',
            'accessible_groups',
            'enrollments__user',
            'enrollments__user__branch'
        )
    
    @staticmethod
    def get_optimized_user_queryset():
        """Get optimized user queryset with all necessary prefetches"""
        from users.models import CustomUser
        
        return CustomUser.objects.select_related(
            'branch',
            'branch__business'
        ).prefetch_related(
            'courseenrollment__course',
            'courseenrollment__course__instructor',
            'groups__group',
            'groups__group__accessible_courses'
        )
    
    @staticmethod
    def get_optimized_assignment_queryset():
        """Get optimized assignment queryset with all necessary prefetches"""
        from assignments.models import Assignment
        
        return Assignment.objects.select_related(
            'user',
            'rubric',
            'course'
        ).prefetch_related(
            'rubric__criteria__ratings',
            'text_fields',
            'text_questions',
            'attachments',
            'submissions__user',
            'submissions__user__branch'
        )
    
    @staticmethod
    def get_optimized_quiz_queryset():
        """Get optimized quiz queryset with all necessary prefetches"""
        from quiz.models import Quiz
        
        return Quiz.objects.select_related(
            'creator',
            'course'
        ).prefetch_related(
            'questions__answers',
            'questions__matching_pairs',
            'attempts__user',
            'attempts__user__branch'
        )
    
    @staticmethod
    def get_optimized_enrollment_queryset():
        """Get optimized enrollment queryset with all necessary prefetches"""
        from courses.models import CourseEnrollment
        
        return CourseEnrollment.objects.select_related(
            'user',
            'user__branch',
            'course',
            'course__instructor'
        ).prefetch_related(
            'user__groups__group',
            'course__topics',
            'course__prerequisites'
        )
    
    @staticmethod
    def get_course_progress_data(course_id: int, user_id: Optional[int] = None):
        """Get optimized course progress data"""
        from courses.models import Course, CourseEnrollment, TopicProgress
        
        # Base queryset
        course = Course.objects.select_related('instructor', 'branch').get(id=course_id)
        
        # Get enrollments with optimized queries
        enrollments_query = CourseEnrollment.objects.filter(course=course)
        if user_id:
            enrollments_query = enrollments_query.filter(user_id=user_id)
        
        enrollments = enrollments_query.select_related(
            'user',
            'user__branch'
        ).prefetch_related(
            'user__groups__group'
        )
        
        # Get topic progress with optimized queries
        topic_progress_query = TopicProgress.objects.filter(
            course=course
        )
        if user_id:
            topic_progress_query = topic_progress_query.filter(user_id=user_id)
        
        topic_progress = topic_progress_query.select_related(
            'user',
            'topic'
        ).prefetch_related(
            'topic__course'
        )
        
        return {
            'course': course,
            'enrollments': enrollments,
            'topic_progress': topic_progress
        }
    
    @staticmethod
    def get_gradebook_data(course_id: int):
        """Get optimized gradebook data"""
        from courses.models import Course
        from assignments.models import Assignment, AssignmentSubmission
        from quiz.models import Quiz, QuizAttempt
        from gradebook.models import Grade
        
        # Get course with all related data
        course = Course.objects.select_related(
            'instructor',
            'branch'
        ).prefetch_related(
            'topics',
            'enrollments__user',
            'enrollments__user__branch'
        ).get(id=course_id)
        
        # Get assignments with submissions
        assignments = Assignment.objects.filter(
            course=course
        ).select_related(
            'rubric',
            'user'
        ).prefetch_related(
            'submissions__user',
            'submissions__user__branch',
            'rubric__criteria__ratings'
        )
        
        # Get quizzes with attempts
        quizzes = Quiz.objects.filter(
            course=course
        ).select_related(
            'creator'
        ).prefetch_related(
            'questions',
            'attempts__user',
            'attempts__user__branch'
        )
        
        # Get grades with optimized queries
        grades = Grade.objects.filter(
            assignment__course=course
        ).select_related(
            'student',
            'assignment',
            'submission__graded_by'
        ).prefetch_related(
            'student__branch'
        )
        
        return {
            'course': course,
            'assignments': assignments,
            'quizzes': quizzes,
            'grades': grades
        }
    
    @staticmethod
    def get_dashboard_data(user_id: int, role: str):
        """Get optimized dashboard data based on user role"""
        from users.models import CustomUser
        from courses.models import Course, CourseEnrollment
        from assignments.models import Assignment
        from quiz.models import Quiz
        
        user = CustomUser.objects.select_related(
            'branch',
            'branch__business'
        ).get(id=user_id)
        
        if role == 'learner':
            # Get learner-specific data
            enrollments = CourseEnrollment.objects.filter(
                user=user
            ).select_related(
                'course',
                'course__instructor'
            ).prefetch_related(
                'course__topics'
            )
            
            assignments = Assignment.objects.filter(
                course__enrollments__user=user
            ).select_related(
                'course',
                'user'
            ).prefetch_related(
                'submissions__user'
            )
            
            quizzes = Quiz.objects.filter(
                course__enrollments__user=user
            ).select_related(
                'creator',
                'course'
            ).prefetch_related(
                'attempts__user'
            )
            
            return {
                'user': user,
                'enrollments': enrollments,
                'assignments': assignments,
                'quizzes': quizzes
            }
        
        elif role == 'instructor':
            # Get instructor-specific data
            courses = Course.objects.filter(
                instructor=user
            ).select_related(
                'branch',
                'category'
            ).prefetch_related(
                'enrollments__user',
                'enrollments__user__branch',
                'topics'
            )
            
            assignments = Assignment.objects.filter(
                course__instructor=user
            ).select_related(
                'course',
                'rubric'
            ).prefetch_related(
                'submissions__user',
                'submissions__user__branch'
            )
            
            quizzes = Quiz.objects.filter(
                creator=user
            ).select_related(
                'course'
            ).prefetch_related(
                'attempts__user',
                'attempts__user__branch'
            )
            
            return {
                'user': user,
                'courses': courses,
                'assignments': assignments,
                'quizzes': quizzes
            }
        
        else:
            # Get admin-specific data
            courses = Course.objects.select_related(
                'instructor',
                'branch',
                'category'
            ).prefetch_related(
                'enrollments__user',
                'enrollments__user__branch'
            )
            
            return {
                'user': user,
                'courses': courses
            }
    
    @staticmethod
    def get_cached_data(cache_key: str, data_func, timeout: int = 300):
        """Get data from cache or compute and cache it"""
        cached_data = cache.get(cache_key)
        if cached_data is not None:
            return cached_data
        
        data = data_func()
        cache.set(cache_key, data, timeout)
        return data
    
    @staticmethod
    def invalidate_related_cache(cache_pattern: str):
        """Invalidate cache entries matching a pattern"""
        # This is a simplified version - in production, you'd use Redis or similar
        # for pattern-based cache invalidation
        logger.info(f"Cache invalidation requested for pattern: {cache_pattern}")
    
    @staticmethod
    def get_paginated_queryset(queryset, page: int, per_page: int = 20):
        """Get paginated queryset with optimized queries"""
        from django.core.paginator import Paginator
        
        paginator = Paginator(queryset, per_page)
        try:
            return paginator.page(page)
        except:
            return paginator.page(1)
