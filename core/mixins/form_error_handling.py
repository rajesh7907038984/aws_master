"""
Enhanced Form Error Handling Mixins
Provides better error handling for form submissions to prevent error pages
"""

import json
import logging
from django.http import JsonResponse, HttpResponseRedirect
from django.contrib import messages
from django.core.exceptions import ValidationError, PermissionDenied
from django.views.generic.edit import FormMixin
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect

logger = logging.getLogger(__name__)


class EnhancedFormErrorHandlingMixin:
    """
    Mixin to provide better error handling for form submissions
    Prevents users from seeing generic error pages
    """
    
    def form_invalid(self, form):
        """Enhanced form error handling"""
        # Log the form errors for debugging
        logger.warning(f"Form validation failed in {self.__class__.__name__}: {form.errors}")
        
        # Check if this is an AJAX request
        if self.request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return self.handle_ajax_form_error(form)
        
        # Handle regular form submission errors
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
            'message': 'Please correct the errors below.'
        }, status=400)
    
    def handle_regular_form_error(self, form):
        """Handle regular form submission errors"""
        # Add user-friendly error messages
        error_messages = []
        
        # Process field errors
        for field, error_list in form.errors.items():
            field_name = self.get_field_display_name(field, form)
            for error in error_list:
                error_messages.append(f"{field_name}: {error}")
        
        # Limit number of error messages to avoid overwhelming user
        if len(error_messages) > 5:
            error_messages = error_messages[:5]
            error_messages.append("... and more errors. Please review all fields.")
        
        # Add messages to Django's message framework
        for message in error_messages:
            messages.error(self.request, message)
        
        # Return to the form page
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
    
    def dispatch(self, request, *args, **kwargs):
        """Enhanced dispatch with error handling"""
        try:
            return super().dispatch(request, *args, **kwargs)
        except PermissionDenied as e:
            return self.handle_permission_error(str(e))
        except ValidationError as e:
            return self.handle_validation_error(e)
        except Exception as e:
            return self.handle_unexpected_error(e)
    
    def handle_permission_error(self, error_message):
        """Handle permission denied errors"""
        logger.warning(f"Permission denied in {self.__class__.__name__}: {error_message}")
        
        if self.request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False,
                'error': 'You do not have permission to perform this action.'
            }, status=403)
        
        messages.error(self.request, 'You do not have permission to perform this action.')
        return HttpResponseRedirect(self.get_permission_denied_redirect())
    
    def handle_validation_error(self, error):
        """Handle validation errors"""
        error_message = str(error) if hasattr(error, 'message') else 'Validation error occurred'
        logger.warning(f"Validation error in {self.__class__.__name__}: {error_message}")
        
        if self.request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False,
                'error': error_message
            }, status=400)
        
        messages.error(self.request, error_message)
        return self.get_form_error_redirect()
    
    def handle_unexpected_error(self, error):
        """Handle unexpected errors"""
        logger.error(f"Unexpected error in {self.__class__.__name__}: {str(error)}", exc_info=True)
        
        # Don't expose internal errors to users
        user_message = "An unexpected error occurred. Please try again."
        
        if self.request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False,
                'error': user_message
            }, status=500)
        
        messages.error(self.request, user_message)
        return self.get_error_redirect()
    
    def get_permission_denied_redirect(self):
        """Get redirect URL for permission denied errors"""
        # Try to redirect to a safe page
        if hasattr(self, 'permission_denied_url'):
            return self.permission_denied_url
        
        # Fallback redirects
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
    
    def get_form_error_redirect(self):
        """Get redirect URL for form errors"""
        # Stay on the same page if possible
        if hasattr(self, 'success_url'):
            return self.request.path
        
        return self.get_error_redirect()
    
    def get_error_redirect(self):
        """Get generic error redirect URL"""
        try:
            return reverse_lazy('users:role_based_redirect')
        except:
            return '/'


class EnhancedGradingFormMixin(EnhancedFormErrorHandlingMixin):
    """
    Specialized mixin for grading forms with additional validation
    """
    
    def form_valid(self, form):
        """Enhanced form validation for grading"""
        try:
            # Additional grading-specific validation
            if hasattr(form, 'cleaned_data'):
                grade = form.cleaned_data.get('grade')
                if grade is not None:
                    if not (0 <= float(grade) <= 100):
                        form.add_error('grade', 'Grade must be between 0 and 100.')
                        return self.form_invalid(form)
            
            return super().form_valid(form)
        except Exception as e:
            logger.error(f"Error in grading form validation: {str(e)}")
            form.add_error(None, 'An error occurred while saving the grade. Please try again.')
            return self.form_invalid(form)
    
    def handle_ajax_form_error(self, form):
        """Handle AJAX errors for grading forms"""
        response = super().handle_ajax_form_error(form)
        
        # Add grading-specific error context
        response_data = json.loads(response.content)
        response_data['context'] = 'grading'
        response_data['help_text'] = 'Please check your grade values and try again.'
        
        return JsonResponse(response_data, status=400)


class CSRFEnhancedMixin:
    """
    Mixin to provide better CSRF error handling - only applies to state-changing requests
    """
    
    def dispatch(self, request, *args, **kwargs):
        """Enhanced CSRF protection - only for POST/PUT/PATCH/DELETE"""
        # Only apply CSRF protection to state-changing requests
        if request.method in ['POST', 'PUT', 'PATCH', 'DELETE']:
            @method_decorator(csrf_protect)
            def csrf_protected_dispatch(request, *args, **kwargs):
                try:
                    return super(CSRFEnhancedMixin, self).dispatch(request, *args, **kwargs)
                except Exception as e:
                    # Check if this might be a CSRF error
                    if 'CSRF' in str(e) or 'Forbidden' in str(e):
                        return self.handle_csrf_error()
                    raise
            return csrf_protected_dispatch(request, *args, **kwargs)
        else:
            # For GET requests, no CSRF protection needed
            return super().dispatch(request, *args, **kwargs)
    
    def handle_csrf_error(self):
        """Handle CSRF token errors"""
        if self.request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False,
                'error': 'Session token expired. Please refresh the page and try again.',
                'csrf_error': True
            }, status=403)
        
        messages.error(
            self.request, 
            'Session token expired. Please refresh the page and try again.'
        )
        return HttpResponseRedirect(self.request.path)


class RobustFormViewMixin(EnhancedFormErrorHandlingMixin, CSRFEnhancedMixin):
    """
    Combined mixin for robust form handling
    """
    pass
