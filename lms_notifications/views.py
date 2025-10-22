from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.http import JsonResponse, Http404
from django.core.paginator import Paginator
from django.db.models import Q, Count
from django.utils import timezone
from django.views.decorators.http import require_POST, require_http_methods
from django.urls import reverse
from django.template.loader import render_to_string
from django.core.exceptions import PermissionDenied
from users.models import Branch
import json

from .models import (
    Notification, NotificationSettings, NotificationTypeSettings,
    NotificationType, BulkNotification, NotificationTemplate, NotificationLog
)
from .forms import (
    NotificationSettingsForm, NotificationTypeSettingsForm, NotificationTypeSettingsFormSet,
    BulkNotificationForm, NotificationTemplateForm, QuickNotificationForm, 
    NotificationFilterForm, EnhancedNotificationSettingsForm
)


def filter_notification_types_by_role(user_role):
    """
    Filter notification types by user role in a database-agnostic way.
    Returns a queryset of notification types that the user can access.
    """
    # Get all active notification types
    all_types = NotificationType.objects.filter(
        is_active=True
    )
    
    # Filter in Python to avoid database-specific JSON operations
    accessible_types = []
    for notification_type in all_types:
        available_roles = notification_type.available_to_roles
        
        # Allow if:
        # 1. available_to_roles is null or empty (available to all)
        # 2. user's role is in the available_to_roles list
        if (not available_roles or 
            available_roles == [] or 
            user_role in available_roles):
            accessible_types.append(notification_type.id)
    
    # Return filtered queryset
    return all_types.filter(id__in=accessible_types)


def is_admin_or_instructor(user):
    """Check if user is admin or instructor"""
    return user.is_authenticated and user.role in ['globaladmin', 'admin', 'superadmin', 'instructor']


def is_admin(user):
    """Check if user is admin"""
    return user.is_authenticated and user.role in ['globaladmin', 'admin', 'superadmin']


@login_required
def notification_center(request):
    """Main notification center view"""
    # Get user's notifications with explicit user verification and additional safety checks
    current_user = request.user
    
    # Ensure user is properly authenticated and has an ID
    if not current_user.is_authenticated or not current_user.id:
        from django.contrib.auth import logout
        logout(request)
        return redirect('users:login')
    
    # Get notifications with explicit user ID filtering for maximum safety
    notifications = Notification.objects.filter(
        recipient_id=current_user.id  # Use explicit ID filtering instead of object reference
    ).select_related(
        'notification_type', 'sender', 'related_course'
    ).order_by('-created_at')
    
    # Filter options
    filter_type = request.GET.get('type', 'all')
    priority = request.GET.get('priority')
    is_read = request.GET.get('read')
    
    if filter_type == 'unread':
        notifications = notifications.filter(is_read=False)
    elif filter_type == 'read':
        notifications = notifications.filter(is_read=True)
    
    if priority:
        notifications = notifications.filter(priority=priority)
    
    if is_read is not None:
        notifications = notifications.filter(is_read=is_read == 'true')
    
    # Search
    search = request.GET.get('search')
    if search:
        notifications = notifications.filter(
            Q(title__icontains=search) |
            Q(short_message__icontains=search) |
            Q(sender__username__icontains=search)
        )
    
    # Pagination
    paginator = Paginator(notifications, 20)
    page_number = request.GET.get('page')
    notifications_page = paginator.get_page(page_number)
    
    # Get notification counts - calculate all statistics for the current user using explicit ID filtering
    user_notifications = Notification.objects.filter(recipient_id=current_user.id)
    
    total_count = user_notifications.count()
    unread_count = user_notifications.filter(is_read=False).count()
    read_count = user_notifications.filter(is_read=True).count()
    urgent_count = user_notifications.filter(priority='urgent').count()
    
    # Breadcrumbs
    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'label': 'Notification Center', 'icon': 'fa-bell'}
    ]
    
    context = {
        'notifications': notifications_page,
        'total_count': total_count,
        'unread_count': unread_count,
        'read_count': read_count,
        'urgent_count': urgent_count,
        'filter_type': filter_type,
        'priority': priority,
        'is_read': is_read,
        'search': search,
        'priority_choices': Notification.PRIORITY_CHOICES,
        'breadcrumbs': breadcrumbs,
    }
    return render(request, 'lms_notifications/notification_center.html', context)


