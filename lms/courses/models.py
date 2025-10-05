import os
import shutil
import logging
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.apps import apps
from users.models import CustomUser, Branch
from django.db.models.signals import post_save
from django.dispatch import receiver
# SCORM imports removed - functionality no longer supported
# from scorm_cloud.utils.api import get_scorm_client
# from scorm_cloud.models import SCORMPackage, SCORMCloudContent, SCORMDestination
from core.utils.fields import TinyMCEField
from django.core.files.storage import default_storage
# Local file storage configuration
from categories.models import CourseCategory

import uuid
import zipfile
import time
from PIL import Image
import traceback
import io
import re
import hashlib
from typing import Any, Dict, List, Optional, Union, Tuple, TYPE_CHECKING
from django.db.models import QuerySet

if TYPE_CHECKING:
    from django.core.files.storage import Storage

logger = logging.getLogger(__name__)

# SCORM model getters removed - functionality no longer supported

def content_file_path(instance: Any, filename: str) -> str:
    """Generate file path for course content with safe filename handling for S3 storage"""
    # Local file storage configuration
    if isinstance(instance, Topic) and instance.content_type == 'SCORM':
        return f"scorm_cloud/{instance.pk}_{filename}"
    
    # Get the base filename and extension
    name, ext = os.path.splitext(filename)
    
    # Generate a unique identifier
    unique_id = uuid.uuid4().hex[:8]
    
    # Truncate the filename to ensure total path length stays under 255
    # Be extremely conservative with the max name length
    max_name_length = 50  # Significantly reduced to account for path components
    
    # Replace potentially problematic characters
    name = "".join(c for c in name if c.isalnum() or c in ['-', '_']).strip()
    
    # Truncate if still too long
    if len(name) > max_name_length:
        name = name[:max_name_length]
    
    # Construct the new filename
    new_filename = f"{name}_{unique_id}{ext.lower()}"
    
    # Determine the course ID
    if isinstance(instance, Course):
        course_id = instance.id
    elif isinstance(instance, Topic):
        # Check if topic has a primary key
        if not instance.pk:
            # No primary key yet, use a default location
            return f"courses/topic_uploads/{unique_id}{ext.lower()}"
            
        # Handle case where topic isn't linked to a course yet
        try:
            # Try to get course via the property (which now checks for pk)
            course = instance.course
            if course:
                course_id = course.id
            else:
                # No course found, use a default folder
                return f"courses/topic_uploads/{instance.pk}/{new_filename}"
        except Exception as e:
            # Log the error and use a fallback location
            logger.error(f"Error in content_file_path: {str(e)}")
            return f"courses/topic_uploads/{unique_id}{ext.lower()}"
    else:
        course_id = 'misc'
    
    # Create the path with course ID as the main folder - compatible with S3 storage
    return f"courses/{course_id}/topics/{instance.pk if isinstance(instance, Topic) else 'misc'}/{new_filename}"

class CourseEnrollment(models.Model):
    """Model to track course enrollments with additional metadata"""
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, null=True, blank=True)
    course = models.ForeignKey('Course', on_delete=models.CASCADE, null=True, blank=True)
    enrolled_at = models.DateTimeField(auto_now_add=True)
    completed = models.BooleanField(default=False)
    completion_date = models.DateTimeField(null=True, blank=True)
    last_accessed = models.DateTimeField(auto_now=True)
    
    ENROLLMENT_SOURCES = [
        ('manual', 'Manual Enrollment'),
        ('auto_prerequisite', 'Auto-enrolled for Prerequisites'),
        ('auto_dependent', 'Auto-enrolled from Dependent Course'),
        ('bulk', 'Bulk Enrollment'),
        ('self', 'Self Enrollment'),
    ]
    
    enrollment_source = models.CharField(
        max_length=20,
        choices=ENROLLMENT_SOURCES,
        default='manual',
        help_text="How the user was enrolled in this course"
    )
    
    # Track which course caused the auto-enrollment (for prerequisite tracking)
    source_course = models.ForeignKey(
        'Course',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='caused_enrollments',
        help_text="The course that caused this auto-enrollment (for prerequisite relationships)"
    )

    class Meta:
        unique_together = ['course', 'user']
        indexes = [
            # Dashboard performance indexes
            models.Index(fields=['user', 'completed']),
            models.Index(fields=['course', 'completed']),
            models.Index(fields=['completed', 'completion_date']),
            models.Index(fields=['user', 'course', 'completed']),
            models.Index(fields=['enrolled_at']),
            models.Index(fields=['last_accessed']),
            models.Index(fields=['user', 'enrolled_at']),
            models.Index(fields=['completion_date']),
        ]

    def __str__(self) -> str:
        user_name = self.user.username if self.user else 'Unknown User'
        course_title = self.course.title if self.course else 'Unknown Course'
        return f"{user_name} - {course_title}"

    def get_progress(self) -> int:
        if not self.course or not self.user:
            return 0
        total_topics = CourseTopic.objects.filter(course=self.course).count()
        if total_topics == 0:
            return 0
        completed_topics = TopicProgress.objects.filter(
            user=self.user,
            topic__coursetopic__course=self.course,
            completed=True
        ).count()
        return round((completed_topics / total_topics) * 100)
        
    @property
    def progress_percentage(self) -> int:
        """Returns the percentage of course completion"""
        if self.completed:
            return 100
        return round(self.get_progress())
    
    def sync_completion_status(self) -> None:
        """Ensure the completed status matches actual progress"""
        if not self.course or not self.user:
            return
            
        actual_progress = self.get_progress()
        should_be_completed = actual_progress == 100
        
        if self.completed != should_be_completed:
            self.completed = should_be_completed
            if should_be_completed and not self.completion_date:
                from django.utils import timezone
                self.completion_date = timezone.now()
            elif not should_be_completed:
                self.completion_date = None
            self.save()
    
    @classmethod
    def sync_user_completions(cls, user):
        """Sync completion status for all enrollments of a user"""
        enrollments = cls.objects.filter(user=user).select_related('course')
        for enrollment in enrollments:
            enrollment.sync_completion_status()
    
    @classmethod
    def sync_branch_completions(cls, branch_id):
        """Sync completion status for all enrollments in a branch"""
        enrollments = cls.objects.filter(user__branch_id=branch_id).select_related('course', 'user')
        for enrollment in enrollments:
            enrollment.sync_completion_status()
        
    @property
    def progress(self):
        """Returns progress percentage (alias for progress_percentage)"""
        return self.progress_percentage

    @property
    def total_time_spent(self):
        """Returns the total time spent in the course in hours and minutes format"""
        from django.db.models import Sum
        
        # Sum time from all topic progress entries for this user and course
        total_seconds = TopicProgress.objects.filter(
            user=self.user,
            topic__coursetopic__course=self.course
        ).aggregate(total=Sum('total_time_spent'))['total'] or 0
        
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        
        return f"{hours}h {minutes}m"
        
    @property
    def score(self):
        """Returns the average score across all graded topics in the course"""
        from django.db.models import Avg
        
        # Get average score from all graded topic progress entries
        avg_score = TopicProgress.objects.filter(
            user=self.user,
            topic__coursetopic__course=self.course,
            last_score__isnull=False
        ).aggregate(avg=Avg('last_score'))['avg']
        
        return round(avg_score) if avg_score is not None else None

class SafeImageFieldDescriptor:
    """Custom descriptor to safely handle missing image files"""
    def __init__(self, field):
        self.field = field

    def __get__(self, instance, owner):
        if instance is None:
            return self.field
        
        try:
            file = instance.__dict__.get(self.field.name)
            
            # If file is None or empty string, return None
            if not file:
                return None
                
            # Handle InMemoryUploadedFile or TemporaryUploadedFile
            if hasattr(file, 'file'):
                # For newly uploaded files that haven't been saved yet
                if not hasattr(file, 'storage'):
                    file.storage = self.field.storage
                return file
                
            # If file is a string (just the name), convert it to a FieldFile
            if isinstance(file, str):
                try:
                    # Try to open file directly instead of checking existence (S3 permission-safe)
                    # This prevents HeadObject operations that require additional S3 permissions
                    try:
                        # Test file access without actually reading content
                        test_file = default_storage.open(file)
                        test_file.close()
                        file_accessible = True
                    except Exception as access_error:
                        # File doesn't exist or permission denied - that's OK
                        file_accessible = False
                        if "403" not in str(access_error) and "Forbidden" not in str(access_error):
                            logger.debug(f"File access test failed for {file}: {access_error}")
                    
                    # Return file even if it doesn't exist to allow regeneration
                    # This prevents lost references when files are temporarily unavailable
                    file = self.field.attr_class(instance, self.field, file)
                    instance.__dict__[self.field.name] = file
                    return file
                    
                except Exception as e:
                    # Log the error for debugging
                    logger.error(f"Error converting file path to FieldFile: {str(e)}")
                    # Return the string path instead of None to preserve the reference
                    return file
            
            return file
            
        except Exception as e:
            logger.error(f"Error in SafeImageFieldDescriptor.__get__: {str(e)}")
            # Return None only as a last resort if everything else fails
            return None

    def __set__(self, instance, value):
        instance.__dict__[self.field.name] = value

class SafeImageField(models.ImageField):
    """Custom ImageField that handles missing files gracefully"""
    def contribute_to_class(self, cls, name, **kwargs):
        super().contribute_to_class(cls, name, **kwargs)
        setattr(cls, self.name, SafeImageFieldDescriptor(self))

    def pre_save(self, model_instance, add):
        """Handle pre-save file operations"""
        file = super().pre_save(model_instance, add)
        # Log pre-save operation for debugging
        logger.info(f"SafeImageField pre_save for {self.name} with file: {file}")
        
        if file and not hasattr(file, '_committed'):
            # Add the _committed attribute if it doesn't exist
            setattr(file, '_committed', True)
        elif file and not file._committed:
            # Get the new file path
            file.name = self.generate_filename(model_instance, file.name)
            # Ensure the file is saved
            file.save(file.name, file.file, save=False)
        return file

    def save_form_data(self, instance, data):
        """Handle form data saving"""
        logger.info(f"SafeImageField save_form_data called with data type: {type(data)}")
        
        # If data is None or False, keep the existing value
        if data is None or data is False:
            logger.info(f"File upload data is None or False, keeping existing value")
            return
            
        # If data is not a string and is a file-like object (upload)
        if data and not isinstance(data, str) and hasattr(data, 'name'):
            logger.info(f"Processing file upload: {data.name}")
            
            # Generate a unique filename
            timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
            unique_id = uuid.uuid4().hex[:8]
            filename = f"{timestamp}_{unique_id}_{data.name}"
            
            # Determine target path
            instance_id = getattr(instance, 'id', None) or 'new'
            
            if self.upload_to:
                # If upload_to is specified, use it with instance id subfolder
                target_dir = self.upload_to.rstrip('/')
                target_path = f"{target_dir}/{instance_id}/{filename}"
            else:
                # Otherwise use a standard format
                target_path = f"course_content/{instance_id}/{filename}"
                
            logger.info(f"Saving file to: {target_path}")
                
            # Save file to storage
            saved_path = default_storage.save(target_path, data)
            logger.info(f"File saved to: {saved_path}")
            
            # Update the model field with the saved path
            setattr(instance, self.attname, saved_path)
            
            # Mark the file as committed
            if hasattr(data, '_committed'):
                data._committed = True
                
            logger.info(f"Instance {self.attname} set to: {getattr(instance, self.attname)}")
        else:
            # For string values or other types, use the parent method
            super().save_form_data(instance, data)

    def generate_filename(self, instance, filename):
        """Generate the complete file path"""
        # Create a unique filename to avoid collisions
        timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
        unique_id = uuid.uuid4().hex[:8]
        unique_filename = f"{timestamp}_{unique_id}_{filename}"
        
        # Use instance id for better organization
        instance_id = getattr(instance, 'id', None) or 'new'
        
        # Use upload_to if specified
        if self.upload_to:
            target_dir = self.upload_to.rstrip('/')
            return f"{target_dir}/{instance_id}/{unique_filename}"
        
        # Default path
        return f"course_content/{instance_id}/{unique_filename}"

def course_image_path(instance, filename):
    """Generate file path for course images with 255 character limit"""
    # Get the base filename and extension
    name, ext = os.path.splitext(filename)
    
    # Generate a unique identifier
    unique_id = uuid.uuid4().hex[:8]
    
    # Truncate the filename to ensure total path length stays under 255
    max_name_length = 180
    if len(name) > max_name_length:
        name = name[:max_name_length]
    
    # Construct the new filename
    new_filename = f"{name}_{unique_id}{ext}"
    
    # Create the path with course ID as the main folder
    return f"course_{instance.id}/images/{new_filename}"

