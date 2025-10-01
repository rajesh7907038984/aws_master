"""
Cache invalidation utilities for maintaining data consistency between reports and dashboard
"""
import logging
from django.core.cache import cache
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

logger = logging.getLogger(__name__)


class CacheInvalidationManager:
    """Manager class for handling cache invalidation across the application"""
    
    @staticmethod
    def invalidate_dashboard_data(branch_id=None, business_id=None, user_id=None):
        """
        Invalidate dashboard and reports cache when data changes
        
        Args:
            branch_id: Branch ID if change affects specific branch
            business_id: Business ID if change affects specific business
            user_id: User ID if change affects specific user
        """
        try:
            from core.utils.dashboard_cache import DashboardCache
            
            # Clear general dashboard cache
            DashboardCache.clear_all_dashboard_cache()
            
            # Clear progress-specific cache
            DashboardCache.clear_progress_cache(branch_id, business_id)
            
            # Clear activity-specific cache
            DashboardCache.clear_activity_cache(branch_id)
            
            # Clear instructor-specific cache if user_id provided
            if user_id:
                DashboardCache.clear_instructor_cache(user_id)
            
            logger.info(f"Cache invalidated for branch_id={branch_id}, business_id={business_id}, user_id={user_id}")
            
        except Exception as e:
            logger.error(f"Error invalidating dashboard cache: {e}")
    
    @staticmethod
    def invalidate_on_enrollment_change(enrollment):
        """Invalidate cache when enrollment data changes"""
        try:
            branch_id = enrollment.user.branch_id if enrollment.user.branch else None
            business_id = enrollment.user.branch.business_id if enrollment.user.branch and enrollment.user.branch.business else None
            
            CacheInvalidationManager.invalidate_dashboard_data(
                branch_id=branch_id,
                business_id=business_id
            )
            
        except Exception as e:
            logger.error(f"Error invalidating cache on enrollment change: {e}")
    
    @staticmethod
    def invalidate_on_user_activity(user):
        """Invalidate cache when user activity changes (login, completion, etc)"""
        try:
            branch_id = user.branch_id if user.branch else None
            business_id = user.branch.business_id if user.branch and user.branch.business else None
            
            CacheInvalidationManager.invalidate_dashboard_data(
                branch_id=branch_id,
                business_id=business_id,
                user_id=user.id
            )
            
        except Exception as e:
            logger.error(f"Error invalidating cache on user activity: {e}")


# Signal handlers for automatic cache invalidation
@receiver(post_save, sender='courses.CourseEnrollment')
def invalidate_cache_on_enrollment_save(sender, instance, **kwargs):
    """Invalidate cache when enrollment is saved"""
    CacheInvalidationManager.invalidate_on_enrollment_change(instance)


@receiver(post_delete, sender='courses.CourseEnrollment')  
def invalidate_cache_on_enrollment_delete(sender, instance, **kwargs):
    """Invalidate cache when enrollment is deleted"""
    CacheInvalidationManager.invalidate_on_enrollment_change(instance)


@receiver(post_save, sender='users.CustomUser')
def invalidate_cache_on_user_save(sender, instance, **kwargs):
    """Invalidate cache when user data changes (last_login, etc)"""
    # Only invalidate if it's an existing user update that might affect activity data
    if not kwargs.get('created', False):
        CacheInvalidationManager.invalidate_on_user_activity(instance)