@login_required
def unread_notifications(request):
    """View for unread notifications only"""
    # Ensure user authentication
    if not request.user.is_authenticated or not request.user.id:
        return redirect('users:login')
        
    notifications = Notification.objects.filter(
        recipient_id=request.user.id,  # Use explicit ID filtering
        is_read=False
    ).select_related(
        'notification_type', 'sender', 'related_course'
    ).order_by('-created_at')
    
    # Pagination
    paginator = Paginator(notifications, 20)
    page_number = request.GET.get('page')
    notifications_page = paginator.get_page(page_number)
    
    context = {
        'notifications': notifications_page,
        'page_title': 'Unread Notifications',
        'filter_type': 'unread',
    }
    return render(request, 'lms_notifications/notification_list.html', context)


@login_required
def all_notifications(request):
    """View for all notifications"""
    # Ensure user authentication
    if not request.user.is_authenticated or not request.user.id:
        return redirect('users:login')
        
    notifications = Notification.objects.filter(
        recipient_id=request.user.id  # Use explicit ID filtering
    ).select_related(
        'notification_type', 'sender', 'related_course'
    ).order_by('-created_at')
    
    # Pagination
    paginator = Paginator(notifications, 20)
    page_number = request.GET.get('page')
    notifications_page = paginator.get_page(page_number)
    
    context = {
        'notifications': notifications_page,
        'page_title': 'All Notifications',
        'filter_type': 'all',
    }
    return render(request, 'lms_notifications/notification_list.html', context)


@login_required
@require_POST
def mark_notification_read(request, notification_id):
    """Mark a single notification as read"""
    # Ensure user authentication
    if not request.user.is_authenticated or not request.user.id:
        return redirect('users:login')
        
    notification = get_object_or_404(
        Notification, 
        id=notification_id, 
        recipient_id=request.user.id  # Use explicit ID filtering
    )
    
    notification.mark_as_read()
    
    # Log the action
    NotificationLog.objects.create(
        notification=notification,
        action='read',
        user=request.user
    )
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True})
    
    messages.success(request, 'Notification marked as read.')
    return redirect('lms_notifications:notification_center')


@login_required
@require_POST
def delete_notification(request, notification_id):
    """Delete a single notification"""
    # Ensure user authentication
    if not request.user.is_authenticated or not request.user.id:
        return redirect('users:login')
        
    notification = get_object_or_404(
        Notification, 
        id=notification_id, 
        recipient_id=request.user.id  # Use explicit ID filtering
    )
    
    # Log the action
    NotificationLog.objects.create(
        notification=notification,
        action='deleted',
        user=request.user
    )
    
    notification.delete()
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True})
    
    messages.success(request, 'Notification deleted.')
    return redirect('lms_notifications:notification_center')


@login_required
@require_POST
def mark_all_read(request):
    """Mark all notifications as read"""
    # Ensure user authentication
    if not request.user.is_authenticated or not request.user.id:
        return redirect('users:login')
        
    count = Notification.objects.filter(
        recipient_id=request.user.id,  # Use explicit ID filtering
        is_read=False
    ).update(is_read=True, read_at=timezone.now())
    
    messages.success(request, f'Marked {count} notifications as read.')
    return redirect('lms_notifications:notification_center')


@login_required
@require_POST
def delete_all_read(request):
    """Delete all read notifications"""
    # Ensure user authentication
    if not request.user.is_authenticated or not request.user.id:
        return redirect('users:login')
        
    count = Notification.objects.filter(
        recipient_id=request.user.id,  # Use explicit ID filtering
        is_read=True
    ).delete()[0]
    
    messages.success(request, f'Deleted {count} read notifications.')
    return redirect('lms_notifications:notification_center')


