from django.db import models
from django.core.exceptions import ValidationError
from django.conf import settings
from typing import Dict, Optional, Union, TYPE_CHECKING
from django.db.models import QuerySet

if TYPE_CHECKING:
    from users.models import CustomUser

class Branch(models.Model):
    name = models.CharField(max_length=255, unique=True)
    business = models.ForeignKey(
        'business.Business',
        on_delete=models.CASCADE,
        related_name='branches',
        null=True,
        blank=True,
        help_text="The business this branch belongs to"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    
    # SharePoint Integration Control
    sharepoint_integration_enabled = models.BooleanField(
        default=False,
        help_text="Enable SharePoint integration for this branch. Global admin can control this setting."
    )
    
    # Order Management Features Control
    order_management_enabled = models.BooleanField(
        default=False,
        help_text="Enable order management features for this branch. Global admin can control this setting."
    )
    
    # SCORM Integration Control
    scorm_integration_enabled = models.BooleanField(
        default=False,
        help_text="Enable SCORM integration for this branch. Admin can control this setting."
    )

    def __str__(self):
        if self.business:
            return f"{self.business.name} - {self.name}"
        return self.name

    def get_branch_users(self) -> 'QuerySet[CustomUser]':
        """Get all users belonging to this branch"""
        return self.users.all()

    def get_branch_admins(self) -> 'QuerySet[CustomUser]':
        """Get admin users of this branch"""
        return self.users.filter(role='admin', is_active=True)

    def get_branch_instructors(self) -> 'QuerySet[CustomUser]':
        """Get instructor users of this branch"""
        return self.users.filter(role='instructor', is_active=True)

    def get_branch_learners(self) -> 'QuerySet[CustomUser]':
        """Get learner users of this branch"""
        return self.users.filter(role='learner', is_active=True)

    def clean(self) -> None:
        """Validate branch data"""
        if not self.name:
            raise ValidationError('Branch name is required')

    def validate_branch_hierarchy(self) -> None:
        """Validate branch hierarchy requirements"""
        # Skip validation for new branches
        if not self.pk:
            return
        
        # Skip validation for inactive branches (being deactivated/deleted)
        if not self.is_active:
            return
        
        if not self.get_branch_admins().exists():
            raise ValidationError("Each branch must have at least one admin")

    def save(self, *args, **kwargs) -> None:
        self.clean()
        # Only validate hierarchy for existing branches
        if self.pk:
            self.validate_branch_hierarchy()
        super().save(*args, **kwargs)

    def get_branch_statistics(self) -> Dict[str, int]:
        """Get statistics about users in the branch"""
        return {
            'total_users': self.users.filter(is_active=True).count(),
            'admins': self.get_branch_admins().count(),
            'instructors': self.get_branch_instructors().count(),
            'learners': self.get_branch_learners().count()
        }

    def get_total_users(self) -> int:
        """Get total number of users in this branch"""
        return self.users.count()

    def get_active_users(self) -> int:
        """Get number of active users in this branch"""
        return self.users.filter(is_active=True).count()

    def can_add_user(self) -> bool:
        """Check if branch can accommodate more users based on limits"""
        branch_limits = getattr(self, 'branch_user_limits', None)
        if branch_limits:
            current_users = self.get_active_users()
            return current_users < branch_limits.user_limit
        return True  # No limits set, can add users

    def get_remaining_user_slots(self) -> Union[int, float]:
        """Get number of remaining user slots in this branch"""
        branch_limits = getattr(self, 'branch_user_limits', None)
        if branch_limits:
            current_users = self.get_active_users()
            return max(0, branch_limits.user_limit - current_users)
        return float('inf')  # No limits set

    class Meta:
        verbose_name = 'Branch'
        verbose_name_plural = 'Branches'
        ordering = ['business__name', 'name']


class BranchUserLimits(models.Model):
    """Model to store user limits for each branch"""
    branch = models.OneToOneField(
        Branch,
        on_delete=models.CASCADE,
        related_name='branch_user_limits',
        help_text="The branch these limits apply to"
    )
    user_limit = models.PositiveIntegerField(
        default=100,
        help_text="Maximum number of users allowed in this branch"
    )
    admin_limit = models.PositiveIntegerField(
        default=5,
        help_text="Maximum number of admin users allowed in this branch"
    )
    instructor_limit = models.PositiveIntegerField(
        default=20,
        help_text="Maximum number of instructor users allowed in this branch"
    )
    learner_limit = models.PositiveIntegerField(
        default=500,
        help_text="Maximum number of learner users allowed in this branch"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='updated_branch_limits',
        help_text="Admin who last updated these limits"
    )

    class Meta:
        verbose_name = 'Branch User Limits'
        verbose_name_plural = 'Branch User Limits'
        ordering = ['branch__name']

    def __str__(self):
        return f"User limits for {self.branch.name}"

    def clean(self):
        """Validate that limits are reasonable"""
        if self.user_limit < (self.admin_limit + self.instructor_limit):
            raise ValidationError(
                "Total user limit must be at least the sum of admin and instructor limits"
            )

    def is_user_limit_reached(self):
        """Check if the user limit has been reached for this branch"""
        current_users = self.branch.get_active_users()
        return current_users >= self.user_limit

    def is_role_limit_reached(self, role):
        """Check if the limit for a specific role has been reached"""
        if role == 'admin':
            current_count = self.branch.users.filter(role='admin', is_active=True).count()
            return current_count >= self.admin_limit
        elif role == 'instructor':
            current_count = self.branch.users.filter(role='instructor', is_active=True).count()
            return current_count >= self.instructor_limit
        elif role == 'learner':
            current_count = self.branch.users.filter(role='learner', is_active=True).count()
            return current_count >= self.learner_limit
        return False

    def get_role_usage_data(self):
        """Get current usage data for all roles - optimized version"""
        from django.db.models import Count, Q
        
        # Use single aggregated query instead of multiple count queries
        counts = self.branch.users.filter(is_active=True).aggregate(
            total_users=Count('id'),
            admin_count=Count('id', filter=Q(role='admin')),
            instructor_count=Count('id', filter=Q(role='instructor')),
            learner_count=Count('id', filter=Q(role='learner'))
        )
        
        total_users = counts.get('total_users', 0)
        admin_count = counts.get('admin_count', 0)
        instructor_count = counts.get('instructor_count', 0)
        learner_count = counts.get('learner_count', 0)
        
        return {
            'total': {
                'current': total_users,
                'limit': self.user_limit,
                'remaining': max(0, self.user_limit - total_users),
                'percentage': min(100, (total_users / self.user_limit) * 100) if self.user_limit > 0 else 0
            },
            'admin': {
                'current': admin_count,
                'limit': self.admin_limit,
                'remaining': max(0, self.admin_limit - admin_count)
            },
            'instructor': {
                'current': instructor_count,
                'limit': self.instructor_limit,
                'remaining': max(0, self.instructor_limit - instructor_count)
            },
            'learner': {
                'current': learner_count,
                'limit': self.learner_limit,
                'remaining': max(0, self.learner_limit - learner_count)
            }
        } 


class AdminBranchAssignment(models.Model):
    """
    Model to track additional branch assignments for admin users.
    Allows super admins to assign admin users to multiple branches within a business.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='additional_branch_assignments',
        help_text="Admin user assigned to additional branch"
    )
    branch = models.ForeignKey(
        Branch,
        on_delete=models.CASCADE,
        related_name='additional_admin_assignments',
        help_text="Branch assigned to the admin user"
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_admin_branches',
        help_text="Super admin who assigned this branch to the admin user"
    )
    assigned_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(
        default=True, 
        help_text="Whether this assignment is active"
    )
    notes = models.TextField(
        blank=True, 
        null=True, 
        help_text="Optional notes about this assignment"
    )

    class Meta:
        unique_together = ['user', 'branch']
        verbose_name = 'Admin Branch Assignment'
        verbose_name_plural = 'Admin Branch Assignments'
        ordering = ['user__username', 'branch__name']
        indexes = [
            models.Index(fields=['user', 'is_active']),
            models.Index(fields=['branch', 'is_active']),
            models.Index(fields=['assigned_by']),
        ]

    def __str__(self):
        return f"{self.user.username} → {self.branch.name}"

    def clean(self):
        """Validate admin branch assignment"""
        if self.user and self.user.role != 'admin':
            raise ValidationError('Only admin users can be assigned to additional branches')
        
        # Prevent assignment to user's primary branch
        if self.user and self.user.branch == self.branch:
            raise ValidationError(
                f'User {self.user.username} is already assigned to {self.branch.name} as their primary branch'
            )
        
        # Validate that both user and branch belong to the same business
        if self.user and self.branch:
            user_business = self.user.branch.business if self.user.branch else None
            branch_business = self.branch.business
            
            if user_business != branch_business:
                raise ValidationError(
                    'Admin users can only be assigned to branches within the same business'
                )

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    @classmethod
    def get_user_accessible_branches(cls, user):
        """Get all branches the admin user has access to (primary + additional)"""
        if user.role != 'admin':
            return Branch.objects.none()
        
        # Start with user's primary branch
        accessible_branches = Branch.objects.filter(id=user.branch.id) if user.branch else Branch.objects.none()
        
        # Add additional assigned branches
        additional_branches = Branch.objects.filter(
            additional_admin_assignments__user=user,
            additional_admin_assignments__is_active=True
        )
        
        # Combine and return unique branches
        return (accessible_branches | additional_branches).distinct()

    @classmethod
    def get_user_switchable_branches(cls, user):
        """Get branches the admin user can switch to (excluding current primary)"""
        if user.role != 'admin':
            return Branch.objects.none()
        
        return Branch.objects.filter(
            additional_admin_assignments__user=user,
            additional_admin_assignments__is_active=True
        ).distinct()