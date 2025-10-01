from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_http_methods
from django.contrib.auth import get_user_model
import requests
import json
import os
from .models import Message, MessageAttachment, MessageReadStatus
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from users.models import CustomUser, Branch
from django.utils.decorators import method_decorator
from django.urls import reverse
from django.utils import timezone
from django.db.models import Q, Count, Exists, OuterRef, Prefetch
from django.forms import Form
from django.contrib import messages
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from tinymce_editor.forms import TinyMCEFormField
from tinymce_editor.widgets import TinyMCEWidget
from groups.models import BranchGroup

from django import forms

User = get_user_model()


def _can_user_message_recipient(sender, recipient):
    """
    Helper function to check if a user can send a message to a specific recipient.
    Implements RBAC v0.1 conditional access rules for messaging.
    """
    if sender.role == 'globaladmin' or sender.is_superuser:
        # Global Admin: FULL access - can message anyone
        return True
    
    elif sender.role == 'superadmin':
        # Super Admin: CONDITIONAL access - can message users in their assigned businesses
        if hasattr(sender, 'business_assignments') and hasattr(recipient, 'branch') and recipient.branch:
            if hasattr(recipient.branch, 'business'):
                return sender.business_assignments.filter(
                    business=recipient.branch.business, 
                    is_active=True
                ).exists()
        return False
    
    elif sender.role == 'admin':
        # Branch Admin: CONDITIONAL access - can message users in their assigned branches
        return sender.branch and recipient.branch == sender.branch
    
    elif sender.role == 'instructor':
        # Instructor: CONDITIONAL access - can message learners in their branch
        if not sender.branch:
            return False
        
        # Can message learners in their branch
        if recipient.role == 'learner' and recipient.branch == sender.branch:
            return True
        
        # Can message other instructors and admins in their branch
        if recipient.role in ['instructor', 'admin'] and recipient.branch == sender.branch:
            return True
        
        return False
    
    elif sender.role == 'learner':
        # Learner: SELF access - can message instructors, admins, and peers in their branch
        if not sender.branch:
            return False
        
        # Can message instructors and admins in their branch
        if recipient.role in ['instructor', 'admin'] and recipient.branch == sender.branch:
            return True
        
        # Can message other learners in their branch
        if recipient.role == 'learner' and recipient.branch == sender.branch:
            return True
        
        return False
    
    return False


def _can_user_access_group(user, group):
    """
    Helper function to check if a user can access a specific group for messaging.
    Implements RBAC v0.1 conditional access rules for group messaging.
    """
    if user.role == 'globaladmin' or user.is_superuser:
        # Global Admin: FULL access - can access any group
        return True
    
    elif user.role == 'superadmin':
        # Super Admin: CONDITIONAL access - can access groups in their assigned businesses
        if hasattr(user, 'business_assignments') and hasattr(group, 'branch') and group.branch:
            if hasattr(group.branch, 'business'):
                return user.business_assignments.filter(
                    business=group.branch.business, 
                    is_active=True
                ).exists()
        return False
    
    elif user.role == 'admin':
        # Branch Admin: CONDITIONAL access - can access groups in their assigned branches
        return user.branch and group.branch == user.branch
    
    elif user.role == 'instructor':
        # Instructor: CONDITIONAL access - can access groups in their branch (if they have manage_groups capability)
        from role_management.utils import PermissionManager
        if not user.branch or group.branch != user.branch:
            return False
        
        return PermissionManager.user_has_capability(user, 'manage_groups')
    
    elif user.role == 'learner':
        # Learner: NONE - cannot access groups for messaging
        return False
    
    return False

