from django.db import models
from django.conf import settings
from django.utils import timezone
from django.urls import reverse
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from django.db.models import F, Q
from django.core.cache import cache
import json

class Quiz(models.Model):
    """Model for storing quizzes"""
    title = models.CharField(max_length=255)
    description = models.TextField()
    instructions = models.TextField(blank=True, help_text="Detailed instructions for taking the quiz. Will be shown to students.")
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='created_quizzes'
    )
    course = models.ForeignKey(
        'courses.Course',
        on_delete=models.CASCADE,
        related_name='quizzes',
        null=True,
        blank=True
    )
    time_limit = models.PositiveIntegerField(
        help_text="Time limit in minutes. Set to 0 for no limit.",
        default=0
    )
    passing_score = models.PositiveIntegerField(
        help_text="Passing score in percentage (not required for VAK Test)",
        default=70,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    attempts_allowed = models.PositiveIntegerField(
        help_text="Number of attempts allowed per user. Set to -1 for unlimited.",
        default=1
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the quiz expires. Leave empty for no expiration."
    )
    show_correct_answers = models.BooleanField(
        default=False,
        help_text="Whether to show correct answers after submission"
    )
    randomize_questions = models.BooleanField(
        default=False,
        help_text="Whether to randomize question order for each attempt"
    )
    require_sequential = models.BooleanField(
        default=False,
        help_text="Whether questions must be answered in order"
    )
    max_concurrent_attempts = models.PositiveIntegerField(
        default=3,
        help_text="Maximum number of concurrent attempts allowed"
    )
    rubric = models.ForeignKey(
        'lms_rubrics.Rubric',
        on_delete=models.SET_NULL,
        related_name='quizzes',
        null=True,
        blank=True,
        help_text="Optional rubric used for additional grading criteria"
    )
    
    # Quiz Type Fields
    is_initial_assessment = models.BooleanField(
        default=False,
        help_text="Mark this quiz as an Initial Assessment. Multiple assessments are allowed per branch."
    )
    is_vak_test = models.BooleanField(
        default=False,
        help_text="Mark this quiz as a VAK Test. Multiple tests are allowed per branch."
    )
    
    # Initial Assessment Percentage Configuration
    level_2_percentage = models.PositiveIntegerField(
        default=75,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Level 2 Minimum % - Percentage threshold for Level 2 (0-100)"
    )
    level_1_percentage = models.PositiveIntegerField(
        default=60,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Level 1 Minimum % - Percentage threshold for Level 1 (0-100)"
    )
    below_level_1_percentage = models.PositiveIntegerField(
        default=50,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Below Level 1 Minimum % - Percentage threshold for Below Level 1 (0-100)"
    )
    total_threshold = models.PositiveIntegerField(
        default=70,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Overall Performance % - Total percentage threshold for overall performance (0-100)"
    )

    class Meta:
        app_label = 'quiz'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['creator', '-created_at']),
            models.Index(fields=['course', '-created_at']),
            models.Index(fields=['expires_at']),
        ]
        verbose_name_plural = "Quizzes"

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('quiz:quiz_detail', kwargs={'quiz_id': self.id})

    def clean(self):
        if self.expires_at and self.expires_at <= timezone.now():
            raise ValidationError("Expiration date must be in the future")
        
        # Clear rubric for assessment type quizzes
        if self.is_initial_assessment or self.is_vak_test:
            self.rubric = None
        
        # Set passing score to None only for VAK Test (Initial Assessment uses passing scores)
        if self.is_vak_test:
            self.passing_score = None
        
        # Validate percentage configuration for Initial Assessment
        if self.is_initial_assessment:
            if (self.level_2_percentage is None or self.level_1_percentage is None or 
                self.below_level_1_percentage is None or self.total_threshold is None):
                raise ValidationError("Initial Assessment requires percentage configuration for all levels including total threshold.")
            
            # Validate that percentages are in descending order
            if not (self.level_2_percentage > self.level_1_percentage > self.below_level_1_percentage):
                raise ValidationError("Level percentages must be in descending order: Level 2 > Level 1 > Below Level 1")
        
        # Quiz type restrictions removed for unlimited assessments

    @property
    def total_points(self):
        """Calculate total points for all questions in the quiz"""
        return self.questions.aggregate(total=models.Sum('points'))['total'] or 0

    @property
    def total_questions(self):
        """Get total number of questions in the quiz"""
        return self.questions.count()

    def is_available_for_user(self, user):
        """Check if quiz is available for the user to take - RESTRICTED TO LEARNERS ONLY"""
        if not self.is_active:
            return False
        
        if self.expires_at and timezone.now() > self.expires_at:
            return False
        
        # ROLE RESTRICTION: Only learner role users can attempt quizzes
        if user.role != 'learner':
            return False
        
        # For learner role, apply strict filtering
        if user.role == 'learner':
            # VAK Test and Initial Assessment quizzes are accessible to all learners without course requirements
            if self.is_vak_test or self.is_initial_assessment:
                # Skip course enrollment and topic checks for these special quiz types
                # But still check attempt limits
                pass  # Continue to attempt limit check below
            else:
                # Check topic status only if quiz is linked to topics
                if self.topics.exists():
                    # Check if this quiz is linked to any published topics
                    # Learners can only access quizzes that are linked to active/published topics
                    if not self.topics.filter(status='active').exists():
                        return False  # No published topics linked to this quiz
                    
                    # Check if this quiz is linked to any draft topics
                    # Learners cannot access quizzes that have any draft topics
                    if self.topics.filter(status='draft').exists():
                        return False  # Quiz has draft topics, not available to learners
                
                # Check if user is enrolled in any courses linked to this quiz
                # Quiz can be linked to courses through direct, M2M, or topic relationships
                from courses.models import Course, CourseEnrollment
                
                # Get all courses that the user is enrolled in as a learner
                enrolled_course_ids = CourseEnrollment.objects.filter(user=user, user__role='learner').values_list('course_id', flat=True)
                
                # Check if quiz is linked to any enrolled courses through any relationship
                linked_to_enrolled_course = (
                    # Direct course relationship
                    (self.course and self.course.id in enrolled_course_ids) or
                    # Topic-based course relationship
                    Course.objects.filter(
                        id__in=enrolled_course_ids,
                        coursetopic__topic__quiz=self
                    ).exists()
                )
                
                if not linked_to_enrolled_course:
                    return False
        
        # Handle unlimited attempts
        if self.attempts_allowed == -1:  # -1 represents unlimited attempts
            return True
        
        # Get number of completed attempts by user
        completed_attempts = self.get_completed_attempts(user)
        return completed_attempts < self.attempts_allowed

    def get_completed_attempts(self, user):
        """Get count of completed attempts by user"""
        return self.attempts.filter(user=user, is_completed=True).count()
    
    def get_remaining_attempts(self, user):
        """Get count of remaining attempts for user"""
        if self.attempts_allowed == -1:  # Unlimited attempts
            return -1
        completed_attempts = self.get_completed_attempts(user)
        return max(0, self.attempts_allowed - completed_attempts)

    def get_concurrent_attempts(self, user):
        """Get number of concurrent attempts by user"""
        # Only count incomplete attempts that were started in the last hour
        recent_time = timezone.now() - timezone.timedelta(hours=1)
        return self.attempts.filter(
            user=user,
            is_completed=False,
            start_time__gte=recent_time
        ).count()

    def get_course_info(self):
        """Get course information for this quiz, checking both direct and topic relationships"""
        # First check if quiz has a direct course relationship
        if self.course:
            return self.course
        
        # If no direct course, check through topics
        # Get the first topic that this quiz is associated with
        topic = self.topics.first()
        if topic:
            # Get the first course that this topic is associated with
            course = topic.courses.first()
            if course:
                return course
        
        # Return None if no course relationship found
        return None

    def can_start_new_attempt(self, user):
        """Check if user can start a new attempt"""
        # Clean up stale attempts first
        self.clean_stale_attempts(user)
        
        # If user has reached max concurrent attempts, try to clean up stuck attempts
        if self.get_concurrent_attempts(user) >= self.max_concurrent_attempts:
            # Check if any of the concurrent attempts are actually stuck (no recent activity)
            stuck_time = timezone.now() - timezone.timedelta(minutes=30)
            stuck_attempts = self.attempts.filter(
                user=user,
                is_completed=False,
                last_activity__lt=stuck_time
            )
            if stuck_attempts.exists():
                # Clean up stuck attempts
                from .models import UserAnswer
                UserAnswer.objects.filter(attempt__in=stuck_attempts).delete()
                stuck_attempts.delete()
                # Recheck after cleanup
                if self.get_concurrent_attempts(user) >= self.max_concurrent_attempts:
                    return False
            else:
                return False
        
        if not self.is_available_for_user(user):
            return False
            
        return True
        
    def clean_stale_attempts(self, user):
        """Clean up stale incomplete attempts"""
        stale_time = timezone.now() - timezone.timedelta(hours=1)
        stale_attempts = self.attempts.filter(
            user=user,
            is_completed=False,
            last_activity__lt=stale_time
        )
        count = stale_attempts.count()
        if count > 0:
            # Delete associated answers first for data integrity
            from .models import UserAnswer
            UserAnswer.objects.filter(attempt__in=stale_attempts).delete()
            stale_attempts.delete()
        return count
    
    def clean_expired_attempts(self, user=None):
        """Clean up expired incomplete attempts"""
        queryset = self.attempts.filter(is_completed=False)
        if user:
            queryset = queryset.filter(user=user)
        
        expired_attempts = []
        for attempt in queryset.select_related('quiz'):
            if attempt.is_expired():
                expired_attempts.append(attempt.id)
        
        if expired_attempts:
            # Delete associated answers first
            from .models import UserAnswer
            UserAnswer.objects.filter(attempt_id__in=expired_attempts).delete()
            self.attempts.filter(id__in=expired_attempts).delete()
        
        return len(expired_attempts)
    
    def cleanup_user_attempts(self, user):
        """Comprehensive cleanup of user attempts for this quiz"""
        stale_count = self.clean_stale_attempts(user)
        expired_count = self.clean_expired_attempts(user)
        return stale_count + expired_count
    
    @classmethod 
    def cleanup_all_expired_attempts(cls):
        """Cleanup expired attempts across all quizzes (for background tasks)"""
        from .models import UserAnswer
        
        total_cleaned = 0
        expired_attempts = []
        
        # Get all incomplete attempts
        incomplete_attempts = cls.objects.prefetch_related(
            'attempts'
        ).filter(attempts__is_completed=False).distinct()
        
        for quiz in incomplete_attempts:
            for attempt in quiz.attempts.filter(is_completed=False):
                if attempt.is_expired():
                    expired_attempts.append(attempt.id)
        
        if expired_attempts:
            # Batch delete answers and attempts
            UserAnswer.objects.filter(attempt_id__in=expired_attempts).delete()
            from .models import QuizAttempt
            QuizAttempt.objects.filter(id__in=expired_attempts).delete()
            total_cleaned = len(expired_attempts)
        
        return total_cleaned

    def get_randomized_questions(self):
        """Get questions in random order if enabled"""
        if self.randomize_questions:
            return self.questions.order_by('?')
        return self.questions.order_by('order')

