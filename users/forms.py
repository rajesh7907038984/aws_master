from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm, PasswordChangeForm, SetPasswordForm
from .models import CustomUser, Branch, ManualVAKScore, ManualAssessmentEntry
from courses.models import Course
import pytz
from django.core.validators import RegexValidator, MinValueValidator, MaxValueValidator
from typing import Any, Dict, List, Optional, Union, TYPE_CHECKING

if TYPE_CHECKING:
    from django.http import HttpRequest

class CustomUserCreationForm(UserCreationForm):
    branch = forms.ModelChoiceField(
        queryset=Branch.objects.all(),
        required=True,
        widget=forms.Select(attrs={'class': 'form-input'})
    )
    
    role = forms.ChoiceField(
        choices=CustomUser.ROLE_CHOICES,
        required=True,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    timezone = forms.ChoiceField(
        choices=[(tz, tz) for tz in pytz.common_timezones],
        required=True,
        initial='UTC',
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    courses = forms.ModelMultipleChoiceField(
        queryset=Course.objects.all(),
        required=False,
        widget=forms.SelectMultiple(attrs={'class': 'form-select', 'size': '5'}),
        help_text="Select courses to enroll the user in (optional)"
    )
    
    # Group selection fields
    user_groups = forms.ModelMultipleChoiceField(
        queryset=None,  # Will be set in __init__
        required=False,
        widget=forms.SelectMultiple(attrs={'class': 'form-select', 'size': '5', 'id': 'user-groups'}),
        help_text="Select user groups to assign the user to (optional)"
    )
    
    course_groups = forms.ModelMultipleChoiceField(
        queryset=None,  # Will be set in __init__
        required=False,
        widget=forms.SelectMultiple(attrs={'class': 'form-select', 'size': '5', 'id': 'course-groups'}),
        help_text="Select course groups to assign the user to (optional)"
    )

    class Meta:
        model = CustomUser
        fields = ['username', 'email', 'first_name', 'last_name', 'role', 'branch', 'timezone', 'password1', 'password2', 'courses', 'user_groups', 'course_groups']

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.request: Optional['HttpRequest'] = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        self.fields['branch'].help_text = "Select your branch"
        self.fields['email'].required = True
        self.fields['first_name'].required = False
        self.fields['last_name'].required = False
        self.fields['role'].initial = 'learner'
        self.fields['timezone'].help_text = "Select your preferred timezone"
        
        # Import here to avoid circular imports
        from groups.models import BranchGroup
        
        # Set up group querysets based on branch selection
        if self.request and hasattr(self.request, 'user') and hasattr(self.request.user, 'branch') and self.request.user.branch:
            # Filter groups by user's branch
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
            self.fields['courses'].queryset = Course.objects.filter(branch=user_branch)
        elif self.data.get('branch'):
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
                self.fields['courses'].queryset = Course.objects.filter(branch=branch)
            except (ValueError, TypeError, Branch.DoesNotExist):
                self.fields['user_groups'].queryset = BranchGroup.objects.none()
                self.fields['course_groups'].queryset = BranchGroup.objects.none()
                self.fields['courses'].queryset = Course.objects.none()
        else:
            # No branch selected, show no groups
            self.fields['user_groups'].queryset = BranchGroup.objects.none()
            self.fields['course_groups'].queryset = BranchGroup.objects.none()
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
        
        # Additional check for username + role combination
        if username and role:
            existing_username_query = CustomUser.objects.filter(
                username=username,
                is_active=True
            )
            
            # Exclude current user if editing
            if self.instance and self.instance.pk:
                existing_username_query = existing_username_query.exclude(pk=self.instance.pk)
                
            if existing_username_query.exists():
                existing_user = existing_username_query.first()
                if existing_user.role == role:
                    if branch and existing_user.branch == branch:
                        raise forms.ValidationError(
                            f"A user with username '{username}' and role '{dict(CustomUser.ROLE_CHOICES)[role]}' "
                            f"already exists in branch '{branch.name}'. Cannot create duplicate user role accounts."
                        )
                    elif not branch and not existing_user.branch:
                        raise forms.ValidationError(
                            f"A user with username '{username}' and role '{dict(CustomUser.ROLE_CHOICES)[role]}' "
                            f"already exists. Cannot create duplicate user role accounts."
                        )
        
        # For Global Admin role users, ensure no other user has the same email with Global Admin role
        if role == 'globaladmin' and email:
            existing_globaladmin = CustomUser.objects.filter(
                email=email,
                role='globaladmin',
                is_active=True
            )
            
            # Exclude current user if editing  
            if self.instance and self.instance.pk:
                existing_globaladmin = existing_globaladmin.exclude(pk=self.instance.pk)
                
            if existing_globaladmin.exists():
                raise forms.ValidationError(
                    f"A Global Admin user with email '{email}' already exists. "
                    f"Cannot create duplicate Global Admin accounts."
                )
        
        # Handle password change validation - only validate if passwords are actually provided
        password1 = cleaned_data.get('password1')
        password2 = cleaned_data.get('password2')
        
        # Only validate passwords if at least one is provided (user is trying to change password)
        if password1 or password2:
            if password1 != password2:
                raise forms.ValidationError("The two password fields didn't match.")
            
            if password1 and len(password1) < 8:
                raise forms.ValidationError("Password must be at least 8 characters long.")
            
            # If passwords are provided, both must be provided
            if not password1:
                raise forms.ValidationError("Please enter a new password.")
            if not password2:
                raise forms.ValidationError("Please confirm your new password.")
        
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

class TabbedUserCreationForm(UserCreationForm):
    # Common Fields
    branch = forms.ModelChoiceField(
        queryset=Branch.objects.all(),
        required=False,  # Changed to False since Super Admins don't need branches
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    # Add business field for Super Admin assignment
    business = forms.ModelChoiceField(
        queryset=None,  # Will be set in __init__
        required=False,  # Will be required conditionally based on role
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text="Select the business for Super Admin assignment"
    )
    
    role = forms.ChoiceField(
        choices=CustomUser.ROLE_CHOICES,
        required=True,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    timezone = forms.ChoiceField(
        choices=[(tz, tz) for tz in pytz.common_timezones],
        required=True,
        initial='UTC',
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text="Select your preferred timezone"
    )
    
    # Account Tab - Adding new fields
    given_name = forms.CharField(
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g., Jane'}),
        help_text="Given/First Name - mandatory"
    )
    
    family_name = forms.CharField(
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g., Doe'}),
        help_text="Family/Last Name - mandatory"
    )
    
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={'class': 'form-input', 'placeholder': 'e.g., jane.doe@email.com'}),
        help_text="Email Address - mandatory for communication"
    )
    
    phone_number = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g., +44 7123 456789'}),
        help_text="Phone Number - optional for communication"
    )
    
    contact_preference = forms.ChoiceField(
        choices=CustomUser.CONTACT_PREFERENCE_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text="Contact Preference - preferred method of contact"
    )
    
    # Tab 1: Personal Information
    unique_learner_number = forms.IntegerField(
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-input', 'placeholder': 'e.g., 1234567890'}),
        help_text="Unique Learner Number (ULN) - optional unique identifier"
    )
    
    date_of_birth = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
        help_text="Date of Birth - optional, format YYYY-MM-DD"
    )
    
    sex = forms.ChoiceField(
        choices=CustomUser.SEX_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text="Sex - optional"
    )
    
    sex_other = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Please specify'}),
        help_text="If 'Other' is selected above, please specify"
    )
    
    sexual_orientation = forms.ChoiceField(
        choices=CustomUser.SEXUAL_ORIENTATION_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text="Sexual orientation - optional"
    )
    
    sexual_orientation_other = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Please specify'}),
        help_text="If 'Other sexual orientation' is selected above, please specify"
    )
    
    ethnicity = forms.ChoiceField(
        choices=CustomUser.ETHNICITY_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text="Ethnicity - optional"
    )
    
    ethnicity_other = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Please specify'}),
        help_text="If any 'Other' ethnicity option is selected above, please specify"
    )
    
    postcode_validator = RegexValidator(
        regex=r'^[A-Z]{1,2}[0-9][A-Z0-9]? ?[0-9][A-Z]{2}$|^ZZ99 9ZZ$',
        message="Enter a valid UK postcode or ZZ99 9ZZ if unknown"
    )
    
    current_postcode = forms.CharField(
        required=False,
        validators=[postcode_validator],
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g., PO1 3AX or ZZ99 9ZZ'}),
        help_text="Current Postcode - optional, valid UK postcode or ZZ99 9ZZ if unknown"
    )
    
    address_line1 = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Address Line 1'}),
        help_text="Street address/house number"
    )
    
    address_line2 = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Address Line 2'}),
        help_text="Apartment/Suite/Unit/Building (optional)"
    )
    
    city = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'City/Town'}),
        help_text="City or Town"
    )
    
    county = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'County'}),
        help_text="County/State/Province"
    )
    
    country = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Country'}),
        help_text="Country (defaults to UK if not specified)"
    )
    
    is_non_uk_address = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
        help_text="Check if address is outside the UK"
    )
    
    # Tab 2: Education Background
    study_area = forms.ChoiceField(
        choices=CustomUser.STUDY_AREA_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text="Study Area - optional"
    )
    
    study_area_other = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Please specify'}),
        help_text="If 'Other' is selected above, please specify"
    )
    
    level_of_study = forms.ChoiceField(
        choices=CustomUser.LEVEL_OF_STUDY_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text="Level of Study - optional"
    )
    
    grades = forms.ChoiceField(
        choices=CustomUser.GRADES_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text="Grades - optional"
    )
    
    grades_other = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Please specify'}),
        help_text="If 'Other (Please Specify)' is selected above, please specify"
    )
    
    date_achieved = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
        help_text="Date Achieved - optional, format YYYY-MM-DD"
    )
    
    has_learning_difficulty = forms.ChoiceField(
        choices=CustomUser.LEARNING_DIFFICULTY_CHOICES,
        required=False,
        help_text="Has Learning Difficulty - optional"
    )
    
    learning_difficulty_details = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-textarea', 'rows': 3, 'placeholder': 'e.g., Dyslexia'}),
        help_text="Learning Difficulty Details - optional, text input if Yes"
    )
    
    # Tab 3: Employment History
    job_role = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g., Office Administrator'}),
        help_text="Job Role - optional, text input"
    )
    
    industry = forms.ChoiceField(
        choices=CustomUser.INDUSTRY_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text="Industry - optional"
    )
    
    industry_other = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Please specify'}),
        help_text="If 'Other' is selected above, please specify"
    )
    
    duration = forms.ChoiceField(
        choices=CustomUser.DURATION_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text="Duration - optional"
    )
    
    key_skills = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-textarea', 'rows': 3, 'placeholder': 'e.g., Team Leadership, Data Analysis'}),
        help_text="Key Skills - optional, text input"
    )
    
    cv_file = forms.FileField(
        required=False,
        widget=forms.FileInput(attrs={'class': 'form-file-input'}),
        help_text="CV File - optional, file upload (PDF/Word, <5MB)"
    )
    
    # Tab 4: Assessment Data - Completely restructured
    # Initial Assessment section
    initial_assessment_english = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-checkbox assessment-checkbox', 'data-type': 'initial', 'data-subject': 'english'}),
        label="English"
    )
    
    initial_assessment_maths = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-checkbox assessment-checkbox', 'data-type': 'initial', 'data-subject': 'maths'}),
        label="Maths"
    )
    
    initial_assessment_subject_specific = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-checkbox assessment-checkbox', 'data-type': 'initial', 'data-subject': 'subject'}),
        label="Subject Specific"
    )
    
    initial_assessment_other = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-checkbox assessment-checkbox', 'data-type': 'initial', 'data-subject': 'other'}),
        label="Other"
    )
    
    initial_assessment_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
        help_text="Initial Assessment Date"
    )
    
    # Initial Assessment Score Fields
    initial_assessment_english_score = forms.DecimalField(
        required=False,
        max_digits=5,
        decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'form-input', 'min': '0', 'max': '100', 'step': '0.01', 'placeholder': 'Score (0-100)'}),
        help_text="English assessment score (0-100)"
    )
    
    initial_assessment_maths_score = forms.DecimalField(
        required=False,
        max_digits=5,
        decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'form-input', 'min': '0', 'max': '100', 'step': '0.01', 'placeholder': 'Score (0-100)'}),
        help_text="Maths assessment score (0-100)"
    )
    
    initial_assessment_subject_score = forms.DecimalField(
        required=False,
        max_digits=5,
        decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'form-input', 'min': '0', 'max': '100', 'step': '0.01', 'placeholder': 'Score (0-100)'}),
        help_text="Subject Specific assessment score (0-100)"
    )
    
    initial_assessment_other_score = forms.DecimalField(
        required=False,
        max_digits=5,
        decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'form-input', 'min': '0', 'max': '100', 'step': '0.01', 'placeholder': 'Score (0-100)'}),
        help_text="Other assessment score (0-100)"
    )
    
    # Diagnostic Assessment section
    diagnostic_assessment_english = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-checkbox assessment-checkbox', 'data-type': 'diagnostic', 'data-subject': 'english'}),
        label="English"
    )
    
    diagnostic_assessment_maths = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-checkbox assessment-checkbox', 'data-type': 'diagnostic', 'data-subject': 'maths'}),
        label="Maths"
    )
    
    diagnostic_assessment_subject_specific = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-checkbox assessment-checkbox', 'data-type': 'diagnostic', 'data-subject': 'subject'}),
        label="Subject Specific"
    )
    
    diagnostic_assessment_other = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-checkbox assessment-checkbox', 'data-type': 'diagnostic', 'data-subject': 'other'}),
        label="Other"
    )
    
    diagnostic_assessment_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
        help_text="Diagnostic Assessment Date"
    )
    
    # Diagnostic Assessment Score Fields
    diagnostic_assessment_english_score = forms.DecimalField(
        required=False,
        max_digits=5,
        decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'form-input', 'min': '0', 'max': '100', 'step': '0.01', 'placeholder': 'Score (0-100)'}),
        help_text="English diagnostic assessment score (0-100)"
    )
    
    diagnostic_assessment_maths_score = forms.DecimalField(
        required=False,
        max_digits=5,
        decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'form-input', 'min': '0', 'max': '100', 'step': '0.01', 'placeholder': 'Score (0-100)'}),
        help_text="Maths diagnostic assessment score (0-100)"
    )
    
    diagnostic_assessment_subject_score = forms.DecimalField(
        required=False,
        max_digits=5,
        decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'form-input', 'min': '0', 'max': '100', 'step': '0.01', 'placeholder': 'Score (0-100)'}),
        help_text="Subject Specific diagnostic assessment score (0-100)"
    )
    
    diagnostic_assessment_other_score = forms.DecimalField(
        required=False,
        max_digits=5,
        decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'form-input', 'min': '0', 'max': '100', 'step': '0.01', 'placeholder': 'Score (0-100)'}),
        help_text="Other diagnostic assessment score (0-100)"
    )
    
    # Functional Skills section
    functional_skills_english = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-checkbox assessment-checkbox', 'data-type': 'functional', 'data-subject': 'english'}),
        label="English"
    )
    
    functional_skills_maths = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-checkbox assessment-checkbox', 'data-type': 'functional', 'data-subject': 'maths'}),
        label="Maths"
    )
    
    functional_skills_other = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-checkbox assessment-checkbox', 'data-type': 'functional', 'data-subject': 'other'}),
        label="Other"
    )
    
    functional_skills_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
        help_text="Functional Skills Assessment Date"
    )
    
    # Functional Skills Score Fields
    functional_skills_english_score = forms.DecimalField(
        required=False,
        max_digits=5,
        decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'form-input', 'min': '0', 'max': '100', 'step': '0.01', 'placeholder': 'Score (0-100)'}),
        help_text="English functional skills score (0-100)"
    )
    
    functional_skills_maths_score = forms.DecimalField(
        required=False,
        max_digits=5,
        decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'form-input', 'min': '0', 'max': '100', 'step': '0.01', 'placeholder': 'Score (0-100)'}),
        help_text="Maths functional skills score (0-100)"
    )
    
    functional_skills_other_score = forms.DecimalField(
        required=False,
        max_digits=5,
        decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'form-input', 'min': '0', 'max': '100', 'step': '0.01', 'placeholder': 'Score (0-100)'}),
        help_text="Other functional skills score (0-100)"
    )
    
    # Tab 5: Additional Information
    statement_of_purpose_file = forms.FileField(
        required=False,
        widget=forms.FileInput(attrs={'class': 'form-file-input'}),
        help_text="Statement of Purpose File - optional, file upload (PDF/Word, <5MB)"
    )
    
    reason_for_pursuing_course = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-textarea', 'rows': 3, 'placeholder': 'e.g., To develop business management skills for entrepreneurship'}),
        help_text="Reason for Pursuing Course - optional, text input"
    )
    
    career_objectives = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-textarea', 'rows': 3, 'placeholder': 'e.g., Start my own business'}),
        help_text="Career Objectives - optional, text input"
    )
    
    relevant_past_work = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-textarea', 'rows': 3, 'placeholder': 'e.g., Previous experience in retail management'}),
        help_text="Relevant Past Work - optional, text input"
    )
    
    profile_image = forms.ImageField(
        required=False,
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
        help_text="Upload a profile picture. Recommended size: 300x300 pixels. Max file size: 5MB."
    )
    
    # Group selection fields
    user_groups = forms.ModelMultipleChoiceField(
        queryset=None,  # Will be set in __init__
        required=False,
        widget=forms.SelectMultiple(attrs={'class': 'form-select', 'size': '5', 'id': 'user-groups'}),
        help_text="Select user groups to assign the user to (optional)"
    )
    
    course_groups = forms.ModelMultipleChoiceField(
        queryset=None,  # Will be set in __init__
        required=False,
        widget=forms.SelectMultiple(attrs={'class': 'form-select', 'size': '5', 'id': 'course-groups'}),
        help_text="Select course groups to assign the user to (optional)"
    )

    
    class Meta:
        model = CustomUser
        fields = [
            # Account fields
            'username', 'password1', 'password2', 'role', 'branch', 'business', 'timezone',
            'email', 'phone_number', 'contact_preference', 'profile_image', 'user_groups', 'course_groups',
            
            # Personal info fields
            'unique_learner_number', 'date_of_birth', 'sex', 'sex_other', 'sexual_orientation', 'sexual_orientation_other', 'ethnicity', 'ethnicity_other',
            'current_postcode', 'address_line1', 'address_line2', 'city', 'county', 'country',
            'is_non_uk_address',
            
            # Education fields
            'study_area', 'study_area_other', 'level_of_study', 'grades', 'grades_other',
            'date_achieved', 'has_learning_difficulty', 'learning_difficulty_details',
            'education_data',
            
            # Employment fields
            'job_role', 'industry', 'industry_other', 'duration', 'key_skills', 'employment_data', 'cv_file',
            
            # Assessment data fields
            'initial_assessment_english', 'initial_assessment_maths',
            'initial_assessment_subject_specific', 'initial_assessment_other',
            'initial_assessment_date',
            'initial_assessment_english_score', 'initial_assessment_maths_score',
            'initial_assessment_subject_score', 'initial_assessment_other_score',
            'diagnostic_assessment_english', 'diagnostic_assessment_maths',
            'diagnostic_assessment_subject_specific', 'diagnostic_assessment_other',
            'diagnostic_assessment_date',
            'diagnostic_assessment_english_score', 'diagnostic_assessment_maths_score',
            'diagnostic_assessment_subject_score', 'diagnostic_assessment_other_score',
            'functional_skills_english', 'functional_skills_maths', 'functional_skills_other',
            'functional_skills_date',
            'functional_skills_english_score', 'functional_skills_maths_score', 'functional_skills_other_score',
            
            # Additional info fields
            'statement_of_purpose_file', 'reason_for_pursuing_course',
            'career_objectives', 'relevant_past_work'
        ]
    
    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        
        # Import here to avoid circular imports
        from business.models import Business
        
        # Determine if this is a self-edit scenario
        self.is_self_edit = (self.request and self.instance and self.instance.pk and 
                            self.request.user.id == self.instance.pk)
        
        # Set up business field queryset
        if self.request and self.request.user.role == 'globaladmin':
            # Global Admin can assign to any business
            self.fields['business'].queryset = Business.objects.filter(is_active=True).order_by('name')
        elif self.request and self.request.user.role == 'superadmin':
            # Super Admin can see businesses they are assigned to
            if hasattr(self.request.user, 'business_assignments'):
                assigned_businesses = self.request.user.business_assignments.filter(is_active=True).values_list('business', flat=True)
                self.fields['business'].queryset = Business.objects.filter(id__in=assigned_businesses, is_active=True).order_by('name')
            else:
                self.fields['business'].queryset = Business.objects.none()
        else:
            # Other users don't see business field
            self.fields['business'].queryset = Business.objects.none()

        # Set field requirements and styling
        self.fields['given_name'].required = True
        self.fields['family_name'].required = True
        self.fields['role'].required = True
        
        # Branch requirement depends on role - Super Admins don't need branches
        self.fields['branch'].required = False
        self.fields['business'].required = False

        # Add help text
        self.fields['username'].help_text = "Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only."
        self.fields['email'].help_text = "Required. Enter a valid email address."
        self.fields['role'].help_text = "Select the user's role in the system."
        self.fields['branch'].help_text = "Select the branch this user belongs to (not required for Super Admin)."
        self.fields['business'].help_text = "Select the business for Super Admin assignment."
        self.fields['timezone'].help_text = "Select your preferred timezone"

        # Set up timezone choices
        self.fields['timezone'].widget.choices = [(tz, tz) for tz in pytz.common_timezones]

        # Set timezone initial value from user's timezone preference
        if self.instance and hasattr(self.instance, 'timezone_preference'):
            try:
                timezone_pref = getattr(self.instance, 'timezone_preference', None)
                if timezone_pref and timezone_pref.timezone:
                    self.fields['timezone'].initial = timezone_pref.timezone
                else:
                    # Fallback to user's timezone field
                    self.fields['timezone'].initial = self.instance.timezone
            except Exception:
                # If there's any error accessing timezone_preference, fallback to user's timezone field
                self.fields['timezone'].initial = self.instance.timezone
        elif self.instance and self.instance.timezone:
            self.fields['timezone'].initial = self.instance.timezone

        # Handle self-editing restrictions
        if self.is_self_edit:
            # Users editing their own profile cannot change role or branch
            self.fields['role'].disabled = True
            self.fields['role'].widget.attrs['readonly'] = True
            self.fields['branch'].disabled = True
            self.fields['branch'].widget.attrs['readonly'] = True
            
            # For super admin users editing themselves, also disable business field
            if self.request.user.role == 'superadmin':
                self.fields['business'].disabled = True
                self.fields['business'].widget.attrs['readonly'] = True
            
            # Set current values for disabled fields
            if self.instance:
                self.fields['role'].initial = self.instance.role
                self.fields['branch'].initial = self.instance.branch
                if self.instance.role == 'superadmin':
                    # Get the business from business_assignments relationship
                    business_assignment = self.instance.business_assignments.filter(is_active=True).first()
                    if business_assignment:
                        self.fields['business'].initial = business_assignment.business

        # Handle branch and role choices based on user role (only for non-self-edit scenarios)
        if self.request and self.request.user and not self.is_self_edit:
            if self.request.user.role == 'globaladmin':
                # Global Admin can assign to any branch
                self.fields['branch'].queryset = Branch.objects.all().order_by('name')
            elif self.request.user.role == 'superadmin':
                # Super Admin: show branches within their business allocation, or all branches as fallback
                if hasattr(self.request.user, 'business_assignments'):
                    assigned_businesses = self.request.user.business_assignments.filter(is_active=True).values_list('business', flat=True)
                    branches = Branch.objects.filter(business__in=assigned_businesses).order_by('name')
                    # If no branches found within business assignments, show all branches as fallback
                    if not branches.exists():
                        branches = Branch.objects.all().order_by('name')
                    self.fields['branch'].queryset = branches
                else:
                    # If no business assignments, show all branches
                    self.fields['branch'].queryset = Branch.objects.all().order_by('name')
            elif not self.request.user.is_superuser:
                # For non-superusers, set their branch and make it read-only
                self.fields['branch'].queryset = Branch.objects.filter(id=self.request.user.branch_id)
                self.fields['branch'].initial = self.request.user.branch
                self.fields['branch'].disabled = True
                self.fields['branch'].widget.attrs['readonly'] = True
            else:
                # For superusers, show all branches
                self.fields['branch'].queryset = Branch.objects.all().order_by('name')
        elif self.is_self_edit:
            # For self-edit, set limited queryset to current user's branch
            if self.instance and self.instance.branch:
                self.fields['branch'].queryset = Branch.objects.filter(id=self.instance.branch.id)
            else:
                self.fields['branch'].queryset = Branch.objects.none()

        # Ensure the current role of the user being edited is always a valid choice
        if self.instance and self.instance.pk and hasattr(self.instance, 'role') and self.instance.role:
            current_role = self.instance.role
            current_choices = dict(self.fields['role'].choices)
            
            if current_role not in current_choices:
                # Add the current role to the choices if it's not already there
                all_choices = dict(CustomUser.ROLE_CHOICES)
                if current_role in all_choices:
                    new_choices = list(self.fields['role'].choices)
                    new_choices.append((current_role, all_choices[current_role]))
                    self.fields['role'].choices = new_choices

    def clean(self):
        cleaned_data = super().clean()
        role = cleaned_data.get('role')
        branch = cleaned_data.get('branch')
        business = cleaned_data.get('business')
        
        # Additional validation for role restrictions
        if self.request and self.request.user:
            user = self.request.user
            
            # Global Admin users must now specify business/branch requirements
            if user.role == 'globaladmin':
                # For Super Admin role, business is required instead of branch
                if role == 'superadmin':
                    if not business:
                        self.add_error('business', 'Business selection is required for Super Admin users.')
                    # Super Admins don't need branches - clear branch if set
                    cleaned_data['branch'] = None
                else:
                    # For other roles, branch is now REQUIRED (no auto-assignment)
                    if role in ['admin', 'instructor', 'learner']:
                        if not branch:
                            self.add_error('branch', 'Branch selection is required for this role. Please select a branch.')
                    # Clear business for non-Super Admin roles
                    if role != 'superadmin':
                        cleaned_data['business'] = None
                return cleaned_data

            # For Admin and Instructor users, use their assigned branch
            elif user.role in ['admin', 'instructor']:
                # For admin/instructor users, always use their branch
                if user.branch:
                    cleaned_data['branch'] = user.branch
                else:
                    # This shouldn't happen, but handle it gracefully
                    self.add_error('branch', 'You must be assigned to a branch to create users.')
                # Clear business field for non-Global Admin users
                cleaned_data['business'] = None
            
            # For Super Admin users, allow branch selection but auto-assign if needed
            elif user.role == 'superadmin':
                if role in ['admin', 'instructor', 'learner'] and not branch:
                    # Auto-assign to first available branch if none selected
                    from branches.models import Branch
                    first_branch = Branch.objects.first()
                    if first_branch:
                        cleaned_data['branch'] = first_branch
                        # Add a message to inform the user about auto-assignment
                        import django.contrib.messages as messages
                        if hasattr(self.request, '_messages'):
                            messages.info(self.request, f'Branch automatically assigned to "{first_branch.name}" for {role} user.')
                    else:
                        self.add_error('branch', 'Branch selection is required for this role, but no branches are available.')
                # Clear business field for Super Admin users creating non-Super Admin roles
                if role != 'superadmin':
                    cleaned_data['business'] = None
            
            # For Django superusers, ensure branch is selected for roles that need it
            elif user.is_superuser and role in ['admin', 'instructor', 'learner'] and not branch:
                from branches.models import Branch
                first_branch = Branch.objects.first()
                if first_branch:
                    cleaned_data['branch'] = first_branch
                else:
                    self.add_error('branch', 'Branch selection is required for this role.')

            # Apply role creation restrictions
            # Global admin users can create other global admin users
            if user.role == 'superadmin' and role in ['globaladmin', 'superadmin']:
                self.add_error('role', 'Super admin users are not allowed to assign global admin or super admin roles.')
            elif user.role == 'admin' and role in ['superadmin', 'globaladmin']:
                self.add_error('role', 'Admin users are not allowed to assign super admin or global admin roles.')

        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        
        # Set critical fields first
        user.role = self.cleaned_data.get('role', 'learner')
        user.branch = self.cleaned_data.get('branch')
        user.timezone = self.cleaned_data.get('timezone', 'UTC')
        
        # Map form fields to both standard Django fields and custom model fields
        given_name = self.cleaned_data.get('given_name', '')
        family_name = self.cleaned_data.get('family_name', '')
        
        # Standard Django User fields
        user.first_name = given_name
        user.last_name = family_name
        
        # Custom model fields for consistency
        user.given_names = given_name
        user.family_name = family_name
        user.phone_number = self.cleaned_data.get('phone_number', '')
        user.contact_preference = self.cleaned_data.get('contact_preference', '')
        
        # Handle business assignment for Super Admin users
        business = self.cleaned_data.get('business')
        if user.role == 'superadmin' and business:
            # Business assignment will be handled after user is saved
            user._pending_business_assignment = business
        
        # Set all the assessment data fields
        user.initial_assessment_english = self.cleaned_data.get('initial_assessment_english', False)
        user.initial_assessment_maths = self.cleaned_data.get('initial_assessment_maths', False)
        user.initial_assessment_subject_specific = self.cleaned_data.get('initial_assessment_subject_specific', False)
        user.initial_assessment_other = self.cleaned_data.get('initial_assessment_other', False)
        user.initial_assessment_date = self.cleaned_data.get('initial_assessment_date')
        
        user.diagnostic_assessment_english = self.cleaned_data.get('diagnostic_assessment_english', False)
        user.diagnostic_assessment_maths = self.cleaned_data.get('diagnostic_assessment_maths', False)
        user.diagnostic_assessment_subject_specific = self.cleaned_data.get('diagnostic_assessment_subject_specific', False)
        user.diagnostic_assessment_other = self.cleaned_data.get('diagnostic_assessment_other', False)
        user.diagnostic_assessment_date = self.cleaned_data.get('diagnostic_assessment_date')
        
        user.functional_skills_english = self.cleaned_data.get('functional_skills_english', False)
        user.functional_skills_maths = self.cleaned_data.get('functional_skills_maths', False)
        user.functional_skills_other = self.cleaned_data.get('functional_skills_other', False)
        user.functional_skills_date = self.cleaned_data.get('functional_skills_date')
        
        # Handle personal information fields
        user.unique_learner_number = self.cleaned_data.get('unique_learner_number')
        user.date_of_birth = self.cleaned_data.get('date_of_birth')
        user.sex = self.cleaned_data.get('sex', '')
        user.sex_other = self.cleaned_data.get('sex_other', '')
        user.sexual_orientation = self.cleaned_data.get('sexual_orientation', '')
        user.sexual_orientation_other = self.cleaned_data.get('sexual_orientation_other', '')
        user.ethnicity = self.cleaned_data.get('ethnicity', '')
        user.ethnicity_other = self.cleaned_data.get('ethnicity_other', '')
        user.current_postcode = self.cleaned_data.get('current_postcode', '')
        user.address_line1 = self.cleaned_data.get('address_line1', '')
        user.address_line2 = self.cleaned_data.get('address_line2', '')
        user.city = self.cleaned_data.get('city', '')
        user.county = self.cleaned_data.get('county', '')
        user.country = self.cleaned_data.get('country', 'United Kingdom')
        user.is_non_uk_address = self.cleaned_data.get('is_non_uk_address', False)
        
        # Handle education fields
        user.study_area = self.cleaned_data.get('study_area', '')
        user.study_area_other = self.cleaned_data.get('study_area_other', '')
        user.level_of_study = self.cleaned_data.get('level_of_study', '')
        user.grades = self.cleaned_data.get('grades', '')
        user.grades_other = self.cleaned_data.get('grades_other', '')
        user.date_achieved = self.cleaned_data.get('date_achieved')
        user.has_learning_difficulty = self.cleaned_data.get('has_learning_difficulty', '')
        user.learning_difficulty_details = self.cleaned_data.get('learning_difficulty_details', '')
        
        # Handle employment fields
        user.job_role = self.cleaned_data.get('job_role', '')
        user.industry = self.cleaned_data.get('industry', '')
        user.industry_other = self.cleaned_data.get('industry_other', '')
        user.duration = self.cleaned_data.get('duration', '')
        user.key_skills = self.cleaned_data.get('key_skills', '')
        
        # Handle additional information fields
        user.reason_for_pursuing_course = self.cleaned_data.get('reason_for_pursuing_course', '')
        user.career_objectives = self.cleaned_data.get('career_objectives', '')
        user.relevant_past_work = self.cleaned_data.get('relevant_past_work', '')
        user.special_interests_and_strengths = self.cleaned_data.get('special_interests_and_strengths', '')
        user.achievements_and_awards = self.cleaned_data.get('achievements_and_awards', '')
        
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
            
            # Handle business assignment for Super Admin users
            role = self.cleaned_data.get('role')
            business = self.cleaned_data.get('business')
            
            if role == 'superadmin' and business and self.request:
                # Create business assignment for Super Admin
                from business.models import BusinessUserAssignment
                BusinessUserAssignment.objects.create(
                    business=business,
                    user=user,
                    assigned_by=self.request.user,
                    is_active=True
                )
        
        return user