def course_video_path(instance, filename):
    """Generate file path for course videos with 255 character limit"""
    # Get the base filename and extension
    name, ext = os.path.splitext(filename)
    
    # Generate a unique identifier
    unique_id = uuid.uuid4().hex[:8]
    
    # Clean the filename (remove spaces and special characters)
    clean_name = name.replace(' ', '_').replace('(', '').replace(')', '')
    
    # Truncate the filename to ensure total path length stays under 255
    max_name_length = 180
    if len(clean_name) > max_name_length:
        clean_name = clean_name[:max_name_length]
    
    # Construct the new filename
    new_filename = f"{clean_name}_{unique_id}{ext}"
    
    # Create the path with course ID as the main folder
    return f"course_videos/{instance.id}/{new_filename}"

class Course(models.Model):
    """Main course model"""
    title = models.TextField()
    short_description = models.TextField(blank=True, null=True, help_text="Brief description of the course")
    description = TinyMCEField(blank=True, default="", help_text="Detailed description of the course")
    course_code = models.CharField(max_length=50, blank=True, null=True, help_text="Course code or identifier")
    course_outcomes = TinyMCEField(blank=True, default="", help_text="Expected learning outcomes for the course")
    course_rubrics = TinyMCEField(blank=True, default="", help_text="Assessment rubrics for the course")
    category = models.ForeignKey(
        CourseCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='courses'
    )
    topics = models.ManyToManyField(
        'Topic',
        through='CourseTopic',
        related_name='courses',
        blank=True
    )
    course_image = models.ImageField(
        upload_to=course_image_path,
        null=True,
        blank=True,
        max_length=500,
        help_text="Course thumbnail image"
    )
    course_video = models.FileField(
        upload_to=course_video_path,
        null=True,
        blank=True,
        max_length=500,
        help_text="Course introduction video"
    )
    is_active = models.BooleanField(default=True)
    is_temporary = models.BooleanField(default=False, help_text="Whether this course is temporary")
    
    # Course Settings
    language = models.CharField(
        max_length=10,
        choices=[
            ('en', 'English'),
            ('es', 'Spanish'),
            ('fr', 'French')
        ],
        default='en',
        help_text="Primary language of the course"
    )
    visibility = models.CharField(
        max_length=20,
        choices=[
            ('public', 'Public'),
            ('private', 'Private'),
            ('password', 'Password Protected')
        ],
        default='public',
        help_text="Course visibility setting"
    )
    schedule_type = models.CharField(
        max_length=20,
        choices=[
            ('self_paced', 'Self-paced'),
            ('scheduled', 'Scheduled')
        ],
        default='self_paced',
        help_text="Course schedule type"
    )
    require_enrollment = models.BooleanField(
        default=True,
        help_text="Require enrollment to access course"
    )
    sequential_progression = models.BooleanField(
        default=False,
        help_text="Require sequential progression through topics"
    )
    all_topics_complete = models.BooleanField(
        default=False,
        help_text="Require all topics to be completed"
    )
    minimum_score = models.BooleanField(
        default=False,
        help_text="Require minimum score to complete"
    )
    certificate_type = models.CharField(
        max_length=20,
        choices=[
            ('standard', 'Standard Certificate'),
            ('custom', 'Custom Certificate')
        ],
        default='standard',
        help_text="Type of certificate issued"
    )
    certificate_template = models.ForeignKey(
        'certificates.CertificateTemplate',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='courses',
        help_text="Certificate template to use for this course"
    )
    
    # Course Availability Settings
    catalog_visibility = models.CharField(
        max_length=20,
        choices=[
            ('visible', 'Visible in Catalog'),
            ('hidden', 'Hidden from Catalog')
        ],
        default='visible',
        help_text="Control whether this course appears in the catalog"
    )
    public_enrollment = models.BooleanField(
        default=True,
        help_text="Allow anyone to enroll in this course"
    )
    enrollment_capacity = models.PositiveIntegerField(
        null=True, 
        blank=True,
        help_text="Maximum number of learners allowed (leave blank for unlimited)"
    )
    require_enrollment_approval = models.BooleanField(
        default=False,
        help_text="Require instructor approval for enrollment requests"
    )
    
    # Course Schedule and Access Rules
    start_date = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="When learners can start taking this course (leave blank for immediate access)"
    )
    end_date = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="When access to this course ends (leave blank for unlimited access)"
    )
    time_limit_days = models.PositiveIntegerField(
        null=True, 
        blank=True,
        help_text="Days allowed to complete the course from enrollment (leave blank for unlimited time)"
    )
    retain_access_after_completion = models.BooleanField(
        default=True,
        help_text="Allow learners to access course content after completion"
    )
    prerequisites = models.ManyToManyField(
        'self',
        symmetrical=False,
        related_name='required_for',
        blank=True,
        help_text="Courses that must be completed before enrolling"
    )
    
    # Course Completion Settings
    enforce_sequence = models.BooleanField(
        default=False,
        help_text="If enabled, learners must complete topics in order"
    )
    completion_percentage = models.PositiveIntegerField(
        default=100,
        help_text="Percentage of topics that must be completed to finish the course"
    )
    passing_score = models.PositiveIntegerField(
        default=70,
        help_text="Minimum score required to pass the course (percentage)"
    )
    certificate_enabled = models.BooleanField(
        default=False,
        help_text="Issue certificates upon course completion"
    )
    issue_certificate = models.BooleanField(
        default=False,
        help_text="Issue certificates to learners upon completion"
    )
    
    # Group Access Integration
    accessible_groups = models.ManyToManyField(
        'groups.BranchGroup',
        through='groups.CourseGroupAccess',
        related_name='accessible_courses',
        blank=True
    )
    
    # Branch and Instructor Relations
    branch = models.ForeignKey(
        Branch,
        on_delete=models.CASCADE,
        related_name="courses",
        null=True,
        blank=True,
        help_text="The branch this course belongs to."
    )
    instructor = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        related_name="instructor_courses",
        limit_choices_to={"role": "instructor"},
        help_text="The instructor assigned to this course."
    )
    
    # Enrollment
    enrolled_users = models.ManyToManyField(
        CustomUser,
        through=CourseEnrollment,
        through_fields=('course', 'user'),
        related_name="enrolled_courses",
        blank=True,
        help_text="The learners enrolled in this course."
    )
    
    # Course Pricing
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0.00,
        help_text="Price of the course"
    )
    coupon_code = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text="Discount coupon code"
    )
    discount_percentage = models.PositiveIntegerField(
        default=0,
        help_text="Discount percentage (0-100)"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        """Custom save method for course"""
        # Store the initial is_active state before any changes
        is_new = self.pk is None
        
        # Check if this is a price-only update
        price_only_update = False
        if kwargs.get('update_fields') and all(field in ['price', 'coupon_code', 'discount_percentage'] for field in kwargs['update_fields']):
            price_only_update = True
        
        # Only run clean if this is not a price-only update
        if not price_only_update:
            try:
                self.clean()
            except ValidationError as e:
                # If the validation error is only about course_image, log but continue
                if hasattr(e, 'error_dict') and len(e.error_dict) == 1 and 'course_image' in e.error_dict:
                    logger.warning(f"Ignoring course image validation for course save: {str(e)}")
                elif hasattr(e, 'message_dict') and len(e.message_dict) == 1 and 'course_image' in e.message_dict:
                    logger.warning(f"Ignoring course image validation for course save: {str(e)}")
                else:
                    # Re-raise if there are other validation errors
                    raise
        
        # Ensure course is active by default for new courses
        if is_new and self.is_active is None:
            self.is_active = True
        
        # Make sure active courses are visible in the catalog
        # Important: Don't change visibility when price/discount are set
        if self.is_active and not (self.price > 0 or self.discount_percentage > 0 or self.coupon_code):
            self.catalog_visibility = 'visible'
        
        # Ensure the user has a branch set
        if self.instructor and not self.branch and self.instructor.branch:
            self.branch = self.instructor.branch
        
        # Ensure timezone-aware datetimes to prevent warnings
        if self.start_date and timezone.is_naive(self.start_date):
            self.start_date = timezone.make_aware(self.start_date)
        if self.end_date and timezone.is_naive(self.end_date):
            self.end_date = timezone.make_aware(self.end_date)
            
        # Continue with the save operation
        super().save(*args, **kwargs)
        
        # If this is a new record, create the course directories
        if is_new:
            self._ensure_course_directories()
            
            # Auto-enroll the instructor if this is a new course
            if self.instructor:
                try:
                    from django.apps import apps
                    CourseEnrollment = apps.get_model('courses', 'CourseEnrollment')
                    CourseEnrollment.objects.get_or_create(
                        course=self,
                        user=self.instructor
                    )
                    logger.info(f"Auto-enrolled instructor {self.instructor.username} in course {self.title}")
                except Exception as e:
                    logger.error(f"Error auto-enrolling instructor: {str(e)}")
        
        # Return the saved instance
        return self

    def _ensure_course_directories(self):
        """Create necessary directories for course files"""
        if not self.pk:
            return
            
        # Define paths for course files
        media_root = settings.MEDIA_ROOT
        
        # Skip directory creation if using S3 storage (MEDIA_ROOT is None)
        if media_root is None:
            logger.info(f"Using S3 storage, skipping local directory creation for course {self.pk}")
            return
        
        course_images_dir = os.path.join(media_root, 'course_images', str(self.pk))
        course_videos_dir = os.path.join(media_root, 'course_videos', str(self.pk))
        
        # Create directories if they don't exist
        for directory in [course_images_dir, course_videos_dir]:
            if not os.path.exists(directory):
                try:
                    os.makedirs(directory, exist_ok=True)
                    logger.info(f"Created directory: {directory}")
                except Exception as e:
                    logger.error(f"Error creating directory {directory}: {str(e)}")

    def clean(self):
        """Validate course fields with improved error handling"""
        errors = {}
        
        try:
            # Check if image file exists if a path is stored
            if self.course_image:
                from django.core.files.storage import default_storage
                
                # Skip validation for new uploads that haven't been committed yet
                if hasattr(self.course_image, '_committed') and not self.course_image._committed:
                    pass  # New upload, skip validation
                elif hasattr(self.course_image, 'name') and self.course_image.name:
                    # Test file access without using exists() to avoid HeadObject permission issues
                    try:
                        test_file = default_storage.open(self.course_image.name)
                        test_file.close()
                    except Exception as img_error:
                        # Handle different types of errors gracefully
                        if "403" in str(img_error) or "Forbidden" in str(img_error):
                            logger.warning(f"S3 permission denied for course image: {self.course_image.name}")
                        elif "NoSuchKey" in str(img_error) or "not found" in str(img_error):
                            logger.warning(f"Course image file does not exist: {self.course_image.name}")
                        else:
                            logger.warning(f"Course image access error: {img_error}")
                        # Don't add to errors to prevent blocking saves
        except Exception as e:
            # For any errors with image validation, just log and continue
            logger.warning(f"Course image validation error for course {self.id}: {str(e)}")
        
        # Validate certificate settings (only if not disabled)
        try:
            if hasattr(self, 'certificate_enabled') and self.certificate_enabled and not self.certificate_template:
                errors['certificate_template'] = ['A certificate template must be selected if certificates are enabled.']
        except Exception as e:
            logger.warning(f"Certificate validation error: {str(e)}")
            
        # Ensure discount percentage is valid
        try:
            if hasattr(self, 'discount_percentage') and self.discount_percentage is not None:
                if self.discount_percentage < 0 or self.discount_percentage > 100:
                    errors['discount_percentage'] = ['Discount percentage must be between 0 and 100.']
        except Exception as e:
            logger.warning(f"Discount validation error: {str(e)}")
            
        # Validate prerequisites (prevent circular dependencies) - only for existing courses
        try:
            if self.pk:
                if hasattr(self, 'prerequisites') and self.prerequisites.filter(id=self.pk).exists():
                    errors['prerequisites'] = ['A course cannot be a prerequisite for itself.']
        except Exception as e:
            logger.warning(f"Prerequisites validation error: {str(e)}")
        
        # Check if a paid course has a branch assigned (only for existing courses)
        # Super admin users (business level) are exempt from branch requirements
        try:
            if (self.pk and hasattr(self, 'price') and self.price and self.price > 0 and 
                not self.branch and not (hasattr(self, '_created_by_superadmin') and self._created_by_superadmin)):
                # This is a warning, not a blocking error for updates
                logger.warning(f"Paid course {self.pk} does not have a branch assigned")
        except Exception as e:
            logger.warning(f"Branch validation error: {str(e)}")
            
        # Validate date relationships
        try:
            if hasattr(self, 'start_date') and hasattr(self, 'end_date'):
                if self.start_date and self.end_date and self.start_date > self.end_date:
                    errors['end_date'] = ['End date must be after start date']
        except Exception as e:
            logger.warning(f"Date validation error: {str(e)}")
        
        # Validate branch and instructor relationships (only warn, don't block)
        try:
            if self.instructor and self.branch:
                if hasattr(self.instructor, 'branch') and self.instructor.branch != self.branch:
                    logger.warning(f"Course {self.pk}: Instructor {self.instructor.id} does not belong to course branch {self.branch.id}")
        except Exception as e:
            logger.warning(f"Instructor-branch validation error: {str(e)}")
        
        # Only check group access if the course already exists (warn only)
        try:
            if self.pk and hasattr(self, 'accessible_groups'):
                for group in self.accessible_groups.all():
                    if hasattr(group, 'branch') and group.branch != self.branch:
                        logger.warning(f"Group {group.id} does not belong to course branch {self.branch.id}")
        except Exception as e:
            logger.warning(f"Group access validation error: {str(e)}")
            
        # Only raise ValidationError if there are actual blocking errors
        if errors:
            raise ValidationError(errors)

    def __str__(self) -> str:
        return self.title

    def is_enrolled(self, user: CustomUser) -> bool:
        """Check if user is enrolled in the course"""
        return self.enrolled_users.filter(id=user.id).exists()

    def get_next_available_topic(self, user: CustomUser) -> Optional['Topic']:
        """Get next available topic for user based on sequence settings"""
        if not self.enforce_sequence:
            return self.topics.filter(is_active=True).first()
        
        completed_topics = TopicProgress.objects.filter(
            user=user,
            topic__course=self,
            completed=True
        ).values_list('topic_id', flat=True)
        
        return self.topics.filter(
            is_active=True
        ).exclude(
            id__in=completed_topics
        ).order_by('order').first()

    def can_access_topic(self, user: CustomUser, topic: 'Topic') -> bool:
        """Check if user can access specific topic based on sequence"""
        if not self.enforce_sequence:
            return True
            
        previous_topics = self.topics.filter(
            order__lt=topic.order
        ).values_list('id', flat=True)
        
        completed_count = TopicProgress.objects.filter(
            user=user,
            topic_id__in=previous_topics,
            completed=True
        ).count()
        
        return completed_count == len(previous_topics)

    def get_group_permissions(self, group: 'groups.models.BranchGroup') -> Dict[str, bool]:
        """Get permissions for a specific group"""
        try:
            access = self.group_access.get(group=group)
            return {
                'can_access': True,
                'can_modify': access.can_modify
            }
        except models.ObjectDoesNotExist:
            return {
                'can_access': False,
                'can_modify': False
            }

    def user_has_access(self, user: CustomUser) -> bool:
        """Check if user has access through enrollment or group membership - Fixed Role Logic"""
        if user.is_superuser:
            return True
        
        # Branch admin access
        if user.role == 'admin' and user.branch == self.branch:
            return True
            
        # Primary instructor access
        if user.role == 'instructor' and user == self.instructor:
            return True
            
        # Invited instructor access (instructors assigned to course by admin)
        if user.role == 'instructor':
            # Check if instructor is enrolled in the course (invited instructor)
            is_enrolled = self.enrolled_users.filter(id=user.id).exists()
            if is_enrolled:
                return True
            
            # Check if instructor has group access
            instructor_group_access = self.accessible_groups.filter(
                memberships__user=user,
                memberships__is_active=True
            ).exists()
            if instructor_group_access:
                return True
            
            # Instructors without enrollment or group access cannot access
            return False
            
        # Group access check for all roles
        group_access = self.accessible_groups.filter(
            memberships__user=user,
            memberships__is_active=True,
            memberships__custom_role__can_view=True
        ).exists()
        
        if group_access:
            return True
            
        # For learner role ONLY, check enrollment and course active status
        if user.role == 'learner':
            # Learners can only access active (published) courses they're enrolled in
            if not self.is_active:
                return False
            return self.enrolled_users.filter(id=user.id).exists()
            
        # Non-learner, non-instructor roles (like custom roles) need explicit group access
        return False

    def user_can_modify(self, user: CustomUser) -> bool:
        """Check if user can modify course content - Role-based permissions"""
        import logging
        logger = logging.getLogger(__name__)
        
        logger.info(f"Checking user_can_modify for user {user.id} ({user.role}) on course {self.id}")
        logger.info(f"Course instructor: {self.instructor}")
        logger.info(f"Course branch: {self.branch}")
        logger.info(f"User branch: {getattr(user, 'branch', 'N/A')}")
        
        # Superuser and global admin always have access
        if user.is_superuser:
            logger.info("User is superuser - allowing modification")
            return True
            
        if user.role == 'globaladmin':
            logger.info("User is globaladmin - allowing modification")
            return True
            
        # Superadmin with business assignment
        if user.role == 'superadmin':
            # Check if user has business assignment for this course's business
            if hasattr(self, 'branch') and self.branch and hasattr(self.branch, 'business'):
                has_business_access = user.business_assignments.filter(
                    business=self.branch.business, 
                    is_active=True
                ).exists()
                logger.info(f"Superadmin business access check: {has_business_access}")
                if has_business_access:
                    return True
            # Fallback: allow if no business restriction or if user is superadmin
            logger.info("Superadmin - allowing modification (fallback)")
            return True
            
        # Admin with matching branch
        if user.role == 'admin':
            if hasattr(user, 'branch') and user.branch == self.branch:
                logger.info("User is admin with matching branch - allowing modification")
                return True
            # Fallback: allow admin access if no branch restriction
            if not hasattr(user, 'branch') or not self.branch:
                logger.info("Admin with no branch restriction - allowing modification")
                return True
                
        # Primary instructor check
        if user.role == 'instructor' and user == self.instructor:
            logger.info("User is primary instructor - allowing modification")
            return True
            
        # Invited instructor check (instructors assigned by admin)
        if user.role == 'instructor':
            # Check if instructor is enrolled in the course (invited instructor)
            is_enrolled = self.enrolled_users.filter(id=user.id).exists()
            if is_enrolled:
                logger.info("User is enrolled instructor - allowing modification")
                return True
                
            # Check if instructor has group access with edit permissions
            instructor_group_access = self.accessible_groups.filter(
                memberships__user=user,
                memberships__is_active=True,
                memberships__custom_role__can_edit=True
            ).exists()
            if instructor_group_access:
                logger.info("User has group access with edit permissions - allowing modification")
                return True
                
            # Fallback: allow instructor access if they have any relationship to the course
            if hasattr(self, 'instructor') and self.instructor and user.id == self.instructor.id:
                logger.info("User is course instructor (fallback check) - allowing modification")
                return True
                
            logger.info("Instructor has no edit permissions - denying modification")
            return False
                
        # Learners and other non-instructor roles CANNOT modify course content
        # Only view access through enrollment
        logger.info(f"User role {user.role} cannot modify course content - denying modification")
        return False

    def get_learners(self) -> 'QuerySet[CustomUser]':
        """Get all actual learners enrolled in this course"""
        from users.models import CustomUser
        return CustomUser.objects.filter(
            id__in=self.enrolled_users.filter(role='learner').values_list('id', flat=True)
        )
    
    def get_instructors(self) -> 'QuerySet[CustomUser]':
        """Get all instructors who can access this course"""
        from users.models import CustomUser
        instructors = set()
        
        # Add primary instructor
        if self.instructor:
            instructors.add(self.instructor)
            
        # Add invited instructors (enrolled instructors)
        enrolled_instructors = CustomUser.objects.filter(
            id__in=self.enrolled_users.filter(role='instructor').values_list('id', flat=True)
        )
        instructors.update(enrolled_instructors)
        
        # Add instructors with group access
        group_instructors = CustomUser.objects.filter(
            role='instructor',
            group_memberships__group__in=self.accessible_groups.all(),
            group_memberships__is_active=True
        ).distinct()
        instructors.update(group_instructors)
        
        return list(instructors)

    def get_editors(self) -> List[CustomUser]:
        """Get all users who can edit this course"""
        editors = set()
        
        # Add primary instructor
        if self.instructor:
            editors.add(self.instructor)
            
        # Add branch admin
        if self.branch:
            editors.update(
                CustomUser.objects.filter(role='admin', branch=self.branch)
            )
            
        # Add group-based editors
        group_editors = CustomUser.objects.filter(
            role='instructor',
            group_memberships__group__in=self.accessible_groups.all(),
            group_memberships__is_active=True,
            group_memberships__custom_role__can_manage_content=True,
            group_memberships__group__course_access__course=self,
            group_memberships__group__course_access__can_modify=True
        )
        
        editors.update(group_editors)
        return editors
    
    def delete(self, *args: Any, **kwargs: Any) -> Tuple[int, Dict[str, int]]:
        """
        Enhanced delete method with comprehensive cascade deletion for Course.
        This method ensures all related data is properly cleaned up when a course is deleted.
        """
        try:
            logger.info(f"Starting comprehensive deletion for Course: {self.title} (ID: {self.id})")
            
            # 1. DELETE ALL COURSE ENROLLMENTS
            try:
                from courses.models import CourseEnrollment
                enrollments = CourseEnrollment.objects.filter(course=self)
                enrollment_count = enrollments.count()
                if enrollment_count > 0:
                    logger.info(f"Deleting {enrollment_count} course enrollments")
                    enrollments.delete()
                    logger.info(f"Successfully deleted {enrollment_count} course enrollments")
            except Exception as e:
                logger.error(f"Error deleting course enrollments: {str(e)}")
            
            # 2. DELETE ALL COURSE SECTIONS
            try:
                from courses.models import Section
                sections = Section.objects.filter(course=self)
                section_count = sections.count()
                if section_count > 0:
                    logger.info(f"Deleting {section_count} course sections")
                    sections.delete()
                    logger.info(f"Successfully deleted {section_count} course sections")
            except Exception as e:
                logger.error(f"Error deleting course sections: {str(e)}")
            
            # 3. DELETE ALL COURSE FEATURES
            try:
                from courses.models import CourseFeature
                features = CourseFeature.objects.filter(course=self)
                feature_count = features.count()
                if feature_count > 0:
                    logger.info(f"Deleting {feature_count} course features")
                    features.delete()
                    logger.info(f"Successfully deleted {feature_count} course features")
            except Exception as e:
                logger.error(f"Error deleting course features: {str(e)}")
            
            # 4. DELETE ALL COMPLETION REQUIREMENTS
            try:
                from courses.models import CourseCompletionRequirement
                requirements = CourseCompletionRequirement.objects.filter(course=self)
                requirement_count = requirements.count()
                if requirement_count > 0:
                    logger.info(f"Deleting {requirement_count} completion requirements")
                    requirements.delete()
                    logger.info(f"Successfully deleted {requirement_count} completion requirements")
            except Exception as e:
                logger.error(f"Error deleting completion requirements: {str(e)}")
            
            # 5. DELETE ALL ASSIGNMENT RELATIONSHIPS
            try:
                from assignments.models import AssignmentCourse, AssignmentSubmission, AssignmentFeedback
                
                # Get all assignments linked to this course
                course_assignments = AssignmentCourse.objects.filter(course=self)
                assignment_count = course_assignments.count()
                
                if assignment_count > 0:
                    logger.info(f"Found {assignment_count} assignments linked to this course")
                    
                    # Delete all submissions and feedback for these assignments
                    for course_assignment in course_assignments:
                        assignment = course_assignment.assignment
                        
                        # Delete all submissions for this assignment
                        submissions = AssignmentSubmission.objects.filter(assignment=assignment)
                        submission_count = submissions.count()
                        if submission_count > 0:
                            logger.info(f"Deleting {submission_count} submissions for assignment: {assignment.title}")
                            
                            # Delete all feedback for these submissions
                            for submission in submissions:
                                feedback_count = AssignmentFeedback.objects.filter(submission=submission).count()
                                if feedback_count > 0:
                                    AssignmentFeedback.objects.filter(submission=submission).delete()
                                    logger.info(f"Deleted {feedback_count} feedback records for submission {submission.id}")
                            
                            # Delete all submissions
                            submissions.delete()
                            logger.info(f"Deleted {submission_count} submissions for assignment: {assignment.title}")
                        
                        # Delete the assignment itself if it's only linked to this course
                        if assignment.courses.count() <= 1:  # Only linked to this course
                            logger.info(f"Deleting assignment: {assignment.title} (only linked to this course)")
                            assignment.delete()
                        else:
                            logger.info(f"Keeping assignment: {assignment.title} (linked to other courses)")
                    
                    # Delete the course-assignment relationships
                    course_assignments.delete()
                    logger.info(f"Deleted {assignment_count} course-assignment relationships")
            except Exception as e:
                logger.error(f"Error deleting assignment relationships: {str(e)}")
            
            # 6. DELETE ALL GRADEBOOK DATA
            try:
                from gradebook.models import Grade
                
                # Delete all grades related to this course
                grades = Grade.objects.filter(course=self)
                grade_count = grades.count()
                if grade_count > 0:
                    logger.info(f"Deleting {grade_count} gradebook entries for this course")
                    grades.delete()
                    logger.info(f"Successfully deleted {grade_count} gradebook entries")
            except Exception as e:
                logger.error(f"Error deleting gradebook data: {str(e)}")
            
            # 7. DELETE ALL REPORT TEMPLATE DATA
            try:
                from reports.models import Report
                
                # Try to import ReportTemplate if it exists
                try:
                    from reports.models import ReportTemplate
                    
                    # Delete report templates that reference this course
                    templates = ReportTemplate.objects.filter(
                        models.Q(content__icontains=f'course_id:{self.id}') |
                        models.Q(content__icontains=f'course:{self.id}') |
                        models.Q(content__icontains=self.title)
                    )
                    template_count = templates.count()
                    if template_count > 0:
                        logger.info(f"Deleting {template_count} report templates referencing this course")
                        templates.delete()
                        logger.info(f"Successfully deleted {template_count} report templates")
                except ImportError:
                    logger.info("ReportTemplate model not available - skipping template cleanup")
                
                # Delete reports that reference this course
                # Note: Report model may not have a 'content' field
                # Check if the field exists before filtering
                if hasattr(Report, 'content'):
                    reports = Report.objects.filter(
                        models.Q(content__icontains=f'course_id:{self.id}') |
                        models.Q(content__icontains=f'course:{self.id}') |
                        models.Q(content__icontains=self.title)
                    )
                else:
                    # Try alternative fields that might contain course references
                    reports = Report.objects.filter(
                        models.Q(title__icontains=self.title) |
                        models.Q(description__icontains=self.title)
                    )
                report_count = reports.count()
                if report_count > 0:
                    logger.info(f"Deleting {report_count} reports referencing this course")
                    reports.delete()
                    logger.info(f"Successfully deleted {report_count} reports")
            except Exception as e:
                logger.error(f"Error deleting report data: {str(e)}")
            
            # 8. SCORM content deletion removed - no longer supported

            # 9. DELETE ALL TOPICS (EXCLUSIVELY LINKED TO THIS COURSE)
            try:
                # Get all topics associated with this course that are not used by other courses
                topics_to_delete = []
                course_topics = CourseTopic.objects.filter(course=self)
                
                # Collect all topics that belong exclusively to this course
                for course_topic in course_topics:
                    topic = course_topic.topic
                    # Check if the topic is used in other courses
                    if topic.coursetopic_set.count() <= 1:
                        topics_to_delete.append(topic.id)
                
                # Log the number of topics to be deleted
                logger.info(f"Course.delete: Deleting {len(topics_to_delete)} topics associated exclusively with course {self.id}")
                
                # Delete the topics that were used exclusively by this course
                # Note: Topic.delete() method already handles comprehensive cleanup
                for topic_id in topics_to_delete:
                    try:
                        topic = Topic.objects.get(id=topic_id)
                        logger.info(f"Deleting topic: {topic.title} (ID: {topic.id})")
                        topic.delete()  # This will trigger Topic.delete() which handles comprehensive cleanup
                    except Exception as e:
                        logger.error(f"Error deleting topic {topic_id}: {str(e)}")
                
                # Delete course-topic relationships
                course_topics.delete()
                logger.info(f"Deleted {course_topics.count()} course-topic relationships")
            except Exception as e:
                logger.error(f"Error deleting course topics: {str(e)}")
            
            # 10. DELETE COURSE MEDIA FILES
            try:
                # Delete course image if it exists
                if self.course_image:
                    try:
                        # Delete the file from storage
                        self.course_image.delete(save=False)
                        # Skip directory cleanup for S3 storage
                        # S3 storage doesn't support absolute paths, skip directory cleanup
                        pass
                        logger.info(f"Deleted course image: {self.course_image.name}")
                    except Exception as e:
                        logger.error(f"Error deleting course image: {str(e)}")

                # Delete course video if it exists
                if self.course_video:
                    try:
                        # Delete the file from storage
                        self.course_video.delete(save=False)
                        # Skip directory cleanup for S3 storage
                        # S3 storage doesn't support absolute paths, skip directory cleanup
                        pass
                        logger.info(f"Deleted course video: {self.course_video.name}")
                    except Exception as e:
                        logger.error(f"Error deleting course video: {str(e)}")

                content_dir = os.path.join(settings.MEDIA_ROOT, 'course_content', str(self.id))
                if os.path.exists(content_dir):
                    try:
                        shutil.rmtree(content_dir)
                        logger.info(f"Deleted course content directory: {content_dir}")
                    except Exception as e:
                        logger.error(f"Error deleting course content directory: {str(e)}")
                        
                # Delete any media folders related to this course (local storage)
                media_folders = [
                    f"course_images/{self.id}",
                    f"course_videos/{self.id}",
                    f"courses/{self.id}",
                    f"editor_uploads/courses/{self.id}"
                ]
                
                for folder in media_folders:
                    try:
                        logger.info(f"Deleting course media folder: {folder}")
                        # Use S3 permission-safe approach - avoid exists() calls
                        from django.core.files.storage import default_storage
                        try:
                            # Directly try to list and delete files without checking folder existence
                            files, dirs = default_storage.listdir(folder)
                            for file in files:
                                file_path = f"{folder}/{file}"
                                try:
                                    default_storage.delete(file_path)
                                    logger.info(f"Deleted file: {file_path}")
                                except Exception as file_error:
                                    if "403" in str(file_error) or "Forbidden" in str(file_error):
                                        logger.warning(f"S3 permission denied for file {file_path}: {file_error}")
                                    elif "NoSuchKey" in str(file_error) or "not found" in str(file_error):
                                        logger.info(f"File {file_path} does not exist - skipping")
                                    else:
                                        logger.error(f"Error deleting file {file_path}: {file_error}")
                        except Exception as list_error:
                            # Handle folder listing errors gracefully
                            if "403" in str(list_error) or "Forbidden" in str(list_error):
                                logger.warning(f"S3 permission denied for listing {folder}: {list_error}")
                            elif "NoSuchKey" in str(list_error) or "not found" in str(list_error):
                                logger.info(f"Course media folder {folder} does not exist - skipping")
                            else:
                                logger.error(f"Error listing course media folder {folder}: {list_error}")
                        
                        logger.info(f"Successfully processed course media folder: {folder}")
                    except Exception as e:
                        logger.error(f"Error processing course media folder {folder}: {str(e)}")
                
                # S3 cleanup for course files
                try:
                    from core.utils.s3_cleanup import cleanup_course_s3_files
                    s3_results = cleanup_course_s3_files(self.id)
                    successful_s3_deletions = sum(1 for success in s3_results.values() if success)
                    total_s3_files = len(s3_results)
                    if total_s3_files > 0:
                        logger.info(f"S3 cleanup: {successful_s3_deletions}/{total_s3_files} files deleted successfully")
                except Exception as e:
                    logger.error(f"Error during S3 cleanup for course {self.id}: {str(e)}")
                       
            except Exception as e:
                logger.error(f"Error deleting course media files: {str(e)}")
            
            # Call the parent delete method
            super().delete(*args, **kwargs)
            logger.info(f"Successfully completed comprehensive deletion for Course: {self.title} (ID: {self.id})")

        except Exception as e:
            logger.error(f"Error in Course.delete(): {str(e)}")
            raise

    def get_quiz_count(self):
        """Get the number of quiz topics in this course"""
        return self.topics.filter(content_type='Quiz').count()
    
    def get_assignment_count(self):
        """Get the number of assignment topics in this course"""
        return self.topics.filter(content_type='Assignment').count()
    
    def can_create_quiz(self):
        """Check if a new quiz can be created (unlimited for instructors)"""
        # Allow unlimited quiz topics per course
        # The 1 quiz per course limit was removed to allow instructors
        # to create multiple quizzes across different courses
        return True
    
    def can_create_assignment(self):
        """Check if a new assignment can be created (unlimited for instructors)"""
        # Allow unlimited assignment topics per course
        # The 1 assignment per course limit was removed to allow instructors
        # to create multiple assignments across different courses
        return True

class Section(models.Model):
    """Model for course sections to organize topics"""
    name = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='sections')
    order = models.PositiveIntegerField(default=0)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['order', 'created_at']
        
    def __str__(self):
        return self.name or f"Section {self.id}"

