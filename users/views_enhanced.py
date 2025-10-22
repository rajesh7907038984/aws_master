"""
Enhanced User Management Views with Comprehensive Error Handling
This file contains upgraded versions of critical user management views
"""

import logging
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.db import transaction, IntegrityError
from django.contrib.auth import update_session_auth_hash
from django.urls import reverse_lazy

from core.mixins.enhanced_view_mixins import UserManagementMixin, RobustAtomicViewMixin
from .models import CustomUser
from .forms import CustomUserCreationForm, CustomUserChangeForm

logger = logging.getLogger(__name__)


class EnhancedUserCreateView(UserManagementMixin, CreateView):
    """
    Enhanced user creation view with comprehensive error handling
    """
    model = CustomUser
    form_class = CustomUserCreationForm
    template_name = 'users/shared/create_user.html'
    success_url = reverse_lazy('users:user_list')
    
    def get_form_kwargs(self):
        """Add request to form kwargs"""
        kwargs = super().get_form_kwargs()
        kwargs['request'] = self.request
        return kwargs
    
    def form_valid(self, form):
        """Enhanced form validation with better error handling"""
        try:
            with transaction.atomic():
                # Create the user
                user = form.save()
                
                # Log successful user creation
                logger.info(f"User created successfully: {user.username} by {self.request.user.username}")
                
                if self.is_ajax_request(self.request):
                    return JsonResponse({
                        'success': True,
                        'message': f'User {user.username} created successfully.',
                        'redirect_url': str(self.success_url),
                        'user_id': user.id
                    })
                
                messages.success(self.request, f'User {user.username} created successfully.')
                return super().form_valid(form)
                
        except IntegrityError as e:
            error_str = str(e).lower()
            if 'email' in error_str:
                form.add_error('email', 'A user with this email address already exists.')
            elif 'username' in error_str:
                form.add_error('username', 'A user with this username already exists.')
            else:
                form.add_error(None, 'This user information conflicts with an existing user.')
            
            return self.form_invalid(form)
        
        except Exception as e:
            logger.error(f"Error creating user: {str(e)}", exc_info=True)
            form.add_error(None, 'An error occurred while creating the user. Please try again.')
            return self.form_invalid(form)
    
    def handle_database_error(self, request, error):
        """Override to provide user-specific error messages"""
        error_str = str(error).lower()
        
        if 'unique' in error_str:
            if 'email' in error_str:
                error_msg = "A user with this email address already exists."
            elif 'username' in error_str:
                error_msg = "A user with this username already exists."
            else:
                error_msg = "A user with this information already exists."
        else:
            error_msg = "A database error occurred while creating the user. Please check the information and try again."
        
        logger.error(f"User creation database error: {str(error)}")
        
        if self.is_ajax_request(request):
            return JsonResponse({
                'success': False,
                'error': error_msg,
                'error_type': 'user_database_error'
            }, status=400)
        
        messages.error(request, error_msg)
        return self.get_error_redirect(request)


class EnhancedUserUpdateView(UserManagementMixin, UpdateView):
    """
    Enhanced user update view with comprehensive error handling
    """
    model = CustomUser
    form_class = CustomUserChangeForm
    template_name = 'users/user_form_tabbed_modular.html'
    context_object_name = 'profile_user'
    
    def get_object(self):
        """Get the user to be edited"""
        user_id = self.kwargs.get('user_id')
        return get_object_or_404(CustomUser, id=user_id)
    
    def get_form_kwargs(self):
        """Add request to form kwargs"""
        kwargs = super().get_form_kwargs()
        kwargs['request'] = self.request
        return kwargs
    
    def form_valid(self, form):
        """Enhanced form validation with better error handling"""
        try:
            with transaction.atomic():
                # Check if password is being changed
                password_changed = False
                if hasattr(form, 'cleaned_data'):
                    new_password = form.cleaned_data.get('password1')
                    if new_password:
                        password_changed = True
                
                # Save the user
                user = form.save()
                
                # Update session auth hash if password changed
                if password_changed and user == self.request.user:
                    update_session_auth_hash(self.request, user)
                
                # Log successful user update
                logger.info(f"User updated successfully: {user.username} by {self.request.user.username}")
                
                # Determine redirect URL
                redirect_url = self.get_success_url()
                
                if self.is_ajax_request(self.request):
                    return JsonResponse({
                        'success': True,
                        'message': f'User {user.username} updated successfully.',
                        'redirect_url': redirect_url,
                        'password_changed': password_changed
                    })
                
                messages.success(self.request, f'User {user.username} updated successfully.')
                return redirect(redirect_url)
                
        except IntegrityError as e:
            return self.handle_database_error(self.request, e)
        
        except Exception as e:
            logger.error(f"Error updating user {self.object.id}: {str(e)}", exc_info=True)
            form.add_error(None, 'An error occurred while updating the user. Please try again.')
            return self.form_invalid(form)
    
    def get_success_url(self):
        """Get URL to redirect to after successful update"""
        # Preserve tab state if provided
        tab = self.request.POST.get('active_tab', '')
        subtab = self.request.POST.get('active_subtab', '')
        
        url = f"/users/edit/{self.object.id}/"
        if tab:
            url += f"?tab={tab}"
            if subtab:
                url += f"&subtab={subtab}"
        
        return url
    
    def get_context_data(self, **kwargs):
        """Add additional context for the template"""
        context = super().get_context_data(**kwargs)
        
        # Add tab state information
        context['active_tab'] = self.request.POST.get('active_tab') or self.request.GET.get('tab', 'account-tab')
        context['active_subtab'] = self.request.POST.get('active_subtab') or self.request.GET.get('subtab', '')
        context['is_edit_mode'] = True
        
        return context


