from django.db import models
from django.conf import settings
from django.utils import timezone
from courses.models import Course, Topic
from users.models import CustomUser
from django.core.exceptions import ValidationError
from core.utils.fields import TinyMCEField
import os
from pathlib import Path
import re
from lms_rubrics.models import Rubric
from django.db.models.signals import post_save
from django.dispatch import receiver

def secure_filename(filename):
    """
    Secure filename by removing potentially dangerous characters
    and limiting length while preserving extension
    """
    # Get the file extension
    ext = Path(filename).suffix
    name = Path(filename).stem
    
    # Remove any non-alphanumeric characters except dashes and underscores
    name = re.sub(r'[^\w\-]', '_', name)
    
    # Limit length while preserving extension
    max_length = 500
    if len(name) + len(ext) > max_length:
        name = name[:max_length - len(ext)]
    
    return f"{name}{ext}"

def assignment_file_path(instance, filename):
    """Define path for assignment files with secure filename handling"""
    safe_name = secure_filename(filename)
    if hasattr(instance, 'assignment'):
        return f"assignment_content/submissions/{instance.assignment.id}/{instance.user.id}/{safe_name}"
    return f"assignment_content/assignments/{safe_name}"

class Assignment(models.Model):
    """Model for assignments"""
    title = models.CharField(max_length=800)
    description = TinyMCEField(help_text="Description of the assignment")
    points = models.IntegerField(default=10000)  # Default 100.00 * 100
    instructions = TinyMCEField(
        help_text="Detailed instructions for completing the assignment",
        null=True
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_assignments',
        help_text="User who created this assignment"
    )
    due_date = models.DateTimeField(null=True, blank=True)
    attachment = models.FileField(
        upload_to=assignment_file_path,
        max_length=500,
        null=True,
        blank=True,
        help_text="Supporting documents for the assignment (Use AssignmentAttachment for new documents)"
    )
    content_type = models.CharField(
        max_length=800,
        null=True,
        blank=True,
        help_text="MIME type of the attachment"
    )
    max_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=100.00
    )
    submission_type = models.CharField(
        max_length=20,
        choices=[
            ('file', 'File Upload Only'),
            ('text', 'Text/Quiz Response Only'),
            ('both', 'Both File Upload and Text/Quiz Response')
        ],
        default='file'
    )
    allowed_file_types = models.CharField(
        max_length=800,
        default='.pdf,.doc,.docx,.txt,.ppt,.pptx,.mp4,.mov,.avi,.wmv',
        help_text="Comma-separated list of allowed file extensions"
    )
    max_file_size = models.IntegerField(
        default=629145600,  # 600MB
        help_text="Maximum file size in bytes"
    )
    rubric = models.ForeignKey(
        'lms_rubrics.Rubric',
        on_delete=models.SET_NULL,
        related_name='rubric_assignments',  # Fixed Bug #7: More specific related_name
        null=True,
        blank=True,
        help_text="Rubric used for grading this assignment"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # Fixed Bug #1: Removed single course ForeignKey, use only ManyToMany relationship
    # Use many-to-many relationship with Course through AssignmentCourse
    courses = models.ManyToManyField(
        'courses.Course',
        through='AssignmentCourse',
        related_name='course_assignments',
        blank=True
    )
    # Add many-to-many relationship with Topic through TopicAssignment
    topics = models.ManyToManyField(
        'courses.Topic',
        through='TopicAssignment',
        related_name='topic_assignments',
        blank=True
    )

    class Meta:
        app_label = 'assignments'
        ordering = ['-created_at']
        indexes = [
            # Bug #1 fix: Removed index on 'course' field (now accessed via M2M relationship)
            models.Index(fields=['-created_at']),
        ]

    def __str__(self):
        return self.title

    @property
    def course(self):
        """
        Get primary course for backward compatibility (Bug #1 fix).
        Returns the course marked as primary in AssignmentCourse, or first course if none is primary.
        """
        primary_ac = self.assignmentcourse_set.filter(is_primary=True).first()
        if primary_ac:
            return primary_ac.course
        # Fallback to first course if no primary is set
        return self.courses.first()
    
    @property
    def all_courses(self):
        """Get all courses this assignment belongs to"""
        return self.courses.all()

    @property
    def is_overdue(self):
        """Check if assignment is overdue"""
        if not self.due_date:
            return False
        return timezone.now() > self.due_date

    @property
    def due_soon(self):
        """Check if assignment is due soon (within 24 hours)"""
        if not self.due_date:
            return False
        return timezone.now() + timezone.timedelta(hours=24) > self.due_date > timezone.now()

    def get_course_info(self):
        """
        Get course information for this assignment.
        Bug #1 fix: Now uses M2M courses relationship (via @property) and topic relationships.
        """
        # Check M2M course relationship (primary course via @property)
        if self.course:
            return self.course
        
        # If no M2M course, check through topics
        # Get the first topic that this assignment is associated with
        topic = self.topics.first()
        if topic:
            # Get the first course that this topic is associated with
            course = topic.courses.first()
            if course:
                return course
        
        # Return None if no course relationship found
        return None

    def is_available_for_user(self, user):
        """Check if assignment is available for the user to access - RESTRICTED TO LEARNERS ONLY"""
        # ROLE RESTRICTION: Only learner role users can access assignments for submission
        if user.role != 'learner':
            return False
            
        # For learner role, only allow access to active assignments
        if user.role == 'learner':
            # Assignment must be active for learners
            if not self.is_active:
                return False
                
            # Check if this assignment has topics
            has_topics = self.topics.exists()
            
            # If assignment has topics, they must be active/published
            # If assignment has no topics, it's a direct course assignment (allowed)
            if has_topics and not self.topics.filter(status='active').exists():
                return False  # Has topics but none are published
            
            # Check if user is enrolled in any courses linked to this assignment
            # Assignment can be linked to courses through direct, M2M, or topic relationships
            from courses.models import Course, CourseEnrollment
            
            # Get all courses that the user is enrolled in
            enrolled_course_ids = CourseEnrollment.objects.filter(user=user).values_list('course_id', flat=True)
            
            # Check if assignment is linked to any enrolled courses through any relationship
            linked_to_enrolled_course = (
                # Direct course relationship
                (self.course and self.course.id in enrolled_course_ids) or
                # M2M course relationship
                self.courses.filter(id__in=enrolled_course_ids).exists() or
                # Topic-based course relationship
                Course.objects.filter(
                    id__in=enrolled_course_ids,
                    coursetopic__topic__topicassignment__assignment=self
                ).exists()
            )
            
            return linked_to_enrolled_course
        
        return False
    
    def delete(self, *args, **kwargs):
        """
        Override delete to clean up S3 files when assignment is deleted.
        This ensures all assignment files, submissions, and attachments are properly removed.
        """
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            logger.info(f"Starting deletion for Assignment: {self.title} (ID: {self.id})")
            
            # Delete the attachment file if it exists
            if self.attachment:
                try:
                    self.attachment.delete(save=False)
                    logger.info(f"Deleted assignment attachment file")
                except Exception as e:
                    logger.error(f"Error deleting assignment attachment: {str(e)}")
            
            # S3 cleanup for assignment files and submissions
            try:
                from core.utils.s3_cleanup import cleanup_assignment_s3_files
                s3_results = cleanup_assignment_s3_files(self.id)
                successful_s3_deletions = sum(1 for success in s3_results.values() if success)
                total_s3_files = len(s3_results)
                if total_s3_files > 0:
                    logger.info(f"S3 cleanup: {successful_s3_deletions}/{total_s3_files} files deleted successfully")
            except Exception as e:
                logger.error(f"Error during S3 cleanup for assignment {self.id}: {str(e)}")
            
            logger.info(f"Successfully completed deletion for Assignment: {self.title} (ID: {self.id})")
            
        except Exception as e:
            logger.error(f"Error in Assignment.delete(): {str(e)}")
        
        # Call the parent delete method
        super().delete(*args, **kwargs)

class TopicAssignment(models.Model):
    """Through model for Topic-Assignment relationship"""
    topic = models.ForeignKey('courses.Topic', on_delete=models.CASCADE)
    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE)
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = 'assignments'
        ordering = ['order', 'created_at']
        unique_together = ['topic', 'assignment']

    def __str__(self):
        return f"{self.topic.title} - {self.assignment.title}"

