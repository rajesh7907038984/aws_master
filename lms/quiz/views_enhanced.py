"""
Enhanced Quiz Management Views with Comprehensive Error Handling
This file contains upgraded versions of critical quiz management views
"""

import json
import logging
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponseForbidden
from django.views.generic.edit import CreateView, UpdateView
from django.views.decorators.http import require_POST
from django.db import transaction, IntegrityError
from django.utils import timezone
from django.core.exceptions import ValidationError

from core.mixins.enhanced_view_mixins import RobustAtomicViewMixin, BaseErrorHandlingMixin
from .models import Quiz, Question, QuizAttempt, Answer
from .forms import QuizForm

logger = logging.getLogger(__name__)


class EnhancedQuizCreateView(RobustAtomicViewMixin, CreateView):
    """
    Enhanced quiz creation view with comprehensive error handling
    """
    model = Quiz
    form_class = QuizForm
    template_name = 'quiz/quiz_form.html'
    
    def form_valid(self, form):
        """Enhanced quiz creation with better error handling"""
        try:
            with transaction.atomic():
                # Set the creator
                form.instance.created_by = self.request.user
                
                # Validate permissions
                if not self.can_create_quiz():
                    form.add_error(None, "You don't have permission to create quizzes.")
                    return self.form_invalid(form)
                
                # Additional validation
                self.validate_quiz_data(form)
                
                # Save the quiz
                quiz = form.save()
                
                # Log successful quiz creation
                logger.info(f"Quiz created successfully: {quiz.title} by {self.request.user.username}")
                
                success_msg = "Quiz created successfully!"
                
                if self.is_ajax_request(self.request):
                    return JsonResponse({
                        'success': True,
                        'message': success_msg,
                        'redirect_url': '/quiz/',
                        'quiz_id': quiz.id
                    })
                
                messages.success(self.request, success_msg)
                return redirect('quiz:quiz_list')
                
        except ValidationError as e:
            logger.warning(f"Quiz validation error: {str(e)}")
            self.handle_validation_errors(form, e)
            return self.form_invalid(form)
        
        except IntegrityError as e:
            logger.error(f"Quiz creation integrity error: {str(e)}")
            form.add_error(None, "A quiz with similar information already exists.")
            return self.form_invalid(form)
        
        except Exception as e:
            logger.error(f"Unexpected error creating quiz: {str(e)}", exc_info=True)
            form.add_error(None, "An unexpected error occurred. Please try again.")
            return self.form_invalid(form)
    
    def validate_quiz_data(self, form):
        """Additional quiz validation"""
        time_limit = form.cleaned_data.get('time_limit')
        passing_score = form.cleaned_data.get('passing_score')
        attempts_allowed = form.cleaned_data.get('attempts_allowed')
        
        if time_limit and time_limit < 0:
            raise ValidationError("Time limit cannot be negative.")
        
        if passing_score and (passing_score < 0 or passing_score > 100):
            raise ValidationError("Passing score must be between 0 and 100.")
        
        if attempts_allowed and attempts_allowed < 1:
            raise ValidationError("Attempts allowed must be at least 1.")
    
    def handle_validation_errors(self, form, validation_error):
        """Handle ValidationError objects properly"""
        if hasattr(validation_error, 'message_dict'):
            for field, messages_list in validation_error.message_dict.items():
                for message in messages_list:
                    if field == '__all__':
                        form.add_error(None, message)
                    else:
                        form.add_error(field, message)
        else:
            form.add_error(None, str(validation_error))
    
    def can_create_quiz(self):
        """Check if user can create quizzes"""
        return (
            self.request.user.role in ['instructor', 'admin', 'superadmin', 'globaladmin'] or 
            self.request.user.is_superuser
        )
    
    def form_invalid(self, form):
        """Enhanced form invalid handling"""
        if self.is_ajax_request(self.request):
            return JsonResponse({
                'success': False,
                'errors': form.errors,
                'error_type': 'form_validation'
            }, status=400)
        
        return super().form_invalid(form)


