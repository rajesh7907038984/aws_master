"""
Base Enhanced Mixins
Consolidates common patterns from enhanced views to eliminate duplication
"""

import json
import logging
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.http import require_POST
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.urls import reverse_lazy

from core.permissions import PermissionMixin, PermissionManager
from core.mixins.enhanced_view_mixins import RobustAtomicViewMixin, BaseErrorHandlingMixin

logger = logging.getLogger(__name__)


class BaseEnhancedViewMixin(PermissionMixin, RobustAtomicViewMixin, BaseErrorHandlingMixin):
    """
    Base mixin for all enhanced views
    Provides common functionality for error handling, permissions, and AJAX responses
    """
    
    def get_success_message(self):
        """Override in subclasses to provide custom success messages"""
        return f"{self.model.__name__} operation completed successfully."
    
    def get_error_message(self):
        """Override in subclasses to provide custom error messages"""
        return "An error occurred. Please try again."
    
    def get_redirect_url(self):
        """Override in subclasses to provide custom redirect URLs"""
        return reverse_lazy(f"{self.model._meta.app_label}:{self.model._meta.model_name}_list")
    
    def form_valid(self, form):
        """Enhanced form validation with comprehensive error handling"""
        try:
            with transaction.atomic():
                # Set common fields
                if hasattr(form.instance, 'created_by') and not form.instance.pk:
                    form.instance.created_by = self.request.user
                if hasattr(form.instance, 'updated_by'):
                    form.instance.updated_by = self.request.user
                
                # Save the instance
                instance = form.save()
                
                # Log successful operation
                logger.info(f"{self.model.__name__} {instance.pk} saved by {self.request.user.username}")
                
                success_msg = self.get_success_message()
                
                if self.is_ajax_request(self.request):
                    return JsonResponse({
                        'success': True,
                        'message': success_msg,
                        'redirect_url': self.get_redirect_url(),
                        'object_id': instance.pk
                    })
                
                messages.success(self.request, success_msg)
                return redirect(self.get_redirect_url())
                
        except ValidationError as e:
            logger.warning(f"{self.model.__name__} validation error: {str(e)}")
            self.handle_validation_errors(form, e)
            return self.form_invalid(form)
        
        except Exception as e:
            logger.error(f"Error saving {self.model.__name__}: {str(e)}", exc_info=True)
            form.add_error(None, self.get_error_message())
            return self.form_invalid(form)
    
    def form_invalid(self, form):
        """Enhanced form invalid handling"""
        if self.is_ajax_request(self.request):
            return JsonResponse({
                'success': False,
                'errors': form.errors,
                'error_type': 'form_validation'
            }, status=400)
        
        return super().form_invalid(form)
    
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


class CourseManagementMixin(BaseEnhancedViewMixin):
    """
    Mixin for course-related views
    Provides course-specific permission checking and functionality
    """
    
    def get_success_message(self):
        """Course-specific success message"""
        if hasattr(self, 'object') and self.object:
            return f'Course "{self.object.title}" {self.get_action_verb()} successfully!'
        return "Course operation completed successfully."
    
    def get_action_verb(self):
        """Get the action verb for the current operation"""
        if isinstance(self, CreateView):
            return "created"
        elif isinstance(self, UpdateView):
            return "updated"
        elif isinstance(self, DeleteView):
            return "deleted"
        return "processed"
    
    def get_redirect_url(self):
        """Course-specific redirect URL"""
        if hasattr(self, 'object') and self.object:
            return f'/courses/{self.object.id}/'
        return reverse_lazy('courses:course_list')
    
    def can_create_course(self):
        """Check if user can create courses"""
        return PermissionManager.can_create_course(self.request.user)
    
    def can_edit_course(self):
        """Check if user can edit this course"""
        if hasattr(self, 'object') and self.object:
            return PermissionManager.can_edit_course(self.request.user, self.object)
        return False
    
    def can_delete_course(self):
        """Check if user can delete this course"""
        if hasattr(self, 'object') and self.object:
            return PermissionManager.can_delete_course(self.request.user, self.object)
        return False


