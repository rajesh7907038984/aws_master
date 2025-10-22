from django.db import models
from django.utils.text import slugify
from django.core.exceptions import ValidationError
from courses.models import Course
from users.models import CustomUser
from django.utils import timezone
from django.conf import settings


def validate_description(value):
    """Ensure the description is complete and not too short"""
    if len(value.strip()) < 3:  # Minimum 3 characters
        raise ValidationError('Description must be at least 3 characters')
    if value.strip() in ['k', 'N/A', 'test']:  # Check for obviously incomplete descriptions
        raise ValidationError('Please provide a complete description')


def rubric_feedback_file_path(instance, filename):
    """Define path for rubric feedback files with secure filename handling"""
    import os
    from django.utils.text import slugify
    
    # Create a safe filename
    name, ext = os.path.splitext(filename)
    safe_name = slugify(name)[:50] + ext
    
    # Determine the path based on the type of evaluation
    if instance.submission:
        # For assignment submissions
        return f"rubric_feedback/assignments/{instance.submission.assignment.id}/{instance.submission.user.id}/{safe_name}"
    elif instance.discussion:
        # For discussion evaluations
        return f"rubric_feedback/discussions/{instance.discussion.id}/{instance.student.id}/{safe_name}"
    elif instance.conference:
        # For conference evaluations
        return f"rubric_feedback/conferences/{instance.conference.id}/{instance.student.id}/{safe_name}"
    elif instance.quiz_attempt:
        # For quiz evaluations
        return f"rubric_feedback/quizzes/{instance.quiz_attempt.quiz.id}/{instance.student.id}/{safe_name}"
    else:
        # Fallback
        return f"rubric_feedback/general/{safe_name}"


