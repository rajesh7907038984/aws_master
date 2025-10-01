from django import forms
from django.forms import formset_factory, BaseFormSet
from django.contrib.auth import get_user_model
from core.utils.fields import TinyMCEField
from users.models import Branch
from groups.models import BranchGroup
from courses.models import Course
from .models import (
    NotificationSettings, NotificationTypeSettings, NotificationType,
    BulkNotification, NotificationTemplate, Notification
)

User = get_user_model()


class NotificationSettingsForm(forms.ModelForm):
    """Form for user notification settings"""
    
    class Meta:
        model = NotificationSettings
        fields = [
            'email_notifications_enabled',
            'web_notifications_enabled'
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email_notifications_enabled'].widget.attrs.update({
            'class': 'form-check-input'
        })
        self.fields['web_notifications_enabled'].widget.attrs.update({
            'class': 'form-check-input'
        })


class NotificationTypeSettingsForm(forms.ModelForm):
    """Form for individual notification type settings"""
    
    class Meta:
        model = NotificationTypeSettings
        fields = ['email_enabled', 'web_enabled']
        widgets = {
            'email_enabled': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'web_enabled': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        self.notification_type = kwargs.pop('notification_type', None)
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        if self.notification_type:
            self.fields['email_enabled'].label = f"Email notifications for {self.notification_type.display_name}"
            self.fields['web_enabled'].label = f"Web notifications for {self.notification_type.display_name}"


class BaseNotificationTypeSettingsFormSet(BaseFormSet):
    """Base formset for notification type settings"""
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        self.notification_types = kwargs.pop('notification_types', [])
        super().__init__(*args, **kwargs)

    def _construct_form(self, i, **kwargs):
        if i < len(self.notification_types):
            kwargs['notification_type'] = self.notification_types[i]
            kwargs['user'] = self.user
            
            # Get or create the settings instance
            if self.user and self.notification_types[i]:
                settings, created = NotificationTypeSettings.objects.get_or_create(
                    user=self.user,
                    notification_type=self.notification_types[i],
                    defaults={
                        'email_enabled': self.notification_types[i].default_email_enabled,
                        'web_enabled': self.notification_types[i].default_web_enabled,
                    }
                )
                kwargs['instance'] = settings
        
        return super()._construct_form(i, **kwargs)

    def save(self):
        """Save all forms in the formset"""
        for form in self.forms:
            if form.is_valid() and form.has_changed():
                form.save()


# Create the formset
NotificationTypeSettingsFormSet = formset_factory(
    NotificationTypeSettingsForm,
    formset=BaseNotificationTypeSettingsFormSet,
    extra=0,
    can_delete=False
)


class BulkNotificationForm(forms.ModelForm):
    """Form for creating/editing bulk notifications"""
    
    # Override target_roles to ensure it always returns a list
    target_roles = forms.MultipleChoiceField(
        choices=[],  # Will be set in __init__
        required=False,
        widget=forms.CheckboxSelectMultiple()
    )
    
    class Meta:
        model = BulkNotification
        fields = [
            'title', 'short_message', 'message', 'notification_type',
            'recipient_type', 'target_roles', 'target_branches', 
            'target_groups', 'target_courses', 'custom_recipients',
            'priority', 'action_url', 'action_text', 'scheduled_for'
        ]
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'short_message': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'recipient_type': forms.Select(attrs={'class': 'form-select'}),
            'target_branches': forms.CheckboxSelectMultiple(),
            'target_groups': forms.CheckboxSelectMultiple(),
            'target_courses': forms.CheckboxSelectMultiple(),
            'custom_recipients': forms.CheckboxSelectMultiple(),
            'priority': forms.Select(attrs={'class': 'form-select'}),
            'action_url': forms.URLInput(attrs={'class': 'form-control'}),
            'action_text': forms.TextInput(attrs={'class': 'form-control'}),
            'scheduled_for': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Set role choices based on user permissions
        if self.user:
            if self.user.role in ['globaladmin', 'superadmin']:
                role_choices = [
                    ('superadmin', 'SuperAdmin'),
                    ('admin', 'Admin'),
                    ('instructor', 'Instructor'),
                    ('learner', 'Learner'),
                ]
            elif self.user.role == 'admin':
                role_choices = [
                    ('admin', 'Admin'),
                    ('instructor', 'Instructor'),
                    ('learner', 'Learner'),
                ]
            else:  # instructor
                role_choices = [
                    ('instructor', 'Instructor'),
                    ('learner', 'Learner'),
                ]
            
            # Update target_roles field choices
            self.fields['target_roles'].choices = role_choices
            
            # Filter queryset based on user permissions
            if self.user.role != 'superadmin':
                # Filter branches based on user's branch
                if self.user.branch:
                    self.fields['target_branches'].queryset = Branch.objects.filter(
                        id=self.user.branch.id
                    )
                else:
                    self.fields['target_branches'].queryset = Branch.objects.none()
                
                # Filter groups based on user's branch
                if self.user.branch:
                    self.fields['target_groups'].queryset = BranchGroup.objects.filter(
                        branch=self.user.branch
                    )
                else:
                    self.fields['target_groups'].queryset = BranchGroup.objects.none()
                
                # Filter courses based on user's access
                accessible_courses = Course.objects.none()
                if hasattr(self.user, 'get_accessible_objects'):
                    accessible_courses = self.user.get_accessible_objects(Course.objects.all())
                self.fields['target_courses'].queryset = accessible_courses
                
                # Filter custom recipients based on user's branch
                if self.user.branch:
                    self.fields['custom_recipients'].queryset = User.objects.filter(
                        branch=self.user.branch, is_active=True
                    )
                else:
                    self.fields['custom_recipients'].queryset = User.objects.filter(
                        is_active=True
                    )

    def clean_target_roles(self):
        """Ensure target_roles is always a list"""
        target_roles = self.cleaned_data.get('target_roles')
        if target_roles is None:
            return []
        return target_roles

    def clean(self):
        cleaned_data = super().clean()
        recipient_type = cleaned_data.get('recipient_type')
        
        # Ensure target_roles is always a list (never None)
        target_roles = cleaned_data.get('target_roles', [])
        if target_roles is None:
            target_roles = []
        cleaned_data['target_roles'] = target_roles
        
        # Validate recipient type specific fields
        if recipient_type == 'role':
            if not target_roles:
                raise forms.ValidationError("Please select at least one role for role-based notifications.")
        
        elif recipient_type == 'branch':
            if not cleaned_data.get('target_branches'):
                raise forms.ValidationError("Please select at least one branch for branch-based notifications.")
        
        elif recipient_type == 'group':
            if not cleaned_data.get('target_groups'):
                raise forms.ValidationError("Please select at least one group for group-based notifications.")
        
        elif recipient_type == 'course':
            if not cleaned_data.get('target_courses'):
                raise forms.ValidationError("Please select at least one course for course-based notifications.")
        
        elif recipient_type == 'custom':
            if not cleaned_data.get('custom_recipients'):
                raise forms.ValidationError("Please select at least one recipient for custom notifications.")
        
        # For non-role recipient types, ensure target_roles is empty
        if recipient_type != 'role':
            cleaned_data['target_roles'] = []
        
        return cleaned_data


class NotificationTemplateForm(forms.ModelForm):
    """Form for creating/editing notification templates"""
    
    class Meta:
        model = NotificationTemplate
        fields = [
            'name', 'description', 'notification_type',
            'title_template', 'message_template', 'short_message_template',
            'default_priority', 'default_action_url', 'default_action_text',
            'available_variables', 'is_active'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'notification_type': forms.Select(attrs={'class': 'form-select'}),
            'title_template': forms.TextInput(attrs={'class': 'form-control'}),
            'short_message_template': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'default_priority': forms.Select(attrs={'class': 'form-select'}),
            'default_action_url': forms.URLInput(attrs={'class': 'form-control'}),
            'default_action_text': forms.TextInput(attrs={'class': 'form-control'}),
            'available_variables': forms.Textarea(attrs={
                'class': 'form-control', 
                'rows': 4,
                'placeholder': 'Enter available variables as JSON array, e.g., ["user_name", "course_name", "deadline"]'
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean_available_variables(self):
        """Validate available_variables as JSON"""
        import json
        data = self.cleaned_data['available_variables']
        if data:
            try:
                # Try to parse as JSON
                variables = json.loads(data)
                if not isinstance(variables, list):
                    raise forms.ValidationError("Available variables must be a JSON array.")
                return variables
            except json.JSONDecodeError:
                # If not valid JSON, treat as list of strings
                variables = [var.strip() for var in data.split(',') if var.strip()]
                return variables
        return []


class QuickNotificationForm(forms.ModelForm):
    """Quick form for sending simple notifications"""
    
    recipient = forms.ModelChoiceField(
        queryset=User.objects.filter(is_active=True),
        widget=forms.Select(attrs={'class': 'form-select'}),
        required=True
    )
    
    class Meta:
        model = Notification
        fields = [
            'recipient', 'notification_type', 'title', 
            'short_message', 'message', 'priority', 
            'action_url', 'action_text'
        ]
        widgets = {
            'notification_type': forms.Select(attrs={'class': 'form-select'}),
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'short_message': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'priority': forms.Select(attrs={'class': 'form-select'}),
            'action_url': forms.URLInput(attrs={'class': 'form-control'}),
            'action_text': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        self.sender = kwargs.pop('sender', None)
        super().__init__(*args, **kwargs)
        
        # Filter recipients based on sender permissions
        if self.sender:
            if self.sender.role == 'instructor':
                # Instructors can only send to their students
                self.fields['recipient'].queryset = User.objects.filter(
                    assigned_instructor=self.sender,
                    is_active=True
                )
            elif self.sender.role == 'admin':
                # Admins can send to users in their branch
                if self.sender.branch:
                    self.fields['recipient'].queryset = User.objects.filter(
                        branch=self.sender.branch,
                        is_active=True
                    )


class NotificationFilterForm(forms.Form):
    """Form for filtering notifications"""
    
    TYPE_CHOICES = [
        ('all', 'All Notifications'),
        ('unread', 'Unread Only'),
        ('read', 'Read Only'),
    ]
    
    filter_type = forms.ChoiceField(
        choices=TYPE_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    priority = forms.ChoiceField(
        choices=[('', 'All Priorities')] + Notification.PRIORITY_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    notification_type = forms.ModelChoiceField(
        queryset=NotificationType.objects.filter(is_active=True),
        required=False,
        empty_label="All Types",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Search notifications...'
        })
    )
    
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )


class SMTPPasswordInput(forms.PasswordInput):
    """
    Custom password input that can optionally render saved passwords
    """
    def __init__(self, render_value=False, *args, **kwargs):
        self.render_value = render_value
        super().__init__(*args, **kwargs)
    
    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        if self.render_value and value:
            context['widget']['value'] = value
        return context





class EnhancedNotificationSettingsForm(forms.ModelForm):
    """Enhanced form for user notification settings"""
    
    class Meta:
        model = NotificationSettings
        fields = [
            'email_notifications_enabled',
            'web_notifications_enabled'
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Add CSS classes for styling
        for field_name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.update({'class': 'form-check-input'})
            elif not field_name.startswith(('enable_all_', 'disable_all_')):
                field.widget.attrs.update({'class': 'form-control'}) 