def fetch_and_save_messages():
    """Fetch messages from external URL and save to database"""
    # Use BASE_URL from settings for dynamic URL
    from django.conf import settings
    base_url = getattr(settings, 'BASE_URL', 'https://localhost')
    url = f"{base_url}/messages/"
    
    try:
        # Fetch messages from external URL
        response = requests.get(url)
        response.raise_for_status()
        messages_data = response.json()
        
        # Process each message
        for msg_data in messages_data:
            # Check if message already exists
            if Message.objects.filter(external_id=msg_data.get('id')).exists():
                continue
                
            # Get or create sender
            sender_email = msg_data.get('sender', {}).get('email', 'unknown@example.com')
            sender, _ = User.objects.get_or_create(
                email=sender_email,
                defaults={'username': sender_email.split('@')[0]}
            )
            
            # Create message
            message = Message.objects.create(
                sender=sender,
                subject=msg_data.get('subject', 'No Subject'),
                content=msg_data.get('content', ''),
                external_id=msg_data.get('id'),
                external_source='devtunnels'
            )
            
            # Add recipients
            for recipient_data in msg_data.get('recipients', []):
                recipient_email = recipient_data.get('email', '')
                if recipient_email:
                    recipient, _ = User.objects.get_or_create(
                        email=recipient_email,
                        defaults={'username': recipient_email.split('@')[0]}
                    )
                    message.recipients.add(recipient)
            
        return {'status': 'success', 'message': 'Messages imported successfully'}
        
    except requests.RequestException as e:
        return {'status': 'error', 'message': f'Failed to fetch messages: {str(e)}'}
    except Exception as e:
        return {'status': 'error', 'message': f'Error processing messages: {str(e)}'}

@require_http_methods(["POST"])
@login_required
def sync_messages(request):
    """API endpoint to trigger message synchronization"""
    result = fetch_and_save_messages()
    return JsonResponse(result)

@login_required
def messages_view(request):
    """View for displaying the messages list."""
    
    # Get date filter parameters
    from_date = request.GET.get('from_date')
    to_date = request.GET.get('to_date')
    
    # Get messages where user is sender or recipient
    user_messages = Message.objects.filter(
        Q(sender=request.user) | Q(recipients=request.user)
    ).distinct()
    
    # Apply date filtering if parameters are provided
    if from_date:
        try:
            # Parse date and apply filter
            from datetime import datetime
            parsed_from_date = datetime.strptime(from_date, '%Y-%m-%d').date()
            user_messages = user_messages.filter(created_at__date__gte=parsed_from_date)
        except ValueError:
            # Invalid date format, ignore filter
            pass
    
    if to_date:
        try:
            # Parse date and apply filter
            from datetime import datetime
            parsed_to_date = datetime.strptime(to_date, '%Y-%m-%d').date()
            user_messages = user_messages.filter(created_at__date__lte=parsed_to_date)
        except ValueError:
            # Invalid date format, ignore filter
            pass
    
    # Apply ordering after filtering
    user_messages = user_messages.order_by('-created_at')
    
    # Add read status for the user
    user_messages = user_messages.annotate(
        is_read_by_user=Exists(
            MessageReadStatus.objects.filter(
                message=OuterRef('pk'),
                user=request.user,
                is_read=True
            )
        )
    )
    
    # Create read status for messages that don't have it yet
    for message in user_messages:
        # Only create read status for received messages
        if message.sender != request.user:
            MessageReadStatus.objects.get_or_create(
                message=message,
                user=request.user,
                defaults={'is_read': False}
            )
    
    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'label': 'Messages', 'icon': 'fa-envelope'}
    ]
    return render(request, 'lms_messages/messages.html', {
        'breadcrumbs': breadcrumbs,
        'messages_list': user_messages,
        'from_date': from_date,
        'to_date': to_date
    })

@login_required
def message_detail(request, message_id):
    """View for displaying a single message."""
    # First get the message by ID to avoid multiple objects being returned
    message = get_object_or_404(Message, id=message_id)
    
    # Then check if the user has permission to view it
    if request.user != message.sender and request.user not in message.recipients.all():
        messages.error(request, "You don't have permission to view this message.")
        return redirect('lms_messages:messages')
    
    # Mark message as read if recipient is viewing
    if request.user in message.recipients.all():
        message.mark_read(request.user)
    
    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': reverse('lms_messages:messages'), 'label': 'Messages', 'icon': 'fa-envelope'},
        {'label': message.subject, 'icon': 'fa-envelope-open'}
    ]
    
    # Initialize reply form
    reply_form = ReplyForm()
    
    return render(request, 'lms_messages/message_detail.html', {
        'breadcrumbs': breadcrumbs,
        'message': message,
        'reply_form': reply_form
    })