class Rubric(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    total_points = models.FloatField(default=0)
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='rubrics', null=True, blank=True)
    created_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, related_name='created_rubrics')
    branch = models.ForeignKey(
        'branches.Branch',
        on_delete=models.CASCADE,
        related_name='rubrics',
        null=True,
        blank=True,
        help_text="The branch this rubric belongs to"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        app_label = 'lms_rubrics'
    
    def __str__(self):
        return self.title
    
    def save(self, *args, **kwargs):
        # Auto-set branch from course or created_by if not set
        if not self.branch:
            if self.course and self.course.branch:
                self.branch = self.course.branch
            elif self.created_by and self.created_by.branch:
                self.branch = self.created_by.branch
        
        # Only recalculate total points if the instance has already been saved (has pk)
        if self.pk:
            # Calculate total points using criterion.points (user's custom values)
            self.total_points = sum(criterion.points for criterion in self.criteria.all())
        super().save(*args, **kwargs)


class RubricCriterion(models.Model):
    rubric = models.ForeignKey(Rubric, on_delete=models.CASCADE, related_name='criteria')
    description = models.TextField(validators=[validate_description])
    points = models.FloatField(default=0)
    position = models.PositiveIntegerField(default=0)
    use_range = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['position']
        app_label = 'lms_rubrics'
    
    def __str__(self):
        return f"{self.rubric.title} - {self.description[:30]}"
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Update the total points in the parent rubric
        self.rubric.save()
    
    def clean(self):
        """Validate criterion data"""
        if self.points < 0:
            raise ValidationError({'points': 'Points cannot be negative'})
        super().clean()


class RubricRating(models.Model):
    criterion = models.ForeignKey(RubricCriterion, on_delete=models.CASCADE, related_name='ratings')
    title = models.CharField(max_length=255, default='Rating')
    description = models.TextField(validators=[validate_description])
    points = models.FloatField()
    position = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['position']
        app_label = 'lms_rubrics'
    
    def __str__(self):
        return f"{self.criterion.description[:20]} - {self.title} - {self.description[:20]}"
    
    def clean(self):
        """Validate rating data"""
        if self.points < 0:
            raise ValidationError({'points': 'Points cannot be negative'})
        if self.points > self.criterion.points:
            raise ValidationError({'points': f'Points cannot exceed criterion maximum of {self.criterion.points}'})
        super().clean()
    
    def save(self, *args, **kwargs):
        # Run validation before saving
        self.full_clean()
        super().save(*args, **kwargs)
        # Update the parent criterion's rubric to recalculate points
        self.criterion.rubric.save()


class RubricEvaluation(models.Model):
    """Model for storing how a submission was evaluated against rubric criteria"""
    submission = models.ForeignKey('assignments.AssignmentSubmission', on_delete=models.CASCADE, related_name='rubric_evaluations', null=True, blank=True)
    discussion = models.ForeignKey('discussions.Discussion', on_delete=models.CASCADE, related_name='rubric_evaluations', null=True, blank=True)
    criterion = models.ForeignKey(RubricCriterion, on_delete=models.CASCADE, related_name='evaluations')
    rating = models.ForeignKey(RubricRating, on_delete=models.SET_NULL, null=True, blank=True, related_name='evaluations')
    points = models.FloatField(default=0)
    comments = models.TextField(blank=True)
    evaluated_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, related_name='rubric_evaluations')
    student = models.ForeignKey(CustomUser, on_delete=models.CASCADE, null=True, blank=True, related_name='received_evaluations')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        app_label = 'lms_rubrics'
        unique_together = [
            ['submission', 'criterion'],
            ['discussion', 'criterion', 'student'],
        ]
        ordering = ['criterion__position']
    
    def __str__(self):
        if self.submission:
            return f"Evaluation for {self.submission} - {self.criterion}"
        else:
            return f"Evaluation for {self.discussion} - {self.criterion}"
        
    def clean(self):
        """Validate evaluation data"""
        if self.points < 0:
            raise ValidationError({'points': 'Points cannot be negative'})
        if self.points > self.criterion.points:
            raise ValidationError({'points': f'Points cannot exceed criterion maximum of {self.criterion.points}'})
        # Ensure either submission or discussion is set, but not both
        if (self.submission and self.discussion) or (not self.submission and not self.discussion):
            raise ValidationError('Either submission or discussion must be set, but not both')
        super().clean()
        
    def save(self, *args, **kwargs):
        # Ensure points don't exceed criterion maximum
        if self.points > self.criterion.points:
            self.points = self.criterion.points
        
        # Check if this is an update to create history
        is_update = self.pk is not None
        if is_update:
            # Get the old instance to compare
            try:
                old_instance = RubricEvaluation.objects.get(pk=self.pk)
                # Check if values have changed
                if (old_instance.points != self.points or 
                    old_instance.rating_id != self.rating_id or 
                    old_instance.comments != self.comments):
                    
                    # Mark all existing history records as not current
                    RubricEvaluationHistory.objects.filter(
                        submission=self.submission,
                        discussion=self.discussion,
                        criterion=self.criterion,
                        student=self.student,
                        is_current=True
                    ).update(is_current=False)
                    
                    # Get the latest version number for this evaluation
                    latest_version = RubricEvaluationHistory.objects.filter(
                        submission=self.submission,
                        discussion=self.discussion,
                        criterion=self.criterion,
                        student=self.student
                    ).aggregate(max_version=models.Max('version'))['max_version'] or 0
                    
                    # Create history record for the OLD values
                    RubricEvaluationHistory.objects.create(
                        submission=old_instance.submission,
                        discussion=old_instance.discussion,
                        criterion=old_instance.criterion,
                        rating=old_instance.rating,
                        points=old_instance.points,
                        comments=old_instance.comments,
                        evaluated_by=old_instance.evaluated_by,
                        student=old_instance.student,
                        version=latest_version + 1,
                        evaluation_date=old_instance.updated_at,
                        is_current=False
                    )
                    
                    # Create history record for the NEW values (current)
                    RubricEvaluationHistory.objects.create(
                        submission=self.submission,
                        discussion=self.discussion,
                        criterion=self.criterion,
                        rating=self.rating,
                        points=self.points,
                        comments=self.comments,
                        evaluated_by=self.evaluated_by,
                        student=self.student,
                        version=latest_version + 2,
                        evaluation_date=timezone.now(),
                        is_current=True
                    )
            except RubricEvaluation.DoesNotExist:
                pass
        
        super().save(*args, **kwargs)
        
        # After saving, create a history record for the current state (only for new evaluations)
        if not is_update:  # This is a new evaluation
            RubricEvaluationHistory.objects.create(
                submission=self.submission,
                discussion=self.discussion,
                criterion=self.criterion,
                rating=self.rating,
                points=self.points,
                comments=self.comments,
                evaluated_by=self.evaluated_by,
                student=self.student,
                version=1,
                evaluation_date=timezone.now(),
                is_current=True
            )


class RubricEvaluationHistory(models.Model):
    """Model for tracking historical rubric evaluations (audit log)"""
    submission = models.ForeignKey('assignments.AssignmentSubmission', on_delete=models.CASCADE, related_name='rubric_evaluation_history', null=True, blank=True)
    discussion = models.ForeignKey('discussions.Discussion', on_delete=models.CASCADE, related_name='rubric_evaluation_history', null=True, blank=True)
    criterion = models.ForeignKey(RubricCriterion, on_delete=models.CASCADE, related_name='evaluation_history')
    rating = models.ForeignKey(RubricRating, on_delete=models.SET_NULL, null=True, blank=True, related_name='evaluation_history')
    points = models.FloatField(default=0)
    comments = models.TextField(blank=True)
    evaluated_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, related_name='rubric_evaluation_history')
    student = models.ForeignKey(CustomUser, on_delete=models.CASCADE, null=True, blank=True, related_name='received_evaluation_history')
    
    # History-specific fields
    version = models.PositiveIntegerField(default=1, help_text="Version number of this evaluation")
    evaluation_date = models.DateTimeField(help_text="When this evaluation was made")
    is_current = models.BooleanField(default=False, help_text="Whether this is the current evaluation")
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        app_label = 'lms_rubrics'
        ordering = ['criterion__position', '-version']
        indexes = [
            models.Index(fields=['submission', 'criterion', '-version']),
            models.Index(fields=['discussion', 'criterion', 'student', '-version']),
        ]
    
    def __str__(self):
        if self.submission:
            return f"History v{self.version} for {self.submission} - {self.criterion}"
        else:
            return f"History v{self.version} for {self.discussion} - {self.criterion} - {self.student}" 