class AssignmentSubmission(models.Model):
    """Model for student assignment submissions"""
    assignment = models.ForeignKey(
        Assignment,
        on_delete=models.CASCADE,
        related_name='submissions',
        null=True,
        blank=True
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='assignment_submissions',
        null=True,
        blank=True
    )
    submission_file = models.FileField(
        upload_to=assignment_file_path,
        max_length=500,
        null=True,
        blank=True
    )
    submission_text = models.TextField(
        blank=True,
        help_text="Text submission or comments"
    )
    submitted_at = models.DateTimeField(auto_now_add=True)
    last_modified = models.DateTimeField(auto_now=True)
    status = models.CharField(
        max_length=20,
        choices=[
            ('draft', 'Draft'),
            ('submitted', 'Submitted'),
            ('not_graded', 'Not Graded'),
            ('graded', 'Graded'),
            ('returned', 'Returned for Revision'),
            ('late', 'Late'),
            ('missing', 'Missing'),
            ('excused', 'Excused')
        ],
        default='not_graded'
    )
    grade = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True
    )
    graded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='graded_submissions'
    )
    graded_at = models.DateTimeField(null=True, blank=True)
    
    # Admin approval fields for detailed reports
    admin_approval_status = models.CharField(
        max_length=20,
        choices=[
            ('approved', 'Approved'),
            ('needs_revision', 'Needs Revision'),
            ('rejected', 'Rejected')
        ],
        null=True,
        blank=True,
        help_text="Admin approval status for the assignment report"
    )
    admin_approval_feedback = models.TextField(
        null=True,
        blank=True,
        help_text="Internal verifier feedback on the assignment report"
    )
    admin_approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='admin_approved_submissions'
    )
    admin_approval_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the admin approval was given"
    )

    class Meta:
        unique_together = ['assignment', 'user']
        ordering = ['-submitted_at']

    def __str__(self):
        return f"{self.user.username if self.user else 'Unknown'}'s submission for {self.assignment.title if self.assignment else 'Unknown Assignment'}"

    def clean(self):
        if not self.submission_file and not self.submission_text:
            raise ValidationError("Either file or text submission is required")

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        old_submission_file = None
        
        if self.pk:  # If this is an update
            try:
                old_instance = AssignmentSubmission.objects.get(pk=self.pk)
                old_submission_file = old_instance.submission_file
                if (old_instance.grade != self.grade or old_instance.status != self.status):
                    GradeHistory.objects.create(
                        submission=self,
                        previous_grade=old_instance.grade,
                        new_grade=self.grade,
                        previous_status=old_instance.status,
                        new_status=self.status,
                        changed_by=self.graded_by,
                        comment=f"Grade changed from {old_instance.grade} to {self.grade}"
                    )
            except AssignmentSubmission.DoesNotExist:
                pass
        
        super().save(*args, **kwargs)
        
        # Register assignment submission file with storage tracking
        if self.submission_file and (is_new or (old_submission_file != self.submission_file)):
            try:
                from core.utils.storage_manager import StorageManager
                from django.core.files.storage import default_storage
                import logging
                logger = logging.getLogger(__name__)
                
                # Get file size
                file_size = self.submission_file.size if hasattr(self.submission_file, 'size') else 0
                
                # If file_size is 0, try to get it from storage
                if file_size == 0:
                    try:
                        file_size = default_storage.size(self.submission_file.name)
                    except Exception:
                        file_size = 0
                
                if file_size > 0 and self.user and self.user.branch:
                    StorageManager.register_file_upload(
                        user=self.user,
                        file_path=self.submission_file.name,
                        original_filename=self.submission_file.name.split('/')[-1],
                        file_size_bytes=file_size,
                        content_type=self.content_type or 'application/octet-stream',
                        source_app='assignments',
                        source_model='AssignmentSubmission',
                        source_object_id=self.id
                    )
                    logger.info(f"Registered assignment submission upload for user {self.user.username}: {file_size} bytes")
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Error registering assignment submission upload: {str(e)}")

    def can_be_edited_by_student(self):
        """
        Check if this submission can be edited by the student.
        Students can only edit submissions that are:
        - In draft status, or
        - Returned for revision
        """
        return self.status in ['draft', 'returned']
    
    def is_final_submission(self):
        """
        Check if this is a final submission (submitted, graded, etc.)
        Students cannot edit final submissions.
        """
        return self.status in ['submitted', 'not_graded', 'graded', 'late', 'missing', 'excused']
    
    def get_submission_attempt_number(self, user=None):
        """
        Get the attempt number for this submission.
        """
        if not user:
            user = self.user
        
        # Get all submissions by this user for this assignment, ordered by submission date
        all_submissions = AssignmentSubmission.objects.filter(
            assignment=self.assignment,
            user=user
        ).order_by('submitted_at')
        
        # Find the position of this submission
        for index, submission in enumerate(all_submissions, 1):
            if submission.id == self.id:
                return index
        return 1  # Default to 1 if not found

