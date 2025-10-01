"""
Enhanced Assignment Views with Comprehensive Error Handling
This file contains upgraded versions of critical assignment views
"""

import json
import logging
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.http import require_POST
from django.views.generic.edit import UpdateView
from django.db import transaction
from django.utils import timezone

from core.mixins.enhanced_view_mixins import GradingViewMixin, RobustAtomicViewMixin
from .models import Assignment, AssignmentSubmission, AssignmentFeedback, RubricEvaluation
from .forms import AssignmentGradingForm

logger = logging.getLogger(__name__)


class EnhancedGradeSubmissionView(GradingViewMixin, UpdateView):
    """
    Enhanced assignment grading view with comprehensive error handling
    Replaces the original grade_submission function-based view
    """
    model = AssignmentSubmission
    form_class = AssignmentGradingForm
    template_name = 'assignments/grade_submission.html'
    context_object_name = 'submission'
    
    def get_object(self):
        """Get the submission and ensure it's the latest"""
        submission_id = self.kwargs.get('submission_id')
        submission = get_object_or_404(AssignmentSubmission, id=submission_id)
        
        # Get the latest submission for this assignment and user
        latest_submission = (
            AssignmentSubmission.objects
            .filter(assignment=submission.assignment, user=submission.user)
            .order_by('-submitted_at', '-id')
            .first()
        )
        
        # If this isn't the latest submission, we'll redirect in get()
        if latest_submission and latest_submission.id != submission.id:
            self.latest_submission_id = latest_submission.id
        else:
            self.latest_submission_id = None
            
        return submission
    
    def get(self, request, *args, **kwargs):
        """Handle GET request with proper redirection for latest submission"""
        self.object = self.get_object()
        
        # Redirect to latest submission if needed
        if hasattr(self, 'latest_submission_id') and self.latest_submission_id:
            return redirect('assignments:grade_submission', submission_id=self.latest_submission_id)
        
        # Check permissions
        if not self.has_grading_permission():
            messages.error(request, "You don't have permission to grade submissions.")
            return redirect('assignments:assignment_detail', assignment_id=self.object.assignment.id)
        
        return super().get(request, *args, **kwargs)
    
    def has_grading_permission(self):
        """Check if user has permission to grade"""
        return (
            self.request.user.role in ['instructor', 'admin', 'superadmin'] or 
            self.request.user.is_superuser
        )
    
    def get_form_kwargs(self):
        """Add custom arguments to form"""
        kwargs = super().get_form_kwargs()
        kwargs.update({
            'assignment': self.object.assignment,
            'submission': self.object,
            'current_user': self.request.user
        })
        return kwargs
    
    def form_valid(self, form):
        """Process successful form submission with comprehensive error handling"""
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
                
                # Process iteration feedback
                self.process_iteration_feedback()
                
                # Process rubric evaluations
                if self.object.assignment.rubric:
                    self.process_rubric_evaluations()
                
                # Log successful grading
                self.log_grading_interaction('success')
                
                if self.is_ajax_request(self.request):
                    return JsonResponse({
                        'success': True,
                        'message': 'Submission graded successfully.',
                        'redirect_url': self.get_success_url()
                    })
                
                messages.success(self.request, 'Submission graded successfully.')
                return redirect(self.get_success_url())
                
        except Exception as e:
            logger.error(f"Error in assignment grading: {str(e)}", exc_info=True)
            self.log_grading_interaction('failure', str(e))
            
            if self.is_ajax_request(self.request):
                return JsonResponse({
                    'success': False,
                    'error': 'An error occurred while grading. Please try again.',
                    'error_type': 'grading_error'
                }, status=500)
            
            form.add_error(None, 'An error occurred while saving the grade. Please try again.')
            return self.form_invalid(form)
    
    def process_iteration_feedback(self):
        """Process text question iteration feedback with error handling"""
        try:
            from .models import TextQuestionAnswerIteration, TextQuestionIterationFeedback
            
            for key, value in self.request.POST.items():
                if key.startswith('iteration_feedback_'):
                    try:
                        iteration_id = int(key.replace('iteration_feedback_', ''))
                        iteration = TextQuestionAnswerIteration.objects.get(
                            id=iteration_id, 
                            submission=self.object
                        )
                        
                        if value.strip():
                            allows_new_key = f'allows_new_iteration_{iteration_id}'
                            allows_new_iteration = allows_new_key in self.request.POST
                            
                            TextQuestionIterationFeedback.objects.create(
                                iteration=iteration,
                                feedback_text=value,
                                allows_new_iteration=allows_new_iteration,
                                created_by=self.request.user
                            )
                    except (ValueError, TextQuestionAnswerIteration.DoesNotExist) as e:
                        logger.warning(f"Error processing iteration feedback: {str(e)}")
                        continue
                        
        except Exception as e:
            logger.error(f"Error processing iteration feedback: {str(e)}")
            # Don't fail the entire grading process for iteration feedback errors
    
    def process_rubric_evaluations(self):
        """Process rubric evaluations with error handling"""
        try:
            from .models import RubricEvaluation, RubricEvaluationHistory
            
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
                            # Update existing evaluation
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
            # Don't fail the entire grading process for rubric errors
    
    def log_grading_interaction(self, result, error_message=None):
        """Log grading interactions for audit trail"""
        try:
            from .models import AssignmentInteractionLog
            
            AssignmentInteractionLog.log_interaction(
                assignment=self.object.assignment,
                user=self.request.user,
                interaction_type='assignment_grading',
                request=self.request,
                submission=self.object,
                success=(result == 'success'),
                error_message=error_message,
                grade_value=getattr(self.object, 'grade', None),
                has_feedback=bool(self.request.POST.get('feedback'))
            )
        except Exception as e:
            logger.error(f"Error logging grading interaction: {str(e)}")
            # Don't fail grading for logging errors
    
    def get_success_url(self):
        """Get URL to redirect to after successful grading"""
        return f"/assignments/{self.object.assignment.id}/"
    
    def get_context_data(self, **kwargs):
        """Add additional context for the template"""
        context = super().get_context_data(**kwargs)
        
        # Add rubric evaluation history
        if self.object.assignment.rubric:
            from .models import RubricEvaluationHistory
            
            all_student_submissions = AssignmentSubmission.objects.filter(
                assignment=self.object.assignment,
                user=self.object.user
            ).values_list('id', flat=True)
            
            context['rubric_evaluation_history'] = RubricEvaluationHistory.objects.filter(
                submission__in=all_student_submissions
            ).select_related(
                'submission', 'criterion', 'rating', 'evaluated_by'
            ).order_by('submission__submitted_at', 'criterion__position', '-version')
        
        return context