@login_required
def enhanced_user_delete(request, user_id):
    """
    Enhanced user deletion with comprehensive error handling
    """
    user_to_delete = get_object_or_404(CustomUser, id=user_id)
    
    # Check permissions
    if not has_user_delete_permission(request.user, user_to_delete):
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False,
                'error': "You don't have permission to delete this user.",
                'error_type': 'permission_denied'
            }, status=403)
        
        messages.error(request, "You don't have permission to delete this user.")
        return redirect('users:user_list')
    
    if request.method == 'POST':
        try:
            with transaction.atomic():
                username = user_to_delete.get_full_name() or user_to_delete.username
                
                # Log user deletion
                logger.info(f"User deletion: {username} (ID: {user_id}) by {request.user.username}")
                
                # Soft delete or hard delete based on configuration
                if should_soft_delete_user(user_to_delete):
                    user_to_delete.is_active = False
                    user_to_delete.save()
                    action = 'deactivated'
                else:
                    user_to_delete.delete()
                    action = 'deleted'
                
                success_msg = f'User {username} has been {action} successfully.'
                
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': True,
                        'message': success_msg,
                        'redirect_url': '/users/'
                    })
                
                messages.success(request, success_msg)
                return redirect('users:user_list')
                
        except Exception as e:
            logger.error(f"Error deleting user {user_id}: {str(e)}", exc_info=True)
            
            error_msg = 'An error occurred while deleting the user. Please try again.'
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'error': error_msg,
                    'error_type': 'deletion_error'
                }, status=500)
            
            messages.error(request, error_msg)
            return redirect('users:user_detail', user_id=user_id)
    
    # GET request - show confirmation
    context = {
        'user_to_delete': user_to_delete,
        'can_delete': True
    }
    return render(request, 'users/shared/user_delete_confirm.html', context)


@login_required
def enhanced_change_password(request, user_id):
    """
    Enhanced password change with comprehensive error handling
    """
    target_user = get_object_or_404(CustomUser, id=user_id)
    
    # Check permissions
    if not has_password_change_permission(request.user, target_user):
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False,
                'error': "You don't have permission to change this user's password.",
                'error_type': 'permission_denied'
            }, status=403)
        
        messages.error(request, "You don't have permission to change this user's password.")
        return redirect('users:user_detail', user_id=user_id)
    
    if request.method == 'POST':
        try:
            from .forms import AdminPasswordChangeForm, CustomPasswordChangeForm
            
            is_admin = request.user.role in ['admin', 'superadmin', 'globaladmin']
            FormClass = AdminPasswordChangeForm if is_admin else CustomPasswordChangeForm
            
            form = FormClass(target_user, request.POST)
            
            if form.is_valid():
                with transaction.atomic():
                    user = form.save()
                    
                    # Update session if changing own password
                    if target_user == request.user:
                        update_session_auth_hash(request, user)
                    
                    # Log password change
                    logger.info(f"Password changed for user {target_user.username} by {request.user.username}")
                    
                    success_msg = f'Password for {target_user.get_full_name() or target_user.username} has been changed successfully.'
                    
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({
                            'success': True,
                            'message': success_msg,
                            'session_updated': (target_user == request.user)
                        })
                    
                    messages.success(request, success_msg)
                    return redirect('users:user_detail', user_id=user_id)
            else:
                # Form validation errors
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': False,
                        'errors': form.errors,
                        'error_type': 'validation_error'
                    }, status=400)
                
                for field, errors in form.errors.items():
                    for error in errors:
                        messages.error(request, f"{field}: {error}")
                
                # Return to form with errors
                context = {
                    'target_user': target_user,
                    'can_change_password': True,
                    'form': form
                }
                return render(request, 'users/shared/change_password.html', context)
                        
        except Exception as e:
            logger.error(f"Error changing password for user {user_id}: {str(e)}", exc_info=True)
            
            error_msg = 'An error occurred while changing the password. Please try again.'
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'error': error_msg,
                    'error_type': 'password_change_error'
                }, status=500)
            
            messages.error(request, error_msg)
    
    # Handle GET request or form errors
    context = {
        'target_user': target_user,
        'can_change_password': True
    }
    return render(request, 'users/shared/change_password.html', context)


def has_user_delete_permission(user, target_user):
    """Check if user has permission to delete target_user"""
    if user.is_superuser:
        return True
    
    if user.role == 'globaladmin':
        return True
    
    if user.role == 'superadmin':
        # Can delete users in their business
        return user.business == target_user.business
    
    if user.role == 'admin':
        # Can delete users in their branch
        return user.branch == target_user.branch
    
    return False


def has_password_change_permission(user, target_user):
    """Check if user has permission to change target_user's password"""
    if user == target_user:
        return True
    
    if user.is_superuser:
        return True
    
    if user.role == 'globaladmin':
        return True
    
    if user.role == 'superadmin':
        return user.business == target_user.business
    
    if user.role == 'admin':
        return user.branch == target_user.branch
    
    return False


def should_soft_delete_user(user):
    """Determine if user should be soft deleted (deactivated) or hard deleted"""
    # Users with submissions, enrollments, or other data should be soft deleted
    if hasattr(user, 'submissions') and user.submissions.exists():
        return True
    
    if hasattr(user, 'enrollments') and user.enrollments.exists():
        return True
    
    # Add other conditions as needed
    return False