class Topic(models.Model):
    """Model for course topics with various content types"""
    TOPIC_TYPE_CHOICES = [
        ('SCORM', 'SCORM Package'),
        ('Video', 'Video'),
        ('Document', 'Document'),
        ('Text', 'Text'),
        ('Audio', 'Audio'),
        ('Web', 'Web Content'),
        ('Quiz', 'Quiz'),
        ('Assignment', 'Assignment'),
        ('EmbedVideo', 'Embedded Video'),
        ('Conference', 'ILT/Conference'),
        ('Discussion', 'Discussion')
    ]

    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('draft', 'Draft'),
        ('archived', 'Archived')
    ]

    ALIGNMENT_CHOICES = [
        ('left', 'Left'),
        ('center', 'Center'),
        ('right', 'Right'),
    ]

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    instructions = models.TextField(blank=True, help_text="Instructions for completing this topic")
    content_type = models.CharField(max_length=20, choices=TOPIC_TYPE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')  # Changed default from 'active' to 'draft'
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    endless_access = models.BooleanField(default=False)
    web_url = models.URLField(max_length=500, blank=True, null=True, help_text="URL for Web Content type topics")
    section = models.ForeignKey(
        'Section',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='topics',
        help_text="Optional section to organize topics"
    )
    content_file = models.FileField(
        upload_to=content_file_path,
        storage=None,  # Use default storage (S3 in production)
        null=True,
        blank=True,
        max_length=255,
        help_text="Upload file for Video, Audio, Document content"
    )
    text_content = TinyMCEField(blank=True, default="", null=True, help_text="Rich text content for Text type topics")
    embed_code = models.TextField(
        null=True,
        blank=True,
        help_text="HTML embed code for embedded video content"
    )
    order = models.PositiveIntegerField(default=0)
    alignment = models.CharField(max_length=10, choices=ALIGNMENT_CHOICES, default='left')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    discussion = models.ForeignKey(
        'discussions.Discussion',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='topics',
        help_text="Associated discussion for Discussion type topics"
    )
    conference = models.ForeignKey(
        'conferences.Conference',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='topics',
        help_text="Associated conference for ILT/Conference type topics"
    )
    quiz = models.ForeignKey(
        'quiz.Quiz',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='topics',
        help_text="Associated quiz for Quiz type topics"
    )
    assignment = models.ForeignKey(
        'assignments.Assignment',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assignment_topics',
        help_text="Associated assignment for Assignment type topics"
    )
    
    # Learner restriction fields
    restrict_to_learners = models.BooleanField(
        default=False, 
        help_text="Enable learner-specific restrictions for this topic"
    )
    restricted_learners = models.ManyToManyField(
        CustomUser,
        blank=True,
        related_name='restricted_topics',
        help_text="Learners who are restricted from viewing this topic"
    )

    class Meta:
        ordering = ['order', 'created_at']
        
    def __str__(self):
        return f"{self.title} ({self.get_content_type_display()})"

    def clean(self):
        """Validate topic data"""
        super().clean()
        # SCORM file validation handled at form level
        # Model validation runs too early before files are assigned to the instance
        
        # Validate dates
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValidationError({
                'end_date': _("End date cannot be before start date.")
            })

    def save(self, *args, **kwargs):
        """Handle topic saving with validations"""
        try:
            self.full_clean()
        except ValidationError as e:
            # Log validation errors but continue with save
            logger.error(f"Validation error in Topic.save: {str(e)}")
            
        super().save(*args, **kwargs)
        
    @property
    def course(self):
        """Get the course associated with this topic through CourseTopic relationship"""
        # If the topic doesn't have a primary key yet, we can't query the
        # related set, so return None
        if not self.pk:
            return None
            
        course_topic = self.coursetopic_set.first()
        return course_topic.course if course_topic else None
        
    @course.setter
    def course(self, course_obj):
        """Set the course for this topic by creating or updating a CourseTopic relationship"""
        from django.db.models import Max
        
        # Import CourseTopic here to avoid circular import
        CourseTopic = self.__class__.coursetopic_set.related.related_model
        
        # Delete any existing relationship
        CourseTopic.objects.filter(topic=self).delete()
        
        # Create new relationship with course if provided
        if course_obj:
            # Get the max order value or default to 0
            max_order = CourseTopic.objects.filter(course=course_obj).aggregate(
                Max('order')).get('order__max') or 0
                
            # Create the new relationship
            CourseTopic.objects.create(
                course=course_obj,
                topic=self,
                order=max_order + 1
            )

    def delete(self, *args, **kwargs):
        """
        Enhanced delete method with comprehensive cascade deletion for Topic.
        This method ensures all related data is properly cleaned up when a topic is deleted.
        """
        try:
            logger.info(f"Starting comprehensive deletion for Topic: {self.title} (ID: {self.id})")
            
            # 1. DELETE ALL RELATED PROGRESS DATA
            try:
                from courses.models import TopicProgress
                progress_count = TopicProgress.objects.filter(topic=self).count()
                if progress_count > 0:
                    logger.info(f"Deleting {progress_count} topic progress records")
                    TopicProgress.objects.filter(topic=self).delete()
                    logger.info(f"Successfully deleted {progress_count} topic progress records")
            except Exception as e:
                logger.error(f"Error deleting topic progress: {str(e)}")
            
            # 2. DELETE ALL ASSIGNMENT RELATIONSHIPS
            try:
                from assignments.models import TopicAssignment, AssignmentSubmission, AssignmentFeedback
                
                # Get all assignments linked to this topic
                topic_assignments = TopicAssignment.objects.filter(topic=self)
                assignment_count = topic_assignments.count()
                
                if assignment_count > 0:
                    logger.info(f"Found {assignment_count} assignments linked to this topic")
                    
                    # Delete all submissions and feedback for these assignments
                    for topic_assignment in topic_assignments:
                        assignment = topic_assignment.assignment
                        
                        # Delete all submissions for this assignment
                        submissions = AssignmentSubmission.objects.filter(assignment=assignment)
                        submission_count = submissions.count()
                        if submission_count > 0:
                            logger.info(f"Deleting {submission_count} submissions for assignment: {assignment.title}")
                            
                            # Delete all feedback for these submissions
                            for submission in submissions:
                                feedback_count = AssignmentFeedback.objects.filter(submission=submission).count()
                                if feedback_count > 0:
                                    AssignmentFeedback.objects.filter(submission=submission).delete()
                                    logger.info(f"Deleted {feedback_count} feedback records for submission {submission.id}")
                            
                            # Delete all submissions
                            submissions.delete()
                            logger.info(f"Deleted {submission_count} submissions for assignment: {assignment.title}")
                        
                        # Delete the assignment itself if it's only linked to this topic
                        if assignment.topics.count() <= 1:  # Only linked to this topic
                            logger.info(f"Deleting assignment: {assignment.title} (only linked to this topic)")
                            assignment.delete()
                        else:
                            logger.info(f"Keeping assignment: {assignment.title} (linked to other topics)")
                    
                    # Delete the topic-assignment relationships
                    topic_assignments.delete()
                    logger.info(f"Deleted {assignment_count} topic-assignment relationships")
            except Exception as e:
                logger.error(f"Error deleting assignment relationships: {str(e)}")
            
            # 3. DELETE ALL QUIZ RELATIONSHIPS
            try:
                from quiz.models import Quiz, QuizAttempt, UserAnswer
                
                # Delete quiz attempts and answers for this topic's quiz
                if hasattr(self, 'quiz') and self.quiz:
                    quiz = self.quiz
                    logger.info(f"Deleting quiz data for quiz: {quiz.title}")
                    
                    # Delete all quiz attempts and answers
                    attempts = QuizAttempt.objects.filter(quiz=quiz)
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
                        logger.info(f"Deleted {attempt_count} quiz attempts")
                    
                    # Delete the quiz if it's only linked to this topic
                    if not hasattr(quiz, 'topics') or quiz.topics.count() <= 1:
                        logger.info(f"Deleting quiz: {quiz.title}")
                        quiz.delete()
                    else:
                        logger.info(f"Keeping quiz: {quiz.title} (linked to other topics)")
            except Exception as e:
                logger.error(f"Error deleting quiz relationships: {str(e)}")
            
            # 4. DELETE ALL DISCUSSION DATA
            try:
                from courses.models import Discussion, Comment, Attachment
                
                # Delete discussion and all related data
                if hasattr(self, 'topic_discussion') and self.topic_discussion:
                    discussion = self.topic_discussion
                    logger.info(f"Deleting discussion: {discussion.title}")
                    
                    # Delete all comments and their attachments
                    comments = Comment.objects.filter(discussion=discussion)
                    comment_count = comments.count()
                    if comment_count > 0:
                        logger.info(f"Deleting {comment_count} discussion comments")
                        
                        # Delete all attachments for these comments
                        for comment in comments:
                            attachment_count = Attachment.objects.filter(comment=comment).count()
                            if attachment_count > 0:
                                Attachment.objects.filter(comment=comment).delete()
                                logger.info(f"Deleted {attachment_count} attachments for comment {comment.id}")
                        
                        # Delete all comments
                        comments.delete()
                        logger.info(f"Deleted {comment_count} discussion comments")
                    
                    # Delete discussion attachments
                    discussion_attachments = Attachment.objects.filter(discussion=discussion)
                    discussion_attachment_count = discussion_attachments.count()
                    if discussion_attachment_count > 0:
                        discussion_attachments.delete()
                        logger.info(f"Deleted {discussion_attachment_count} discussion attachments")
                    
                    # Delete the discussion
                    discussion.delete()
                    logger.info(f"Deleted discussion: {discussion.title}")
            except Exception as e:
                logger.error(f"Error deleting discussion data: {str(e)}")
            
            # 5. DELETE ALL GRADEBOOK DATA
            try:
                from gradebook.models import Grade
                
                # Delete all grades related to this topic
                # Note: Grade model may not have a direct 'topic' field
                # Check if the field exists before filtering
                if hasattr(Grade, 'topic'):
                    grades = Grade.objects.filter(topic=self)
                    grade_count = grades.count()
                    if grade_count > 0:
                        logger.info(f"Deleting {grade_count} gradebook entries for this topic")
                        grades.delete()
                        logger.info(f"Successfully deleted {grade_count} gradebook entries")
                else:
                    logger.info("Grade model does not have a 'topic' field - skipping gradebook cleanup")
            except Exception as e:
                logger.error(f"Error deleting gradebook data: {str(e)}")
            
            # 6. DELETE ALL REPORT TEMPLATE DATA
            try:
                from reports.models import Report
                
                # Try to import ReportTemplate if it exists
                try:
                    from reports.models import ReportTemplate
                    
                    # Delete report templates that reference this topic
                    templates = ReportTemplate.objects.filter(
                        models.Q(content__icontains=f'topic_id:{self.id}') |
                        models.Q(content__icontains=f'topic:{self.id}') |
                        models.Q(content__icontains=self.title)
                    )
                    template_count = templates.count()
                    if template_count > 0:
                        logger.info(f"Deleting {template_count} report templates referencing this topic")
                        templates.delete()
                        logger.info(f"Successfully deleted {template_count} report templates")
                except ImportError:
                    logger.info("ReportTemplate model not available - skipping template cleanup")
                
                # Delete reports that reference this topic
                # Note: Report model may not have a 'content' field
                # Check if the field exists before filtering
                if hasattr(Report, 'content'):
                    reports = Report.objects.filter(
                        models.Q(content__icontains=f'topic_id:{self.id}') |
                        models.Q(content__icontains=f'topic:{self.id}') |
                        models.Q(content__icontains=self.title)
                    )
                else:
                    # Try alternative fields that might contain topic references
                    reports = Report.objects.filter(
                        models.Q(title__icontains=self.title) |
                        models.Q(description__icontains=self.title)
                    )
                report_count = reports.count()
                if report_count > 0:
                    logger.info(f"Deleting {report_count} reports referencing this topic")
                    reports.delete()
                    logger.info(f"Successfully deleted {report_count} reports")
            except Exception as e:
                logger.error(f"Error deleting report data: {str(e)}")
            
            # 7. SCORM content deletion removed - no longer supported
            
            # 8. DELETE CONTENT FILES
            if self.content_file:
                try:
                    # Delete the file from S3 storage
                    self.content_file.delete(save=False)
                    logger.info(f"Deleted topic content file: {self.content_file.name}")
                    
                    # Skip directory cleanup for S3 storage
                    # S3 storage doesn't support absolute paths, skip directory cleanup
                    pass
                        
                except Exception as e:
                    logger.error(f"Error deleting topic content file: {str(e)}")
            
            # 8.1. S3 CLEANUP FOR TOPIC FILES
            try:
                from core.utils.s3_cleanup import cleanup_topic_s3_files
                s3_results = cleanup_topic_s3_files(self.id)
                successful_s3_deletions = sum(1 for success in s3_results.values() if success)
                total_s3_files = len(s3_results)
                if total_s3_files > 0:
                    logger.info(f"S3 cleanup: {successful_s3_deletions}/{total_s3_files} files deleted successfully")
            except Exception as e:
                logger.error(f"Error during S3 cleanup for topic {self.id}: {str(e)}")
            
            # 9. DELETE COURSE-TOPIC RELATIONSHIPS
            try:
                from courses.models import CourseTopic
                course_topic_count = CourseTopic.objects.filter(topic=self).count()
                if course_topic_count > 0:
                    logger.info(f"Deleting {course_topic_count} course-topic relationships")
                    CourseTopic.objects.filter(topic=self).delete()
                    logger.info(f"Successfully deleted {course_topic_count} course-topic relationships")
            except Exception as e:
                logger.error(f"Error deleting course-topic relationships: {str(e)}")
            
            # 10. DELETE COMPLETION REQUIREMENTS
            try:
                from courses.models import CourseCompletionRequirement
                requirements = CourseCompletionRequirement.objects.filter(topic=self)
                requirement_count = requirements.count()
                if requirement_count > 0:
                    logger.info(f"Deleting {requirement_count} completion requirements")
                    requirements.delete()
                    logger.info(f"Successfully deleted {requirement_count} completion requirements")
            except Exception as e:
                logger.error(f"Error deleting completion requirements: {str(e)}")
            
            # Call the parent delete method
            super().delete(*args, **kwargs)
            logger.info(f"Successfully completed comprehensive deletion for Topic: {self.title} (ID: {self.id})")
            
        except Exception as e:
            logger.error(f"Error in Topic.delete(): {str(e)}")
            raise

    def user_has_access(self, user):
        """Check if user has access to this topic - requires course enrollment and proper permissions"""
        if user.is_superuser:
            return True
        
        # Check if user is restricted from this topic (learner-specific restrictions)
        if self.restrict_to_learners and user.role == 'learner':
            if self.restricted_learners.filter(id=user.id).exists():
                return False
        
        # Get the course through CourseTopic
        course = Course.objects.filter(coursetopic__topic=self).first()
        if course:
            # All content types (including SCORM) require proper course access
            # This includes enrollment for learners, instructor permissions, etc.
            return course.user_has_access(user)
        return False

    def user_can_modify(self, user):
        """Check if user can modify this topic"""
        if user.is_superuser:
            return True
        # Get the course through CourseTopic
        course = Course.objects.filter(coursetopic__topic=self).first()
        if course:
            return course.user_can_modify(user)
        return False

    def get_completion_requirements(self):
        """Get topic completion requirements based on content type"""
        if self.content_type == 'SCORM':
            if hasattr(self, 'scorm_cloud_content'):
                return {
                    'requires_score': self.scorm_cloud_content.requires_passing_score,
                    'requires_completion': True,
                    'pass_score': self.scorm_cloud_content.passing_score,
                    'requires_passing_score': self.scorm_cloud_content.requires_passing_score
                }
        return {
            'requires_completion': True,
            'requires_score': False,
            'pass_score': None,
            'requires_passing_score': False
        }

    def get_user_progress(self, user):
        """Get progress for a specific user"""
        if self.content_type == 'SCORM':
            scorm_progress = self.get_scorm_progress(user)
            if scorm_progress:
                return scorm_progress
        return TopicProgress.objects.filter(
            topic=self,
            user=user
        ).first()

    def get_scorm_content(self):
        """Get SCORM content with improved error handling"""
        if self.content_type == 'SCORM':
            try:
                # Get SCORM content by content_id
                SCORMCloudContent = apps.get_model('scorm_cloud', 'SCORMCloudContent')
                
                # First check if file exists
                if not self.content_file:
                    logger.warning(f"Topic {self.id} ({self.title}) has no content file")
                    return None
                
                # For S3 storage, we can't use os.path.exists with .path
                # Instead, check if the file has a URL (which means it exists)
                if not hasattr(self.content_file, 'url'):
                    logger.warning(f"Topic {self.id} ({self.title}) content file does not exist: {self.content_file.name}")
                    return None
                
                # Then try to get the SCORM Cloud content
                return SCORMCloudContent.objects.filter(
                    content_id=str(self.id),
                    content_type='topic'
                ).first()
            except Exception as e:
                logger.error(f"Error getting SCORM content for topic {self.id}: {str(e)}")
                return None
        return None

    def get_launch_url(self, user):
        """Get SCORM launch URL for user with branch-specific support"""
        scorm_content = self.get_scorm_content()
        if scorm_content:
            return scorm_content.get_launch_url(user)
        return None

    def get_scorm_progress(self, user):
        """Get SCORM progress for a specific user"""
        if self.content_type == 'SCORM':
            scorm_content = self.get_scorm_content()
            if scorm_content:
                registration = scorm_content.package.get_registration(user)
                return registration
        return None

    def sync_scorm_progress(self, user):
        """Sync SCORM progress data with branch-specific support"""
        scorm_content = self.get_scorm_content()
        if scorm_content:
            return scorm_content.sync_progress(user)
        return False

    def get_user_progress_record(self, user=None):
        """Get progress record for a specific user or the current request user"""
        from django.utils.functional import SimpleLazyObject
        
        # If no user provided, try to get from request context
        if user is None:
            from django.core.exceptions import ObjectDoesNotExist
            from django.template import RequestContext
            try:
                # Try to get user from request context
                context = RequestContext.get_context()
                user = context.get('user', None)
            except:
                return None
                
        # Handle case where user is a lazy object
        if isinstance(user, SimpleLazyObject):
            if not hasattr(user, '_wrapped') or user._wrapped.__class__.__name__ == 'AnonymousUser':
                return None
        
        # Return None for anonymous users
        if not user or not user.is_authenticated:
            return None
            
        # Try to get progress record
        try:
            return self.topicprogress_set.filter(user=user).first()
        except Exception:
            return None

class TopicProgress(models.Model):
    """Model for tracking user progress on topics"""
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='topic_progress'
    )
    topic = models.ForeignKey(
        Topic,
        on_delete=models.CASCADE,
        related_name='user_progress'
    )
    
    # SCORM tracking
    scorm_registration = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="SCORM Cloud registration ID"
    )
    
    # Progress tracking
    progress_data = models.JSONField(
        default=dict,
        help_text="Stores progress data specific to content type"
    )
    bookmark = models.JSONField(
        null=True,
        blank=True,
        help_text="Stores last position or state in content"
    )
    completion_data = models.JSONField(
        null=True,
        blank=True,
        help_text="Detailed completion tracking data"
    )
    
    # Status tracking
    completed = models.BooleanField(default=False)
    completion_method = models.CharField(
        max_length=20,
        choices=[
            ('auto', 'Automatic'),
            ('manual', 'Manual'),
            ('scorm', 'SCORM')
        ],
        default='auto'
    )
    manually_completed = models.BooleanField(default=False)
    
    # Score tracking
    attempts = models.IntegerField(default=0)
    last_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True
    )
    best_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True
    )
    
    # Time tracking
    total_time_spent = models.IntegerField(
        default=0,
        help_text="Total time spent in seconds"
    )
    last_accessed = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    first_accessed = models.DateTimeField(auto_now_add=True)
    
    # Audio progress tracking
    audio_progress = models.FloatField(default=0.0)  # Store progress as percentage
    last_audio_position = models.FloatField(default=0.0)  # Store last position in seconds
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['user', 'topic']),
            # Dashboard performance indexes
            models.Index(fields=['user', 'completed']),
            models.Index(fields=['topic', 'completed']),
            models.Index(fields=['completed', 'completed_at']),
            models.Index(fields=['user', 'last_accessed']),
            models.Index(fields=['user', 'completed', 'last_score']),
            models.Index(fields=['topic', 'user', 'completed']),
        ]
        unique_together = ['user', 'topic']
        ordering = ['-last_accessed']
        
    def __str__(self):
        status = 'Completed' if self.completed else 'In Progress'
        return f"{self.user.username}'s progress on {self.topic.title} - {status}"
    
    @property
    def video_progress(self):
        """Get video progress percentage from progress_data"""
        from core.utils.type_guards import normalize_mixed_type_field, safe_get_float
        
        normalized_data = normalize_mixed_type_field(self.progress_data)
        if normalized_data:
            progress = safe_get_float(normalized_data, 'progress', 0)
            # Handle both percentage (0-100) and decimal (0-1) formats
            if progress <= 1:  # Decimal format (0-1)
                return progress * 100
            else:  # Percentage format (0-100)
                return min(progress, 100)
        return 0.0
    
    def get_progress_percentage(self):
        """Calculate progress percentage for this topic"""
        from core.utils.type_guards import normalize_mixed_type_field, safe_get_float
        
        if self.completed:
            return 100
        
        # Use type-safe progress data handling
        normalized_data = normalize_mixed_type_field(self.progress_data)
        if normalized_data:
            # For Video, Audio, SCORM content
            progress = safe_get_float(normalized_data, 'progress')
            if progress is not None:
                # Handle both percentage (0-100) and decimal (0-1) formats
                if progress <= 1:  # Decimal format (0-1)
                    return round(progress * 100)
                else:  # Percentage format (0-100)
                    return round(min(progress, 100))
            
            # For SCORM content, check completion_percent
            completion = safe_get_float(normalized_data, 'completion_percent')
            if completion is not None:
                return round(min(completion, 100))
        
        # For other content types, use attempts as indicator
        if self.attempts > 0:
            return 50  # In progress if attempted
        
        return 0  # Not started

    def save(self, *args, **kwargs):
        """Override save to ensure completed_at is set when completed becomes True"""
        if self.completed and not self.completed_at:
            from django.utils import timezone
            self.completed_at = timezone.now()
        super().save(*args, **kwargs)

    def init_progress_data(self):
        """Initialize progress_data with default values for content type"""
        from django.utils import timezone
        timestamp_iso = timezone.now().isoformat()

        # Initialize progress_data if missing or not a valid dictionary
        from core.utils.type_guards import normalize_mixed_type_field
        
        normalized_data = normalize_mixed_type_field(self.progress_data)
        if not normalized_data:
            self.progress_data = {}
        else:
            self.progress_data = normalized_data
        
        # Base fields for all content types
        if 'first_viewed_at' not in self.progress_data:
            self.progress_data['first_viewed_at'] = timestamp_iso
            
        if 'last_updated_at' not in self.progress_data:
            self.progress_data['last_updated_at'] = timestamp_iso
            
        # Video-specific defaults
        if self.topic.content_type in ['Video', 'EmbedVideo']:
            if 'progress' not in self.progress_data:
                self.progress_data['progress'] = 0
                
            if 'view_count' not in self.progress_data:
                self.progress_data['view_count'] = 1
                
            if 'last_position' not in self.progress_data:
                self.progress_data['last_position'] = 0
                
            if 'duration' not in self.progress_data:
                # Will be updated by player, but set a default
                self.progress_data['duration'] = 0
                
            if 'total_viewing_time' not in self.progress_data:
                self.progress_data['total_viewing_time'] = 0
                
            if 'viewing_sessions' not in self.progress_data:
                self.progress_data['viewing_sessions'] = []
        
        # Audio-specific defaults
        elif self.topic.content_type == 'Audio':
            if 'progress' not in self.progress_data:
                self.progress_data['progress'] = 0
                
            if 'last_position' not in self.progress_data:
                self.progress_data['last_position'] = 0
        
        # SCORM-specific defaults
        elif self.topic.content_type == 'SCORM':
            if 'status' not in self.progress_data:
                self.progress_data['status'] = 'not_attempted'
                
        # Discussion-specific defaults
        elif self.topic.content_type == 'Discussion':
            if 'view_count' not in self.progress_data:
                self.progress_data['view_count'] = 1
                
            if 'comment_count' not in self.progress_data:
                self.progress_data['comment_count'] = 0
        
        self.save(update_fields=['progress_data'])
        return self.progress_data

    def update_progress(self, progress_data):
        """Update progress with new data"""
        from core.utils.type_guards import normalize_mixed_type_field, validate_progress_data
        
        normalized_data = normalize_mixed_type_field(progress_data)
        if normalized_data:
            # Ensure progress_data is initialized
            self.init_progress_data()
            
            # Validate and update progress data
            validated_data = validate_progress_data(normalized_data)
            if validated_data:
                self.progress_data.update(validated_data)
            else:
                # Fallback to raw data if validation fails
                self.progress_data.update(normalized_data)
            
            # Check for completion status
            if progress_data.get('status') == 'completed':
                self.completed = True
                self.completed_at = timezone.now()
                
            # Update time spent if provided
            if 'time_spent' in progress_data:
                self.total_time_spent += progress_data['time_spent']
                
            self.save()

    def update_from_scorm(self, registration):
        """Update progress based on SCORM Cloud registration data"""
        # Ensure progress_data is initialized as a dictionary
        if not isinstance(self.progress_data, dict):
            self.progress_data = {}
            
        # Increment attempts counter
        self.attempts += 1
        
        # Update score tracking
        if registration.score is not None:
            self.last_score = registration.score
            if self.best_score is None or registration.score > self.best_score:
                self.best_score = registration.score
        
        # Update completion data
        if not self.completion_data:
            self.completion_data = {}
            
        self.completion_data.update({
            'last_attempt': {
                'date': timezone.now().isoformat(),
                'score': float(self.last_score) if self.last_score else None,
                'status': registration.completion_status,
                'time_spent': registration.total_time
            },
            'total_attempts': self.attempts,
            'best_score': float(self.best_score) if self.best_score else None,
        })
        
        # Update progress data
        self.progress_data.update({
            'status': registration.completion_status,
            'score': float(registration.score) if registration.score else None,
            'total_time': self.total_time_spent + registration.total_time,
            'last_updated': timezone.now().isoformat()
        })
        
        # Check completion requirements
        if registration.completion_status in ['completed', 'passed']:
            scorm_content = self.topic.get_scorm_content()
            if scorm_content:
                if not scorm_content.requires_passing_score or (
                    registration.score and registration.score >= scorm_content.passing_score
                ):
                    self.mark_complete('scorm')
                    return  # mark_complete already calls save()
                    
        # Save if mark_complete wasn't called
        self.save()

    def mark_complete(self, method='auto'):
        """Mark topic as complete with the specified method"""
        from django.utils import timezone
        current_time = timezone.now()
        
        self.completed = True
        self.completion_method = method
        self.manually_completed = (method == 'manual')
        
        if not self.completed_at:
            self.completed_at = current_time
            
        # Ensure completion_data is initialized
        if not self.completion_data:
            self.completion_data = {}
            
        # Update completion data
        self.completion_data.update({
            'completed_at': current_time.isoformat(),
            'completion_method': method,
            'manually_completed': self.manually_completed,
            'total_attempts': self.attempts,
            'total_time': self.total_time_spent
        })
        
        # For video content, ensure progress is set to 100%
        if hasattr(self, 'topic') and self.topic and self.topic.content_type in ['Video', 'EmbedVideo']:
            if not self.progress_data:
                self.progress_data = {}
            self.progress_data['progress'] = 100.0
            self.progress_data['completed'] = True
            self.progress_data['completed_at'] = current_time.isoformat()
        
        self.save()
        
        # Check if course is now complete
        self._check_course_completion()
        
    def mark_video_progress(self, current_time, duration, progress):
        """
        Mark video progress and automatically complete if threshold reached
        This provides a consistent way to handle video progress for all topics
        """
        from django.utils import timezone
        
        # Get current timestamp
        timestamp = timezone.now()
        timestamp_iso = timestamp.isoformat()
        
        # Initialize progress_data with consistent defaults
        self.init_progress_data()
        
        # Calculate time watched since last update
        time_watched = 0
        last_position = self.progress_data.get('last_position', 0)
        
        # If current_time is greater than last_position, user is progressing
        if current_time > last_position:
            time_watched = current_time - last_position
            
            # Add to total viewing time (protect against unrealistic values)
            if time_watched > 0 and time_watched < 3600:  # Limit to 1 hour max per update
                total_time = self.progress_data.get('total_viewing_time', 0) + time_watched
                self.progress_data['total_viewing_time'] = total_time
        
        # Track viewing sessions
        viewing_sessions = self.progress_data.get('viewing_sessions', [])
        
        # Check if this is a new session (more than 30 minutes since last update)
        is_new_session = True
        if 'last_updated_at' in self.progress_data:
            try:
                from datetime import datetime
                last_updated = datetime.fromisoformat(self.progress_data['last_updated_at'].replace('Z', '+00:00'))
                time_diff = (timestamp - last_updated).total_seconds()
                is_new_session = time_diff > 1800  # 30 minutes
            except (ValueError, TypeError):
                is_new_session = True
        
        # If new session, increment view count and add to session history
        if is_new_session:
            self.progress_data['view_count'] = self.progress_data.get('view_count', 0) + 1
            
            # Add new session to the list (limit to last 10 sessions)
            new_session = {
                'started_at': timestamp_iso,
                'position': current_time,
                'progress': progress
            }
            viewing_sessions.append(new_session)
            
            # Keep only the last 10 sessions
            if len(viewing_sessions) > 10:
                viewing_sessions = viewing_sessions[-10:]
            
            self.progress_data['viewing_sessions'] = viewing_sessions
        # Otherwise update the latest session
        elif viewing_sessions:
            viewing_sessions[-1]['updated_at'] = timestamp_iso
            viewing_sessions[-1]['position'] = current_time
            viewing_sessions[-1]['progress'] = progress
            self.progress_data['viewing_sessions'] = viewing_sessions
        
        # Ensure progress is a valid number
        if progress is None or not isinstance(progress, (int, float)) or progress < 0:
            # If duration is valid, calculate progress as percentage of video watched
            if duration and duration > 0 and isinstance(duration, (int, float)) and duration > 0:
                progress = min(100, round((current_time / duration) * 100))
            else:
                progress = 0
                
        # Ensure progress is a float or int, not a string or other type
        try:
            progress = float(progress)
        except (ValueError, TypeError):
            progress = 0
        
        # Update progress data
        self.progress_data.update({
            'last_position': current_time,
            'duration': duration,
            'progress': min(100, progress),
            'last_updated_at': timestamp_iso
        })
        
        # Update bookmark
        if not self.bookmark:
            self.bookmark = {}
            
        self.bookmark.update({
            'position': current_time,
            'updated_at': timestamp_iso
        })
        
        # Mark as completed if progress is at least 95%
        if not self.completed and progress >= 95:
            self.mark_complete('auto')
        else:
            self.save()
            
        return self.completed

    def _check_course_completion(self):
        """Check if all topics in course are completed"""
        # Get courses related to this topic through the CourseTopic relationship
        courses = Course.objects.filter(coursetopic__topic=self.topic)
        
        for course in courses:
            # Check if course has custom completion requirements
            custom_requirements = CourseCompletionRequirement.objects.filter(course=course)
            
            if custom_requirements.exists():
                # Handle custom completion requirements
                all_requirements_met = True
                for requirement in custom_requirements:
                    if not requirement.is_met_by_user(self.user):
                        all_requirements_met = False
                        logger.info(f"Custom requirement not met: {requirement.topic.title} requires {requirement.required_score}% score")
                        break
                
                if not all_requirements_met:
                    logger.info(f"Not all custom requirements met for course '{course.title}' by user {self.user.username}")
                    continue
                    
                logger.info(f"All custom requirements met for course '{course.title}' by user {self.user.username}")
                # Will continue to mark course as completed below
            else:
                # Use standard completion logic
                total_topics = course.topics.count()
                
                if total_topics == 0:
                    continue  # Skip if course has no topics
                    
                completed_topics = TopicProgress.objects.filter(
                    user=self.user,
                    topic__coursetopic__course=course,
                    completed=True
                ).count()
                
                # Calculate completion percentage based on course settings
                completion_threshold = course.completion_percentage if hasattr(course, 'completion_percentage') else 100
                completion_rate = round((completed_topics / total_topics) * 100) if total_topics > 0 else 0
                
                # Log the completion progress for debugging
                logger.info(f"Course completion check: User {self.user.username}, Course '{course.title}'")
                logger.info(f"Completed topics: {completed_topics}/{total_topics}, Rate: {completion_rate:.1f}%, Threshold: {completion_threshold}%")
                
                # Check if completion threshold is met
                if completion_rate < completion_threshold:
                    logger.info(f"Course completion threshold not met: {completion_rate}% < {completion_threshold}%")
                    continue  # Not completed yet
                
                logger.info(f"Course completion threshold met: {completion_rate}% >= {completion_threshold}%")
            
            # At this point, either custom requirements are met or standard completion is achieved
            # Look up enrollment record
            enrollment = CourseEnrollment.objects.filter(
                user=self.user,
                course=course
            ).first()
            
            if enrollment:
                # Only update enrollment status if not already completed
                if not enrollment.completed:
                    logger.info(f"Marking course '{course.title}' as completed for user {self.user.username}")
                    enrollment.completed = True
                    enrollment.completion_date = timezone.now()
                    enrollment.save()
                
                # Auto-generate certificate if enabled for this course
                if course.issue_certificate and course.certificate_template:
                    try:
                        from certificates.models import IssuedCertificate
                        import uuid
                        
                        # Check if certificate already exists for this user and course
                        existing_cert = IssuedCertificate.objects.filter(
                            recipient=self.user,
                            course_name=course.title
                        ).first()
                        
                        if not existing_cert:
                            # Generate unique certificate number
                            certificate_number = f"CERT-{uuid.uuid4().hex[:8].upper()}"
                            
                            # Get course instructor or superuser as issuer
                            issuer = course.instructor
                            if not issuer:
                                from django.contrib.auth import get_user_model
                                User = get_user_model()
                                issuer = User.objects.filter(is_superuser=True).first()
                            
                            if not issuer:
                                logger.warning(f"No issuer found for certificate generation for course '{course.title}'")
                                issuer = self.user  # Fallback to user themselves
                            
                            # Create certificate
                            certificate = IssuedCertificate.objects.create(
                                template=course.certificate_template,
                                recipient=self.user,
                                issued_by=issuer,
                                course_name=course.title,
                                certificate_number=certificate_number,
                                # Optional: can also add grade if available
                            )
                            
                            logger.info(f"Auto-generated certificate {certificate.certificate_number} for {self.user.username} for course '{course.title}'")
                        else:
                            logger.info(f"Certificate already exists for {self.user.username} for course '{course.title}': {existing_cert.certificate_number}")
                    except Exception as e:
                        logger.error(f"Error generating certificate for {self.user.username} in course '{course.title}': {str(e)}")
                elif course.issue_certificate and not course.certificate_template:
                    logger.warning(f"Certificate generation enabled for course '{course.title}' but no certificate template is set")
            else:
                logger.warning(f"User {self.user.username} completed all topics in course '{course.title}' but no enrollment record found")

    def get_progress_percentage(self):
        """Calculate overall progress percentage"""
        if self.completed:
            return 100
        if 'progress' in self.progress_data:
            return min(int(self.progress_data['progress']), 99)
        return 0

    def get_status_display(self):
        """Get user-friendly status display"""
        if self.completed:
            return 'Completed'
        if self.attempts > 0:
            return 'In Progress'
        return 'Not Started'

    def update_scorm_progress(self, registration_report):
        """Update progress based on SCORM Cloud registration report"""
        if not registration_report:
            logger.warning(f"Empty registration report for topic {self.topic.id}, user {self.user.username}")
            return

        try:
            logger.info(f"Updating SCORM progress for topic {self.topic.id}, user {self.user.username}")
            
            # Ensure progress_data is initialized as a dictionary
            if not isinstance(self.progress_data, dict):
                self.progress_data = {}
                
            # Make sure we have required fields initialized
            from django.utils import timezone
            if 'first_viewed_at' not in self.progress_data:
                self.progress_data['first_viewed_at'] = timezone.now().isoformat()
            
            # Always update last_updated_at 
            self.progress_data['last_updated_at'] = timezone.now().isoformat()
                
            # Process the registrationCompletion status field - handle case variations
            completion_status = None
            if 'registrationCompletion' in registration_report:
                completion_status = registration_report.get('registrationCompletion', '').lower()
                logger.info(f"Found registrationCompletion status: {completion_status}")
            elif 'completion' in registration_report:
                completion_status = registration_report.get('completion', '').lower()
                logger.info(f"Found completion status: {completion_status}")
            elif 'completionStatus' in registration_report:
                completion_status = registration_report.get('completionStatus', '').lower()
                logger.info(f"Found completionStatus: {completion_status}")
                
            # Process the success status field
            success_status = None
            if 'registrationSuccess' in registration_report:
                success_status = registration_report.get('registrationSuccess', '').lower()
                logger.info(f"Found registrationSuccess: {success_status}")
            elif 'success' in registration_report:
                success_status = registration_report.get('success', '').lower()
                logger.info(f"Found success status: {success_status}")
            elif 'successStatus' in registration_report:
                success_status = registration_report.get('successStatus', '').lower()
                logger.info(f"Found successStatus: {success_status}")
                
            # Set default values if we couldn't find them
            if not completion_status:
                completion_status = 'incomplete'
                logger.info(f"No completion status found, using default: incomplete")
            if not success_status:
                success_status = 'unknown'
                logger.info(f"No success status found, using default: unknown")
            
            # Normalize status values for consistency
            if completion_status == 'complete':
                completion_status = 'completed'
                logger.info(f"Normalized 'complete' to 'completed'")
                
            # Handle score using unified scoring service
            normalized_score = None
            if 'score' in registration_report:
                from core.utils.scoring import ScoreCalculationService
                
                score_data = registration_report.get('score', {})
                normalized_score = ScoreCalculationService.handle_scorm_score(score_data)
                
                if normalized_score is not None:
                    self.last_score = normalized_score
                    if self.best_score is None or normalized_score > self.best_score:
                        self.best_score = normalized_score
                    logger.info(f"Updated score: {normalized_score}")
            
            # Calculate completion percentage
            completion_percent = 0
            objectives = registration_report.get('objectives', [])
            
            if objectives and len(objectives) > 0:
                completed_objectives = sum(1 for obj_data in objectives if obj_data.get('success') == 'PASSED')
                if len(objectives) > 0:
                    completion_percent = round((completed_objectives / len(objectives)) * 100)
                    logger.info(f"Calculated completion percentage from objectives: {completion_percent}% ({completed_objectives}/{len(objectives)} objectives completed)")
            elif completion_status in ['completed', 'passed'] or success_status == 'passed':
                completion_percent = 100
                logger.info(f"Setting completion percentage to 100% based on completion/success status")
            
            # Save progress data with standardized field names for consistency
            self.progress_data.update({
                'status': completion_status,
                'completion_status': completion_status,
                'success_status': success_status,
                'completion_percent': completion_percent,
                'score': float(normalized_score) if normalized_score is not None else None,
                'total_time': registration_report.get('totalSecondsTracked', 0),
                'last_updated': timezone.now().isoformat(),
                'scorm_cloud_sync': True
            })
            logger.info(f"Updated progress_data with completion status: {completion_status}, success status: {success_status}, progress: {completion_percent}%")
            
            # Update completion data
            if not self.completion_data:
                self.completion_data = {}
                
            self.completion_data.update({
                'last_attempt': {
                    'date': timezone.now().isoformat(),
                    'score': float(self.last_score) if self.last_score else None,
                    'status': completion_status,
                    'success': success_status
                },
                'total_attempts': self.attempts,
                'best_score': float(self.best_score) if self.best_score else None,
                'completion_method': self.completion_method
            })
            logger.info(f"Updated completion_data")

            # Capture runtime data for bookmark
            runtime_data = registration_report.get('runtime', {})
            if runtime_data and not self.bookmark:
                self.bookmark = {}
                
            if runtime_data:
                self.bookmark.update({
                    'suspendData': runtime_data.get('suspendData'),
                    'lessonLocation': runtime_data.get('lessonLocation'),
                    'lessonStatus': runtime_data.get('completionStatus'),
                    'entry': runtime_data.get('entry'),
                    'updated_at': timezone.now().isoformat()
                })
                logger.info(f"Updated bookmark data with runtime info")

            # Mark as completed if appropriate
            if completion_status in ['completed', 'passed'] or success_status == 'passed':
                logger.info(f"Completion/success status indicates completion, marking as completed")
                self.completed = True
                self.completion_method = 'scorm'
                if not self.completed_at:
                    self.completed_at = timezone.now()
                    logger.info(f"Set completed_at to {self.completed_at}")

            # Final confirmation of completion status before saving
            logger.info(f"Final completion status before saving: {self.completed}")
            self.save()
            logger.info(f"Saved progress record")
            
            # Check course completion after updating SCORM progress
            if self.completed:
                logger.info(f"Topic completed, checking course completion")
                self._check_course_completion()
                
        except Exception as e:
            logger.error(f"Error updating SCORM progress: {str(e)}")
            logger.exception("Exception details:")

    def update_audio_progress(self, current_time, duration):
        """Update audio progress and handle completion"""
        if duration > 0:
            self.last_audio_position = current_time
            self.audio_progress = round((current_time / duration) * 100)
            
            # If 95% or more of the audio has been listened to
            if self.audio_progress >= 95:
                self.mark_complete('auto')  # Use mark_complete to properly handle completion
            else:
                self.completed = False  # Reset completion if progress drops below 95%
                
            self.save()
            
            # Check course completion after updating progress
            self._check_course_completion()

