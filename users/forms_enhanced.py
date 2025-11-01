"""
Enhanced User Forms with Group Selection and Automatic Enrollment
This module provides enhanced user creation and editing forms with group selection functionality.
"""

from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from .models import CustomUser
from branches.models import Branch
from courses.models import Course
from .forms import TabbedUserCreationForm, CustomUserChangeForm
import pytz
from typing import Any, Dict, List, Optional, Union, TYPE_CHECKING

if TYPE_CHECKING:
    from django.http import HttpRequest


class EnhancedUserCreationForm(TabbedUserCreationForm):
    """Enhanced user creation form with group selection and automatic enrollment"""
    
    class Meta(TabbedUserCreationForm.Meta):
        # Inherit all fields from TabbedUserCreationForm including group fields
        pass


    def __init__(self, *args: Any, **kwargs: Any) -> None:
        # Store request before parent init to prevent it from being consumed
        request = kwargs.get('request', None)
        self.request: Optional['HttpRequest'] = request
        super().__init__(*args, **kwargs)
        
        # Override group querysets after parent initialization
        try:
            self._setup_group_querysets()
        except Exception as e:
            # Log error but don't crash
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error in _setup_group_querysets: {e}")
        
        # Set up field help texts
        if 'branch' in self.fields:
            self.fields['branch'].help_text = "Select the branch for this user"
        if 'email' in self.fields:
            self.fields['email'].required = True
        if 'first_name' in self.fields:
            self.fields['first_name'].required = False
        if 'last_name' in self.fields:
            self.fields['last_name'].required = False
        if 'role' in self.fields:
            self.fields['role'].initial = 'learner'
        if 'timezone' in self.fields:
            self.fields['timezone'].help_text = "Select the user's preferred timezone"
        
        # Import here to avoid circular imports
        from groups.models import BranchGroup
        
        # Set up group querysets based on user permissions
        if 'user_groups' in self.fields and 'course_groups' in self.fields:
            if self.request and hasattr(self.request, 'user'):
                user = self.request.user
                print(f"Form init - User: {user.username}, Role: {user.role}")
                
                # For superusers, globaladmins, and superadmins, show all groups
                if user.is_superuser or user.role in ['globaladmin', 'superadmin']:
                    print("Using superuser/admin group query")
                    self.fields['user_groups'].queryset = BranchGroup.objects.filter(
                        group_type='user',
                        is_active=True
                    ).order_by('name')
                    self.fields['course_groups'].queryset = BranchGroup.objects.filter(
                        group_type='course',
                        is_active=True
                    ).order_by('name')
                # For admin users, show groups from their branch and accessible branches
                elif user.role == 'admin':
                    print("Using admin group query")
                    # Show groups from user's branch and any other accessible branches
                    self.fields['user_groups'].queryset = BranchGroup.objects.filter(
                        group_type='user',
                        is_active=True
                    ).order_by('name')
                    self.fields['course_groups'].queryset = BranchGroup.objects.filter(
                        group_type='course',
                        is_active=True
                    ).order_by('name')
                # For other users, show only groups from their branch
                elif hasattr(user, 'branch') and user.branch:
                    user_branch = user.branch
                    self.fields['user_groups'].queryset = BranchGroup.objects.filter(
                        branch=user_branch, 
                        group_type='user',
                        is_active=True
                    ).order_by('name')
                    self.fields['course_groups'].queryset = BranchGroup.objects.filter(
                        branch=user_branch, 
                        group_type='course',
                        is_active=True
                    ).order_by('name')
                else:
                    # No branch or permission, show no groups
                    self.fields['user_groups'].queryset = BranchGroup.objects.none()
                    self.fields['course_groups'].queryset = BranchGroup.objects.none()
                
                if 'courses' in self.fields:
                    if user.is_superuser or user.role in ['globaladmin', 'superadmin', 'admin']:
                        self.fields['courses'].queryset = Course.objects.all()
                    elif hasattr(user, 'branch') and user.branch:
                        self.fields['courses'].queryset = Course.objects.filter(branch=user.branch)
                    else:
                        self.fields['courses'].queryset = Course.objects.none()
            else:
                # No request or user, show no groups
                if 'user_groups' in self.fields:
                    self.fields['user_groups'].queryset = BranchGroup.objects.none()
                if 'course_groups' in self.fields:
                    self.fields['course_groups'].queryset = BranchGroup.objects.none()
                if 'courses' in self.fields:
                    self.fields['courses'].queryset = Course.objects.none()
        else:
            # Group fields not found in form - this is expected for some form types
            pass
    
    def _setup_group_querysets(self):
        """Setup group querysets based on user permissions"""
        # Import here to avoid circular imports
        from groups.models import BranchGroup
        from courses.models import Course
        
        if 'user_groups' in self.fields and 'course_groups' in self.fields:
            if self.request and hasattr(self.request, 'user'):
                user = self.request.user
                
                # For superusers, globaladmins, and superadmins, show all groups
                if user.is_superuser or user.role in ['globaladmin', 'superadmin']:
                    self.fields['user_groups'].queryset = BranchGroup.objects.filter(
                        group_type='user',
                        is_active=True
                    ).order_by('name')
                    self.fields['course_groups'].queryset = BranchGroup.objects.filter(
                        group_type='course',
                        is_active=True
                    ).order_by('name')
                # For admin users, show groups from their branch and accessible branches
                elif user.role == 'admin':
                    # Show groups from user's branch and any other accessible branches
                    self.fields['user_groups'].queryset = BranchGroup.objects.filter(
                        group_type='user',
                        is_active=True
                    ).order_by('name')
                    self.fields['course_groups'].queryset = BranchGroup.objects.filter(
                        group_type='course',
                        is_active=True
                    ).order_by('name')
                # For other users, show only groups from their branch
                elif hasattr(user, 'branch') and user.branch:
                    user_branch = user.branch
                    self.fields['user_groups'].queryset = BranchGroup.objects.filter(
                        branch=user_branch, 
                        group_type='user',
                        is_active=True
                    ).order_by('name')
                    self.fields['course_groups'].queryset = BranchGroup.objects.filter(
                        branch=user_branch, 
                        group_type='course',
                        is_active=True
                    ).order_by('name')
                else:
                    # No branch or permission, show no groups
                    self.fields['user_groups'].queryset = BranchGroup.objects.none()
                    self.fields['course_groups'].queryset = BranchGroup.objects.none()
                
                if 'courses' in self.fields:
                    if user.is_superuser or user.role in ['globaladmin', 'superadmin', 'admin']:
                        self.fields['courses'].queryset = Course.objects.all()
                    elif hasattr(user, 'branch') and user.branch:
                        self.fields['courses'].queryset = Course.objects.filter(branch=user.branch)
                    else:
                        self.fields['courses'].queryset = Course.objects.none()
        
        # Handle branch selection from form data
        if self.data.get('branch'):
            try:
                branch_id = int(self.data.get('branch'))
                branch = Branch.objects.get(id=branch_id)
                self.fields['user_groups'].queryset = BranchGroup.objects.filter(
                    branch=branch, 
                    group_type='user',
                    is_active=True
                ).order_by('name')
                self.fields['course_groups'].queryset = BranchGroup.objects.filter(
                    branch=branch, 
                    group_type='course',
                    is_active=True
                ).order_by('name')
                if 'courses' in self.fields:
                    self.fields['courses'].queryset = Course.objects.filter(branch=branch)
            except (ValueError, TypeError, Branch.DoesNotExist):
                if 'user_groups' in self.fields:
                    self.fields['user_groups'].queryset = BranchGroup.objects.none()
                if 'course_groups' in self.fields:
                    self.fields['course_groups'].queryset = BranchGroup.objects.none()
                if 'courses' in self.fields:
                    self.fields['courses'].queryset = Course.objects.none()
        else:
            # No branch selected, show no groups
            if 'user_groups' in self.fields:
                self.fields['user_groups'].queryset = BranchGroup.objects.none()
            if 'course_groups' in self.fields:
                self.fields['course_groups'].queryset = BranchGroup.objects.none()
            if 'courses' in self.fields:
                self.fields['courses'].queryset = Course.objects.none()
        
        # Add error classes to all fields
        for field in self.fields:
            self.fields[field].widget.attrs.update({'class': 'form-input'})
            if self.fields[field].required:
                self.fields[field].widget.attrs.update({'required': 'required'})

    def clean(self) -> Dict[str, Any]:
        cleaned_data = super().clean()
        
        # Get key fields for duplicate checking
        email = cleaned_data.get('email')
        username = cleaned_data.get('username') 
        role = cleaned_data.get('role')
        branch = cleaned_data.get('branch')
        
        # Check for duplicate user role accounts
        if email and role:
            # Check for existing user with same email and role combination
            existing_user_query = CustomUser.objects.filter(
                email=email,
                role=role,
                is_active=True
            )
            
            # If branch is provided, include it in the uniqueness check
            if branch:
                existing_user_query = existing_user_query.filter(branch=branch)
                
            # Exclude current user if editing
            if self.instance and self.instance.pk:
                existing_user_query = existing_user_query.exclude(pk=self.instance.pk)
                
            if existing_user_query.exists():
                existing_user = existing_user_query.first()
                if branch:
                    raise forms.ValidationError(
                        f"A user with the same email ({email}) and role ({dict(CustomUser.ROLE_CHOICES)[role]}) "
                        f"already exists in branch '{branch.name}'. User role accounts must be unique."
                    )
                else:
                    raise forms.ValidationError(
                        f"A user with the same email ({email}) and role ({dict(CustomUser.ROLE_CHOICES)[role]}) "
                        f"already exists. User role accounts must be unique."
                    )
        
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = self.cleaned_data.get('role', 'learner')
        user.branch = self.cleaned_data.get('branch')
        if commit:
            user.save()
            
            # Handle group assignments
            user_groups = self.cleaned_data.get('user_groups', [])
            course_groups = self.cleaned_data.get('course_groups', [])
            
            # Add user to selected user groups
            for group in user_groups:
                from groups.models import GroupMembership
                GroupMembership.objects.get_or_create(
                    group=group,
                    user=user,
                    defaults={
                        'is_active': True,
                        'invited_by': self.request.user if self.request else None
                    }
                )
            
            # Add user to selected course groups
            for group in course_groups:
                from groups.models import GroupMembership
                GroupMembership.objects.get_or_create(
                    group=group,
                    user=user,
                    defaults={
                        'is_active': True,
                        'invited_by': self.request.user if self.request else None
                    }
                )
            
            # Handle course enrollments if courses were selected
            courses = self.cleaned_data.get('courses')
            if courses:
                from courses.models import CourseEnrollment
                from django.utils import timezone
                
                for course in courses:
                    CourseEnrollment.objects.get_or_create(
                        user=user,
                        course=course,
                        defaults={
                            'enrolled_at': timezone.now(),
                            'enrollment_source': 'manual'
                        }
                    )
            
            # Auto-enroll user in courses based on course group memberships
            if course_groups:
                from courses.models import CourseEnrollment
                from django.utils import timezone
                
                for group in course_groups:
                    # Get courses accessible to this group
                    accessible_courses = group.accessible_courses.all()
                    for course in accessible_courses:
                        CourseEnrollment.objects.get_or_create(
                            user=user,
                            course=course,
                            defaults={
                                'enrolled_at': timezone.now(),
                                'enrollment_source': 'auto_group'
                            }
                        )
        return user


