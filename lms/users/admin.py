from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm
from django.core.exceptions import PermissionDenied
from django.contrib.auth.models import AnonymousUser
from .models import CustomUser, UserQuestionnaire, UserQuizAssignment
from branches.models import Branch
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from django.http import HttpRequest

class BranchRestrictedUserChangeForm(UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = CustomUser
        fields = ('username', 'email', 'first_name', 'last_name', 'role', 'branch')

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if hasattr(self, 'current_user') and not (self.current_user.is_superuser or self.current_user.role in ['globaladmin', 'superadmin']):
            # Handle branch field
            if 'branch' in self.fields:
                self.fields['branch'].queryset = Branch.objects.filter(id=self.current_user.branch.id)
                self.fields['branch'].initial = self.current_user.branch
                self.fields['branch'].disabled = True
                self.fields['branch'].widget.can_change_related = False
                self.fields['branch'].widget.can_add_related = False
            
            # Restrict role choices for branch admin
            if 'role' in self.fields and self.current_user.role == 'admin':
                self.fields['role'].choices = [
                    choice for choice in self.fields['role'].choices 
                    if choice[0] not in ['superadmin', 'admin']
                ]

class BranchRestrictedUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = CustomUser
        fields = ('username', 'email', 'first_name', 'last_name', 'role', 'branch')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if hasattr(self, 'current_user') and not self.current_user.is_superuser:
            # Handle branch field
            if 'branch' in self.fields:
                self.fields['branch'].queryset = Branch.objects.filter(id=self.current_user.branch.id)
                self.fields['branch'].initial = self.current_user.branch
                self.fields['branch'].disabled = True
                self.fields['branch'].widget.can_change_related = False
                self.fields['branch'].widget.can_add_related = False

@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    form = BranchRestrictedUserChangeForm
    add_form = BranchRestrictedUserCreationForm

    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Personal info', {'fields': ('first_name', 'last_name', 'email', 'phone_number')}),
        ('Personal Information', {
            'fields': ('unique_learner_number', 'family_name', 'given_names', 'date_of_birth', 
                      'sex', 'sex_other', 'sexual_orientation', 'sexual_orientation_other',
                      'ethnicity', 'ethnicity_other', 'current_postcode'),
            'classes': ('collapse',)
        }),
        ('Address Information', {
            'fields': ('address_line1', 'address_line2', 'city', 'county', 'country', 
                      'is_non_uk_address', 'contact_preference'),
            'classes': ('collapse',)
        }),
        ('Education Background', {
            'fields': ('study_area', 'study_area_other', 'level_of_study', 'grades', 
                      'grades_other', 'date_achieved', 'has_learning_difficulty', 
                      'learning_difficulty_details', 'education_data'),
            'classes': ('collapse',)
        }),
        ('Employment History', {
            'fields': ('job_role', 'industry', 'industry_other', 'duration', 'key_skills', 
                      'employment_data', 'cv_file'),
            'classes': ('collapse',)
        }),
        ('Assessment Data', {
            'fields': ('initial_assessment_english', 'initial_assessment_maths', 
                      'initial_assessment_subject_specific', 'initial_assessment_other',
                      'initial_assessment_date', 'diagnostic_assessment_english',
                      'diagnostic_assessment_maths', 'diagnostic_assessment_subject_specific',
                      'diagnostic_assessment_other', 'diagnostic_assessment_date',
                      'functional_skills_english', 'functional_skills_maths',
                      'functional_skills_other', 'functional_skills_date'),
            'classes': ('collapse',)
        }),
        ('Additional Information', {
            'fields': ('statement_of_purpose_file', 'reason_for_pursuing_course', 
                      'career_objectives', 'relevant_past_work', 
                      'special_interests_and_strengths', 'achievements_and_awards'),
            'classes': ('collapse',)
        }),
        ('Roles and Permissions', {'fields': ('role', 'branch', 'assigned_instructor', 'is_active', 'is_staff', 'is_superuser')}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'email', 'password1', 'password2', 'role', 'branch'),
        }),
    )

    list_display = ['username', 'email', 'role', 'branch', 'has_cv_file', 'has_sop_file', 'is_active', 'date_joined']
    list_filter = ['is_active', 'role', 'branch']
    search_fields = ['username', 'email', 'first_name', 'last_name']
    ordering = ['-date_joined']
    
    def has_cv_file(self, obj):
        """Display if user has uploaded a CV file"""
        return bool(obj.cv_file)
    has_cv_file.boolean = True
    has_cv_file.short_description = 'CV File'
    
    def has_sop_file(self, obj):
        """Display if user has uploaded a Statement of Purpose file"""
        return bool(obj.statement_of_purpose_file)
    has_sop_file.boolean = True
    has_sop_file.short_description = 'SOP File'
    
    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.current_user = request.user
        if not request.user.is_superuser and request.user.role == 'admin':
            # Check if branch field exists in base_fields
            if 'branch' in form.base_fields:
                form.base_fields['branch'].initial = request.user.branch
                form.base_fields['branch'].disabled = True
                form.base_fields['branch'].queryset = Branch.objects.filter(id=request.user.branch.id)
            
            # Handle role choices
            if 'role' in form.base_fields:
                form.base_fields['role'].choices = [
                    (role, label) for role, label in form.base_fields['role'].choices
                    if role not in ['superadmin', 'admin']
                ]
        return form

