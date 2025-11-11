from django.contrib.auth.models import AbstractUser, Permission
from django.db import models
from branches.models import Branch
from django.core.exceptions import ValidationError
from role_management.models import RoleCapability, UserRole
from django.core.validators import RegexValidator, MinValueValidator, MaxValueValidator
from django.utils import timezone
from datetime import timedelta
import uuid
import logging
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse
from django.contrib.sites.models import Site
import pytz
from typing import Dict, List, Optional, Any, Union, Tuple, TYPE_CHECKING
from django.db.models import QuerySet
from django.http import HttpRequest

if TYPE_CHECKING:
    from courses.models import Course, CourseEnrollment, TopicProgress
    from quiz.models import QuizAttempt, Quiz

class CustomUser(AbstractUser):
    ROLE_CHOICES = [
        ('globaladmin', 'Global Admin'),
        ('superadmin', 'SuperAdmin'),
        ('admin', 'Admin'),
        ('instructor', 'Instructor'),
        ('learner', 'Learner'),
    ]

    # Gender choices
    SEX_CHOICES = [
        ('Male', 'Male'),
        ('Female', 'Female'),
        ('Other', 'Other'),
        ('Prefer Not to Say', 'Prefer Not to Say'),
    ]
    
    # Sexual orientation choices
    SEXUAL_ORIENTATION_CHOICES = [
        ('Heterosexual or Straight', 'Heterosexual or Straight'),
        ('Gay or Lesbian', 'Gay or Lesbian'),
        ('Bisexual', 'Bisexual'),
        ('Other sexual orientation', 'Other sexual orientation'),
    ]
    
    # Ethnicity choices
    ETHNICITY_CHOICES = [
        ('White British', 'White British'),
        ('White Irish', 'White Irish'),
        ('White Other', 'White Other'),
        ('Black African', 'Black African'),
        ('Black Caribbean', 'Black Caribbean'),
        ('Black Other', 'Black Other'),
        ('Asian Indian', 'Asian Indian'),
        ('Asian Pakistani', 'Asian Pakistani'),
        ('Asian Bangladeshi', 'Asian Bangladeshi'),
        ('Asian Chinese', 'Asian Chinese'),
        ('Asian Other', 'Asian Other'),
        ('Mixed White and Black Caribbean', 'Mixed White and Black Caribbean'),
        ('Mixed White and Black African', 'Mixed White and Black African'),
        ('Mixed White and Asian', 'Mixed White and Asian'),
        ('Mixed Other', 'Mixed Other'),
        ('Other Ethnic Group', 'Other Ethnic Group'),
        ('Prefer Not to Say', 'Prefer Not to Say'),
    ]
    
    # Contact preference choices
    CONTACT_PREFERENCE_CHOICES = [
        ('Email', 'Email'),
        ('Phone', 'Phone'),
        ('None', 'None'),
    ]
    
    # Study area choices
    STUDY_AREA_CHOICES = [
        ('Business and Management', 'Business and Management'),
        ('Engineering', 'Engineering'),
        ('Health and Social Care', 'Health and Social Care'),
        ('Information Technology', 'Information Technology'),
        ('Construction', 'Construction'),
        ('Education and Training', 'Education and Training'),
        ('Arts and Media', 'Arts and Media'),
        ('Science and Mathematics', 'Science and Mathematics'),
        ('Hospitality and Catering', 'Hospitality and Catering'),
        ('Other', 'Other'),
    ]
    
    # Level of study choices
    LEVEL_OF_STUDY_CHOICES = [
        ('Pre Entry', 'Pre Entry'),
        ('Entry Level 1', 'Entry Level 1'),
        ('Entry Level 2', 'Entry Level 2'),
        ('Entry Level 3', 'Entry Level 3'),
        ('Level 1', 'Level 1'),
        ('Level 2', 'Level 2'),
        ('Level 3', 'Level 3'),
        ('Level 4', 'Level 4'),
        ('Level 5', 'Level 5'),
        ('Level 6', 'Level 6'),
        ('Level 7', 'Level 7'),
        ('Level 8', 'Level 8'),
    ]
    
    # Grades choices
    GRADES_CHOICES = [
        ('No Formal Qualification', 'No Formal Qualification'),
        ('High School Incomplete', 'High School Incomplete'),
        ('High School Diploma / Secondary School Certificate', 'High School Diploma / Secondary School Certificate'),
        ('Vocational Qualification', 'Vocational Qualification'),
        ('Certificate', 'Certificate'),
        ('Diploma', 'Diploma'),
        ('Advanced Diploma', 'Advanced Diploma'),
        ('Associate Degree', 'Associate Degree'),
        ('Bachelor\'s Degree', 'Bachelor\'s Degree'),
        ('Postgraduate Certificate', 'Postgraduate Certificate'),
        ('Postgraduate Diploma', 'Postgraduate Diploma'),
        ('Master\'s Degree', 'Master\'s Degree'),
        ('Doctorate / PhD', 'Doctorate / PhD'),
        ('A+', 'A+'),
        ('A', 'A'),
        ('A−', 'A−'),
        ('B+', 'B+'),
        ('B', 'B'),
        ('B−', 'B−'),
        ('C+', 'C+'),
        ('C', 'C'),
        ('C−', 'C−'),
        ('D', 'D'),
        ('E', 'E'),
        ('F / Fail', 'F / Fail'),
        ('Pass', 'Pass'),
        ('Merit', 'Merit'),
        ('Distinction', 'Distinction'),
        ('Honours (First Class / Upper Second / etc.)', 'Honours (First Class / Upper Second / etc.)'),
        ('Other (Please Specify)', 'Other (Please Specify)'),
    ]
    
    # Learning difficulty choices
    LEARNING_DIFFICULTY_CHOICES = [
        ('Yes', 'Yes'),
        ('No', 'No'),
    ]
    
    # Industry choices
    INDUSTRY_CHOICES = [
        ('Office and Administration', 'Office and Administration'),
        ('Customer Service and Retail', 'Customer Service and Retail'),
        ('Construction and Trades', 'Construction and Trades'),
        ('Healthcare', 'Healthcare'),
        ('Education', 'Education'),
        ('Information Technology', 'Information Technology'),
        ('Manufacturing', 'Manufacturing'),
        ('Hospitality and Catering', 'Hospitality and Catering'),
        ('Finance and Banking', 'Finance and Banking'),
        ('Other', 'Other'),
    ]
    
    # Duration choices
    DURATION_CHOICES = [
        ('Less than 6 months', 'Less than 6 months'),
        ('6 months to 1 year', '6 months to 1 year'),
        ('1-2 years', '1-2 years'),
        ('2-5 years', '2-5 years'),
        ('Over 5 years', 'Over 5 years'),
    ]
    
    # Functional skills level choices
    FUNCTIONAL_SKILLS_LEVEL_CHOICES = [
        ('Entry Level', 'Entry Level'),
        ('Level 1', 'Level 1'),
        ('Level 2', 'Level 2'),
    ]

    # Override email field to make it unique and required
    email = models.EmailField(
        unique=True,
        blank=False,
        null=False,
        help_text="Email address - must be unique across all users"
    )

    # Basic fields
    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default='learner',
        help_text="Role of the user (e.g., admin, instructor, learner)."
    )

    branch = models.ForeignKey(
        Branch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='users',
        help_text="The branch this user belongs to. Not required for Global Admin users."
    )

    language = models.CharField(
        max_length=10,
        default='en',
        help_text="Preferred language of the user."
    )

    timezone = models.CharField(
        max_length=50,
        default='UTC',
        help_text="Preferred timezone of the user."
    )
    
    # Timezone detection tracking
    timezone_detected_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the user's timezone was first auto-detected"
    )
    
    # Terms and Privacy Policy acceptance tracking
    terms_accepted_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Date and time when the user accepted Terms of Service and Privacy Policy"
    )
    
    # Profile image
    profile_image = models.ImageField(
        upload_to='profile_images/',
        null=True,
        blank=True,
        help_text="Profile picture for the user. Recommended size: 300x300 pixels."
    )

    user_permissions = models.ManyToManyField(
        Permission,
        related_name="customuser_permissions_set",
        blank=True,
        help_text="Specific permissions for this user."
    )

    assigned_instructor = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_students',
        limit_choices_to={'role': 'instructor'},
        help_text="The instructor assigned to this learner."
    )
    
    # Basic account information
    phone_number = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        help_text="Contact phone number"
    )
    
    # Personal Information Tab
    unique_learner_number = models.BigIntegerField(
        unique=True,
        null=True,
        blank=True,
        help_text="Unique Learner Number (ULN)"
    )
    
    family_name = models.CharField(
        max_length=800,
        null=True,
        blank=True,
        help_text="Family name/surname"
    )
    
    given_names = models.CharField(
        max_length=800,
        null=True,
        blank=True,
        help_text="Given name(s)/first name(s)"
    )
    
    date_of_birth = models.DateField(
        null=True,
        blank=True,
        help_text="Date of birth (YYYY-MM-DD)"
    )
    
    sex = models.CharField(
        max_length=20,
        choices=SEX_CHOICES,
        null=True,
        blank=True,
        help_text="Gender"
    )
    
    sex_other = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text="Other sex/gender if 'Other' is selected"
    )
    
    sexual_orientation = models.CharField(
        max_length=50,
        choices=SEXUAL_ORIENTATION_CHOICES,
        null=True,
        blank=True,
        help_text="Sexual orientation"
    )
    
    sexual_orientation_other = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text="Other sexual orientation if 'Other sexual orientation' is selected"
    )
    
    ethnicity = models.CharField(
        max_length=50,
        choices=ETHNICITY_CHOICES,
        null=True,
        blank=True,
        help_text="Ethnicity"
    )
    
    ethnicity_other = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text="Other ethnicity if any 'Other' ethnicity option is selected"
    )
    
    postcode_validator = RegexValidator(
        regex=r'^[A-Z]{1,2}[0-9][A-Z0-9]? ?[0-9][A-Z]{2}$|^ZZ99 9ZZ$',
        message="Enter a valid UK postcode or ZZ99 9ZZ if unknown"
    )
    
    current_postcode = models.CharField(
        max_length=10,
        validators=[postcode_validator],
        null=True,
        blank=True,
        help_text="Current UK postcode or ZZ99 9ZZ if unknown"
    )
    
    # Address fields
    address_line1 = models.CharField(
        max_length=800,
        null=True,
        blank=True,
        help_text="Street address/house number"
    )
    
    address_line2 = models.CharField(
        max_length=800,
        null=True,
        blank=True,
        help_text="Apartment/Suite/Unit/Building"
    )
    
    city = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text="City or town"
    )
    
    county = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text="County/state/province"
    )
    
    country = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        default="United Kingdom",
        help_text="Country"
    )
    
    is_non_uk_address = models.BooleanField(
        default=False,
        help_text="Whether the address is outside the UK"
    )
    
    contact_preference = models.CharField(
        max_length=10,
        choices=CONTACT_PREFERENCE_CHOICES,
        null=True,
        blank=True,
        help_text="Preferred method of contact"
    )
    
    # Education Background Tab
    study_area = models.CharField(
        max_length=50,
        choices=STUDY_AREA_CHOICES,
        null=True,
        blank=True,
        help_text="Area of study"
    )
    
    study_area_other = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text="Other study area if 'Other' is selected"
    )
    
    level_of_study = models.CharField(
        max_length=50,
        choices=LEVEL_OF_STUDY_CHOICES,
        null=True,
        blank=True,
        help_text="Level of study"
    )
    
    grades = models.CharField(
        max_length=100,
        choices=GRADES_CHOICES,
        null=True,
        blank=True,
        help_text="Grades achieved"
    )
    
    grades_other = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text="Other grades/qualification if 'Other (Please Specify)' is selected"
    )
    
    date_achieved = models.DateField(
        null=True,
        blank=True,
        help_text="Date qualification was achieved (YYYY-MM-DD)"
    )
    
    has_learning_difficulty = models.CharField(
        max_length=3,
        choices=LEARNING_DIFFICULTY_CHOICES,
        null=True,
        blank=True,
        help_text="Whether the learner has any learning difficulties"
    )
    
    learning_difficulty_details = models.TextField(
        null=True,
        blank=True,
        help_text="Details of learning difficulty if applicable"
    )
    
    # Multiple Education Records (JSON storage)
    education_data = models.JSONField(
        null=True,
        blank=True,
        help_text="Multiple education records stored as JSON"
    )
    
    # Employment History Tab
    job_role = models.CharField(
        max_length=800,
        null=True,
        blank=True,
        help_text="Current or most recent job role"
    )
    
    industry = models.CharField(
        max_length=50,
        choices=INDUSTRY_CHOICES,
        null=True,
        blank=True,
        help_text="Industry sector"
    )
    
    industry_other = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text="Other industry if 'Other' is selected"
    )
    
    duration = models.CharField(
        max_length=20,
        choices=DURATION_CHOICES,
        null=True,
        blank=True,
        help_text="Duration in role"
    )
    
    key_skills = models.TextField(
        null=True,
        blank=True,
        help_text="Key skills and competencies"
    )
    
    # Multiple Employment Records (JSON storage)
    employment_data = models.JSONField(
        null=True,
        blank=True,
        help_text="Multiple employment records stored as JSON"
    )
    
    cv_file = models.FileField(
        upload_to='user_files/cv/',
        null=True,
        blank=True,
        help_text="Upload CV (PDF/Word, <5MB)"
    )
    
    # Assessment Data Tab - Restructured
    # Initial Assessment fields
    initial_assessment_english = models.BooleanField(
        default=False,
        help_text="Initial assessment for English"
    )
    
    initial_assessment_maths = models.BooleanField(
        default=False,
        help_text="Initial assessment for Maths"
    )
    
    initial_assessment_subject_specific = models.BooleanField(
        default=False,
        help_text="Initial assessment for Subject Specific skills"
    )
    
    initial_assessment_other = models.BooleanField(
        default=False,
        help_text="Initial assessment for Other skills"
    )
    
    initial_assessment_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date of initial assessment"
    )
    
    # Diagnostic Assessment fields
    diagnostic_assessment_english = models.BooleanField(
        default=False,
        help_text="Diagnostic assessment for English"
    )
    
    diagnostic_assessment_maths = models.BooleanField(
        default=False,
        help_text="Diagnostic assessment for Maths"
    )
    
    diagnostic_assessment_subject_specific = models.BooleanField(
        default=False,
        help_text="Diagnostic assessment for Subject Specific skills"
    )
    
    diagnostic_assessment_other = models.BooleanField(
        default=False,
        help_text="Diagnostic assessment for Other skills"
    )
    
    diagnostic_assessment_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date of diagnostic assessment"
    )
    
    # Functional Skills fields
    functional_skills_english = models.BooleanField(
        default=False,
        help_text="Functional skills assessment for English"
    )
    
    functional_skills_maths = models.BooleanField(
        default=False,
        help_text="Functional skills assessment for Maths"
    )
    
    functional_skills_other = models.BooleanField(
        default=False,
        help_text="Functional skills assessment for Other skills"
    )
    
    functional_skills_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date of functional skills assessment"
    )
    
    # Legacy assessment fields - keep for backwards compatibility but not actively used
    initial_assessment_english_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Initial Assessment English score (0-100)"
    )
    
    initial_assessment_maths_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Initial Assessment Maths score (0-100)"
    )
    
    initial_assessment_subject_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Initial Assessment Subject Specific score (0-100)"
    )
    
    initial_assessment_other_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Initial Assessment Other score (0-100)"
    )
    
    diagnostic_assessment_english_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Diagnostic Assessment English score (0-100)"
    )
    
    diagnostic_assessment_maths_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Diagnostic Assessment Maths score (0-100)"
    )
    
    diagnostic_assessment_subject_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Diagnostic Assessment Subject score (0-100)"
    )
    
    diagnostic_assessment_other_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Diagnostic Assessment Other score (0-100)"
    )
    
    functional_skills_english_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Functional Skills English score (0-100)"
    )
    
    functional_skills_maths_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Functional Skills Maths score (0-100)"
    )
    
    functional_skills_other_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Functional Skills Other score (0-100)"
    )
    
    functional_skills_level = models.CharField(
        max_length=20,
        choices=FUNCTIONAL_SKILLS_LEVEL_CHOICES,
        null=True,
        blank=True,
        help_text="Functional Skills Level"
    )
    
    # Additional Information Tab
    statement_of_purpose_file = models.FileField(
        upload_to='user_files/statement_of_purpose/',
        null=True,
        blank=True,
        help_text="Statement of Purpose file (PDF/Word, <5MB)"
    )
    
    reason_for_pursuing_course = models.TextField(
        null=True,
        blank=True,
        help_text="Reason for pursuing this course"
    )
    
    career_objectives = models.TextField(
        null=True,
        blank=True,
        help_text="Career objectives"
    )
    
    relevant_past_work = models.TextField(
        null=True,
        blank=True,
        help_text="Relevant past work experience"
    )
    
    special_interests_and_strengths = models.TextField(
        null=True,
        blank=True,
        help_text="Special interests and strengths"
    )
    
    achievements_and_awards = models.TextField(
        null=True,
        blank=True,
        help_text="Achievements and awards"
    )

    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"
        ordering = ["-date_joined"]
        db_table = 'users_customuser'
        indexes = [
            # Dashboard performance indexes
            models.Index(fields=['role', 'is_active']),
            models.Index(fields=['branch', 'role']),
            models.Index(fields=['last_login', 'is_active']),
            models.Index(fields=['role', 'branch', 'is_active']),
            models.Index(fields=['date_joined']),
            models.Index(fields=['branch', 'date_joined']),
            # Existing indexes can be added here
        ]

    @property
    def enrolled_courses(self) -> 'QuerySet[Course]':
        """Get courses the user is enrolled in"""
        from courses.models import Course
        return Course.objects.filter(courseenrollment__user=self)

    @property
    def group_accessible_courses(self) -> 'QuerySet[Course]':
        """Get courses accessible through group membership"""
        from courses.models import Course
        return Course.objects.filter(
            accessible_groups__memberships__user=self,
            accessible_groups__memberships__is_active=True
        ).distinct()

    @property
    def instructor_courses(self) -> 'QuerySet[Course]':
        """Get courses where user is assigned as instructor"""
        from courses.models import Course
        return Course.objects.filter(instructor=self)

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.is_superuser and self.role not in ['globaladmin', 'superadmin']:
            self.role = 'superadmin'
        super().save(*args, **kwargs)

    def has_module_perms(self, app_label: str) -> bool:
        if self.is_superuser or self.role in ['globaladmin', 'superadmin']:
            return True
        if self.role == 'admin':
            return app_label in [
                'courses',
                'users'
            ]
        return False

    def has_branch_permission(self, obj: Optional[Any] = None) -> bool:
        """
        Check if user has permission to access branch-specific content
        """
        from core.utils.type_guards import safe_get_attribute, has_branch, is_django_model
        
        # Global admins have permission to all content
        if self.is_superuser or self.role == 'globaladmin':
            return True
            
        # Super admins have permission to content in their assigned businesses
        if self.role == 'superadmin':
            if obj is None:
                return True
            
            # Safely check for branch and business attributes
            obj_branch = safe_get_attribute(obj, 'branch')
            if obj_branch:
                obj_business = safe_get_attribute(obj_branch, 'business')
                if obj_business:
                    # Check if user is assigned to the business that owns this branch
                    try:
                        return self.business_assignments.filter(
                            business=obj_business, 
                            is_active=True
                        ).exists()
                    except AttributeError:
                        # User doesn't have business_assignments
                        pass
            return True
            
        # Other roles need a branch assignment
        if not self.branch:
            return False
            
        if obj is None:
            return True
            
        # Safely check if object has branch attribute and compare
        if has_branch(obj):
            return obj.branch == self.branch
            
        return False

    def has_perm(self, perm: str, obj: Optional[Any] = None) -> bool:
        from core.utils.type_guards import has_branch
        
        if self.is_superuser or self.role in ['globaladmin', 'superadmin']:
            return True
            
        # First check branch permission
        if obj and not self.has_branch_permission(obj):
            return False
            
        if self.role == 'admin':
            try:
                app_label = perm.split('.')[0]
                return self.has_module_perms(app_label)
            except (IndexError, AttributeError):
                return False
            
        if self.role in ['instructor', 'learner']:
            # Instructors and learners can only access their branch content
            if obj and has_branch(obj):
                return obj.branch == self.branch
                
        return False

    def get_accessible_objects(self, queryset: 'QuerySet[Any]') -> 'QuerySet[Any]':
        """
        Filter queryset based on user's branch access
        """
        if self.is_superuser or self.role == 'globaladmin':
            return queryset
            
        if not self.branch:
            return queryset.none()
            
        return queryset.filter(branch=self.branch)

    def is_branch_admin(self) -> bool:
        """Check if user is an admin of their branch"""
        return self.role == 'admin' and self.branch is not None

    def get_branch_instructors(self) -> Optional['QuerySet[CustomUser]']:
        """Get all instructors in the admin's branch"""
        if not self.is_branch_admin():
            return None
        return CustomUser.objects.filter(
            branch=self.branch,
            role='instructor'
        )

    def get_instructor_students(self) -> Optional['QuerySet[CustomUser]']:
        """Get all students assigned to this instructor"""
        if self.role != 'instructor':
            return None
        return CustomUser.objects.filter(
            branch=self.branch,
            role='learner',
            assigned_instructor=self
        )

    def clean(self) -> None:
        """Validate user data"""
        super().clean()
        
        # For existing users, check if role or branch has actually changed before validating
        role_changed = True
        branch_changed = True
        
        if self.pk:  # This is an existing user
            try:
                original = CustomUser.objects.get(pk=self.pk)
                role_changed = original.role != self.role
                branch_changed = original.branch != self.branch
            except CustomUser.DoesNotExist:
                # User doesn't exist yet, so it's a new user - validate everything
                pass
        
        # Only validate default branch assignment if role or branch has changed, or it's a new user
        if self.branch and (role_changed or branch_changed):
            from core.utils.default_assignments import DefaultAssignmentManager
            if DefaultAssignmentManager.is_default_branch(self.branch):
                if not DefaultAssignmentManager.can_user_access_default_branch(self):
                    raise ValidationError(f'Only Global Admin users can be assigned to default branches. User {self.username} has role: {self.role}')
        
        # Role-specific validations - only validate if role or branch has changed, or it's a new user
        if (role_changed or branch_changed) and self.role in ['admin', 'instructor', 'learner'] and not self.branch:
            # Add debugging information
            # Log validation failure for debugging
            logger = logging.getLogger(__name__)
            logger.warning(f"User clean() validation failed - Role: {self.role}, Branch: {self.branch}")
            raise ValidationError(f'{self.get_role_display()} users must be assigned to a branch')
        
        # Global admins have system-wide access and don't require branch restrictions
        # They can be assigned to any branch or left unassigned for full system access
        # (No validation needed for Global Admin branch assignments)
        
        # Check instructor assignment only if role, branch, or instructor assignment has changed
        instructor_changed = True
        if self.pk:  # Existing user
            try:
                original = CustomUser.objects.get(pk=self.pk)
                instructor_changed = original.assigned_instructor != self.assigned_instructor
            except CustomUser.DoesNotExist:
                pass
        
        if (role_changed or branch_changed or instructor_changed) and self.role == 'learner' and self.assigned_instructor:
            if self.assigned_instructor.role != 'instructor':
                raise ValidationError('Assigned instructor must have instructor role')
            if self.assigned_instructor.branch != self.branch:
                raise ValidationError('Instructor must be from the same branch')
        
        # Validate email uniqueness across all users
        if self.email:
            # Normalize email to lowercase for case-insensitive comparison
            self.email = self.email.lower()
            
            # Check for existing user with same email
            existing_user_query = CustomUser.objects.filter(
                email__iexact=self.email
            )
            
            # Exclude current user if editing
            if self.pk:
                existing_user_query = existing_user_query.exclude(pk=self.pk)
            
            if existing_user_query.exists():
                existing_user = existing_user_query.first()
                raise ValidationError(
                    f"A user with email address '{self.email}' already exists. "
                    f"Each email address can only be used for one account. "
                    f"Please use a different email address or contact support if you need help accessing your existing account."
                )

    def delete(self, *args: Any, **kwargs: Any) -> Tuple[int, Dict[str, int]]:
        """
        Enhanced delete method with comprehensive cascade deletion for User.
        This method ensures all related data is properly cleaned up when a user is deleted.
        """
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            logger.info(f"Starting comprehensive deletion for User: {self.username} (ID: {self.id})")
            
            # 1. DELETE ALL COURSE ENROLLMENTS
            try:
                from courses.models import CourseEnrollment
                enrollments = CourseEnrollment.objects.filter(user=self)
                enrollment_count = enrollments.count()
                if enrollment_count > 0:
                    logger.info(f"Deleting {enrollment_count} course enrollments")
                    enrollments.delete()
                    logger.info(f"Successfully deleted {enrollment_count} course enrollments")
            except Exception as e:
                logger.error(f"Error deleting course enrollments: {str(e)}")
            
            # 2. DELETE ALL TOPIC PROGRESS
            try:
                from courses.models import TopicProgress
                progress = TopicProgress.objects.filter(user=self)
                progress_count = progress.count()
                if progress_count > 0:
                    logger.info(f"Deleting {progress_count} topic progress records")
                    progress.delete()
                    logger.info(f"Successfully deleted {progress_count} topic progress records")
            except Exception as e:
                logger.error(f"Error deleting topic progress: {str(e)}")
            
            # 3. DELETE ALL ASSIGNMENT SUBMISSIONS
            try:
                from assignments.models import AssignmentSubmission, AssignmentFeedback
                
                # Get all submissions by this user
                submissions = AssignmentSubmission.objects.filter(user=self)
                submission_count = submissions.count()
                if submission_count > 0:
                    logger.info(f"Deleting {submission_count} assignment submissions")
                    
                    # Delete all feedback for these submissions
                    for submission in submissions:
                        feedback_count = AssignmentFeedback.objects.filter(submission=submission).count()
                        if feedback_count > 0:
                            AssignmentFeedback.objects.filter(submission=submission).delete()
                            logger.info(f"Deleted {feedback_count} feedback records for submission {submission.id}")
                    
                    # Delete all submissions
                    submissions.delete()
                    logger.info(f"Successfully deleted {submission_count} assignment submissions")
            except Exception as e:
                logger.error(f"Error deleting assignment submissions: {str(e)}")
            
            # 4. DELETE ALL QUIZ ATTEMPTS
            try:
                from quiz.models import QuizAttempt, UserAnswer
                
                # Get all quiz attempts by this user
                attempts = QuizAttempt.objects.filter(user=self)
                attempt_count = attempts.count()
                if attempt_count > 0:
                    logger.info(f"Deleting {attempt_count} quiz attempts")
                    
                    # Delete all user answers for these attempts
                    for attempt in attempts:
                        answer_count = UserAnswer.objects.filter(attempt=attempt).count()
                        if answer_count > 0:
                            UserAnswer.objects.filter(attempt=attempt).delete()
                            logger.info(f"Deleted {answer_count} user answers for attempt {attempt.id}")
                    
                    # Delete all attempts
                    attempts.delete()
                    logger.info(f"Successfully deleted {attempt_count} quiz attempts")
            except Exception as e:
                logger.error(f"Error deleting quiz attempts: {str(e)}")
            
            # 5. DELETE ALL GROUP MEMBERSHIPS
            try:
                from groups.models import GroupMembership
                memberships = GroupMembership.objects.filter(user=self)
                membership_count = memberships.count()
                if membership_count > 0:
                    logger.info(f"Deleting {membership_count} group memberships")
                    memberships.delete()
                    logger.info(f"Successfully deleted {membership_count} group memberships")
            except Exception as e:
                logger.error(f"Error deleting group memberships: {str(e)}")
            
            # 6. DELETE ALL GRADEBOOK DATA
            try:
                from gradebook.models import Grade
                
                # Delete all grades for this user
                grades = Grade.objects.filter(student=self)
                grade_count = grades.count()
                if grade_count > 0:
                    logger.info(f"Deleting {grade_count} gradebook entries")
                    grades.delete()
                    logger.info(f"Successfully deleted {grade_count} gradebook entries")
            except Exception as e:
                logger.error(f"Error deleting gradebook data: {str(e)}")
            
            # 7. DELETE ALL USER FILES
            try:
                import os
                import shutil
                from django.conf import settings
                
                # Delete profile image
                if self.profile_image:
                    try:
                        self.profile_image.delete(save=False)
                        logger.info(f"Deleted profile image: {self.profile_image.name}")
                    except Exception as e:
                        logger.error(f"Error deleting profile image: {str(e)}")
                
                # Delete CV file
                if self.cv_file:
                    try:
                        self.cv_file.delete(save=False)
                        logger.info(f"Deleted CV file: {self.cv_file.name}")
                    except Exception as e:
                        logger.error(f"Error deleting CV file: {str(e)}")
                
                # Delete statement of purpose file
                if self.statement_of_purpose_file:
                    try:
                        self.statement_of_purpose_file.delete(save=False)
                        logger.info(f"Deleted statement of purpose file: {self.statement_of_purpose_file.name}")
                    except Exception as e:
                        logger.error(f"Error deleting statement of purpose file: {str(e)}")
                
                user_dirs = [
                    f"user_files/{self.id}",
                    f"profile_images/{self.id}",
                    f"assignment_content/submissions/{self.id}",
                    f"quiz_uploads/{self.id}"
                ]
                
                for user_dir in user_dirs:
                    try:
                        if os.path.exists(user_dir):
                            shutil.rmtree(user_dir)
                            logger.info(f"Deleted user directory: {user_dir}")
                    except Exception as e:
                        logger.error(f"Error deleting user directory {user_dir}: {str(e)}")
                
                # S3 cleanup for user files
                try:
                    from core.utils.s3_cleanup import cleanup_user_s3_files
                    s3_results = cleanup_user_s3_files(self.id)
                    successful_s3_deletions = sum(1 for success in s3_results.values() if success)
                    total_s3_files = len(s3_results)
                    if total_s3_files > 0:
                        logger.info(f"S3 cleanup: {successful_s3_deletions}/{total_s3_files} files deleted successfully")
                except Exception as e:
                    logger.error(f"Error during S3 cleanup for user {self.id}: {str(e)}")
                    
            except Exception as e:
                logger.error(f"Error deleting user files: {str(e)}")
            
            # 8. DELETE ALL USER QUESTIONNAIRES
            try:
                from users.models import UserQuestionnaire
                questionnaires = UserQuestionnaire.objects.filter(user=self)
                questionnaire_count = questionnaires.count()
                if questionnaire_count > 0:
                    logger.info(f"Deleting {questionnaire_count} user questionnaires")
                    questionnaires.delete()
                    logger.info(f"Successfully deleted {questionnaire_count} user questionnaires")
            except Exception as e:
                logger.error(f"Error deleting user questionnaires: {str(e)}")
            
            # 9. DELETE ALL USER QUIZ ASSIGNMENTS
            try:
                from users.models import UserQuizAssignment
                quiz_assignments = UserQuizAssignment.objects.filter(user=self)
                assignment_count = quiz_assignments.count()
                if assignment_count > 0:
                    logger.info(f"Deleting {assignment_count} user quiz assignments")
                    quiz_assignments.delete()
                    logger.info(f"Successfully deleted {assignment_count} user quiz assignments")
            except Exception as e:
                logger.error(f"Error deleting user quiz assignments: {str(e)}")
            
            # 10. DELETE ALL MANUAL ASSESSMENT ENTRIES
            try:
                from users.models import ManualAssessmentEntry
                assessments = ManualAssessmentEntry.objects.filter(user=self)
                assessment_count = assessments.count()
                if assessment_count > 0:
                    logger.info(f"Deleting {assessment_count} manual assessment entries")
                    assessments.delete()
                    logger.info(f"Successfully deleted {assessment_count} manual assessment entries")
            except Exception as e:
                logger.error(f"Error deleting manual assessment entries: {str(e)}")
            
            # 11. DELETE ALL MANUAL VAK SCORES
            try:
                from users.models import ManualVAKScore
                vak_scores = ManualVAKScore.objects.filter(user=self)
                vak_count = vak_scores.count()
                if vak_count > 0:
                    logger.info(f"Deleting {vak_count} manual VAK scores")
                    vak_scores.delete()
                    logger.info(f"Successfully deleted {vak_count} manual VAK scores")
            except Exception as e:
                logger.error(f"Error deleting manual VAK scores: {str(e)}")
            
            # 12. DELETE ALL PASSWORD RESET TOKENS
            try:
                from users.models import PasswordResetToken
                reset_tokens = PasswordResetToken.objects.filter(user=self)
                token_count = reset_tokens.count()
                if token_count > 0:
                    logger.info(f"Deleting {token_count} password reset tokens")
                    reset_tokens.delete()
                    logger.info(f"Successfully deleted {token_count} password reset tokens")
            except Exception as e:
                logger.error(f"Error deleting password reset tokens: {str(e)}")
            
            # 13. DELETE ALL EMAIL VERIFICATION TOKENS
            try:
                from users.models import EmailVerificationToken
                verification_tokens = EmailVerificationToken.objects.filter(user=self)
                token_count = verification_tokens.count()
                if token_count > 0:
                    logger.info(f"Deleting {token_count} email verification tokens")
                    verification_tokens.delete()
                    logger.info(f"Successfully deleted {token_count} email verification tokens")
            except Exception as e:
                logger.error(f"Error deleting email verification tokens: {str(e)}")
            
            # 14. DELETE ALL TWO-FACTOR AUTH DATA
            try:
                from users.models import TwoFactorAuth
                two_factor = TwoFactorAuth.objects.filter(user=self)
                two_factor_count = two_factor.count()
                if two_factor_count > 0:
                    logger.info(f"Deleting {two_factor_count} two-factor auth records")
                    two_factor.delete()
                    logger.info(f"Successfully deleted {two_factor_count} two-factor auth records")
            except Exception as e:
                logger.error(f"Error deleting two-factor auth data: {str(e)}")
            
            # 15. DELETE ALL OTP TOKENS
            try:
                from users.models import OTPToken
                otp_tokens = OTPToken.objects.filter(user=self)
                otp_count = otp_tokens.count()
                if otp_count > 0:
                    logger.info(f"Deleting {otp_count} OTP tokens")
                    otp_tokens.delete()
                    logger.info(f"Successfully deleted {otp_count} OTP tokens")
            except Exception as e:
                logger.error(f"Error deleting OTP tokens: {str(e)}")
            
            # 16. DELETE ALL USER TIMEZONE DATA
            try:
                from users.models import UserTimezone
                timezone_data = UserTimezone.objects.filter(user=self)
                timezone_count = timezone_data.count()
                if timezone_count > 0:
                    logger.info(f"Deleting {timezone_count} user timezone records")
                    timezone_data.delete()
                    logger.info(f"Successfully deleted {timezone_count} user timezone records")
            except Exception as e:
                logger.error(f"Error deleting user timezone data: {str(e)}")
            
            # 17. DELETE ALL ASSIGNED STUDENTS (if this user is an instructor)
            try:
                if self.role == 'instructor':
                    assigned_students = CustomUser.objects.filter(assigned_instructor=self)
                    student_count = assigned_students.count()
                    if student_count > 0:
                        logger.info(f"Removing instructor assignment from {student_count} students")
                        assigned_students.update(assigned_instructor=None)
                        logger.info(f"Successfully removed instructor assignment from {student_count} students")
            except Exception as e:
                logger.error(f"Error removing instructor assignments: {str(e)}")
            
            # 18. DELETE ALL DISCUSSION COMMENTS AND LIKES
            try:
                from courses.models import Comment, Discussion
                
                # Delete all comments by this user
                comments = Comment.objects.filter(created_by=self)
                comment_count = comments.count()
                if comment_count > 0:
                    logger.info(f"Deleting {comment_count} discussion comments")
                    comments.delete()
                    logger.info(f"Successfully deleted {comment_count} discussion comments")
                
                # Remove user from discussion likes
                discussions = Discussion.objects.filter(likes=self)
                discussion_count = discussions.count()
                if discussion_count > 0:
                    logger.info(f"Removing user from {discussion_count} discussion likes")
                    for discussion in discussions:
                        discussion.likes.remove(self)
                    logger.info(f"Successfully removed user from {discussion_count} discussion likes")
            except Exception as e:
                logger.error(f"Error deleting discussion data: {str(e)}")
            
            # Call the parent delete method
            super().delete(*args, **kwargs)
            logger.info(f"Successfully completed comprehensive deletion for User: {self.username} (ID: {self.id})")
            
        except Exception as e:
            logger.error(f"Error in CustomUser.delete(): {str(e)}")
            raise

    def get_role_capabilities(self) -> List[Dict[str, Union[str, bool]]]:
        """Get all capabilities for the user's role"""
        capabilities: List[Dict[str, Union[str, bool]]] = []
        
        # Get default capabilities based on role
        default_capabilities = {
            'superadmin': [
                'view_users', 'manage_users',
                'view_courses', 'manage_courses',
                'view_assignments', 'manage_assignments', 'grade_assignments',
                # Role management capability removed - only Global Admin can manage roles
                'view_groups', 'manage_groups', 'manage_group_members',
                'view_branches', 'manage_branches',
                'view_topics', 'manage_topics',
                'view_quizzes', 'manage_quizzes', 'grade_quizzes',
                'view_progress', 'manage_progress',
                'view_reports', 'manage_reports'
            ],
            'admin': [
                'view_users', 'manage_users',
                'view_courses', 'manage_courses',
                'view_assignments', 'manage_assignments', 'grade_assignments',
                'view_groups', 'manage_groups', 'manage_group_members',
                'view_branches', 'manage_branches',
                'view_topics', 'manage_topics',
                'view_quizzes', 'manage_quizzes', 'grade_quizzes',
                'view_progress', 'manage_progress',
                'view_reports'
            ],
            'instructor': [
                'view_users',
                'view_courses', 'manage_courses',
                'view_assignments', 'manage_assignments', 'grade_assignments',
                'view_groups',
                'view_branches',
                'view_topics', 'manage_topics',
                'view_quizzes', 'manage_quizzes', 'grade_quizzes',
                'view_progress', 'manage_progress',
                'view_reports'
            ],
            'learner': [
                'view_users',
                'view_courses',
                'view_assignments',
                'view_groups',
                'view_branches',
                'view_topics',
                'view_quizzes',
                'view_progress'
            ]
        }

        # Add default capabilities for the user's role
        if self.role in default_capabilities:
            for capability in default_capabilities[self.role]:
                capabilities.append({
                    'name': capability.replace('_', ' ').title(),
                    'is_active': True
                })

        # Add custom role capabilities
        try:
            user_roles = UserRole.objects.filter(user=self)
            if user_roles.exists():
                for user_role in user_roles:
                    role_capabilities = RoleCapability.objects.filter(role=user_role.role)
                    for capability in role_capabilities:
                        capabilities.append({
                            'name': capability.capability.replace('_', ' ').title(),
                            'is_active': True
                        })
        except Exception:
            pass

        return capabilities
    
    def get_profile_completion_percentage(self) -> Dict[str, Union[float, Dict[str, float]]]:
        """Calculate profile completion percentage based on filled fields."""
        # Define field categories with their respective fields and weights
        field_categories = {
            'account': {
                'weight': 20,
                'fields': ['username', 'email', 'given_names', 'family_name', 'role', 'branch', 'timezone']
            },
            'personal': {
                'weight': 20,
                'fields': ['date_of_birth', 'sex', 'sexual_orientation', 'ethnicity', 'current_postcode', 
                          'address_line1', 'city', 'county', 'country', 'phone_number', 'contact_preference']
            },
            'education': {
                'weight': 15,
                'fields': ['education_data']  # Use the new education_data JSONField
            },
            'employment': {
                'weight': 15,
                'fields': ['employment_data']  # Use the new employment_data JSONField
            },
            'additional': {
                'weight': 15,
                'fields': ['reason_for_pursuing_course', 'career_objectives', 'relevant_past_work', 
                          'special_interests_and_strengths']
            },
            'ilp': {
                'weight': 15,
                'fields': ['ilp_completion']  # This will be calculated separately
            }
        }
        
        total_weighted_score = 0
        total_weight = 0
        
        for category, config in field_categories.items():
            fields = config['fields']
            weight = config['weight']
            total_weight += weight
            
            # Handle ILP category separately
            if category == 'ilp':
                ilp_completion = self._get_ilp_completion()
                total_weighted_score += (ilp_completion * weight / 100)
            else:
                # Calculate completion for regular field categories
                completed_fields = 0
                total_fields = len(fields)
                
                for field_name in fields:
                    field_value = getattr(self, field_name, None)
                    if field_value is not None and str(field_value).strip():
                        # Handle special cases
                        if field_name == 'has_learning_difficulty' and field_value in ['Yes', 'No']:
                            completed_fields += 1
                        elif field_name != 'has_learning_difficulty':
                            completed_fields += 1
                
                # Calculate category completion percentage
                category_completion = round((completed_fields / total_fields) * 100) if total_fields > 0 else 0
                
                # Add weighted score
                total_weighted_score += (category_completion * weight / 100)
        
        # Calculate overall completion percentage
        overall_completion = round((total_weighted_score / total_weight) * 100) if total_weight > 0 else 0
        
        return {
            'overall_percentage': round(overall_completion, 1),
            'categories': {
                'account': self._get_category_completion(field_categories['account']['fields']),
                'personal': self._get_category_completion(field_categories['personal']['fields']),
                'education': self._get_category_completion(field_categories['education']['fields']),
                'employment': self._get_category_completion(field_categories['employment']['fields']),
                'additional': self._get_category_completion(field_categories['additional']['fields']),
                'ilp': self._get_ilp_completion()
            }
        }

    def get_vak_quiz_attempts_with_context(self) -> List[Dict[str, Any]]:
        """Get latest VAK quiz attempts with course and topic information - only one per quiz-course combination"""
        from quiz.models import Quiz, QuizAttempt
        from courses.models import Topic
        
        # Get all VAK quiz attempts for this user
        vak_attempts = QuizAttempt.objects.filter(
            user=self,
            quiz__is_vak_test=True,
            is_completed=True
        ).select_related('quiz').order_by('-end_time')
        
        # Group attempts by quiz-course combination and keep only the latest
        attempts_dict = {}
        
        for attempt in vak_attempts:
            # Get course and topic information
            course_info = None
            topic_info = None
            
            # Check if quiz is linked to a topic
            topic = Topic.objects.filter(quiz=attempt.quiz).first()
            if topic:
                topic_info = {
                    'id': topic.id,
                    'title': topic.title,
                    'content_type': topic.content_type
                }
                
                # Get course information from the topic
                # Topic could be linked to multiple courses, get the first one
                course_topic = topic.coursetopic_set.first()
                if course_topic:
                    course_info = {
                        'id': course_topic.course.id,
                        'title': course_topic.course.title,
                        'description': course_topic.course.description
                    }
            
            # Create a unique key for quiz-course combination
            course_id = course_info['id'] if course_info else None
            quiz_course_key = f"{attempt.quiz.id}_{course_id}"
            
            # Only keep the latest attempt for each quiz-course combination
            if quiz_course_key not in attempts_dict:
                # Calculate learning style scores
                learning_scores = self._calculate_vak_scores_for_attempt(attempt)
                
                attempt_data = {
                    'attempt': attempt,
                    'quiz': attempt.quiz,
                    'course': course_info,
                    'topic': topic_info,
                    'learning_scores': learning_scores,
                    'end_time': attempt.end_time,
                    'score': attempt.score
                }
                
                attempts_dict[quiz_course_key] = attempt_data
        
        # Return only the latest attempts
        return list(attempts_dict.values())

    def _calculate_vak_scores_for_attempt(self, attempt: 'QuizAttempt') -> Dict[str, Dict[str, Union[float, int]]]:
        """Calculate VAK learning style scores for a specific attempt"""
        from quiz.models import UserAnswer, Answer
        import json
        
        # Initialize score counters
        style_scores = {
            'visual': {'count': 0, 'total': 0},
            'auditory': {'count': 0, 'total': 0},
            'kinesthetic': {'count': 0, 'total': 0}
        }
        
        # Get all user answers for this attempt
        user_answers = UserAnswer.objects.filter(
            attempt=attempt
        ).select_related('answer', 'question')
        
        total_questions = 0
        
        # Calculate scores by learning style based on selected answers
        for user_answer in user_answers:
            total_questions += 1
            
            # Handle different ways answers might be stored
            selected_answer_ids = []
            
            # Method 1: Direct answer relationship
            if user_answer.answer:
                selected_answer_ids.append(user_answer.answer.id)
            
            # Method 2: Multiple answers stored in text_answer as JSON or comma-separated
            if user_answer.text_answer:
                try:
                    # Try to parse as JSON first
                    if user_answer.text_answer.startswith('[') or user_answer.text_answer.startswith('{'):
                        parsed_ids = json.loads(user_answer.text_answer)
                        if isinstance(parsed_ids, list):
                            selected_answer_ids.extend([int(id) for id in parsed_ids if str(id).isdigit()])
                        elif isinstance(parsed_ids, (int, str)):
                            if str(parsed_ids).isdigit():
                                selected_answer_ids.append(int(parsed_ids))
                    else:
                        # Try comma-separated values
                        ids = [id.strip() for id in user_answer.text_answer.split(',') if id.strip().isdigit()]
                        selected_answer_ids.extend([int(id) for id in ids])
                except (json.JSONDecodeError, ValueError):
                    # If parsing fails, try to extract single number
                    if user_answer.text_answer.isdigit():
                        selected_answer_ids.append(int(user_answer.text_answer))
            
            # Remove duplicates
            selected_answer_ids = list(set(selected_answer_ids))
            
            # Get the learning styles for all selected answers
            if selected_answer_ids:
                selected_answers = Answer.objects.filter(
                    id__in=selected_answer_ids,
                    question=user_answer.question
                )
                
                for answer in selected_answers:
                    if answer.learning_style:
                        style = answer.learning_style.lower()
                        if style in style_scores:
                            style_scores[style]['count'] += 1
        
        # Calculate total selections
        total_selections = sum(scores['count'] for scores in style_scores.values())
        
        # Calculate percentages
        result = {}
        for style, scores in style_scores.items():
            if total_selections > 0:
                percentage = round((scores['count'] / total_selections) * 100)
                result[style] = {
                    'percentage': round(percentage, 1),
                    'count': scores['count'],
                    'total': total_selections
                }
            else:
                result[style] = {
                    'percentage': 0,
                    'count': 0,
                    'total': 0
                }
        
        return result

    def _get_category_completion(self, fields: List[str]) -> float:
        """Helper method to calculate completion percentage for a category."""
        completed_fields = 0
        total_fields = len(fields)
        
        for field_name in fields:
            field_value = getattr(self, field_name, None)
            
            # Special handling for employment_data JSONField
            if field_name == 'employment_data':
                if field_value:
                    try:
                        # Check if it's a list with at least one valid employment record
                        if isinstance(field_value, list) and len(field_value) > 0:
                            # Check if any employment record has required fields filled
                            for employment_record in field_value:
                                if isinstance(employment_record, dict):
                                    # Check for key employment fields
                                    if (employment_record.get('job_role') and 
                                        employment_record.get('industry')):
                                        completed_fields += 1
                                        break
                        elif isinstance(field_value, str):
                            # Try to parse as JSON if it's a string
                            import json
                            try:
                                parsed_data = json.loads(field_value)
                                if isinstance(parsed_data, list) and len(parsed_data) > 0:
                                    for employment_record in parsed_data:
                                        if isinstance(employment_record, dict):
                                            if (employment_record.get('job_role') and 
                                                employment_record.get('industry')):
                                                completed_fields += 1
                                                break
                            except json.JSONDecodeError:
                                pass
                    except (TypeError, AttributeError):
                        pass
            # Special handling for education_data JSONField
            elif field_name == 'education_data':
                if field_value:
                    try:
                        # Check if it's a list with at least one valid education record
                        if isinstance(field_value, list) and len(field_value) > 0:
                            # Check if any education record has required fields filled
                            for education_record in field_value:
                                if isinstance(education_record, dict):
                                    # Check for key education fields
                                    if (education_record.get('institution_name') and 
                                        education_record.get('level_of_study')):
                                        completed_fields += 1
                                        break
                        elif isinstance(field_value, str):
                            # Try to parse as JSON if it's a string
                            import json
                            try:
                                parsed_data = json.loads(field_value)
                                if isinstance(parsed_data, list) and len(parsed_data) > 0:
                                    for education_record in parsed_data:
                                        if isinstance(education_record, dict):
                                            if (education_record.get('institution_name') and 
                                                education_record.get('level_of_study')):
                                                completed_fields += 1
                                                break
                            except json.JSONDecodeError:
                                pass
                    except (TypeError, AttributeError):
                        pass
            # Handle other fields normally
            elif field_value is not None and str(field_value).strip():
                # Handle special cases
                if field_name == 'has_learning_difficulty' and field_value in ['Yes', 'No']:
                    completed_fields += 1
                elif field_name != 'has_learning_difficulty':
                    completed_fields += 1
        
        return round((completed_fields / total_fields) * 100, 1) if total_fields > 0 else 0
    
    def _get_ilp_completion(self) -> float:
        """Calculate ILP completion percentage based on various ILP components."""
        try:
            # Check if user has an ILP
            if not hasattr(self, 'individual_learning_plan'):
                return 0.0
            
            ilp = self.individual_learning_plan
            total_score = 0
            max_score = 0
            
            # 1. Learning Preferences (15 points)
            max_score += 15
            learning_preferences = ilp.learning_preferences.filter(preference_level__gte=3)
            if learning_preferences.count() >= 3:  # At least 3 strong preferences
                total_score += 15
            elif learning_preferences.count() >= 1:
                total_score += learning_preferences.count() * 5
            
            # 2. SEND Accommodations (10 points) - if applicable or marked as not needed
            max_score += 10
            send_accommodations = ilp.send_accommodations.filter(is_active=True)
            # Give full points if either has accommodations or none needed (default assumption)
            if send_accommodations.exists():
                total_score += 10
            else:
                # Assume not needed if no accommodations listed
                total_score += 10
            
            # 3. Strengths & Weaknesses (20 points)
            max_score += 20
            strengths = ilp.strengths_weaknesses.filter(type='strength')
            weaknesses = ilp.strengths_weaknesses.filter(type='weakness')
            strength_points = min(strengths.count() * 5, 10)  # Max 10 points for strengths
            weakness_points = min(weaknesses.count() * 5, 10)  # Max 10 points for weaknesses
            total_score += strength_points + weakness_points
            
            # 4. Learning Needs (15 points)
            max_score += 15
            if hasattr(ilp, 'learning_needs'):
                learning_needs = ilp.learning_needs
                needs_score = 0
                # Check if any employability skills are selected
                skill_fields = ['job_search_skills', 'effective_cvs', 'improving_it_skills', 
                               'interview_skills', 'team_skills', 'communication_skills']
                selected_skills = sum(1 for field in skill_fields if getattr(learning_needs, field, False))
                if selected_skills > 0:
                    needs_score += 10
                # Check if assessment fields are filled
                if learning_needs.prior_learning_experience or learning_needs.learning_challenges:
                    needs_score += 5
                total_score += needs_score
            
            # 5. Induction Checklist (20 points)
            max_score += 20
            if hasattr(ilp, 'induction_checklist'):
                induction_checklist = ilp.induction_checklist
                induction_score = (induction_checklist.completion_percentage / 100) * 20
                total_score += induction_score
            
            # 6. Health & Safety Questionnaire (20 points)
            max_score += 20
            if hasattr(ilp, 'health_safety_questionnaire'):
                health_safety = ilp.health_safety_questionnaire
                health_safety_score = (health_safety.completion_percentage / 100) * 20
                total_score += health_safety_score
            
            # Calculate final percentage
            completion_percentage = round((total_score / max_score) * 100) if max_score > 0 else 0
            return round(completion_percentage, 1)
            
        except Exception as e:
            # If there's any error in calculation, return 0
            return 0.0