class AssignmentFeedback(models.Model):
    """Model for instructor feedback on assignments"""
    submission = models.ForeignKey(
        AssignmentSubmission,
        on_delete=models.CASCADE,
        related_name='feedback_entries',
        null=True,
        blank=True
    )
    feedback = models.TextField(blank=True, help_text="Text feedback from instructor")
    audio_feedback = models.FileField(
        upload_to=assignment_file_path,
        max_length=500,
        null=True,
        blank=True,
        help_text="Audio feedback file (mp3, wav, m4a, etc.)"
    )
    video_feedback = models.FileField(
        upload_to=assignment_file_path,
        max_length=500,
        null=True,
        blank=True,
        help_text="Video feedback file (mp4, mov, avi, etc.)"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='given_feedback'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    is_private = models.BooleanField(
        default=False,
        help_text="Whether feedback is visible to the student or only to instructors"
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Feedback on {self.submission}"
    
    def has_multimedia_feedback(self):
        """Check if this feedback entry has audio or video files"""
        return bool(self.audio_feedback or self.video_feedback)
    
    def get_feedback_types(self):
        """Return a list of feedback types present"""
        types = []
        if self.feedback:
            types.append('text')
        if self.audio_feedback:
            types.append('audio')
        if self.video_feedback:
            types.append('video')
        return types
    
    def delete(self, *args, **kwargs):
        """
        Override delete to clean up audio/video feedback files when deleted.
        """
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            # Delete audio feedback file if it exists
            if self.audio_feedback:
                try:
                    self.audio_feedback.delete(save=False)
                    logger.info(f"Deleted audio feedback file for feedback {self.id}")
                except Exception as e:
                    logger.error(f"Error deleting audio feedback file: {str(e)}")
            
            # Delete video feedback file if it exists
            if self.video_feedback:
                try:
                    self.video_feedback.delete(save=False)
                    logger.info(f"Deleted video feedback file for feedback {self.id}")
                except Exception as e:
                    logger.error(f"Error deleting video feedback file: {str(e)}")
                    
        except Exception as e:
            logger.error(f"Error in AssignmentFeedback.delete(): {str(e)}")
        
        # Call the parent delete method
        super().delete(*args, **kwargs)

class TextQuestion(models.Model):
    """Model for text-based questions in assignments"""
    assignment = models.ForeignKey(
        Assignment,
        on_delete=models.CASCADE,
        related_name='text_questions',
        null=True,
        blank=True
    )
    question_text = models.TextField(
        help_text="The text of the question"
    )
    question_html = models.TextField(
        blank=True,
        null=True,
        help_text="The HTML version of the question text"
    )
    order = models.PositiveIntegerField(
        default=0,
        help_text="Display order of the question"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order', 'created_at']
        indexes = [
            models.Index(fields=['assignment', 'order']),
        ]

    def __str__(self):
        return f"Question {self.order}: {self.question_text[:50]}..."

class TextQuestionAnswer(models.Model):
    """Model for student answers to text questions"""
    question = models.ForeignKey(
        TextQuestion,
        on_delete=models.CASCADE,
        related_name='answers'
    )
    submission = models.ForeignKey(
        AssignmentSubmission,
        on_delete=models.CASCADE,
        related_name='text_answers'
    )
    answer_text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['question__order']
        unique_together = ['question', 'submission']

    def __str__(self):
        return f"Answer to {self.question}"

class TextQuestionAnswerIteration(models.Model):
    """Model for iterative text question answers - supports multiple rounds of feedback"""
    question = models.ForeignKey(
        TextQuestion,
        on_delete=models.CASCADE,
        related_name='answer_iterations'
    )
    submission = models.ForeignKey(
        AssignmentSubmission,
        on_delete=models.CASCADE,
        related_name='text_answer_iterations'
    )
    iteration_number = models.PositiveIntegerField(
        default=1,
        help_text="Iteration number for this response (1, 2, 3, etc.)"
    )
    answer_text = models.TextField(
        help_text="The learner's response text"
    )
    is_submitted = models.BooleanField(
        default=False,
        help_text="Whether this iteration has been submitted by the learner"
    )
    submitted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this iteration was submitted"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['question__order', 'iteration_number']
        unique_together = ['question', 'submission', 'iteration_number']
        indexes = [
            models.Index(fields=['question', 'submission', 'iteration_number']),
            models.Index(fields=['question', 'submission', '-iteration_number']),
        ]

    def __str__(self):
        return f"Iteration {self.iteration_number} for {self.question}"

    def get_next_iteration_number(self):
        """Get the next iteration number for this question/submission pair"""
        last_iteration = TextQuestionAnswerIteration.objects.filter(
            question=self.question,
            submission=self.submission
        ).order_by('-iteration_number').first()
        
        if last_iteration:
            return last_iteration.iteration_number + 1
        return 1

    def can_submit_new_iteration(self):
        """Check if learner can submit a new iteration based on latest feedback"""
        latest_feedback = self.feedback_entries.first()
        if not latest_feedback:
            return True
        return latest_feedback.allows_new_iteration


class TextQuestionIterationFeedback(models.Model):
    """Model for instructor feedback on individual text question answer iterations"""
    iteration = models.ForeignKey(
        TextQuestionAnswerIteration,
        on_delete=models.CASCADE,
        related_name='feedback_entries'
    )
    feedback_text = models.TextField(
        help_text="Instructor feedback for this specific iteration"
    )
    allows_new_iteration = models.BooleanField(
        default=True,
        help_text="Whether this feedback allows the learner to submit a new iteration"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='given_question_iteration_feedback'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['iteration', '-created_at']),
        ]

    def __str__(self):
        return f"Feedback on {self.iteration}"

class TextSubmissionField(models.Model):
    """Model for configurable text submission fields in assignments"""
    assignment = models.ForeignKey(
        Assignment,
        on_delete=models.CASCADE,
        related_name='text_fields'
    )
    label = models.CharField(
        max_length=800,
        help_text="Label for the text field"
    )
    placeholder = models.CharField(
        max_length=800,
        blank=True,
        help_text="Placeholder text for the field"
    )
    order = models.PositiveIntegerField(
        default=0,
        help_text="Display order of the field"
    )
    content = models.JSONField(
        null=True,
        blank=True,
        help_text="JSON content for the editor field - includes delta and HTML"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order', 'created_at']
        indexes = [
            models.Index(fields=['assignment', 'order']),
        ]

    def __str__(self):
        return f"{self.label} ({self.assignment.title})"

class TextSubmissionAnswer(models.Model):
    """Model for student answers to text submission fields"""
    field = models.ForeignKey(
        TextSubmissionField,
        on_delete=models.CASCADE,
        related_name='answers'
    )
    submission = models.ForeignKey(
        AssignmentSubmission,
        on_delete=models.CASCADE,
        related_name='field_answers'
    )
    answer_text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['field__order']
        unique_together = ['field', 'submission']

    def __str__(self):
        return f"Answer to {self.field.label}"

class TextSubmissionAnswerIteration(models.Model):
    """Model for iterative text submission field answers - supports multiple rounds of feedback"""
    field = models.ForeignKey(
        TextSubmissionField,
        on_delete=models.CASCADE,
        related_name='answer_iterations'
    )
    submission = models.ForeignKey(
        AssignmentSubmission,
        on_delete=models.CASCADE,
        related_name='field_answer_iterations'
    )
    iteration_number = models.PositiveIntegerField(
        default=1,
        help_text="Iteration number for this response (1, 2, 3, etc.)"
    )
    answer_text = models.TextField(
        help_text="The learner's response text"
    )
    is_submitted = models.BooleanField(
        default=False,
        help_text="Whether this iteration has been submitted by the learner"
    )
    submitted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this iteration was submitted"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['field__order', 'iteration_number']
        unique_together = ['field', 'submission', 'iteration_number']
        indexes = [
            models.Index(fields=['field', 'submission', 'iteration_number']),
            models.Index(fields=['field', 'submission', '-iteration_number']),
        ]

    def __str__(self):
        return f"Iteration {self.iteration_number} for {self.field.label}"

    def get_next_iteration_number(self):
        """Get the next iteration number for this field/submission pair"""
        last_iteration = TextSubmissionAnswerIteration.objects.filter(
            field=self.field,
            submission=self.submission
        ).order_by('-iteration_number').first()
        
        if last_iteration:
            return last_iteration.iteration_number + 1
        return 1

    def can_submit_new_iteration(self):
        """Check if learner can submit a new iteration based on latest feedback"""
        latest_feedback = self.feedback_entries.first()
        if not latest_feedback:
            return True
        return latest_feedback.allows_new_iteration


class TextSubmissionIterationFeedback(models.Model):
    """Model for instructor feedback on individual text submission field iterations"""
    iteration = models.ForeignKey(
        TextSubmissionAnswerIteration,
        on_delete=models.CASCADE,
        related_name='feedback_entries'
    )
    feedback_text = models.TextField(
        help_text="Instructor feedback for this specific iteration"
    )
    allows_new_iteration = models.BooleanField(
        default=True,
        help_text="Whether this feedback allows the learner to submit a new iteration"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='given_field_iteration_feedback'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['iteration', '-created_at']),
        ]

    def __str__(self):
        return f"Feedback on {self.iteration}"

class FileSubmissionIteration(models.Model):
    """Model for iterative file submissions - supports multiple rounds of file uploads and feedback"""
    submission = models.ForeignKey(
        AssignmentSubmission,
        on_delete=models.CASCADE,
        related_name='file_iterations'
    )
    iteration_number = models.PositiveIntegerField(
        default=1,
        help_text="Iteration number for this file upload (1, 2, 3, etc.)"
    )
    file = models.FileField(
        upload_to=assignment_file_path,
        max_length=500,
        help_text="The uploaded file for this iteration"
    )
    file_name = models.CharField(
        max_length=800,
        blank=True,
        null=True,
        help_text="Original filename"
    )
    file_size = models.PositiveBigIntegerField(
        blank=True,
        null=True,
        help_text="File size in bytes"
    )
    content_type = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        help_text="MIME type of the file"
    )
    description = models.TextField(
        blank=True,
        help_text="Optional description or notes about this file version"
    )
    is_submitted = models.BooleanField(
        default=False,
        help_text="Whether this iteration has been submitted by the learner"
    )
    submitted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this iteration was submitted"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['iteration_number']
        unique_together = ['submission', 'iteration_number']
        indexes = [
            models.Index(fields=['submission', 'iteration_number']),
            models.Index(fields=['submission', '-iteration_number']),
        ]

    def __str__(self):
        return f"File iteration {self.iteration_number} for {self.submission}"

    def get_next_iteration_number(self):
        """Get the next iteration number for this submission"""
        last_iteration = FileSubmissionIteration.objects.filter(
            submission=self.submission
        ).order_by('-iteration_number').first()
        
        if last_iteration:
            return last_iteration.iteration_number + 1
        return 1

    def can_submit_new_iteration(self):
        """Check if a new file iteration can be submitted"""
        # Check if there's any feedback that allows new iterations
        latest_feedback = self.feedback_entries.order_by('-created_at').first()
        if latest_feedback:
            return latest_feedback.allows_new_iteration
        return True  # If no feedback yet, allow new iterations

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        old_file = None
        
        if self.pk:
            try:
                old_instance = FileSubmissionIteration.objects.get(pk=self.pk)
                old_file = old_instance.file
            except FileSubmissionIteration.DoesNotExist:
                pass
        
        if self.file and not self.file_name:
            try:
                self.file_name = self.file.name
            except Exception as e:
                import logging
                logger = logging.getLogger('assignments')
                logger.warning(f"Error accessing file name: {e}")
                self.file_name = "unknown_file"
        if self.file and not self.file_size:
            # Safely get file size without raising FileNotFoundError
            try:
                file_name = self.file.name  # Get name safely first
                if hasattr(self.file, 'size') and file_name:
                    self.file_size = self.file.size
                else:
                    self.file_size = 0
            except (FileNotFoundError, OSError, ValueError, Exception):
                # File doesn't exist on disk or other file access error
                self.file_size = 0
        if self.file and not self.content_type:
            try:
                import mimetypes
                content_type, encoding = mimetypes.guess_type(self.file.name)
                self.content_type = content_type or 'application/octet-stream'
            except Exception as e:
                import logging
                logger = logging.getLogger('assignments')
                logger.warning(f"Error accessing file name for content type: {e}")
                self.content_type = 'application/octet-stream'
        
        super().save(*args, **kwargs)
        
        # Register file iteration upload with storage tracking
        if self.file and (is_new or (old_file != self.file)):
            try:
                from core.utils.storage_manager import StorageManager
                from django.core.files.storage import default_storage
                import logging
                logger = logging.getLogger(__name__)
                
                # Get file size
                file_size = self.file_size or 0
                
                # If file_size is 0, try to get it from storage
                if file_size == 0 and hasattr(self.file, 'size'):
                    file_size = self.file.size
                
                if file_size == 0:
                    try:
                        file_size = default_storage.size(self.file.name)
                    except Exception:
                        file_size = 0
                
                if file_size > 0 and self.submission and self.submission.user and self.submission.user.branch:
                    StorageManager.register_file_upload(
                        user=self.submission.user,
                        file_path=self.file.name,
                        original_filename=self.file_name or self.file.name.split('/')[-1],
                        file_size_bytes=file_size,
                        content_type=self.content_type or 'application/octet-stream',
                        source_app='assignments',
                        source_model='FileSubmissionIteration',
                        source_object_id=self.id
                    )
                    logger.info(f"Registered file iteration upload for user {self.submission.user.username}: {file_size} bytes")
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Error registering file iteration upload: {str(e)}")
    
    def delete(self, *args, **kwargs):
        """
        Override delete to clean up the uploaded file when iteration is deleted.
        """
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            # Delete the file if it exists
            if self.file:
                try:
                    self.file.delete(save=False)
                    logger.info(f"Deleted file for iteration {self.iteration_number} of submission {self.submission_id}")
                except Exception as e:
                    logger.error(f"Error deleting file iteration file: {str(e)}")
                    
        except Exception as e:
            logger.error(f"Error in FileSubmissionIteration.delete(): {str(e)}")
        
        # Call the parent delete method
        super().delete(*args, **kwargs)

class FileSubmissionIterationFeedback(models.Model):
    """Model for instructor feedback on individual file submission iterations"""
    iteration = models.ForeignKey(
        FileSubmissionIteration,
        on_delete=models.CASCADE,
        related_name='feedback_entries'
    )
    feedback_text = models.TextField(
        help_text="Instructor feedback for this file iteration"
    )
    allows_new_iteration = models.BooleanField(
        default=True,
        help_text="Whether this feedback allows the learner to submit a new file"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='given_file_iteration_feedback'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['iteration', '-created_at']),
        ]

    def __str__(self):
        return f"Feedback on {self.iteration}"