@admin.register(UserQuestionnaire)
class UserQuestionnaireAdmin(admin.ModelAdmin):
    list_display = ['user', 'question_order', 'question_text_short', 'has_answer', 'has_document', 'confirmation_required', 'created_at']
    list_filter = ['confirmation_required', 'created_at', 'user__branch']
    search_fields = ['user__username', 'user__email', 'question_text', 'answer_text']
    ordering = ['user', 'question_order']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('user', 'question_order', 'created_by')
        }),
        ('Question Content', {
            'fields': ('question_text', 'answer_text', 'document')
        }),
        ('Confirmation', {
            'fields': ('confirmation_required',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def question_text_short(self, obj):
        """Display shortened question text"""
        return obj.question_text[:100] + "..." if len(obj.question_text) > 100 else obj.question_text
    question_text_short.short_description = 'Question'
    
    def has_answer(self, obj):
        """Display if question has an answer"""
        return obj.has_answer
    has_answer.boolean = True
    has_answer.short_description = 'Answered'
    
    def has_document(self, obj):
        """Display if question has a document"""
        return obj.has_document
    has_document.boolean = True
    has_document.short_description = 'Has Document'

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser or request.user.role in ['globaladmin', 'superadmin']:
            return qs
        if isinstance(request.user, AnonymousUser):
            return qs.none()
        return qs.filter(branch=request.user.branch).exclude(role='superadmin')

    def save_model(self, request, obj, form, change):
        if not (request.user.is_superuser or request.user.role in ['globaladmin', 'superadmin']):
            obj.branch = request.user.branch
        super().save_model(request, obj, form, change)

    def has_view_permission(self, request, obj=None):
        if request.user.is_superuser or request.user.role in ['globaladmin', 'superadmin']:
            return True
        if isinstance(request.user, AnonymousUser):
            return False
        if obj is None:
            return True
        return obj.branch == request.user.branch

    def has_change_permission(self, request, obj=None):
        if request.user.is_superuser or request.user.role in ['globaladmin', 'superadmin']:
            return True
        if isinstance(request.user, AnonymousUser):
            return False
        if obj is None:
            return True
        return obj.branch == request.user.branch

    def has_delete_permission(self, request, obj=None):
        if request.user.is_superuser or request.user.role in ['globaladmin', 'superadmin']:
            return True
        if isinstance(request.user, AnonymousUser):
            return False
        if obj is None:
            return True
        return obj.branch == request.user.branch

    def has_add_permission(self, request):
        if isinstance(request.user, AnonymousUser):
            return False
        return request.user.is_superuser or request.user.role in ['superadmin', 'admin']


@admin.register(UserQuizAssignment)
class UserQuizAssignmentAdmin(admin.ModelAdmin):
    list_display = ['user', 'quiz', 'assignment_type', 'item_name', 'assigned_by', 'assigned_at', 'is_active']
    list_filter = ['assignment_type', 'is_active', 'assigned_at', 'user__branch']
    search_fields = ['user__username', 'user__email', 'quiz__title', 'item_name', 'assigned_by__username']
    ordering = ['-assigned_at']
    readonly_fields = ['assigned_at']
    
    fieldsets = (
        ('Assignment Details', {
            'fields': ('user', 'quiz', 'assignment_type', 'item_name')
        }),
        ('Assignment Info', {
            'fields': ('assigned_by', 'assigned_at', 'is_active', 'notes')
        }),
    )
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser or request.user.role in ['globaladmin', 'superadmin']:
            return qs
        if isinstance(request.user, AnonymousUser):
            return qs.none()
        # Filter to show only assignments for users in the same branch
        return qs.filter(user__branch=request.user.branch)
    
    def save_model(self, request, obj, form, change):
        if not change:  # Only set assigned_by on creation
            obj.assigned_by = request.user
        super().save_model(request, obj, form, change)
    
    def has_view_permission(self, request, obj=None):
        if request.user.is_superuser or request.user.role in ['globaladmin', 'superadmin']:
            return True
        if isinstance(request.user, AnonymousUser):
            return False
        if obj is None:
            return True
        return obj.user.branch == request.user.branch
    
    def has_change_permission(self, request, obj=None):
        if request.user.is_superuser or request.user.role in ['globaladmin', 'superadmin']:
            return True
        if isinstance(request.user, AnonymousUser):
            return False
        if obj is None:
            return True
        return obj.user.branch == request.user.branch and request.user.role in ['admin', 'instructor']
    
    def has_delete_permission(self, request, obj=None):
        if request.user.is_superuser or request.user.role in ['globaladmin', 'superadmin']:
            return True
        if isinstance(request.user, AnonymousUser):
            return False
        if obj is None:
            return True
        return obj.user.branch == request.user.branch and request.user.role in ['admin', 'instructor']
    
    def has_add_permission(self, request):
        if isinstance(request.user, AnonymousUser):
            return False
        return request.user.is_superuser or request.user.role in ['superadmin', 'admin', 'instructor']