class UserQuestionnaire(models.Model):
    """Model to store dynamic questionnaire data for users"""
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='questionnaires')
    question_text = models.TextField(help_text="The question text")
    answer_text = models.TextField(blank=True, null=True, help_text="The answer to the question")
    document = models.FileField(
        upload_to='questionnaire_documents/',
        blank=True,
        null=True,
        help_text="Supporting document for this question"
    )
    confirmation_required = models.CharField(
        max_length=3,
        choices=[('yes', 'Yes'), ('no', 'No')],
        blank=True,
        null=True,
        help_text="Whether confirmation is required for this question"
    )
    question_order = models.PositiveIntegerField(default=1, help_text="Order of the question")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        CustomUser, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='created_questionnaires',
        help_text="User who created this questionnaire entry"
    )

    class Meta:
        ordering = ['question_order', 'created_at']
        verbose_name = "User Questionnaire"
        verbose_name_plural = "User Questionnaires"

    def __str__(self):
        return f"Q{self.question_order}: {self.question_text[:50]}..." if len(self.question_text) > 50 else f"Q{self.question_order}: {self.question_text}"

    @property
    def has_answer(self):
        """Check if the question has been answered"""
        return bool(self.answer_text and self.answer_text.strip())

    @property
    def has_document(self):
        """Check if the question has a supporting document"""
        return bool(self.document)

    @property
    def is_confirmed(self):
        """Check if the question has been confirmed"""
        return bool(self.confirmation_required)

    def get_document_url(self):
        """Get the URL for the document if it exists"""
        if self.document:
            try:
                return self.document.url
            except Exception as e:
                # Log the error but don't break the page
                import logging
                logger = logging.getLogger('users')
                logger.warning(f"Error getting document URL for document {self.document.name}: {e}")
                return None  # Return None if we can't get the URL
        return None

    def get_document_name(self):
        """Get the filename of the document if it exists"""
        if self.document:
            try:
                return self.document.name.split('/')[-1]
            except Exception as e:
                # Log the error but don't break the page
                import logging
                logger = logging.getLogger('users')
                logger.warning(f"Error getting document name: {e}")
                return "Unknown Document"  # Return a fallback name
        return None

