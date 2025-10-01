from django.db import models
from django.core.exceptions import ValidationError
from django.conf import settings
from django.db.models import Count, Q
from django.db.models.signals import post_save
from django.dispatch import receiver

class Business(models.Model):
    name = models.CharField(max_length=255, unique=True, help_text="Business name")
    description = models.TextField(blank=True, null=True, help_text="Business description")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True, help_text="Whether this business is active")
    
    # Business contact information
    address_line1 = models.CharField(max_length=255, blank=True, null=True)
    address_line2 = models.CharField(max_length=255, blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    state_province = models.CharField(max_length=100, blank=True, null=True)
    postal_code = models.CharField(max_length=20, blank=True, null=True)
    country = models.CharField(max_length=100, blank=True, null=True, default="United Kingdom")
    phone = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    website = models.URLField(blank=True, null=True)

    class Meta:
        verbose_name = 'Business'
        verbose_name_plural = 'Businesses'
        # Use primary key ordering to avoid potential column issues during deletion
        ordering = ['id']

    def __str__(self):
        return self.name

    def get_business_super_admins(self):
        """Get all super admin users assigned to this business"""
        from users.models import CustomUser
        return CustomUser.objects.filter(
            business_assignments__business=self,
            business_assignments__is_active=True,
            role='superadmin'
        )

    def get_business_branches(self):
        """Get all branches belonging to this business"""
        return self.branches.filter(is_active=True)

    def get_default_branch(self):
        """Get the default branch for this business"""
        return self.branches.filter(name=f"{self.name} - Default Branch").first()

    def create_default_branch(self):
        """Create a default branch for this business if it doesn't exist"""
        default_branch = self.get_default_branch()
        if not default_branch:
            from branches.models import Branch
            default_branch = Branch.objects.create(
                name=f"{self.name} - Default Branch",
                business=self,
                description=f"Default branch for {self.name} business",
                is_active=True
            )
        return default_branch

    def get_business_branch_count(self):
        """Get count of active branches in this business"""
        return self.get_business_branches().count()

    def get_total_users_count(self):
        """Get total count of users across all branches in this business - optimized version"""
        # Use database aggregation instead of Python loops
        result = self.branches.filter(is_active=True).aggregate(
            total_users=Count('users', filter=Q(users__is_active=True))
        )
        return result.get('total_users', 0)

    def get_business_statistics(self):
        """Get comprehensive statistics about this business"""
        branches = self.get_business_branches()
        total_users = 0
        total_admins = 0
        total_instructors = 0
        total_learners = 0
        
        for branch in branches:
            total_users += branch.users.filter(is_active=True).count()
            total_admins += branch.get_branch_admins().count()
            total_instructors += branch.get_branch_instructors().count()
            total_learners += branch.get_branch_learners().count()
        
        return {
            'super_admins': self.get_business_super_admins().count(),
            'branches': branches.count(),
            'total_users': total_users,
            'total_admins': total_admins,
            'total_instructors': total_instructors,
            'total_learners': total_learners
        }

    def clean(self):
        """Validate business data"""
        if not self.name:
            raise ValidationError('Business name is required')

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)


class BusinessUserAssignment(models.Model):
    """Model to assign Super Admin users to businesses"""
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name='user_assignments',
        help_text="The business this user is assigned to"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='business_assignments',
        help_text="The super admin user assigned to this business"
    )
    assigned_at = models.DateTimeField(auto_now_add=True)
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_business_users',
        help_text="Global admin who assigned this user to the business"
    )
    is_active = models.BooleanField(default=True, help_text="Whether this assignment is active")

    class Meta:
        unique_together = ['business', 'user']
        verbose_name = 'Business User Assignment'
        verbose_name_plural = 'Business User Assignments'
        ordering = ['business__name', 'user__username']

    def __str__(self):
        return f"{self.user.username} -> {self.business.name}"

    def clean(self):
        """Validate business user assignment"""
        if self.user and self.user.role not in ['superadmin', 'globaladmin']:
            raise ValidationError('Only Super Admin and Global Admin users can be assigned to businesses')
        
        # Additional validation: only global admin can be assigned to default business
        if self.user and self.business:
            from core.utils.default_assignments import DefaultAssignmentManager
            if DefaultAssignmentManager.is_default_business(self.business):
                if not DefaultAssignmentManager.can_user_access_default_business(self.user):
                    raise ValidationError(f'Only Global Admin users can be assigned to the default business. User {self.user.username} has role: {self.user.role}')

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)


@receiver(post_save, sender=Business)
def create_default_branch_for_business(sender, instance, created, **kwargs):
    """Automatically create a default branch when a business is created"""
    if created:
        instance.create_default_branch()
        print(f"✅ Created default branch for business: {instance.name}")