class CourseTopic(models.Model):
    """Through model for Course-Topic relationship"""
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE)
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['order', 'created_at']
        unique_together = ['course', 'topic']
        
    def __str__(self):
        return f"{self.course.title} - {self.topic.title}"

# DISABLED - Using direct upload system instead of signals
# @receiver(post_save, sender=Topic)
# def handle_scorm_content(sender, instance, created, **kwargs):
#     """
#     DISABLED - Direct upload system handles SCORM content creation
#     """
#     return  # Signal disabled - using direct upload in views
    
#     # Import required models and utilities
#     from django.core.cache import cache
#     from scorm_cloud.models import SCORMCloudContent, SCORMPackage
    
#     # Use a more robust lock key with file hash to prevent duplicates
#     import hashlib
#     try:
#         # Create a unique identifier based on topic and file
#         # For S3 storage, use the file name instead of path
#         if instance.content_file:
#             try:
#                 # Try to get path for local storage
#                 file_path = instance.content_file.path
#             except (ValueError, NotImplementedError):
#                 # For S3 storage, use the file name
#                 file_path = instance.content_file.name
#         else:
#             file_path = 'no_file'
#         
#         # Safely get file size without raising FileNotFoundError
#         try:
#             file_size = instance.content_file.size if instance.content_file and hasattr(instance.content_file, 'size') else 0
#         except (FileNotFoundError, OSError, ValueError):
#             # File doesn't exist on disk or other file access error
#             file_size = 0
#         
#         unique_key = f"{instance.id}_{file_size}_{instance.title}"
#         lock_key = f"scorm_upload_lock_{hashlib.md5(unique_key.encode()).hexdigest()}"
#         
#         # Use database-level check first (more reliable than cache)
#         existing_content = SCORMCloudContent.objects.filter(
#             content_type='topic',
#             content_id=str(instance.id)
#         ).first()
#         
#         if existing_content and existing_content.package:
#             logger.info(f"Found existing SCORM content for topic {instance.id}, skipping upload")
#             return
#             
#         # Try to acquire cache lock with shorter timeout to reduce blocking
#         lock_acquired = cache.add(lock_key, 1, timeout=60)  # 1 minute timeout
#         
#         if not lock_acquired:
#             logger.info(f"Skipping duplicate upload for topic {instance.id} - already being processed")
#             return
#             
#         try:
#             # Double-check after acquiring lock (race condition protection)
#             existing_content = SCORMCloudContent.objects.filter(
#                 content_type='topic',
#                 content_id=str(instance.id)
#             ).first()
#             
#             if existing_content and existing_content.package:
#                 logger.info(f"Found existing SCORM content for topic {instance.id} after lock, skipping upload")
#                 return
#             
#             # Check if the file exists
#             # For S3 storage, we can't use os.path.exists with .path
#             # Instead, check if the file has a URL (which means it exists)
#             if not hasattr(instance.content_file, 'url'):
#                 logger.error(f"SCORM file does not exist: {instance.content_file.name}")
#                 return
#                 
#             # Use the async uploader and return early
#             try:
#                 from scorm_cloud.utils.async_uploader import enqueue_upload
#                 
#                 # Queue the upload task with unique identifier and user context
#                 # Try to get user from course/branch context for branch-specific SCORM
#                 user = None
#                 try:
#                     logger.info(f"🏭 courses/models.py: Determining user context for topic {instance.id}")
#                     
#                     # First try to get user from the stored context
#                     if hasattr(instance, '_creation_user') and instance._creation_user:
#                         user = instance._creation_user
#                         logger.info(f"🏭 courses/models.py: Using stored creation user: {user.username}")
#                     else:
#                         # Fallback to course lookup
#                         from courses.views import get_topic_course
#                         topic_course = get_topic_course(instance)
#                         logger.info(f"🏭 courses/models.py: get_topic_course result: {topic_course.title if topic_course else None}")
#                         
#                         if topic_course and hasattr(topic_course, 'created_by'):
#                             logger.info(f"🏭 courses/models.py: Using course.created_by")
#                             user = topic_course.created_by
#                         elif topic_course and topic_course.branch:
#                             logger.info(f"🏭 courses/models.py: Looking for branch admin in {topic_course.branch.name}")
#                             # Get a branch admin user for branch-specific SCORM
#                             from django.contrib.auth import get_user_model
#                             User = get_user_model()
#                             user = User.objects.filter(
#                                 branch=topic_course.branch,
#                                 role='admin'
#                             ).first()
#                             logger.info(f"🏭 courses/models.py: Branch admin found: {user.username if user else None}")
#                             
#                             # If no branch admin, try to get any admin user
#                             if not user:
#                                 user = User.objects.filter(role='admin').first()
#                                 logger.info(f"🏭 courses/models.py: Fallback admin found: {user.username if user else None}")
#                         else:
#                             logger.info(f"🏭 courses/models.py: No course or no branch")
#                             
#                 except Exception as e:
#                     logger.error(f"🏭 courses/models.py: Error determining user context: {str(e)}")
#                     import traceback
#                     logger.error(f"🏭 courses/models.py: Full traceback: {traceback.format_exc()}")
#                 
#                 logger.info(f"🏭 courses/models.py: Final user for enqueue_upload: {user.username if user else None}")
#                 
#                 # For SCORM topics with content files, we need to upload to SCORM Cloud
#                 # This handles the case where topics are created with SCORM files
#                 if instance.content_file:
#                     try:
#                         # Get the file path for upload (handle cloud storage properly)
#                         upload_file_path = None
#                         
#                         # Use local storage for SCORM files - no need for cloud storage handling
#                         upload_file_path = instance.content_file.path
#                         logger.info(f"Using local SCORM file path: {upload_file_path}")
#                         
#                         if not upload_file_path:
#                             logger.error("Could not determine file path for SCORM upload")
#                             raise Exception("Could not determine file path for SCORM upload")
#                         
#                         logger.info(f"Uploading SCORM file for topic {instance.id}: {upload_file_path}")
#                         
#                         # Enqueue the upload
#                         enqueue_upload(
#                             file_path=upload_file_path,
#                             topic_id=instance.id,
#                             title=instance.title,
#                             user=user
#                         )
#                         
#                         logger.info(f"Queued SCORM upload for topic {instance.id}")
#                         return
#                         
#                     except Exception as upload_error:
#                         logger.error(f"Error queuing SCORM upload for topic {instance.id}: {str(upload_error)}")
#                         logger.exception("Full upload error traceback:")
#                         
#                         # Upload failed, log error and return
#                         logger.error(f"SCORM upload failed for topic {instance.id}")
#                         return
#                 else:
#                     logger.info(f"SCORM topic {instance.id} has no content file - skipping upload")
#                     return
#                 
#                 logger.error(f"No file path available for SCORM upload of topic {instance.id}")
#                 
#                 logger.info(f"Queued SCORM upload for topic {instance.id}")
#                 return
#                 
#             except ImportError:
#                 logger.warning("Async uploader not available, skipping upload for now")
#                 return
#                 
#         finally:
#             # Release the lock
#             try:
#                 cache.delete(lock_key)
#             except Exception as cache_error:
#                 logger.warning(f"Error releasing cache lock for topic {instance.id}: {str(cache_error)}")
#                 
#     except Exception as e:
#         logger.error(f"Error processing SCORM content for topic {instance.id}: {str(e)}")
#         # Make sure to release lock on error
#         try:
#                 cache.delete(lock_key)
#         except:
#             pass