class UserQuizAssignment(models.Model):
    """Model to track quiz assignments to users for Assessment Data and Learning Preferences tabs"""
    ASSIGNMENT_TYPE_CHOICES = [
        ('initial_assessment', 'Initial Assessment'),
        ('vak_test', 'VAK Test'),
    ]
    
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='quiz_assignments',
        help_text="User who is assigned the quiz"
    )
    quiz = models.ForeignKey(
        'quiz.Quiz',
        on_delete=models.CASCADE,
        related_name='user_assignments',
        help_text="Quiz assigned to the user"
    )
    assignment_type = models.CharField(
        max_length=20,
        choices=ASSIGNMENT_TYPE_CHOICES,
        help_text="Type of assignment (Initial Assessment or VAK Test)"
    )
    item_name = models.CharField(
        max_length=800,
        help_text="Display name for the quiz assignment (defaults to quiz title)"
    )
    assigned_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_quizzes',
        help_text="Admin/Instructor who assigned the quiz"
    )
    assigned_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the quiz was assigned"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether the assignment is active"
    )
    notes = models.TextField(
        blank=True,
        null=True,
        help_text="Optional notes about the assignment"
    )
    
    class Meta:
        unique_together = ['user', 'quiz', 'assignment_type']
        ordering = ['assigned_at']
        
    def __str__(self):
        return f"{self.user.get_full_name()} - {self.item_name} ({self.get_assignment_type_display()})"
    
    def save(self, *args, **kwargs):
        # Default item name to quiz title if not provided
        if not self.item_name and self.quiz:
            self.item_name = self.quiz.title
        super().save(*args, **kwargs)
    
    def get_user_attempts(self):
        """Get all attempts by the assigned user for this quiz"""
        from quiz.models import QuizAttempt
        return QuizAttempt.objects.filter(
            quiz=self.quiz,
            user=self.user,
            is_completed=True
        ).order_by('-end_time')
    
    def get_latest_attempt(self):
        """Get the latest attempt by the assigned user for this quiz"""
        return self.get_user_attempts().first()
    
    def get_best_score(self):
        """Get the best score for this assignment"""
        attempts = self.get_user_attempts()
        if attempts:
            return max(attempt.score for attempt in attempts)
        return None
    
    def get_attempt_count(self):
        """Get the number of attempts for this assignment"""
        return self.get_user_attempts().count()
    
    def get_learning_style_scores(self):
        """Calculate learning style scores for VAK tests"""
        if self.assignment_type != 'vak_test':
            return None
        
        # Get the latest completed attempt
        latest_attempt = self.get_user_attempts().first()
        if not latest_attempt:
            return None
        
        # Initialize score counters
        style_scores = {
            'visual': {'correct': 0, 'total': 0},
            'auditory': {'correct': 0, 'total': 0},
            'kinesthetic': {'correct': 0, 'total': 0}
        }
        
        # Get all user answers for this attempt
        from quiz.models import UserAnswer
        user_answers = UserAnswer.objects.filter(attempt=latest_attempt).select_related('question')
        
        # Calculate scores by learning style based on selected answers
        for user_answer in user_answers:
            # For VAK tests, check the learning style of the selected answer
            if user_answer.answer and user_answer.answer.learning_style:
                style = user_answer.answer.learning_style
                style_scores[style]['total'] += 1
                # For VAK tests, we count all selections (no concept of correct/incorrect)
                style_scores[style]['correct'] += 1
        
        # Calculate percentages for VAK tests
        result = {}
        total_selections = sum(scores['total'] for scores in style_scores.values())
        
        for style, scores in style_scores.items():
            if total_selections > 0:
                percentage = round((scores['total'] / total_selections) * 100)
                result[style] = {
                    'percentage': round(percentage, 1),
                    'count': scores['total'],
                    'total': total_selections
                }
            else:
                result[style] = {
                    'percentage': 0,
                    'count': 0,
                    'total': 0
                }
        
        return result
    
    def get_dominant_learning_style(self):
        """Get the dominant learning style based on VAK test results"""
        scores = self.get_learning_style_scores()
        if not scores:
            return None
        
        # Find the style with the highest percentage
        dominant_style = max(scores.items(), key=lambda x: x[1]['percentage'])
        
        return {
            'style': dominant_style[0],
            'percentage': dominant_style[1]['percentage'],
            'display_name': {
                'visual': 'Visual',
                'auditory': 'Auditory', 
                'kinesthetic': 'Kinesthetic'
            }.get(dominant_style[0], dominant_style[0].title())
        }

