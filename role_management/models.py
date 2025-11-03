from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.cache import cache
from django.utils import timezone
import logging
from django.db import transaction

logger = logging.getLogger(__name__)

class RoleManager(models.Manager):
    """Custom manager for Role model with caching and optimization"""
    
    def get_role_with_capabilities(self, role_id):
        """Get role with prefetched capabilities for performance"""
        cache_key = f"role_capabilities_{role_id}"
        result = cache.get(cache_key)
        
        if result is None:
            try:
                result = self.select_related().prefetch_related('capabilities').get(id=role_id)
                cache.set(cache_key, result, 3600)  # Cache for 1 hour
            except Role.DoesNotExist:
                return None
        
        return result
    
    def get_default_capabilities(self, role_name):
        """Get default capabilities for a role type"""
        default_capabilities = {
            'globaladmin': [
                # Global Admin has ALL capabilities plus special system controls
                'view_users', 'manage_users', 'create_users', 'delete_users',
                'view_courses', 'manage_courses', 'create_courses', 'delete_courses',
                'view_assignments', 'manage_assignments', 'grade_assignments', 'create_assignments', 'delete_assignments',
                'manage_roles', 'view_roles', 'create_roles', 'delete_roles',
                'view_groups', 'manage_groups', 'manage_group_members', 'create_groups', 'delete_groups',
                'view_branches', 'manage_branches', 'create_branches', 'delete_branches',
                'view_topics', 'manage_topics', 'create_topics', 'delete_topics',
                'view_quizzes', 'manage_quizzes', 'grade_quizzes', 'create_quizzes', 'delete_quizzes',
                'view_progress', 'manage_progress',
                'view_reports', 'manage_reports', 'export_reports', 'view_analytics',
                'manage_system_settings', 'view_system_logs',
                'manage_notifications', 'send_notifications',
                'create_messages', 'manage_messages', 'view_messages', 'delete_messages',
                'view_categories', 'manage_categories', 'create_categories', 'delete_categories',
                'view_certificates_templates', 'manage_certificates',
                'view_rubrics', 'manage_rubrics', 'create_rubrics', 'delete_rubrics',
                'view_discussions', 'manage_discussions', 'create_discussions', 'delete_discussions',
                'view_conferences', 'manage_conferences', 'create_conferences', 'delete_conferences',
                
                # Outcomes Management
                'view_outcomes', 'manage_outcomes', 'create_outcomes', 'delete_outcomes', 'align_outcomes',
                # Gradebook Management
                'view_gradebook', 'manage_gradebook', 'export_gradebook', 'import_gradebook',
                # Calendar Management
                'view_calendar', 'manage_calendar', 'create_calendar_events', 'delete_calendar_events',
                # Individual Learning Plans
                'view_ilp', 'manage_ilp', 'create_ilp', 'delete_ilp', 'assign_ilp',
                # Media Management
                'view_media', 'manage_media', 'upload_media', 'delete_media',
                # Course Reviews
                'view_course_reviews', 'manage_course_reviews', 'delete_course_reviews', 'moderate_reviews',
                # Survey Management
                'view_surveys', 'manage_surveys', 'view_survey_responses',
                # SharePoint Integration
                'view_sharepoint', 'manage_sharepoint_integration', 'sync_sharepoint',
                # Account Settings
                'view_account_settings', 'manage_account_settings', 'manage_global_admin_settings',
                # Business Management
                'view_business', 'manage_business', 'create_business', 'delete_business',
                # Global Admin exclusive capabilities
                'manage_global_settings', 'manage_oauth_configuration', 'manage_menu_control',
                'manage_ai_settings', 'system_wide_administration', 'global_menu_visibility',
                'configure_google_oauth', 'manage_all_integrations', 'global_feature_control'
            ],
            'superadmin': [
                'view_users', 'manage_users', 'create_users', 'delete_users',
                'view_courses', 'manage_courses', 'create_courses', 'delete_courses',
                'view_assignments', 'manage_assignments', 'grade_assignments', 'create_assignments', 'delete_assignments',
                # Role management capabilities removed - only Global Admin can manage roles
                'view_groups', 'manage_groups', 'manage_group_members', 'create_groups', 'delete_groups',
                'view_branches', 'manage_branches', 'create_branches', 'delete_branches',
                'view_topics', 'manage_topics', 'create_topics', 'delete_topics',
                'view_quizzes', 'manage_quizzes', 'grade_quizzes', 'create_quizzes', 'delete_quizzes',
                'view_progress', 'manage_progress',
                'view_reports', 'manage_reports', 'export_reports',
                'manage_system_settings', 'view_system_logs',
                'manage_notifications', 'send_notifications',
                'create_messages', 'manage_messages', 'view_messages',
                'view_categories', 'manage_categories', 'create_categories', 'delete_categories',
                'view_certificates_templates', 'manage_certificates',
                
                # Outcomes Management
                'view_outcomes', 'manage_outcomes', 'create_outcomes', 'delete_outcomes', 'align_outcomes',
                # Gradebook Management
                'view_gradebook', 'manage_gradebook', 'export_gradebook', 'import_gradebook',
                # Calendar Management
                'view_calendar', 'manage_calendar', 'create_calendar_events', 'delete_calendar_events',
                # Individual Learning Plans
                'view_ilp', 'manage_ilp', 'create_ilp', 'delete_ilp', 'assign_ilp',
                # Media Management
                'view_media', 'manage_media', 'upload_media', 'delete_media',
                # Course Reviews
                'view_course_reviews', 'manage_course_reviews', 'delete_course_reviews', 'moderate_reviews',
                # Survey Management
                'view_surveys', 'manage_surveys', 'view_survey_responses',
                # SharePoint Integration
                'view_sharepoint', 'manage_sharepoint_integration', 'sync_sharepoint',
                # Account Settings
                'view_account_settings', 'manage_account_settings',
                # Business Management
                'view_business', 'manage_business'
            ],
            'admin': [
                'view_users', 'manage_users', 'create_users', 'delete_users',
                'view_courses', 'manage_courses', 'create_courses', 'delete_courses',
                'view_assignments', 'manage_assignments', 'grade_assignments', 'create_assignments', 'delete_assignments',
                # Role management capabilities for admins
                'manage_roles', 'view_roles', 'create_roles', 'delete_roles',
                'view_groups', 'manage_groups', 'manage_group_members', 'create_groups', 'delete_groups',
                'view_branches', 'manage_branches', 'create_branches', 'delete_branches',
                'view_topics', 'manage_topics', 'create_topics', 'delete_topics',
                'view_quizzes', 'manage_quizzes', 'grade_quizzes', 'create_quizzes', 'delete_quizzes',
                'view_progress', 'manage_progress',
                'view_reports', 'manage_reports', 'export_reports',
                'manage_notifications', 'send_notifications',
                'create_messages', 'manage_messages', 'view_messages',
                'view_categories', 'manage_categories', 'create_categories', 'delete_categories',
                'view_certificates_templates', 'manage_certificates',
                
                # Outcomes Management
                'view_outcomes', 'manage_outcomes', 'create_outcomes', 'align_outcomes',
                # Gradebook Management
                'view_gradebook', 'manage_gradebook', 'export_gradebook', 'import_gradebook',
                # Calendar Management
                'view_calendar', 'manage_calendar', 'create_calendar_events', 'delete_calendar_events',
                # Individual Learning Plans
                'view_ilp', 'manage_ilp', 'create_ilp', 'assign_ilp',
                # Media Management
                'view_media', 'manage_media', 'upload_media',
                # Course Reviews
                'view_course_reviews', 'manage_course_reviews', 'moderate_reviews',
                # Survey Management
                'view_surveys', 'manage_surveys', 'view_survey_responses',
                # Account Settings
                'view_account_settings'
            ],
            'instructor': [
                'view_users',
                'view_courses', 'manage_courses', 'create_courses',
                'view_assignments', 'manage_assignments', 'grade_assignments', 'create_assignments',
                'view_groups',
                'view_branches',
                'view_topics', 'manage_topics', 'create_topics',
                'view_quizzes', 'manage_quizzes', 'grade_quizzes', 'create_quizzes',
                'view_progress', 'manage_progress',
                'create_messages', 'manage_messages', 'view_messages',
                'view_reports',
                'view_categories',
                'view_certificates_templates', 'manage_certificates',
                
                # Outcomes Management
                'view_outcomes', 'manage_outcomes', 'align_outcomes',
                # Gradebook Management
                'view_gradebook', 'manage_gradebook', 'export_gradebook',
                # Calendar Management
                'view_calendar', 'create_calendar_events',
                # Individual Learning Plans
                'view_ilp', 'manage_ilp', 'assign_ilp',
                # Media Management
                'view_media', 'upload_media',
                # Course Reviews
                'view_course_reviews',
                # Survey Management
                'view_surveys', 'manage_surveys',
                # Account Settings
                'view_account_settings'
            ],
            'learner': [
                'view_users',
                'view_courses',
                'view_assignments', 'submit_assignments',
                'view_groups',
                'view_branches',
                'view_topics',
                'view_quizzes', 'take_quizzes',
                'view_progress',
                'view_messages', 'create_messages',
                'view_certificates_templates',
                'view_reports',
                'view_categories',
                
                # Outcomes Management
                'view_outcomes',
                # Gradebook Management
                'view_gradebook',
                # Calendar Management
                'view_calendar',
                # Individual Learning Plans
                'view_ilp',
                # Media Management
                'view_media',
                # Course Reviews
                'view_course_reviews',
                # Account Settings
                'view_account_settings'
            ]
        }
        return default_capabilities.get(role_name, [])

