from django import forms
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from .models import Course, Topic, CourseCategory, Section
from core.utils.forms import BaseModelFormWithTinyMCE
from tinymce_editor.widgets import TinyMCEWidget
import logging
from django.db.models import Q
from django.utils import timezone
from django.core.exceptions import ValidationError
from quiz.models import Quiz
from assignments.models import Assignment
from conferences.models import Conference
from discussions.models import Discussion
# CourseTopic will be imported dynamically to avoid circular import
# from courses.models import CourseTopic  
from branches.models import Branch
from groups.models import BranchGroup
import os
import json
from bs4 import BeautifulSoup
import zipfile
from django.conf import settings
from django.core.files.uploadedfile import InMemoryUploadedFile
from typing import Any, Dict, List, Optional, Union, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from django.db.models import QuerySet

CustomUser = get_user_model()
logger = logging.getLogger(__name__)

class CourseForm(BaseModelFormWithTinyMCE):
    course_status = forms.ChoiceField(
        choices=[
            ('published', 'Published'),
            ('draft', 'Draft')
        ],
        widget=forms.RadioSelect(attrs={
            'class': 'form-radio h-4 w-4 text-blue-600 inline-block mr-2',
            'style': 'margin-right: 8px;'
        })
    )
    # Make branch and instructor explicitly optional in the form
    branch = forms.ModelChoiceField(
        queryset=None, 
        required=False,
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-2 bg-gray-700 text-white rounded border border-gray-600 focus:border-blue-500 focus:ring-1 focus:ring-blue-500'
        })
    )
    instructor = forms.ModelChoiceField(
        queryset=None, 
        required=False,
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-2 bg-gray-700 text-white rounded border border-gray-600 focus:border-blue-500 focus:ring-1 focus:ring-blue-500'
        })
    )

    class Meta:
        model = Course
        fields = [
            'title',
            'short_description',
            'description',
            'course_code',
            'course_outcomes',
            'course_rubrics',
            'branch',
            'instructor',
            'is_active',
            'course_image',
            'course_video',
            'category',
            'accessible_groups',
            'enforce_sequence',
            # Course Settings
            'language',
            'visibility',
            'schedule_type',
            'require_enrollment',
            'sequential_progression',
            'all_topics_complete',
            'minimum_score',
            'certificate_type',
            # Course Availability Settings
            'catalog_visibility',
            'public_enrollment',
            'enrollment_capacity',
            'require_enrollment_approval',
            # Course Schedule and Access Rules
            'start_date',
            'end_date',
            'time_limit_days',
            'retain_access_after_completion',
            'prerequisites',
            # Course Completion Settings
            'completion_percentage',
            'passing_score',
            'certificate_enabled',
            # Course Pricing
            'price',
            'coupon_code',
            'discount_percentage',
        ]
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 bg-gray-700 text-white rounded border border-gray-600 focus:border-blue-500 focus:ring-1 focus:ring-blue-500',
                'placeholder': 'Enter course title',
                'required': 'required'
            }),
            'short_description': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 bg-gray-700 text-white rounded border border-gray-600 focus:border-blue-500 focus:ring-1 focus:ring-blue-500',
                'placeholder': 'Enter a brief description for course cards (recommended: 2-3 sentences)',
                'rows': 3
            }),
            'description': TinyMCEWidget(attrs={
                'class': 'tinymce-editor w-full bg-white',
                'id': 'course_description',
                'data-no-html-display': 'true',
                'data-custom-footer': 'true',
                'style': 'background-color: white !important;',
                'required': 'required'
            }, config={
                'height': 300,
                'menubar': 'edit view insert format tools table',
                'skin': 'oxide',
                'content_css': False,
                'body_class': 'white-bg',
                'plugins': 'advlist autolink link image lists charmap preview anchor searchreplace visualblocks code fullscreen insertdatetime media table wordcount help aiwriter toolbarfix',
                'toolbar': 'formatselect bold italic underline strikethrough | forecolor backcolor | alignleft aligncenter alignright alignjustify | bullist numlist outdent indent | removeformat | link image media table | code fullscreen help aiwriter',
                'toolbar_mode': 'sliding',
                'toolbar_sticky': True,
                'toolbar_location': 'top',
                'branding': False,
                'promotion': False,
                'statusbar': True,
                'resize': 'both',
                'elementpath': True,
                'content_style': 'body { font-family:Helvetica,Arial,sans-serif; font-size:14px; background-color: white !important; color: #333 !important; }',
                'placeholder': 'Enter course description',
                'custom_footer': True,
                'image_advtab': True,
                'image_uploadtab': True,
                'images_upload_url': '/tinymce/upload_image/',
                'automatic_uploads': True,
                'file_picker_types': 'image media',
                'media_upload_url': '/tinymce/upload_media_file/',
                'media_live_embeds': True,
                'media_filter_html': False,
                'paste_data_images': True,
                'images_upload_handler': None,  # Will be set via JavaScript
                'media_upload_handler': None,  # Will be set via JavaScript
                'convert_urls': False,
                'relative_urls': False,
            }),
            'course_code': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 bg-gray-700 text-white rounded border border-gray-600 focus:border-blue-500 focus:ring-1 focus:ring-blue-500'
            }),
            'branch': forms.Select(attrs={
                'class': 'w-full px-4 py-2 bg-gray-700 text-white rounded border border-gray-600 focus:border-blue-500 focus:ring-1 focus:ring-blue-500'
            }),
            'instructor': forms.Select(attrs={
                'class': 'w-full px-4 py-2 bg-gray-700 text-white rounded border border-gray-600 focus:border-blue-500 focus:ring-1 focus:ring-blue-500'
            }),
            'is_active': forms.HiddenInput(),  # Hide the original is_active field
            'course_image': forms.FileInput(attrs={
                'class': 'hidden',
                'accept': 'image/jpeg,image/jpg,image/png',
                'data-help-text': 'Allowed formats: JPG, PNG, JPEG • Maximum size: 10MB'
            }),
            'course_video': forms.FileInput(attrs={
                'class': 'hidden',
                'accept': 'video/mp4,video/webm',
                'data-help-text': 'Allowed formats: MP4, WEBM only • Maximum size: 500MB'
            }),
            'category': forms.Select(attrs={
                'class': 'w-full px-4 py-2 bg-gray-700 text-white rounded border border-gray-600 focus:border-blue-500 focus:ring-1 focus:ring-blue-500'
            }),
            'accessible_groups': forms.SelectMultiple(attrs={
                'class': 'w-full px-4 py-2 bg-gray-700 text-white rounded border border-gray-600 focus:border-blue-500 focus:ring-1 focus:ring-blue-500',
                'size': '5'
            }),
            'enforce_sequence': forms.CheckboxInput(attrs={
                'class': 'form-checkbox h-4 w-4 text-blue-500 border-gray-600 rounded focus:ring-blue-500 bg-gray-700'
            }),
            # Course Settings
            'language': forms.Select(attrs={
                'class': 'w-full px-4 py-2 bg-gray-700 text-white rounded border border-gray-600 focus:border-blue-500 focus:ring-1 focus:ring-blue-500'
            }),
            'visibility': forms.Select(attrs={
                'class': 'w-full px-4 py-2 bg-gray-700 text-white rounded border border-gray-600 focus:border-blue-500 focus:ring-1 focus:ring-blue-500'
            }),
            'schedule_type': forms.Select(attrs={
                'class': 'w-full px-4 py-2 bg-gray-700 text-white rounded border border-gray-600 focus:border-blue-500 focus:ring-1 focus:ring-blue-500'
            }),
            'require_enrollment': forms.CheckboxInput(attrs={
                'class': 'form-checkbox h-4 w-4 text-blue-500 border-gray-600 rounded focus:ring-blue-500 bg-gray-700'
            }),
            'sequential_progression': forms.CheckboxInput(attrs={
                'class': 'form-checkbox h-4 w-4 text-blue-500 border-gray-600 rounded focus:ring-blue-500 bg-gray-700'
            }),
            'all_topics_complete': forms.CheckboxInput(attrs={
                'class': 'form-checkbox h-4 w-4 text-blue-500 border-gray-600 rounded focus:ring-blue-500 bg-gray-700'
            }),
            'minimum_score': forms.CheckboxInput(attrs={
                'class': 'form-checkbox h-4 w-4 text-blue-500 border-gray-600 rounded focus:ring-blue-500 bg-gray-700'
            }),
            'certificate_type': forms.Select(attrs={
                'class': 'w-full px-4 py-2 bg-gray-700 text-white rounded border border-gray-600 focus:border-blue-500 focus:ring-1 focus:ring-blue-500'
            }),
            # Course Availability Settings
            'catalog_visibility': forms.Select(attrs={
                'class': 'w-full px-4 py-2 bg-gray-700 text-white rounded border border-gray-600 focus:border-blue-500 focus:ring-1 focus:ring-blue-500'
            }),
            'public_enrollment': forms.CheckboxInput(attrs={
                'class': 'form-checkbox h-4 w-4 text-blue-500 border-gray-600 rounded focus:ring-blue-500 bg-gray-700'
            }),
            'enrollment_capacity': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 bg-gray-700 text-white rounded border border-gray-600 focus:border-blue-500 focus:ring-1 focus:ring-blue-500',
                'min': '1'
            }),
            'require_enrollment_approval': forms.CheckboxInput(attrs={
                'class': 'form-checkbox h-4 w-4 text-blue-500 border-gray-600 rounded focus:ring-blue-500 bg-gray-700'
            }),
            # Course Schedule and Access Rules
            'start_date': forms.DateTimeInput(attrs={
                'class': 'w-full px-4 py-2 bg-gray-700 text-white rounded border border-gray-600 focus:border-blue-500 focus:ring-1 focus:ring-blue-500',
                'type': 'datetime-local'
            }),
            'end_date': forms.DateTimeInput(attrs={
                'class': 'w-full px-4 py-2 bg-gray-700 text-white rounded border border-gray-600 focus:border-blue-500 focus:ring-1 focus:ring-blue-500',
                'type': 'datetime-local'
            }),
            'time_limit_days': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 bg-gray-700 text-white rounded border border-gray-600 focus:border-blue-500 focus:ring-1 focus:ring-blue-500',
                'min': '1'
            }),
            'retain_access_after_completion': forms.CheckboxInput(attrs={
                'class': 'form-checkbox h-4 w-4 text-blue-500 border-gray-600 rounded focus:ring-blue-500 bg-gray-700'
            }),
            'prerequisites': forms.SelectMultiple(attrs={
                'class': 'w-full px-4 py-2 bg-gray-700 text-white rounded border border-gray-600 focus:border-blue-500 focus:ring-1 focus:ring-blue-500',
                'size': '5'
            }),
            # Course Completion Settings
            'completion_percentage': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 bg-gray-700 text-white rounded border border-gray-600 focus:border-blue-500 focus:ring-1 focus:ring-blue-500',
                'min': '0',
                'max': '100'
            }),
            'passing_score': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 bg-gray-700 text-white rounded border border-gray-600 focus:border-blue-500 focus:ring-1 focus:ring-blue-500',
                'min': '0',
                'max': '100'
            }),
            'certificate_enabled': forms.CheckboxInput(attrs={
                'class': 'form-checkbox h-4 w-4 text-blue-500 border-gray-600 rounded focus:ring-blue-500 bg-gray-700'
            }),
            # Course Pricing
            'price': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 bg-gray-700 text-white rounded border border-gray-600 focus:border-blue-500 focus:ring-1 focus:ring-blue-500',
                'min': '0',
                'step': '0.01'
            }),
            'coupon_code': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 bg-gray-700 text-white rounded border border-gray-600 focus:border-blue-500 focus:ring-1 focus:ring-blue-500'
            }),
            'discount_percentage': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 bg-gray-700 text-white rounded border border-gray-600 focus:border-blue-500 focus:ring-1 focus:ring-blue-500',
                'min': '0',
                'max': '100'
            }),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        user: Optional[CustomUser] = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Store user for access in clean method
        self.user = user
        
        # Add debug logging
        logger.info(f"Initializing CourseForm for user: {user.username if user else 'None'}")
        logger.info(f"User is_superuser: {user.is_superuser if user else 'None'}")
        logger.info(f"User role: {user.role if user else 'None'}")
        
        # Debug instance data
        if self.instance and self.instance.pk:
            logger.info(f"Form instance ID: {self.instance.pk}")
            logger.info(f"Form instance category_id: {self.instance.category_id}")
            
                    # Note: course_outcomes and course_rubrics are now simple TextFields
            
            # No special handling needed for description field anymore
            
            # Ensure category is in initial data if present on instance
            if self.instance.category_id:
                self.initial['category'] = self.instance.category_id
                self.fields['category'].initial = self.instance.category_id
                logger.info(f"Setting initial category to: {self.instance.category_id}")
        
        # Set querysets based on user/role
        if user:
            if user.is_superuser or user.role in ['globaladmin', 'superadmin']:
                # Superuser/superadmin can see all users with instructor role
                self.fields['instructor'].queryset = CustomUser.objects.filter(role='instructor').order_by('first_name', 'last_name')
                # Superuser/superadmin can see all branches
                self.fields['branch'].queryset = Branch.objects.all().order_by('name')
                self.fields['branch'].empty_label = "Select Branch"
            elif user.role == 'admin':
                # Admin can only see instructors in their branch
                self.fields['instructor'].queryset = CustomUser.objects.filter(
                    role='instructor', 
                    branch=user.branch
                ).order_by('first_name', 'last_name')
                # Admin can only see their branch
                self.fields['branch'].queryset = Branch.objects.filter(id=user.branch.id)
                self.fields['branch'].initial = user.branch
                self.fields['branch'].empty_label = None  # No empty choice
            else:
                # Instructor or other role can only see themselves
                self.fields['instructor'].queryset = CustomUser.objects.filter(id=user.id)
                self.fields['instructor'].initial = user
                self.fields['instructor'].empty_label = None  # No empty choice
                # And can only see their branch
                if user.branch:
                    self.fields['branch'].queryset = Branch.objects.filter(id=user.branch.id)
                    self.fields['branch'].initial = user.branch
                    self.fields['branch'].empty_label = None  # No empty choice
                else:
                    self.fields['branch'].queryset = Branch.objects.none()
        else:
            # No user provided, use all instructors and branches (fallback)
            self.fields['instructor'].queryset = CustomUser.objects.filter(role='instructor').order_by('first_name', 'last_name')
            self.fields['branch'].queryset = Branch.objects.all().order_by('name')
        
        # For Course creation handling (no instance)
        if not self.instance or not self.instance.pk:
            # For a new course, set defaults based on user
            if user:
                if user.role == 'instructor':
                    # Set instructor to current user for instructor role
                    self.fields['instructor'].initial = user
                    self.fields['branch'].initial = user.branch
                elif user.role == 'admin':
                    # Set branch to admin's branch
                    self.fields['branch'].initial = user.branch
        
        # Filter accessible_groups based on branch to avoid validation errors
        if self.instance and self.instance.pk and self.instance.branch:
            # Filter accessible_groups to only show groups from the same branch as the course
            self.fields['accessible_groups'].queryset = BranchGroup.objects.filter(
                branch=self.instance.branch
            ).order_by('name')
        elif user and user.branch:
            # For new courses, filter by user's branch
            self.fields['accessible_groups'].queryset = BranchGroup.objects.filter(
                branch=user.branch
            ).order_by('name')
        
        # Handle pricing fields based on order management settings
        self._configure_pricing_fields()
        
        # Make new fields not required since they have model defaults
        self.fields['course_code'].required = False
        self.fields['course_video'].required = False
        self.fields['enrollment_capacity'].required = False
        self.fields['completion_percentage'].required = False
        self.fields['passing_score'].required = False
        self.fields['language'].required = False
        self.fields['visibility'].required = False
        self.fields['schedule_type'].required = False
        self.fields['certificate_type'].required = False
        self.fields['catalog_visibility'].required = False
        self.fields['public_enrollment'].required = False
        self.fields['retain_access_after_completion'].required = False
        self.fields['require_enrollment_approval'].required = False
        
        # Make branch optional for super admin users (they operate at business level)
        if user and user.role == 'superadmin':
            self.fields['branch'].required = False
        
        # Set initial course status based on is_active
        if self.instance and self.instance.pk:
            self.initial['course_status'] = 'published' if self.instance.is_active else 'draft'
            
            # Unescape HTML entities in TinyMCE fields for proper editor display
            import html
            tinymce_fields = ['description', 'course_outcomes', 'course_rubrics']
            
            for field_name in tinymce_fields:
                if hasattr(self.instance, field_name):
                    field_value = getattr(self.instance, field_name)
                    if field_value and isinstance(field_value, str):
                        # Check if content contains any HTML entities
                        if ('&lt;' in field_value or '&gt;' in field_value or '&amp;' in field_value or 
                            '&quot;' in field_value or '&#x27;' in field_value or '&#' in field_value):
                            # Unescape HTML entities for proper display in TinyMCE editor
                            unescaped_value = html.unescape(field_value)
                            self.initial[field_name] = unescaped_value
                            logger.info(f"Unescaped HTML entities in field '{field_name}' for course {self.instance.pk}")
        
        # Set initial values for fields with model defaults
        if not self.initial.get('catalog_visibility'):
            self.initial['catalog_visibility'] = 'visible'
        if not self.initial.get('public_enrollment'):
            self.initial['public_enrollment'] = True
        if not self.initial.get('retain_access_after_completion'):
            self.initial['retain_access_after_completion'] = True
        if not self.initial.get('completion_percentage'):
            self.initial['completion_percentage'] = 100
        if not self.initial.get('passing_score'):
            self.initial['passing_score'] = 70
        if not self.initial.get('language'):
            self.initial['language'] = 'en'
        if not self.initial.get('visibility'):
            self.initial['visibility'] = 'public'
        if not self.initial.get('schedule_type'):
            self.initial['schedule_type'] = 'self_paced'
        if not self.initial.get('require_enrollment'):
            self.initial['require_enrollment'] = True
        if not self.initial.get('sequential_progression'):
            self.initial['sequential_progression'] = False
        if not self.initial.get('all_topics_complete'):
            self.initial['all_topics_complete'] = False
        if not self.initial.get('minimum_score'):
            self.initial['minimum_score'] = False
        if not self.initial.get('certificate_type'):
            self.initial['certificate_type'] = 'standard'
        
        # Handle category field with role-based filtering
        if user:
            self.fields['category'].queryset = self.get_user_accessible_categories(user)
        else:
            self.fields['category'].queryset = CourseCategory.objects.filter(is_active=True).order_by('name')
        self.fields['category'].empty_label = "Select Category"
        logger.info(f"Category queryset: {list(self.fields['category'].queryset.values('id', 'name'))}")
        
        # Ensure the instance's category is in the initial data
        if self.instance and self.instance.pk and self.instance.category_id:
            logger.info(f"Setting initial category ID to: {self.instance.category_id}")
            # Make sure form recognizes the category value
            self.initial['category'] = self.instance.category_id
            
            # Explicitly set the field's initial value
            self.fields['category'].initial = self.instance.category_id
            
            # Make sure the category is in the queryset
            if not self.fields['category'].queryset.filter(id=self.instance.category_id).exists():
                category = CourseCategory.objects.filter(id=self.instance.category_id).first()
                if category:
                    self.fields['category'].queryset = self.fields['category'].queryset | CourseCategory.objects.filter(id=self.instance.category_id)
                    logger.info(f"Added category {self.instance.category_id} to queryset")
        
        # Handle user-specific logic
        if user:
            if user.role == 'instructor':
                # For instructors, remove branch and instructor fields
                logger.info("Removing branch and instructor fields for instructor user")
                if 'branch' in self.fields:
                    del self.fields['branch']
                if 'instructor' in self.fields:
                    del self.fields['instructor']
            elif user.role == 'admin':
                # For admin, limit branch to their own branch
                if 'branch' in self.fields:
                    self.fields['branch'].queryset = Branch.objects.filter(id=user.branch.id)
                    self.fields['branch'].initial = user.branch
                    self.fields['branch'].disabled = True
                # Limit instructors to those in their branch
                if 'instructor' in self.fields:
                    self.fields['instructor'].queryset = CustomUser.objects.filter(
                        role='instructor',
                        branch=user.branch
                    ).order_by('username')
                    self.fields['instructor'].empty_label = "Select Instructor"
    
    def _configure_pricing_fields(self):
        """Configure pricing fields based on order management settings"""
        order_management_enabled = False
        
        try:
            from account_settings.models import GlobalAdminSettings
            
            # Check global order management setting
            global_settings = GlobalAdminSettings.get_settings()
            global_order_enabled = global_settings.order_management_enabled if global_settings else False
            
            # Check branch-level order management setting
            branch_order_enabled = False
            course_branch = None
            
            if self.instance and self.instance.pk and self.instance.branch:
                # For existing course, use its branch
                course_branch = self.instance.branch
            elif self.user and self.user.branch:
                # For new course, use user's branch
                course_branch = self.user.branch
            
            if course_branch:
                branch_order_enabled = getattr(course_branch, 'order_management_enabled', False)
            
            # Order management is enabled only if both global and branch settings are enabled
            order_management_enabled = global_order_enabled and branch_order_enabled
            
        except Exception as e:
            logger.error(f"Error checking order management settings in form: {str(e)}")
            order_management_enabled = False
        
        # Configure pricing fields based on order management status
        if not order_management_enabled:
            # Make pricing fields not required and set defaults
            self.fields['price'].required = False
            self.fields['discount_percentage'].required = False
            self.fields['coupon_code'].required = False
            
            # Set default values if not already set
            if not self.data.get('price'):
                self.fields['price'].initial = 0.00
            if not self.data.get('discount_percentage'):
                self.fields['discount_percentage'].initial = 0
    
    def clean(self) -> Dict[str, Any]:
        """Custom clean method to handle pricing fields and validation with better error handling"""
        try:
            cleaned_data = super().clean()
            logger.info(f"CourseForm clean method started for user: {self.user.username if self.user else 'Unknown'}")
            
            # Check if order management is enabled for this course/branch
            order_management_enabled = False
            
            try:
                from account_settings.models import GlobalAdminSettings
                
                # Check global order management setting
                global_settings = GlobalAdminSettings.get_settings()
                global_order_enabled = global_settings.order_management_enabled if global_settings else False
                
                # Check branch-level order management setting
                branch_order_enabled = False
                course_branch = None
                
                if self.instance and self.instance.pk and self.instance.branch:
                    # For existing course, use its branch
                    course_branch = self.instance.branch
                elif self.user and self.user.branch:
                    # For new course, use user's branch
                    course_branch = self.user.branch
                elif cleaned_data.get('branch'):
                    # Use branch from form data
                    course_branch = cleaned_data.get('branch')
                
                if course_branch:
                    branch_order_enabled = getattr(course_branch, 'order_management_enabled', False)
                
                # Order management is enabled only if both global and branch settings are enabled
                order_management_enabled = global_order_enabled and branch_order_enabled
                
            except Exception as e:
                logger.error(f"Error checking order management settings in clean method: {str(e)}")
                order_management_enabled = False
            
            # If order management is disabled, set default values for pricing fields
            if not order_management_enabled:
                cleaned_data['price'] = cleaned_data.get('price', 0.00) or 0.00
                cleaned_data['discount_percentage'] = cleaned_data.get('discount_percentage', 0) or 0
                cleaned_data['coupon_code'] = cleaned_data.get('coupon_code', '') or ''
            
            # Ensure catalog_visibility has a default value
            if not cleaned_data.get('catalog_visibility'):
                cleaned_data['catalog_visibility'] = 'visible'
            
            # Ensure other fields have default values if missing
            if not cleaned_data.get('completion_percentage'):
                cleaned_data['completion_percentage'] = 100
            if not cleaned_data.get('passing_score'):
                cleaned_data['passing_score'] = 70
            if not cleaned_data.get('language'):
                cleaned_data['language'] = 'en'
            if not cleaned_data.get('visibility'):
                cleaned_data['visibility'] = 'public'
            if not cleaned_data.get('schedule_type'):
                cleaned_data['schedule_type'] = 'self_paced'
            if not cleaned_data.get('certificate_type'):
                cleaned_data['certificate_type'] = 'standard'
            
            # Ensure boolean fields have default values
            if 'public_enrollment' not in cleaned_data or cleaned_data['public_enrollment'] is None:
                cleaned_data['public_enrollment'] = True
            if 'retain_access_after_completion' not in cleaned_data or cleaned_data['retain_access_after_completion'] is None:
                cleaned_data['retain_access_after_completion'] = True
            if 'require_enrollment_approval' not in cleaned_data or cleaned_data['require_enrollment_approval'] is None:
                cleaned_data['require_enrollment_approval'] = False
            
            # Validate required fields
            if not cleaned_data.get('title', '').strip():
                raise ValidationError({'title': 'Course title is required.'})
            
            logger.info(f"CourseForm clean method completed successfully")
            return cleaned_data
            
        except ValidationError as e:
            logger.error(f"Validation error in CourseForm clean method: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in CourseForm clean method: {str(e)}")
            # Re-raise as a validation error to prevent silent failures
            raise ValidationError(f"Form validation error: {str(e)}")


    def get_user_accessible_categories(self, user):
        """
        Get categories accessible to user based on their role.
        - Global Admin: All categories
        - Super Admin: Categories from branches under their assigned businesses
        - Regular users: Categories from their assigned branch only
        """
        if user.role == 'globaladmin' or user.is_superuser:
            # Global Admin can see all categories
            return CourseCategory.objects.filter(is_active=True).order_by('name')
        
        elif user.role == 'superadmin':
            # Super Admin can see categories from branches under their assigned businesses
            if hasattr(user, 'business_assignments'):
                assigned_businesses = user.business_assignments.filter(is_active=True).values_list('business', flat=True)
                return CourseCategory.objects.filter(
                    is_active=True,
                    branch__business__in=assigned_businesses
                ).order_by('name')
            return CourseCategory.objects.none()
        
        elif user.role in ['admin', 'instructor', 'learner']:
            # Regular users can only see categories from their assigned branch
            if user.branch:
                return CourseCategory.objects.filter(
                    is_active=True,
                    branch=user.branch
                ).order_by('name')
            return CourseCategory.objects.none()
        
        # Default: no categories
        return CourseCategory.objects.none()

    def _clean_html_content(self, html_content):
        """Clean HTML content to remove editor UI elements and potentially unsafe content"""
        if not html_content:
            return html_content
            
        try:
            # Parse the HTML
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Remove potentially harmful elements
            for script in soup.find_all('script'):
                script.decompose()
            
            # Remove iframe elements without whitelisted sources
            for iframe in soup.find_all('iframe'):
                src = iframe.get('src', '')
                # Check if iframe src is from a trusted source (add more as needed)
                trusted_sources = ['youtube.com', 'vimeo.com', 'player.vimeo.com', 'dailymotion.com', 'ted.com']
                is_trusted = any(source in src for source in trusted_sources)
                if not is_trusted:
                    iframe.decompose()
            
            # Remove event handler attributes (on*)
            for tag in soup.find_all(True):
                attrs_to_remove = []
                for attr in tag.attrs:
                    # Remove event handlers (on*)
                    if attr.startswith('on'):
                        attrs_to_remove.append(attr)
                    # Remove javascript: URLs
                    elif attr == 'href' and tag.get(attr, '').startswith('javascript:'):
                        tag['href'] = '#'
                # Remove the collected attributes
                for attr in attrs_to_remove:
                    del tag.attrs[attr]
            
            # Remove editor UI elements
            editor_controls = soup.select('.image-controls, .editor-controls, [data-editor-control], .image-size-controls, .image-selection-info')
            for control in editor_controls:
                control.decompose()
                
            # Remove toolbars and other editor elements - FIXED to exclude editor-table class
            toolbar_elements = soup.select('[class*="toolbar"], [id*="toolbar"]')
            editor_elements = soup.select('[class*="editor-"], [id*="editor-"]')
            
            # Filter out tables with the editor-table class
            for element in editor_elements:
                if not (element.name == 'table' and 'editor-table' in element.get('class', [])):
                    element.decompose()
                    
            for element in toolbar_elements:
                element.decompose()
                
            # Return the cleaned HTML
            return str(soup)
        except Exception as e:
            logger.error(f"Error cleaning HTML content: {str(e)}")
            return html_content

    def clean_start_date(self):
        """Ensure start_date is timezone-aware to avoid naive datetime warnings"""
        start_date = self.cleaned_data.get('start_date')
        if start_date:
            from django.utils import timezone
            if start_date.tzinfo is None:
                # Convert naive datetime to timezone-aware
                start_date = timezone.make_aware(start_date)
        return start_date
    
    def clean_end_date(self):
        """Ensure end_date is timezone-aware to avoid naive datetime warnings"""
        end_date = self.cleaned_data.get('end_date')
        if end_date:
            from django.utils import timezone
            if end_date.tzinfo is None:
                # Convert naive datetime to timezone-aware
                end_date = timezone.make_aware(end_date)
        return end_date

    def save(self, commit: bool = True) -> Course:
        """Custom save to handle various field transformations and additional logic"""
        logger.info(f"CourseForm saving with commit={commit}")
        course = super().save(commit=False)
        
        # Handle description field explicitly to ensure it's saved properly
        description = self.cleaned_data.get('description', '')
        if description:
            # Check if description is JSON (either as string or object)
            try:
                # If it's a JSON string, parse it
                if isinstance(description, str) and description.strip().startswith('{') and description.strip().endswith('}'):
                    try:
                        json_data = json.loads(description)
                        if isinstance(json_data, dict) and 'html' in json_data:
                            # Extract HTML from JSON
                            logger.info(f"Extracting HTML from JSON description")
                            description = json_data['html']
                            if '<table' in description:
                                logger.info("Description contains table elements")
                    except json.JSONDecodeError:
                        # Not valid JSON, keep as is
                        logger.info(f"Description looks like JSON but couldn't be parsed, keeping as is")
                        pass
            except Exception as e:
                logger.error(f"Error processing description: {str(e)}")
            
            # Log before cleaning to debug any issues
            if '<table' in description:
                logger.info("Pre-cleaning: Description contains table elements")
            
            # Clean the description HTML to remove editor UI elements
            description = self._clean_html_content(description)
            
            # Log after cleaning to ensure tables are preserved
            if '<table' in description:
                logger.info("Post-cleaning: Description contains table elements")
            else:
                logger.warning("Table elements may have been removed during cleaning")
            
            # Description should be saved directly as HTML string
            logger.info(f"Setting description directly (length: {len(description)})")
            course.description = description
        
        # Note: course_outcomes and course_rubrics are now simple TextFields
        
        # Handle category field
        category_id = self.cleaned_data.get('category')
        if category_id:
            course.category_id = category_id
            logger.info(f"Setting category_id to: {category_id}")
            
        # Make sure branch and instructor are set correctly
        user = getattr(self, 'user', None)
        
        # Handle branch field if not set
        if not course.branch and user and user.branch:
            logger.info(f"Setting branch from user: {user.branch}")
            course.branch = user.branch
            
        # Handle instructor field if not set
        if not course.instructor and user and user.role == 'instructor':
            logger.info(f"Setting instructor to current user: {user}")
            course.instructor = user
            
        # Log final branch and instructor values
        logger.info(f"Final branch value: {course.branch}")
        logger.info(f"Final instructor value: {course.instructor}")
        
        if commit:
            course.save()
            self.save_m2m()
            
        return course

    def clean_course_image(self):
        """Simple image format validation - only allow JPG, PNG, JPEG"""
        image = self.cleaned_data.get('course_image')
        if image:
            import os
            
            # Get file extension
            file_extension = os.path.splitext(image.name)[1].lower()
            
            # Check if it's an allowed image format
            allowed_formats = ['.jpg', '.jpeg', '.png']
            if file_extension not in allowed_formats:
                raise forms.ValidationError(f"Only JPG, PNG, and JPEG files are allowed. You uploaded: {file_extension}")
            
            # Check file size (max 10MB)
            if image.size > 10 * 1024 * 1024:
                raise forms.ValidationError(f"File size too large. Maximum allowed: 10MB. Your file: {image.size / (1024*1024):.1f}MB")
                
        return image

    def clean_course_video(self):
        """Simple video format validation"""
        video = self.cleaned_data.get('course_video')
        if video:
            import os
            
            # Get file extension
            file_extension = os.path.splitext(video.name)[1].lower()
            
            # Check if it's an allowed video format
            allowed_formats = ['.mp4', '.webm']
            if file_extension not in allowed_formats:
                raise forms.ValidationError(f"Only MP4 and WEBM video files are allowed. You uploaded: {file_extension}")
            
            # Check file size (max 500MB)
            if video.size > 500 * 1024 * 1024:
                raise forms.ValidationError(f"Video file too large. Maximum allowed: 500MB. Your file: {video.size / (1024*1024):.1f}MB")
                
        return video

