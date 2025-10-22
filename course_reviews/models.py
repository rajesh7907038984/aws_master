from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from courses.models import Course
from users.models import CustomUser
import json


class Survey(models.Model):
    """Survey template that can be assigned to courses"""
    title = models.CharField(max_length=255, help_text="Survey title")
    description = models.TextField(blank=True, help_text="Survey description")
    created_by = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='created_surveys',
        help_text="User who created this survey"
    )
    branch = models.ForeignKey(
        'branches.Branch',
        on_delete=models.CASCADE,
        related_name='surveys',
        null=True,
        blank=True,
        help_text="Branch this survey belongs to"
    )
    is_active = models.BooleanField(default=True, help_text="Is this survey active?")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['is_active', 'branch']),
            models.Index(fields=['created_by']),
        ]
    
    def __str__(self):
        return self.title
    
    def get_fields_count(self):
        """Get total number of fields in this survey"""
        return self.fields.count()
    
    def get_responses_count(self):
        """Get total number of responses for this survey"""
        return SurveyResponse.objects.filter(survey_field__survey=self).values('user', 'course').distinct().count()


class SurveyField(models.Model):
    """Individual fields within a survey"""
    FIELD_TYPES = [
        ('text', 'Text Input'),
        ('textarea', 'Text Area'),
        ('rating', 'Star Rating'),
        ('number', 'Number'),
        ('email', 'Email'),
    ]
    
    survey = models.ForeignKey(
        Survey,
        on_delete=models.CASCADE,
        related_name='fields',
        help_text="Survey this field belongs to"
    )
    label = models.CharField(max_length=800, help_text="Field label/question")
    field_type = models.CharField(
        max_length=20,
        choices=FIELD_TYPES,
        default='text',
        help_text="Type of input field"
    )
    is_required = models.BooleanField(default=True, help_text="Is this field required?")
    order = models.PositiveIntegerField(default=0, help_text="Display order of field")
    placeholder = models.CharField(max_length=800, blank=True, help_text="Placeholder text for input")
    help_text = models.TextField(blank=True, help_text="Help text for the field")
    
    # For rating fields
    max_rating = models.PositiveIntegerField(
        default=5,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
        help_text="Maximum rating value (for rating fields)"
    )
    
    class Meta:
        ordering = ['order', 'id']
        indexes = [
            models.Index(fields=['survey', 'order']),
        ]
    
    def __str__(self):
        return f"{self.survey.title} - {self.label}"


class SurveyResponse(models.Model):
    """Individual responses to survey fields"""
    survey_field = models.ForeignKey(
        SurveyField,
        on_delete=models.CASCADE,
        related_name='responses',
        help_text="Survey field this response is for"
    )
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='survey_responses',
        help_text="User who submitted this response"
    )
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='survey_responses',
        help_text="Course this response is related to"
    )
    
    # Response data
    text_response = models.TextField(blank=True, help_text="Text response")
    rating_response = models.PositiveIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
        help_text="Rating response (1-10)"
    )
    
    submitted_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-submitted_at']
        unique_together = ['survey_field', 'user', 'course']
        indexes = [
            models.Index(fields=['user', 'course']),
            models.Index(fields=['course', 'submitted_at']),
            models.Index(fields=['survey_field']),
        ]
    
    def __str__(self):
        return f"{self.user.username} - {self.survey_field.label} - {self.course.title}"
    
    @property
    def response_value(self):
        """Get the appropriate response value based on field type"""
        if self.survey_field.field_type == 'rating':
            return self.rating_response
        return self.text_response


class CourseReview(models.Model):
    """Aggregated course review with average rating"""
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='reviews',
        help_text="Course being reviewed"
    )
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='course_reviews',
        help_text="User who submitted the review"
    )
    survey = models.ForeignKey(
        Survey,
        on_delete=models.SET_NULL,
        null=True,
        related_name='course_reviews',
        help_text="Survey this review is based on"
    )
    
    # Aggregated rating (average of all rating fields)
    average_rating = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(10)],
        help_text="Average rating from all rating fields"
    )
    
    # Optional text review (from textarea fields)
    review_text = models.TextField(blank=True, help_text="Compiled review text")
    
    submitted_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_published = models.BooleanField(default=True, help_text="Is this review published?")
    
    class Meta:
        ordering = ['-submitted_at']
        unique_together = ['course', 'user', 'survey']
        indexes = [
            models.Index(fields=['course', 'is_published']),
            models.Index(fields=['user']),
            models.Index(fields=['average_rating']),
            models.Index(fields=['-submitted_at']),
        ]
    
    def __str__(self):
        return f"{self.user.username} - {self.course.title} - {self.average_rating}★"
    
    @classmethod
    def create_from_responses(cls, user, course, survey):
        """Create or update a CourseReview from SurveyResponses"""
        # Get all responses for this user, course, and survey
        responses = SurveyResponse.objects.filter(
            user=user,
            course=course,
            survey_field__survey=survey
        ).select_related('survey_field')
        
        if not responses.exists():
            return None
        
        # Calculate average rating from rating fields
        rating_responses = [r.rating_response for r in responses if r.rating_response is not None]
        if rating_responses:
            avg_rating = sum(rating_responses) / len(rating_responses)
        else:
            avg_rating = 0
        
        # Compile review text from textarea fields
        text_responses = [
            f"{r.survey_field.label}: {r.text_response}"
            for r in responses
            if r.text_response and r.survey_field.field_type in ['textarea', 'text']
        ]
        review_text = "\n\n".join(text_responses)
        
        # Create or update the review
        review, created = cls.objects.update_or_create(
            course=course,
            user=user,
            survey=survey,
            defaults={
                'average_rating': avg_rating,
                'review_text': review_text,
            }
        )
        
        return review
    
    def get_all_responses(self):
        """Get all survey responses related to this review"""
        return SurveyResponse.objects.filter(
            user=self.user,
            course=self.course,
            survey_field__survey=self.survey
        ).select_related('survey_field').order_by('survey_field__order')