@login_required
def notification_settings(request):
    """Enhanced user notification settings"""
    settings_obj, created = NotificationSettings.objects.get_or_create(
        user=request.user
    )
    
    if request.method == 'POST':
        form = EnhancedNotificationSettingsForm(request.POST, instance=settings_obj)
        
        # Handle individual notification type settings
        notification_types = filter_notification_types_by_role(request.user.role)
        
        for notification_type in notification_types:
            # Get or create individual settings
            type_settings, _ = NotificationTypeSettings.objects.get_or_create(
                user=request.user,
                notification_type=notification_type,
                defaults={
                    'email_enabled': notification_type.default_email_enabled,
                    'web_enabled': notification_type.default_web_enabled,
                }
            )
            
            # Update settings from form data
            email_key = f'type_{notification_type.id}_email'
            web_key = f'type_{notification_type.id}_web'
            
            type_settings.email_enabled = email_key in request.POST
            type_settings.web_enabled = web_key in request.POST
            type_settings.save()
        
        # Handle certificate expiry reminder intervals
        intervals_json = request.POST.get('certificate_expiry_intervals_json', '[]')
        try:
            intervals = json.loads(intervals_json)
            if isinstance(intervals, list):
                # Filter valid intervals (positive integers)
                valid_intervals = [int(i) for i in intervals if isinstance(i, (int, str)) and int(i) > 0]
                settings_obj.certificate_expiry_reminder_intervals = valid_intervals
        except (json.JSONDecodeError, ValueError):
            pass  # Keep existing intervals if parsing fails
        
        if form.is_valid():
            form.save()
            messages.success(request, 'Notification settings updated successfully.')
            return redirect('lms_notifications:settings')
    else:
        form = EnhancedNotificationSettingsForm(instance=settings_obj)
    
    # Get available notification types for current user's role
    notification_types = filter_notification_types_by_role(request.user.role).order_by('display_name')
    
    # Get existing user settings for each notification type
    notification_types_with_settings = []
    for notification_type in notification_types:
        type_settings, _ = NotificationTypeSettings.objects.get_or_create(
            user=request.user,
            notification_type=notification_type,
            defaults={
                'email_enabled': notification_type.default_email_enabled,
                'web_enabled': notification_type.default_web_enabled,
            }
        )
        notification_types_with_settings.append({
            'type': notification_type,
            'settings': type_settings
        })
    
    # Breadcrumbs
    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': reverse('lms_notifications:notification_center'), 'label': 'Notification Center', 'icon': 'fa-bell'},
        {'label': 'Settings', 'icon': 'fa-cog'}
    ]
    
    context = {
        'form': form,
        'notification_types_with_settings': notification_types_with_settings,
        'breadcrumbs': breadcrumbs,
    }
    return render(request, 'lms_notifications/settings.html', context)


@login_required
@require_POST
def send_test_email(request):
    """Send a test email for a specific notification type"""
    try:
        notification_type_id = request.POST.get('notification_type_id')
        
        if not notification_type_id:
            return JsonResponse({
                'success': False, 
                'message': 'Notification type ID is required'
            }, status=400)
        
        # Get the notification type
        notification_type = get_object_or_404(
            NotificationType.objects.filter(is_active=True), 
            id=notification_type_id
        )
        
        # Check if user has access to this notification type
        user_role = request.user.role
        if (notification_type.available_to_roles and 
            user_role not in notification_type.available_to_roles):
            return JsonResponse({
                'success': False,
                'message': 'You do not have access to this notification type'
            }, status=403)
        
        # Check if user has email enabled for this notification type
        type_settings, _ = NotificationTypeSettings.objects.get_or_create(
            user=request.user,
            notification_type=notification_type,
            defaults={
                'email_enabled': notification_type.default_email_enabled,
                'web_enabled': notification_type.default_web_enabled,
            }
        )
        
        if not type_settings.email_enabled:
            return JsonResponse({
                'success': False,
                'message': f'Email notifications are disabled for {notification_type.display_name}'
            }, status=400)
        
        # Import the send_notification utility
        from .utils import send_notification
        
        # Send test notification
        test_notification = send_notification(
            recipient=request.user,
            notification_type_name=notification_type.name,
            title=f'🧪 Test: {notification_type.display_name}',
            message=f'''<h2>Test Email for {notification_type.display_name}</h2>
            
<p>This is a test email to verify that your <strong>{notification_type.display_name}</strong> notifications are working correctly.</p>

<h3>Test Details:</h3>
<ul>
    <li><strong>Notification Type:</strong> {notification_type.display_name}</li>
    <li><strong>Description:</strong> {notification_type.description}</li>
    <li><strong>Test Time:</strong> {timezone.now().strftime("%Y-%m-%d %H:%M:%S")}</li>
    <li><strong>Sent To:</strong> {request.user.email}</li>
    <li><strong>User Role:</strong> {request.user.get_role_display()}</li>
</ul>

<p>If you received this email, your {notification_type.display_name} notifications are configured correctly!</p>

<p><small>This is an automated test email from your LMS notification system.</small></p>''',
            short_message=f'Test email for {notification_type.display_name} notifications',
            send_email=True,
            priority='normal'
        )
        
        if test_notification:
            # Check if email was sent successfully
            test_notification.refresh_from_db()
            if test_notification.email_sent:
                return JsonResponse({
                    'success': True,
                    'message': f'Test email for {notification_type.display_name} sent successfully to {request.user.email}'
                })
            else:
                error_msg = test_notification.email_error or 'Unknown error occurred'
                return JsonResponse({
                    'success': False,
                    'message': f'Failed to send test email: {error_msg}'
                })
        else:
            return JsonResponse({
                'success': False,
                'message': 'Failed to create test notification'
            })
            
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Error sending test email: {str(e)}'
        }, status=500)