class RubricOverallFeedback(models.Model):
    """Model for overall instructor feedback on rubric evaluations"""
    
    # Relationship to the specific evaluation context
    submission = models.ForeignKey(
        'assignments.AssignmentSubmission',
        on_delete=models.CASCADE,
        related_name='rubric_overall_feedback',
        null=True,
        blank=True,
        help_text="Related assignment submission if applicable"
    )
    discussion = models.ForeignKey(
        'discussions.Discussion',
        on_delete=models.CASCADE,
        related_name='rubric_overall_feedback',
        null=True,
        blank=True,
        help_text="Related discussion if applicable"
    )
    conference = models.ForeignKey(
        'conferences.Conference',
        on_delete=models.CASCADE,
        related_name='rubric_overall_feedback',
        null=True,
        blank=True,
        help_text="Related conference if applicable"
    )
    quiz_attempt = models.ForeignKey(
        'quiz.QuizAttempt',
        on_delete=models.CASCADE,
        related_name='rubric_overall_feedback',
        null=True,
        blank=True,
        help_text="Related quiz attempt if applicable"
    )
    
    # The student who is receiving the feedback
    student = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='received_rubric_feedback',
        help_text="The student who is receiving this feedback"
    )
    
    # The rubric being evaluated
    rubric = models.ForeignKey(
        'lms_rubrics.Rubric',
        on_delete=models.CASCADE,
        related_name='overall_feedback',
        help_text="The rubric this feedback is for"
    )
    
    # Feedback content
    feedback = models.TextField(
        blank=True,
        help_text="Text feedback from instructor about the overall rubric evaluation"
    )
    audio_feedback = models.FileField(
        upload_to=rubric_feedback_file_path,
        null=True,
        blank=True,
        help_text="Audio feedback file (mp3, wav, m4a, etc.)"
    )
    video_feedback = models.FileField(
        upload_to=rubric_feedback_file_path,
        null=True,
        blank=True,
        help_text="Video feedback file (mp4, mov, avi, etc.)"
    )
    
    # Metadata
    created_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        related_name='given_rubric_feedback',
        help_text="The instructor who created this feedback"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Privacy setting
    is_private = models.BooleanField(
        default=False,
        help_text="Whether feedback is visible to the student or only to instructors"
    )
    
    class Meta:
        app_label = 'lms_rubrics'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['submission', 'student']),
            models.Index(fields=['discussion', 'student']),
            models.Index(fields=['conference', 'student']),
            models.Index(fields=['quiz_attempt', 'student']),
            models.Index(fields=['rubric', 'student']),
            models.Index(fields=['created_by', '-created_at']),
        ]
        # Ensure only one feedback per student per rubric evaluation context
        unique_together = [
            ['submission', 'student'],
            ['discussion', 'student'],
            ['conference', 'student'],
            ['quiz_attempt', 'student'],
        ]
    
    def __str__(self):
        context = ""
        if self.submission:
            context = f"Assignment: {self.submission.assignment.title}"
        elif self.discussion:
            context = f"Discussion: {self.discussion.title}"
        elif self.conference:
            context = f"Conference: {self.conference.title}"
        elif self.quiz_attempt:
            context = f"Quiz: {self.quiz_attempt.quiz.title}"
        
        return f"Overall Feedback - {context} - {self.student.get_full_name()}"
    
    def clean(self):
        """Validate that exactly one context is set"""
        context_count = sum([
            bool(self.submission),
            bool(self.discussion),
            bool(self.conference),
            bool(self.quiz_attempt)
        ])
        
        if context_count != 1:
            raise ValidationError(
                "Exactly one context (submission, discussion, conference, or quiz_attempt) must be set"
            )
        
        # Ensure at least one type of feedback is provided
        if not any([self.feedback, self.audio_feedback, self.video_feedback]):
            raise ValidationError(
                "At least one type of feedback (text, audio, or video) must be provided"
            )
        
        super().clean()
    
    def save(self, *args, **kwargs):
        # Run validation
        self.full_clean()
        super().save(*args, **kwargs)
    
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
    
    def get_context_type(self):
        """Return the type of context this feedback is for"""
        if self.submission:
            return 'assignment'
        elif self.discussion:
            return 'discussion'
        elif self.conference:
            return 'conference'
        elif self.quiz_attempt:
            return 'quiz'
        return 'unknown'
    
    def get_context_object(self):
        """Return the actual context object"""
        if self.submission:
            return self.submission
        elif self.discussion:
            return self.discussion
        elif self.conference:
            return self.conference
        elif self.quiz_attempt:
            return self.quiz_attempt
        return None 