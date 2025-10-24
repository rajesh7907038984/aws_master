from django.contrib import admin
from django.core.exceptions import PermissionDenied, ValidationError
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.urls import reverse
from django.http import HttpResponseRedirect
from django.contrib.auth.models import AnonymousUser
from .models import BranchGroup, GroupMemberRole, GroupMembership, CourseGroupAccess
from courses.models import Course
from django import forms
from users.models import CustomUser, Branch

class GroupMemberRoleInline(admin.TabularInline):
    model = GroupMemberRole
    extra = 1
    fields = ('name', 'can_view', 'can_edit', 'can_manage_members', 'can_manage_content')
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        # Show all roles for groups in user's branch
        return qs.filter(
            group__branch=request.user.branch
        ).select_related('group')
        
    def has_add_permission(self, request, obj=None):
        return True

    def has_view_permission(self, request, obj=None):
        return True
        
    def has_delete_permission(self, request, obj=None):
        return True

class GroupMembershipInline(admin.TabularInline):
    model = GroupMembership
    extra = 1
    fields = ('user', 'custom_role', 'is_active')
    # Remove invited_by from fields since it's handled automatically
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(
            group__branch=request.user.branch
        ).select_related(
            'user', 
            'custom_role', 
            'group',
            'invited_by'
        )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if not request.user.is_superuser:
            if db_field.name == "user":
                kwargs["queryset"] = CustomUser.objects.filter(
                    branch=request.user.branch,
                    is_active=True
                )
            elif db_field.name == "custom_role":
                if getattr(self, 'parent_instance', None):
                    kwargs["queryset"] = GroupMemberRole.objects.filter(
                        group=self.parent_instance  # Only show roles from the current group
                    )

        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        self.parent_instance = obj
        return formset

    def has_add_permission(self, request, obj=None):
        return True

    def has_change_permission(self, request, obj=None):
        return True

    def has_delete_permission(self, request, obj=None):
        return True

class BranchGroupForm(forms.ModelForm):
    class Meta:
        model = BranchGroup
        fields = ['name', 'description', 'branch', 'created_by', 'is_active']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }
        
    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Get the user from either request or user parameter
        current_user = self.request.user if self.request else self.user
        
        if current_user and not current_user.is_superuser:
            # For non-superusers, set their branch and make it read-only
            self.fields['branch'].initial = current_user.branch
            self.fields['branch'].disabled = True
            self.fields['branch'].required = True
            self.fields['created_by'].widget = forms.HiddenInput()
            self.fields['created_by'].initial = current_user
            self.fields['created_by'].disabled = True
        else:
            # For superusers, branch is required
            self.fields['branch'].required = True
            self.fields['branch'].queryset = Branch.objects.all()
            self.fields['created_by'].required = False

    def clean(self):
        cleaned_data = super().clean()
        current_user = self.request.user if self.request else self.user
        
        # Handle branch field
        if current_user and not current_user.is_superuser:
            # For non-superusers, always use their branch
            cleaned_data['branch'] = current_user.branch
            if not current_user.branch:
                raise forms.ValidationError("You must be assigned to a branch to create groups.")
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
        
        # Set created_by for non-superusers
        if current_user and not current_user.is_superuser:
            cleaned_data['created_by'] = current_user
        
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        current_user = self.request.user if self.request else self.user
        
        if not current_user.is_superuser:
            instance.branch = current_user.branch
            instance.created_by = current_user
        
        if commit:
            instance.save()
        return instance