class Question(models.Model):
    """Model for storing quiz questions"""
    QUESTION_TYPES = (
        ('multiple_choice', 'Multiple Choice'),
        ('multiple_select', 'Multiple Select'),
        ('true_false', 'True/False'),
        ('fill_blank', 'Fill in the Blank'),
        ('multi_blank', 'Multiple Blanks'),
        ('matching', 'Matching'),
        ('drag_drop_matching', 'Drag & Drop Matching'),
    )
    
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='questions')
    question_text = models.TextField()
    question_type = models.CharField(max_length=20, choices=QUESTION_TYPES)
    points = models.PositiveIntegerField(default=1)
    order = models.PositiveIntegerField(default=0)
    min_required = models.PositiveIntegerField(
        default=1,
        help_text="Minimum number of options required for multiple select questions"
    )
    case_sensitive = models.BooleanField(
        default=False,
        help_text="Whether text answers are case sensitive"
    )
    assessment_level = models.CharField(
        max_length=20,
        choices=[
            ('below_level_1', 'Below Level 1'),
            ('level_1', 'Level 1'),
            ('level_2', 'Level 2'),
        ],
        null=True,
        blank=True,
        help_text="Assessment level for Initial Assessment questions"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'quiz'
        ordering = ['order', 'id']
        indexes = [
            models.Index(fields=['quiz', 'order']),
        ]

    def __str__(self):
        return f"{self.question_text[:50]}..."

    def clean(self):
        if self.question_type == 'multiple_select' and self.min_required < 1:
            raise ValidationError("Minimum required options must be at least 1")

    def check_answer(self, user_answer):
        """Check if user's answer is correct"""
        import logging
        logger = logging.getLogger(__name__)
        
        if not user_answer:
            logger.debug(f"Empty answer for {self.question_type} question")
            return False
            
        correct_answers = self.get_correct_answers()
        logger.debug(f"Question type: {self.question_type}, user answer: {user_answer}, correct answers: {correct_answers}")
        
        if self.question_type in ['multiple_choice', 'multiple_select']:
            # Ensure all IDs are strings for consistent comparison
            if isinstance(correct_answers, list):
                correct_answers = [str(ans) for ans in correct_answers if ans]
                
            if isinstance(user_answer, list):
                user_answer = [str(ans) for ans in user_answer if ans]
                # For multiple_select, compare sets to ignore order
                result = set(user_answer) == set(correct_answers)
                logger.debug(f"Multiple select comparison: {set(user_answer)} == {set(correct_answers)} = {result}")
                return result
            
            # For multiple_choice
            result = str(user_answer) in correct_answers
            logger.debug(f"Multiple choice comparison: {str(user_answer)} in {correct_answers} = {result}")
            return result
            
        elif self.question_type == 'true_false':
            # Normalize true/false values for comparison
            correct = correct_answers[0].lower().strip()
            if isinstance(user_answer, bool):
                user_val = str(user_answer).lower()
            elif isinstance(user_answer, str):
                user_val = user_answer.lower().strip()
            else:
                user_val = str(user_answer).lower().strip()
                
            # Handle special case where database has "True"/"False" but user inputs boolean
            return user_val == correct or (user_val == 'true' and correct == 'true') or (user_val == 'false' and correct == 'false')
            
        elif self.question_type == 'fill_blank':
            if not self.case_sensitive:
                return user_answer.lower().strip() == correct_answers[0].lower().strip()
            return user_answer.strip() == correct_answers[0].strip()
            
        elif self.question_type == 'multi_blank':
            if not self.case_sensitive:
                return [ans.lower().strip() for ans in user_answer] == [ans.lower().strip() for ans in correct_answers]
            return [ans.strip() for ans in user_answer] == [ans.strip() for ans in correct_answers]
            
        elif self.question_type == 'matching':
            if not isinstance(user_answer, list) or len(user_answer) != len(correct_answers):
                return False
            
            # Convert user answers to set of tuples for comparison
            user_pairs = set((pair.get('left_item', '').strip(), pair.get('right_item', '').strip()) 
                           for pair in user_answer)
            correct_pairs = set((pair['left_item'].strip(), pair['right_item'].strip()) 
                              for pair in correct_answers)
            
            return user_pairs == correct_pairs
            
        elif self.question_type == 'drag_drop_matching':
            if not isinstance(user_answer, dict):
                return False
            
            # Get correct pairs from matching_pairs
            correct_pairs = {}
            for pair in self.matching_pairs.all():
                correct_pairs[pair.left_item.strip()] = pair.right_item.strip()
            
            # Check if user's drag-drop matches are correct
            for left_item, right_item in user_answer.items():
                if left_item.strip() not in correct_pairs:
                    return False
                if correct_pairs[left_item.strip()] != right_item.strip():
                    return False
            
            # Check if all items are matched
            return len(user_answer) == len(correct_pairs)
            
        return False

    def get_correct_answers(self):
        """Get list of correct answers based on question type"""
        if self.question_type in ['multiple_choice', 'multiple_select']:
            return list(self.answers.filter(is_correct=True).values_list('id', flat=True))
        elif self.question_type == 'true_false':
            return [self.answers.filter(is_correct=True).first().answer_text]
        elif self.question_type == 'fill_blank':
            return [self.answers.first().answer_text]
        elif self.question_type == 'multi_blank':
            return list(self.answers.order_by('answer_order').values_list('answer_text', flat=True))
        elif self.question_type == 'matching':
            return list(self.matching_pairs.order_by('pair_order').values('left_item', 'right_item'))
        elif self.question_type == 'drag_drop_matching':
            return list(self.matching_pairs.order_by('pair_order').values('left_item', 'right_item'))
        return []

class Answer(models.Model):
    """Model for storing question answers"""
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='answers')
    answer_text = models.TextField()
    is_correct = models.BooleanField(default=False)
    answer_order = models.PositiveIntegerField(default=0, db_column='answer_order')
    explanation = models.TextField(
        blank=True,
        help_text="Explanation for why this answer is correct/incorrect"
    )
    learning_style = models.CharField(
        max_length=20,
        choices=[
            ('visual', 'Visual'),
            ('auditory', 'Auditory'),
            ('kinesthetic', 'Kinesthetic'),
        ],
        null=True,
        blank=True,
        help_text="Learning style for VAK test answer options"
    )

    class Meta:
        app_label = 'quiz'
        ordering = ['answer_order', 'id']
        indexes = [
            models.Index(fields=['question', 'answer_order']),
        ]

    def __str__(self):
        return f"{self.answer_text[:50]}..."

    def clean(self):
        if self.question.question_type == 'multiple_choice':
            # Multiple choice must have exactly one correct answer
            if self.is_correct and self.question.answers.filter(is_correct=True).exclude(id=self.id).exists():
                raise ValidationError("Multiple choice questions can only have one correct answer")

