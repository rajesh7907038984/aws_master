"""
Dashboard Query Optimization Utilities
Provides optimized queries for dashboard views to prevent N+1 problems
"""

import logging
from typing import Dict, List, Any, Optional
from django.db.models import Prefetch, Q, Count, Avg, Max, Min
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)

class DashboardQueryOptimizer:
    """Optimized query utilities for dashboard views"""
    
    @classmethod
    def get_optimized_user_queryset(cls, user, role_based=True):
        """
        Get optimized user queryset based on user role
        Prevents N+1 queries by using select_related and prefetch_related
        """
        User = get_user_model()
        
        if user.role == 'globaladmin':
            # Global admin can see all users - OPTIMIZED
            return User.objects.select_related(
                'branch', 
                'branch__business', 
                'assigned_instructor'
            ).prefetch_related(
                'business_assignments__business',
                'groups__memberships'
            ).all()
            
        elif user.role == 'superadmin':
            # Super admin can see users in their assigned businesses - OPTIMIZED
            business_ids = user.business_assignments.filter(is_active=True).values_list('business_id', flat=True)
            return User.objects.select_related(
                'branch', 
                'branch__business', 
                'assigned_instructor'
            ).prefetch_related(
                'business_assignments__business',
                'groups__memberships'
            ).filter(
                Q(branch__business_id__in=business_ids) | 
                Q(business_assignments__business_id__in=business_ids)
            ).distinct()
            
        elif user.role == 'admin':
            # Admin can see users in their branch - OPTIMIZED
            return User.objects.select_related(
                'branch', 
                'branch__business', 
                'assigned_instructor'
            ).prefetch_related(
                'groups__memberships'
            ).filter(branch=user.branch)
            
        elif user.role == 'instructor':
            # Instructor can see their assigned students - OPTIMIZED
            return User.objects.select_related(
                'branch', 
                'branch__business', 
                'assigned_instructor'
            ).prefetch_related(
                'groups__memberships'
            ).filter(assigned_instructor=user)
            
        else:
            # Learners can only see themselves - OPTIMIZED
            return User.objects.select_related(
                'branch', 
                'branch__business', 
                'assigned_instructor'
            ).prefetch_related(
                'groups__memberships'
            ).filter(id=user.id)
    
    @classmethod
    def get_optimized_course_queryset(cls, user):
        """
        Get optimized course queryset based on user role
        """
        from courses.models import Course, CourseEnrollment
        
        if user.role == 'globaladmin':
            # Global admin can see all courses - OPTIMIZED
            return Course.objects.select_related(
                'instructor', 
                'branch', 
                'branch__business'
            ).prefetch_related(
                'topics',
                'enrollments__user',
                'accessible_groups'
            ).all()
            
        elif user.role == 'superadmin':
            # Super admin can see courses in their businesses - OPTIMIZED
            business_ids = user.business_assignments.filter(is_active=True).values_list('business_id', flat=True)
            return Course.objects.select_related(
                'instructor', 
                'branch', 
                'branch__business'
            ).prefetch_related(
                'topics',
                'enrollments__user',
                'accessible_groups'
            ).filter(branch__business_id__in=business_ids)
            
        elif user.role == 'admin':
            # Admin can see courses in their branch - OPTIMIZED
            return Course.objects.select_related(
                'instructor', 
                'branch', 
                'branch__business'
            ).prefetch_related(
                'topics',
                'enrollments__user',
                'accessible_groups'
            ).filter(branch=user.branch)
            
        elif user.role == 'instructor':
            # Instructor can see their courses - OPTIMIZED
            return Course.objects.select_related(
                'instructor', 
                'branch', 
                'branch__business'
            ).prefetch_related(
                'topics',
                'enrollments__user',
                'accessible_groups'
            ).filter(instructor=user)
            
        else:
            # Learners can see their enrolled courses - OPTIMIZED
            return Course.objects.select_related(
                'instructor', 
                'branch', 
                'branch__business'
            ).prefetch_related(
                'topics',
                'enrollments__user',
                'accessible_groups'
            ).filter(enrollments__user=user)
    
    @classmethod
    def get_optimized_enrollment_queryset(cls, user):
        """
        Get optimized enrollment queryset based on user role
        """
        from courses.models import CourseEnrollment
        
        if user.role == 'globaladmin':
            # Global admin can see all enrollments - OPTIMIZED
            return CourseEnrollment.objects.select_related(
                'user', 
                'course', 
                'course__instructor',
                'course__branch',
                'course__branch__business'
            ).prefetch_related(
                'course__topics'
            ).all()
            
        elif user.role == 'superadmin':
            # Super admin can see enrollments in their businesses - OPTIMIZED
            business_ids = user.business_assignments.filter(is_active=True).values_list('business_id', flat=True)
            return CourseEnrollment.objects.select_related(
                'user', 
                'course', 
                'course__instructor',
                'course__branch',
                'course__branch__business'
            ).prefetch_related(
                'course__topics'
            ).filter(
                Q(course__branch__business_id__in=business_ids) |
                Q(user__business_assignments__business_id__in=business_ids)
            ).distinct()
            
        elif user.role == 'admin':
            # Admin can see enrollments in their branch - OPTIMIZED
            return CourseEnrollment.objects.select_related(
                'user', 
                'course', 
                'course__instructor',
                'course__branch',
                'course__branch__business'
            ).prefetch_related(
                'course__topics'
            ).filter(course__branch=user.branch)
            
        elif user.role == 'instructor':
            # Instructor can see enrollments in their courses - OPTIMIZED
            return CourseEnrollment.objects.select_related(
                'user', 
                'course', 
                'course__instructor',
                'course__branch',
                'course__branch__business'
            ).prefetch_related(
                'course__topics'
            ).filter(course__instructor=user)
            
        else:
            # Learners can see their own enrollments - OPTIMIZED
            return CourseEnrollment.objects.select_related(
                'user', 
                'course', 
                'course__instructor',
                'course__branch',
                'course__branch__business'
            ).prefetch_related(
                'course__topics'
            ).filter(user=user)
    
    @classmethod
    def get_dashboard_stats(cls, user):
        """
        Get optimized dashboard statistics
        """
        stats = {}
        
        try:
            if user.role == 'globaladmin':
                # Global admin stats - OPTIMIZED
                from users.models import CustomUser
                from courses.models import Course, CourseEnrollment
                from groups.models import Group
                
                stats.update({
                    'total_users': CustomUser.objects.count(),
                    'active_users': CustomUser.objects.filter(is_active=True).count(),
                    'total_courses': Course.objects.count(),
                    'active_courses': Course.objects.filter(is_active=True).count(),
                    'total_enrollments': CourseEnrollment.objects.count(),
                    'completed_enrollments': CourseEnrollment.objects.filter(completed=True).count(),
                    'total_groups': Group.objects.count(),
                })
                
            elif user.role == 'superadmin':
                # Super admin stats - OPTIMIZED
                business_ids = user.business_assignments.filter(is_active=True).values_list('business_id', flat=True)
                
                stats.update({
                    'total_users': CustomUser.objects.filter(
                        Q(branch__business_id__in=business_ids) | 
                        Q(business_assignments__business_id__in=business_ids)
                    ).distinct().count(),
                    'active_users': CustomUser.objects.filter(
                        Q(branch__business_id__in=business_ids) | 
                        Q(business_assignments__business_id__in=business_ids),
                        is_active=True
                    ).distinct().count(),
                    'total_courses': Course.objects.filter(branch__business_id__in=business_ids).count(),
                    'active_courses': Course.objects.filter(branch__business_id__in=business_ids, is_active=True).count(),
                    'total_enrollments': CourseEnrollment.objects.filter(
                        Q(course__branch__business_id__in=business_ids) |
                        Q(user__business_assignments__business_id__in=business_ids)
                    ).distinct().count(),
                    'completed_enrollments': CourseEnrollment.objects.filter(
                        Q(course__branch__business_id__in=business_ids) |
                        Q(user__business_assignments__business_id__in=business_ids),
                        completed=True
                    ).distinct().count(),
                })
                
            elif user.role == 'admin':
                # Admin stats - OPTIMIZED
                stats.update({
                    'total_users': CustomUser.objects.filter(branch=user.branch).count(),
                    'active_users': CustomUser.objects.filter(branch=user.branch, is_active=True).count(),
                    'total_courses': Course.objects.filter(branch=user.branch).count(),
                    'active_courses': Course.objects.filter(branch=user.branch, is_active=True).count(),
                    'total_enrollments': CourseEnrollment.objects.filter(course__branch=user.branch).count(),
                    'completed_enrollments': CourseEnrollment.objects.filter(course__branch=user.branch, completed=True).count(),
                })
                
            elif user.role == 'instructor':
                # Instructor stats - OPTIMIZED
                stats.update({
                    'total_courses': Course.objects.filter(instructor=user).count(),
                    'active_courses': Course.objects.filter(instructor=user, is_active=True).count(),
                    'total_students': CourseEnrollment.objects.filter(course__instructor=user).count(),
                    'completed_students': CourseEnrollment.objects.filter(course__instructor=user, completed=True).count(),
                })
                
            else:
                # Learner stats - OPTIMIZED
                stats.update({
                    'total_enrollments': CourseEnrollment.objects.filter(user=user).count(),
                    'completed_enrollments': CourseEnrollment.objects.filter(user=user, completed=True).count(),
                    'in_progress_enrollments': CourseEnrollment.objects.filter(user=user, completed=False).count(),
                })
                
        except Exception as e:
            logger.error(f"Error getting dashboard stats: {str(e)}")
            stats = {'error': str(e)}
        
        return stats