@login_required
@user_passes_test(is_admin_or_instructor)
def bulk_notification_list(request):
    """List bulk notifications"""
    bulk_notifications = BulkNotification.objects.filter(
        sender=request.user
    ).order_by('-created_at')
    
    # Pagination
    paginator = Paginator(bulk_notifications, 20)
    page_number = request.GET.get('page')
    bulk_notifications_page = paginator.get_page(page_number)
    
    # Breadcrumbs
    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': reverse('lms_notifications:notification_center'), 'label': 'Notifications', 'icon': 'fa-bell'},
        {'label': 'Bulk Notifications', 'icon': 'fa-bullhorn'}
    ]
    
    context = {
        'bulk_notifications': bulk_notifications_page,
        'breadcrumbs': breadcrumbs,
    }
    return render(request, 'lms_notifications/bulk_notification_list.html', context)


@login_required
@user_passes_test(is_admin_or_instructor)
def bulk_notification_create(request):
    """Create new bulk notification"""
    if request.method == 'POST':
        form = BulkNotificationForm(request.POST, user=request.user)
        if form.is_valid():
            bulk_notification = form.save(commit=False)
            bulk_notification.sender = request.user
            bulk_notification.save()
            form.save_m2m()  # Save many-to-many relationships
            
            messages.success(request, 'Bulk notification created successfully.')
            return redirect('lms_notifications:bulk_notification_list')
    else:
        form = BulkNotificationForm(user=request.user)
    
    # Breadcrumbs
    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': reverse('lms_notifications:notification_center'), 'label': 'Notifications', 'icon': 'fa-bell'},
        {'url': reverse('lms_notifications:bulk_notification_list'), 'label': 'Bulk Notifications', 'icon': 'fa-bullhorn'},
        {'label': 'Create', 'icon': 'fa-plus'}
    ]
    
    context = {
        'form': form,
        'action': 'Create',
        'breadcrumbs': breadcrumbs,
    }
    return render(request, 'lms_notifications/bulk_notification_form.html', context)


@login_required
@user_passes_test(is_admin_or_instructor)
def bulk_notification_edit(request, bulk_id):
    """Edit bulk notification"""
    bulk_notification = get_object_or_404(
        BulkNotification, 
        id=bulk_id, 
        sender=request.user
    )
    
    if bulk_notification.status != 'draft':
        messages.error(request, 'Cannot edit a bulk notification that has already been sent.')
        return redirect('lms_notifications:bulk_notification_list')
    
    if request.method == 'POST':
        form = BulkNotificationForm(
            request.POST, 
            instance=bulk_notification, 
            user=request.user
        )
        if form.is_valid():
            form.save()
            messages.success(request, 'Bulk notification updated successfully.')
            return redirect('lms_notifications:bulk_notification_list')
    else:
        form = BulkNotificationForm(instance=bulk_notification, user=request.user)
    
    # Breadcrumbs
    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': reverse('lms_notifications:notification_center'), 'label': 'Notifications', 'icon': 'fa-bell'},
        {'url': reverse('lms_notifications:bulk_notification_list'), 'label': 'Bulk Notifications', 'icon': 'fa-bullhorn'},
        {'label': 'Edit', 'icon': 'fa-edit'}
    ]
    
    context = {
        'form': form,
        'action': 'Edit',
        'bulk_notification': bulk_notification,
        'breadcrumbs': breadcrumbs,
    }
    return render(request, 'lms_notifications/bulk_notification_form.html', context)


