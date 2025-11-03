from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from courses.models import Course
from assignments.models import Assignment
from decimal import Decimal


class Grade(models.Model):
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='gradebook_entries')
    # Fixed Bug #3: Removed redundant course field (access via assignment.course)
    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name='grades', db_index=True)
    submission = models.ForeignKey('assignments.AssignmentSubmission', on_delete=models.CASCADE, related_name='grade_record', null=True, blank=True)
    score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    excused = models.BooleanField(default=False)
    feedback = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['student', 'assignment']
        indexes = [
            models.Index(fields=['student', 'assignment']),
            models.Index(fields=['assignment', '-created_at']),
        ]

    def clean(self):
        """Validate the grade model"""
        super().clean()
        
        # Validate score is within reasonable bounds
        if self.score is not None:
            if self.score < 0:
                raise ValidationError({'score': 'Score cannot be negative'})
            if self.score > 9999.99:  # Based on max_digits=5, decimal_places=2
                raise ValidationError({'score': 'Score is too large'})
        
        # Validate that excused grades don't have scores
        if self.excused and self.score is not None:
            raise ValidationError({'score': 'Excused grades should not have a score'})
    
    @property
    def course(self):
        """Get course through assignment (Bug #3 fix: removed redundant course field)"""
        return self.assignment.course if self.assignment else None
    
    def __str__(self):
        course_name = self.course.title if self.course else 'Unknown Course'
        return f"{self.student.username} - {course_name} - {self.assignment.title} - {self.score if self.score else 'Excused' if self.excused else 'Not graded'}"

    def save(self, *args, **kwargs):
        # Validate before saving
        self.full_clean()
        
        # Auto-link submission if not already linked
        if not self.submission and self.assignment and self.student:
            try:
                from assignments.models import AssignmentSubmission
                submission = AssignmentSubmission.objects.filter(
                    assignment=self.assignment,
                    user=self.student
                ).first()
                if submission:
                    self.submission = submission
            except Exception:
                # Don't fail the save if submission linking fails
                pass
        
        super().save(*args, **kwargs)