@login_required
@require_POST
def enhanced_submit_assignment(request, assignment_id):
    """
    Enhanced assignment submission with comprehensive error handling
    Replaces the original submit_assignment function
    """
    assignment = get_object_or_404(Assignment, id=assignment_id)
    
    # Check permissions
    if not assignment.is_available_for_user(request.user):
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False,
                'error': "You don't have permission to submit to this assignment.",
                'error_type': 'permission_denied'
            }, status=403)
        
        messages.error(request, "You don't have permission to submit to this assignment.")
        return redirect('assignments:assignment_list')
    
    try:
        with transaction.atomic():
            # Get or create submission
            submission, created = AssignmentSubmission.objects.get_or_create(
                assignment=assignment,
                user=request.user,
                defaults={'status': 'draft'}
            )
            
            # Check if student can edit this submission
            if request.user.role == 'learner':
                if submission and not submission.can_be_edited_by_student():
                    error_msg = "You cannot edit this submission. It has already been submitted and is being graded, or has been graded."
                    
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({
                            'success': False,
                            'error': error_msg,
                            'error_type': 'submission_locked'
                        }, status=400)
                    
                    messages.error(request, error_msg)
                    return redirect('assignments:assignment_detail', assignment_id=assignment.id)
            
            # Process file upload
            uploaded_file = request.FILES.get('submission_file')
            submission_text = request.POST.get('submission_text', '').strip()
            
            # Validate that we have some content
            if not uploaded_file and not submission_text:
                error_msg = "Please provide either a file or text submission."
                
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': False,
                        'error': error_msg,
                        'error_type': 'validation_error'
                    }, status=400)
                
                messages.error(request, error_msg)
                return redirect('assignments:submit_assignment', assignment_id=assignment.id)
            
            # Update submission
            if uploaded_file:
                submission.submission_file = uploaded_file
            if submission_text:
                submission.submission_text = submission_text
            
            submission.status = 'submitted'
            submission.submitted_at = timezone.now()
            submission.save()
            
            # Process text questions if any
            process_text_questions(request, assignment, submission)
            
            # Log successful submission
            log_submission_interaction(assignment, request.user, submission, 'success')
            
            success_msg = f'Your {"resubmission" if not created else "submission"} has been submitted successfully!'
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'message': success_msg,
                    'redirect_url': f"/assignments/{assignment.id}/"
                })
            
            messages.success(request, success_msg)
            return redirect('assignments:assignment_detail', assignment_id=assignment.id)
            
    except Exception as e:
        logger.error(f"Assignment submission error for user {request.user.id}: {str(e)}", exc_info=True)
        
        # Log failed submission
        
        error_msg = 'An error occurred while submitting your assignment. Please try again.'
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False,
                'error': error_msg,
                'error_type': 'submission_error'
            }, status=500)
        
        messages.error(request, error_msg)
        return redirect('assignments:submit_assignment', assignment_id=assignment.id)


def process_text_questions(request, assignment, submission):
    """Process text questions with error handling"""
    try:
        from .models import TextQuestion, create_or_get_latest_iteration
        
        text_questions = TextQuestion.objects.filter(assignment=assignment)
        for question in text_questions:
            question_name = f'text_question_{question.id}'
            if question_name in request.POST:
                answer_content = request.POST.get(question_name, '').strip()
                
                if answer_content:
                    iteration, created = create_or_get_latest_iteration(question, submission, 'question')
                    if iteration:
                        iteration.answer_text = answer_content
                        iteration.is_submitted = True
                        iteration.submitted_at = timezone.now()
                        iteration.save()
    except Exception as e:
        logger.error(f"Error processing text questions: {str(e)}")
        # Don't fail entire submission for text question errors


def log_submission_interaction(assignment, user, submission, result, error_message=None):
    """Log submission interactions"""
    try:
        from .models import AssignmentInteractionLog
        
        AssignmentInteractionLog.log_interaction(
            assignment=assignment,
            user=user,
            interaction_type='assignment_submission',
            submission=submission,
            success=(result == 'success'),
            error_message=error_message
        )
    except Exception as e:
        logger.error(f"Error logging submission interaction: {str(e)}")
        # Don't fail submission for logging errors