class EnhancedQuizUpdateView(RobustAtomicViewMixin, UpdateView):
    """
    Enhanced quiz update view with comprehensive error handling
    """
    model = Quiz
    form_class = QuizForm
    template_name = 'quiz/quiz_form.html'
    pk_url_kwarg = 'quiz_id'
    
    def form_valid(self, form):
        """Enhanced quiz update with better error handling"""
        try:
            with transaction.atomic():
                # Validate permissions
                if not self.can_edit_quiz():
                    form.add_error(None, "You don't have permission to edit this quiz.")
                    return self.form_invalid(form)
                
                # Check if quiz has attempts and warn about changes
                if self.object.attempts.exists():
                    self.handle_quiz_with_attempts(form)
                
                # Save the quiz
                quiz = form.save()
                
                # Log successful quiz update
                logger.info(f"Quiz updated successfully: {quiz.title} by {self.request.user.username}")
                
                success_msg = "Quiz updated successfully!"
                
                if self.is_ajax_request(self.request):
                    return JsonResponse({
                        'success': True,
                        'message': success_msg,
                        'quiz_id': quiz.id
                    })
                
                messages.success(self.request, success_msg)
                return redirect('quiz:quiz_list')
                
        except ValidationError as e:
            logger.warning(f"Quiz update validation error: {str(e)}")
            form.add_error(None, str(e))
            return self.form_invalid(form)
        
        except Exception as e:
            logger.error(f"Error updating quiz {self.object.id}: {str(e)}", exc_info=True)
            form.add_error(None, "An error occurred while updating the quiz. Please try again.")
            return self.form_invalid(form)
    
    def handle_quiz_with_attempts(self, form):
        """Handle updates to quiz with existing attempts"""
        # Add warning message
        messages.warning(
            self.request, 
            "This quiz has existing attempts. Changes may affect scoring consistency."
        )
        
        # Log the modification
        logger.info(f"Quiz {self.object.id} with attempts modified by {self.request.user.username}")
    
    def can_edit_quiz(self):
        """Check if user can edit this quiz"""
        if self.request.user.is_superuser:
            return True
        
        if self.request.user.role == 'globaladmin':
            return True
        
        if self.request.user.role == 'superadmin':
            return self.object.created_by.business == self.request.user.business
        
        if self.request.user.role in ['admin', 'instructor']:
            return (
                self.object.created_by == self.request.user or
                self.object.created_by.branch == self.request.user.branch
            )
        
        return False


@login_required
@require_POST
def enhanced_submit_quiz(request, attempt_id):
    """
    Enhanced quiz submission with comprehensive error handling
    """
    attempt = get_object_or_404(QuizAttempt, id=attempt_id)
    quiz = attempt.quiz
    
    # Validate permissions
    if attempt.user != request.user:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False,
                'error': 'You can only submit your own quiz attempts.',
                'error_type': 'permission_denied'
            }, status=403)
        
        messages.error(request, 'You can only submit your own quiz attempts.')
        return redirect('quiz:quiz_list')
    
    # Check if attempt is already completed
    if attempt.is_completed:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False,
                'error': 'This quiz attempt has already been completed.',
                'error_type': 'attempt_completed'
            }, status=400)
        
        messages.error(request, 'This quiz attempt has already been completed.')
        return redirect('quiz:quiz_view', quiz_id=quiz.id)
    
    try:
        with transaction.atomic():
            # Update last activity
            attempt.update_last_activity()
            
            # Process answers with comprehensive error handling
            processed_questions, total_score = process_quiz_answers(request, attempt)
            
            # Complete the attempt
            attempt.end_time = timezone.now()
            attempt.is_completed = True
            attempt.score = total_score
            attempt.save()
            
            # Clean up session marker for completed attempt
            session_key = f'active_quiz_attempt_{attempt.id}'
            if session_key in request.session:
                del request.session[session_key]
            
            # Determine pass/fail status
            passing_score = quiz.passing_score or 70
            passed = total_score >= passing_score
            
            # Log quiz completion
            logger.info(f"Quiz completed: {quiz.title} by {request.user.username}, Score: {total_score}%")
            
            success_msg = f'Quiz submitted successfully! Your score: {total_score:.1f}%'
            if passed:
                success_msg += ' - Congratulations, you passed!'
            else:
                success_msg += f' - You need {passing_score}% to pass.'
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'message': success_msg,
                    'score': total_score,
                    'passed': passed,
                    'redirect_url': f'/quiz/{quiz.id}/results/{attempt.id}/'
                })
            
            messages.success(request, success_msg)
            return redirect('quiz:quiz_results', quiz_id=quiz.id, attempt_id=attempt.id)
            
    except Exception as e:
        logger.error(f"Error submitting quiz attempt {attempt_id}: {str(e)}", exc_info=True)
        
        error_msg = 'An error occurred while submitting your quiz. Please try again.'
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False,
                'error': error_msg,
                'error_type': 'submission_error'
            }, status=500)
        
        messages.error(request, error_msg)
        return redirect('quiz:quiz_attempt', attempt_id=attempt.id)