class EnhancedUserChangeForm(CustomUserChangeForm):
    """Enhanced user editing form with group selection and automatic enrollment"""
    
    class Meta(CustomUserChangeForm.Meta):
        # Inherit all fields from CustomUserChangeForm including group fields
        pass


    def __init__(self, *args, **kwargs):
        # Don't pop 'request' here - let the parent class handle it
        # The parent class (CustomUserChangeForm) will pop it and set self.request
        super().__init__(*args, **kwargs)
        
        # Note: self.request and self.is_self_edit are already set by parent CustomUserChangeForm.__init__
        # Re-confirm self-edit scenario (already set by parent, but kept for clarity)
        self.is_self_edit = (self.request and self.instance and self.instance.pk and 
                            self.request.user.id == self.instance.pk)
        
        # Set field requirements and styling
        if 'first_name' in self.fields:
            self.fields['first_name'].required = True
        if 'last_name' in self.fields:
            self.fields['last_name'].required = True
        if 'role' in self.fields:
            self.fields['role'].required = True
        
        # Add help text
        if 'username' in self.fields:
            self.fields['username'].help_text = "Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only."
        if 'email' in self.fields:
            self.fields['email'].help_text = "Required. Enter a valid email address."
        if 'role' in self.fields:
            self.fields['role'].help_text = "Select the user's role in the system."
        if 'branch' in self.fields:
            self.fields['branch'].help_text = "Select the branch this user belongs to."
        if 'timezone' in self.fields:
            self.fields['timezone'].help_text = "Select the user's preferred timezone"

        # Set up timezone choices
        if 'timezone' in self.fields:
            self.fields['timezone'].widget.choices = [(tz, tz) for tz in pytz.common_timezones]

        # Set up group querysets
        from groups.models import BranchGroup
        
        # Set up group querysets based on target user's branch (not editor's branch)
        if 'user_groups' in self.fields and 'course_groups' in self.fields:
            # For editing existing users, use the target user's branch
            if self.instance and self.instance.pk and self.instance.branch:
                target_branch = self.instance.branch
                self.fields['user_groups'].queryset = BranchGroup.objects.filter(
                    branch=target_branch, 
                    group_type='user',
                    is_active=True
                ).order_by('name')
                self.fields['course_groups'].queryset = BranchGroup.objects.filter(
                    branch=target_branch, 
                    group_type='course',
                    is_active=True
                ).order_by('name')
            # For new users or when no branch is set, use editor's branch as fallback
            elif self.request and hasattr(self.request, 'user') and hasattr(self.request.user, 'branch') and self.request.user.branch:
                user_branch = self.request.user.branch
                self.fields['user_groups'].queryset = BranchGroup.objects.filter(
                    branch=user_branch, 
                    group_type='user',
                    is_active=True
                ).order_by('name')
                self.fields['course_groups'].queryset = BranchGroup.objects.filter(
                    branch=user_branch, 
                    group_type='course',
                    is_active=True
                ).order_by('name')
            else:
                # No branch available, show no groups
                self.fields['user_groups'].queryset = BranchGroup.objects.none()
                self.fields['course_groups'].queryset = BranchGroup.objects.none()
        else:
            print("Warning: Group fields not found in change form!")
        
        # Handle branch selection from form data (for POST requests)
        if self.data.get('branch'):
            try:
                branch_id = int(self.data.get('branch'))
                branch = Branch.objects.get(id=branch_id)
                self.fields['user_groups'].queryset = BranchGroup.objects.filter(
                    branch=branch, 
                    group_type='user',
                    is_active=True
                ).order_by('name')
                self.fields['course_groups'].queryset = BranchGroup.objects.filter(
                    branch=branch, 
                    group_type='course',
                    is_active=True
                ).order_by('name')
            except (ValueError, TypeError, Branch.DoesNotExist):
                self.fields['user_groups'].queryset = BranchGroup.objects.none()
                self.fields['course_groups'].queryset = BranchGroup.objects.none()

        # Set initial values for group fields if editing existing user
        if self.instance and self.instance.pk:
            # Get current group memberships
            user_groups = self.instance.group_memberships.filter(
                group__group_type='user',
                is_active=True
            ).values_list('group', flat=True)
            course_groups = self.instance.group_memberships.filter(
                group__group_type='course',
                is_active=True
            ).values_list('group', flat=True)
            
            # Include current memberships in the queryset even if they're from different branches
            # This ensures they show as selected in the form
            if user_groups.exists():
                current_user_groups = BranchGroup.objects.filter(
                    id__in=user_groups
                )
                # Union the current queryset with the user's current groups
                self.fields['user_groups'].queryset = self.fields['user_groups'].queryset.union(current_user_groups)
            
            if course_groups.exists():
                current_course_groups = BranchGroup.objects.filter(
                    id__in=course_groups
                )
                # Union the current queryset with the user's current groups
                self.fields['course_groups'].queryset = self.fields['course_groups'].queryset.union(current_course_groups)
            
            # Auto-select user groups if learner has course groups but no user groups
            if (self.instance.role == 'learner' and 
                course_groups.exists() and 
                not user_groups.exists()):
                
                # Get the branch from the user
                user_branch = self.instance.branch
                if user_branch:
                    # Find appropriate user groups for this learner
                    suggested_user_groups = BranchGroup.objects.filter(
                        branch=user_branch,
                        group_type='user',
                        is_active=True
                    ).values_list('id', flat=True)
                    
                    # Set the suggested user groups as initial
                    self.fields['user_groups'].initial = list(suggested_user_groups)
            else:
                # Use current user groups if they exist
                # Only include groups that are in the queryset
                available_user_group_ids = set(self.fields['user_groups'].queryset.values_list('id', flat=True))
                user_group_ids = set(user_groups)
                initial_user_groups = list(user_group_ids.intersection(available_user_group_ids))
                self.fields['user_groups'].initial = initial_user_groups
            
            # Only include course groups that are in the queryset
            available_course_group_ids = set(self.fields['course_groups'].queryset.values_list('id', flat=True))
            course_group_ids = set(course_groups)
            initial_course_groups = list(course_group_ids.intersection(available_course_group_ids))
            self.fields['course_groups'].initial = initial_course_groups

        # Handle self-editing restrictions
        if self.is_self_edit:
            # Users editing their own profile cannot change role or branch
            self.fields['role'].disabled = True
            self.fields['role'].widget.attrs['readonly'] = True
            self.fields['branch'].disabled = True
            self.fields['branch'].widget.attrs['readonly'] = True
            
            # Set current values for disabled fields
            if self.instance:
                self.fields['role'].initial = self.instance.role
                self.fields['branch'].initial = self.instance.branch

        # Ensure password fields are not required in edit mode
        if self.is_self_edit or (self.instance and self.instance.pk):
            # Remove required attribute from password fields in edit mode
            if 'password1' in self.fields:
                self.fields['password1'].required = False
                self.fields['password1'].widget.attrs.pop('required', None)
            if 'password2' in self.fields:
                self.fields['password2'].required = False
                self.fields['password2'].widget.attrs.pop('required', None)

    def clean(self):
        cleaned_data = super().clean()
        
        # Handle password change validation - only validate if passwords are actually provided
        password1 = cleaned_data.get('password1')
        password2 = cleaned_data.get('password2')
        
        # Check if user is attempting to change password (both fields must have meaningful content)
        has_password1 = password1 and password1.strip()
        has_password2 = password2 and password2.strip()
        
        # If only one password field has content, that's an error
        if has_password1 and not has_password2:
            raise forms.ValidationError("Please confirm your new password.")
        if has_password2 and not has_password1:
            raise forms.ValidationError("Please enter a new password.")
        
        # Only validate password change if both fields have content
        if has_password1 and has_password2:
            # Both password fields have content, validate password change
            if password1 != password2:
                raise forms.ValidationError("The two password fields didn't match.")
            
            # Validate password strength
            if len(password1) < 8:
                raise forms.ValidationError("Password must be at least 8 characters long.")
        
        return cleaned_data

    def save(self, commit=True):
        """Save the form data to the model instance."""
        user = super().save(commit=False)
        
        # Set fields from form data
        user.role = self.cleaned_data.get('role', user.role)
        user.branch = self.cleaned_data.get('branch', user.branch)
        
        # Set timezone if provided
        if 'timezone' in self.cleaned_data:
            user.timezone = self.cleaned_data.get('timezone')
        
        # Handle password change if provided
        password = self.cleaned_data.get('password1')
        if password:
            user.set_password(password)
        
        if commit:
            user.save()
            
            # Ensure all existing memberships have a valid invited_by value
            # This prevents validation errors when updating memberships
            from groups.models import GroupMembership
            if self.request and self.request.user:
                GroupMembership.objects.filter(
                    user=user,
                    invited_by__isnull=True
                ).update(invited_by=self.request.user)
            
            # Handle group assignments
            user_groups = self.cleaned_data.get('user_groups', [])
            course_groups = self.cleaned_data.get('course_groups', [])
            
            # Get current group memberships
            current_user_groups = set(user.group_memberships.filter(
                group__group_type='user',
                is_active=True
            ).values_list('group', flat=True))
            current_course_groups = set(user.group_memberships.filter(
                group__group_type='course',
                is_active=True
            ).values_list('group', flat=True))
            
            # Determine groups to add and remove
            new_user_groups = set(user_groups)
            new_course_groups = set(course_groups)
            
            groups_to_add = new_user_groups - current_user_groups
            groups_to_remove = current_user_groups - new_user_groups
            course_groups_to_add = new_course_groups - current_course_groups
            course_groups_to_remove = current_course_groups - new_course_groups
            
            # Add user to new groups
            for group in groups_to_add:
                from groups.models import GroupMembership
                GroupMembership.objects.get_or_create(
                    group=group,
                    user=user,
                    defaults={
                        'is_active': True,
                        'invited_by': self.request.user if self.request else None
                    }
                )
            
            for group in course_groups_to_add:
                from groups.models import GroupMembership
                GroupMembership.objects.get_or_create(
                    group=group,
                    user=user,
                    defaults={
                        'is_active': True,
                        'invited_by': self.request.user if self.request else None
                    }
                )
            
            # Remove user from groups that are no longer selected
            for group in groups_to_remove:
                from groups.models import GroupMembership
                GroupMembership.objects.filter(
                    group=group,
                    user=user
                ).update(is_active=False)
            
            for group in course_groups_to_remove:
                from groups.models import GroupMembership
                GroupMembership.objects.filter(
                    group=group,
                    user=user
                ).update(is_active=False)
            
            # Auto-enroll user in courses based on new course group memberships
            if course_groups_to_add:
                from courses.models import CourseEnrollment
                from django.utils import timezone
                
                for group in course_groups_to_add:
                    # Get courses accessible to this group
                    accessible_courses = group.accessible_courses.all()
                    for course in accessible_courses:
                        CourseEnrollment.objects.get_or_create(
                            user=user,
                            course=course,
                            defaults={
                                'enrolled_at': timezone.now(),
                                'enrollment_source': 'auto_group'
                            }
                        )
            
        return user
