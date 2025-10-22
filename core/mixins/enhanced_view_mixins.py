"""
Enhanced View Mixins - Comprehensive error handling for all LMS views
Provides standardized error handling, form processing, and user feedback
"""

import json
import logging
from django.http import JsonResponse, HttpResponseRedirect, HttpResponse
from django.contrib import messages
from django.core.exceptions import ValidationError, PermissionDenied, SuspiciousOperation
from django.views.generic.edit import FormMixin
from django.views.generic import View
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from django.db import transaction, IntegrityError
from django.conf import settings
from django.template.response import TemplateResponse

logger = logging.getLogger(__name__)


class BaseErrorHandlingMixin:
    """
    Base mixin that provides comprehensive error handling for all view types
    """
    
    def dispatch(self, request, *args, **kwargs):
        """Enhanced dispatch with comprehensive error handling"""
        try:
            return super().dispatch(request, *args, **kwargs)
        except PermissionDenied as e:
            return self.handle_permission_error(request, str(e))
        except ValidationError as e:
            return self.handle_validation_error(request, e)
        except SuspiciousOperation as e:
            return self.handle_suspicious_operation(request, str(e))
        except IntegrityError as e:
            return self.handle_database_error(request, e)
        except Exception as e:
            return self.handle_unexpected_error(request, e)
    
    def handle_permission_error(self, request, error_message):
        """Handle permission denied errors consistently"""
        logger.warning(f"Permission denied in {self.__class__.__name__}: {error_message} (User: {request.user.id if hasattr(request, 'user') else 'Unknown'})")
        
        if self.is_ajax_request(request):
            return JsonResponse({
                'success': False,
                'error': 'You do not have permission to perform this action.',
                'error_type': 'permission_denied',
                'action_required': 'redirect'
            }, status=403)
        
        messages.error(request, 'You do not have permission to perform this action.')
        return HttpResponseRedirect(self.get_permission_denied_redirect(request))
    
    def handle_validation_error(self, request, error):
        """Handle validation errors consistently"""
        error_message = str(error) if hasattr(error, 'message') else 'Please check your input and try again.'
        logger.warning(f"Validation error in {self.__class__.__name__}: {error_message}")
        
        if self.is_ajax_request(request):
            return JsonResponse({
                'success': False,
                'error': error_message,
                'error_type': 'validation_error'
            }, status=400)
        
        messages.error(request, error_message)
        return self.get_error_redirect(request)
    
    def handle_suspicious_operation(self, request, error_message):
        """Handle suspicious operation errors"""
        logger.warning(f"Suspicious operation in {self.__class__.__name__}: {error_message} (User: {request.user.id if hasattr(request, 'user') else 'Unknown'})")
        
        if self.is_ajax_request(request):
            return JsonResponse({
                'success': False,
                'error': 'Invalid request. Please refresh the page and try again.',
                'error_type': 'suspicious_operation',
                'action_required': 'refresh'
            }, status=400)
        
        messages.error(request, 'Invalid request. Please refresh the page and try again.')
        return self.get_error_redirect(request)
    
    def handle_database_error(self, request, error):
        """Handle database integrity errors"""
        logger.error(f"Database error in {self.__class__.__name__}: {str(error)}")
        
        # Provide user-friendly message
        user_message = "A database error occurred. This might be due to conflicting data. Please try again."
        
        if self.is_ajax_request(request):
            return JsonResponse({
                'success': False,
                'error': user_message,
                'error_type': 'database_error'
            }, status=500)
        
        messages.error(request, user_message)
        return self.get_error_redirect(request)
    
    def handle_unexpected_error(self, request, error):
        """Handle unexpected errors with comprehensive logging"""
        logger.error(f"Unexpected error in {self.__class__.__name__}: {str(error)}", exc_info=True, extra={
            'view_class': self.__class__.__name__,
            'user_id': getattr(request.user, 'id', 'anonymous') if hasattr(request, 'user') else 'anonymous',
            'path': request.path,
            'method': request.method,
            'user_agent': request.META.get('HTTP_USER_AGENT', 'Unknown'),
            'referer': request.META.get('HTTP_REFERER', 'None')
        })
        
        # Don't expose internal error details to users
        user_message = "An unexpected error occurred. Our technical team has been notified and is working to resolve this issue."
        
        if self.is_ajax_request(request):
            return JsonResponse({
                'success': False,
                'error': user_message,
                'error_type': 'server_error'
            }, status=500)
        
        messages.error(request, user_message)
        return self.get_error_redirect(request)
    
    def is_ajax_request(self, request):
        """Check if the request is an AJAX request"""
        return (request.headers.get('X-Requested-With') == 'XMLHttpRequest' or
                request.content_type == 'application/json' or
                'application/json' in request.headers.get('Accept', ''))
    
    def get_permission_denied_redirect(self, request):
        """Get redirect URL for permission denied errors"""
        # Try to redirect to a contextually appropriate page
        fallback_urls = [
            'users:role_based_redirect',
            'users:dashboard', 
            'users:login'
        ]
        
        for url_name in fallback_urls:
            try:
                return reverse_lazy(url_name)
            except:
                continue
        
        return '/'
    
    def get_error_redirect(self, request):
        """Get redirect URL for general errors"""
        # Try to stay on the current page or go to a safe page
        if hasattr(self, 'success_url') and self.success_url:
            return request.path
        
        try:
            return reverse_lazy('users:role_based_redirect')
        except:
            return '/'