class MatchingPair(models.Model):
    """Model for storing matching question pairs"""
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='matching_pairs')
    left_item = models.TextField()
    right_item = models.TextField()
    pair_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'quiz'
        ordering = ['pair_order', 'id']
        indexes = [
            models.Index(fields=['question', 'pair_order']),
        ]

    def __str__(self):
        return f"{self.left_item[:25]} -> {self.right_item[:25]}"

    def clean(self):
        if self.question.question_type not in ['matching', 'drag_drop_matching']:
            raise ValidationError("Matching pairs can only be added to matching or drag & drop matching type questions")

class QuizAttempt(models.Model):
    """Model for storing quiz attempts by users"""
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='attempts')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='module_quiz_attempts')
    score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    is_completed = models.BooleanField(default=False)
    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    last_activity = models.DateTimeField(auto_now=True)
    
    # Active time tracking fields
    active_time_seconds = models.PositiveIntegerField(
        default=0,
        help_text="Total active time spent on quiz pages in seconds"
    )
    last_activity_ping = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="Last time user activity was detected"
    )
    page_focus_time = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When user last focused on the quiz page"
    )
    is_currently_active = models.BooleanField(
        default=False,
        help_text="Whether user is currently active on the quiz page"
    )
    
    class Meta:
        app_label = 'quiz'
        ordering = ['-start_time']
        indexes = [
            models.Index(fields=['quiz', 'user']),
            models.Index(fields=['user', '-start_time']),
            models.Index(fields=['is_completed']),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.quiz.title}"
        
    @property
    def passed(self):
        """Check if the attempt passed the quiz based on passing score"""
        return self.score >= self.quiz.passing_score
        
    def calculate_score(self):
        """Calculate the score based on the user's answers"""
        if not self.is_completed:
            return 0
            
        total_points = sum(q.points for q in self.quiz.questions.all())
        if total_points == 0:
            return 0
            
        earned_points = sum(answer.question.points for answer in self.user_answers.filter(is_correct=True))
        percentage = round((earned_points / total_points) * 100)
        self.score = percentage
        self.save()
        return percentage
    
    def calculate_assessment_classification(self):
        """Calculate initial assessment classification and level percentages"""
        if not self.is_completed or not self.quiz.is_initial_assessment:
            return None
        
        # Get all questions with their assessment levels
        questions = self.quiz.questions.all()
        user_answers = self.user_answers.all()
        
        # Initialize points tracking
        level_points = {'level_2': 0, 'level_1': 0, 'below_level_1': 0}
        total_level_points = {'level_2': 0, 'level_1': 0, 'below_level_1': 0}
        
        # Calculate points for each level
        for question in questions:
            if question.assessment_level:
                total_level_points[question.assessment_level] += question.points
                
                # Check if user answered this question correctly
                user_answer = user_answers.filter(question=question).first()
                if user_answer and user_answer.is_correct:
                    level_points[question.assessment_level] += question.points
        
        # Calculate percentages for each level
        l2_percentage = round((level_points['level_2'] / total_level_points['level_2']) * 100) if total_level_points['level_2'] > 0 else 0
        l1_percentage = round((level_points['level_1'] / total_level_points['level_1']) * 100) if total_level_points['level_1'] > 0 else 0
        below_l1_percentage = round((level_points['below_level_1'] / total_level_points['below_level_1']) * 100) if total_level_points['below_level_1'] > 0 else 0
        
        # Total percentage (already calculated in self.score)
        total_percentage = float(self.score)
        
        # Get thresholds from quiz configuration
        level2_threshold = self.quiz.level_2_percentage or 75
        level1_threshold = self.quiz.level_1_percentage or 60
        below_level1_threshold = self.quiz.below_level_1_percentage or 50
        total_threshold = self.quiz.total_threshold or 70
        
        # Determine classification based on conditions
        classification = "Below Level 1"
        
        # Classification logic based on user requirements
        if (l2_percentage >= level2_threshold and 
            total_percentage >= total_threshold and 
            l1_percentage >= level1_threshold):
            classification = "Level 2"
        elif (l1_percentage >= level1_threshold and 
              l2_percentage < level2_threshold and 
              below_l1_percentage >= below_level1_threshold):
            classification = "Level 1"
        elif (l1_percentage < level1_threshold or 
              below_l1_percentage < below_level1_threshold):
            classification = "Below Level 1"
        
        return {
            "student_id": self.user.id,
            "classification": classification,
            "L2_Percentage": round(l2_percentage, 1),
            "L1_Percentage": round(l1_percentage, 1),
            "Below_Level1_Percentage": round(below_l1_percentage, 1),
            "Total_Percentage": round(total_percentage, 1),
            "thresholds": {
                "level2_threshold": level2_threshold,
                "level1_threshold": level1_threshold,
                "below_level1_threshold": below_level1_threshold,
                "total_threshold": total_threshold
            }
        }

    def is_expired(self):
        """Check if the attempt has expired based on quiz time limit"""
        if not self.quiz.time_limit or self.is_completed:
            return False
            
        # Calculate elapsed time
        now = timezone.now()
        elapsed_time = (now - self.start_time).total_seconds()
        time_limit_seconds = self.quiz.time_limit * 60  # Convert minutes to seconds
        
        # Increased grace period to handle network issues and user experience
        # This prevents premature expiration due to network delays or minor timing issues
        grace_period = 120  # 2 minutes grace period for better UX
        adjusted_limit = time_limit_seconds + grace_period
        
        # Add debugging for time calculations
        import logging
        logger = logging.getLogger(__name__)
        is_expired = elapsed_time >= adjusted_limit
        
        # Only log when approaching or exceeding time limit to reduce noise
        if elapsed_time >= time_limit_seconds * 0.9:  # Log when 90% of time used
            logger.info(f"Quiz attempt {self.id} time check - User: {self.user.username}, "
                       f"Start: {self.start_time}, Now: {now}, "
                       f"Elapsed: {elapsed_time:.1f}s, Original_Limit: {time_limit_seconds}s, "
                       f"Adjusted_Limit: {adjusted_limit}s, Is_Expired: {is_expired}, "
                       f"Quiz Time Limit: {self.quiz.time_limit} minutes, "
                       f"Grace Period: {grace_period}s")
        
        return is_expired

    def get_remaining_time(self):
        """Get remaining time in seconds"""
        if not self.quiz.time_limit or self.is_completed:
            return None
            
        # Calculate elapsed time
        now = timezone.now()
        elapsed_time = (now - self.start_time).total_seconds()
        time_limit_seconds = self.quiz.time_limit * 60  # Convert minutes to seconds
        
        remaining = time_limit_seconds - elapsed_time
        return max(0, int(remaining))

    def update_last_activity(self):
        """Update last activity timestamp"""
        self.last_activity = timezone.now()
        self.save()
    
    @property
    def duration(self):
        """Get the duration of the quiz attempt as a timedelta object"""
        if self.end_time and self.start_time:
            return self.end_time - self.start_time
        return None
    
    @property
    def duration_formatted(self):
        """Get formatted duration string"""
        duration = self.duration
        if not duration:
            return "N/A"
            
        total_seconds = int(duration.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        
        if hours > 0:
            return f"{hours}h {minutes}m {seconds}s"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"
    
    @property
    def active_time_formatted(self):
        """Get formatted active time string"""
        if not self.active_time_seconds:
            return "0s"
            
        total_seconds = self.active_time_seconds
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        
        if hours > 0:
            return f"{hours}h {minutes}m {seconds}s"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"
    
    def update_active_time(self, additional_seconds=0):
        """Update active time and last activity ping"""
        from django.utils import timezone
        
        if additional_seconds > 0:
            self.active_time_seconds += additional_seconds
        
        self.last_activity_ping = timezone.now()
        self.last_activity = timezone.now()
        self.save(update_fields=['active_time_seconds', 'last_activity_ping', 'last_activity'])
    
    def set_page_focus(self, is_focused=True):
        """Set page focus state and update tracking"""
        from django.utils import timezone
        
        now = timezone.now()
        
        if is_focused:
            self.page_focus_time = now
            self.is_currently_active = True
        else:
            # Calculate time since last focus and add to active time
            if self.page_focus_time and self.is_currently_active:
                time_diff = now - self.page_focus_time
                additional_seconds = int(time_diff.total_seconds())
                if additional_seconds > 0:
                    self.active_time_seconds += additional_seconds
            
            self.is_currently_active = False
        
        self.last_activity_ping = now
        self.save(update_fields=['page_focus_time', 'is_currently_active', 'last_activity_ping', 'active_time_seconds'])
    
    def get_current_active_session_time(self):
        """Get current active session time in seconds"""
        from django.utils import timezone
        
        if not self.is_currently_active or not self.page_focus_time:
            return 0
        
        time_diff = timezone.now() - self.page_focus_time
        return int(time_diff.total_seconds())
    
    @property
    def total_active_time_with_current_session(self):
        """Get total active time including current session"""
        return self.active_time_seconds + self.get_current_active_session_time()
    
    @property
    def responses(self):
        """Get user responses for this attempt"""
        user_answers = self.user_answers.all().select_related('question', 'answer')
        responses = []
        for user_answer in user_answers:
            response_data = {
                'question': user_answer.question,
                'answer': user_answer.answer,
                'text_answer': user_answer.text_answer,
                'matching_answers': user_answer.matching_answers,
                'is_correct': user_answer.is_correct,
                'points_earned': user_answer.points_earned,
                'selected_options': user_answer.get_selected_options_for_admin() if user_answer.question.question_type == 'multiple_select' else [],
                'parsed_matching_answers': user_answer.matching_answers if user_answer.matching_answers else []
            }
            responses.append(response_data)
        return responses
    
    def get_vak_results(self):
        """Get VAK learning style results for this attempt"""
        if not self.quiz.is_vak_test or not self.is_completed:
            return None
        
        # Count learning style selections
        visual_count = 0
        auditory_count = 0
        kinesthetic_count = 0
        total_selections = 0
        
        # Get all user answers for this attempt
        user_answers = self.user_answers.all().select_related('question', 'answer')
        
        for user_answer in user_answers:
            if user_answer.question.question_type in ['multiple_choice', 'multiple_select']:
                # Get selected answers
                selected_answers = user_answer.get_selected_options_for_admin()
                for answer in selected_answers:
                    if answer.learning_style:
                        total_selections += 1
                        if answer.learning_style == 'visual':
                            visual_count += 1
                        elif answer.learning_style == 'auditory':
                            auditory_count += 1
                        elif answer.learning_style == 'kinesthetic':
                            kinesthetic_count += 1
        
        # Calculate percentages
        visual_percentage = round((visual_count / total_selections) * 100) if total_selections > 0 else 0
        auditory_percentage = round((auditory_count / total_selections) * 100) if total_selections > 0 else 0
        kinesthetic_percentage = round((kinesthetic_count / total_selections) * 100) if total_selections > 0 else 0
        
        return {
            'visual': {
                'count': visual_count,
                'total': total_selections,
                'percentage': visual_percentage
            },
            'auditory': {
                'count': auditory_count,
                'total': total_selections,
                'percentage': auditory_percentage
            },
            'kinesthetic': {
                'count': kinesthetic_count,
                'total': total_selections,
                'percentage': kinesthetic_percentage
            }
        }

class UserAnswer(models.Model):
    """Model for storing user's answers to questions"""
    attempt = models.ForeignKey(QuizAttempt, on_delete=models.CASCADE, related_name='user_answers')
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    answer = models.ForeignKey(Answer, on_delete=models.CASCADE, null=True, blank=True)
    text_answer = models.TextField(null=True, blank=True)
    matching_answers = models.JSONField(null=True, blank=True)
    is_correct = models.BooleanField(default=False)
    points_earned = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    submitted_at = models.DateTimeField(default=timezone.now)
    
    class Meta:
        app_label = 'quiz'
        ordering = ['question__order']
        indexes = [
            models.Index(fields=['attempt', 'question']),
            models.Index(fields=['is_correct']),
        ]

    def __str__(self):
        return f"{self.attempt.user.username} - {self.question.question_text[:50]}..."

    def check_answer(self):
        """Check if the answer is correct and update points"""
        try:
            if self.question.question_type == 'multiple_select':
                # Check if there's a single answer ID (older format)
                if self.answer and not self.text_answer:
                    self.is_correct = self.question.check_answer(str(self.answer.id))
                else:
                    # Try to parse the JSON string from text_answer field
                    try:
                        if not self.text_answer:
                            answer_ids = []
                        elif isinstance(self.text_answer, list):
                            answer_ids = self.text_answer  # Already a list
                        else:
                            try:
                                answer_ids = json.loads(self.text_answer)
                            except json.JSONDecodeError:
                                # In case it's not valid JSON, try splitting by comma
                                answer_ids = [id.strip() for id in self.text_answer.split(',') if id.strip()]
                            
                        # Convert all IDs to strings for consistent comparison
                        answer_ids = [str(id) for id in answer_ids if id]
                        
                        if not answer_ids and self.answer:
                            answer_ids = [str(self.answer.id)]  # Fall back to single answer
                        
                        # Log the values for debugging
                        import logging
                        logger = logging.getLogger(__name__)
                        logger.debug(f"Checking multiple select answer: {answer_ids}")
                            
                        # Get correct answer IDs for comparison
                        correct_answer_ids = [str(id) for id in self.question.get_correct_answers()]
                        logger.debug(f"Correct answers: {correct_answer_ids}")
                        
                        # Get human-readable answer texts
                        try:
                            selected_answers = list(self.question.answers.filter(id__in=answer_ids))
                            selected_texts = [ans.answer_text for ans in selected_answers]
                            logger.debug(f"Selected answer texts: {selected_texts}")
                            
                            correct_answers = list(self.question.answers.filter(is_correct=True))
                            correct_texts = [ans.answer_text for ans in correct_answers]
                            logger.debug(f"Correct answer texts: {correct_texts}")
                        except Exception as e:
                            logger.error(f"Error getting answer texts: {e}")
                            
                        # Compare as sets to ignore order
                        self.is_correct = set(answer_ids) == set(correct_answer_ids)
                        logger.debug(f"Is correct: {self.is_correct}, User answers: {set(answer_ids)}, Correct answers: {set(correct_answer_ids)}")
                        
                        # If using answer IDs, update answer object reference
                        if answer_ids and not self.answer_id and answer_ids[0].isdigit():
                            try:
                                self.answer_id = answer_ids[0]
                            except Exception as e:
                                logger.error(f"Error setting answer_id: {e}")
                    except Exception as e:
                        # If there's an error parsing, mark as incorrect
                        logger.error(f"Error processing multiple select: {e}")
                        self.is_correct = False
            
            elif self.question.question_type == 'multi_blank':
                # Try to parse the JSON string from text_answer field
                try:
                    if self.text_answer:
                        if isinstance(self.text_answer, str) and self.text_answer.startswith('['):
                            blank_answers = json.loads(self.text_answer)
                        elif isinstance(self.text_answer, list):
                            blank_answers = self.text_answer
                        else:
                            # If it's comma-separated, split it
                            blank_answers = [ans.strip() for ans in str(self.text_answer).split(',') if ans.strip()]
                    else:
                        blank_answers = []
                    
                    self.is_correct = self.question.check_answer(blank_answers)
                except (json.JSONDecodeError, ValueError):
                    # If parsing fails, mark as incorrect
                    print(f"Error parsing multi_blank answer: {self.text_answer}")
                    self.is_correct = False
                    
            elif self.question.question_type == 'multiple_choice':
                if self.answer:
                    self.is_correct = self.question.check_answer(self.answer.id)
                else:
                    self.is_correct = False
                    
            elif self.question.question_type == 'true_false':
                # Handle true/false questions specifically
                if self.answer:
                    answer_text = self.answer.answer_text.lower().strip()
                elif self.text_answer:
                    answer_text = self.text_answer.lower().strip()
                else:
                    self.is_correct = False
                    return False
                    
                # Check against correct answer
                self.is_correct = self.question.check_answer(answer_text)
            
            elif self.question.question_type == 'matching':
                try:
                    # Ensure matching_answers is in the right format
                    if not self.matching_answers:
                        self.is_correct = False
                    else:
                        # For matching questions, we need to ensure the data is in the right format
                        # Clean up the pairs data: ensure left_item and right_item are present in each pair
                        matching_pairs = []
                        for pair in self.matching_answers:
                            if isinstance(pair, dict) and 'left_item' in pair and 'right_item' in pair:
                                matching_pairs.append({
                                    'left_item': str(pair['left_item']).strip(),
                                    'right_item': str(pair['right_item']).strip()
                                })
                        
                        self.matching_answers = matching_pairs
                        self.is_correct = self.question.check_answer(matching_pairs)
                except Exception as e:
                    print(f"Error checking matching answer: {e}")
                    self.is_correct = False
            
            elif self.question.question_type == 'drag_drop_matching':
                try:
                    # Handle drag drop matching questions
                    if not self.matching_answers:
                        self.is_correct = False
                    else:
                        # Convert matching_answers list to dictionary format expected by check_answer
                        drag_drop_dict = {}
                        for pair in self.matching_answers:
                            if isinstance(pair, dict) and 'left_item' in pair and 'right_item' in pair:
                                drag_drop_dict[str(pair['left_item']).strip()] = str(pair['right_item']).strip()
                        
                        self.is_correct = self.question.check_answer(drag_drop_dict)
                except Exception as e:
                    print(f"Error checking drag drop matching answer: {e}")
                    self.is_correct = False
            
            else:
                self.is_correct = self.question.check_answer(self.text_answer)
                
            if self.is_correct:
                self.points_earned = self.question.points
            else:
                self.points_earned = 0
                
            self.save()
            return self.is_correct
        except Exception as e:
            print(f"Error checking answer: {e}")
            self.is_correct = False
            self.points_earned = 0
            self.save()
            return False

    def get_feedback(self):
        """Get feedback for the answer"""
        if not self.answer:
            return None
        return self.answer.explanation

    def get_selected_options_for_admin(self):
        """Get the user's selected options for multiple select questions for admin display"""
        if self.question.question_type != 'multiple_select':
            return []
            
        try:
            # Handle various formats of stored answers
            if self.answer and not self.text_answer:
                # Single answer reference case
                return [self.answer]
                
            if not self.text_answer:
                return []
                
            # Parse the text_answer field
            answer_ids = []
            if isinstance(self.text_answer, list):
                answer_ids = self.text_answer
            else:
                try:
                    # Try JSON parsing
                    parsed = json.loads(self.text_answer)
                    
                    # Handle nested JSON
                    if isinstance(parsed, list) and len(parsed) == 1 and isinstance(parsed[0], str) and parsed[0].startswith('['):
                        try:
                            inner_json = json.loads(parsed[0])
                            if isinstance(inner_json, list):
                                parsed = inner_json
                        except:
                            pass
                            
                    if isinstance(parsed, list):
                        answer_ids = parsed
                    else:
                        answer_ids = [parsed]
                except json.JSONDecodeError:
                    # Try comma-separated values
                    answer_ids = [id.strip() for id in self.text_answer.split(',') if id.strip()]
            
            # Filter out empty entries and convert to strings
            answer_ids = [str(id) for id in answer_ids if id]
            
            # Get the corresponding Answer objects
            if answer_ids:
                return list(Answer.objects.filter(id__in=answer_ids))
            
            return []
        except Exception as e:
            print(f"Error getting selected options: {e}")
            return []

class QuizTag(models.Model):
    """Model for storing quiz tags for organization"""
    name = models.CharField(max_length=50)
    slug = models.SlugField(unique=True)
    
    class Meta:
        app_label = 'quiz'
        # Use primary key ordering to avoid potential column issues during deletion
        ordering = ['id']
        
    def __str__(self):
        return self.name

class QuizGradeOverride(models.Model):
    """Model for storing quiz grade overrides by instructors"""
    quiz_attempt = models.OneToOneField(QuizAttempt, on_delete=models.CASCADE, related_name='override')
    original_score = models.DecimalField(max_digits=5, decimal_places=2)
    override_score = models.DecimalField(max_digits=5, decimal_places=2)
    override_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='quiz_overrides')
    override_reason = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        app_label = 'quiz'
        ordering = ['-created_at']
        
    def __str__(self):
        return f"Override for {self.quiz_attempt}"