class ManualVAKScore(models.Model):
    """Model to store manually entered VAK scores by instructors/admins"""
    user = models.OneToOneField(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='manual_vak_score',
        help_text="User for whom VAK scores are manually entered"
    )
    visual_score = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Manual Visual learning style score (0-100)"
    )
    auditory_score = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Manual Auditory learning style score (0-100)"
    )
    kinesthetic_score = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Manual Kinesthetic learning style score (0-100)"
    )
    entered_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='entered_vak_scores',
        help_text="Admin/Instructor who entered the manual scores"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Manual VAK Score"
        verbose_name_plural = "Manual VAK Scores"
        ordering = ['-updated_at']
    
    def __str__(self):
        return f"Manual VAK Scores for {self.user.get_full_name()}"
    
    def get_manual_scores(self):
        """Get manual scores in simple format"""
        return {
            'visual': float(self.visual_score) if self.visual_score else 0,
            'auditory': float(self.auditory_score) if self.auditory_score else 0,
            'kinesthetic': float(self.kinesthetic_score) if self.kinesthetic_score else 0
        }
    
    def has_any_scores(self):
        """Check if any manual scores are entered"""
        return any([self.visual_score, self.auditory_score, self.kinesthetic_score])

class ManualAssessmentEntry(models.Model):
    """Model to store manually entered assessment data by instructors/admins"""
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='manual_assessment_entries',
        help_text="User for whom manual assessment data is entered"
    )
    subject = models.CharField(
        max_length=800,
        help_text="Subject or assessment name"
    )
    score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Assessment score (0-100)"
    )
    notes = models.TextField(
        blank=True,
        null=True,
        help_text="Optional notes about the assessment"
    )
    assessment_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date of assessment"
    )
    entered_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='entered_manual_assessments',
        help_text="Admin/Instructor who entered the manual assessment"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Manual Assessment Entry"
        verbose_name_plural = "Manual Assessment Entries"
        ordering = ['-updated_at', 'subject']
        unique_together = ['user', 'subject']  # Prevent duplicate subjects for the same user
    
    def __str__(self):
        return f"{self.user.get_full_name()} - {self.subject}: {self.score}%"
    
    def clean(self):
        """Validate the model data"""
        super().clean()
        
        # Validate score range
        if self.score is not None:
            if self.score < 0 or self.score > 100:
                raise ValidationError({'score': 'Score must be between 0 and 100.'})
        
        # Validate subject is not empty
        if not self.subject or not self.subject.strip():
            raise ValidationError({'subject': 'Subject cannot be empty.'})
        
        # Clean the subject field
        self.subject = self.subject.strip()
    
    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