class EnhancedFormHandlingMixin(BaseErrorHandlingMixin, FormMixin):
    """
    Enhanced form handling mixin with comprehensive error handling
    """
    
    def form_invalid(self, form):
        """Enhanced form error handling with better user feedback"""
        logger.warning(f"Form validation failed in {self.__class__.__name__}: {form.errors}")
        
        if self.is_ajax_request(self.request):
            return self.handle_ajax_form_error(form)
        
        return self.handle_regular_form_error(form)
    
    def handle_ajax_form_error(self, form):
        """Handle AJAX form submission errors"""
        errors = {}
        
        # Collect field-specific errors
        for field, error_list in form.errors.items():
            if field == '__all__':
                errors['non_field_errors'] = error_list
            else:
                errors[field] = error_list
        
        return JsonResponse({
            'success': False,
            'errors': errors,
            'message': 'Please correct the errors below and try again.',
            'error_type': 'form_validation'
        }, status=400)
    
    def handle_regular_form_error(self, form):
        """Handle regular form submission errors"""
        # Add user-friendly error messages
        error_messages = []
        
        # Process field errors with better formatting
        for field, error_list in form.errors.items():
            field_name = self.get_field_display_name(field, form)
            for error in error_list:
                error_messages.append(f"{field_name}: {error}")
        
        # Limit number of error messages to avoid overwhelming user
        if len(error_messages) > 5:
            error_messages = error_messages[:5]
            error_messages.append("...and additional errors. Please review all fields.")
        
        # Add messages to Django's message framework
        for message in error_messages:
            messages.error(self.request, message)
        
        return super().form_invalid(form)
    
    def get_field_display_name(self, field_name, form):
        """Get human-readable field name"""
        if field_name == '__all__':
            return 'Form'
        
        try:
            field = form.fields.get(field_name)
            if field and field.label:
                return field.label
        except:
            pass
        
        # Convert field name to readable format
        return field_name.replace('_', ' ').title()
    
    def form_valid(self, form):
        """Enhanced form valid handling with transaction support"""
        try:
            with transaction.atomic():
                return super().form_valid(form)
        except Exception as e:
            # Add form error and re-process as invalid
            form.add_error(None, f"An error occurred while saving: {str(e)}")
            return self.form_invalid(form)


class AtomicViewMixin:
    """
    Mixin to wrap view processing in database transactions
    """
    
    @method_decorator(transaction.atomic)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)