class AssignmentAttachment(models.Model):
    """Model for managing multiple attachments for assignments"""
    assignment = models.ForeignKey(
        Assignment,
        on_delete=models.CASCADE,
        related_name='attachments'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assignment_attachments'
    )
    file = models.FileField(
        upload_to=assignment_file_path,
        max_length=500,
        help_text="Supporting document for the assignment"
    )
    file_name = models.CharField(
        max_length=800, 
        blank=True
    )
    content_type = models.CharField(
        max_length=800,
        null=True,
        blank=True,
        help_text="MIME type of the attachment"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        
    def __str__(self):
        return f"Attachment for {self.assignment.title}"
    
    def save(self, *args, **kwargs):
        if self.file and not self.file_name:
            try:
                self.file_name = self.file.name
            except Exception as e:
                import logging
                logger = logging.getLogger('assignments')
                logger.warning(f"Error accessing file name: {e}")
                self.file_name = "unknown_file"
        if self.file and not self.content_type:
            try:
                import mimetypes
                content_type, encoding = mimetypes.guess_type(self.file.name)
                self.content_type = content_type or 'application/octet-stream'
            except Exception as e:
                import logging
                logger = logging.getLogger('assignments')
                logger.warning(f"Error accessing file name for content type: {e}")
                self.content_type = 'application/octet-stream'
        super().save(*args, **kwargs)
    
    def delete(self, *args, **kwargs):
        """
        Override delete to clean up the attachment file when deleted.
        """
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            # Delete the file if it exists
            if self.file:
                try:
                    self.file.delete(save=False)
                    logger.info(f"Deleted attachment file for assignment {self.assignment_id}")
                except Exception as e:
                    logger.error(f"Error deleting assignment attachment file: {str(e)}")
                    
        except Exception as e:
            logger.error(f"Error in AssignmentAttachment.delete(): {str(e)}")
        
        # Call the parent delete method
        super().delete(*args, **kwargs)

class SupportingDocQuestion(models.Model):
    """Model for questions and answers in the Supporting Documents section"""
    assignment = models.ForeignKey(
        Assignment,
        on_delete=models.CASCADE,
        related_name='supporting_doc_questions'
    )
    question = models.TextField(
        help_text="Question related to supporting documents"
    )
    answer = models.TextField(
        blank=True,
        null=True,
        help_text="Instructor reference answer to the question"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='supporting_doc_answers',
        null=True,
        blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Q: {self.question[:50]}..."

class StudentAnswer(models.Model):
    """Model for student answers to SupportingDocQuestions"""
    question = models.ForeignKey(
        SupportingDocQuestion,
        on_delete=models.CASCADE,
        related_name='student_answers'
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='question_answers'
    )
    answer = models.TextField(
        help_text="Student's answer to the question"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        unique_together = ['question', 'student']
        
    def __str__(self):
        return f"Answer by {self.student.username} to {self.question}"

@receiver(post_save, sender=AssignmentSubmission)
def create_or_update_grade(sender, instance, **kwargs):
    """
    Signal handler to automatically create or update Grade records
    when an assignment submission is graded.
    """
    # Only create Grade if the submission has been graded
    if instance.grade is not None:
        # Import here to avoid circular import
        from gradebook.models import Grade
        from django.db import transaction
        
        # Get the assignment's course
        course = None
        if instance.assignment.course:
            course = instance.assignment.course
        else:
            # Try to find course through topics
            topics = Topic.objects.filter(assignment=instance.assignment)
            if topics.exists():
                topic = topics.first()
                course_topic = topic.coursetopic_set.first()
                if course_topic:
                    course = course_topic.course
                    
                    # Update assignment's course reference for future use
                    if not instance.assignment.course:
                        instance.assignment.course = course
                        instance.assignment.save(update_fields=['course'])
        
        if course and instance.user:
            # Use a transaction to ensure atomicity
            with transaction.atomic():
                # First, check if a grade already exists
                existing_grades = Grade.objects.filter(
                    student=instance.user,
                    assignment=instance.assignment
                )
                
                if existing_grades.exists():
                    # Update the existing grade
                    grade = existing_grades.first()
                    grade.score = instance.grade
                    # Bug #3 fix: Removed grade.course (no longer a field, accessed via assignment)
                    grade.save()
                else:
                    # Create a new grade (Bug #3 fix: removed course parameter)
                    Grade.objects.create(
                        student=instance.user,
                        assignment=instance.assignment,
                        score=instance.grade
                    )

class GradeHistory(models.Model):
    """Model for tracking grade changes on assignment submissions"""
    submission = models.ForeignKey(
        AssignmentSubmission,
        on_delete=models.CASCADE,
        related_name='grade_history'
    )
    previous_grade = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True
    )
    new_grade = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True
    )
    previous_status = models.CharField(
        max_length=20,
        choices=AssignmentSubmission.status.field.choices,
        null=True,
        blank=True
    )
    new_status = models.CharField(
        max_length=20,
        choices=AssignmentSubmission.status.field.choices,
        null=True,
        blank=True
    )
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='grade_changes'
    )
    changed_at = models.DateTimeField(auto_now_add=True)
    comment = models.TextField(
        blank=True,
        help_text="Optional comment about the grade change"
    )

    class Meta:
        ordering = ['-changed_at']
        verbose_name_plural = "Grade histories"

    def __str__(self):
        return f"Grade change for {self.submission} at {self.changed_at}"