@login_required
@require_POST
@ensure_csrf_cookie
def upload_image(request):
    """Handle image uploads for rich text editor"""
    
    if 'upload' not in request.FILES:  # Editor sends file in 'upload' parameter
        return HttpResponseBadRequest("No image file found")
        
    # Get the uploaded file
    upload = request.FILES['upload']
    
    # Check if the uploaded file is an image
    if not upload.name.endswith(('.jpg', '.jpeg', '.png', '.gif')):
        return HttpResponseBadRequest("File type not supported")
    
    # Save the file to media
    from django.core.files.storage import default_storage
    from django.core.files.base import ContentFile
    import os
    
    # Define path to save the image (inside media)
    path = os.path.join('messages', 'uploads', upload.name)
    path = default_storage.save(path, ContentFile(upload.read()))
    
    # Return the URL for the uploaded image in standard format for rich text editors
    file_url = default_storage.url(path)
    return JsonResponse({
        'url': file_url,
        'uploaded': '1',
        'fileName': upload.name
    })

@login_required
@require_POST
def send_message(request):
    try:
        # Handle form data
        recipients_str = request.POST.get('recipients', '')
        subject = request.POST.get('subject', '')
        content = request.POST.get('content', '')
        
        recipients_usernames = [username.strip() for username in recipients_str.split(',')]
        
        # Validate recipients
        recipients = []
        invalid_users = []
        for username in recipients_usernames:
            try:
                user = CustomUser.objects.get(username=username)
                recipients.append(user)
            except CustomUser.DoesNotExist:
                invalid_users.append(username)
        
        if invalid_users:
            return JsonResponse({
                'status': 'error',
                'message': f'Invalid recipients: {", ".join(invalid_users)}'
            })
        
        # Create message
        message = Message.objects.create(
            subject=subject,
            content=content,
            sender=request.user,
            branch=request.user.branch  # Set branch to sender's branch
        )
        message.recipients.set(recipients)
        
        # Handle file uploads
        files = request.FILES.getlist('files[]')
        for file in files:
            # Get the file extension
            _, ext = os.path.splitext(file.name)
            
            # Create attachment
            attachment = MessageAttachment.objects.create(
                message=message,
                file=file,
                filename=file.name,
                file_type=ext.lstrip('.').lower()
            )
        
        return JsonResponse({
            'status': 'success',
            'message': 'Message sent successfully'
        })
        
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        })

class ComposeForm(Form):
    """Dynamic form for composing messages"""
    content = TinyMCEFormField(
        label="Message",
        required=True,
        config={
            'height': 300,
            'menubar': False,
            'plugins': [
                'autolink', 'lists', 'link', 'charmap',
                'searchreplace', 'visualblocks', 'code', 'fullscreen',
                'insertdatetime', 'media', 'wordcount', 'image'
            ],
            'toolbar': 'undo redo | bold italic | ' +
                      'alignleft aligncenter alignright | ' +
                      'bullist numlist | ' +
                      'link | image media | ' +
                      'removeformat | fullscreen',
            'content_style': 'body { font-family:Helvetica,Arial,sans-serif; font-size:14px }',
            'placeholder': 'Enter your message here...'
        }
    )

class ReplyForm(Form):
    """Form for replying to messages"""
    content = TinyMCEFormField(
        label="Your Reply",
        required=True,
        config={
            'height': 200,
            'menubar': False,
            'plugins': [
                'autolink', 'lists', 'link', 'charmap',
                'searchreplace', 'visualblocks', 'code', 'fullscreen',
                'insertdatetime', 'media', 'wordcount', 'image'
            ],
            'toolbar': 'undo redo | bold italic | ' +
                      'alignleft aligncenter alignright | ' +
                      'bullist numlist | ' +
                      'link | image media | ' +
                      'removeformat | fullscreen',
            'content_style': 'body { font-family:Helvetica,Arial,sans-serif; font-size:14px }',
            'placeholder': 'Type your reply here...'
        }
    )