class Role(models.Model):
    ROLE_CHOICES = [
        ('globaladmin', 'Global Admin'),
        ('superadmin', 'Super Admin'),
        ('admin', 'Admin'),
        ('instructor', 'Instructor'),
        ('learner', 'Learner'),
        ('custom', 'Custom'),
    ]

    ROLE_HIERARCHY = {
        'globaladmin': 5,
        'superadmin': 4,
        'admin': 3,
        'instructor': 2,
        'learner': 1,
        'custom': 0
    }

    name = models.CharField(max_length=50, choices=ROLE_CHOICES)
    custom_name = models.CharField(max_length=50, blank=True, null=True, help_text="Name for custom role")
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, help_text="Whether this role is active")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_roles',
        help_text="User who created this role"
    )

    objects = RoleManager()

    class Meta:
        # Use primary key ordering to avoid potential column issues during deletion
        ordering = ['id']
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['is_active']),
        ]
        constraints = [
            # Ensure custom_name is unique when not null
            models.UniqueConstraint(
                fields=['custom_name'],
                condition=models.Q(custom_name__isnull=False),
                name='unique_custom_name'
            ),
            # Ensure non-custom roles have unique names
            models.UniqueConstraint(
                fields=['name'],
                condition=models.Q(name__in=['globaladmin', 'superadmin', 'admin', 'instructor', 'learner']),
                name='unique_non_custom_roles'
            )
        ]

    def __str__(self):
        if self.name == 'custom' and self.custom_name:
            return self.custom_name
        return self.get_name_display()

    def clean(self):
        import re
        import html
        from django.utils.html import strip_tags
        
        # Sanitize inputs to prevent injection attacks
        if self.custom_name:
            # Remove HTML tags and decode HTML entities
            self.custom_name = strip_tags(html.unescape(self.custom_name))
            # Remove potentially dangerous characters
            self.custom_name = re.sub(r'[<>"\'\(\)\[\]{}\\;]+', '', self.custom_name)
            # Limit length to prevent buffer overflow
            self.custom_name = self.custom_name[:50]
            # Strip whitespace
            self.custom_name = self.custom_name.strip()
        
        if self.description:
            # Sanitize description field
            self.description = strip_tags(html.unescape(self.description))
            self.description = self.description[:500]  # Limit length
            self.description = self.description.strip()
        
        # Basic validation
        if self.name == 'custom' and not self.custom_name:
            raise ValidationError({'custom_name': 'Custom name is required for custom roles'})
        if self.name != 'custom' and self.custom_name:
            raise ValidationError({'custom_name': 'Custom name should only be set for custom roles'})
        
        # Enhanced custom name validation
        if self.custom_name:
            # Strict pattern validation - only alphanumeric, spaces, hyphens, underscores
            if not re.match(r'^[a-zA-Z0-9\s\-_]+$', self.custom_name):
                raise ValidationError({
                    'custom_name': 'Custom name can only contain letters, numbers, spaces, hyphens, and underscores'
                })
            
            # Length validation
            if len(self.custom_name) < 3:
                raise ValidationError({'custom_name': 'Custom name must be at least 3 characters long'})
            if len(self.custom_name) > 50:
                raise ValidationError({'custom_name': 'Custom name cannot exceed 50 characters'})
            
            # Prevent reserved words and dangerous patterns
            forbidden_patterns = [
                # System role names (case insensitive)
                r'(?i)\b(global|admin|super|system|root|administrator)\b',
                # SQL injection patterns
                r'(?i)\b(select|insert|update|delete|drop|union|exec|script)\b',
                # XSS patterns
                r'(?i)\b(script|javascript|vbscript|onload|onerror)\b',
                # Command injection
                r'(?i)\b(cmd|bash|sh|powershell|eval)\b',
                # Path traversal
                r'\.\./|\.\.\\',
            ]
            
            for pattern in forbidden_patterns:
                if re.search(pattern, self.custom_name):
                    raise ValidationError({
                        'custom_name': 'Custom name contains forbidden words or patterns'
                    })
            
            # Check against existing role names with enhanced matching
            existing_role_names = [choice[0] for choice in self.ROLE_CHOICES if choice[0] != 'custom']
            # Normalize comparison (remove spaces, convert to lowercase)
            normalized_custom = re.sub(r'\s+', '', self.custom_name.lower())
            
            for existing_name in existing_role_names:
                normalized_existing = re.sub(r'\s+', '', existing_name.lower())
                if normalized_custom == normalized_existing:
                    raise ValidationError({
                        'custom_name': f'Custom name cannot be similar to existing role "{existing_name}"'
                    })
            
            # Check for variations of system roles
            dangerous_variations = [
                'globaladmin', 'global_admin', 'global-admin', 'globadmin',
                'superadmin', 'super_admin', 'super-admin', 'supadmin',
                'administrator', 'admin_user', 'admin-user', 'sysadmin',
                'system_admin', 'system-admin', 'systemadmin'
            ]
            
            for variation in dangerous_variations:
                if normalized_custom == variation or variation in normalized_custom:
                    raise ValidationError({
                        'custom_name': 'Custom name cannot resemble system administrator roles'
                    })
        
        super().clean()

    def save(self, *args, **kwargs):
        self.clean()
        # Clear cache when role is saved
        if self.pk:
            cache.delete(f"role_capabilities_{self.pk}")
            cache.delete(f"user_capabilities_{self.pk}")
        super().save(*args, **kwargs)
        
        # Log role creation/update
        action = "updated" if self.pk else "created"
        logger.info(f"Role {self} was {action} by user {getattr(self, 'created_by', 'system')}")

    def delete(self, *args, **kwargs):
        # Clear cache before deletion
        cache.delete(f"role_capabilities_{self.pk}")
        cache.delete(f"user_capabilities_{self.pk}")
        
        # Log role deletion
        logger.info(f"Role {self} was deleted")
        super().delete(*args, **kwargs)

    @property
    def hierarchy_level(self):
        """Get the hierarchy level of this role"""
        return self.ROLE_HIERARCHY.get(self.name, 0)

    def is_higher_than(self, other_role):
        """Check if this role has higher hierarchy than another role"""
        if isinstance(other_role, str):
            other_level = self.ROLE_HIERARCHY.get(other_role, 0)
        else:
            other_level = other_role.hierarchy_level
        return self.hierarchy_level > other_level

    def get_capabilities(self):
        """Get all capabilities for this role with caching"""
        cache_key = f"role_capabilities_{self.pk}"
        capabilities = cache.get(cache_key)
        
        if capabilities is None:
            capabilities = list(self.capabilities.values_list('capability', flat=True))
            cache.set(cache_key, capabilities, 3600)  # Cache for 1 hour
        
        return capabilities

    def has_capability(self, capability):
        """Check if this role has a specific capability"""
        return capability in self.get_capabilities()

    def add_capability(self, capability, description=""):
        """Add a capability to this role"""
        role_capability, created = RoleCapability.objects.get_or_create(
            role=self,
            capability=capability,
            defaults={'description': description}
        )
        
        if created:
            # Clear cache
            cache.delete(f"role_capabilities_{self.pk}")
            logger.info(f"Capability '{capability}' added to role {self}")
        
        return role_capability

    def remove_capability(self, capability):
        """Remove a capability from this role"""
        try:
            role_capability = RoleCapability.objects.get(role=self, capability=capability)
            role_capability.delete()
            
            # Clear cache
            cache.delete(f"role_capabilities_{self.pk}")
            logger.info(f"Capability '{capability}' removed from role {self}")
            return True
        except RoleCapability.DoesNotExist:
            return False

    def get_users_count(self):
        """Get count of users assigned to this role"""
        return self.user_roles.count()

    def can_be_deleted(self, requesting_user=None):
        """Check if this role can be safely deleted"""
        # Only Global Admin can delete system roles
        if self.name in ['globaladmin', 'superadmin', 'admin', 'instructor', 'learner']:
            if not (requesting_user and requesting_user.role == 'globaladmin'):
                return False, "System roles cannot be deleted"
        
        # Check if any users are assigned to this role
        if self.get_users_count() > 0:
            return False, f"Role has {self.get_users_count()} users assigned"
        
        return True, "Role can be deleted"