@receiver(post_save, sender=BusinessUserAssignment)
def assign_user_to_appropriate_branch(sender, instance, created, **kwargs):
    """Automatically assign user to appropriate branch when assigned to a business"""
    if created and instance.is_active and instance.user.role in ['superadmin', 'globaladmin']:
        from core.utils.default_assignments import DefaultAssignmentManager
        
        # Check if this is assignment to default business
        if DefaultAssignmentManager.is_default_business(instance.business):
            # Only global admin can be assigned to default business and its default branch
            if instance.user.role == 'globaladmin':
                # Ensure the business has a default branch
                default_branch = instance.business.get_default_branch()
                if not default_branch:
                    default_branch = instance.business.create_default_branch()
                
                # Assign the user to the default branch if they don't have a branch
                if not instance.user.branch:
                    instance.user.branch = default_branch
                    instance.user.save()
                    print(f"✅ Assigned Global Admin {instance.user.username} to default branch: {default_branch.name}")
                elif instance.user.branch.business != instance.business:
                    # If user has a branch but it's in a different business, update it
                    instance.user.branch = default_branch
                    instance.user.save()
                    print(f"✅ Reassigned Global Admin {instance.user.username} to default branch: {default_branch.name}")
            else:
                # Super admin assigned to default business - this should not happen due to validation
                print(f"⚠️  Warning: Super Admin {instance.user.username} assigned to default business - this should be prevented")
        else:
            # Non-default business - assign to business's default branch or first available branch
            branches = instance.business.get_business_branches()
            if branches.exists():
                target_branch = branches.first()
                
                # Assign the user to the branch if they don't have a branch
                if not instance.user.branch:
                    instance.user.branch = target_branch
                    instance.user.save()
                    print(f"✅ Assigned {instance.user.username} to branch: {target_branch.name}")
                elif instance.user.branch.business != instance.business:
                    # If user has a branch but it's in a different business, update it
                    instance.user.branch = target_branch
                    instance.user.save()
                    print(f"✅ Reassigned {instance.user.username} to branch: {target_branch.name}")


class BusinessLimits(models.Model):
    """Model to store user and branch limits for each business"""
    business = models.OneToOneField(
        Business,
        on_delete=models.CASCADE,
        related_name='business_limits',
        help_text="The business these limits apply to"
    )
    total_user_limit = models.PositiveIntegerField(
        default=500,
        help_text="Maximum total number of users allowed across all branches in this business"
    )
    branch_creation_limit = models.PositiveIntegerField(
        default=10,
        help_text="Maximum number of branches that can be created for this business"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='updated_business_limits',
        help_text="Global admin who last updated these limits"
    )

    class Meta:
        verbose_name = 'Business Limits'
        verbose_name_plural = 'Business Limits'
        ordering = ['business__name']

    def __str__(self):
        return f"Limits for {self.business.name}"

    def is_user_limit_reached(self):
        """Check if the total user limit has been reached for this business"""
        current_users = self.business.get_total_users_count()
        return current_users >= self.total_user_limit

    def is_branch_creation_limit_reached(self):
        """Check if the branch creation limit has been reached for this business"""
        current_branches = self.business.get_business_branch_count()
        return current_branches >= self.branch_creation_limit

    def get_usage_data(self):
        """Get current usage data for the business - optimized version"""
        from django.db.models import Count, Q
        
        # Use optimized counting methods and database aggregation
        current_users = self.business.get_total_users_count()
        current_branches = self.business.get_business_branch_count()
        
        return {
            'users': {
                'current': current_users,
                'limit': self.total_user_limit,
                'percentage': (current_users / self.total_user_limit * 100) if self.total_user_limit > 0 else 0
            },
            'branches': {
                'current': current_branches,
                'limit': self.branch_creation_limit,
                'percentage': (current_branches / self.branch_creation_limit * 100) if self.branch_creation_limit > 0 else 0
            }
        }

    def clean(self):
        """Validate business limits"""
        if self.total_user_limit < 1:
            raise ValidationError('Total user limit must be at least 1')
        if self.branch_creation_limit < 1:
            raise ValidationError('Branch creation limit must be at least 1')
        
        # Check that current usage doesn't exceed new limits
        if self.pk:  # Only for existing records
            current_users = self.business.get_total_users_count()
            current_branches = self.business.get_business_branch_count()
            
            if self.total_user_limit < current_users:
                raise ValidationError(f'Total user limit ({self.total_user_limit}) cannot be less than current users ({current_users})')
            
            if self.branch_creation_limit < current_branches:
                raise ValidationError(f'Branch creation limit ({self.branch_creation_limit}) cannot be less than current branches ({current_branches})')

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)