class AssignmentCourse(models.Model):
    """Model for the many-to-many relationship between Assignment and Course"""
    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE)
    course = models.ForeignKey('courses.Course', on_delete=models.CASCADE)
    is_primary = models.BooleanField(default=False, help_text="Whether this is the primary course for the assignment")
    created_at = models.DateTimeField(auto_now_add=True)  # This field tracks when the relationship was created

    class Meta:
        app_label = 'assignments'
        unique_together = ['assignment', 'course']
        ordering = ['-is_primary', 'created_at']

    def __str__(self):
        return f"{self.assignment.title} - {self.course.title}"

class AssignmentReportConfirmation(models.Model):
    """Model for tracking assignment report confirmations by branch admins."""
    assignment = models.ForeignKey(
        Assignment,
        on_delete=models.CASCADE,
        related_name='report_confirmations'
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='report_confirmations'
    )
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='confirmed_reports'
    )
    confirmed_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, help_text="Optional notes about the confirmation")
    
    class Meta:
        unique_together = ['assignment', 'student']
        ordering = ['-confirmed_at']
    
    def __str__(self):
        return f"Report confirmation for {self.student.get_full_name()} - {self.assignment.title}"


class AdminApprovalHistory(models.Model):
    """Model for tracking all admin approval decisions over time"""
    submission = models.ForeignKey(
        AssignmentSubmission,
        on_delete=models.CASCADE,
        related_name='admin_approval_history'
    )
    approval_status = models.CharField(
        max_length=20,
        choices=[
            ('approved', 'Approved'),
            ('needs_revision', 'Needs Revision'),
            ('rejected', 'Rejected')
        ],
        help_text="Admin approval status for the assignment report"
    )
    admin_feedback = models.TextField(
        null=True,
        blank=True,
        help_text="Internal verifier feedback on the assignment report"
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='admin_approval_history_entries'
    )
    approval_date = models.DateTimeField(
        auto_now_add=True,
        help_text="When the admin approval was given"
    )
    is_current = models.BooleanField(
        default=True,
        help_text="Whether this is the current/latest approval status"
    )
    
    # Track what triggered this approval (optional)
    trigger_reason = models.CharField(
        max_length=800,
        null=True,
        blank=True,
        help_text="What triggered this approval review (e.g., 'new_feedback', 'file_resubmission', 'text_revision')"
    )
    
    class Meta:
        ordering = ['-approval_date']
        verbose_name_plural = "Admin approval histories"
    
    def __str__(self):
        return f"Admin approval: {self.submission} - {self.get_approval_status_display()} ({self.approval_date})"
    
    def save(self, *args, **kwargs):
        # When saving a new approval, mark all previous approvals as not current
        if self.is_current:
            AdminApprovalHistory.objects.filter(
                submission=self.submission,
                is_current=True
            ).exclude(id=self.id).update(is_current=False)
        super().save(*args, **kwargs)