@login_required
@user_passes_test(is_admin_or_instructor)
@require_POST
def bulk_notification_send(request, bulk_id):
    """Send bulk notification"""
    bulk_notification = get_object_or_404(
        BulkNotification, 
        id=bulk_id, 
        sender=request.user
    )
    
    if bulk_notification.status != 'draft':
        messages.error(request, 'This bulk notification has already been sent or is in progress.')
        return redirect('lms_notifications:bulk_notification_list')
    
    # Send the notification
    bulk_notification.send_notifications()
    
    # Log the action
    NotificationLog.objects.create(
        bulk_notification=bulk_notification,
        action='bulk_sent',
        user=request.user,
        details={'total_recipients': bulk_notification.total_recipients}
    )
    
    messages.success(
        request, 
        f'Bulk notification sent to {bulk_notification.total_recipients} recipients.'
    )
    return redirect('lms_notifications:bulk_notification_list')


@login_required
@user_passes_test(is_admin_or_instructor)
def bulk_notification_preview(request, bulk_id):
    """Preview bulk notification recipients"""
    bulk_notification = get_object_or_404(
        BulkNotification, 
        id=bulk_id, 
        sender=request.user
    )
    
    recipients = bulk_notification.get_recipients()
    
    # Breadcrumbs
    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': reverse('lms_notifications:notification_center'), 'label': 'Notifications', 'icon': 'fa-bell'},
        {'url': reverse('lms_notifications:bulk_notification_list'), 'label': 'Bulk Notifications', 'icon': 'fa-bullhorn'},
        {'label': 'Preview', 'icon': 'fa-eye'}
    ]
    
    context = {
        'bulk_notification': bulk_notification,
        'recipients': recipients[:50],  # Show first 50 for preview
        'total_recipients': len(recipients),
        'breadcrumbs': breadcrumbs,
    }
    return render(request, 'lms_notifications/bulk_notification_preview.html', context)


@login_required
@user_passes_test(is_admin_or_instructor)
@require_POST
def bulk_notification_delete(request, bulk_id):
    """Delete bulk notification"""
    bulk_notification = get_object_or_404(
        BulkNotification, 
        id=bulk_id, 
        sender=request.user
    )
    
    bulk_notification.delete()
    messages.success(request, 'Bulk notification deleted successfully.')
    return redirect('lms_notifications:bulk_notification_list')


@login_required
@user_passes_test(is_admin)
def notification_template_list(request):
    """List notification templates"""
    templates = NotificationTemplate.objects.filter(
        is_active=True
    ).order_by('name')
    
    context = {
        'templates': templates,
    }
    return render(request, 'lms_notifications/template_list.html', context)


@login_required
@user_passes_test(is_admin)
def notification_template_create(request):
    """Create notification template"""
    if request.method == 'POST':
        form = NotificationTemplateForm(request.POST)
        if form.is_valid():
            template = form.save(commit=False)
            template.created_by = request.user
            template.save()
            messages.success(request, 'Notification template created successfully.')
            return redirect('lms_notifications:template_list')
    else:
        form = NotificationTemplateForm()
    
    context = {
        'form': form,
        'action': 'Create',
    }
    return render(request, 'lms_notifications/template_form.html', context)


@login_required
@user_passes_test(is_admin)
def notification_template_edit(request, template_id):
    """Edit notification template"""
    template = get_object_or_404(NotificationTemplate, id=template_id)
    
    if request.method == 'POST':
        form = NotificationTemplateForm(request.POST, instance=template)
        if form.is_valid():
            form.save()
            messages.success(request, 'Notification template updated successfully.')
            return redirect('lms_notifications:template_list')
    else:
        form = NotificationTemplateForm(instance=template)
    
    context = {
        'form': form,
        'action': 'Edit',
        'template': template,
    }
    return render(request, 'lms_notifications/template_form.html', context)


