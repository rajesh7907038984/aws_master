"""
Dashboard Caching and Optimization Utilities
Provides caching mechanisms for expensive dashboard calculations.
"""

import logging
from django.core.cache import cache
from django.db.models import Count, Q, Avg, Sum
from django.utils import timezone
from datetime import timedelta
from users.models import CustomUser
from courses.models import Course, CourseEnrollment, TopicProgress
from branches.models import Branch
from django.contrib.admin.models import LogEntry
from django.contrib.contenttypes.models import ContentType

logger = logging.getLogger(__name__)

class DashboardCache:
    """Dashboard caching utility for performance optimization"""
    
    # Cache timeout settings (in seconds)
    CACHE_TIMEOUT_SHORT = 300      # 5 minutes for frequently changing data
    CACHE_TIMEOUT_MEDIUM = 900     # 15 minutes for moderate data
    CACHE_TIMEOUT_LONG = 3600      # 1 hour for stable data
    
    @staticmethod
    def _safe_cache_get(key, default=None):
        """Safely get from cache with fallback"""
        try:
            return cache.get(key, default)
        except Exception as e:
            logger.warning(f"Cache get failed for key '{key}': {str(e)}. Returning default value.")
            return default
    
    @staticmethod
    def _safe_cache_set(key, value, timeout=None):
        """Safely set cache with fallback"""
        try:
            cache.set(key, value, timeout)
            return True
        except Exception as e:
            logger.warning(f"Cache set failed for key '{key}': {str(e)}. Continuing without cache.")
            return False
    
    @staticmethod
    def _safe_cache_delete(key):
        """Safely delete from cache with fallback"""
        try:
            cache.delete(key)
            return True
        except Exception as e:
            logger.warning(f"Cache delete failed for key '{key}': {str(e)}. Continuing without cache.")
            return False
    
    @staticmethod
    def get_cache_key(prefix, user_id=None, branch_id=None, business_id=None, timeframe=None):
        """Generate cache key with optional parameters"""
        key_parts = [prefix]
        if user_id:
            key_parts.append(f"u{user_id}")
        if branch_id:
            key_parts.append(f"b{branch_id}")
        if business_id:
            key_parts.append(f"bus{business_id}")
        if timeframe:
            key_parts.append(f"t{timeframe}")
        return "_".join(key_parts)
    
    @staticmethod
    def get_global_stats():
        """Get cached global statistics for global admin dashboard"""
        cache_key = "dashboard_global_stats"
        stats = DashboardCache._safe_cache_get(cache_key)
        
        if stats is None:
            logger.info("Cache miss for global stats, calculating...")
            stats = CustomUser.objects.aggregate(
                total_users=Count('id'),
                active_users=Count('id', filter=Q(is_active=True)),
                globaladmin_count=Count('id', filter=Q(role='globaladmin')),
                superadmin_count=Count('id', filter=Q(role='superadmin')),
                admin_count=Count('id', filter=Q(role='admin')),
                instructor_count=Count('id', filter=Q(role='instructor')),
                learner_count=Count('id', filter=Q(role='learner'))
            )
            
            # Add course and branch counts
            stats['total_courses'] = Course.objects.count()
            stats['total_branches'] = Branch.objects.count()
            
            # Add enrollment stats - only include learner role users
            enrollment_stats = CourseEnrollment.objects.filter(user__role='learner').aggregate(
                total_enrollments=Count('id'),
                completed_enrollments=Count('id', filter=Q(completed=True))
            )
            stats.update(enrollment_stats)
            
            # Calculate completion rate
            if stats['total_enrollments'] > 0:
                stats['completion_rate'] = round(
                    (stats['completed_enrollments'] / stats['total_enrollments']) * 100
                )
            else:
                stats['completion_rate'] = 0
            
            DashboardCache._safe_cache_set(cache_key, stats, DashboardCache.CACHE_TIMEOUT_MEDIUM)
            logger.info("Global stats cached successfully")
        
        return stats
    
    @staticmethod
    def get_branch_stats(branch_id):
        """Get cached branch-specific statistics"""
        cache_key = DashboardCache.get_cache_key("dashboard_branch_stats", branch_id=branch_id)
        stats = DashboardCache._safe_cache_get(cache_key)
        
        if stats is None:
            logger.info(f"Cache miss for branch {branch_id} stats, calculating...")
            
            # Branch user stats
            branch_users = CustomUser.objects.filter(branch_id=branch_id)
            stats = branch_users.aggregate(
                total_users=Count('id'),
                active_users=Count('id', filter=Q(is_active=True)),
                instructor_count=Count('id', filter=Q(role='instructor')),
                learner_count=Count('id', filter=Q(role='learner'))
            )
            
            # Branch course stats
            branch_courses = Course.objects.filter(branch_id=branch_id)
            stats['total_courses'] = branch_courses.count()
            
            # Branch enrollment stats
            branch_enrollments = CourseEnrollment.objects.filter(user__branch_id=branch_id, user__role='learner')
            
            # Sync completion status for branch enrollments before calculating stats
            CourseEnrollment.sync_branch_completions(branch_id)
            
            enrollment_stats = branch_enrollments.aggregate(
                total_enrollments=Count('id'),
                completed_enrollments=Count('id', filter=Q(completed=True))
            )
            stats.update(enrollment_stats)
            
            # Calculate completion rate
            if stats['total_enrollments'] > 0:
                stats['completion_rate'] = round(
                    (stats['completed_enrollments'] / stats['total_enrollments']) * 100
                )
            else:
                stats['completion_rate'] = 0
            
            DashboardCache._safe_cache_set(cache_key, stats, DashboardCache.CACHE_TIMEOUT_MEDIUM)
            logger.info(f"Branch {branch_id} stats cached successfully")
        
        return stats
    
    @staticmethod
    def get_instructor_stats(user_id):
        """Get cached instructor-specific statistics"""
        cache_key = DashboardCache.get_cache_key("dashboard_instructor_stats", user_id=user_id)
        stats = DashboardCache._safe_cache_get(cache_key)
        
        if stats is None:
            logger.info(f"Cache miss for instructor {user_id} stats, calculating...")
            
            # Get assigned courses efficiently
            # Include courses where user is:
            # 1. The direct instructor, OR
            # 2. Member of accessible group with instructor role, OR
            # 3. Member of accessible group with general access (admin assigned)
            assigned_courses = Course.objects.filter(
                Q(instructor_id=user_id) |
                Q(accessible_groups__memberships__user_id=user_id,
                  accessible_groups__memberships__is_active=True,
                  accessible_groups__memberships__custom_role__name__icontains='instructor') |
                Q(accessible_groups__memberships__user_id=user_id,
                  accessible_groups__memberships__is_active=True)
            ).distinct()
            
            # Count groups this instructor has access to through their courses
            from groups.models import BranchGroup
            instructor_groups_count = BranchGroup.objects.filter(
                Q(memberships__user_id=user_id, memberships__is_active=True) |
                Q(course_groups__course__in=assigned_courses)
            ).distinct().count()
            
            stats = {
                'assigned_courses_count': assigned_courses.count(),
                'instructor_groups_count': instructor_groups_count
            }
            
            # Get unique learners count
            stats['unique_learners_count'] = CourseEnrollment.objects.filter(
                course__in=assigned_courses,
                user__role='learner'
            ).values('user').distinct().count()
            
            # Calculate completion rate - only include learner role users
            course_enrollments = CourseEnrollment.objects.filter(course__in=assigned_courses, user__role='learner')
            total_enrollments = course_enrollments.count()
            completed_enrollments = course_enrollments.filter(completed=True).count()
            
            if total_enrollments > 0:
                stats['completion_rate'] = round((completed_enrollments / total_enrollments) * 100)
            else:
                stats['completion_rate'] = 0
            
            DashboardCache._safe_cache_set(cache_key, stats, DashboardCache.CACHE_TIMEOUT_MEDIUM)
            logger.info(f"Instructor {user_id} stats cached successfully")
        
        return stats
    
    @staticmethod
    def clear_instructor_cache(user_id):
        """Clear cached instructor statistics when courses or memberships change"""
        cache_key = DashboardCache.get_cache_key("dashboard_instructor_stats", user_id=user_id)
        cache.delete(cache_key)
        logger.info(f"Cleared instructor cache for user {user_id}")
    
    @staticmethod
    def clear_all_dashboard_cache():
        """Clear all dashboard-related cache for data consistency"""
        import re
        from django.conf import settings
        
        try:
            # Get all cache keys that start with dashboard prefixes
            dashboard_prefixes = [
                "dashboard_progress",
                "dashboard_activity", 
                "dashboard_instructor_stats",
                "dashboard_recent_activities"
            ]
            
            # Clear cache keys matching dashboard patterns
            for prefix in dashboard_prefixes:
                cache_pattern = f"{prefix}*"
                # In Redis, we can use pattern matching
                if hasattr(cache, 'delete_pattern'):
                    cache.delete_pattern(cache_pattern)
                else:
                    # Fallback for other cache backends
                    cache.clear()  # Clear all cache as fallback
                    break
                    
            logger.info("Cleared all dashboard cache for consistency")
                    
        except Exception as e:
            logger.error(f"Error clearing dashboard cache: {e}")
    
    @staticmethod
    def clear_progress_cache(branch_id=None, business_id=None):
        """Clear progress-related cache when enrollment data changes"""
        try:
            # Clear general progress cache
            cache.delete("dashboard_progress")
            
            # Clear branch-specific cache if branch_id provided
            if branch_id:
                cache.delete(f"dashboard_progress_b{branch_id}")
                
            # Clear business-specific cache if business_id provided  
            if business_id:
                cache.delete(f"dashboard_progress_bus{business_id}")
                
            logger.info(f"Cleared progress cache for branch_id={branch_id}, business_id={business_id}")
            
        except Exception as e:
            logger.error(f"Error clearing progress cache: {e}")
    
    @staticmethod 
    def clear_activity_cache(branch_id=None):
        """Clear activity-related cache when login/completion data changes"""
        try:
            # Clear activity cache for different timeframes
            timeframes = ['day', 'week', 'month']
            for timeframe in timeframes:
                cache_key = f"dashboard_activity_{timeframe}"
                if branch_id:
                    cache_key += f"_b{branch_id}"
                cache.delete(cache_key)
                
            logger.info(f"Cleared activity cache for branch_id={branch_id}")
            
        except Exception as e:
            logger.error(f"Error clearing activity cache: {e}")
    
    @staticmethod
    def get_progress_data(user=None, branch_id=None, business_id=None, apply_role_filtering=True):
        """Get cached course progress data with optional role-based filtering"""
        cache_key_parts = ["dashboard_progress"]
        if user and hasattr(user, 'id'):
            cache_key_parts.append(f"u{user.id}")
        if branch_id:
            cache_key_parts.append(f"b{branch_id}")
        if business_id:
            cache_key_parts.append(f"bus{business_id}")
        if apply_role_filtering:
            cache_key_parts.append("filtered")
        
        cache_key = "_".join(cache_key_parts)
        progress_data = DashboardCache._safe_cache_get(cache_key)
        
        if progress_data is None:
            logger.info("Cache miss for progress data, calculating...")
            
            # Base queryset for enrollments
            enrollments = CourseEnrollment.objects.all()
            
            # Apply role-based filtering if requested (for consistency with reports)
            if apply_role_filtering and user:
                try:
                    # Import here to avoid circular imports
                    from reports.views import apply_role_based_filtering
                    enrollments = apply_role_based_filtering(user, enrollments, business_id, branch_id)
                except ImportError:
                    logger.warning("Could not import apply_role_based_filtering, using basic filtering")
                    # Fallback to basic filtering
                    if branch_id:
                        enrollments = enrollments.filter(user__branch_id=branch_id)
                    elif user and user.role == 'learner':
                        enrollments = enrollments.filter(user=user)
            else:
                # Original basic filtering logic
                if branch_id:
                    enrollments = enrollments.filter(user__branch_id=branch_id)
                elif user and user.role == 'learner':
                    enrollments = enrollments.filter(user=user)
            
            # For completion rate calculations, only include learner role users
            enrollments = enrollments.filter(user__role='learner')
            
            # Calculate progress statistics
            total_enrollments = enrollments.count()
            
            if total_enrollments > 0:
                completed_count = enrollments.filter(completed=True).count()
                
                # Count in_progress and not_started based on actual topic completion
                in_progress_count = 0
                not_started_count = 0
                
                for enrollment in enrollments.filter(completed=False):
                    try:
                        # Use the enrollment's get_progress method which counts completed topics
                        progress = enrollment.get_progress()
                        if progress > 0:
                            in_progress_count += 1
                        else:
                            not_started_count += 1
                    except Exception:
                        # If there's an error calculating progress, assume not started
                        not_started_count += 1
                
                # Calculate percentages
                completed_percentage = round((completed_count / total_enrollments) * 100)
                in_progress_percentage = round((in_progress_count / total_enrollments) * 100)
                not_started_percentage = round((not_started_count / total_enrollments) * 100)
                not_passed_percentage = max(0, 100 - completed_percentage - in_progress_percentage - not_started_percentage)
                
                progress_data = {
                    'completed_count': completed_count,
                    'in_progress_count': in_progress_count,
                    'not_started_count': not_started_count,
                    'completed_percentage': completed_percentage,
                    'in_progress_percentage': in_progress_percentage,
                    'not_started_percentage': not_started_percentage,
                    'not_passed_percentage': not_passed_percentage,
                }
            else:
                progress_data = {
                    'completed_count': 0,
                    'in_progress_count': 0,
                    'not_started_count': 0,
                    'completed_percentage': 0,
                    'in_progress_percentage': 0,
                    'not_started_percentage': 0,
                    'not_passed_percentage': 0,
                }
            
            DashboardCache._safe_cache_set(cache_key, progress_data, DashboardCache.CACHE_TIMEOUT_SHORT)
            logger.info("Progress data cached successfully")
        
        return progress_data
    
    @staticmethod
    def get_activity_data(timeframe='month', branch_id=None):
        """Get cached portal activity data"""
        cache_key = DashboardCache.get_cache_key(
            "dashboard_activity", 
            branch_id=branch_id, 
            timeframe=timeframe
        )
        activity_data = DashboardCache._safe_cache_get(cache_key)
        
        if activity_data is None:
            logger.info(f"Cache miss for activity data ({timeframe}), calculating...")
            
            today = timezone.now().date()
            
            # Set date range based on timeframe
            if timeframe == 'day':
                start_date = today
                hours = 24
                dates = [(timezone.now() - timedelta(hours=i)).strftime('%I %p') for i in range(hours-1, -1, -1)]
                # For hourly data, use different calculation
                activity_data = DashboardCache._calculate_hourly_activity(dates, today, branch_id)
            elif timeframe == 'week':
                start_date = today - timedelta(days=6)
                days = 7
                dates = [(start_date + timedelta(days=i)).strftime('%a') for i in range(days)]
                activity_data = DashboardCache._calculate_daily_activity(dates, start_date, days, branch_id)
            else:  # month
                start_date = today - timedelta(days=29)
                days = 30
                dates = [(start_date + timedelta(days=i)).strftime('%b %d') for i in range(days)]
                activity_data = DashboardCache._calculate_daily_activity(dates, start_date, days, branch_id)
            
            activity_data['labels'] = dates
            
            DashboardCache._safe_cache_set(cache_key, activity_data, DashboardCache.CACHE_TIMEOUT_SHORT)
            logger.info(f"Activity data ({timeframe}) cached successfully")
        
        return activity_data
    
    @staticmethod
    def _calculate_daily_activity(dates, start_date, days, branch_id=None):
        """Calculate daily activity data efficiently"""
        # Initialize data structures
        login_counts = [0] * days
        completion_counts = [0] * days
        
        # Build base querysets
        login_query = CustomUser.objects.filter(
            last_login__date__gte=start_date,
            last_login__date__lte=start_date + timedelta(days=days-1)
        )
        completion_query = CourseEnrollment.objects.filter(
            completed=True,
            completion_date__date__gte=start_date,
            completion_date__date__lte=start_date + timedelta(days=days-1)
        )
        
        if branch_id:
            login_query = login_query.filter(branch_id=branch_id)
            completion_query = completion_query.filter(user__branch_id=branch_id)
        
        # Get login data in batch
        logins = login_query.values('last_login__date').annotate(count=Count('id'))
        for login in logins:
            login_date = login['last_login__date']
            day_index = (login_date - start_date).days
            if 0 <= day_index < days:
                login_counts[day_index] = login['count']
        
        # Get completion data in batch
        completions = completion_query.values('completion_date__date').annotate(count=Count('id'))
        for completion in completions:
            completion_date = completion['completion_date__date']
            day_index = (completion_date - start_date).days
            if 0 <= day_index < days:
                completion_counts[day_index] = completion['count']
        
        return {
            'logins': login_counts,
            'completions': completion_counts
        }
    
    @staticmethod
    def _calculate_hourly_activity(dates, today, branch_id=None):
        """Calculate hourly activity data efficiently"""
        from django.db.models.functions import ExtractHour
        
        hours = 24
        login_counts = [0] * hours
        completion_counts = [0] * hours
        
        # Get login data for today
        login_query = CustomUser.objects.filter(last_login__date=today)
        completion_query = CourseEnrollment.objects.filter(
            completed=True,
            completion_date__date=today
        )
        
        if branch_id:
            login_query = login_query.filter(branch_id=branch_id)
            completion_query = completion_query.filter(user__branch_id=branch_id)
        
        # Get hourly login data
        logins = login_query.annotate(
            hour=ExtractHour('last_login')
        ).values('hour').annotate(count=Count('id'))
        
        for login in logins:
            hour = login['hour']
            current_hour = timezone.now().hour
            hour_index = (current_hour - hour) % 24
            if 0 <= hour_index < hours:
                login_counts[hours - 1 - hour_index] = login['count']
        
        # Get hourly completion data
        completions = completion_query.annotate(
            hour=ExtractHour('completion_date')
        ).values('hour').annotate(count=Count('id'))
        
        for completion in completions:
            hour = completion['hour']
            current_hour = timezone.now().hour
            hour_index = (current_hour - hour) % 24
            if 0 <= hour_index < hours:
                completion_counts[hours - 1 - hour_index] = completion['count']
        
        return {
            'logins': login_counts,
            'completions': completion_counts
        }
    
    @staticmethod
    def get_recent_activities(limit=10, branch_id=None):
        """Get cached recent activities"""
        cache_key = DashboardCache.get_cache_key(
            "dashboard_recent_activities", 
            branch_id=branch_id
        )
        activities = DashboardCache._safe_cache_get(cache_key)
        
        if activities is None:
            logger.info("Cache miss for recent activities, calculating...")
            
            # Get recent log entries
            log_query = LogEntry.objects.select_related('user').order_by('-action_time')[:limit]
            
            activities = []
            for entry in log_query:
                # Filter by branch if specified
                if branch_id and entry.user and entry.user.branch_id != branch_id:
                    continue
                    
                activities.append({
                    'description': f"{entry.user.username if entry.user else 'System'} {entry.get_action_flag_display()} {entry.object_repr}",
                    'timestamp': entry.action_time,
                    'icon': 'user-edit' if entry.action_flag == 2 else 'plus' if entry.action_flag == 1 else 'trash',
                    'user': entry.user.username if entry.user else 'System'
                })
            
            DashboardCache._safe_cache_set(cache_key, activities, DashboardCache.CACHE_TIMEOUT_SHORT)
            logger.info("Recent activities cached successfully")
        
        return activities
    
    @staticmethod
    def clear_user_cache(user_id):
        """Clear cache for specific user"""
        # Use the same key generation logic as in get_instructor_stats
        instructor_cache_key = DashboardCache.get_cache_key("dashboard_instructor_stats", user_id=user_id)
        
        cache_patterns = [
            instructor_cache_key,
            f"dashboard_progress_u{user_id}",  # Also clear progress cache
        ]
        
        for pattern in cache_patterns:
            DashboardCache._safe_cache_delete(pattern)
        
        logger.info(f"Cleared cache for user {user_id} - patterns: {cache_patterns}")
    
    @staticmethod
    def clear_branch_cache(branch_id):
        """Clear cache for specific branch"""
        cache_patterns = [
            f"dashboard_branch_stats_b{branch_id}",
            f"dashboard_activity_b{branch_id}",
        ]
        
        for pattern in cache_patterns:
            DashboardCache._safe_cache_delete(pattern)
        
        logger.info(f"Cleared cache for branch {branch_id}")
    
    @staticmethod
    def clear_all_dashboard_cache():
        """Clear all dashboard cache entries"""
        DashboardCache._safe_cache_delete("dashboard_global_stats")
        logger.info("Cleared all dashboard cache entries") 