@login_required
def new_message(request):
    """View for creating a new message - RBAC v0.1 Compliant"""
    from role_management.utils import PermissionManager
    from django.http import HttpResponseForbidden
    
    # RBAC v0.1 Validation: Check if user has create_messages capability
    if not PermissionManager.user_has_capability(request.user, 'create_messages'):
        return HttpResponseForbidden("Access denied: You don't have permission to create messages")
    
    form = ComposeForm()
    user = request.user
    
    # Handle reply_to parameter
    reply_to_message = None
    initial_subject = ""
    initial_recipients = []
    
    reply_to_id = request.GET.get('reply_to')
    if reply_to_id:
        try:
            reply_to_message = Message.objects.get(id=reply_to_id)
            # Check if user has permission to view the original message
            if user == reply_to_message.sender or user in reply_to_message.recipients.all():
                # Pre-fill subject with "Re: "
                initial_subject = f"Re: {reply_to_message.subject}" if not reply_to_message.subject.startswith("Re:") else reply_to_message.subject
                # Pre-fill recipients - reply to sender and all original recipients, excluding current user
                initial_recipients = list(reply_to_message.recipients.all())
                if reply_to_message.sender != user:
                    initial_recipients.append(reply_to_message.sender)
                # Remove current user from recipients
                initial_recipients = [r for r in initial_recipients if r != user]
            else:
                reply_to_message = None
        except Message.DoesNotExist:
            reply_to_message = None
    
    # Initialize context variables
    branch_users = {}
    user_groups = []
    
    # Get user's branch
    user_branch = user.branch
    
    # Apply role-based filtering - RBAC v0.1 Compliant
    if user.role == 'globaladmin' or user.is_superuser:
        # Global Admin: FULL access - can message anyone
        branches = Branch.objects.all().prefetch_related('users')
        for branch in branches:
            branch_users[branch.name] = list(branch.users.values('id', 'username', 'first_name', 'last_name'))
        
        # Get all groups
        groups = BranchGroup.objects.all()
        user_groups = groups.values('id', 'name')
    
    elif user.role == 'superadmin':
        # Super Admin: CONDITIONAL access - can only message users in their assigned businesses
        if hasattr(user, 'business_assignments'):
            assigned_businesses = user.business_assignments.filter(is_active=True).values_list('business', flat=True)
            branches = Branch.objects.filter(business__in=assigned_businesses).prefetch_related('users')
            for branch in branches:
                branch_users[branch.name] = list(branch.users.values('id', 'username', 'first_name', 'last_name'))
            
            # Get groups in assigned businesses
            groups = BranchGroup.objects.filter(branch__business__in=assigned_businesses)
            user_groups = groups.values('id', 'name')
        else:
            # No business assignments, no access
            branch_users = {}
            user_groups = []
    
    elif user.role == 'admin':
        # Branch Admin: CONDITIONAL access - can only message users in their assigned branches
        if user_branch:
            branch_users[user_branch.name] = list(user_branch.users.values('id', 'username', 'first_name', 'last_name'))
            
            # Get groups in their branch
            groups = BranchGroup.objects.filter(branch=user_branch)
            user_groups = groups.values('id', 'name')
        else:
            # No branch assignment, no access
            branch_users = {}
            user_groups = []
    
    elif user.role == 'instructor':
        # Instructor: CONDITIONAL access - can only message learners in their branch
        if user_branch:
            # Get learners in their branch
            learners = CustomUser.objects.filter(branch=user_branch, role='learner')
            branch_users[user_branch.name] = list(learners.values('id', 'username', 'first_name', 'last_name'))
            
            # Get groups in their branch (only if they have manage_groups capability)
            if PermissionManager.user_has_capability(user, 'manage_groups'):
                groups = BranchGroup.objects.filter(branch=user_branch)
                user_groups = groups.values('id', 'name')
            else:
                user_groups = []
        else:
            # No branch assignment, no access
            branch_users = {}
            user_groups = []
    
    elif user.role == 'learner':
        # Learner: SELF access - can only message instructors and peers in their branch
        if user_branch:
            # Get instructors and other learners in their branch
            accessible_users = CustomUser.objects.filter(
                branch=user_branch,
                role__in=['instructor', 'admin', 'learner']
            ).exclude(id=user.id)  # Exclude self
            
            branch_users[user_branch.name] = list(accessible_users.values('id', 'username', 'first_name', 'last_name'))
            
            # Learners cannot access groups directly
            user_groups = []
        else:
            # No branch assignment, no access
            branch_users = {}
            user_groups = []
    
    else:
        # Unknown role, no access
        branch_users = {}
        user_groups = []
    
    # Define breadcrumbs
    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': reverse('lms_messages:messages'), 'label': 'Messages', 'icon': 'fa-envelope'},
        {'label': 'New Message', 'icon': 'fa-paper-plane'}
    ]
    
    if request.method == 'POST':
        form = ComposeForm(request.POST)
        if form.is_valid():
            # Get form data
            recipient_ids = set()
            group_id = None
            

            # Process group recipients (for instructors/admins)
            group_id = request.POST.get('user_group')
            if group_id:
                try:
                    group = BranchGroup.objects.get(id=group_id)
                    # RBAC v0.1 Validation: Check if user can access this group
                    if _can_user_access_group(user, group):
                        # Add all users from the group
                        group_user_ids = [str(u.user.id) for u in group.memberships.all()]
                        # Filter group users to only those the user can message
                        valid_recipients = []
                        for user_id in group_user_ids:
                            try:
                                potential_recipient = CustomUser.objects.get(id=user_id)
                                if _can_user_message_recipient(user, potential_recipient):
                                    valid_recipients.append(user_id)
                            except CustomUser.DoesNotExist:
                                continue
                        recipient_ids.update(valid_recipients)
                        # Mark this as a group message
                        sent_to_group = group
                    else:
                        form.add_error(None, 'You do not have permission to access this group.')
                except BranchGroup.DoesNotExist:
                    form.add_error(None, 'Selected group does not exist.')
            
            # Process selected individual recipients
            for key in request.POST.getlist('recipients[]'):
                if key.startswith('branch_'):
                    # If a branch is selected, add all users from that branch
                    branch_name = key.replace('branch_', '')
                    branch_user_ids = [str(user['id']) for user in branch_users.get(branch_name, [])]
                    # Filter branch users to only those the user can message
                    valid_recipients = []
                    for user_id in branch_user_ids:
                        try:
                            potential_recipient = CustomUser.objects.get(id=user_id)
                            if _can_user_message_recipient(user, potential_recipient):
                                valid_recipients.append(user_id)
                        except CustomUser.DoesNotExist:
                            continue
                    recipient_ids.update(valid_recipients)
                else:
                    # Individual user selection - validate access
                    try:
                        potential_recipient = CustomUser.objects.get(id=key)
                        if _can_user_message_recipient(user, potential_recipient):
                            recipient_ids.add(key)
                        else:
                            form.add_error(None, f'You do not have permission to message {potential_recipient.get_full_name() or potential_recipient.username}.')
                    except CustomUser.DoesNotExist:
                        form.add_error(None, f'Invalid recipient selected.')
            
            subject = request.POST.get('subject', '')
            content = form.cleaned_data['content']
            
            try:
                # Get recipients
                recipients = CustomUser.objects.filter(id__in=recipient_ids)
                if not recipients.exists():
                    form.add_error('recipients', 'Please select at least one recipient')
                else:
                    # Create message
                    message = Message.objects.create(
                        subject=subject,
                        content=content,
                        sender=request.user,
                        branch=user_branch,
                        is_course_message=False,
                        related_course=None,
                        parent_message=reply_to_message if reply_to_message else None
                    )
                    message.recipients.set(recipients)
                    
                    return redirect('lms_messages:messages')
            
            except Exception as e:
                form.add_error(None, f'Error sending message: {str(e)}')
    
    context = {
        'form': form,
        'branch_users': branch_users,
        'user_groups': user_groups,
        'user_role': user.role,
        'breadcrumbs': breadcrumbs,
        'reply_to_message': reply_to_message,
        'initial_subject': initial_subject,
        'initial_recipients': initial_recipients
    }
    return render(request, 'lms_messages/new_message.html', context)