class LearningObjective(models.Model):
    """Model for course learning objectives"""
    course = models.ForeignKey(
        'Course',
        on_delete=models.CASCADE,
        related_name='learning_objectives'
    )
    description = models.TextField()
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order', 'created_at']

    def __str__(self):
        return f"{self.course.title} - Objective {self.order}"

class CourseFeature(models.Model):
    """Model for course features"""
    course = models.ForeignKey(
        'Course',
        on_delete=models.CASCADE,
        related_name='features'
    )
    description = models.TextField()
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order', 'created_at']

    def __str__(self):
        return f"{self.course.title} - Feature {self.order}"

class Discussion(models.Model):
    """Model for topic discussions"""
    topic = models.OneToOneField(Topic, on_delete=models.CASCADE, related_name='topic_discussion')
    title = models.CharField(max_length=200)
    content = models.TextField()
    created_by = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    likes = models.ManyToManyField(CustomUser, related_name='liked_topic_discussions', blank=True)

    def __str__(self):
        return f"Discussion for {self.topic.title}"

class Comment(models.Model):
    """Model for discussion comments"""
    discussion = models.ForeignKey(Discussion, on_delete=models.CASCADE, related_name='comments')
    content = models.TextField()
    created_by = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='replies')
    likes = models.ManyToManyField(CustomUser, related_name='liked_topic_comments', blank=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Comment by {self.created_by.username} on {self.discussion.title}"

class Attachment(models.Model):
    """Model for discussion attachments"""
    discussion = models.ForeignKey(Discussion, on_delete=models.CASCADE, related_name='attachments', null=True, blank=True)
    comment = models.ForeignKey(Comment, on_delete=models.CASCADE, related_name='attachments', null=True, blank=True)
    file = models.FileField(upload_to='discussion_attachments/')
    file_type = models.CharField(max_length=10, choices=[
        ('image', 'Image'),
        ('video', 'Video'),
        ('document', 'Document')
    ])
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Attachment for {self.discussion.title if self.discussion else self.comment.discussion.title}"

# Add a signal to enforce branch assignment for paid courses
@receiver(models.signals.pre_save, sender=Course)
def ensure_paid_course_has_branch(sender, instance, **kwargs):
    """Ensure that paid courses always have a branch assigned (except for super admin created courses)"""
    if (instance.price and instance.price > 0 and not instance.branch and 
        not (hasattr(instance, '_created_by_superadmin') and instance._created_by_superadmin)):
        # Try to assign to the first branch if available
        default_branch = Branch.objects.first()
        if default_branch:
            instance.branch = default_branch
            logger.info(f"Auto-assigned paid course '{instance.title}' to default branch '{default_branch.name}'")
        else:
            logger.warning(f"Cannot auto-assign branch to paid course '{instance.title}' - no branches available")




class CourseCompletionRequirement(models.Model):
    """Model for storing custom course completion requirements"""
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='completion_requirements'
    )
    topic = models.ForeignKey(
        Topic,
        on_delete=models.CASCADE,
        related_name='required_for_completion'
    )
    required_score = models.IntegerField(
        default=0,
        help_text="Minimum score required for this topic (0-100). 0 means just completion is required."
    )
    is_mandatory = models.BooleanField(
        default=True,
        help_text="Whether this topic must be completed for course completion"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['course', 'topic']
        ordering = ['topic__order']

    def __str__(self):
        return f"{self.course.title} - {self.topic.title} (Required: {self.required_score}%)"

    def is_met_by_user(self, user):
        """Check if this requirement is met by the given user"""
        progress = TopicProgress.objects.filter(
            user=user,
            topic=self.topic
        ).first()
        
        if not progress:
            return False
            
        # Check if topic is completed
        if not progress.completed:
            return False
            
        # If required score is 0, just completion is enough
        if self.required_score == 0:
            return True
            
        # Check if the user's score meets the requirement
        if progress.last_score is not None:
            return progress.last_score >= self.required_score
            
        return False