class QuizManagementMixin(BaseEnhancedViewMixin):
    """
    Mixin for quiz-related views
    Provides quiz-specific permission checking and functionality
    """
    
    def get_success_message(self):
        """Quiz-specific success message"""
        if hasattr(self, 'object') and self.object:
            return f'Quiz "{self.object.title}" {self.get_action_verb()} successfully!'
        return "Quiz operation completed successfully."
    
    def get_action_verb(self):
        """Get the action verb for the current operation"""
        if isinstance(self, CreateView):
            return "created"
        elif isinstance(self, UpdateView):
            return "updated"
        elif isinstance(self, DeleteView):
            return "deleted"
        return "processed"
    
    def get_redirect_url(self):
        """Quiz-specific redirect URL"""
        return reverse_lazy('quiz:quiz_list')
    
    def can_create_quiz(self):
        """Check if user can create quizzes"""
        return PermissionManager.can_create_quiz(self.request.user)
    
    def can_edit_quiz(self):
        """Check if user can edit this quiz"""
        if hasattr(self, 'object') and self.object:
            return PermissionManager.can_edit_quiz(self.request.user, self.object)
        return False
    
    def can_delete_quiz(self):
        """Check if user can delete this quiz"""
        if hasattr(self, 'object') and self.object:
            return PermissionManager.can_edit_quiz(self.request.user, self.object)
        return False


class AssignmentManagementMixin(BaseEnhancedViewMixin):
    """
    Mixin for assignment-related views
    Provides assignment-specific permission checking and functionality
    """
    
    def get_success_message(self):
        """Assignment-specific success message"""
        if hasattr(self, 'object') and self.object:
            return f'Assignment "{self.object.title}" {self.get_action_verb()} successfully!'
        return "Assignment operation completed successfully."
    
    def get_action_verb(self):
        """Get the action verb for the current operation"""
        if isinstance(self, CreateView):
            return "created"
        elif isinstance(self, UpdateView):
            return "updated"
        elif isinstance(self, DeleteView):
            return "deleted"
        return "processed"
    
    def get_redirect_url(self):
        """Assignment-specific redirect URL"""
        if hasattr(self, 'object') and self.object:
            return f'/assignments/{self.object.id}/'
        return reverse_lazy('assignments:assignment_list')
    
    def can_grade_submission(self):
        """Check if user can grade submissions"""
        return PermissionManager.can_grade_submission(self.request.user)


class GradingMixin(BaseEnhancedViewMixin):
    """
    Mixin for grading-related views
    Provides grading-specific functionality
    """
    
    def get_success_message(self):
        """Grading-specific success message"""
        return "Grading completed successfully."
    
    def get_redirect_url(self):
        """Grading-specific redirect URL"""
        if hasattr(self, 'object') and self.object:
            return f'/assignments/{self.object.assignment.id}/'
        return reverse_lazy('assignments:assignment_list')
    
    def can_grade_submission(self):
        """Check if user can grade this submission"""
        return PermissionManager.can_grade_submission(self.request.user)
    
    def process_grading_data(self, form):
        """Process grading form data with error handling"""
        try:
            with transaction.atomic():
                # Process basic grading fields
                grade = form.cleaned_data.get('grade')
                feedback = form.cleaned_data.get('feedback')
                audio_feedback = form.cleaned_data.get('audio_feedback')
                video_feedback = form.cleaned_data.get('video_feedback')
                is_private = form.cleaned_data.get('is_private', False)
                
                # Update submission
                if grade is not None:
                    self.object.grade = grade
                
                self.object.graded_by = self.request.user
                self.object.graded_at = timezone.now()
                self.object.status = 'graded'
                self.object.save()
                
                # Process feedback
                if feedback or audio_feedback or video_feedback:
                    self.create_or_update_feedback(feedback, audio_feedback, video_feedback, is_private)
                
                # Process rubric evaluations
                if hasattr(self.object, 'assignment') and self.object.assignment.rubric:
                    self.process_rubric_evaluations()
                
                return True
                
        except Exception as e:
            logger.error(f"Error processing grading data: {str(e)}", exc_info=True)
            return False
    
    def create_or_update_feedback(self, feedback, audio_feedback, video_feedback, is_private):
        """Create or update feedback for submission"""
        try:
            from assignments.models import AssignmentFeedback
            
            feedback_obj, created = AssignmentFeedback.objects.get_or_create(
                submission=self.object,
                defaults={
                    'feedback_text': feedback,
                    'audio_feedback': audio_feedback,
                    'video_feedback': video_feedback,
                    'is_private': is_private,
                    'created_by': self.request.user
                }
            )
            
            if not created:
                feedback_obj.feedback_text = feedback
                feedback_obj.audio_feedback = audio_feedback
                feedback_obj.video_feedback = video_feedback
                feedback_obj.is_private = is_private
                feedback_obj.updated_by = self.request.user
                feedback_obj.updated_at = timezone.now()
                feedback_obj.save()
                
        except Exception as e:
            logger.error(f"Error creating/updating feedback: {str(e)}")
    
    def process_rubric_evaluations(self):
        """Process rubric evaluations with error handling"""
        try:
            from assignments.models import RubricEvaluation
            
            rubric_data_raw = self.request.POST.get('rubric_data', '{}')
            if rubric_data_raw:
                rubric_data = json.loads(rubric_data_raw)
                
                for criterion_id, evaluation in rubric_data.items():
                    try:
                        points = float(evaluation.get('points', 0))
                        rating_id = evaluation.get('rating_id')
                        comments = evaluation.get('comments', '')
                        
                        # Get or create evaluation
                        rubric_eval, created = RubricEvaluation.objects.get_or_create(
                            submission=self.object,
                            criterion_id=criterion_id,
                            defaults={
                                'points': points,
                                'rating_id': rating_id,
                                'comments': comments,
                                'evaluated_by': self.request.user
                            }
                        )
                        
                        if not created:
                            rubric_eval.points = points
                            rubric_eval.rating_id = rating_id
                            rubric_eval.comments = comments
                            rubric_eval.evaluated_by = self.request.user
                            rubric_eval.save()
                            
                    except (ValueError, KeyError) as e:
                        logger.warning(f"Error processing rubric evaluation for criterion {criterion_id}: {str(e)}")
                        continue
                        
        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"Error processing rubric evaluations: {str(e)}")


