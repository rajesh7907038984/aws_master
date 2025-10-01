from django import forms
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory, modelformset_factory
from django.db import models
from .models import Quiz, Question, Answer, MatchingPair
from lms_rubrics.models import Rubric
from tinymce_editor.widgets import TinyMCEWidget

class QuizForm(forms.ModelForm):
    """Form for creating and editing quizzes"""
    class Meta:
        model = Quiz
        fields = ['title', 'description', 'instructions', 'time_limit', 'passing_score', 'attempts_allowed', 'is_active', 'rubric', 'is_initial_assessment', 'is_vak_test', 'level_2_percentage', 'level_1_percentage', 'below_level_1_percentage', 'total_threshold']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm',
                'placeholder': 'Enter quiz title'
            }),
            'description': TinyMCEWidget(attrs={
                'class': 'block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm tinymce-editor',
                'rows': '4',
                'placeholder': 'Enter quiz description'
            }),
            'instructions': TinyMCEWidget(attrs={
                'class': 'block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm tinymce-editor',
                'rows': '4',
                'placeholder': 'Enter detailed instructions for taking the quiz'
            }),
            'time_limit': forms.NumberInput(attrs={
                'class': 'block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm',
                'min': '0',
                'value': '0'
            }),
            'passing_score': forms.NumberInput(attrs={
                'class': 'block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm',
                'min': '0',
                'max': '100',
                'value': '70'
            }),
            'attempts_allowed': forms.NumberInput(attrs={
                'class': 'block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm',
                'min': '1',
                'value': '1'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500'
            }),
            'rubric': forms.Select(attrs={
                'class': 'block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm'
            }),
            'is_initial_assessment': forms.CheckboxInput(attrs={
                'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500'
            }),
            'is_vak_test': forms.CheckboxInput(attrs={
                'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500'
            }),
            'level_2_percentage': forms.NumberInput(attrs={
                'class': 'block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm',
                'min': '0',
                'max': '100',
                'placeholder': '70'
            }),
            'level_1_percentage': forms.NumberInput(attrs={
                'class': 'block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm',
                'min': '0',
                'max': '100',
                'placeholder': '50'
            }),
            'below_level_1_percentage': forms.NumberInput(attrs={
                'class': 'block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm',
                'min': '0',
                'max': '100',
                'placeholder': '50'
            }),
            'total_threshold': forms.NumberInput(attrs={
                'class': 'block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm',
                'min': '0',
                'max': '100',
                'placeholder': '70'
            })
        }
        
    def __init__(self, *args, **kwargs):
        # Extract custom kwargs before calling super
        user = kwargs.pop('user', None)
        # Remove quiz type restriction parameters as they're no longer needed
        kwargs.pop('has_initial_assessment', None)  # Remove but don't use
        kwargs.pop('has_vak_test', None)  # Remove but don't use
        
        super().__init__(*args, **kwargs)
        
        # Make description required
        self.fields['description'].required = True
        
        # Add help texts
        self.fields['title'].help_text = 'Choose a clear and descriptive title for your quiz'
        self.fields['description'].help_text = 'Provide detailed instructions and context for quiz takers'
        self.fields['instructions'].help_text = 'Detailed step-by-step instructions for students taking the quiz'
        self.fields['time_limit'].help_text = 'Time limit in minutes. Set to 0 for no limit.'
        self.fields['passing_score'].help_text = 'Passing score in percentage (0-100)'
        self.fields['attempts_allowed'].help_text = 'Number of attempts allowed per user. Default is 1.'
        self.fields['is_active'].help_text = 'Active quizzes are visible to students and can be taken'
        self.fields['rubric'].help_text = 'Optional: Select a rubric for additional grading criteria'
        self.fields['is_initial_assessment'].help_text = 'Mark as Initial Assessment (multiple assessments allowed per branch)'
        self.fields['is_vak_test'].help_text = 'Mark as VAK Test (multiple tests allowed per branch)'
        self.fields['level_2_percentage'].help_text = 'Level 2 Minimum % - Percentage threshold for Level 2 (highest level)'
        self.fields['level_1_percentage'].help_text = 'Level 1 Minimum % - Percentage threshold for Level 1 (middle level)'
        self.fields['below_level_1_percentage'].help_text = 'Below Level 1 Minimum % - Percentage threshold for Below Level 1 (lowest level)'
        self.fields['total_threshold'].help_text = 'Overall Performance % - Total percentage threshold for overall performance'
        
        # Note: Quiz type restrictions have been removed - all users can create unlimited assessments
        
        # Filter rubrics based on user role using centralized function
        from lms_rubrics.utils import get_filtered_rubrics_for_user
        
        # Get the course if available
        course = None
        if self.instance and self.instance.course_id:
            course = self.instance.course
        
        # Apply rubric filtering
        filtered_rubrics = get_filtered_rubrics_for_user(user, course)
        
        # For editing existing quiz, always include the currently assigned rubric in the queryset
        # This prevents validation errors when the assigned rubric is no longer in the filtered list
        if self.instance and self.instance.pk and self.instance.rubric:
            # Create a list of rubric IDs to include
            rubric_ids = list(filtered_rubrics.values_list('pk', flat=True))
            if self.instance.rubric.pk not in rubric_ids:
                rubric_ids.append(self.instance.rubric.pk)
            
            # Recreate the queryset with all necessary rubrics
            filtered_rubrics = Rubric.objects.filter(pk__in=rubric_ids).order_by('title')
        
        self.fields['rubric'].queryset = filtered_rubrics
        
    def clean(self):
        """Simplified form validation with better error messages"""
        cleaned_data = super().clean()
        
        # Validate title - more lenient
        title = cleaned_data.get('title')
        if title:
            title = title.strip()
            if len(title) < 2:
                self.add_error('title', 'Please enter a title (at least 2 characters)')
            elif len(title) > 255:
                self.add_error('title', 'Title is too long (maximum 255 characters)')
        
        # Validate description - more lenient
        description = cleaned_data.get('description')
        if description and len(description.strip()) < 5:
            self.add_error('description', 'Please add a brief description (at least 5 characters)')
        
        # Validate time limit
        time_limit = cleaned_data.get('time_limit')
        if time_limit is not None and time_limit < 0:
            self.add_error('time_limit', 'Time limit must be a positive number')
        
        # Simplified passing score validation
        passing_score = cleaned_data.get('passing_score')
        is_vak_test = cleaned_data.get('is_vak_test', False)
        
        # Only validate passing score for regular quizzes
        if not is_vak_test and passing_score is not None:
            if passing_score < 0 or passing_score > 100:
                self.add_error('passing_score', 'Passing score must be between 0 and 100')
        
        # Validate attempts allowed - more lenient
        attempts = cleaned_data.get('attempts_allowed')
        if attempts is not None and attempts < 1:
            self.add_error('attempts_allowed', 'Please allow at least 1 attempt')
        
        # Simplified quiz type validation
        is_initial_assessment = cleaned_data.get('is_initial_assessment', False)
        is_vak_test = cleaned_data.get('is_vak_test', False)
        rubric = cleaned_data.get('rubric')
        
        # Ensure only one quiz type is selected
        if is_initial_assessment and is_vak_test:
            self.add_error('is_initial_assessment', 'A quiz cannot be both Initial Assessment and VAK Test')
            self.add_error('is_vak_test', 'A quiz cannot be both Initial Assessment and VAK Test')
        
        # Prevent rubric selection for Initial Assessment and VAK Test types
        if (is_initial_assessment or is_vak_test) and rubric:
            if is_initial_assessment:
                self.add_error('rubric', 'Initial Assessment quizzes cannot use custom rubrics. They use standardized scoring.')
            if is_vak_test:
                self.add_error('rubric', 'VAK Test quizzes cannot use custom rubrics. They use standardized scoring.')
        
        # Validate percentage configuration for Initial Assessment
        if is_initial_assessment:
            level_2_percentage = cleaned_data.get('level_2_percentage')
            level_1_percentage = cleaned_data.get('level_1_percentage')
            below_level_1_percentage = cleaned_data.get('below_level_1_percentage')
            total_threshold = cleaned_data.get('total_threshold')
            
            # Check if all percentage fields are provided
            if level_2_percentage is None:
                self.add_error('level_2_percentage', 'Level 2 percentage is required for Initial Assessment.')
            if level_1_percentage is None:
                self.add_error('level_1_percentage', 'Level 1 percentage is required for Initial Assessment.')
            if below_level_1_percentage is None:
                self.add_error('below_level_1_percentage', 'Below Level 1 percentage is required for Initial Assessment.')
            if total_threshold is None:
                self.add_error('total_threshold', 'Total threshold percentage is required for Initial Assessment.')
            
            # Validate percentage values and order
            if all(p is not None for p in [level_2_percentage, level_1_percentage, below_level_1_percentage]):
                if not (level_2_percentage > level_1_percentage > below_level_1_percentage):
                    self.add_error('level_2_percentage', 'Level 2 percentage must be higher than Level 1.')
                    self.add_error('level_1_percentage', 'Level 1 percentage must be higher than Below Level 1.')
                    self.add_error('below_level_1_percentage', 'Below Level 1 percentage must be the lowest.')
        
        return cleaned_data