class PasswordResetToken(models.Model):
    """Token for password reset email verification"""
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='password_reset_tokens'
    )
    token = models.UUIDField(default=uuid.uuid4, unique=True)
    branch = models.ForeignKey(
        'branches.Branch',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text="Branch context for this reset request"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    used_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        verbose_name = "Password Reset Token"
        verbose_name_plural = "Password Reset Tokens"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Password reset token for {self.user.username}"
    
    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(hours=1)  # 1 hour expiry
        super().save(*args, **kwargs)
    
    def is_expired(self):
        return timezone.now() > self.expires_at
    
    def mark_as_used(self):
        self.is_used = True
        self.used_at = timezone.now()
        self.save()
    
    def send_reset_email(self, request=None):
        """Send password reset email using configured email backend"""
        from django.conf import settings
        from django.core.mail import EmailMultiAlternatives
        import logging
        
        logger = logging.getLogger(__name__)
        
        # Try to use GlobalAdminSettings SMTP configuration first
        try:
            from account_settings.models import GlobalAdminSettings
            global_settings = GlobalAdminSettings.get_settings()
            
            if global_settings.smtp_enabled and global_settings.smtp_host and global_settings.smtp_password:
                # Use GlobalAdminSettings email backend
                email_backend = global_settings.get_email_backend()
                from_email = global_settings.get_from_email()
                logger.info("Using GlobalAdminSettings SMTP configuration for password reset email")
            else:
                # Fall back to Django's configured email backend
                email_backend = None
                from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None)
                logger.info("GlobalAdminSettings SMTP not fully configured, using Django default email backend")
        except Exception as e:
            # Fall back to Django's configured email backend if GlobalAdminSettings fails
            logger.warning(f"Failed to load GlobalAdminSettings: {str(e)}, using Django default email backend")
            email_backend = None
            from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None)
        
        # Validate that email backend is properly configured
        if not from_email:
            logger.error("DEFAULT_FROM_EMAIL is not configured in settings")
            return False
        
        # Build reset URL
        if request:
            base_url = request.build_absolute_uri('/')
        else:
            try:
                current_site = Site.objects.get_current()
                base_url = f"https://{current_site.domain}/"
            except Exception as e:
                logger.error(f"Failed to get current site: {str(e)}")
                # Use BASE_URL from settings instead of hardcoded domain
                from django.conf import settings
                base_url = getattr(settings, 'BASE_URL', f"https://{getattr(settings, 'PRIMARY_DOMAIN', 'localhost')}/").rstrip('/') + '/'
        
        # Include branch in reset URL if available
        if self.branch:
            try:
                reset_url = f"{base_url}auth/{self.branch.portal.slug}/reset-password/{self.token}/"
            except Exception as e:
                logger.error(f"Failed to get branch portal slug: {str(e)}")
                reset_url = f"{base_url}auth/reset-password/{self.token}/"
        else:
            reset_url = f"{base_url}auth/reset-password/{self.token}/"
        
        # Prepare email context
        context = {
            'user': self.user,
            'reset_url': reset_url,
            'token': self.token,
            'branch': self.branch,
            'expires_at': self.expires_at,
            'site_name': self.branch.name if self.branch else 'Nexsy LMS',
        }
        
        # Render email templates
        try:
            subject = f"Password Reset - {context['site_name']}"
            html_message = render_to_string('users/email/password_reset.html', context)
            text_message = render_to_string('users/email/password_reset.txt', context)
        except Exception as e:
            logger.error(f"Failed to render email templates: {str(e)}")
            return False
        
        # Send email with comprehensive error handling
        try:
            email = EmailMultiAlternatives(
                subject=subject,
                body=text_message,
                from_email=from_email,
                to=[self.user.email],
                connection=email_backend  # Use custom backend if available
            )
            email.attach_alternative(html_message, "text/html")
            
            # Send email with detailed error logging
            # fail_silently=False ensures we catch all errors
            result = email.send(fail_silently=False)
            
            # Check if email was sent successfully
            # result should be 1 for success, 0 for failure
            if result == 1:
                logger.info(f" Password reset email sent successfully to {self.user.email}")
                return True
            elif result == 0:
                # Email backend returned 0 - this means the email failed to send
                logger.error(f" Email backend returned 0 - email not sent to {self.user.email}. "
                           f"This usually means OAuth2 credentials are invalid or SMTP is not configured.")
                return False
            else:
                logger.warning(f" Unexpected result from email.send(): {result}")
                return False
                
        except Exception as e:
            # Catch all email sending errors
            error_msg = str(e)
            logger.error(f" Exception while sending password reset email to {self.user.email}: {error_msg}")
            
            # Provide specific error messages for common issues
            if "400 Client Error" in error_msg or "Bad Request" in error_msg:
                logger.error("🔑 OAuth2 authentication failed - credentials may be invalid or expired. "
                           "Please check OUTLOOK_CLIENT_ID, OUTLOOK_CLIENT_SECRET, and OUTLOOK_TENANT_ID in settings.")
            elif "Connection refused" in error_msg or "Errno 111" in error_msg:
                logger.error("🔌 SMTP connection refused - email server may not be configured or accessible.")
            elif "Authentication failed" in error_msg:
                logger.error("🔐 Email authentication failed - check email credentials.")
            
            # Return False instead of re-raising to prevent server crashes
            return False