class AssignmentComment(models.Model):
    """Model for comments/conversations between learners and instructors on assignments"""
    assignment = models.ForeignKey(
        Assignment,
        on_delete=models.CASCADE,
        related_name='comments',
        help_text="The assignment this comment is related to"
    )
    submission = models.ForeignKey(
        AssignmentSubmission,
        on_delete=models.CASCADE,
        related_name='comments',
        null=True,
        blank=True,
        help_text="The specific submission this comment is related to (optional)"
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='assignment_comments',
        help_text="The user who wrote this comment"
    )
    content = models.TextField(
        help_text="The content of the comment"
    )
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='replies',
        help_text="Parent comment if this is a reply"
    )
    is_private = models.BooleanField(
        default=False,
        help_text="Whether this comment is private (instructor only)"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'assignments'
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['assignment', 'created_at']),
            models.Index(fields=['submission', 'created_at']),
            models.Index(fields=['author', 'created_at']),
        ]

    def __str__(self):
        return f"Comment by {self.author.get_full_name()} on {self.assignment.title}"

    @property
    def is_reply(self):
        """Check if this comment is a reply to another comment"""
        return self.parent is not None

    def get_replies(self):
        """Get all replies to this comment"""
        return self.replies.all().order_by('created_at')
    
    def get_visible_replies(self):
        """Get replies that have been filtered for visibility by the view"""
        # This will be set by the view after filtering
        return getattr(self, '_visible_replies', self.get_replies())

    def can_edit(self, user):
        """Check if the user can edit this comment"""
        return self.author == user or user.role in ['admin', 'superadmin'] or user.is_superuser

    def can_view(self, user):
        """Check if the user can view this comment"""
        if self.is_private and user.role == 'learner':
            return False
        return True