class RoleCapability(models.Model):
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name='capabilities')
    capability = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, help_text="Whether this capability is active")
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_capabilities',
        help_text="User who created this capability"
    )

    class Meta:
        ordering = ['capability']
        unique_together = ['role', 'capability']
        indexes = [
            models.Index(fields=['role', 'capability']),
            models.Index(fields=['capability']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return f"{self.role.get_name_display()} - {self.capability}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Clear role capabilities cache
        cache.delete(f"role_capabilities_{self.role.pk}")
        
        # Log capability assignment
        logger.info(f"Capability '{self.capability}' assigned to role {self.role}")

    def delete(self, *args, **kwargs):
        role_pk = self.role.pk
        capability = self.capability
        super().delete(*args, **kwargs)
        
        # Clear cache
        cache.delete(f"role_capabilities_{role_pk}")
        
        # Log capability removal
        logger.info(f"Capability '{capability}' removed from role {self.role}")

class UserRole(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='user_roles')
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name='user_roles')
    assigned_at = models.DateTimeField(auto_now_add=True)
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_user_roles',
        help_text="User who assigned this role"
    )
    is_active = models.BooleanField(default=True, help_text="Whether this role assignment is active")
    expires_at = models.DateTimeField(null=True, blank=True, help_text="When this role assignment expires")

    class Meta:
        unique_together = ['user', 'role']
        indexes = [
            models.Index(fields=['user', 'role']),
            models.Index(fields=['user']),
            models.Index(fields=['role']),
            models.Index(fields=['is_active']),
            models.Index(fields=['expires_at']),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.role.get_name_display()}"

    def clean(self):
        """Enhanced validation with comprehensive Session checks"""
        from django.core.exceptions import ValidationError
        from django.utils import timezone
        
        super().clean()
        
        errors = {}
        
        # 1. Validate role assignment hierarchy
        if self.role and self.assigned_by:
            assigned_by_highest_role = None
            
            # Get the highest role of the assigner
            if hasattr(self.assigned_by, 'role') and self.assigned_by.role:
                try:
                    from .models import Role
                    assigned_by_highest_role = Role.objects.get(name=self.assigned_by.role)
                except Role.DoesNotExist:
                    pass
            
            # Check assigned roles for higher hierarchy
            assigned_user_roles = UserRole.objects.filter(
                user=self.assigned_by, 
                is_active=True,
                role__is_active=True
            ).select_related('role')
            
            for user_role in assigned_user_roles:
                if not user_role.is_expired and (
                    not assigned_by_highest_role or 
                    user_role.role.hierarchy_level > assigned_by_highest_role.hierarchy_level
                ):
                    assigned_by_highest_role = user_role.role
            
            # Validate hierarchy: assigner must have higher role than the role being assigned
            if assigned_by_highest_role:
                if assigned_by_highest_role.hierarchy_level <= self.role.hierarchy_level:
                    errors['role'] = f"You cannot assign a role ({self.role.name}) that is equal to or higher than your highest role ({assigned_by_highest_role.name})"
            else:
                # If no role found for assigner, they shouldn't be able to assign anything except learner
                if self.role.name != 'learner':
                    errors['role'] = "You do not have sufficient privileges to assign this role"
        
        # 2. Superadmin role special validation
        if self.role.name == 'superadmin':
            if not (self.assigned_by and hasattr(self.assigned_by, 'role') and self.assigned_by.role == 'superadmin'):
                # Also check if assigner has active superadmin role assignment
                has_superadmin_role = UserRole.objects.filter(
                    user=self.assigned_by,
                    role__name='superadmin',
                    is_active=True
                ).exists()
                
                if not has_superadmin_role:
                    errors['role'] = "Only users with superadmin role can assign superadmin roles"
        
        # 3. Branch-based role assignment validation
        if hasattr(self.user, 'branch') and hasattr(self.assigned_by, 'branch'):
            # Non-superadmins can only assign roles within their branch
            if (self.assigned_by and 
                hasattr(self.assigned_by, 'role') and 
                self.assigned_by.role != 'superadmin' and
                self.user.branch_id != self.assigned_by.branch_id):
                
                # Check if assigner has superadmin role assignment
                has_superadmin_role = UserRole.objects.filter(
                    user=self.assigned_by,
                    role__name='superadmin',
                    is_active=True
                ).exists()
                
                if not has_superadmin_role:
                    errors['user'] = "You can only assign roles to users within your branch"
        
        # 4. Prevent conflicting role assignments
        if self.role and self.user:
            # Check for existing active assignments of the same role
            existing_assignment = UserRole.objects.filter(
                user=self.user,
                role=self.role,
                is_active=True
            ).exclude(pk=self.pk).first()
            
            if existing_assignment:
                errors['role'] = f"User already has an active assignment for role '{self.role.name}'"
            
            # Check for conflicting role combinations
            conflicting_roles = {
                'superadmin': ['admin', 'instructor', 'learner'],
                'admin': ['superadmin', 'learner'], 
                'instructor': ['superadmin'],
                'learner': ['superadmin', 'admin']
            }
            
            if self.role.name in conflicting_roles:
                existing_conflicting = UserRole.objects.filter(
                    user=self.user,
                    role__name__in=conflicting_roles[self.role.name],
                    is_active=True
                ).exclude(pk=self.pk)
                
                if existing_conflicting.exists():
                    conflicting_role_names = [ur.role.name for ur in existing_conflicting]
                    errors['role'] = f"Cannot assign '{self.role.name}' role. User has conflicting roles: {', '.join(conflicting_role_names)}"
        
        # 5. Expiration date validation
        if self.expires_at:
            if self.expires_at <= timezone.now():
                errors['expires_at'] = "Expiration date must be in the future"
            
            # Prevent excessively long role assignments for Session
            max_duration = timezone.timedelta(days=365 * 2)  # 2 years max
            if self.expires_at > timezone.now() + max_duration:
                errors['expires_at'] = "Role assignment cannot exceed 2 years"
        
        # 6. Validate role is active and assignable
        if self.role and not self.role.is_active:
            errors['role'] = "Cannot assign an inactive role"
        
        # 7. Validate user is active
        if self.user and not self.user.is_active:
            errors['user'] = "Cannot assign roles to inactive users"
        
        # 8. Prevent self-assignment for privilege escalation
        if self.user and self.assigned_by and self.user.pk == self.assigned_by.pk:
            # Allow only if current user already has superadmin role
            if not (hasattr(self.assigned_by, 'role') and self.assigned_by.role == 'superadmin'):
                has_superadmin_role = UserRole.objects.filter(
                    user=self.assigned_by,
                    role__name='superadmin',
                    is_active=True
                ).exists()
                
                if not has_superadmin_role:
                    errors['user'] = "You cannot assign roles to yourself unless you are a superadmin"
        
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        """Simplified save method to prevent deadlocks"""
        from django.db import transaction, IntegrityError
        from django.utils import timezone
        
        # Full validation before saving
        self.clean()
        
        # Deactivate expired roles before saving
        if self.is_expired:
            self.is_active = False
        
        try:
            with transaction.atomic():
                # Simple save without complex locking
                super().save(*args, **kwargs)
        except IntegrityError as e:
            logger.warning(f"Integrity error in UserRole save: {e}")
            # Handle gracefully without retry loops
            raise ValidationError(f"Role assignment conflict: {str(e)}")
    
    def _invalidate_Session_caches(self):
        """Securely invalidate all related caches"""
        try:
            cache_keys = [
                f"user_capabilities_{self.user.pk}",
                f"user_capabilities_version_{self.user.pk}",
                f"user_session_capabilities_{self.user.pk}",
                f"role_capabilities_{self.role.pk}"
            ]
            
            # Use safe cache operations
            from .utils import safe_cache_operation
            success, _ = safe_cache_operation(cache.delete_many, cache_keys)
            
            if not success:
                # Fallback to individual deletions
                for key in cache_keys:
                    safe_cache_operation(cache.delete, key)
                    
        except Exception as e:
            logger.error(f"Error invalidating Session caches for user {self.user.pk}: {str(e)}")

    def delete(self, *args, **kwargs):
        user_pk = self.user.pk
        super().delete(*args, **kwargs)
        
        # Clear cache
        cache.delete(f"user_capabilities_{user_pk}")
        
        # Log role removal
        logger.info(f"Role {self.role} removed from user {self.user.username}")

    @property
    def is_expired(self):
        """Check if this role assignment has expired"""
        if self.expires_at:
            return timezone.now() > self.expires_at
        return False

    def extend_expiration(self, days=30, extended_by=None):
        """Extend the expiration date by specified days with Session validation"""
        from django.core.exceptions import ValidationError
        from django.utils import timezone
        
        # Session check: only allow extension if requester has appropriate permissions
        if extended_by:
            from .utils import PermissionManager
            if not PermissionManager.can_user_assign_role(extended_by, self.role, self.user):
                raise ValidationError("You do not have permission to extend this role assignment")
        
        # Limit maximum extension to prevent abuse
        max_extension_days = 365  # 1 year maximum extension
        if days > max_extension_days:
            raise ValidationError(f"Cannot extend role assignment by more than {max_extension_days} days")
        
        # Calculate new expiration date
        if self.expires_at:
            new_expiration = self.expires_at + timezone.timedelta(days=days)
        else:
            new_expiration = timezone.now() + timezone.timedelta(days=days)
        
        # Prevent extension beyond maximum allowed duration
        max_total_duration = timezone.timedelta(days=365 * 2)  # 2 years total
        if new_expiration > timezone.now() + max_total_duration:
            raise ValidationError("Role assignment cannot exceed 2 years total duration")
        
        self.expires_at = new_expiration
        self.save()
        
        # Log the extension
        logger.info(f"Role assignment {self.pk} extended by {days} days by {extended_by.username if extended_by else 'system'}")
        
        # Create audit log
        if extended_by:
            try:
                RoleAuditLog.log_action(
                    user=extended_by,
                    action='update',
                    role=self.role,
                    target_user=self.user,
                    description=f"Extended role assignment expiration by {days} days",
                    metadata={
                        'days_extended': days,
                        'new_expiration': new_expiration.isoformat(),
                        'assignment_id': self.pk
                    }
                )
            except Exception as e:
                logger.error(f"Failed to create audit log for role extension: {str(e)}")

    @classmethod
    def deactivate_expired_roles(cls):
        """Class method to deactivate all expired role assignments"""
        from django.utils import timezone
        
        expired_roles = cls.objects.filter(
            expires_at__lte=timezone.now(),
            is_active=True
        )
        
        expired_count = expired_roles.count()
        if expired_count > 0:
            # Get details before updating for logging
            expired_details = list(expired_roles.values(
                'id', 'user__username', 'role__name', 'expires_at'
            ))
            
            # Deactivate expired roles
            expired_roles.update(is_active=False)
            
            # Clear cache for affected users
            user_ids = expired_roles.values_list('user_id', flat=True).distinct()
            for user_id in user_ids:
                cache.delete(f"user_capabilities_{user_id}")
            
            # Log the deactivation
            logger.info(f"Automatically deactivated {expired_count} expired role assignments")
            
            # Create audit logs for each deactivated role
            for role_info in expired_details:
                try:
                    RoleAuditLog.objects.create(
                        user=None,  # System action
                        role_id=None,  # We don't have the role object here
                        target_user_id=None,  # We don't have the user object here
                        action='update',
                        description=f"Automatically deactivated expired role assignment (ID: {role_info['id']})",
                        metadata={
                            'assignment_id': role_info['id'],
                            'username': role_info['user__username'],
                            'role_name': role_info['role__name'],
                            'expired_at': role_info['expires_at'].isoformat() if role_info['expires_at'] else None,
                            'auto_deactivated': True
                        }
                    )
                except Exception as e:
                    logger.error(f"Failed to create audit log for expired role {role_info['id']}: {str(e)}")
        
        return expired_count

    @classmethod
    def get_Session_violations(cls):
        """Identify potential Session violations in role assignments"""
        violations = []
        
        # Check for users with conflicting active roles
        from django.db.models import Count
        
        users_with_conflicts = cls.objects.filter(
            is_active=True
        ).values('user').annotate(
            role_count=Count('role'),
            superadmin_count=Count('role', filter=models.Q(role__name='superadmin')),
            admin_count=Count('role', filter=models.Q(role__name='admin')),
            instructor_count=Count('role', filter=models.Q(role__name='instructor')),
            learner_count=Count('role', filter=models.Q(role__name='learner'))
        ).filter(
            models.Q(superadmin_count__gt=0, admin_count__gt=0) |
            models.Q(superadmin_count__gt=0, learner_count__gt=0) |
            models.Q(admin_count__gt=0, learner_count__gt=0)
        )
        
        for user_data in users_with_conflicts:
            violations.append({
                'type': 'conflicting_roles',
                'user_id': user_data['user'],
                'details': f"User has conflicting active roles"
            })
        
        # Check for role assignments without proper hierarchy
        # This would require more complex logic and might be expensive
        
        return violations