class EmailVerificationToken(models.Model):
    """Token for email verification during registration"""
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='email_verification_tokens'
    )
    token = models.UUIDField(default=uuid.uuid4, unique=True)
    branch = models.ForeignKey(
        'branches.Branch',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text="Branch context for this verification request"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    used_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        verbose_name = "Email Verification Token"
        verbose_name_plural = "Email Verification Tokens"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Email verification token for {self.user.username}"
    
    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(hours=24)  # 24 hours expiry
        super().save(*args, **kwargs)
    
    def is_expired(self):
        return timezone.now() > self.expires_at
    
    def mark_as_used(self):
        self.is_used = True
        self.used_at = timezone.now()
        self.user.is_active = True
        self.user.save()
        self.save()
    
    def send_verification_email(self, request=None):
        """Send email verification using configured email backend"""
        from django.conf import settings
        import logging
        
        logger = logging.getLogger(__name__)
        
        # Try to use GlobalAdminSettings SMTP configuration first
        try:
            from account_settings.models import GlobalAdminSettings
            global_settings = GlobalAdminSettings.get_settings()
            
            if global_settings.smtp_enabled and global_settings.smtp_host and global_settings.smtp_password:
                # Use GlobalAdminSettings email backend
                email_backend = global_settings.get_email_backend()
                from_email = global_settings.get_from_email()
                logger.info("Using GlobalAdminSettings SMTP configuration for email verification")
            else:
                # Fall back to Django's configured email backend
                email_backend = None
                from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None)
                logger.info("GlobalAdminSettings SMTP not fully configured, using Django default email backend")
        except Exception as e:
            # Fall back to Django's configured email backend if GlobalAdminSettings fails
            logger.warning(f"Failed to load GlobalAdminSettings: {str(e)}, using Django default email backend")
            email_backend = None
            from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None)
        
        # Build verification URL
        if request:
            base_url = request.build_absolute_uri('/')
        else:
            current_site = Site.objects.get_current()
            base_url = f"https://{current_site.domain}/"
        
        # Include branch in verification URL if available
        if self.branch:
            verify_url = f"{base_url}auth/{self.branch.portal.slug}/verify-email/{self.token}/"
        else:
            verify_url = f"{base_url}auth/verify-email/{self.token}/"
        
        # Prepare email context
        context = {
            'user': self.user,
            'verify_url': verify_url,
            'token': self.token,
            'branch': self.branch,
            'expires_at': self.expires_at,
            'site_name': self.branch.name if self.branch else 'Nexsy LMS',
        }
        
        # Render email templates
        subject = f"Verify Your Email - {context['site_name']}"
        html_message = render_to_string('users/email/email_verification.html', context)
        text_message = render_to_string('users/email/email_verification.txt', context)
        
        # Send email
        from django.core.mail import EmailMultiAlternatives
        email = EmailMultiAlternatives(
            subject=subject,
            body=text_message,
            from_email=from_email,
            to=[self.user.email],
            connection=email_backend  # Use custom backend if available
        )
        email.attach_alternative(html_message, "text/html")
        email.send()