@login_required
@require_POST
def mark_as_read(request, message_id):
    """Mark a message as read"""
    message = get_object_or_404(
        Message.objects.filter(recipients=request.user),
        id=message_id
    )
    
    status = message.mark_read(request.user)
    
    return JsonResponse({
        'status': 'success',
        'is_read': status.is_read
    })

@login_required
@require_POST
def mark_all_as_read(request):
    """Mark all messages as read for the current user"""
    unread_messages = Message.objects.filter(
        recipients=request.user
    ).exclude(
        read_statuses__user=request.user,
        read_statuses__is_read=True
    )
    
    now = timezone.now()
    read_statuses = []
    
    for message in unread_messages:
        status, created = MessageReadStatus.objects.get_or_create(
            message=message,
            user=request.user,
            defaults={'is_read': True, 'read_at': now}
        )
        if not created and not status.is_read:
            status.is_read = True
            status.read_at = now
            status.save()
        read_statuses.append(status)
    
    return JsonResponse({
        'status': 'success',
        'count': len(read_statuses)
    })

@login_required
def message_count_api(request):
    """API endpoint for message count"""
    if not request.user.is_authenticated:
        return JsonResponse({
            'unread_count': 0,
            'total_count': 0,
        })
    
    # Get unread messages count for the user
    unread_count = Message.objects.filter(
        Q(recipients=request.user) & ~Q(sender=request.user)
    ).exclude(
        read_statuses__user=request.user,
        read_statuses__is_read=True
    ).distinct().count()
    
    # Get total messages count for the user
    total_count = Message.objects.filter(
        Q(sender=request.user) | Q(recipients=request.user)
    ).distinct().count()
    
    return JsonResponse({
        'unread_count': unread_count,
        'total_count': total_count,
    })

