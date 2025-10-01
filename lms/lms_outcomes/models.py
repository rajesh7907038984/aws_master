from django.db import models
from django.utils.text import slugify
from django.core.exceptions import ValidationError
from courses.models import Course
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
import json
from datetime import datetime, timedelta
from django.utils import timezone
from django.db.models import Avg, Max, Q
from decimal import Decimal, ROUND_HALF_UP


class OutcomeGroup(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='outcome_groups', null=True, blank=True)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='children')
    branch = models.ForeignKey(
        'branches.Branch',
        on_delete=models.CASCADE,
        related_name='outcome_groups',
        null=True,
        blank=True,
        help_text="The branch this outcome group belongs to"
    )
    created_by = models.ForeignKey(
        'users.CustomUser',
        on_delete=models.SET_NULL,
        related_name='created_outcome_groups',
        null=True,
        blank=True,
        help_text="The user who created this outcome group"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name)
            slug = base_slug
            counter = 1
            
            # Check if slug already exists and find a unique one
            while OutcomeGroup.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
                
            self.slug = slug
            
        # Auto-set branch from course if not set
        if self.course and not self.branch:
            self.branch = self.course.branch
        super().save(*args, **kwargs)
    
    def __str__(self):
        return self.name
    
    class Meta:
        app_label = 'lms_outcomes'
        # Use primary key ordering to avoid potential column issues during deletion
        ordering = ['id']