@login_required
@user_passes_test(is_admin)
@require_POST
def notification_template_delete(request, template_id):
    """Delete notification template"""
    template = get_object_or_404(NotificationTemplate, id=template_id)
    template.delete()
    messages.success(request, 'Notification template deleted successfully.')
    return redirect('lms_notifications:template_list')


# API Views

@login_required
def notification_count_api(request):
    """API endpoint for notification count"""
    # Ensure user authentication
    if not request.user.is_authenticated or not request.user.id:
        return JsonResponse({'error': 'Authentication required'}, status=401)
        
    notifications = Notification.objects.filter(recipient_id=request.user.id)
    
    unread_count = notifications.filter(is_read=False).count()
    urgent_count = notifications.filter(is_read=False, priority='urgent').count()
    total_count = notifications.count()
    
    return JsonResponse({
        'unread_count': unread_count,
        'urgent_count': urgent_count,
        'total_count': total_count,
    })


@login_required
def recent_notifications_api(request):
    """API endpoint for recent notifications"""
    # Ensure user authentication
    if not request.user.is_authenticated or not request.user.id:
        return JsonResponse({'error': 'Authentication required'}, status=401)
        
    notifications = Notification.objects.filter(
        recipient_id=request.user.id
    ).select_related(
        'notification_type', 'sender'
    ).order_by('-created_at')[:10]
    
    data = []
    for notification in notifications:
        data.append({
            'id': notification.id,
            'title': notification.title,
            'short_message': notification.short_message,
            'is_read': notification.is_read,
            'priority': notification.priority,
            'created_at': notification.created_at.isoformat(),
            'sender': notification.sender.username if notification.sender else 'System',
            'action_url': notification.action_url,
            'action_text': notification.action_text,
        })
    
    return JsonResponse({
        'notifications': data,
    })


@login_required
@require_POST
def mark_read_api(request, notification_id):
    """API endpoint to mark notification as read"""
    # Ensure user authentication
    if not request.user.is_authenticated or not request.user.id:
        return JsonResponse({'success': False, 'error': 'Authentication required'})
        
    try:
        notification = Notification.objects.get(
            id=notification_id,
            recipient_id=request.user.id  # Use explicit ID filtering
        )
        notification.mark_as_read()
        
        # Log the action
        NotificationLog.objects.create(
            notification=notification,
            action='read',
            user=request.user
        )
        
        return JsonResponse({'success': True})
    except Notification.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Notification not found'})