class CustomUserChangeForm(forms.ModelForm):
    # Common Fields
    branch = forms.ModelChoiceField(
        queryset=Branch.objects.all(),
        required=True,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    # Add business field for Super Admin assignment
    business = forms.ModelChoiceField(
        queryset=None,  # Will be set in __init__
        required=False,  # Will be required conditionally based on role
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text="Select the business for Super Admin assignment"
    )
    
    role = forms.ChoiceField(
        choices=CustomUser.ROLE_CHOICES,
        required=True,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    timezone = forms.ChoiceField(
        choices=[(tz, tz) for tz in pytz.common_timezones],
        required=True,
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text="Select your preferred timezone"
    )
    
    # Account Tab fields
    given_name = forms.CharField(
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-input'}),
        help_text="Given/First Name - mandatory"
    )
    
    family_name = forms.CharField(
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-input'}),
        help_text="Family/Last Name - mandatory"
    )
    
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={'class': 'form-input'}),
        help_text="Email Address - mandatory for communication"
    )
    
    phone_number = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-input'}),
        help_text="Phone Number - optional for communication"
    )
    
    contact_preference = forms.ChoiceField(
        choices=CustomUser.CONTACT_PREFERENCE_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text="Contact Preference - preferred method of contact"
    )
    
    # Assessment checkboxes that were missing
    initial_assessment_english = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-checkbox assessment-checkbox', 'data-type': 'initial', 'data-subject': 'english'}),
        label="English"
    )
    
    initial_assessment_maths = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-checkbox assessment-checkbox', 'data-type': 'initial', 'data-subject': 'maths'}),
        label="Maths"
    )
    
    initial_assessment_subject_specific = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-checkbox assessment-checkbox', 'data-type': 'initial', 'data-subject': 'subject'}),
        label="Subject Specific"
    )
    
    initial_assessment_other = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-checkbox assessment-checkbox', 'data-type': 'initial', 'data-subject': 'other'}),
        label="Other"
    )
    
    diagnostic_assessment_english = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-checkbox assessment-checkbox', 'data-type': 'diagnostic', 'data-subject': 'english'}),
        label="English"
    )
    
    diagnostic_assessment_maths = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-checkbox assessment-checkbox', 'data-type': 'diagnostic', 'data-subject': 'maths'}),
        label="Maths"
    )
    
    diagnostic_assessment_subject_specific = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-checkbox assessment-checkbox', 'data-type': 'diagnostic', 'data-subject': 'subject'}),
        label="Subject Specific"
    )
    
    diagnostic_assessment_other = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-checkbox assessment-checkbox', 'data-type': 'diagnostic', 'data-subject': 'other'}),
        label="Other"
    )
    
    functional_skills_english = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-checkbox assessment-checkbox', 'data-type': 'functional', 'data-subject': 'english'}),
        label="English"
    )
    
    functional_skills_maths = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-checkbox assessment-checkbox', 'data-type': 'functional', 'data-subject': 'maths'}),
            label="Maths"
    )
    
    functional_skills_other = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-checkbox assessment-checkbox', 'data-type': 'functional', 'data-subject': 'other'}),
        label="Other"
    )

    is_non_uk_address = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
        help_text="Check if address is outside the UK"
    )
    
    # Password fields for optional password change during edit
    password1 = forms.CharField(
        required=False,
        widget=forms.PasswordInput(attrs={'class': 'form-input'}),
        help_text="Leave blank to keep current password unchanged"
    )
    
    password2 = forms.CharField(
        required=False,
        widget=forms.PasswordInput(attrs={'class': 'form-input'}),
        help_text="Enter the same password as before, for verification"
    )
    
    sexual_orientation = forms.ChoiceField(
        choices=CustomUser.SEXUAL_ORIENTATION_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text="Sexual orientation - optional"
    )
    
    profile_image = forms.ImageField(
        required=False,
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
        help_text="Upload a profile picture. Recommended size: 300x300 pixels. Max file size: 5MB."
    )
    
    # Group selection fields
    user_groups = forms.ModelMultipleChoiceField(
        queryset=None,  # Will be set in __init__
        required=False,
        widget=forms.SelectMultiple(attrs={'class': 'form-select', 'size': '5', 'id': 'user-groups'}),
        help_text="Select user groups to assign the user to (optional)"
    )
    
    course_groups = forms.ModelMultipleChoiceField(
        queryset=None,  # Will be set in __init__
        required=False,
        widget=forms.SelectMultiple(attrs={'class': 'form-select', 'size': '5', 'id': 'course-groups'}),
        help_text="Select course groups to assign the user to (optional)"
    )
    
    class Meta:
        model = CustomUser
        fields = [
            # Account fields
            'username', 'email', 'role', 'branch', 'business', 'timezone', 'is_active',
            'phone_number', 'contact_preference', 'password1', 'password2', 'profile_image', 'user_groups', 'course_groups',
            
            # Personal info fields
            'unique_learner_number', 'date_of_birth', 'sex', 'sex_other', 'sexual_orientation', 'sexual_orientation_other', 'ethnicity', 'ethnicity_other',
            'current_postcode', 'address_line1', 'address_line2', 'city', 'county', 'country',
            'is_non_uk_address',
            
            # Education fields
            'study_area', 'study_area_other', 'level_of_study', 'grades', 'grades_other',
            'date_achieved', 'has_learning_difficulty', 'learning_difficulty_details',
            'education_data',
            
            # Employment fields
            'job_role', 'industry', 'industry_other', 'duration', 'key_skills', 'employment_data', 'cv_file',
            
            # Assessment data fields
            'initial_assessment_english', 'initial_assessment_maths',
            'initial_assessment_subject_specific', 'initial_assessment_other',
            'initial_assessment_date',
            'initial_assessment_english_score', 'initial_assessment_maths_score',
            'initial_assessment_subject_score', 'initial_assessment_other_score',
            'diagnostic_assessment_english', 'diagnostic_assessment_maths',
            'diagnostic_assessment_subject_specific', 'diagnostic_assessment_other',
            'diagnostic_assessment_date',
            'diagnostic_assessment_english_score', 'diagnostic_assessment_maths_score',
            'diagnostic_assessment_subject_score', 'diagnostic_assessment_other_score',
            'functional_skills_english', 'functional_skills_maths', 'functional_skills_other',
            'functional_skills_date',
            'functional_skills_english_score', 'functional_skills_maths_score', 'functional_skills_other_score',
            
            # Additional info fields
            'statement_of_purpose_file', 'reason_for_pursuing_course',
            'career_objectives', 'relevant_past_work'
        ]
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-input'}),
            'email': forms.EmailInput(attrs={'class': 'form-input'}),
            'role': forms.Select(attrs={'class': 'form-select'}),
            'branch': forms.Select(attrs={'class': 'form-select'}),
            'timezone': forms.Select(attrs={'class': 'form-select'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-input'}),
            'contact_preference': forms.Select(attrs={'class': 'form-select'}),
            'sex': forms.Select(attrs={'class': 'form-select'}),
            'sex_other': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Please specify'}),
            'sexual_orientation': forms.Select(attrs={'class': 'form-select'}),
            'sexual_orientation_other': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Please specify'}),
            'ethnicity': forms.Select(attrs={'class': 'form-select'}),
            'ethnicity_other': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Please specify'}),
            'study_area': forms.Select(attrs={'class': 'form-select'}),
            'study_area_other': forms.TextInput(attrs={'class': 'form-input'}),
            'level_of_study': forms.Select(attrs={'class': 'form-select'}),
            'grades': forms.Select(attrs={'class': 'form-select'}),
            'grades_other': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Please specify'}),
            'date_achieved': forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
            'has_learning_difficulty': forms.Select(attrs={'class': 'form-select'}),
            'learning_difficulty_details': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 3}),
            'job_role': forms.TextInput(attrs={'class': 'form-input'}),
            'industry': forms.Select(attrs={'class': 'form-select'}),
            'industry_other': forms.TextInput(attrs={'class': 'form-input'}),
            'duration': forms.Select(attrs={'class': 'form-select'}),
            'key_skills': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 3}),
            'cv_file': forms.FileInput(attrs={'class': 'form-file-input'}),
            'initial_assessment_date': forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
            'initial_assessment_english_score': forms.NumberInput(attrs={'class': 'form-input', 'min': '0', 'max': '100', 'step': '0.01'}),
            'initial_assessment_maths_score': forms.NumberInput(attrs={'class': 'form-input', 'min': '0', 'max': '100', 'step': '0.01'}),
            'initial_assessment_subject_score': forms.NumberInput(attrs={'class': 'form-input', 'min': '0', 'max': '100', 'step': '0.01'}),
            'initial_assessment_other_score': forms.NumberInput(attrs={'class': 'form-input', 'min': '0', 'max': '100', 'step': '0.01'}),
            'diagnostic_assessment_date': forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
            'diagnostic_assessment_english_score': forms.NumberInput(attrs={'class': 'form-input', 'min': '0', 'max': '100', 'step': '0.01'}),
            'diagnostic_assessment_maths_score': forms.NumberInput(attrs={'class': 'form-input', 'min': '0', 'max': '100', 'step': '0.01'}),
            'diagnostic_assessment_subject_score': forms.NumberInput(attrs={'class': 'form-input', 'min': '0', 'max': '100', 'step': '0.01'}),
            'diagnostic_assessment_other_score': forms.NumberInput(attrs={'class': 'form-input', 'min': '0', 'max': '100', 'step': '0.01'}),
            'functional_skills_date': forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
            'functional_skills_english_score': forms.NumberInput(attrs={'class': 'form-input', 'min': '0', 'max': '100', 'step': '0.01'}),
            'functional_skills_maths_score': forms.NumberInput(attrs={'class': 'form-input', 'min': '0', 'max': '100', 'step': '0.01'}),
            'functional_skills_other_score': forms.NumberInput(attrs={'class': 'form-input', 'min': '0', 'max': '100', 'step': '0.01'}),
            'statement_of_purpose_file': forms.FileInput(attrs={'class': 'form-file-input'}),
            'reason_for_pursuing_course': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 3}),
            'career_objectives': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 3}),
            'relevant_past_work': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        
        # Import here to avoid circular imports
        from business.models import Business
        
        # Determine if this is a self-edit scenario
        self.is_self_edit = (self.request and self.instance and self.instance.pk and 
                            self.request.user.id == self.instance.pk)
        
        # Set up business field queryset
        if self.request and self.request.user.role == 'globaladmin':
            # Global Admin can assign to any business
            self.fields['business'].queryset = Business.objects.filter(is_active=True).order_by('name')
        elif self.request and self.request.user.role == 'superadmin':
            # Super Admin can assign to businesses they manage
            if hasattr(self.request.user, 'business_assignments'):
                assigned_businesses = self.request.user.business_assignments.filter(is_active=True).values_list('business', flat=True)
                self.fields['business'].queryset = Business.objects.filter(id__in=assigned_businesses, is_active=True).order_by('name')
            else:
                self.fields['business'].queryset = Business.objects.none()
        else:
            # Other users don't see business field
            self.fields['business'].queryset = Business.objects.none()

        # Set field requirements and styling
        self.fields['given_name'].required = True
        self.fields['family_name'].required = True
        self.fields['role'].required = True
        
        # Branch requirement depends on role - Super Admins don't need branches
        self.fields['branch'].required = False
        self.fields['business'].required = False

        # Add help text
        self.fields['username'].help_text = "Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only."
        self.fields['email'].help_text = "Required. Enter a valid email address."
        self.fields['role'].help_text = "Select the user's role in the system."
        self.fields['branch'].help_text = "Select the branch this user belongs to (not required for Super Admin)."
        self.fields['business'].help_text = "Select the business for Super Admin assignment."
        self.fields['timezone'].help_text = "Select your preferred timezone"

        # Set up timezone choices
        self.fields['timezone'].widget.choices = [(tz, tz) for tz in pytz.common_timezones]

        # Set timezone initial value from user's timezone preference
        if self.instance and hasattr(self.instance, 'timezone_preference'):
            try:
                timezone_pref = getattr(self.instance, 'timezone_preference', None)
                if timezone_pref and timezone_pref.timezone:
                    self.fields['timezone'].initial = timezone_pref.timezone
                else:
                    # Fallback to user's timezone field
                    self.fields['timezone'].initial = self.instance.timezone
            except Exception:
                # If there's any error accessing timezone_preference, fallback to user's timezone field
                self.fields['timezone'].initial = self.instance.timezone
        elif self.instance and self.instance.timezone:
            self.fields['timezone'].initial = self.instance.timezone

        # Handle self-editing restrictions
        if self.is_self_edit:
            # Users editing their own profile cannot change role or branch
            self.fields['role'].disabled = True
            self.fields['role'].widget.attrs['readonly'] = True
            self.fields['branch'].disabled = True
            self.fields['branch'].widget.attrs['readonly'] = True
            
            # For super admin users editing themselves, also disable business field
            if self.request.user.role == 'superadmin':
                self.fields['business'].disabled = True
                self.fields['business'].widget.attrs['readonly'] = True
            
            # Set current values for disabled fields
            if self.instance:
                self.fields['role'].initial = self.instance.role
                self.fields['branch'].initial = self.instance.branch
                if self.instance.role == 'superadmin':
                    # Get the business from business_assignments relationship
                    business_assignment = self.instance.business_assignments.filter(is_active=True).first()
                    if business_assignment:
                        self.fields['business'].initial = business_assignment.business

        # Handle branch and role choices based on user role (only for non-self-edit scenarios)
        if self.request and self.request.user and not self.is_self_edit:
            if self.request.user.role == 'globaladmin':
                # Global Admin can assign to any branch
                self.fields['branch'].queryset = Branch.objects.all().order_by('name')
            elif self.request.user.role == 'superadmin':
                # Super Admin: show branches within their business allocation, or all branches as fallback
                if hasattr(self.request.user, 'business_assignments'):
                    assigned_businesses = self.request.user.business_assignments.filter(is_active=True).values_list('business', flat=True)
                    branches = Branch.objects.filter(business__in=assigned_businesses).order_by('name')
                    # If no branches found within business assignments, show all branches as fallback
                    if not branches.exists():
                        branches = Branch.objects.all().order_by('name')
                    self.fields['branch'].queryset = branches
                else:
                    # If no business assignments, show all branches
                    self.fields['branch'].queryset = Branch.objects.all().order_by('name')
            elif not self.request.user.is_superuser:
                # For non-superusers, set their branch and make it read-only
                self.fields['branch'].queryset = Branch.objects.filter(id=self.request.user.branch_id)
                self.fields['branch'].initial = self.request.user.branch
                self.fields['branch'].disabled = True
                self.fields['branch'].widget.attrs['readonly'] = True
            else:
                # For superusers, show all branches
                self.fields['branch'].queryset = Branch.objects.all().order_by('name')
        elif self.is_self_edit:
            # For self-edit, set limited queryset to current user's branch
            if self.instance and self.instance.branch:
                self.fields['branch'].queryset = Branch.objects.filter(id=self.instance.branch.id)
            else:
                self.fields['branch'].queryset = Branch.objects.none()

        # Ensure the current role of the user being edited is always a valid choice
        if self.instance and self.instance.pk and hasattr(self.instance, 'role') and self.instance.role:
            current_role = self.instance.role
            current_choices = dict(self.fields['role'].choices)
            
            if current_role not in current_choices:
                # Add the current role to the choices if it's not already there
                all_choices = dict(CustomUser.ROLE_CHOICES)
                if current_role in all_choices:
                    new_choices = list(self.fields['role'].choices)
                    new_choices.append((current_role, all_choices[current_role]))
                    self.fields['role'].choices = new_choices

        # Ensure password fields are not required in edit mode
        if self.is_self_edit or (self.instance and self.instance.pk):
            # Remove required attribute from password fields in edit mode
            if 'password1' in self.fields:
                self.fields['password1'].required = False
                self.fields['password1'].widget.attrs.pop('required', None)
            if 'password2' in self.fields:
                self.fields['password2'].required = False
                self.fields['password2'].widget.attrs.pop('required', None)

        # Ensure the branch field has the correct initial value when editing existing users
        if self.instance and self.instance.pk and self.instance.branch:
            current_branch = self.instance.branch
            # Make sure the user's current branch is included in the queryset
            if current_branch not in self.fields['branch'].queryset:
                # Add the current branch to the queryset if it's not already there
                self.fields['branch'].queryset = self.fields['branch'].queryset | Branch.objects.filter(id=current_branch.id)
            
            # Set the initial value to the user's current branch
            self.fields['branch'].initial = current_branch

    def clean_branch(self):
        """Clean branch field, ensuring it's set even if disabled in form"""
        branch = self.cleaned_data.get('branch')
        
        # For self-editing scenarios, users keep their current branch
        if self.is_self_edit:
            return self.instance.branch if self.instance else branch
        
        # For Global Admin users, branch is OPTIONAL - they can manage users in any branch
        if self.request and self.request.user.role == 'globaladmin':
            # Global Admin can leave branch empty or select any branch
            return branch
        
        # For superadmins, branch selection is mandatory
        if self.request and self.request.user.role == 'superadmin' and not branch:
            raise forms.ValidationError('Branch selection is required.')
            
        # For non-superusers, use their branch if not set
        if not branch and self.request and self.request.user.role not in ['superadmin', 'globaladmin']:
            return self.request.user.branch
            
        return branch

    def clean_role(self):
        """Clean role field, ensuring proper restrictions are enforced"""
        role = self.cleaned_data.get('role')
        if not role:
            raise forms.ValidationError('Role is required.')
            
        # Allow users to keep their current role even if it wouldn't normally be available
        if self.instance and self.instance.pk and hasattr(self.instance, 'role') and role == self.instance.role:
            return role
        
        # Skip role validation for self-editing scenarios - users can't change their own role anyway
        if self.is_self_edit:
            return role
            
        if self.request and self.request.user:
            user = self.request.user
            
            # Global Admin users bypass ALL role restrictions - they can assign any role
            if user.role == 'globaladmin':
                return role
            
            # Apply business rule restrictions for non-Global Admin users
            # Super admin users cannot assign globaladmin roles
            if user.role == 'superadmin' and role == 'globaladmin':
                raise forms.ValidationError('Super admin users are not allowed to assign global admin roles.')
            
            # Admin users cannot assign superadmin or globaladmin roles
            elif user.role == 'admin' and role in ['superadmin', 'globaladmin']:
                # Exception: allow admin to keep their own admin role when editing themselves
                if not (self.instance and self.instance.pk == user.pk and role == 'admin'):
                    raise forms.ValidationError('Admin users are not allowed to assign super admin or global admin roles.')
            
            # Instructors can only assign learner roles
            if user.role == 'instructor' and role not in ['learner']:
                raise forms.ValidationError('Instructors can only assign learner roles.')
        
        # Check branch user limits (skip for Global Admin and superadmin, and self-edit)
        if (self.request and self.request.user.role not in ['globaladmin', 'superadmin'] and 
            not self.is_self_edit and role in ['admin', 'instructor', 'learner']):
            branch = self.cleaned_data.get('branch')
            if branch:
                # Import here to avoid circular imports
                from branches.models import BranchUserLimits
                
                # Get or create user limits for this branch
                user_limits, created = BranchUserLimits.objects.get_or_create(branch=branch)
                
                # For existing users, if role is changed, check limits
                if self.instance and self.instance.pk and hasattr(self.instance, 'role') and role != self.instance.role:
                    if user_limits.is_limit_reached(role):
                        role_display = dict(self.fields['role'].choices).get(role, role)
                        raise forms.ValidationError(f'The {role_display} user limit for this branch has been reached.')
                
                # For new users, always check limits
                if not self.instance or not self.instance.pk:
                    if user_limits.is_limit_reached(role):
                        role_display = dict(self.fields['role'].choices).get(role, role)
                        raise forms.ValidationError(f'The {role_display} user limit for this branch has been reached.')
        
        return role

    def clean_password1(self):
        """Override password1 validation to skip Django's built-in validators when field is empty"""
        password1 = self.cleaned_data.get('password1')
        if not password1:
            # If password is empty, don't validate - user is not changing password
            return password1
        
        # Only run Django's built-in password validation if password is provided
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError
        
        try:
            validate_password(password1, self.instance)
        except ValidationError as e:
            raise forms.ValidationError(e.messages)
        
        return password1
    
    def clean_password2(self):
        """Override password2 validation to skip when field is empty"""
        password2 = self.cleaned_data.get('password2')
        if not password2:
            # If password is empty, don't validate - user is not changing password
            return password2
        
        # Only run Django's built-in password validation if password is provided
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError
        
        try:
            validate_password(password2, self.instance)
        except ValidationError as e:
            raise forms.ValidationError(e.messages)
        
        return password2

    def clean(self):
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
        
        # Additional check for username + role combination
        if username and role:
            existing_username_query = CustomUser.objects.filter(
                username=username,
                is_active=True
            )
            
            # Exclude current user if editing
            if self.instance and self.instance.pk:
                existing_username_query = existing_username_query.exclude(pk=self.instance.pk)
                
            if existing_username_query.exists():
                existing_user = existing_username_query.first()
                if existing_user.role == role:
                    if branch and existing_user.branch == branch:
                        raise forms.ValidationError(
                            f"A user with username '{username}' and role '{dict(CustomUser.ROLE_CHOICES)[role]}' "
                            f"already exists in branch '{branch.name}'. Cannot create duplicate user role accounts."
                        )
                    elif not branch and not existing_user.branch:
                        raise forms.ValidationError(
                            f"A user with username '{username}' and role '{dict(CustomUser.ROLE_CHOICES)[role]}' "
                            f"already exists. Cannot create duplicate user role accounts."
                        )
        
        # For Global Admin role users, ensure no other user has the same email with Global Admin role
        if role == 'globaladmin' and email:
            existing_globaladmin = CustomUser.objects.filter(
                email=email,
                role='globaladmin',
                is_active=True
            )
            
            # Exclude current user if editing  
            if self.instance and self.instance.pk:
                existing_globaladmin = existing_globaladmin.exclude(pk=self.instance.pk)
                
            if existing_globaladmin.exists():
                raise forms.ValidationError(
                    f"A Global Admin user with email '{email}' already exists. "
                    f"Cannot create duplicate Global Admin accounts."
                )
        
        # Validate business field for Super Admin users
        business = cleaned_data.get('business')
        if role == 'superadmin':
            if not business:
                raise forms.ValidationError("Business selection is required for Super Admin users.")
        elif role != 'superadmin' and business:
            # Clear business for non-Super Admin users
            cleaned_data['business'] = None
        
        # Handle password change validation - only validate if passwords are actually provided
        password1 = cleaned_data.get('password1')
        password2 = cleaned_data.get('password2')
        
        # Check if user is attempting to change password (both fields must have meaningful content)
        # Only validate if both password fields have actual content (not empty or just whitespace)
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
            # Validate password match
            if password1 != password2:
                raise forms.ValidationError("The two password fields didn't match.")
            
            # Validate password strength
            if len(password1) < 8:
                raise forms.ValidationError("Password must be at least 8 characters long.")
            
            # Additional password strength validation
            if not any(c.isupper() for c in password1):
                raise forms.ValidationError("Password must contain at least one uppercase letter.")
            if not any(c.islower() for c in password1):
                raise forms.ValidationError("Password must contain at least one lowercase letter.")
            if not any(c.isdigit() for c in password1):
                raise forms.ValidationError("Password must contain at least one number.")
            if not any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in password1):
                raise forms.ValidationError("Password must contain at least one special character.")
        
        return cleaned_data

    def save(self, commit=True):
        """Save the form data to the model instance."""
        user = super().save(commit=False)
        
        # Map form fields to model fields where names don't exactly match
        if 'given_name' in self.cleaned_data:
            given_name = self.cleaned_data.get('given_name')
            user.first_name = given_name
            user.given_names = given_name  # Also update the custom field for consistency
            
        if 'family_name' in self.cleaned_data:
            family_name = self.cleaned_data.get('family_name')
            user.last_name = family_name
            user.family_name = family_name  # Also update the custom field for consistency
            
        # Set fields from form data
        user.role = self.cleaned_data.get('role', user.role)
        user.branch = self.cleaned_data.get('branch', user.branch)
        
        # Handle business field for Super Admin users
        if 'business' in self.cleaned_data:
            business = self.cleaned_data.get('business')
            if business and user.role == 'superadmin':
                # Handle business assignment through BusinessUserAssignment model
                from business.models import BusinessUserAssignment
                
                # Deactivate any existing business assignments
                user.business_assignments.filter(is_active=True).update(is_active=False)
                
                # Create or reactivate business assignment
                assignment, created = BusinessUserAssignment.objects.get_or_create(
                    business=business,
                    user=user,
                    defaults={'assigned_by': self.request.user if self.request else None, 'is_active': True}
                )
                if not created and not assignment.is_active:
                    assignment.is_active = True
                    assignment.assigned_by = self.request.user if self.request else None
                    assignment.save()
        
        # Set timezone if provided
        if 'timezone' in self.cleaned_data:
            timezone_value = self.cleaned_data.get('timezone')
            user.timezone = timezone_value
            
            # Also update UserTimezone model if it exists
            try:
                if hasattr(user, 'timezone_preference'):
                    timezone_pref, created = user.timezone_preference.get_or_create(
                        defaults={'timezone': timezone_value, 'auto_detected': False}
                    )
                    if not created:
                        timezone_pref.timezone = timezone_value
                        timezone_pref.auto_detected = False
                        timezone_pref.save()
                else:
                    # Create UserTimezone record if it doesn't exist
                    from .models import UserTimezone
                    UserTimezone.objects.get_or_create(
                        user=user,
                        defaults={'timezone': timezone_value, 'auto_detected': False}
                    )
            except Exception as e:
                # Log the error but don't fail the form save
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Failed to update UserTimezone for user {user.username}: {str(e)}")
        
        # Handle password change if provided
        password = self.cleaned_data.get('password1')
        if password:
            user.set_password(password)
            
        # Handle file fields for all roles (not just learners)
        if self.cleaned_data.get('cv_file'):
            user.cv_file = self.cleaned_data['cv_file']
            
        if self.cleaned_data.get('statement_of_purpose_file'):
            user.statement_of_purpose_file = self.cleaned_data['statement_of_purpose_file']
            
        # Save the changes
        if commit:
            user.save()
            
        return user

class CustomPasswordChangeForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Style the password fields
        for field in ['old_password', 'new_password1', 'new_password2']:
            self.fields[field].widget.attrs.update({
                'class': 'w-full px-4 py-2 bg-gray-700 text-white rounded border border-gray-600 focus:border-blue-500 focus:ring-1 focus:ring-blue-500'
            })
        
        # Update help texts
        self.fields['old_password'].help_text = "Enter your current password"
        self.fields['new_password1'].help_text = "Enter your new password"
        self.fields['new_password2'].help_text = "Confirm your new password"

class AdminPasswordChangeForm(SetPasswordForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Style the password fields
        for field in ['new_password1', 'new_password2']:
            self.fields[field].widget.attrs.update({
                'class': 'w-full px-4 py-2 bg-gray-700 text-white rounded border border-gray-600 focus:border-blue-500 focus:ring-1 focus:ring-blue-500'
            })
        
        # Update help texts
        self.fields['new_password1'].help_text = "Enter new password"
        self.fields['new_password2'].help_text = "Confirm new password"

class SimpleRegistrationForm(UserCreationForm):
    """Simple registration form for public learner registration"""
    
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={'class': 'form-input', 'placeholder': 'your@email.com'}),
        help_text="Email Address - required for communication"
    )
    
    first_name = forms.CharField(
        required=True,
        max_length=30,
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'First Name'}),
        help_text="Your first name"
    )
    
    last_name = forms.CharField(
        required=True,
        max_length=30,
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Last Name'}),
        help_text="Your last name"
    )
    
    phone_number = forms.CharField(
        required=False,
        max_length=20,
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': '+1234567890'}),
        help_text="Phone Number - optional"
    )
    
    terms_acceptance = forms.BooleanField(
        required=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
        help_text="You must agree to the Terms of Service and Privacy Policy",
        error_messages={'required': 'You must agree to the Terms of Service and Privacy Policy to create an account.'}
    )

    class Meta:
        model = CustomUser
        fields = ['username', 'first_name', 'last_name', 'email', 'phone_number', 'password1', 'password2', 'terms_acceptance']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Username'}),
        }

    def __init__(self, *args, **kwargs):
        self.branch = kwargs.pop('branch', None)
        super().__init__(*args, **kwargs)
        
        # Set custom widget attributes
        for field_name in ['password1', 'password2']:
            if field_name in self.fields:
                self.fields[field_name].widget.attrs.update({'class': 'form-input'})

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        user.phone_number = self.cleaned_data.get('phone_number', '')
        user.role = 'learner'  # Always learner for public registration
        user.is_active = True  # Auto-activate learner accounts
        
        # Assign to branch if provided
        if self.branch:
            user.branch = self.branch
        
        if commit:
            user.save()
        return user