class Outcome(models.Model):
    CALCULATION_METHODS = (
        ('weighted_average', 'Weighted Average'),
        ('decaying_average', 'Decaying Average'),
        ('n_times', 'n Number of Times'),
        ('most_recent', 'Most Recent Score'),
        ('highest', 'Highest score'),
        ('average', 'Average'),
        ('no_point', 'No Point'),
    )
    
    title = models.CharField(max_length=350)
    friendly_name = models.CharField(max_length=255, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    friendly_description = models.TextField(blank=True, null=True)
    criterion = models.TextField(blank=True, null=True)
    group = models.ForeignKey(OutcomeGroup, on_delete=models.CASCADE, related_name='outcomes', null=True, blank=True)
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='outcomes', null=True, blank=True)
    branch = models.ForeignKey(
        'branches.Branch',
        on_delete=models.CASCADE,
        related_name='outcomes',
        null=True,
        blank=True,
        help_text="The branch this outcome belongs to"
    )
    created_by = models.ForeignKey(
        'users.CustomUser',
        on_delete=models.SET_NULL,
        related_name='created_outcomes',
        null=True,
        blank=True,
        help_text="The user who created this outcome"
    )
    
    # Proficiency ratings
    proficiency_ratings = models.JSONField(blank=True, null=True)
    mastery_points = models.IntegerField(default=3)
    calculation_method = models.CharField(max_length=20, choices=CALCULATION_METHODS, default='weighted_average')
    last_item_weight = models.IntegerField(default=65)  # As percentage
    times_to_achieve = models.IntegerField(default=5)   # Used for n_times calculation method
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.title
    
    def save(self, *args, **kwargs):
        # Ensure proficiency_ratings is a valid JSON
        if self.proficiency_ratings and isinstance(self.proficiency_ratings, str):
            try:
                self.proficiency_ratings = json.loads(self.proficiency_ratings)
            except json.JSONDecodeError:
                # If it's not valid JSON, set a default structure
                self.proficiency_ratings = self.get_default_ratings()
        elif not self.proficiency_ratings:
            self.proficiency_ratings = self.get_default_ratings()
        
        # Auto-set branch from course or group if not set
        if not self.branch:
            if self.course:
                self.branch = self.course.branch
            elif self.group and self.group.branch:
                self.branch = self.group.branch
            
        super().save(*args, **kwargs)
    
    def get_default_ratings(self):
        return [
            {"name": "Exceeds Mastery", "points": 4},
            {"name": "Mastery", "points": 3},
            {"name": "Near Mastery", "points": 2},
            {"name": "Below Mastery", "points": 1},
            {"name": "No Evidence", "points": 0}
        ]
    
    def calculate_outcome_score(self, student):
        """
        Calculate the outcome score for a student based on their rubric evaluations
        and the outcome's calculation method.
        """
        # Get all evidence (rubric evaluations) for this student that are connected to this outcome
        evidence_scores = self._get_evidence_scores(student)
        
        if not evidence_scores:
            return None
            
        # Apply the calculation method
        if self.calculation_method == 'weighted_average':
            return self._calculate_weighted_average(evidence_scores)
        elif self.calculation_method == 'decaying_average':
            return self._calculate_decaying_average(evidence_scores)
        elif self.calculation_method == 'n_times':
            return self._calculate_n_times(evidence_scores)
        elif self.calculation_method == 'most_recent':
            return self._calculate_most_recent(evidence_scores)
        elif self.calculation_method == 'highest':
            return self._calculate_highest(evidence_scores)
        elif self.calculation_method == 'average':
            return self._calculate_average(evidence_scores)
        elif self.calculation_method == 'no_point':
            return self._calculate_no_point(evidence_scores)
        else:
            return self._calculate_weighted_average(evidence_scores)  # default
    
    def _get_evidence_scores(self, student):
        """Get all evidence scores for this outcome from rubric evaluations"""
        evidence_scores = []
        
        # Get all rubric criteria connected to this outcome
        connections = self.criterion_connections.all()
        
        for connection in connections:
            criterion = connection.criterion
            weight = connection.weight
            
            # Get all evaluations for this criterion and student
            from lms_rubrics.models import RubricEvaluation
            from quiz.models import QuizRubricEvaluation  
            from conferences.models import ConferenceRubricEvaluation
            
            # Assignment and Discussion evaluations
            evaluations = RubricEvaluation.objects.filter(
                criterion=criterion,
                student=student
            ).order_by('-created_at')
            
            for eval in evaluations:
                # Convert points to proficiency score based on criterion max points
                if criterion.points > 0:
                    proficiency_score = (eval.points / criterion.points) * max([r['points'] for r in self.proficiency_ratings])
                else:
                    proficiency_score = 0
                    
                evidence_scores.append({
                    'score': proficiency_score,
                    'weight': weight,
                    'date': eval.created_at,
                    'max_score': max([r['points'] for r in self.proficiency_ratings]),
                    'raw_points': eval.points,
                    'max_points': criterion.points
                })
            
            # Quiz evaluations
            quiz_evaluations = QuizRubricEvaluation.objects.filter(
                criterion=criterion,
                quiz_attempt__user=student
            ).order_by('-created_at')
            
            for eval in quiz_evaluations:
                if criterion.points > 0:
                    proficiency_score = (eval.points / criterion.points) * max([r['points'] for r in self.proficiency_ratings])
                else:
                    proficiency_score = 0
                    
                evidence_scores.append({
                    'score': proficiency_score,
                    'weight': weight,
                    'date': eval.created_at,
                    'max_score': max([r['points'] for r in self.proficiency_ratings]),
                    'raw_points': eval.points,
                    'max_points': criterion.points
                })
            
            # Conference evaluations
            conference_evaluations = ConferenceRubricEvaluation.objects.filter(
                criterion=criterion,
                attendance__user=student
            ).order_by('-created_at')
            
            for eval in conference_evaluations:
                if criterion.points > 0:
                    proficiency_score = (eval.points / criterion.points) * max([r['points'] for r in self.proficiency_ratings])
                else:
                    proficiency_score = 0
                    
                evidence_scores.append({
                    'score': proficiency_score,
                    'weight': weight,
                    'date': eval.created_at,
                    'max_score': max([r['points'] for r in self.proficiency_ratings]),
                    'raw_points': eval.points,
                    'max_points': criterion.points
                })
        
        return sorted(evidence_scores, key=lambda x: x['date'])
    
    def _calculate_weighted_average(self, evidence_scores):
        """Calculate weighted average with more weight on recent items"""
        if not evidence_scores:
            return 0
            
        total_weighted_score = 0
        total_weight = 0
        
        # Apply weights based on recency and criterion weight
        for i, evidence in enumerate(evidence_scores):
            # Recent items get more weight based on last_item_weight percentage
            if i == len(evidence_scores) - 1:  # Most recent
                recency_weight = self.last_item_weight / 100.0
            else:
                # Distribute remaining weight among older items
                remaining_weight = (100 - self.last_item_weight) / 100.0
                older_count = len(evidence_scores) - 1
                recency_weight = remaining_weight / older_count if older_count > 0 else 0
            
            combined_weight = evidence['weight'] * recency_weight
            total_weighted_score += evidence['score'] * combined_weight
            total_weight += combined_weight
        
        return total_weighted_score / total_weight if total_weight > 0 else 0
    
    def _calculate_decaying_average(self, evidence_scores):
        """Calculate decaying average where older scores have less influence"""
        if not evidence_scores:
            return 0
            
        total_weighted_score = 0
        total_weight = 0
        
        for i, evidence in enumerate(evidence_scores):
            # Apply exponential decay - more recent items have higher weight
            decay_factor = (self.last_item_weight / 100.0) ** (len(evidence_scores) - i - 1)
            combined_weight = evidence['weight'] * decay_factor
            
            total_weighted_score += evidence['score'] * combined_weight
            total_weight += combined_weight
        
        return total_weighted_score / total_weight if total_weight > 0 else 0
    
    def _calculate_n_times(self, evidence_scores):
        """Only consider outcome achieved if student reaches mastery n times"""
        if not evidence_scores:
            return 0
            
        mastery_scores = []
        for evidence in evidence_scores:
            if evidence['score'] >= self.mastery_points:
                mastery_scores.append(evidence['score'])
        
        if len(mastery_scores) >= self.times_to_achieve:
            # Return average of mastery scores when achieved
            return sum(mastery_scores) / len(mastery_scores)
        else:
            # Return average of all attempts when not achieved
            return sum(e['score'] for e in evidence_scores) / len(evidence_scores)
    
    def _calculate_most_recent(self, evidence_scores):
        """Use only the most recent score"""
        if not evidence_scores:
            return 0
        return evidence_scores[-1]['score']
    
    def _calculate_highest(self, evidence_scores):
        """Use the highest score achieved"""
        if not evidence_scores:
            return 0
        return max(evidence['score'] for evidence in evidence_scores)
    
    def _calculate_average(self, evidence_scores):
        """Simple average of all scores"""
        if not evidence_scores:
            return 0
        total_score = sum(evidence['score'] * evidence['weight'] for evidence in evidence_scores)
        total_weight = sum(evidence['weight'] for evidence in evidence_scores)
        return total_score / total_weight if total_weight > 0 else 0
    
    def _calculate_no_point(self, evidence_scores):
        """Binary achievement - either met or not met"""
        if not evidence_scores:
            return 0
            
        # Check if any evidence shows mastery
        for evidence in evidence_scores:
            if evidence['score'] >= self.mastery_points:
                return 1  # Met
        return 0  # Not met
    
    def update_student_evaluation(self, student):
        """Calculate and save/update the outcome evaluation for a student"""
        score = self.calculate_outcome_score(student)
        
        if score is not None:
            # Get evidence count
            evidence_scores = self._get_evidence_scores(student)
            evidence_count = len(evidence_scores)
            
            # Create or update evaluation
            evaluation, created = OutcomeEvaluation.objects.get_or_create(
                student=student,
                outcome=self,
                defaults={
                    'score': score,
                    'evidence_count': evidence_count
                }
            )
            
            if not created:
                evaluation.score = score
                evaluation.evidence_count = evidence_count
            
            # Always save to trigger proficiency_level calculation
            evaluation.save()
            
            return evaluation
        
        return None
    
    class Meta:
        app_label = 'lms_outcomes'
        # Use primary key ordering to avoid potential column issues during deletion
        ordering = ['id']