class CSRFEnhancedMixin:
    """
    Enhanced CSRF handling mixin - only applies to state-changing requests
    """
    
    def dispatch(self, request, *args, **kwargs):
        """Enhanced CSRF protection with better error handling - only for POST/PUT/PATCH/DELETE"""
        # Only apply CSRF protection to state-changing requests
        if request.method in ['POST', 'PUT', 'PATCH', 'DELETE']:
            @method_decorator(csrf_protect)
            def csrf_protected_dispatch(request, *args, **kwargs):
                try:
                    return super(CSRFEnhancedMixin, self).dispatch(request, *args, **kwargs)
                except Exception as e:
                    # Check if this is a CSRF-related error
                    error_str = str(e).lower()
                    if any(keyword in error_str for keyword in ['csrf', 'forbidden', 'token']):
                        return self.handle_csrf_error(request)
                    raise
            return csrf_protected_dispatch(request, *args, **kwargs)
        else:
            # For GET requests, no CSRF protection needed
            return super().dispatch(request, *args, **kwargs)
    
    def handle_csrf_error(self, request):
        """Handle CSRF token errors"""
        if hasattr(self, 'is_ajax_request') and self.is_ajax_request(request):
            return JsonResponse({
                'success': False,
                'error': 'Session token expired. Please refresh the page and try again.',
                'error_type': 'csrf_error',
                'action_required': 'refresh'
            }, status=403)
        
        messages.error(request, 'Session token expired. Please refresh the page and try again.')
        return HttpResponseRedirect(request.path)


class GradingViewMixin(EnhancedFormHandlingMixin, AtomicViewMixin):
    """
    Specialized mixin for grading views with enhanced error handling
    """
    
    def form_valid(self, form):
        """Enhanced grading form validation"""
        try:
            # Additional grading-specific validation
            if hasattr(form, 'cleaned_data'):
                grade = form.cleaned_data.get('grade')
                if grade is not None:
                    try:
                        grade_float = float(grade)
                        if not (0 <= grade_float <= 100):
                            form.add_error('grade', 'Grade must be between 0 and 100.')
                            return self.form_invalid(form)
                    except (ValueError, TypeError):
                        form.add_error('grade', 'Please enter a valid numeric grade.')
                        return self.form_invalid(form)
            
            return super().form_valid(form)
        except Exception as e:
            logger.error(f"Error in grading form validation: {str(e)}")
            form.add_error(None, 'An error occurred while saving the grade. Please try again.')
            return self.form_invalid(form)
    
    def handle_ajax_form_error(self, form):
        """Enhanced AJAX error handling for grading forms"""
        response_data = super().handle_ajax_form_error(form).content
        response_data = json.loads(response_data)
        
        # Add grading-specific context
        response_data['context'] = 'grading'
        response_data['help_text'] = 'Please check your grade values and feedback content.'
        
        return JsonResponse(response_data, status=400)


class CourseViewMixin(EnhancedFormHandlingMixin, AtomicViewMixin):
    """
    Specialized mixin for course-related views
    """
    
    def handle_permission_error(self, request, error_message):
        """Course-specific permission error handling"""
        logger.warning(f"Course permission denied: {error_message}")
        
        if self.is_ajax_request(request):
            return JsonResponse({
                'success': False,
                'error': 'You do not have permission to modify this course.',
                'error_type': 'course_permission_denied'
            }, status=403)
        
        messages.error(request, 'You do not have permission to modify this course.')
        return HttpResponseRedirect(reverse_lazy('courses:course_list'))


class UserManagementMixin(EnhancedFormHandlingMixin, AtomicViewMixin):
    """
    Specialized mixin for user management views
    """
    
    def handle_database_error(self, request, error):
        """User-specific database error handling"""
        error_str = str(error).lower()
        
        if 'unique' in error_str or 'duplicate' in error_str:
            user_message = "A user with this information already exists. Please check the email address and username."
        else:
            user_message = "A database error occurred while processing the user information. Please try again."
        
        logger.error(f"User management database error: {str(error)}")
        
        if self.is_ajax_request(request):
            return JsonResponse({
                'success': False,
                'error': user_message,
                'error_type': 'user_database_error'
            }, status=400)
        
        messages.error(request, user_message)
        return self.get_error_redirect(request)


class RobustViewMixin(EnhancedFormHandlingMixin, CSRFEnhancedMixin):
    """
    Combined mixin for maximum robustness
    Use this for most views that need comprehensive error handling
    """
    pass


class RobustAtomicViewMixin(EnhancedFormHandlingMixin, CSRFEnhancedMixin, AtomicViewMixin):
    """
    Combined mixin with database transactions
    Use this for views that modify data
    """
    pass