@login_required
@user_passes_test(is_admin_or_instructor)
def bulk_preview_api(request):
    """API endpoint for bulk notification preview"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            recipient_type = data.get('recipient_type')
            target_roles = data.get('target_roles', [])
            target_branches = data.get('target_branches', [])
            target_groups = data.get('target_groups', [])
            target_courses = data.get('target_courses', [])
            
            # Create a temporary bulk notification to get recipients
            temp_bulk = BulkNotification(
                recipient_type=recipient_type,
                target_roles=target_roles,
                sender=request.user
            )
            
            # Simulate getting recipients without saving
            recipients = []
            if recipient_type == 'all_users':
                from users.models import CustomUser
                recipients = list(CustomUser.objects.filter(is_active=True))
            elif recipient_type == 'role' and target_roles:
                from users.models import CustomUser
                recipients = list(CustomUser.objects.filter(
                    role__in=target_roles, 
                    is_active=True
                ))
            # Add other recipient types as needed
            
            return JsonResponse({
                'success': True,
                'recipient_count': len(recipients),
                'recipients': [r.username for r in recipients[:10]]  # First 10 for preview
            })
            
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Invalid request'})


@login_required
@user_passes_test(is_admin)
def notification_reports(request):
    """Notification reports and statistics"""
    # Get statistics
    total_notifications = Notification.objects.count()
    unread_notifications = Notification.objects.filter(is_read=False).count()
    email_sent = Notification.objects.filter(email_sent=True).count()
    
    # Recent bulk notifications
    recent_bulk = BulkNotification.objects.order_by('-created_at')[:10]
    
    # Notification types usage
    type_stats = NotificationType.objects.annotate(
        notification_count=Count('notifications')
    ).order_by('-notification_count')
    
    context = {
        'total_notifications': total_notifications,
        'unread_notifications': unread_notifications,
        'email_sent': email_sent,
        'recent_bulk': recent_bulk,
        'type_stats': type_stats,
    }
    return render(request, 'lms_notifications/reports.html', context)


@login_required
@user_passes_test(is_admin)
def notification_analytics(request):
    """Detailed notification analytics"""
    # This would include charts, graphs, and detailed analytics
    # For now, return basic data
    context = {
        'page_title': 'Notification Analytics',
    }
    return render(request, 'lms_notifications/analytics.html', context)


@login_required
def notification_type_settings(request, type_id):
    """Individual notification type settings"""
    notification_type = get_object_or_404(NotificationType, id=type_id)
    
    # Check if user has access to this notification type
    if (notification_type.available_to_roles and 
        request.user.role not in notification_type.available_to_roles):
        raise Http404("Notification type not found")
    
    settings_obj, created = NotificationTypeSettings.objects.get_or_create(
        user=request.user,
        notification_type=notification_type,
        defaults={
            'email_enabled': notification_type.default_email_enabled,
            'web_enabled': notification_type.default_web_enabled,
        }
    )
    
    if request.method == 'POST':
        email_enabled = request.POST.get('email_enabled') == 'on'
        web_enabled = request.POST.get('web_enabled') == 'on'
        
        settings_obj.email_enabled = email_enabled
        settings_obj.web_enabled = web_enabled
        settings_obj.save()
        
        messages.success(request, f'Settings for {notification_type.display_name} updated.')
        return redirect('lms_notifications:settings')
    
    context = {
        'notification_type': notification_type,
        'settings': settings_obj,
    }
    return render(request, 'lms_notifications/type_settings.html', context)


def is_global_admin(user):
    """Check if user is global admin"""
    return user.is_authenticated and user.role == 'globaladmin'


@login_required
@user_passes_test(is_global_admin)
def notification_admin_settings(request):
    """Global notification settings management for admin"""
    if request.method == 'POST':
        # Handle form submission for updating notification type settings
        for notification_type in NotificationType.objects.all():
            # Get the enabled status for each notification type
            enabled_key = f'notification_{notification_type.id}_enabled'
            is_enabled = request.POST.get(enabled_key) == 'on'
            
            # Update the notification type
            notification_type.is_active = is_enabled
            notification_type.save()
        
        messages.success(request, 'Notification settings updated successfully.')
        return redirect('lms_notifications:admin_settings')
    
    # Get all notification types with their current settings
    notification_types = NotificationType.objects.all().order_by('display_name')
    
    # Organize notification types by category for better display
    categorized_types = {
        'Session & Account': [],
        'Course Activities': [],
        'Assignments & Assessments': [],
        'Communication': [],
        'System & Administrative': [],
    }
    
    # Categorize notification types
    for nt in notification_types:
        if nt.name in ['account_Session', 'system_maintenance']:
            categorized_types['Session & Account'].append(nt)
        elif nt.name in ['course_enrollment', 'course_announcement', 'course_completion', 'conference_reminder', 'enrollment_approved', 'enrollment_rejected']:
            categorized_types['Course Activities'].append(nt)
        elif nt.name in ['assignment_due', 'assignment_graded', 'quiz_available', 'quiz_reminder', 'certificate_earned']:
            categorized_types['Assignments & Assessments'].append(nt)
        elif nt.name in ['message_received', 'discussion_reply', 'instructor_feedback', 'bulk_announcement']:
            categorized_types['Communication'].append(nt)
        else:
            categorized_types['System & Administrative'].append(nt)
    
    # Breadcrumbs
    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': reverse('lms_notifications:notification_center'), 'label': 'Notifications', 'icon': 'fa-bell'},
        {'label': 'Admin Settings', 'icon': 'fa-cogs'}
    ]
    
    context = {
        'notification_types': notification_types,
        'categorized_types': categorized_types,
        'breadcrumbs': breadcrumbs,
    }
    
    return render(request, 'lms_notifications/admin_settings.html', context)