class ManualVAKScoreForm(forms.ModelForm):
    """Form for instructors/admins to manually enter VAK scores"""
    
    class Meta:
        model = ManualVAKScore
        fields = ['visual_score', 'auditory_score', 'kinesthetic_score']
        widgets = {
            'visual_score': forms.NumberInput(attrs={
                'class': 'form-input',
                'min': '0',
                'max': '100',
                'step': '0.1',
                'placeholder': 'Visual Score (0-100)'
            }),
            'auditory_score': forms.NumberInput(attrs={
                'class': 'form-input',
                'min': '0',
                'max': '100',
                'step': '0.1',
                'placeholder': 'Auditory Score (0-100)'
            }),
            'kinesthetic_score': forms.NumberInput(attrs={
                'class': 'form-input',
                'min': '0',
                'max': '100',
                'step': '0.1',
                'placeholder': 'Kinesthetic Score (0-100)'
            })
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Add help text
        self.fields['visual_score'].help_text = 'Visual learning style score (0-100)'
        self.fields['auditory_score'].help_text = 'Auditory learning style score (0-100)'
        self.fields['kinesthetic_score'].help_text = 'Kinesthetic learning style score (0-100)'
    
    def clean(self):
        cleaned_data = super().clean()
        visual_score = cleaned_data.get('visual_score')
        auditory_score = cleaned_data.get('auditory_score')
        kinesthetic_score = cleaned_data.get('kinesthetic_score')
        
        # Ensure at least one score is provided
        if not any([visual_score, auditory_score, kinesthetic_score]):
            raise forms.ValidationError("At least one VAK score must be provided.")
        
        # Validate score ranges
        for score, label in [(visual_score, 'Visual'), (auditory_score, 'Auditory'), (kinesthetic_score, 'Kinesthetic')]:
            if score is not None and (score < 0 or score > 100):
                raise forms.ValidationError(f"{label} score must be between 0 and 100.")
        
        return cleaned_data

class ManualAssessmentEntryForm(forms.ModelForm):
    """Form for instructors/admins to manually enter assessment data"""
    
    class Meta:
        model = ManualAssessmentEntry
        fields = ['subject', 'score', 'notes', 'assessment_date']
        widgets = {
            'subject': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'e.g., Mathematics, English, Science'
            }),
            'score': forms.NumberInput(attrs={
                'class': 'form-input',
                'min': '0',
                'max': '100',
                'step': '0.01',
                'placeholder': 'Score (0-100)'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-textarea',
                'rows': 3,
                'placeholder': 'Optional notes about the assessment'
            }),
            'assessment_date': forms.DateInput(attrs={
                'class': 'form-input',
                'type': 'date'
            })
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Add help text
        self.fields['subject'].help_text = 'Subject or assessment name'
        self.fields['score'].help_text = 'Assessment score (0-100)'
        self.fields['notes'].help_text = 'Optional notes about the assessment'
        self.fields['assessment_date'].help_text = 'Date of assessment (optional)'
        
        # Make assessment_date optional
        self.fields['assessment_date'].required = False
        self.fields['notes'].required = False
    
    def clean_subject(self):
        subject = self.cleaned_data.get('subject')
        if subject:
            subject = subject.strip()
            if not subject:
                raise forms.ValidationError("Subject cannot be empty.")
        return subject
    
    def clean_score(self):
        score = self.cleaned_data.get('score')
        if score is not None:
            if score < 0 or score > 100:
                raise forms.ValidationError("Score must be between 0 and 100.")
        return score


class ManualAssessmentEntryFormSet(forms.BaseFormSet):
    """FormSet for handling multiple manual assessment entries"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
    def clean(self):
        """Validate the entire formset"""
        if any(self.errors):
            return
        
        subjects = []
        valid_forms = 0
        
        for form in self.forms:
            if form.cleaned_data and not form.cleaned_data.get('DELETE', False):
                subject = form.cleaned_data.get('subject')
                if subject:
                    subject = subject.strip().lower()
                    if subject in subjects:
                        raise forms.ValidationError("Subjects must be unique. You cannot add the same subject multiple times.")
                    subjects.append(subject)
                    valid_forms += 1
        
        if valid_forms == 0:
            raise forms.ValidationError("At least one valid assessment entry is required.")


# Create the formset factory
ManualAssessmentEntryFormSetFactory = forms.formset_factory(
    ManualAssessmentEntryForm,
    formset=ManualAssessmentEntryFormSet,
    extra=1,
    can_delete=True,
    min_num=0,
    validate_min=False
)
