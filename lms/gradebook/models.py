from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from courses.models import Course
from assignments.models import Assignment
from decimal import Decimal


class Grade(models.Model):
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name='grades')
    submission = models.ForeignKey('assignments.AssignmentSubmission', on_delete=models.CASCADE, related_name='grade_record', null=True, blank=True)
    score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    excused = models.BooleanField(default=False)
    feedback = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['student', 'assignment']

    def clean(self):
        """Validate the grade model with comprehensive checks"""
        super().clean()
        
        # Validate score is within reasonable bounds
        if self.score is not None:
            from decimal import Decimal
            
            # Convert to Decimal for precise validation
            try:
                score_decimal = Decimal(str(self.score))
            except (ValueError, TypeError):
                raise ValidationError({'score': 'Invalid score format'})
            
            if score_decimal < 0:
                raise ValidationError({'score': 'Score cannot be negative'})
            
            # Check against assignment's max score if available
            if self.assignment and hasattr(self.assignment, 'max_score') and self.assignment.max_score:
                if score_decimal > Decimal(str(self.assignment.max_score)):
                    raise ValidationError({
                        'score': f'Score cannot exceed assignment maximum of {self.assignment.max_score}'
                    })
            elif score_decimal > Decimal('9999.99'):  # Fallback to field max
                raise ValidationError({'score': 'Score is too large (max 9999.99)'})
        
        # Validate that excused grades don't have scores
        if self.excused and self.score is not None:
            raise ValidationError({'score': 'Excused grades should not have a score'})
        
        # Validate that non-excused grades have scores
        if not self.excused and self.score is None:
            raise ValidationError({'score': 'Non-excused grades must have a score'})
        
        # Validate course consistency
        if self.assignment and self.assignment.course and self.course:
            if self.assignment.course != self.course:
                raise ValidationError({
                    'course': 'Course must match the assignment\'s course'
                })
        
        # Validate student is enrolled in the course
        if self.course and self.student:
            from courses.models import CourseEnrollment
            if not CourseEnrollment.objects.filter(
                course=self.course, 
                user=self.student, 
                is_active=True
            ).exists():
                raise ValidationError({
                    'student': 'Student must be enrolled in the course'
                })
    
    def __str__(self):
        return f"{self.student.username} - {self.assignment.title} - {self.score if self.score else 'Excused' if self.excused else 'Not graded'}"

    def save(self, *args, **kwargs):
        # Validate before saving
        self.full_clean()
        
        # Track score changes for audit trail
        old_score = None
        if self.pk:
            try:
                old_grade = Grade.objects.get(pk=self.pk)
                old_score = old_grade.score
            except Grade.DoesNotExist:
                pass
        
        # Ensure course is always consistent with assignment's course
        if self.assignment and self.assignment.course:
            self.course = self.assignment.course
        
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
        
        # Log score change for audit trail
        if old_score != self.score:
            from .score_history import ScoreHistory
            change_type = 'created' if not self.pk else 'updated'
            ScoreHistory.log_score_change(
                obj=self,
                old_score=old_score,
                new_score=self.score,
                changed_by=getattr(self, '_changed_by', None),
                change_type=change_type,
                reason=getattr(self, '_change_reason', ''),
                metadata={
                    'assignment_id': self.assignment.id if self.assignment else None,
                    'student_id': self.student.id if self.student else None,
                    'excused': self.excused
                }
            )