def process_quiz_answers(request, attempt):
    """
    Process quiz answers with comprehensive error handling
    Returns: (processed_questions_count, total_score_percentage)
    """
    quiz = attempt.quiz
    questions = Question.objects.filter(quiz=quiz)
    processed_questions = set()
    total_score = 0
    max_possible_score = questions.count()
    
    if max_possible_score == 0:
        logger.warning(f"Quiz {quiz.id} has no questions")
        return 0, 0
    
    # Track multi-blank questions
    multi_blank_answers = {}
    
    try:
        # First pass - collect all answers
        for key, value in request.POST.items():
                continue
                
            if key.startswith('question_') and not key.endswith('_is_multiple'):
                parts = key.split('_')
                if len(parts) < 2:
                    continue
                    
                try:
                    question_id = int(parts[1])
                except (ValueError, IndexError):
                    logger.warning(f"Invalid question ID in form field: {key}")
                    continue
                
                # Handle multi-blank questions
                if len(parts) > 2 and parts[2].isdigit():
                    blank_index = int(parts[2])
                    if question_id not in multi_blank_answers:
                        multi_blank_answers[question_id] = {}
                    multi_blank_answers[question_id][blank_index] = value
                    processed_questions.add(key)
        
        # Process multi-blank questions
        for question_id, answers in multi_blank_answers.items():
            try:
                question = questions.get(id=question_id)
                if process_multi_blank_question(attempt, question, answers):
                    total_score += 1
            except Question.DoesNotExist:
                logger.warning(f"Question {question_id} not found in quiz {quiz.id}")
                continue
            except Exception as e:
                logger.error(f"Error processing multi-blank question {question_id}: {str(e)}")
                continue
        
        # Process regular questions
        for key, value in request.POST.items():
                continue
                
            if key.startswith('question_'):
                parts = key.split('_')
                if len(parts) != 2:
                    continue
                    
                try:
                    question_id = int(parts[1])
                    question = questions.get(id=question_id)
                except (ValueError, Question.DoesNotExist):
                    logger.warning(f"Invalid question {question_id} in quiz {quiz.id}")
                    continue
                
                try:
                    if process_single_question(attempt, question, key, value, request.POST):
                        total_score += 1
                except Exception as e:
                    logger.error(f"Error processing question {question_id}: {str(e)}")
                    continue
        
        # Calculate percentage
        score_percentage = (total_score / max_possible_score) * 100 if max_possible_score > 0 else 0
        
        return len(processed_questions), score_percentage
        
    except Exception as e:
        logger.error(f"Error processing quiz answers for attempt {attempt.id}: {str(e)}")
        return 0, 0


def process_multi_blank_question(attempt, question, answers):
    """Process multi-blank fill-in questions"""
    try:
        # Get correct answers
        correct_answers = question.get_correct_multi_blank_answers()
        if not correct_answers:
            return False
        
        # Check each blank
        all_correct = True
        for blank_index, user_answer in answers.items():
            if blank_index >= len(correct_answers):
                continue
                
            expected = correct_answers[blank_index].strip().lower()
            provided = user_answer.strip().lower()
            
            if expected != provided:
                all_correct = False
                break
        
        # Save answer
        Answer.objects.create(
            attempt=attempt,
            question=question,
            answer_text=json.dumps(answers),
            is_correct=all_correct
        )
        
        return all_correct
        
    except Exception as e:
        logger.error(f"Error processing multi-blank question {question.id}: {str(e)}")
        return False


def process_single_question(attempt, question, key, value, post_data):
    """Process single answer questions"""
    try:
        question_type = question.question_type
        is_correct = False
        
        if question_type == 'multiple_choice':
            # Single choice question
            try:
                selected_choice = int(value)
                correct_choice = question.get_correct_choice()
                is_correct = (selected_choice == correct_choice.id if correct_choice else False)
            except (ValueError, AttributeError):
                is_correct = False
        
        elif question_type == 'multiple_select':
            # Multiple selection question
            is_multiple_key = f"{key}_is_multiple"
            if is_multiple_key in post_data:
                selected_choices = post_data.getlist(key)
                correct_choices = [str(choice.id) for choice in question.get_correct_choices()]
                is_correct = set(selected_choices) == set(correct_choices)
        
        elif question_type == 'true_false':
            # True/False question
            correct_answer = question.get_correct_answer()
            is_correct = (value.lower() == correct_answer.lower() if correct_answer else False)
        
        elif question_type == 'fill_blank':
            # Single fill in the blank
            correct_answer = question.get_correct_answer()
            is_correct = (value.strip().lower() == correct_answer.strip().lower() if correct_answer else False)
        
        # Save answer
        Answer.objects.create(
            attempt=attempt,
            question=question,
            answer_text=value,
            is_correct=is_correct
        )
        
        return is_correct
        
    except Exception as e:
        logger.error(f"Error processing single question {question.id}: {str(e)}")
        return False