class QuizRubricEvaluation(models.Model):
    """Model for storing quiz rubric evaluations"""
    quiz_attempt = models.ForeignKey(QuizAttempt, on_delete=models.CASCADE, related_name='rubric_evaluations')
    criterion = models.ForeignKey('lms_rubrics.RubricCriterion', on_delete=models.CASCADE, related_name='quiz_evaluations')
    rating = models.ForeignKey('lms_rubrics.RubricRating', on_delete=models.SET_NULL, null=True, blank=True, related_name='quiz_evaluations')
    points = models.FloatField(default=0)
    comments = models.TextField(blank=True)
    evaluated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='quiz_rubric_evaluations')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        app_label = 'quiz'
        unique_together = ['quiz_attempt', 'criterion']
        ordering = ['criterion__position']
    
    def __str__(self):
        return f"Evaluation for {self.quiz_attempt} - {self.criterion}"
        
    def clean(self):
        """Validate evaluation data"""
        if self.points < 0:
            raise ValidationError({'points': 'Points cannot be negative'})
        if self.points > self.criterion.points:
            raise ValidationError({'points': f'Points cannot exceed criterion maximum of {self.criterion.points}'})
        super().clean()
        
    def save(self, *args, **kwargs):
        # Ensure points don't exceed criterion maximum
        if self.points > self.criterion.points:
            self.points = self.criterion.points
        super().save(*args, **kwargs)