class SubmissionMixin(BaseEnhancedViewMixin):
    """
    Mixin for submission-related views
    Provides submission-specific functionality
    """
    
    def get_success_message(self):
        """Submission-specific success message"""
        return "Submission completed successfully."
    
    def get_redirect_url(self):
        """Submission-specific redirect URL"""
        if hasattr(self, 'object') and self.object:
            return f'/assignments/{self.object.assignment.id}/'
        return reverse_lazy('assignments:assignment_list')
    
    def can_submit_assignment(self, assignment):
        """Check if user can submit to this assignment"""
        if not assignment.is_available_for_user(self.request.user):
            return False
        
        # Check if student can edit this submission
        if self.request.user.role == 'learner':
            if hasattr(self, 'object') and self.object:
                return self.object.can_be_edited_by_student()
        
        return True
    
    def process_submission_data(self, assignment, form_data, files):
        """Process submission data with error handling"""
        try:
            with transaction.atomic():
                # Get or create submission
                submission, created = self.get_or_create_submission(assignment)
                
                # Validate submission content
                if not self.validate_submission_content(files, form_data):
                    return False, "Please provide either a file or text submission."
                
                # Update submission
                self.update_submission(submission, files, form_data)
                
                # Process text questions if any
                self.process_text_questions(assignment, submission, form_data)
                
                return True, "Submission completed successfully."
                
        except Exception as e:
            logger.error(f"Error processing submission: {str(e)}", exc_info=True)
            return False, "An error occurred while submitting. Please try again."
    
    def get_or_create_submission(self, assignment):
        """Get or create submission for assignment"""
        from assignments.models import AssignmentSubmission
        
        submission, created = AssignmentSubmission.objects.get_or_create(
            assignment=assignment,
            user=self.request.user,
            defaults={'status': 'draft'}
        )
        
        return submission, created
    
    def validate_submission_content(self, files, form_data):
        """Validate that submission has content"""
        uploaded_file = files.get('submission_file')
        submission_text = form_data.get('submission_text', '').strip()
        
        return bool(uploaded_file or submission_text)
    
    def update_submission(self, submission, files, form_data):
        """Update submission with new data"""
        uploaded_file = files.get('submission_file')
        submission_text = form_data.get('submission_text', '').strip()
        
        if uploaded_file:
            submission.submission_file = uploaded_file
        if submission_text:
            submission.submission_text = submission_text
        
        submission.status = 'submitted'
        submission.submitted_at = timezone.now()
        submission.save()
    
    def process_text_questions(self, assignment, submission, form_data):
        """Process text questions with error handling"""
        try:
            from assignments.models import TextQuestion, create_or_get_latest_iteration
            
            text_questions = TextQuestion.objects.filter(assignment=assignment)
            for question in text_questions:
                question_name = f'text_question_{question.id}'
                if question_name in form_data:
                    answer_content = form_data.get(question_name, '').strip()
                    
                    if answer_content:
                        iteration, created = create_or_get_latest_iteration(question, submission, 'question')
                        if iteration:
                            iteration.answer_text = answer_content
                            iteration.is_submitted = True
                            iteration.submitted_at = timezone.now()
                            iteration.save()
        except Exception as e:
            logger.error(f"Error processing text questions: {str(e)}")