class QuestionForm(forms.ModelForm):
    class Meta:
        model = Question
        fields = ['question_text', 'question_type', 'points', 'order', 'assessment_level']
        widgets = {
            'question_text': forms.Textarea(attrs={
                'class': 'block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm',
                'rows': '6',
                'placeholder': 'Enter your question text',
                'style': 'min-height: 120px; resize: vertical;'
            }),
            'question_type': forms.Select(attrs={
                'class': 'block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm'
            }),
            'points': forms.NumberInput(attrs={
                'class': 'block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm',
                'min': '1',
                'value': '1'
            }),
            'order': forms.NumberInput(attrs={
                'class': 'block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm',
                'min': '0'
            }),

            'assessment_level': forms.Select(attrs={
                'class': 'block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm'
            })
        }
    
    def __init__(self, *args, **kwargs):
        is_edit = kwargs.pop('is_edit', False)
        quiz = kwargs.pop('quiz', None)
        super().__init__(*args, **kwargs)
        
        # Get quiz from instance if not provided
        if not quiz and self.instance and hasattr(self.instance, 'quiz'):
            quiz = self.instance.quiz
        
        # Store quiz as instance attribute for use in clean method
        self.quiz = quiz
        if is_edit:
            self.fields['question_type'].widget.attrs['disabled'] = True
            self.fields['question_type'].widget.attrs['class'] += ' bg-gray-100'
        
        # Add help texts
        self.fields['question_text'].help_text = 'Enter the question text that will be shown to students'
        self.fields['question_type'].help_text = 'Select the type of question'
        self.fields['points'].help_text = 'Number of points awarded for correct answer'
        self.fields['order'].help_text = 'Order in which this question appears in the quiz'

        self.fields['assessment_level'].help_text = 'Select the assessment level for Initial Assessment questions'
        
        # Make all fields required except order and assessment_level
        self.fields['order'].required = False
        self.fields['assessment_level'].required = False
        
        # Handle VAK tests - points are not used for scoring
        if quiz and quiz.is_vak_test:
            self.fields['points'].required = False
            self.fields['points'].initial = 1  # Set default value
            self.fields['points'].help_text = 'VAK tests do not use point-based scoring'
        
        # Update question type choices based on quiz type
        if quiz and quiz.is_vak_test:
            # For VAK tests, only allow multiple choice (no correct/incorrect answers)
            self.fields['question_type'].choices = [
                ('multiple_choice', 'Multiple Choice - Select your preferred option'),
            ]
            self.fields['question_type'].help_text = 'VAK tests only support Multiple Choice questions for learning style assessment'
        else:
            # For regular quizzes, show all question types
            self.fields['question_type'].choices = [
                ('multiple_choice', 'Multiple Choice - Select one correct answer'),
                ('multiple_select', 'Multiple Select - Select all correct answers'),
                ('true_false', 'True/False - Choose between true or false'),
                ('fill_blank', 'Fill in the Blank - Enter the exact answer'),
                ('multi_blank', 'Multiple Blanks - Enter multiple answers'),
                ('matching', 'Matching - Match items using dropdowns'),
                ('drag_drop_matching', 'Drag & Drop Matching - Drag items to match')
            ]

    def clean_points(self):
        points = self.cleaned_data.get('points')
        
        # For VAK tests, points are not used for scoring, so set default value
        if self.quiz and self.quiz.is_vak_test:
            return 1  # Set default value for VAK tests
        
        if points < 1:
            raise ValidationError("Points must be at least 1")
        return points

    def clean_order(self):
        order = self.cleaned_data.get('order')
        quiz = self.instance.quiz if self.instance.pk else None
        
        if quiz and order is not None:
            # Check for duplicate order
            existing_question = Question.objects.filter(
                quiz=quiz,
                order=order
            ).exclude(pk=self.instance.pk).first()
            
            if existing_question:
                raise ValidationError(f"Question order {order} is already taken")
        
        return order

    def clean(self):
        """Simplified validation with clearer error messages"""
        cleaned_data = super().clean()
        question_type = cleaned_data.get('question_type')
        question_text = cleaned_data.get('question_text')
        
        # Basic validation for question text
        if not question_text or len(question_text.strip()) < 5:
            raise ValidationError("Please enter a question (at least 5 characters)")
        
        # Check VAK test constraints
        quiz = self.quiz
        if quiz and quiz.is_vak_test and question_type != 'multiple_choice':
            raise ValidationError("VAK learning style tests can only use multiple choice questions")
        
        # Validate multiple choice and multiple select questions
        if question_type in ['multiple_choice', 'multiple_select']:
            options = self.data.getlist('options[]')
            
            if not options or len([opt for opt in options if opt.strip()]) < 2:
                raise ValidationError("Please provide at least 2 answer options")
            
            # VAK test specific validation
            is_vak_test = quiz and quiz.is_vak_test
            if is_vak_test:
                learning_styles = self.data.getlist('learning_styles[]')
                if not learning_styles or len(learning_styles) < len(options):
                    raise ValidationError("Each answer option needs a learning style (Visual, Auditory, or Kinesthetic)")
                
                # Validate learning styles are valid
                valid_styles = ['visual', 'auditory', 'kinesthetic']
                for i, style in enumerate(learning_styles):
                    if style and style not in valid_styles:
                        raise ValidationError(f"Invalid learning style for option {i+1}. Choose Visual, Auditory, or Kinesthetic")
            else:
                # Regular quiz validation - simplified
                # Check for both correct_answers[] (multiple select) and correct_answer (single choice)
                correct_answers = self.data.getlist('correct_answers[]')
                correct_answer = self.data.get('correct_answer')
                
                # For multiple choice, check correct_answers[] (single value from radio buttons)
                if question_type == 'multiple_choice':
                    if not any(correct_answers):
                        raise ValidationError("Please mark at least one answer as correct")
                # For multiple select, check correct_answers[] (multiple values)
                elif question_type == 'multiple_select':
                    if not any(correct_answers):
                        raise ValidationError("Please mark at least one answer as correct")
        
        elif question_type == 'true_false':
            correct_answer = self.data.get('correct_answer')
            if not correct_answer:
                raise ValidationError("Please select the correct answer (True or False)")
        
        elif question_type == 'fill_blank':
            blank_answer = self.data.get('blank_answer', '').strip()
            if not blank_answer:
                raise ValidationError("Please enter the correct answer for this fill-in-the-blank question")
        
        elif question_type == 'multi_blank':
            multi_blank_answers = self.data.getlist('multi_blank_answers[]')
            if not multi_blank_answers or not any(answer.strip() for answer in multi_blank_answers):
                raise ValidationError("At least one answer is required for multiple blanks questions")
        
        elif question_type == 'matching':
            left_items = self.data.getlist('matching_left[]')
            right_items = self.data.getlist('matching_right[]')
            
            if not left_items or not right_items:
                raise ValidationError("At least one matching pair is required")
            
            if len(left_items) != len(right_items):
                raise ValidationError("Each left item must have a corresponding right item")
            
            if not all(left.strip() for left in left_items) or not all(right.strip() for right in right_items):
                raise ValidationError("All matching items must have non-empty values")
        
        return cleaned_data 