@login_required
@require_POST
def reply_message(request, message_id):
    """Handle simple reply to a message - comment style"""
    from role_management.utils import PermissionManager
    from django.http import HttpResponseForbidden
    
    # RBAC v0.1 Validation: Check if user has create_messages capability
    if not PermissionManager.user_has_capability(request.user, 'create_messages'):
        return HttpResponseForbidden("Access denied: You don't have permission to reply to messages")
    
    # Get the original message
    original_message = get_object_or_404(Message, id=message_id)
    
    # Check if user has permission to view the original message
    if request.user != original_message.sender and request.user not in original_message.recipients.all():
        messages.error(request, "You don't have permission to reply to this message.")
        return redirect('lms_messages:messages')
    
    # Get reply content
    content = request.POST.get('content', '').strip()
    if not content:
        messages.error(request, "Reply content cannot be empty.")
        return redirect('lms_messages:message_detail', message_id=message_id)
    
    try:
        # Create reply message
        reply = Message.objects.create(
            subject=f"Re: {original_message.subject}",
            content=content,
            sender=request.user,
            parent_message=original_message,
            branch=request.user.branch,
            is_course_message=original_message.is_course_message,
            related_course=original_message.related_course,
            sent_to_group=original_message.sent_to_group
        )
        
        # Add recipients - reply to sender and all original recipients, excluding the current user
        recipients = set()
        recipients.add(original_message.sender)
        recipients.update(original_message.recipients.all())
        recipients.discard(request.user)  # Don't send to self
        
        # Validate recipients based on RBAC
        valid_recipients = []
        for recipient in recipients:
            if _can_user_message_recipient(request.user, recipient):
                valid_recipients.append(recipient)
        
        if valid_recipients:
            reply.recipients.set(valid_recipients)
            messages.success(request, "Your reply has been sent successfully.")
        else:
            # If no valid recipients, delete the reply
            reply.delete()
            messages.error(request, "You don't have permission to send replies to any of the message participants.")
    
    except Exception as e:
        messages.error(request, f"Error sending reply: {str(e)}")
    
    return redirect('lms_messages:message_detail', message_id=message_id)

@login_required
@require_POST
def delete_message(request, message_id):
    """Delete a message - only sender can delete their own messages"""
    message = get_object_or_404(Message, id=message_id)
    
    # Check if user is the sender of the message
    if request.user != message.sender:
        messages.error(request, "You can only delete messages you have sent.")
        return redirect('lms_messages:messages')
    
    try:
        # Delete the message
        message.delete()
        messages.success(request, "Message deleted successfully.")
    except Exception as e:
        messages.error(request, f"Error deleting message: {str(e)}")
    
    return redirect('lms_messages:messages')
