from django.db import models
from django.core.exceptions import ValidationError
from branches.models import Branch
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
import logging
from django.utils import timezone
from django.db import transaction
from django.apps import apps  # For lazy model loading

logger = logging.getLogger(__name__)

class BranchGroup(models.Model):
    """Model for managing groups within a branch"""
    GROUP_TYPE_CHOICES = [
        ('user', 'User Group'),
        ('course', 'Course Group'),
    ]
    
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    branch = models.ForeignKey(
        'branches.Branch',
        on_delete=models.SET_NULL,
        related_name='branch_groups',
        null=True,
        blank=True
    )
    created_by = models.ForeignKey(
        'users.CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_groups'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    group_type = models.CharField(
        max_length=10,
        choices=GROUP_TYPE_CHOICES,
        default='user',
        help_text='Type of group (user or course)'
    )

    class Meta:
        unique_together = ['name', 'branch']
        # Use primary key ordering to avoid potential column issues during deletion
        ordering = ['id']
        permissions = [
            ("manage_group", "Can manage group members and settings"),
        ]

    def clean(self):
        if self.created_by and self.branch:
            if self.created_by.branch != self.branch:
                raise ValidationError("Group creator must belong to the same branch.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        branch_name = self.branch.name if self.branch else "No Branch"
        return f"{self.name} ({branch_name})"

class GroupMemberRole(models.Model):
    """Model to define custom roles within a group"""
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    group = models.ForeignKey(
        BranchGroup, 
        on_delete=models.CASCADE,
        related_name='custom_roles',
        null=True,
        blank=True,
        help_text="If null, this is a global role that can be assigned to any group"
    )
    can_view = models.BooleanField(default=True)
    can_edit = models.BooleanField(default=False)
    can_manage_members = models.BooleanField(default=False)
    can_manage_content = models.BooleanField(default=False)
    can_create_topics = models.BooleanField(default=False, help_text="Can create new topics in courses")
    created_at = models.DateTimeField(auto_now_add=True)
    auto_enroll = models.BooleanField(default=False, help_text="Automatically enroll users with this role to associated course groups")

    class Meta:
        unique_together = ['name', 'group']
        # Use primary key ordering to avoid potential column issues during deletion
        ordering = ['id']

    def __str__(self):
        group_name = self.group.name if self.group else "Global"
        return f"{self.name} - {group_name}"

    def save(self, *args, **kwargs):
        # Automatically set edit permission for instructor roles
        if self.name and 'instructor' in self.name.lower():
            self.can_edit = True
            self.can_manage_content = True
            self.can_create_topics = True
        super().save(*args, **kwargs)

class GroupMembership(models.Model):
    """Model to manage user memberships in branch groups"""
    group = models.ForeignKey(
        BranchGroup, 
        on_delete=models.CASCADE,
        related_name='memberships'
    )
    user = models.ForeignKey(
        'users.CustomUser', 
        on_delete=models.CASCADE,
        related_name='group_memberships'
    )
    custom_role = models.ForeignKey(
        GroupMemberRole,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='members'
    )
    is_active = models.BooleanField(default=True)
    joined_at = models.DateTimeField(auto_now_add=True)
    invited_by = models.ForeignKey(
        'users.CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='group_invites_sent'
    )

    class Meta:
        unique_together = ['group', 'user']
        ordering = ['group', '-joined_at']


    def save(self, *args, **kwargs):
        is_new = self.pk is None
        self.full_clean()
        super().save(*args, **kwargs)

        # Handle automatic enrollment for learners
        if is_new and self.is_active and self.user.role == 'learner':
            from courses.models import CourseEnrollment
            # Get accessible courses for this group
            courses = self.group.accessible_courses.all()
            # Create enrollments for each accessible course
            for course in courses:
                from core.utils.enrollment import EnrollmentService
                EnrollmentService.create_or_get_enrollment(
                    user=self.user,
                    course=course,
                    source='auto_group'
                )

    def clean(self):
        if self.user.branch != self.group.branch:
            raise ValidationError("User must belong to the same branch as the group.")
        if self.custom_role and self.custom_role.group is not None and self.custom_role.group != self.group:
            raise ValidationError("Custom role must belong to the same group or be a global role.")
        if self.invited_by and self.invited_by.branch != self.group.branch:
            raise ValidationError("Inviter must belong to the same branch as the group.")

    def __str__(self):
        role_name = self.custom_role.name if self.custom_role else "Member"
        return f"{self.user.username} - {self.group.name} ({role_name})"

class CourseGroupAccess(models.Model):
    """Model to manage group access to courses"""
    course = models.ForeignKey(
        'courses.Course',
        on_delete=models.CASCADE,
        related_name='group_access'
    )
    group = models.ForeignKey(
        BranchGroup,
        on_delete=models.CASCADE,
        related_name='course_access'
    )
    can_modify = models.BooleanField(
        default=False,
        help_text="Whether group members with sufficient permissions can modify the course"
    )
    assigned_role = models.ForeignKey(
        GroupMemberRole,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='course_accesses',
        help_text="Role to assign to group members for this course access"
    )
    assigned_at = models.DateTimeField(auto_now_add=True)
    assigned_by = models.ForeignKey(
        'users.CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        related_name='course_group_assignments'
    )

    class Meta:
        unique_together = ['course', 'group']
        ordering = ['-assigned_at']

    def clean(self):
        # Only check branch relationships if branch is set
        if self.course.branch and self.group.branch and self.course.branch != self.group.branch:
            raise ValidationError("Course and group must belong to the same branch.")
        if self.assigned_by and self.group.branch and self.assigned_by.branch != self.group.branch:
            raise ValidationError("Assigner must belong to the same branch.")

    def has_edit_roles(self):
        """Check if the group has any roles with edit permission"""
        if not self.group:
            return False
        
        # Check for group-specific roles with edit permission
        group_has_edit = self.group.custom_roles.filter(can_edit=True).exists()
        
        # Check for global roles with edit permission
        global_has_edit = GroupMemberRole.objects.filter(group__isnull=True, can_edit=True).exists()
        
        return group_has_edit or global_has_edit

    def save(self, *args, **kwargs):
        # Automatically set can_modify based on group roles
        if self.group:
            # Check for instructor roles in the group
            instructor_roles = self.group.custom_roles.filter(
                name__icontains='instructor'
            ).exists()
            
            # Set can_modify to True for instructor roles
            if instructor_roles:
                self.can_modify = True
            else:
                self.can_modify = self.has_edit_roles()
                
        super().save(*args, **kwargs)
        
        # Get CourseEnrollment model using apps to avoid circular import
        CourseEnrollment = apps.get_model('courses', 'CourseEnrollment')
        
        # Trigger enrollment for existing group members
        if self.group:
            learner_memberships = self.group.memberships.filter(
                user__role='learner',
                is_active=True
            )
            for membership in learner_memberships:
                from core.utils.enrollment import EnrollmentService
                EnrollmentService.create_or_get_enrollment(
                    user=membership.user,
                    course=self.course,
                    source='auto_group_course'
                )

    def __str__(self):
        return f"{self.course.title} - {self.group.name}"

class CourseGroup(models.Model):
    """Model to associate groups with courses for the group management interface"""
    course = models.ForeignKey(
        'courses.Course',
        on_delete=models.CASCADE,
        related_name='course_groups'
    )
    group = models.ForeignKey(
        BranchGroup,
        on_delete=models.CASCADE,
        related_name='course_groups'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        'users.CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_course_groups'
    )

    class Meta:
        unique_together = ['course', 'group']
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.course.title} - {self.group.name}"

class GroupPermissionManager:
    def check_user_permissions(self, user, course=None):
        """Centralized permission checking"""
        # Get user's active group memberships
        memberships = GroupMembership.objects.filter(
            user=user,
            is_active=True
        ).select_related('custom_role', 'group')
        
        base_permissions = {
            'can_view': False,
            'can_edit': False,
            'can_manage_members': False,
            'can_manage_content': False
        }
        
        # Aggregate permissions from all roles
        for membership in memberships:
            role = membership.custom_role
            if role:
                base_permissions['can_view'] |= role.can_view
                base_permissions['can_edit'] |= role.can_edit
                base_permissions['can_manage_members'] |= role.can_manage_members
                base_permissions['can_manage_content'] |= role.can_manage_content
        
        return base_permissions

# Signal receiver - place AFTER all model classes
@receiver(post_save, sender=GroupMembership)
def handle_group_membership_changes(sender, instance, created, **kwargs):
    """Handle changes to group membership including automatic enrollment"""
    try:
        logger.info(f"============ GroupMembership Signal Triggered ============")
        logger.info(f"User: {instance.user.username} ({instance.user.role})")
        logger.info(f"Group: {instance.group.name}")
        logger.info(f"Is Active: {instance.is_active}")
        logger.info(f"Is New: {created}")

        # Invalidate dashboard cache for instructors when group membership changes
        if instance.user.role == 'instructor':
            from core.utils.dashboard_cache import DashboardCache
            logger.info(f"Invalidating dashboard cache for instructor {instance.user.username}")
            DashboardCache.clear_user_cache(instance.user.id)

        if instance.user.role == 'learner':
            from courses.models import CourseEnrollment
            
            # Get accessible courses
            courses = instance.group.accessible_courses.all()
            logger.info(f"Found {courses.count()} accessible courses for group")
            
            # List accessible courses for debugging
            for course in courses:
                logger.info(f"Course available: {course.title}")

            if instance.is_active:
                logger.info("Processing active membership - creating enrollments")
                for course in courses:
                    try:
                        from core.utils.enrollment import EnrollmentService
                        enrollment, created, message = EnrollmentService.create_or_get_enrollment(
                            user=instance.user,
                            course=course,
                            source='auto_group'
                        )
                        status = "created" if created else "already exists"
                        logger.info(f"Enrollment {status} for course: {course.title}")
                    except Exception as e:
                        logger.error(f"Error creating enrollment for course {course.title}: {str(e)}")
            else:
                logger.info("Processing inactive membership - checking for enrollment removal")
                for course in courses:
                    try:
                        # Check if user has access through other active group memberships
                        other_active_memberships = course.accessible_groups.filter(
                            memberships__user=instance.user,
                            memberships__is_active=True
                        ).exclude(id=instance.group.id).exists()
                        
                        logger.info(f"Other active memberships exist: {other_active_memberships}")
                        
                        if not other_active_memberships:
                            deleted_count = CourseEnrollment.objects.filter(
                                user=instance.user,
                                course=course
                            ).delete()
                            logger.info(f"Deleted {deleted_count} enrollments for course: {course.title}")
                    except Exception as e:
                        logger.error(f"Error removing enrollment for course {course.title}: {str(e)}")

        logger.info("============ Signal Processing Complete ============\n")

    except Exception as e:
        logger.error(f"Error in group membership signal handler: {str(e)}")
        logger.exception("Full traceback:")

@receiver(post_delete, sender=GroupMembership)
def handle_group_membership_delete(sender, instance, **kwargs):
    """Handle cache invalidation when group membership is deleted"""
    try:
        logger.info(f"GroupMembership deleted for user: {instance.user.username} ({instance.user.role})")
        
        # Invalidate dashboard cache for instructors when group membership is removed
        if instance.user.role == 'instructor':
            from core.utils.dashboard_cache import DashboardCache
            logger.info(f"Invalidating dashboard cache for instructor {instance.user.username}")
            DashboardCache.clear_user_cache(instance.user.id)
        
    except Exception as e:
        logger.error(f"Error in group membership delete signal handler: {str(e)}")
        logger.exception("Full traceback:")

@receiver([post_save, post_delete], sender='groups.GroupMemberRole')
def update_course_access_modify_permission(sender, instance, **kwargs):
    """Update can_modify for all course access entries when group roles change"""
    group = instance.group
    if group:  # Only update if the role is associated with a specific group
        has_edit_roles = group.custom_roles.filter(can_edit=True).exists()
        
        # Update all course access entries for this group
        CourseGroupAccess = apps.get_model('groups', 'CourseGroupAccess')
        CourseGroupAccess.objects.filter(group=group).update(can_modify=has_edit_roles)

@receiver([post_save, post_delete], sender=CourseGroupAccess)
def handle_course_group_access_changes(sender, instance, **kwargs):
    """Invalidate cache for instructors when course group access changes"""
    try:
        from core.utils.dashboard_cache import DashboardCache
        logger.info(f"CourseGroupAccess changed for course: {instance.course.title}, group: {instance.group.name}")
        
        # Invalidate cache for all instructors in the affected group
        instructor_memberships = instance.group.memberships.filter(
            user__role='instructor',
            is_active=True
        )
        
        for membership in instructor_memberships:
            logger.info(f"Invalidating dashboard cache for instructor {membership.user.username}")
            DashboardCache.clear_user_cache(membership.user.id)
            
        # Also invalidate cache for the direct instructor of the course if any
        if instance.course.instructor:
            logger.info(f"Invalidating dashboard cache for course instructor {instance.course.instructor.username}")
            DashboardCache.clear_user_cache(instance.course.instructor.id)
        
    except Exception as e:
        logger.error(f"Error in course group access signal handler: {str(e)}")
        logger.exception("Full traceback:")


class AzureADGroupImport(models.Model):
    """Model to track Azure AD group imports"""
    azure_group_id = models.CharField(max_length=255, help_text="Azure AD Group ID")
    azure_group_name = models.CharField(max_length=255, help_text="Azure AD Group Name")
    lms_group = models.ForeignKey(
        BranchGroup,
        on_delete=models.CASCADE,
        related_name='azure_imports',
        help_text="Linked LMS Group"
    )
    branch = models.ForeignKey(
        'branches.Branch',
        on_delete=models.CASCADE,
        related_name='azure_group_imports',
        help_text="Branch this import belongs to"
    )
    assigned_role = models.CharField(
        max_length=50,
        choices=[('learner', 'Learner'), ('instructor', 'Instructor')],
        default='learner',
        help_text="Role assigned to imported users"
    )
    imported_by = models.ForeignKey(
        'users.CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        related_name='azure_imports',
        help_text="Branch admin who imported this group"
    )
    imported_at = models.DateTimeField(auto_now_add=True)
    last_synced_at = models.DateTimeField(null=True, blank=True, help_text="Last time this group was synced")
    is_active = models.BooleanField(default=True, help_text="Whether this import is active for syncing")
    
    class Meta:
        unique_together = ['azure_group_id', 'branch']
        ordering = ['-imported_at']
    
    def __str__(self):
        return f"{self.azure_group_name} -> {self.lms_group.name} ({self.branch.name})"


class AzureADUserMapping(models.Model):
    """Model to track Azure AD users imported to LMS"""
    azure_user_id = models.CharField(max_length=255, help_text="Azure AD User ID")
    azure_email = models.EmailField(help_text="Azure AD User Email")
    lms_user = models.ForeignKey(
        'users.CustomUser',
        on_delete=models.CASCADE,
        related_name='azure_mappings',
        help_text="Linked LMS User"
    )
    azure_group_import = models.ForeignKey(
        AzureADGroupImport,
        on_delete=models.CASCADE,
        related_name='user_mappings',
        help_text="The Azure group import this user belongs to"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['azure_user_id', 'azure_group_import']
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.azure_email} -> {self.lms_user.username}"