class RoleAuditLog(models.Model):
    """Audit log for role-related changes"""
    ACTION_CHOICES = [
        ('create', 'Created'),
        ('update', 'Updated'),
        ('delete', 'Deleted'),
        ('assign', 'Assigned'),
        ('unassign', 'Unassigned'),
        ('capability_add', 'Capability Added'),
        ('capability_remove', 'Capability Removed'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='role_audit_logs'
    )
    role = models.ForeignKey(
        Role,
        on_delete=models.SET_NULL,
        null=True,
        related_name='audit_logs'
    )
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='role_audit_target_logs'
    )
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    description = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['timestamp']),
            models.Index(fields=['user']),
            models.Index(fields=['role']),
            models.Index(fields=['action']),
        ]

    def __str__(self):
        return f"{self.user} {self.get_action_display()} {self.role} at {self.timestamp}"

    @classmethod
    def log_action(cls, user, action, role=None, target_user=None, description="", metadata=None, ip_address=None):
        """Log a role-related action with enhanced Session"""
        # Encrypt sensitive metadata before storing
        if metadata:
            metadata = cls._secure_metadata(metadata)
        
        audit_log = cls.objects.create(
            user=user,
            role=role,
            target_user=target_user,
            action=action,
            description=description,
            metadata=metadata or {},
            ip_address=ip_address
        )
        
        # Generate integrity hash after creation
        audit_log._generate_integrity_hash()
        audit_log.save(update_fields=['metadata'])
        
        return audit_log
    
    @classmethod
    def _secure_metadata(cls, metadata):
        """Encrypt sensitive data in metadata"""
        import json
        from cryptography.fernet import Fernet
        from django.conf import settings
        
        if not metadata:
            return metadata
        
        # Get or generate encryption key
        encryption_key = getattr(settings, 'AUDIT_LOG_ENCRYPTION_KEY', None)
        if not encryption_key:
            # For demonstration - in production, this should be properly configured
            encryption_key = Fernet.generate_key()
        
        try:
            fernet = Fernet(encryption_key)
            
            # Fields that should be encrypted
            sensitive_fields = [
                'ip_address', 'session_key', 'user_agent', 'query_params',
                'attempted_capabilities', 'Session_level', 'operation_hash'
            ]
            
            secured_metadata = metadata.copy()
            
            for field in sensitive_fields:
                if field in secured_metadata and secured_metadata[field]:
                    # Encrypt the sensitive field
                    field_data = json.dumps(secured_metadata[field]).encode()
                    encrypted_data = fernet.encrypt(field_data)
                    secured_metadata[field] = {
                        'encrypted': True,
                        'data': encrypted_data.decode()
                    }
            
            # Add integrity information
            secured_metadata['_Session'] = {
                'encrypted_fields': sensitive_fields,
                'encryption_timestamp': timezone.now().isoformat(),
                'version': '1.0'
            }
            
            return secured_metadata
            
        except Exception as e:
            logger.error(f"Failed to encrypt audit log metadata: {str(e)}")
            # Return original metadata if encryption fails
            return metadata
    
    def _generate_integrity_hash(self):
        """Generate integrity hash for audit log"""
        import hashlib
        import json
        
        try:
            # Create hash of all important fields
            hash_content = {
                'user_id': self.user.pk if self.user else None,
                'role_id': self.role.pk if self.role else None,
                'target_user_id': self.target_user.pk if self.target_user else None,
                'action': self.action,
                'description': self.description,
                'timestamp': self.timestamp.isoformat(),
                'ip_address': self.ip_address,
                'metadata_keys': list(self.metadata.keys()) if self.metadata else []
            }
            
            # Add salt for Session
            hash_content['_salt'] = 'lms_audit_integrity_2024'
            
            content_str = json.dumps(hash_content, sort_keys=True)
            integrity_hash = hashlib.sha256(content_str.encode()).hexdigest()
            
            # Store hash in metadata
            if not self.metadata:
                self.metadata = {}
            self.metadata['_integrity'] = {
                'hash': integrity_hash,
                'generated_at': timezone.now().isoformat(),
                'algorithm': 'sha256'
            }
            
        except Exception as e:
            logger.error(f"Failed to generate integrity hash for audit log {self.pk}: {str(e)}")
    
    def verify_integrity(self):
        """Verify the integrity of this audit log entry"""
        if not self.metadata or '_integrity' not in self.metadata:
            return False, "No integrity hash found"
        
        try:
            stored_hash = self.metadata['_integrity']['hash']
            
            # Temporarily remove integrity data and regenerate hash
            original_metadata = self.metadata.copy()
            temp_metadata = self.metadata.copy()
            if '_integrity' in temp_metadata:
                del temp_metadata['_integrity']
            
            self.metadata = temp_metadata
            self._generate_integrity_hash()
            calculated_hash = self.metadata['_integrity']['hash']
            
            # Restore original metadata
            self.metadata = original_metadata
            
            if stored_hash == calculated_hash:
                return True, "Integrity verified"
            else:
                return False, "Integrity hash mismatch - possible tampering"
                
        except Exception as e:
            return False, f"Integrity verification failed: {str(e)}"
    
    def get_decrypted_metadata(self):
        """Decrypt and return metadata for authorized access"""
        if not self.metadata:
            return {}
        
        try:
            from cryptography.fernet import Fernet
            from django.conf import settings
            import json
            
            encryption_key = getattr(settings, 'AUDIT_LOG_ENCRYPTION_KEY', None)
            if not encryption_key:
                return self.metadata
            
            fernet = Fernet(encryption_key)
            decrypted_metadata = self.metadata.copy()
            
            for field, value in self.metadata.items():
                if isinstance(value, dict) and value.get('encrypted'):
                    try:
                        encrypted_data = value['data'].encode()
                        decrypted_data = fernet.decrypt(encrypted_data)
                        decrypted_metadata[field] = json.loads(decrypted_data.decode())
                    except Exception as e:
                        logger.error(f"Failed to decrypt field {field}: {str(e)}")
                        decrypted_metadata[field] = "[DECRYPTION_FAILED]"
            
            return decrypted_metadata
            
        except Exception as e:
            logger.error(f"Failed to decrypt audit log metadata: {str(e)}")
            return self.metadata
    
    @classmethod
    def verify_all_integrity(cls, limit=1000):
        """Verify integrity of recent audit logs"""
        recent_logs = cls.objects.order_by('-timestamp')[:limit]
        results = {
            'total_checked': 0,
            'verified': 0,
            'failed': 0,
            'no_hash': 0,
            'failures': []
        }
        
        for log in recent_logs:
            results['total_checked'] += 1
            
            if not log.metadata or '_integrity' not in log.metadata:
                results['no_hash'] += 1
                continue
            
            verified, message = log.verify_integrity()
            if verified:
                results['verified'] += 1
            else:
                results['failed'] += 1
                results['failures'].append({
                    'id': log.pk,
                    'timestamp': log.timestamp.isoformat(),
                    'message': message
                })
        
        return results
