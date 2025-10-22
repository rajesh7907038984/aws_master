from django import forms
from django.core.exceptions import ValidationError
from .models import BranchGroup, GroupMemberRole, GroupMembership, CourseGroupAccess, Branch
from users.models import CustomUser
from django.db import transaction

class BranchGroupForm(forms.ModelForm):
    branch = forms.ModelChoiceField(
        queryset=Branch.objects.all(),
        empty_label="Select Branch",
        required=True,
        widget=forms.Select(attrs={
            'class': 'w-full px-3 py-2 border border-gray-300 rounded-md text-black bg-white'
        })
    )

    class Meta:
        model = BranchGroup
        fields = ['name', 'description', 'is_active', 'branch', 'group_type']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-md text-black',
                'placeholder': 'Enter group name'
            }),
            'description': forms.Textarea(attrs={
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-md text-black',
                'rows': 3,
                'placeholder': 'Enter group description'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'h-4 w-4 text-blue-600 rounded border-gray-300'
            }),
            'group_type': forms.HiddenInput()
        }
        
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        if self.user:
            # For Super Admin users, show branches from their assigned businesses
            if self.user.role == 'superadmin':
                from core.utils.business_filtering import filter_branches_by_business
                allowed_branches = filter_branches_by_business(self.user)
                self.fields['branch'].queryset = allowed_branches
                self.fields['branch'].help_text = "Select a branch from your assigned businesses."
            # For non-superusers (including instructors), set their branch and make the field read-only
            elif not self.user.is_superuser:
                if self.user.branch:
                    self.fields['branch'].initial = self.user.branch
                    self.fields['branch'].widget.attrs['disabled'] = True
                    # Use a hidden field to ensure the branch value is submitted
                    self.initial['branch'] = self.user.branch.id
                else:
                    # If user has no branch, show an error message
                    self.fields['branch'].help_text = "Your account doesn't have a branch assigned. Please contact an administrator."

    def clean(self):
        cleaned_data = super().clean()
        
        if self.user and self.user.role == 'superadmin':
            # For super admins, validate the selected branch is within their businesses
            selected_branch = cleaned_data.get('branch')
            if selected_branch:
                from core.utils.business_filtering import filter_branches_by_business
                allowed_branches = filter_branches_by_business(self.user).values_list('id', flat=True)
                if selected_branch.id not in allowed_branches:
                    self.add_error('branch', "You can only create groups in branches within your assigned businesses.")
            else:
                self.add_error('branch', 'Please select a branch.')
        elif self.user and not self.user.is_superuser:
            # For non-superusers (including instructors), always use their branch
            if self.user.branch:
                cleaned_data['branch'] = self.user.branch
            else:
                self.add_error('branch', "You don't have a branch assigned to your account. Please contact an administrator.")
        elif not cleaned_data.get('branch'):
            # For superusers, ensure branch is selected
            self.add_error('branch', 'Please select a branch.')
        
        # Validate name is unique within the branch
        name = cleaned_data.get('name')
        branch = cleaned_data.get('branch')
        
        if name and branch:
            query = BranchGroup.objects.filter(name=name, branch=branch)
            if self.instance and self.instance.pk:
                query = query.exclude(pk=self.instance.pk)
            
            if query.exists():
                self.add_error('name', 'A group with this name already exists in this branch.')
        
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.created_by = self.user
        
        if self.user.role != 'superadmin' and not self.user.is_superuser and self.user.branch:
            instance.branch = self.user.branch
        
        # Preserve the group_type value from the form data
        if 'group_type' in self.cleaned_data:
            instance.group_type = self.cleaned_data['group_type']
        
        if commit:
            instance.save()
        return instance

class GroupMembershipForm(forms.ModelForm):
    class Meta:
        model = GroupMembership
        fields = ['custom_role', 'is_active']

    def __init__(self, *args, **kwargs):
        self.group = kwargs.pop('group', None)
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        if self.group:
            # Filter roles by group
            self.fields['custom_role'].queryset = GroupMemberRole.objects.filter(group=self.group)
            self.fields['custom_role'].empty_label = None

            # Style form fields
            self.fields['custom_role'].widget.attrs.update({
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-md'
            })
            self.fields['is_active'].widget.attrs.update({
                'class': 'h-4 w-4 text-blue-600 rounded border-gray-300'
            })

    def clean(self):
        cleaned_data = super().clean()
        return cleaned_data

class CourseGroupAccessForm(forms.ModelForm):
    class Meta:
        model = CourseGroupAccess
        fields = ['course', 'group', 'can_modify', 'assigned_role']
        
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        if self.user and not self.user.is_superuser:
            # Filter courses by branch if user has a branch
            if self.user.branch:
                self.fields['course'].queryset = self.fields['course'].queryset.filter(
                    branch=self.user.branch
                )
            # Don't filter groups by branch anymore
            
        # Add styling classes to form fields
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'w-full px-3 py-2 border border-gray-300 rounded-md'
            
        # Initialize assigned_role field with empty queryset
        self.fields['assigned_role'].queryset = GroupMemberRole.objects.none()
        self.fields['assigned_role'].required = False
        
        # If initial group is provided, filter roles by group
        if 'group' in self.initial:
            group_id = self.initial['group']
            if group_id:
                self.fields['assigned_role'].queryset = GroupMemberRole.objects.filter(
                    group_id=group_id
                )