class AssignmentInteractionLog(models.Model):
    """Model to track all types of assignment interactions for detailed reporting"""
    INTERACTION_TYPES = [
        ('view', 'Assignment Viewed'),
        ('start_submission', 'Started Submission'),
        ('draft_save', 'Draft Saved'),
        ('file_upload', 'File Uploaded'),
        ('file_download', 'File Downloaded'),
        ('submission_edit', 'Submission Edited'),
        ('submission_submit', 'Submission Submitted'),
        ('feedback_viewed', 'Feedback Viewed'),
        ('rubric_viewed', 'Rubric Viewed'),
        ('comment_viewed', 'Comment Viewed'),
        ('assignment_edit', 'Assignment Content Edited'),
        ('page_exit', 'Page Exited'),
        ('session_timeout', 'Session Timeout'),
    ]
    
    assignment = models.ForeignKey(
        Assignment,
        on_delete=models.CASCADE,
        related_name='interaction_logs'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='assignment_interactions'
    )
    interaction_type = models.CharField(
        max_length=50,
        choices=INTERACTION_TYPES
    )
    submission = models.ForeignKey(
        AssignmentSubmission,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='interaction_logs',
        help_text="Related submission if applicable"
    )
    interaction_data = models.JSONField(
        null=True,
        blank=True,
        help_text="Additional data about the interaction (file names, duration, etc.)"
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(null=True, blank=True)
    session_key = models.CharField(max_length=40, null=True, blank=True)
    duration_seconds = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Duration of interaction in seconds (for timed interactions)"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = 'assignments'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['assignment', 'user', '-created_at']),
            models.Index(fields=['interaction_type', '-created_at']),
            models.Index(fields=['user', '-created_at']),
        ]

    def __str__(self):
        return f"{self.user.get_full_name()} - {self.get_interaction_type_display()} - {self.assignment.title}"

    @classmethod
    def log_interaction(cls, assignment, user, interaction_type, request=None, submission=None, **extra_data):
        """Helper method to easily log interactions"""
        interaction_data = extra_data
        ip_address = None
        user_agent = None
        session_key = None
        
        if request:
            ip_address = cls.get_client_ip(request)
            user_agent = request.META.get('HTTP_USER_AGENT', '')
            session_key = request.session.session_key
        
        return cls.objects.create(
            assignment=assignment,
            user=user,
            interaction_type=interaction_type,
            submission=submission,
            interaction_data=interaction_data,
            ip_address=ip_address,
            user_agent=user_agent,
            session_key=session_key
        )
    
    @staticmethod
    def get_client_ip(request):
        """Get the client's IP address from request"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class AssignmentSessionLog(models.Model):
    """Model to track assignment session durations and activities"""
    assignment = models.ForeignKey(
        Assignment,
        on_delete=models.CASCADE,
        related_name='session_logs'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='assignment_sessions'
    )
    session_key = models.CharField(max_length=40)
    start_time = models.DateTimeField(auto_now_add=True)
    last_activity = models.DateTimeField(auto_now=True)
    end_time = models.DateTimeField(null=True, blank=True)
    total_duration_seconds = models.PositiveIntegerField(default=0)
    page_views = models.PositiveIntegerField(default=0)
    interactions_count = models.PositiveIntegerField(default=0)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        app_label = 'assignments'
        ordering = ['-start_time']
        indexes = [
            models.Index(fields=['assignment', 'user', '-start_time']),
            models.Index(fields=['session_key', 'is_active']),
        ]

    def __str__(self):
        return f"{self.user.get_full_name()} - {self.assignment.title} - {self.start_time}"

    def update_activity(self):
        """Update the last activity timestamp and calculate duration"""
        from django.utils import timezone
        self.last_activity = timezone.now()
        if self.start_time:
            self.total_duration_seconds = int((self.last_activity - self.start_time).total_seconds())
        self.save(update_fields=['last_activity', 'total_duration_seconds'])

    def end_session(self):
        """Mark the session as ended"""
        from django.utils import timezone
        self.end_time = timezone.now()
        self.is_active = False
        if self.start_time:
            self.total_duration_seconds = int((self.end_time - self.start_time).total_seconds())
        self.save(update_fields=['end_time', 'is_active', 'total_duration_seconds'])

    @property
    def duration_display(self):
        """Return a human-readable duration"""
        if self.total_duration_seconds:
            hours = self.total_duration_seconds // 3600
            minutes = (self.total_duration_seconds % 3600) // 60
            seconds = self.total_duration_seconds % 60
            if hours > 0:
                return f"{hours}h {minutes}m {seconds}s"
            elif minutes > 0:
                return f"{minutes}m {seconds}s"
            else:
                return f"{seconds}s"
        return "0s"