@admin.register(BranchGroup)
class BranchGroupAdmin(admin.ModelAdmin):
    form = BranchGroupForm
    list_display = ['name', 'branch', 'created_by', 'is_active', 'created_at']
    list_filter = ['is_active', 'branch']
    search_fields = ['name', 'description']
    inlines = [GroupMemberRoleInline, GroupMembershipInline]
    readonly_fields = ('created_at', 'updated_at')

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        # Show all groups in user's branch
        return qs.filter(branch=request.user.branch)

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.request = request
        return form

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        formset.form.request = request
        return formset

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if not request.user.is_superuser:
            if db_field.name == "created_by":
                kwargs["initial"] = request.user
                kwargs["disabled"] = True
                kwargs["queryset"] = CustomUser.objects.filter(
                    branch=request.user.branch
                )
            elif db_field.name == "branch":
                kwargs["queryset"] = request.user.branch.__class__.objects.filter(
                    id=request.user.branch.id
                )
        else:
            # For superusers, filter created_by based on selected branch
            if db_field.name == "created_by" and request.method == "GET":
                branch_id = request.GET.get('branch')
                if branch_id:
                    kwargs["queryset"] = CustomUser.objects.filter(branch_id=branch_id)
                else:
                    kwargs["queryset"] = CustomUser.objects.all()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_inline_instances(self, request, obj=None):
        # Only show inlines for existing objects
        if not obj:
            return []
        return super().get_inline_instances(request, obj)

    def save_formset(self, request, form, formset, change):
        if formset.model == GroupMembership:
            # Handle deletions explicitly
            instances = formset.save(commit=False)
            for obj in formset.deleted_objects:
                obj.delete()
            # Save new/modified instances
            for instance in instances:
                if isinstance(instance, GroupMembership):
                    # Set invited_by for new instances or if it's None
                    if not instance.pk or instance.invited_by is None:
                        instance.invited_by = request.user
                instance.save()
            formset.save_m2m()
        else:
            formset.save()

    def save_model(self, request, obj, form, change):
        if not change:  # Only for new objects
            obj.created_by = request.user
            if not (request.user.is_superuser or request.user.role in ['globaladmin', 'superadmin']):
                obj.branch = request.user.branch
        super().save_model(request, obj, form, change)

    def has_module_permission(self, request):
        return True

    def has_view_permission(self, request, obj=None):
        if request.user.is_superuser or (hasattr(request.user, 'role') and request.user.role in ['globaladmin', 'superadmin']):
            return True
        if obj is None:
            return True
        # If the group has no branch, everyone can see it
        if not obj.branch:
            return True
        return hasattr(request.user, 'branch') and obj.branch == request.user.branch

    def has_change_permission(self, request, obj=None):
        return self.has_view_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if request.user.is_superuser or request.user.role in ['globaladmin', 'superadmin']:
            return True
        if obj is None:
            return False
        return obj.branch == request.user.branch

    def has_add_permission(self, request):
        if not request.user.is_authenticated:
            return False
        return request.user.is_superuser or request.user.role in ['superadmin', 'admin']

    def response_add(self, request, obj, post_url_continue=None):
        """Customize response after adding a new object"""
        response = super().response_add(request, obj, post_url_continue)
        if '_addanother' not in request.POST and '_continue' not in request.POST:
            # Redirect to the change form to show inlines
            return HttpResponseRedirect(
                reverse('admin:groups_branchgroup_change', args=[obj.pk])
            )

    class Media:
        js = ('admin/js/branch_group_admin.js',)  # We'll create this file next

class CourseGroupAccessForm(forms.ModelForm):
    class Meta:
        model = CourseGroupAccess
        fields = ['course', 'group', 'can_modify', 'assigned_by']
        
    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        
        if self.request and not self.request.user.is_superuser:
            # For non-superusers with a branch, filter courses by their branch
            if self.request.user.branch:
                self.fields['course'].queryset = Course.objects.filter(
                    branch=self.request.user.branch
                )
            # Don't filter groups by branch anymore
            self.fields['assigned_by'].initial = self.request.user
            self.fields['assigned_by'].disabled = True
        else:
            # For superusers, show all courses and groups
            self.fields['course'].queryset = Course.objects.all()
            self.fields['group'].queryset = BranchGroup.objects.all()
            self.fields['assigned_by'].required = False

    def clean(self):
        cleaned_data = super().clean()
        course = cleaned_data.get('course')
        group = cleaned_data.get('group')
        assigned_by = cleaned_data.get('assigned_by')
        
        if not course or not group:
            return cleaned_data
            
        # Only validate branch relationships if both entities have branches
        if course.branch and group.branch and course.branch != group.branch:
            self.add_error('group', 'Course and group must belong to the same branch.')
            
        if assigned_by and group.branch and assigned_by.branch and assigned_by.branch != group.branch:
            self.add_error('assigned_by', 'Assigner must belong to the same branch as the group.')
            
        return cleaned_data

@admin.register(CourseGroupAccess)
class CourseGroupAccessAdmin(admin.ModelAdmin):
    form = CourseGroupAccessForm
    list_display = ['course', 'group', 'can_modify', 'assigned_by', 'assigned_at']
    list_filter = ['can_modify', 'group__branch']
    search_fields = ['course__title', 'group__name']
    readonly_fields = ('assigned_at',)

    def get_form(self, request, obj=None, **kwargs):
        kwargs['form'] = self.form
        form = super().get_form(request, obj, **kwargs)
        form.request = request
        return form

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(group__branch=request.user.branch)

    def save_model(self, request, obj, form, change):
        if not change:  # Only for new objects
            obj.assigned_by = request.user
        super().save_model(request, obj, form, change)

    def has_module_permission(self, request):
        return True

    def has_view_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        if obj is None:
            return True
        return obj.group.branch == request.user.branch

    def has_change_permission(self, request, obj=None):
        return self.has_view_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        if obj is None:
            return False
        return obj.group.branch == request.user.branch

    def has_add_permission(self, request):
        if not request.user.is_authenticated:
            return False
        return request.user.is_superuser or getattr(request.user, 'role', None) == 'admin'