# Create formsets
AnswerFormSet = inlineformset_factory(
    Question, 
    Answer, 
    fields=['answer_text', 'is_correct'], 
    extra=4
)

MatchingPairFormSet = inlineformset_factory(
    Question, 
    MatchingPair, 
    fields=['left_item', 'right_item'], 
    extra=4
)

class MultipleChoiceQuestionForm(forms.ModelForm):
    class Meta:
        model = Question
        fields = ['question_text', 'points']
        widgets = {
            'question_text': forms.Textarea(attrs={
                'class': 'block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm',
                'rows': '6',
                'placeholder': 'Enter your question text',
                'style': 'min-height: 120px; resize: vertical;'
            }),
        }

class TrueFalseQuestionForm(forms.ModelForm):
    class Meta:
        model = Question
        fields = ['question_text', 'points']
        widgets = {
            'question_text': forms.Textarea(attrs={
                'class': 'block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm',
                'rows': '6',
                'placeholder': 'Enter your question text',
                'style': 'min-height: 120px; resize: vertical;'
            }),
        }

class FillBlankQuestionForm(forms.ModelForm):
    class Meta:
        model = Question
        fields = ['question_text', 'points']
        widgets = {
            'question_text': forms.Textarea(attrs={
                'class': 'block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm',
                'rows': '6',
                'placeholder': 'Enter your question text',
                'style': 'min-height: 120px; resize: vertical;'
            }),
        }

class MultiBlankQuestionForm(forms.ModelForm):
    class Meta:
        model = Question
        fields = ['question_text', 'points']
        widgets = {
            'question_text': forms.Textarea(attrs={
                'class': 'block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm',
                'rows': '6',
                'placeholder': 'Enter your question text',
                'style': 'min-height: 120px; resize: vertical;'
            }),
        }

class MatchingQuestionForm(forms.ModelForm):
    class Meta:
        model = Question
        fields = ['question_text', 'points']
        widgets = {
            'question_text': forms.Textarea(attrs={
                'class': 'block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm',
                'rows': '6',
                'placeholder': 'Enter your question text',
                'style': 'min-height: 120px; resize: vertical;'
            }),
        }

class MultipleSelectQuestionForm(forms.ModelForm):
    class Meta:
        model = Question
        fields = ['question_text', 'points']
        widgets = {
            'question_text': forms.Textarea(attrs={
                'class': 'block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm',
                'rows': '6',
                'placeholder': 'Enter your question text',
                'style': 'min-height: 120px; resize: vertical;'
            }),
        }



class QuizGradeFilterForm(forms.Form):
    student = forms.CharField(required=False)
    date_from = forms.DateField(required=False)
    date_to = forms.DateField(required=False) 