class TwoFactorAuth(models.Model):
    """Two-factor authentication settings for users"""
    user = models.OneToOneField(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='two_factor_auth'
    )
    is_enabled = models.BooleanField(
        default=False,
        help_text="Enable 2FA for regular email/password login"
    )
    oauth_enabled = models.BooleanField(
        default=False,
        help_text="Enable 2FA for Google/Microsoft OAuth login"
    )
    totp_enabled = models.BooleanField(
        default=False,
        help_text="Enable TOTP authenticator app 2FA"
    )
    totp_secret = models.CharField(
        max_length=32,
        blank=True,
        null=True,
        help_text="Secret key for TOTP generation"
    )
    backup_tokens = models.JSONField(
        default=list,
        blank=True,
        help_text="One-time backup tokens for account recovery"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Two Factor Authentication"
        verbose_name_plural = "Two Factor Authentications"
    
    def __str__(self):
        regular_status = "Enabled" if self.is_enabled else "Disabled"
        oauth_status = "Enabled" if self.oauth_enabled else "Disabled"
        totp_status = "Enabled" if self.totp_enabled else "Disabled"
        return f"2FA for {self.user.username} - Regular: {regular_status}, OAuth: {oauth_status}, TOTP: {totp_status}"
    
    def generate_totp_secret(self):
        """Generate a new TOTP secret key"""
        import pyotp
        import secrets
        self.totp_secret = pyotp.random_base32()
        return self.totp_secret
    
    def get_totp_uri(self, issuer_name="Nexsy LMS"):
        """Get TOTP URI for QR code generation"""
        if not self.totp_secret:
            self.generate_totp_secret()
        
        import pyotp
        totp = pyotp.TOTP(self.totp_secret)
        return totp.provisioning_uri(
            name=self.user.email,
            issuer_name=issuer_name
        )
    
    def verify_totp(self, token):
        """Verify TOTP token"""
        if not self.totp_secret or not self.totp_enabled:
            return False
        
        import pyotp
        totp = pyotp.TOTP(self.totp_secret)
        return totp.verify(token, valid_window=1)  # Allow 30 seconds window
    
    def generate_backup_tokens(self, count=8):
        """Generate backup recovery tokens"""
        import secrets
        import string
        
        tokens = []
        for _ in range(count):
            token = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))
            tokens.append(token)
        
        self.backup_tokens = tokens
        return tokens
    
    def use_backup_token(self, token):
        """Use a backup token (can only be used once)"""
        if token in self.backup_tokens:
            self.backup_tokens.remove(token)
            self.save()
            return True
        return False