class DisabledOptionWidget(forms.Select):
    """Custom widget that can disable specific options and show which topic they're linked to"""
    def __init__(self, disabled_choices=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.disabled_choices = disabled_choices or []
        self.linked_to_topics = {}
    
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        
        # If this choice is linked to another topic, update the label and disable it
        if value in self.disabled_choices:
            option['attrs']['disabled'] = 'disabled'
            option['attrs']['style'] = 'color: #9CA3AF; background-color: #F3F4F6;'
            
            # Add topic name to label if available
            if hasattr(self, 'linked_to_topics') and value in self.linked_to_topics:
                topic_name = self.linked_to_topics[value]
                # Truncate topic name if too long
                if len(topic_name) > 30:
                    topic_name = topic_name[:27] + '...'
                option['label'] = f"{label} [Used in: {topic_name}]"
        
        return option

class TopicForm(BaseModelFormWithTinyMCE):
    quiz = forms.ModelChoiceField(
        queryset=Quiz.objects.all(),
        required=False,
        widget=DisabledOptionWidget(attrs={
            'class': 'w-full px-4 py-2 bg-gray-700 text-white rounded border border-gray-600 focus:border-blue-500 focus:ring-1 focus:ring-blue-500'
        })
    )
    assignment = forms.ModelChoiceField(
        queryset=Assignment.objects.all(),
        required=False,
        widget=DisabledOptionWidget(attrs={
            'class': 'w-full px-4 py-2 bg-gray-700 text-white rounded border border-gray-600 focus:border-blue-500 focus:ring-1 focus:ring-blue-500'
        })
    )
    conference = forms.ModelChoiceField(
        queryset=Conference.objects.all(),
        required=False,
        widget=DisabledOptionWidget(attrs={
            'class': 'w-full px-4 py-2 bg-gray-700 text-white rounded border border-gray-600 focus:border-blue-500 focus:ring-1 focus:ring-blue-500'
        })
    )
    discussion = forms.ModelChoiceField(
        queryset=Discussion.objects.all(),
        required=False,
        widget=DisabledOptionWidget(attrs={
            'class': 'w-full px-4 py-2 bg-gray-700 text-white rounded border border-gray-600 focus:border-blue-500 focus:ring-1 focus:ring-blue-500'
        })
    )
    order = forms.IntegerField(
        initial=0,
        widget=forms.HiddenInput(),
        required=False
    )
    
    def __init__(self, *args, course=None, filtered_content=None, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Store course instance for validation
        self.course = course
        
        # Set required fields
        self.fields['title'].required = True
        self.fields['content_type'].required = True
        self.fields['status'].required = True
        self.fields['status'].initial = 'draft'
        self.fields['order'].initial = 0
        
        # Unescape HTML entities in TinyMCE fields when initializing with an instance
        if hasattr(self, 'instance') and self.instance and self.instance.pk:
            import html
            
            # List of TinyMCE fields that might have escaped HTML
            tinymce_fields = ['description', 'text_content', 'instructions']
            
            for field_name in tinymce_fields:
                if hasattr(self.instance, field_name):
                    field_value = getattr(self.instance, field_name)
                    if field_value and isinstance(field_value, str):
                        # Check if content contains any HTML entities
                        if ('&lt;' in field_value or '&gt;' in field_value or '&amp;' in field_value or 
                            '&quot;' in field_value or '&#x27;' in field_value or '&#' in field_value):
                            # Unescape HTML entities for proper display in TinyMCE editor
                            unescaped_value = html.unescape(field_value)
                            self.initial[field_name] = unescaped_value
                            logger.info(f"Unescaped HTML entities in field '{field_name}' for topic {self.instance.pk}")
        
        # Find which quizzes, assignments, conferences, discussions are already linked to topics
        # Exclude the current topic if editing
        current_topic_id = self.instance.pk if self.instance and self.instance.pk else None
        
        # Get IDs of items already linked to OTHER topics
        linked_quizzes = list(Topic.objects.filter(
            quiz__isnull=False,
            content_type='Quiz'
        ).exclude(pk=current_topic_id).values_list('quiz_id', flat=True))
        
        linked_assignments = list(Topic.objects.filter(
            assignment__isnull=False,
            content_type='Assignment'
        ).exclude(pk=current_topic_id).values_list('assignment_id', flat=True))
        
        linked_conferences = list(Topic.objects.filter(
            conference__isnull=False,
            content_type='Conference'
        ).exclude(pk=current_topic_id).values_list('conference_id', flat=True))
        
        linked_discussions = list(Topic.objects.filter(
            discussion__isnull=False,
            content_type='Discussion'
        ).exclude(pk=current_topic_id).values_list('discussion_id', flat=True))
        
        if course:
            if filtered_content:
                # Use properly filtered content based on user role and permissions
                self.fields['quiz'].queryset = filtered_content['quizzes']
                self.fields['assignment'].queryset = filtered_content['assignments']
                self.fields['conference'].queryset = filtered_content['conferences']
                self.fields['discussion'].queryset = filtered_content['discussions']
            else:
                # Set quiz queryset
                self.fields['quiz'].queryset = Quiz.objects.filter(
                    Q(course=course) | Q(course__isnull=True)
                ).order_by('title')
                self.fields['assignment'].queryset = Assignment.objects.filter(
                    Q(course=course) | Q(course__isnull=True)
                ).order_by('title')
                self.fields['conference'].queryset = Conference.objects.filter(
                    Q(course=course) | Q(course__isnull=True)
                ).order_by('title')
                self.fields['discussion'].queryset = Discussion.objects.filter(
                    Q(course=course) | Q(course__isnull=True)
                ).order_by('title')
            
            # Filter restricted learners to only show enrolled learners
            enrolled_learners = course.enrolled_users.filter(role='learner')
            self.fields['restricted_learners'].queryset = enrolled_learners
        
        # Set disabled choices for the widgets to show already-linked items as disabled
        self.fields['quiz'].widget.disabled_choices = linked_quizzes
        self.fields['assignment'].widget.disabled_choices = linked_assignments
        self.fields['conference'].widget.disabled_choices = linked_conferences
        self.fields['discussion'].widget.disabled_choices = linked_discussions
        
        # Update choice labels to show which topic they're linked to
        self._update_choice_labels_with_linked_info()

    def _update_choice_labels_with_linked_info(self):
        """Update choice labels to show which items are already linked to topics"""
        current_topic_id = self.instance.pk if self.instance and self.instance.pk else None
        
        # Update quiz labels
        quiz_topics = {}
        for topic in Topic.objects.filter(quiz__isnull=False, content_type='Quiz').exclude(pk=current_topic_id).select_related('quiz'):
            if topic.quiz_id:
                quiz_topics[topic.quiz_id] = topic.title
        
        # Update assignment labels
        assignment_topics = {}
        for topic in Topic.objects.filter(assignment__isnull=False, content_type='Assignment').exclude(pk=current_topic_id).select_related('assignment'):
            if topic.assignment_id:
                assignment_topics[topic.assignment_id] = topic.title
        
        # Update conference labels
        conference_topics = {}
        for topic in Topic.objects.filter(conference__isnull=False, content_type='Conference').exclude(pk=current_topic_id).select_related('conference'):
            if topic.conference_id:
                conference_topics[topic.conference_id] = topic.title
        
        # Update discussion labels
        discussion_topics = {}
        for topic in Topic.objects.filter(discussion__isnull=False, content_type='Discussion').exclude(pk=current_topic_id).select_related('discussion'):
            if topic.discussion_id:
                discussion_topics[topic.discussion_id] = topic.title
        
        # Store these mappings for use in the widget
        self.fields['quiz'].widget.linked_to_topics = quiz_topics
        self.fields['assignment'].widget.linked_to_topics = assignment_topics
        self.fields['conference'].widget.linked_to_topics = conference_topics
        self.fields['discussion'].widget.linked_to_topics = discussion_topics

    class Meta:
        model = Topic
        fields = [
            'title', 
            'description', 
            'instructions',
            'content_type', 
            'content_file', 
            'text_content',
            'web_url',
            'embed_code',
            'order',
            'status',
            'restrict_to_learners',
            'restricted_learners'
        ]
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 bg-gray-700 text-white rounded border border-gray-600 focus:border-blue-500 focus:ring-1 focus:ring-blue-500',
                'placeholder': 'Enter topic title'
            }),
            'description': TinyMCEWidget(attrs={
                'class': 'tinymce-fixed-editor',
                'id': 'topic_description',
                'data-no-html-display': 'true',
                'data-custom-footer': 'true'  # Enable custom footer with word/character count
            }, config={
                'height': 300,
                'menubar': 'edit view insert format tools table',
                'skin': 'oxide',
                'plugins': 'advlist autolink link image lists charmap preview anchor searchreplace visualblocks code fullscreen insertdatetime media table wordcount help aiwriter toolbarfix',
                'toolbar': 'formatselect bold italic underline strikethrough | forecolor backcolor | alignleft aligncenter alignright alignjustify | bullist numlist outdent indent | removeformat | link image media table | code fullscreen help aiwriter',
                'toolbar_mode': 'sliding',
                'toolbar_sticky': True,
                'toolbar_location': 'top',
                'branding': False,
                'promotion': False,
                'statusbar': True,  # Enable statusbar for the footer
                'resize': 'both',
                'elementpath': True,
                'content_style': '''
                body { 
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
                    font-size: 14px;
                    line-height: 1.6;
                    color: #4b5563;
                    max-width: none;
                }
                h1 { 
                    font-size: 2.25rem; 
                    font-weight: 800; 
                    line-height: 1.1; 
                    margin: 0 0 1rem 0; 
                    color: #111827; 
                }
                h2 { 
                    font-size: 1.875rem; 
                    font-weight: 700; 
                    line-height: 1.2; 
                    margin: 2rem 0 1rem 0; 
                    color: #111827; 
                }
                h3 { 
                    font-size: 1.5rem; 
                    font-weight: 600; 
                    line-height: 1.3; 
                    margin: 1.75rem 0 0.75rem 0; 
                    color: #111827; 
                }
                h4 { 
                    font-size: 1.25rem; 
                    font-weight: 600; 
                    line-height: 1.4; 
                    margin: 1.5rem 0 0.5rem 0; 
                    color: #111827; 
                }
                h5 { 
                    font-size: 1.125rem; 
                    font-weight: 600; 
                    line-height: 1.5; 
                    margin: 1.25rem 0 0.5rem 0; 
                    color: #111827; 
                }
                h6 { 
                    font-size: 1rem; 
                    font-weight: 600; 
                    line-height: 1.5; 
                    margin: 1rem 0 0.5rem 0; 
                    color: #111827; 
                }
                p { 
                    margin: 0 0 1rem 0; 
                    color: #4b5563; 
                }
                strong { 
                    font-weight: 600; 
                    color: #111827; 
                }
                em { 
                    font-style: italic; 
                }
                ul, ol { 
                    margin: 0 0 1rem 0; 
                    padding-left: 1.5rem; 
                }
                li { 
                    margin: 0.25rem 0; 
                }
                blockquote { 
                    border-left: 4px solid #e5e7eb; 
                    padding-left: 1rem; 
                    margin: 1.5rem 0; 
                    font-style: italic; 
                    color: #6b7280; 
                }
                code { 
                    background-color: #f3f4f6; 
                    padding: 0.125rem 0.25rem; 
                    border-radius: 0.25rem; 
                    font-family: ui-monospace, SFMono-Regular, "SF Mono", Monaco, Consolas, "Liberation Mono", "Courier New", monospace; 
                    font-size: 0.875rem; 
                    color: #dc2626; 
                }
                a { 
                    color: #2563eb; 
                    text-decoration: underline; 
                }
                a:hover { 
                    color: #1d4ed8; 
                }
                ''',
                'placeholder': 'Enter a description of this topic',
                'custom_footer': True  # Enable custom footer in config
            }),
            'instructions': TinyMCEWidget(attrs={
                'class': 'tinymce-editor',
                'id': 'topic_instructions',
                'data-no-html-display': 'true'
            }, config={
                'height': 450,
                'menubar': 'edit view insert format tools table',
                'skin': 'oxide',
                'plugins': 'advlist autolink link image lists charmap preview anchor searchreplace visualblocks code fullscreen insertdatetime media table wordcount help aiwriter toolbarfix',
                'toolbar': 'formatselect bold italic underline strikethrough | forecolor backcolor | alignleft aligncenter alignright alignjustify | bullist numlist outdent indent | removeformat | link image media table | code fullscreen help aiwriter',
                'toolbar_mode': 'sliding',
                'toolbar_sticky': True,
                'toolbar_location': 'top',
                'branding': False,
                'promotion': False,
                'statusbar': True,
                'resize': 'both',
                'elementpath': True,
                'content_style': 'body { font-family:Helvetica,Arial,sans-serif; font-size:14px }',
                'placeholder': 'Enter instructions for completing this topic'
            }),
            'text_content': TinyMCEWidget(attrs={
                'class': 'tinymce-editor',
                'id': 'text_content',
                'data-no-html-display': 'true',
                'style': 'min-height: 450px; height: 450px;'
            }, config={
                'height': 450,
                'min_height': 450,
                'menubar': 'edit view insert format tools table',
                'skin': 'oxide',
                'plugins': 'advlist autolink link image lists charmap preview anchor searchreplace visualblocks code fullscreen insertdatetime media table wordcount help aiwriter toolbarfix',
                'toolbar': 'formatselect bold italic underline strikethrough | forecolor backcolor | alignleft aligncenter alignright alignjustify | bullist numlist outdent indent | removeformat | link image media table | code fullscreen help aiwriter',
                'toolbar_mode': 'sliding',
                'toolbar_sticky': True,
                'toolbar_location': 'top',
                'branding': False,
                'promotion': False,
                'statusbar': True,
                'resize': 'both',
                'elementpath': True,
                'content_style': 'body { font-family:Helvetica,Arial,sans-serif; font-size:14px }',
                'placeholder': 'Enter content for this topic',
                'setup': 'function(editor) { editor.on("init", function() { const container = editor.getContainer(); if (container) { container.style.minHeight = "450px"; container.style.height = "450px"; const iframe = container.querySelector(".tox-edit-area__iframe"); if (iframe) { iframe.style.minHeight = "400px"; iframe.style.height = "400px"; } } }); }'
            }),
            'content_type': forms.Select(attrs={
                'class': 'w-full px-4 py-2 bg-gray-700 text-white rounded border border-gray-600 focus:border-blue-500 focus:ring-1 focus:ring-blue-500'
            }),
            'content_file': forms.FileInput(attrs={
                'class': 'w-full px-4 py-2 bg-gray-700 text-white rounded border border-gray-600 focus:border-blue-500 focus:ring-1 focus:ring-blue-500',
                'data-validate': 'general',
                'data-max-size': str(100 * 1024 * 1024),  # 100MB
                'data-categories': 'document,video,audio,archive'
            }),
            'web_url': forms.URLInput(attrs={
                'class': 'w-full px-4 py-2 bg-gray-700 text-white rounded border border-gray-600 focus:border-blue-500 focus:ring-1 focus:ring-blue-500',
                'placeholder': 'Enter URL'
            }),
            'embed_code': forms.Textarea(attrs={
                'rows': 4,
                'class': 'w-full px-4 py-2 bg-gray-700 text-white rounded border border-gray-600 focus:border-blue-500 focus:ring-1 focus:ring-blue-500',
                'placeholder': 'Enter embed code'
            }),
            'status': forms.Select(attrs={
                'class': 'w-full px-3 py-2 text-sm rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500'
            }),
            'restrict_to_learners': forms.CheckboxInput(attrs={
                'class': 'h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded'
            }),
            'restricted_learners': forms.CheckboxSelectMultiple(attrs={
                'class': 'restricted-learners-checkbox'
            })
        }


    def clean(self):
        cleaned_data = super().clean()
        content_type = cleaned_data.get('content_type')
        
        # Skip validation if content_type is missing
        if not content_type:
            return cleaned_data
            
        # Standardize content type to match the model choices
        # Fix case-sensitivity issues with content types
        else:
            # Don't use capitalize() as it lowercases everything after first char
            # Just use the original content_type as it should match model choices
            content_type_upper = content_type
        
        content_type_lower = content_type.lower()
        
        # Set default for order field if missing
        if 'order' not in cleaned_data or not cleaned_data.get('order'):
            cleaned_data['order'] = 0
        
        # Reset all content fields except the one needed for the selected content type
        fields_to_reset = {
            'web_url': '',
            'embed_code': '',
            'content_file': None,
            'quiz': None,
            'assignment': None,
            'conference': None,
            'discussion': None
        }
        
        
        # Don't reset text_content as it might contain valid content
        # Also don't reset the field we're actually using
        for field, value in fields_to_reset.items():
            # Skip resetting if this is the field we need for the current content type
            if content_type_lower == 'web' and field == 'web_url':
                continue
            elif content_type_lower == 'embedvideo' and field == 'embed_code':
                continue
            elif content_type_lower == 'quiz' and field == 'quiz':
                continue
            elif content_type_lower == 'assignment' and field == 'assignment':
                continue
            elif content_type_lower == 'conference' and field == 'conference':
                continue
            elif content_type_lower == 'discussion' and field == 'discussion':
                continue
            elif content_type_lower in ['video', 'audio', 'document'] and field == 'content_file':
                continue
                
            if field in cleaned_data:
                cleaned_data[field] = value
        
        # Validate required fields based on content type
        if content_type_lower == 'text':
            # Check if text_content has any actual content (could be empty HTML tags)
            text_content = cleaned_data.get('text_content', '')
            if not text_content or text_content.strip() == '':
                self.add_error('text_content', 'Text content is required for text topics.')
            # Don't reset text_content even if validation fails
        elif content_type_lower == 'web':
            if not cleaned_data.get('web_url'):
                self.add_error('web_url', 'URL is required for web topics.')
        elif content_type_lower == 'embedvideo':
            if not cleaned_data.get('embed_code'):
                self.add_error('embed_code', 'Embed code is required for embedded video topics.')
            elif content_type_lower in ['audio', 'video', 'document']:
                # Check if we're editing an existing topic with a file already
                if self.instance and self.instance.pk and self.instance.content_file:
                    # File already exists, no need to upload a new one unless one was provided
                    pass
                elif 'content_file' not in self.files:
                    file_type = content_type_lower
                    self.add_error('content_file', f'File upload is required for {file_type} topics.')
                else:
                    # File upload validation
                    content_file = self.files.get('content_file')
                    if content_file:
                        # Basic file validation is handled by the form field
                        pass
            # If no file is provided, that's OK - direct upload to cloud is supported
        elif content_type_lower == 'quiz':
            quiz = cleaned_data.get('quiz')
            if not quiz:
                self.add_error('quiz', 'Quiz selection is required for quiz topics.')
            else:
                # Check if this quiz is already linked to another topic
                current_topic_id = self.instance.pk if self.instance and self.instance.pk else None
                existing_topic = Topic.objects.filter(
                    quiz=quiz,
                    content_type='Quiz'
                ).exclude(pk=current_topic_id).first()
                
                if existing_topic:
                    self.add_error('quiz', f'This quiz is already used in topic "{existing_topic.title}". Each quiz can only be added to one topic.')
                else:
                    cleaned_data['quiz'] = quiz
        elif content_type_lower == 'assignment':
            assignment = cleaned_data.get('assignment')
            if not assignment:
                self.add_error('assignment', 'Assignment selection is required for assignment topics.')
            else:
                # Check if this assignment is already linked to another topic
                current_topic_id = self.instance.pk if self.instance and self.instance.pk else None
                existing_topic = Topic.objects.filter(
                    assignment=assignment,
                    content_type='Assignment'
                ).exclude(pk=current_topic_id).first()
                
                if existing_topic:
                    self.add_error('assignment', f'This assignment is already used in topic "{existing_topic.title}". Each assignment can only be added to one topic.')
                else:
                    cleaned_data['assignment'] = assignment
        elif content_type_lower == 'conference':
            conference = cleaned_data.get('conference')
            if not conference:
                self.add_error('conference', 'Conference selection is required for conference topics.')
            else:
                # Check if this conference is already linked to another topic
                current_topic_id = self.instance.pk if self.instance and self.instance.pk else None
                existing_topic = Topic.objects.filter(
                    conference=conference,
                    content_type='Conference'
                ).exclude(pk=current_topic_id).first()
                
                if existing_topic:
                    self.add_error('conference', f'This conference is already used in topic "{existing_topic.title}". Each conference can only be added to one topic.')
                else:
                    cleaned_data['conference'] = conference
        elif content_type_lower == 'discussion':
            discussion = cleaned_data.get('discussion')
            if not discussion:
                self.add_error('discussion', 'Discussion selection is required for discussion topics.')
            else:
                # Check if this discussion is already linked to another topic
                current_topic_id = self.instance.pk if self.instance and self.instance.pk else None
                existing_topic = Topic.objects.filter(
                    discussion=discussion,
                    content_type='Discussion'
                ).exclude(pk=current_topic_id).first()
                
                if existing_topic:
                    self.add_error('discussion', f'This discussion is already used in topic "{existing_topic.title}". Each discussion can only be added to one topic.')
                else:
                    cleaned_data['discussion'] = discussion
        
        # Store the standardized content type
        cleaned_data['content_type'] = content_type_upper
        
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        
        # Set content based on content type
        content_type = self.cleaned_data.get('content_type')
        content_type_lower = content_type.lower() if content_type else ''
        
        if content_type_lower == 'text':
            text_content = self.cleaned_data.get('text_content')
            # Check if the content is in JSON format
            if text_content and isinstance(text_content, str) and text_content.startswith('{') and text_content.endswith('}'):
                try:
                    content_data = json.loads(text_content)
                    # If content has HTML property, use that
                    if 'html' in content_data:
                        instance.text_content = content_data['html']
                    else:
                        instance.text_content = text_content
                except (json.JSONDecodeError, ValueError):
                    # If not valid JSON or missing 'html', use as is
                    instance.text_content = text_content
            else:
                # Handle direct HTML content from TinyMCE
                instance.text_content = text_content
        elif content_type_lower == 'web':
            instance.web_url = self.cleaned_data.get('web_url')
        elif content_type_lower == 'embedvideo':
            instance.embed_code = self.cleaned_data.get('embed_code')
        elif content_type_lower in ['video', 'audio', 'document']:
            if 'content_file' in self.files:
                instance.content_file = self.files['content_file']
        elif content_type_lower == 'quiz':
            instance.quiz = self.cleaned_data.get('quiz')
        elif content_type_lower == 'assignment':
            assignment = self.cleaned_data.get('assignment')
            instance.assignment = assignment
        elif content_type_lower == 'conference':
            instance.conference = self.cleaned_data.get('conference')
        elif content_type_lower == 'discussion':
            instance.discussion = self.cleaned_data.get('discussion')
        
        if commit:
            instance.save()
            self.save_m2m()
            
            # Handle course association for assignment topics
            if content_type_lower == 'assignment' and instance.assignment:
                # Look for the first CourseTopic relationship to find associated course
                from courses.models import CourseTopic
                course_topic = CourseTopic.objects.filter(topic=instance).first()
                
                if course_topic and course_topic.course:
                    # Import needed models
                    from assignments.models import AssignmentCourse
                    
                    
                    # Also create the many-to-many relationship through AssignmentCourse
                    AssignmentCourse.objects.get_or_create(
                        assignment=instance.assignment,
                        course=course_topic.course,
                        defaults={'is_primary': True}
                    )
            
        return instance

    def clean_content_file(self):
        """Validate content file using content-type specific validation"""
        content_file = self.cleaned_data.get('content_file')
        if content_file:
            # Get the content type to determine appropriate validation
            content_type = self.cleaned_data.get('content_type', '').lower()
            
            # Note: Other file types are now validated by secure_filename_validator in their respective clean methods
            pass
        return content_file


class TopicAdminForm(forms.ModelForm):
    course = forms.ModelChoiceField(
        queryset=Course.objects.all(),
        required=False,
        help_text="Select a course to associate this topic with"
    )

    class Meta:
        model = Topic
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            # Get the course through CourseTopic
            course = Course.objects.filter(coursetopic__topic=self.instance).first()
            if course:
                self.initial['course'] = course.id

    def save(self, commit=True):
        topic = super().save(commit=commit)
        if commit and self.cleaned_data.get('course'):
            # Create or update CourseTopic relationship
            course = self.cleaned_data['course']
            CourseTopic.objects.update_or_create(
                topic=topic,
                course=course,
                defaults={'order': CourseTopic.objects.filter(course=course).count() + 1}
            )
        return topic