class OutcomeAlignment(models.Model):
    """
    Model to connect outcomes with assessable artifacts like assignments, quizzes, and discussions.
    Uses ContentType framework for a generic relationship.
    """
    CONTENT_TYPE_CHOICES = (
        ('assignment', 'Assignment'),
        ('quiz', 'Quiz'),
        ('discussion', 'Discussion'),
    )
    
    outcome = models.ForeignKey(
        Outcome, 
        on_delete=models.CASCADE,
        related_name='alignments'
    )
    content_type = models.CharField(
        max_length=20,
        choices=CONTENT_TYPE_CHOICES
    )
    object_id = models.PositiveIntegerField()
    
    # Optional fields for tracking and metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        app_label = 'lms_outcomes'
        unique_together = ['outcome', 'content_type', 'object_id']
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['outcome']),
        ]
        
    def __str__(self):
        return f"Alignment: {self.outcome.title} -> {self.content_type} #{self.object_id}"


class RubricCriterionOutcome(models.Model):
    """
    Model to connect rubric criteria to specific outcomes for assessment.
    This enables rubric evaluations to contribute to outcome calculations.
    """
    criterion = models.ForeignKey(
        'lms_rubrics.RubricCriterion',
        on_delete=models.CASCADE,
        related_name='outcome_connections'
    )
    outcome = models.ForeignKey(
        Outcome,
        on_delete=models.CASCADE,
        related_name='criterion_connections'
    )
    weight = models.FloatField(
        default=1.0,
        help_text="Weight of this criterion in the outcome calculation (0.0-1.0)"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        app_label = 'lms_outcomes'
        unique_together = ['criterion', 'outcome']
        indexes = [
            models.Index(fields=['criterion']),
            models.Index(fields=['outcome']),
        ]
    
    def __str__(self):
        return f"{self.criterion} -> {self.outcome.title} (weight: {self.weight})"
    
    def clean(self):
        """Validate weight is between 0 and 1"""
        if self.weight < 0 or self.weight > 1:
            raise ValidationError({'weight': 'Weight must be between 0.0 and 1.0'})
        super().clean()


class OutcomeEvaluation(models.Model):
    """
    Model to store calculated outcome scores for students based on their performance.
    """
    student = models.ForeignKey(
        'users.CustomUser',
        on_delete=models.CASCADE,
        related_name='outcome_evaluations'
    )
    outcome = models.ForeignKey(
        Outcome,
        on_delete=models.CASCADE,
        related_name='evaluations'
    )
    score = models.FloatField(
        help_text="Calculated score based on the outcome's calculation method"
    )
    proficiency_level = models.CharField(
        max_length=100,
        blank=True,
        help_text="Text description of proficiency level (e.g., 'Mastery', 'Near Mastery')"
    )
    
    # Tracking fields
    calculation_date = models.DateTimeField(auto_now=True)
    evidence_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of evidence items used in calculation"
    )
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        app_label = 'lms_outcomes'
        unique_together = ['student', 'outcome']
        ordering = ['-calculation_date']
        indexes = [
            models.Index(fields=['student', 'outcome']),
            models.Index(fields=['outcome', '-score']),
        ]
    
    def __str__(self):
        return f"{self.student.get_full_name()} - {self.outcome.title}: {self.score}"
    
    def get_proficiency_rating(self):
        """Get the proficiency rating based on score and outcome's proficiency ratings"""
        if not self.outcome.proficiency_ratings:
            return None
            
        # Find the appropriate rating based on score
        for rating in sorted(self.outcome.proficiency_ratings, key=lambda x: x['points'], reverse=True):
            if self.score >= rating['points']:
                return rating
        
        # If no rating found, return the lowest
        if self.outcome.proficiency_ratings:
            return min(self.outcome.proficiency_ratings, key=lambda x: x['points'])
        
        return None
    
    def save(self, *args, **kwargs):
        # Update proficiency level based on score
        rating = self.get_proficiency_rating()
        if rating:
            self.proficiency_level = rating['name']
        super().save(*args, **kwargs) 