class OTPToken(models.Model):
    """One-time password tokens for 2FA email verification"""
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='otp_tokens'
    )
    otp_code = models.CharField(max_length=6)
    purpose = models.CharField(
        max_length=20,
        choices=[
            ('login', 'Login Verification'),
            ('settings', 'Settings Change'),
        ],
        default='login'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    used_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        verbose_name = "OTP Token"
        verbose_name_plural = "OTP Tokens"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"OTP for {self.user.username} - {self.otp_code}"
    
    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(minutes=10)  # 10 minutes expiry
        if not self.otp_code:
            import random
            self.otp_code = str(random.randint(100000, 999999))
        super().save(*args, **kwargs)
    
    def is_expired(self):
        return timezone.now() > self.expires_at
    
    def mark_as_used(self):
        self.is_used = True
        self.used_at = timezone.now()
        self.save()
    
    def send_otp_email(self, request=None):
        """Send OTP email using configured email backend"""
        from django.conf import settings
        from django.contrib.sites.models import Site
        import logging
        
        logger = logging.getLogger(__name__)
        
        # Try to use GlobalAdminSettings SMTP configuration first
        try:
            from account_settings.models import GlobalAdminSettings
            global_settings = GlobalAdminSettings.get_settings()
            
            if global_settings.smtp_enabled and global_settings.smtp_host and global_settings.smtp_password:
                # Use GlobalAdminSettings email backend
                email_backend = global_settings.get_email_backend()
                from_email = global_settings.get_from_email()
                logger.info("Using GlobalAdminSettings SMTP configuration for OTP email")
            else:
                # Fall back to Django's configured email backend
                email_backend = None
                from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None)
                logger.info("GlobalAdminSettings SMTP not fully configured, using Django default email backend")
        except Exception as e:
            # Fall back to Django's configured email backend if GlobalAdminSettings fails
            logger.warning(f"Failed to load GlobalAdminSettings: {str(e)}, using Django default email backend")
            email_backend = None
            from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None)
        
        # Prepare email context
        context = {
            'user': self.user,
            'otp_code': self.otp_code,
            'purpose': self.get_purpose_display(),
            'expires_at': self.expires_at,
            'site_name': self.user.branch.name if self.user.branch else 'Nexsy LMS',
        }
        
        # Render email templates
        subject = f"Your Login Verification Code - {context['site_name']}"
        html_message = render_to_string('users/email/otp_verification.html', context)
        text_message = render_to_string('users/email/otp_verification.txt', context)
        
        # Send email
        from django.core.mail import EmailMultiAlternatives
        email = EmailMultiAlternatives(
            subject=subject,
            body=text_message,
            from_email=from_email,
            to=[self.user.email],
            connection=email_backend  # Use custom backend if available
        )
        email.attach_alternative(html_message, "text/html")
        email.send()
        
        return True


class UserTimezone(models.Model):
    """Model to store user timezone preferences"""
    user = models.OneToOneField(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='timezone_preference'
    )
    timezone = models.CharField(
        max_length=100,
        default='UTC',
        help_text="User's preferred timezone (e.g., 'America/New_York', 'Europe/London')"
    )
    auto_detected = models.BooleanField(
        default=False,
        help_text="Whether timezone was auto-detected from browser"
    )
    last_updated = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        app_label = 'users'
        verbose_name = 'User Timezone'
        verbose_name_plural = 'User Timezones'
    
    def __str__(self):
        return f"{self.user.username} - {self.timezone}"
    
    def get_timezone_obj(self):
        """Get pytz timezone object"""
        try:
            return pytz.timezone(self.timezone)
        except pytz.UnknownTimeZoneError:
            return pytz.UTC
    
    def convert_to_user_timezone(self, utc_datetime):
        """Convert UTC datetime to user's timezone"""
        if not utc_datetime:
            return None
        
        if timezone.is_naive(utc_datetime):
            utc_datetime = timezone.make_aware(utc_datetime, pytz.UTC)
        
        user_tz = self.get_timezone_obj()
        return utc_datetime.astimezone(user_tz)
    
    def convert_to_utc(self, local_datetime):
        """Convert local datetime to UTC"""
        if not local_datetime:
            return None
        
        user_tz = self.get_timezone_obj()
        
        if user_tz:
            local_datetime = user_tz.localize(local_datetime)
        
        return local_datetime.astimezone(pytz.UTC)
    
    @classmethod
    def get_user_timezone(cls, user):
        """Get user's timezone, create default if doesn't exist"""
        try:
            return cls.objects.get(user=user)
        except cls.DoesNotExist:
            return cls.objects.create(
                user=user,
                timezone='UTC',
                auto_detected=False
            )
    
    @classmethod
    def detect_timezone_from_offset(cls, offset_minutes):
        """Detect timezone from UTC offset in minutes"""
        # Common timezone mappings based on UTC offset
        offset_mapping = {
            -720: 'Pacific/Midway',      # UTC-12
            -660: 'Pacific/Honolulu',    # UTC-11
            -600: 'Pacific/Marquesas',   # UTC-10
            -540: 'America/Anchorage',   # UTC-9
            -480: 'America/Los_Angeles', # UTC-8
            -420: 'America/Denver',      # UTC-7
            -360: 'America/Chicago',     # UTC-6
            -300: 'America/New_York',    # UTC-5
            -240: 'America/Caracas',     # UTC-4
            -180: 'America/Argentina/Buenos_Aires', # UTC-3
            -120: 'Atlantic/South_Georgia', # UTC-2
            -60: 'Atlantic/Azores',      # UTC-1
            0: 'UTC',                    # UTC+0
            60: 'Europe/London',         # UTC+1
            120: 'Europe/Paris',         # UTC+2
            180: 'Europe/Moscow',        # UTC+3
            240: 'Asia/Dubai',           # UTC+4
            300: 'Asia/Karachi',         # UTC+5
            360: 'Asia/Dhaka',           # UTC+6
            420: 'Asia/Bangkok',         # UTC+7
            480: 'Asia/Shanghai',        # UTC+8
            540: 'Asia/Tokyo',           # UTC+9
            600: 'Australia/Sydney',     # UTC+10
            660: 'Pacific/Noumea',       # UTC+11
            720: 'Pacific/Auckland',     # UTC+12
        }
        
        return offset_mapping.get(offset_minutes, 'UTC')
