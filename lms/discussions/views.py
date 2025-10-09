from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseForbidden
from django.contrib import messages
from .models import Discussion, Comment, Attachment
from courses.models import Course
from lms_rubrics.models import Rubric, RubricEvaluation, RubricCriterion, RubricRating, RubricOverallFeedback
from django.urls import reverse
from django.core.exceptions import ValidationError
from django.views.decorators.http import require_POST
import mimetypes
from django.db import models
from django.core.paginator import Paginator
from users.models import CustomUser
from django.db.models import Q
from django.utils.html import strip_tags
import json
import os
import uuid
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.conf import settings
import logging
from django.contrib.auth import get_user_model
from core.rbac_validators import ConditionalAccessValidator
from django.utils.html import strip_tags

CustomUser = get_user_model()

logger = logging.getLogger(__name__)

def get_safe_file_size(file_field):
    """
    Safely get file size without raising FileNotFoundError
    Returns 0 if file doesn't exist or can't be accessed
    """
    try:
        if file_field and hasattr(file_field, 'size') and file_field.name:
            return file_field.size
    except (FileNotFoundError, OSError, ValueError):
        # File doesn't exist on disk or other file access error
        pass
    return 0

@login_required
def discussion_list(request):
    """View to display list of discussions"""
    # RBAC v0.1 Compliant Access Control
    from core.rbac_validators import rbac_validator
    
    if request.user.role == 'globaladmin':
        # Global Admin: FULL access to all discussions
        discussions_list = Discussion.objects.all().order_by('-created_at')
        can_create = True
        can_edit = True
        
    elif request.user.role == 'superadmin':
        # Super Admin: CONDITIONAL access (business-scoped discussions)
        if hasattr(request.user, 'business_assignments'):
            assigned_businesses = request.user.business_assignments.filter(is_active=True).values_list('business', flat=True)
            discussions_list = Discussion.objects.filter(
                created_by__branch__business__in=assigned_businesses
            ).order_by('-created_at')
        else:
            discussions_list = Discussion.objects.none()
        can_create = True
        can_edit = True
        
    elif request.user.role == 'admin':
        # Branch Admin: CONDITIONAL access (branch-scoped discussions)
        if request.user.branch:
            discussions_list = Discussion.objects.filter(
                created_by__branch=request.user.branch
            ).order_by('-created_at')
        else:
            discussions_list = Discussion.objects.none()
        can_create = True
        can_edit = True
        
    elif request.user.role == 'instructor':
        # Instructor: CONDITIONAL access (own discussions + assigned courses + group-assigned courses)
        if request.user.branch:
            # Own discussions
            own_discussions = Discussion.objects.filter(created_by=request.user)
            
            # Discussions from directly assigned courses
            assigned_courses = Course.objects.filter(instructor=request.user)
            course_discussions = Discussion.objects.filter(course__in=assigned_courses)
            
            # Discussions from group-assigned courses
            group_assigned_courses = Course.objects.filter(
                accessible_groups__memberships__user=request.user,
                accessible_groups__memberships__is_active=True,
                accessible_groups__memberships__custom_role__name__icontains='instructor'
            )
            group_course_discussions = Discussion.objects.filter(course__in=group_assigned_courses)
            
            discussions_list = (own_discussions | course_discussions | group_course_discussions).distinct().order_by('-created_at')
        else:
            discussions_list = Discussion.objects.filter(created_by=request.user).order_by('-created_at')
        can_create = True
        can_edit = True
        
    else:  # learner
        # Learner: SELF access (enrolled courses only)
        enrolled_courses = Course.objects.filter(courseenrollment__user=request.user).values_list('id', flat=True)
        
        # Filter discussions to include:
        # 1. Published discussions with active topics
        # 2. Discussions directly linked to enrolled courses 
        # 3. Discussions linked to topics within enrolled courses
        discussions_list = Discussion.objects.filter(
            Q(status='published') & Q(topics__status='active') & (
                Q(course__in=enrolled_courses) |  # Direct course link
                Q(topics__coursetopic__course__in=enrolled_courses)  # Through topics
            )
        ).distinct().order_by('-created_at')
        can_create = False
        can_edit = False
    
    # Pagination
    paginator = Paginator(discussions_list, 10)  # Show 10 discussions per page
    page = request.GET.get('page')
    discussions = paginator.get_page(page)
    
    # Define breadcrumbs
    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'label': 'Discussions', 'icon': 'fa-comments'}
    ]
    
    context = {
        'discussions': discussions,
        'title': 'Discussions',
        'breadcrumbs': breadcrumbs,
        'can_create': can_create,
        'can_edit': can_edit
    }
    return render(request, 'discussions/discussions.html', context)

@login_required
def new_discussion(request, course_id=None):
    """View to create a new discussion"""
    # RBAC v0.1 Compliant Access Control
    user = request.user
    can_create = False
    
    if user.role == 'globaladmin':
        can_create = True  # FULL access
    elif user.role == 'superadmin':
        can_create = True  # CONDITIONAL access (business-scoped)
    elif user.role == 'admin':
        can_create = True  # CONDITIONAL access (branch-scoped)
    elif user.role == 'instructor':
        can_create = True  # CONDITIONAL access (branch-scoped)
    
    if not can_create:
        return HttpResponseForbidden("You don't have permission to create discussions")
    
    # Get the course
    course = None
    if course_id:
        course = get_object_or_404(Course, id=course_id)
        
        # Additional validation for course access
        from core.rbac_validators import ConditionalAccessValidator
        if not ConditionalAccessValidator.validate_branch_access(user, course.branch if hasattr(course, 'branch') else None):
            return HttpResponseForbidden("You don't have permission to create discussions for this course")
    
    # Define breadcrumbs
    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': reverse('discussions:discussion_list'), 'label': 'Discussions', 'icon': 'fa-comments'},
        {'label': 'New Discussion', 'icon': 'fa-plus-circle'}
    ]
    
    if request.method == 'POST':
        title = request.POST.get('title')
        content = request.POST.get('content')
        instructions = request.POST.get('instructions', '')
        visibility = request.POST.get('visibility', 'public')
        files = request.FILES.getlist('attachments')
        rubric_id = request.POST.get('rubric')
        
        if title and content:
            discussion = Discussion.objects.create(
                title=title,
                content=content,
                instructions=instructions,
                created_by=request.user,
                visibility=visibility,
                course=course
            )
            
            # Set the rubric if one was selected
            if rubric_id:
                try:
                    rubric = Rubric.objects.get(id=rubric_id)
                    discussion.rubric = rubric
                    discussion.save()
                except Rubric.DoesNotExist:
                    pass
            
            # Handle file attachments
            for file in files:
                Attachment.objects.create(
                    discussion=discussion,
                    file=file,
                    file_type=get_file_type(file.name),
                    uploaded_by=request.user
                )
            
            messages.success(request, 'Discussion created successfully.')
            return redirect('discussions:discussion_detail', discussion_id=discussion.id)
        else:
            messages.error(request, 'Title and content are required.')
    
    # Get available rubrics - RBAC scoped
    user = request.user
    # Get available rubrics based on user role using centralized function
    from lms_rubrics.utils import get_filtered_rubrics_for_user
    available_rubrics = get_filtered_rubrics_for_user(user, course)
    
    context = {
        'title': 'New Discussion',
        'description': 'Create a new discussion',
        'breadcrumbs': breadcrumbs,
        'available_rubrics': available_rubrics,
        'course': course
    }
    return render(request, 'discussions/new_discussion.html', context)

@login_required
def discussion_detail(request, discussion_id):
    discussion = get_object_or_404(Discussion, id=discussion_id)
    comments = discussion.comments.all()
    
    # Define breadcrumbs for this view
    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': reverse('discussions:discussion_list'), 'label': 'Discussions', 'icon': 'fa-comments'},
        {'label': discussion.title, 'icon': 'fa-file-alt'}
    ]
    
    # Initialize context
    context = {
        'discussion': discussion,
        'comments': comments,
        'title': discussion.title,
        'description': 'Discussion details',
        'breadcrumbs': breadcrumbs
    }
    
    # Add rubric evaluation data for non-learners
    if discussion.rubric and (request.user.role in ['instructor', 'admin', 'superadmin'] or request.user.is_superuser):
        # Get the student ID from the query parameters if available
        student_id = request.GET.get('student_id')
        student = None
        
        if student_id:
            try:
                student = CustomUser.objects.get(id=student_id)
            except CustomUser.DoesNotExist:
                pass
                
        # Get all enrolled students if there's a course
        enrolled_students = []
        if discussion.course:
            enrolled_students = discussion.course.courseenrollment_set.filter(
                user__role='learner'
            ).select_related('user').values_list('user', flat=True)
            enrolled_students = CustomUser.objects.filter(id__in=enrolled_students)
        
        # Also include students who have participated in the discussion (commented)
        # This handles cases where discussions aren't tied to courses or students participate without formal enrollment
        participating_students = CustomUser.objects.filter(
            discussion_comments__discussion=discussion,
            role='learner'
        ).distinct()
        
        # Combine enrolled and participating students
        if enrolled_students:
            enrolled_students = enrolled_students.union(participating_students).distinct()
        else:
            enrolled_students = participating_students
        
        # Get existing evaluations for this discussion and student if selected
        evaluations = RubricEvaluation.objects.filter(discussion=discussion)
        if student:
            evaluations = evaluations.filter(student=student)
            
            # Get student interactions with this discussion
            student_comments = Comment.objects.filter(
                discussion=discussion,
                created_by=student
            ).select_related('parent')
            
            student_interactions = {
                'comment_count': student_comments.filter(parent__isnull=True).count(),
                'reply_count': student_comments.filter(parent__isnull=False).count(),
                'comments': student_comments.order_by('created_at'),
                'likes_given': student.liked_comments.filter(discussion=discussion).count() + (1 if student in discussion.likes.all() else 0),
            }
            
            context['student_interactions'] = student_interactions
        
        # Create a dictionary to store evaluations by criterion ID
        evaluation_data = {}
        for evaluation in evaluations:
            evaluation_data[evaluation.criterion.id] = evaluation
        
        # Add this data to the context
        context['can_evaluate_rubric'] = True
        context['rubric'] = discussion.rubric
        context['evaluation_data'] = evaluation_data
        context['enrolled_students'] = enrolled_students
        context['selected_student'] = student
        
        # Calculate the current total points
        total_points = sum(evaluation.points for evaluation in evaluations)
        context['total_points'] = total_points
        
        # Get existing overall feedback for selected student
        existing_feedback = None
        if student:
            try:
                existing_feedback = RubricOverallFeedback.objects.get(
                    discussion=discussion,
                    student=student
                )
            except RubricOverallFeedback.DoesNotExist:
                pass
        
        context['existing_feedback'] = existing_feedback
    else:
        context['can_evaluate_rubric'] = False
    
    # Add rubric evaluation data for learners (to view their feedback)
    if discussion.rubric and request.user.role == 'learner':
        # Get learner's rubric evaluation
        learner_evaluations = RubricEvaluation.objects.filter(
            discussion=discussion,
            student=request.user
        ).select_related('criterion', 'rating')
        
        # Get learner's overall feedback
        learner_overall_feedback = None
        try:
            learner_overall_feedback = RubricOverallFeedback.objects.get(
                discussion=discussion,
                student=request.user
            )
        except RubricOverallFeedback.DoesNotExist:
            pass
        
        # Create evaluation data for learner view
        learner_evaluation_data = {}
        total_learner_points = 0
        
        for evaluation in learner_evaluations:
            learner_evaluation_data[evaluation.criterion.id] = evaluation
            total_learner_points += evaluation.points
        
        # Add learner data to context
        context['learner_rubric_data'] = {
            'rubric': discussion.rubric,
            'evaluations': learner_evaluation_data,
            'total_points': total_learner_points,
            'overall_feedback': learner_overall_feedback,
            'has_evaluation': learner_evaluations.exists()
        }
    
    return render(request, 'discussions/discussion_detail.html', context)

@login_required
def edit_discussion(request, discussion_id):
    discussion = get_object_or_404(Discussion, id=discussion_id)
    
    # Define breadcrumbs for this view
    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': reverse('discussions:discussion_list'), 'label': 'Discussions', 'icon': 'fa-comments'},
        {'url': reverse('discussions:discussion_detail', kwargs={'discussion_id': discussion_id}), 'label': discussion.title, 'icon': 'fa-file-alt'},
        {'label': 'Edit', 'icon': 'fa-edit'}
    ]
    
    # Check if user has permission to edit this discussion
    is_admin = request.user.role in ['superadmin', 'admin', 'instructor'] or request.user.is_superuser
    is_creator = discussion.created_by == request.user
    
    if not (is_admin or is_creator):
        messages.error(request, 'You do not have permission to edit this discussion.')
        return redirect('discussions:discussion_detail', discussion_id=discussion.id)
    
    if request.method == 'POST':
        title = request.POST.get('title')
        content = request.POST.get('content')
        instructions = request.POST.get('instructions', '')
        visibility = request.POST.get('visibility', 'public')
        rubric_id = request.POST.get('rubric')
        
        if title and content:
            discussion.title = title
            discussion.content = content
            discussion.instructions = instructions
            discussion.visibility = visibility
            
            # Update the rubric if one was selected
            if rubric_id:
                try:
                    rubric = Rubric.objects.get(id=rubric_id)
                    discussion.rubric = rubric
                except Rubric.DoesNotExist:
                    discussion.rubric = None
            else:
                discussion.rubric = None
                
            discussion.save()
            
            messages.success(request, 'Discussion updated successfully.')
            return redirect('discussions:discussion_detail', discussion_id=discussion.id)
        else:
            messages.error(request, 'Please fill in all required fields.')
    
    # Get available rubrics based on user role
    user = request.user
    # Get available rubrics based on user role using centralized function
    from lms_rubrics.utils import get_filtered_rubrics_for_user
    course = discussion.course if hasattr(discussion, 'course') else None
    available_rubrics = get_filtered_rubrics_for_user(user, course)
    
    return render(request, 'discussions/edit_discussion.html', {
        'discussion': discussion,
        'title': f'Edit: {discussion.title}',
        'description': 'Edit discussion',
        'breadcrumbs': breadcrumbs,
        'available_rubrics': available_rubrics
    })

@login_required
def delete_discussion(request, discussion_id):
    discussion = get_object_or_404(Discussion, id=discussion_id)
    
    # Define breadcrumbs for this view
    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': reverse('discussions:discussion_list'), 'label': 'Discussions', 'icon': 'fa-comments'},
        {'url': reverse('discussions:discussion_detail', kwargs={'discussion_id': discussion_id}), 'label': discussion.title, 'icon': 'fa-file-alt'},
        {'label': 'Delete', 'icon': 'fa-trash'}
    ]
    
    # Check if user has permission to delete this discussion
    is_admin = request.user.role in ['superadmin', 'admin', 'instructor'] or request.user.is_superuser
    is_creator = discussion.created_by == request.user
    
    if not (is_admin or is_creator):
        messages.error(request, 'You do not have permission to delete this discussion.')
        return redirect('discussions:discussion_detail', discussion_id=discussion.id)
    
    if request.method == 'POST':
        discussion.delete()
        messages.success(request, 'Discussion deleted successfully.')
        return redirect('discussions:discussion_list')
    
    return render(request, 'discussions/delete_discussion.html', {
        'discussion': discussion,
        'title': f'Delete: {discussion.title}',
        'description': 'Delete discussion',
        'breadcrumbs': breadcrumbs
    })


@login_required
def clone_discussion(request, discussion_id):
    """View to clone an existing discussion"""
    original_discussion = get_object_or_404(Discussion, id=discussion_id)
    
    # Check permissions
    is_admin = request.user.role in ['superadmin', 'admin', 'instructor'] or request.user.is_superuser
    is_creator = original_discussion.created_by == request.user
    
    if not (is_admin or is_creator):
        messages.error(request, "You don't have permission to clone this discussion.")
        return redirect('discussions:discussion_list')
    
    try:
        with transaction.atomic():
            # Clone the discussion
            cloned_discussion = Discussion.objects.get(pk=original_discussion.pk)
            cloned_discussion.pk = None
            cloned_discussion.id = None
            cloned_discussion.title = f"{original_discussion.title} (Copy)"
            cloned_discussion.created_by = request.user
            cloned_discussion.created_at = timezone.now()
            cloned_discussion.updated_at = timezone.now()
            cloned_discussion.save()
            
            # Clone discussion-course relationships
            for discussion_course in DiscussionCourse.objects.filter(discussion=original_discussion):
                DiscussionCourse.objects.create(
                    discussion=cloned_discussion,
                    course=discussion_course.course,
                    topic=discussion_course.topic
                )
            
            # Clone discussion-topic relationships
            for topic_discussion in TopicDiscussion.objects.filter(discussion=original_discussion):
                TopicDiscussion.objects.create(
                    discussion=cloned_discussion,
                    topic=topic_discussion.topic,
                    course=topic_discussion.course
                )
            
            messages.success(request, f"Discussion '{original_discussion.title}' has been successfully cloned as '{cloned_discussion.title}'")
            return redirect('discussions:discussion_list')
            
    except Exception as e:
        logger.error(f"Error cloning discussion: {str(e)}", exc_info=True)
        messages.error(request, f"An error occurred while cloning the discussion: {str(e)}")
        return redirect('discussions:discussion_list')


@login_required
@require_POST
def toggle_discussion_like(request, discussion_id):
    discussion = get_object_or_404(Discussion, id=discussion_id)
    if request.user in discussion.likes.all():
        discussion.likes.remove(request.user)
        liked = False
    else:
        discussion.likes.add(request.user)
        liked = True
    
    return JsonResponse({
        'liked': liked,
        'likes_count': discussion.likes.count()
    })

@login_required
@require_POST
def toggle_comment_like(request, comment_id):
    comment = get_object_or_404(Comment, id=comment_id)
    if request.user in comment.likes.all():
        comment.likes.remove(request.user)
        liked = False
    else:
        comment.likes.add(request.user)
        liked = True
    
    return JsonResponse({
        'liked': liked,
        'likes_count': comment.likes.count()
    })

@login_required
def add_reply(request, discussion_id, comment_id):
    discussion = get_object_or_404(Discussion, id=discussion_id)
    parent_comment = get_object_or_404(Comment, id=comment_id, discussion=discussion)
    
    if request.method == 'POST':
        content = request.POST.get('content')
        files = request.FILES.getlist('attachments')
        
        if content:
            reply = Comment.objects.create(
                discussion=discussion,
                content=content,
                created_by=request.user,
                parent=parent_comment
            )
            
            # Handle attachments
            for file in files:
                file_type = get_file_type(file.name)
                Attachment.objects.create(
                    comment=reply,
                    file=file,
                    file_type=file_type,
                    uploaded_by=request.user
                )
            
            messages.success(request, 'Reply added successfully.')
        else:
            messages.error(request, 'Please enter a reply.')
    
    return redirect('discussions:discussion_detail', discussion_id=discussion.id)

def get_file_type(filename):
    import mimetypes
    mime_type, _ = mimetypes.guess_type(filename)
    
    # Check by mime type first
    if mime_type:
        if mime_type.startswith('image/'):
            return 'image'
        elif mime_type.startswith('video/'):
            return 'video'
        elif mime_type.startswith('audio/'):
            return 'audio'
    
    # Fallback to file extension for common audio formats
    filename_lower = filename.lower()
    audio_extensions = ['.mp3', '.wav', '.m4a', '.aac', '.ogg', '.flac', '.wma']
    
    for ext in audio_extensions:
        if filename_lower.endswith(ext):
            return 'audio'
    
    # Default to document for everything else
    return 'document'

@login_required
def add_comment(request, discussion_id):
    discussion = get_object_or_404(Discussion, id=discussion_id)
    
    if request.method == 'POST':
        content = request.POST.get('content')
        files = request.FILES.getlist('attachments')
        
        if content:
            comment = Comment.objects.create(
                discussion=discussion,
                content=content,
                created_by=request.user
            )
            
            # Handle attachments
            for file in files:
                file_type = get_file_type(file.name)
                Attachment.objects.create(
                    comment=comment,
                    file=file,
                    file_type=file_type,
                    uploaded_by=request.user
                )
            
            messages.success(request, 'Comment added successfully.')
        else:
            messages.error(request, 'Please enter a comment.')
    
    return redirect('discussions:discussion_detail', discussion_id=discussion.id)

@login_required
def edit_comment(request, discussion_id, comment_id):
    discussion = get_object_or_404(Discussion, id=discussion_id)
    comment = get_object_or_404(Comment, id=comment_id, discussion=discussion)
    
    # Check if user is the creator of the comment
    if comment.created_by != request.user:
        messages.error(request, 'You do not have permission to edit this comment.')
        return redirect('discussions:discussion_detail', discussion_id=discussion.id)
    
    if request.method == 'POST':
        content = request.POST.get('content')
        
        if content:
            comment.content = content
            comment.save()
            messages.success(request, 'Comment updated successfully.')
        else:
            messages.error(request, 'Please enter a comment.')
    
    return redirect('discussions:discussion_detail', discussion_id=discussion.id)

@login_required
def delete_comment(request, discussion_id, comment_id):
    discussion = get_object_or_404(Discussion, id=discussion_id)
    comment = get_object_or_404(Comment, id=comment_id, discussion=discussion)
    
    # Check if user is the creator of the comment
    if comment.created_by != request.user:
        messages.error(request, 'You do not have permission to delete this comment.')
        return redirect('discussions:discussion_detail', discussion_id=discussion.id)
    
    if request.method == 'POST':
        comment.delete()
        messages.success(request, 'Comment deleted successfully.')
    
    return redirect('discussions:discussion_detail', discussion_id=discussion.id)

@login_required
def add_topic(request, course_id=None):
    # Define breadcrumbs for this view
    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': reverse('discussions:discussion_list'), 'label': 'Discussions', 'icon': 'fa-comments'},
        {'label': 'Add Topic', 'icon': 'fa-plus-circle'}
    ]
    
    # Get the course if course_id is provided
    course = None
    if course_id:
        course = get_object_or_404(Course, id=course_id)
    
    if request.method == 'POST':
        title = request.POST.get('title')
        description = request.POST.get('description')
        content_type = request.POST.get('content_type')
        assessment_type = request.POST.get('assessment_type')
        status = request.POST.get('status')
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date')
        initial_post = request.POST.get('initial_post')
        course_id = request.POST.get('course', course_id)  # Use course_id from URL or form
        
        if title:
            discussion = Discussion.objects.create(
                title=title,
                description=description,
                content=initial_post,  # Using initial_post as the main content
                content_type=content_type,
                assessment_type=assessment_type,
                status=status,
                start_date=start_date if start_date else None,
                end_date=end_date if end_date else None,
                initial_post=initial_post,
                created_by=request.user,
                course=course  # Link to the course if available
            )
            
            messages.success(request, 'Topic created successfully.')
            return redirect('discussions:discussion_detail', discussion_id=discussion.id)
        else:
            messages.error(request, 'Please fill in all required fields.')
    
    # Get available courses for dropdown
    available_courses = Course.objects.all()
    
    return render(request, 'discussions/add_topic.html', {
        'title': 'Add Topic',
        'description': 'Create a new topic',
        'breadcrumbs': breadcrumbs,
        'course': course,
        'available_courses': available_courses
    })

@login_required
@require_POST
def evaluate_discussion_rubric(request, discussion_id):
    """Evaluates a discussion using a rubric and saves the results"""
    discussion = get_object_or_404(Discussion, id=discussion_id)
    
    # Only allow non-learner users to evaluate rubrics
    if request.user.role not in ['instructor', 'admin', 'superadmin', 'globaladmin'] and not request.user.is_superuser:
        return HttpResponseForbidden("You don't have permission to evaluate rubrics")
    
    # Check if the discussion has a rubric
    if not discussion.rubric:
        messages.error(request, 'This discussion does not have a rubric attached.')
        return redirect('discussions:discussion_detail', discussion_id=discussion_id)
        
    # Get the student being evaluated
    student_id = request.POST.get('student_id')
    student = None
    
    if student_id:
        try:
            student = CustomUser.objects.get(id=student_id)
        except CustomUser.DoesNotExist:
            messages.error(request, 'Selected student not found.')
            return redirect('discussions:discussion_detail', discussion_id=discussion_id)
    
    # Process each criterion evaluation
    for criterion in discussion.rubric.criteria.all():
        criterion_id = criterion.id
        
        # Get form data for this criterion
        rating_id = request.POST.get(f'rating_{criterion_id}')
        points_str = request.POST.get(f'points_{criterion_id}', '0')
        comments = request.POST.get(f'comments_{criterion_id}', '')
        
        # Validate points
        try:
            points = float(points_str)
            if points < 0:
                points = 0
            if points > criterion.points:
                points = criterion.points
        except (ValueError, TypeError):
            points = 0
        
        # Delete any existing evaluation to ensure clean state
        if student:
            RubricEvaluation.objects.filter(discussion=discussion, criterion=criterion, student=student).delete()
        else:
            RubricEvaluation.objects.filter(discussion=discussion, criterion=criterion, student__isnull=True).delete()
        
        # Create a new evaluation
        evaluation = RubricEvaluation.objects.create(
            discussion=discussion,
            criterion=criterion,
            points=points,
            comments=comments,
            evaluated_by=request.user,
            student=student
        )
        
        # Set the rating if one was selected
        if rating_id:
            try:
                rating = RubricRating.objects.get(id=rating_id, criterion=criterion)
                evaluation.rating = rating
                # Keep the instructor-entered points, don't overwrite with rating points
                # This allows instructors to select a rating but adjust points as needed
                evaluation.save()
            except RubricRating.DoesNotExist:
                pass
    
    # Handle overall feedback for discussion
    overall_feedback = request.POST.get('overall_feedback', '').strip()
    audio_feedback = request.FILES.get('audio_feedback')
    video_feedback = request.FILES.get('video_feedback')
    
    # Create or update overall feedback if provided
    if overall_feedback or audio_feedback or video_feedback:
        if discussion.rubric and student:
            feedback_data = {
                'feedback': overall_feedback,
                'is_private': False,
                'created_by': request.user,
                'student': student,
                'rubric': discussion.rubric,
                'discussion': discussion
            }
            
            # Add files if provided
            if audio_feedback:
                feedback_data['audio_feedback'] = audio_feedback
            if video_feedback:
                feedback_data['video_feedback'] = video_feedback
            
            # Update or create feedback
            overall_feedback_obj, created = RubricOverallFeedback.objects.update_or_create(
                discussion=discussion,
                student=student,
                defaults=feedback_data
            )
    
    messages.success(request, f'Rubric evaluation saved successfully{" for " + student.get_full_name() if student else ""}.')
    
    # If redirect to scores is requested, go to the scores page
    if request.POST.get('view_scores'):
        return redirect('discussions:discussion_scores', discussion_id=discussion_id)
    
    # Otherwise redirect back to the discussion detail with the student_id parameter if there was one
    if student:
        return redirect(f'{reverse("discussions:discussion_detail", kwargs={"discussion_id": discussion_id})}?student_id={student.id}')
    return redirect('discussions:discussion_detail', discussion_id=discussion_id)

@login_required
def discussion_scores(request, discussion_id):
    """View to display discussion scores with rubric evaluations"""
    discussion = get_object_or_404(Discussion, id=discussion_id)
    
    # Check permissions
    if not (request.user.role in ['instructor', 'admin', 'superadmin'] or request.user.is_superuser):
        messages.error(request, 'You do not have permission to view discussion scores.')
        return redirect('discussions:discussion_detail', discussion_id=discussion_id)
    
    # Get rubric evaluations if discussion has rubric
    rubric_evaluations = []
    if discussion.rubric:
        # Get all learners who have rubric evaluations for this discussion
        evaluations = RubricEvaluation.objects.filter(
            discussion=discussion
        ).select_related('student', 'criterion', 'rating', 'evaluated_by')
        
        # Group evaluations by student
        student_evaluations = {}
        for evaluation in evaluations:
            student_id = evaluation.student.id
            if student_id not in student_evaluations:
                student_evaluations[student_id] = {
                    'student': evaluation.student,
                    'evaluations': {},
                    'total_score': 0
                }
            student_evaluations[student_id]['evaluations'][evaluation.criterion.id] = evaluation
            student_evaluations[student_id]['total_score'] += evaluation.points
        
        # Convert to list for template
        for student_id, data in student_evaluations.items():
            rubric_evaluations.append({
                'student': data['student'],
                'evaluations': data['evaluations'],
                'total_score': data['total_score'],
                'percentage': round((data['total_score'] / discussion.rubric.total_points * 100)) if discussion.rubric.total_points > 0 else 0
            })
    
    # Get overall feedback
    overall_feedback = RubricOverallFeedback.objects.filter(
        discussion=discussion
    ).select_related('student', 'created_by')
    
    # Define breadcrumbs
    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': reverse('discussions:discussion_list'), 'label': 'Discussions', 'icon': 'fa-comments'},
        {'url': reverse('discussions:discussion_detail', args=[discussion.id]), 'label': discussion.title, 'icon': 'fa-comment'},
        {'label': 'Scores', 'icon': 'fa-chart-bar'}
    ]
    
    context = {
        'discussion': discussion,
        'rubric_evaluations': rubric_evaluations,
        'overall_feedback': overall_feedback,
        'breadcrumbs': breadcrumbs,
    }
    
    return render(request, 'discussions/discussion_scores.html', context)


@login_required
def discussion_detailed_report(request, discussion_id):
    """Comprehensive detailed report for a specific student's discussion participation with complete timeline"""
    discussion = get_object_or_404(Discussion, id=discussion_id)
    
    # Check permissions - only instructors, admins, and superadmins can access
    if not (request.user.role in ['instructor', 'admin', 'superadmin'] or request.user.is_superuser):
        messages.error(request, "You don't have permission to access this report.")
        return redirect('discussions:discussion_detail', discussion_id=discussion_id)
    
    # Get student_id from query parameters
    student_id = request.GET.get('student_id')
    if not student_id:
        messages.error(request, "Student ID is required.")
        return redirect('discussions:discussion_detail', discussion_id=discussion_id)
    
    # Get the specific student
    from django.contrib.auth import get_user_model
    User = get_user_model()
    student = get_object_or_404(User, id=student_id)
    
    # Get student's comments in this discussion
    student_comments = Comment.objects.filter(
        discussion=discussion,
        created_by=student
    ).select_related('created_by', 'parent').prefetch_related('attachments', 'replies').order_by('created_at')
    
    # Get student's comment replies
    student_replies = Comment.objects.filter(
        discussion=discussion,
        created_by=student,
        parent__isnull=False
    ).select_related('created_by', 'parent').prefetch_related('attachments').order_by('created_at')
    
    # Get likes given by this student
    student_likes = []
    discussion_likes = discussion.likes.filter(id=student_id)
    if discussion_likes.exists():
        student_likes.append({
            'type': 'discussion',
            'object': discussion,
            'liked_at': discussion.created_at  # Approximate, since we don't track when likes were given
        })
    
    # Get comment likes
    comment_likes = Comment.objects.filter(
        discussion=discussion,
        likes=student
    ).select_related('created_by')
    
    for comment in comment_likes:
        student_likes.append({
            'type': 'comment',
            'object': comment,
            'liked_at': comment.created_at  # Approximate
        })
    
    # Get attachments uploaded by this student
    student_attachments = Attachment.objects.filter(
        Q(discussion=discussion, uploaded_by=student) |
        Q(comment__discussion=discussion, uploaded_by=student)
    ).select_related('uploaded_by', 'discussion', 'comment').order_by('uploaded_at')
    
    # Get rubric evaluations if discussion has rubric
    rubric_evaluations = []
    rubric_total_score = 0
    if discussion.rubric:
        rubric_evaluations = RubricEvaluation.objects.filter(
            discussion=discussion,
            student=student
        ).select_related('criterion', 'rating', 'evaluated_by').order_by('criterion__position')
        
        # Calculate total score
        rubric_total_score = sum(eval.points for eval in rubric_evaluations)
    
    # Get overall feedback for this student
    overall_feedback = None
    if discussion.rubric:
        try:
            overall_feedback = RubricOverallFeedback.objects.get(
                discussion=discussion,
                student=student
            )
        except RubricOverallFeedback.DoesNotExist:
            pass
    
    # === BUILD COMPREHENSIVE TIMELINE ===
    timeline_events = []
    
    # Add initial discussion view (approximated by first comment/like)
    first_activity = None
    if student_comments.exists():
        first_activity = student_comments.first().created_at
    elif student_likes:
        first_activity = min(like['liked_at'] for like in student_likes)
    
    if first_activity:
        timeline_events.append({
            'type': 'discussion_view',
            'timestamp': first_activity,
            'actor': student,
            'title': 'Viewed Discussion',
            'description': f'Student accessed discussion: {discussion.title}',
            'data': {
                'discussion_title': discussion.title,
                'discussion_content': strip_tags(discussion.content)[:200] + ('...' if len(strip_tags(discussion.content)) > 200 else ''),
                'activity_type': 'view'
            }
        })
    
    # Add comment events
    for comment in student_comments:
        timeline_events.append({
            'type': 'comment_post',
            'timestamp': comment.created_at,
            'actor': comment.created_by,
            'title': 'Posted Comment',
            'description': f'Student posted a comment in discussion',
            'data': {
                'comment_id': comment.id,
                'content': strip_tags(comment.content)[:300] + ('...' if len(strip_tags(comment.content)) > 300 else ''),
                'is_reply': comment.parent is not None,
                'reply_to': comment.parent.created_by.get_full_name() if comment.parent else None,
                'attachments_count': comment.attachments.count()
            }
        })
        
        # Add comment update events if updated
        if comment.updated_at > comment.created_at:
            timeline_events.append({
                'type': 'comment_edit',
                'timestamp': comment.updated_at,
                'actor': comment.created_by,
                'title': 'Edited Comment',
                'description': f'Student edited their comment',
                'data': {
                    'comment_id': comment.id,
                    'content': strip_tags(comment.content)[:300] + ('...' if len(strip_tags(comment.content)) > 300 else ''),
                    'edit_time_diff': (comment.updated_at - comment.created_at).total_seconds() / 60  # minutes
                }
            })
    
    # Add reply events
    for reply in student_replies:
        timeline_events.append({
            'type': 'reply_post',
            'timestamp': reply.created_at,
            'actor': reply.created_by,
            'title': 'Posted Reply',
            'description': f'Student replied to {reply.parent.created_by.get_full_name()}',
            'data': {
                'reply_id': reply.id,
                'content': strip_tags(reply.content)[:300] + ('...' if len(strip_tags(reply.content)) > 300 else ''),
                'parent_comment': strip_tags(reply.parent.content)[:100] + ('...' if len(strip_tags(reply.parent.content)) > 100 else ''),
                'replied_to': reply.parent.created_by.get_full_name(),
                'attachments_count': reply.attachments.count()
            }
        })
    
    # Add like events
    for like in student_likes:
        timeline_events.append({
            'type': 'like_action',
            'timestamp': like['liked_at'],
            'actor': student,
            'title': f'Liked {like["type"].title()}',
            'description': f'Student liked a {like["type"]} in discussion',
            'data': {
                'liked_type': like['type'],
                'liked_content': strip_tags(like['object'].content)[:200] + ('...' if len(strip_tags(like['object'].content)) > 200 else '') if hasattr(like['object'], 'content') else like['object'].title if hasattr(like['object'], 'title') else 'N/A',
                'liked_author': like['object'].created_by.get_full_name() if hasattr(like['object'], 'created_by') else 'N/A'
            }
        })
    
    # Add attachment events
    for attachment in student_attachments:
        timeline_events.append({
            'type': 'attachment_upload',
            'timestamp': attachment.uploaded_at,
            'actor': attachment.uploaded_by,
            'title': 'Uploaded Attachment',
            'description': f'Student uploaded {attachment.get_file_type_display().lower()} attachment',
            'data': {
                'attachment_id': attachment.id,
                'file_name': (
                    attachment.file.name.split('/')[-1] 
                    if attachment.file and hasattr(attachment.file, 'name') 
                    and attachment.file.name else 'Unknown file'
                ),
                'file_type': attachment.file_type,
                'file_size': get_safe_file_size(attachment.file),
                'attached_to': 'Discussion' if attachment.discussion else f'Comment #{attachment.comment.id}' if attachment.comment else 'Unknown'
            }
        })
    
    # Add rubric evaluation events
    for evaluation in rubric_evaluations:
        timeline_events.append({
            'type': 'rubric_evaluation',
            'timestamp': evaluation.created_at,
            'actor': evaluation.evaluated_by,
            'title': 'Rubric Evaluation',
            'description': f'Evaluated {evaluation.criterion.description}',
            'data': {
                'criterion': evaluation.criterion.description,
                'points': evaluation.points,
                'max_points': evaluation.criterion.points,
                'rating': evaluation.rating.title if evaluation.rating else None,
                'comments': strip_tags(evaluation.comments) if evaluation.comments else None
            }
        })
    
    # Add overall feedback event
    if overall_feedback:
        timeline_events.append({
            'type': 'overall_feedback',
            'timestamp': overall_feedback.created_at,
            'actor': overall_feedback.created_by,
            'title': 'Overall Feedback',
            'description': f'Instructor provided overall feedback',
            'data': {
                'feedback_text': strip_tags(overall_feedback.feedback),
                'has_audio': bool(overall_feedback.audio_feedback),
                'has_video': bool(overall_feedback.video_feedback),
                'is_private': overall_feedback.is_private
            }
        })
    
    # Sort timeline events by timestamp (most recent first)
    timeline_events.sort(key=lambda x: x['timestamp'], reverse=True)
    
    # Calculate participation metrics
    participation_stats = {
        'total_comments': student_comments.count(),
        'total_replies': student_replies.count(),
        'total_likes_given': len(student_likes),
        'total_attachments': student_attachments.count(),
        'first_activity': first_activity,
        'last_activity': max([event['timestamp'] for event in timeline_events]) if timeline_events else None,
        'engagement_score': (student_comments.count() * 3) + (student_replies.count() * 2) + len(student_likes) + student_attachments.count()
    }
    
    # Build breadcrumbs
    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': reverse('discussions:discussion_list'), 'label': 'Discussions', 'icon': 'fa-comments'},
        {'url': reverse('discussions:discussion_detail', args=[discussion.id]), 'label': discussion.title[:30] + ('...' if len(discussion.title) > 30 else ''), 'icon': 'fa-comment'},
        {'label': f'Report: {student.get_full_name()}', 'icon': 'fa-user'}
    ]
    
    context = {
        'discussion': discussion,
        'student': student,
        'student_comments': student_comments,
        'student_replies': student_replies,
        'student_likes': student_likes,
        'student_attachments': student_attachments,
        'rubric_evaluations': rubric_evaluations,
        'rubric_total_score': rubric_total_score,
        'overall_feedback': overall_feedback,
        'timeline_events': timeline_events,
        'participation_stats': participation_stats,
        'breadcrumbs': breadcrumbs,
    }
    
    return render(request, 'discussions/detailed_report_comprehensive.html', context)

@login_required
def discussion_detailed_report_print(request, discussion_id):
    """Print-friendly version of comprehensive detailed report for a specific student's discussion participation"""
    discussion = get_object_or_404(Discussion, id=discussion_id)
    
    # Check permissions - only instructors, admins, and superadmins can access
    if not (request.user.role in ['instructor', 'admin', 'superadmin'] or request.user.is_superuser):
        messages.error(request, "You don't have permission to access this report.")
        return redirect('discussions:discussion_detail', discussion_id=discussion_id)
    
    # Get student_id from query parameters
    student_id = request.GET.get('student_id')
    if not student_id:
        messages.error(request, "Student ID is required.")
        return redirect('discussions:discussion_detail', discussion_id=discussion_id)
    
    # Get the specific student
    from django.contrib.auth import get_user_model
    User = get_user_model()
    student = get_object_or_404(User, id=student_id)
    
    # Get student's comments in this discussion
    student_comments = Comment.objects.filter(
        discussion=discussion,
        created_by=student
    ).select_related('created_by', 'parent').prefetch_related('attachments', 'replies').order_by('created_at')
    
    # Get student's comment replies
    student_replies = Comment.objects.filter(
        discussion=discussion,
        created_by=student,
        parent__isnull=False
    ).select_related('created_by', 'parent').prefetch_related('attachments').order_by('created_at')
    
    # Get likes given by this student
    student_likes = []
    discussion_likes = discussion.likes.filter(id=student_id)
    if discussion_likes.exists():
        student_likes.append({
            'type': 'discussion',
            'object': discussion,
            'liked_at': discussion.created_at  # Approximate, since we don't track when likes were given
        })
    
    # Get comment likes
    comment_likes = Comment.objects.filter(
        discussion=discussion,
        likes=student
    ).select_related('created_by')
    
    for comment in comment_likes:
        student_likes.append({
            'type': 'comment',
            'object': comment,
            'liked_at': comment.created_at  # Approximate
        })
    
    # Get attachments uploaded by this student
    student_attachments = Attachment.objects.filter(
        Q(discussion=discussion, uploaded_by=student) |
        Q(comment__discussion=discussion, uploaded_by=student)
    ).select_related('uploaded_by', 'discussion', 'comment').order_by('uploaded_at')
    
    # Get rubric evaluations if discussion has rubric
    rubric_evaluations = []
    rubric_total_score = 0
    if discussion.rubric:
        rubric_evaluations = RubricEvaluation.objects.filter(
            discussion=discussion,
            student=student
        ).select_related('criterion', 'rating', 'evaluated_by').order_by('criterion__position')
        
        # Calculate total score
        rubric_total_score = sum(eval.points for eval in rubric_evaluations)
    
    # Get overall feedback for this student
    overall_feedback = None
    if discussion.rubric:
        try:
            overall_feedback = RubricOverallFeedback.objects.get(
                discussion=discussion,
                student=student
            )
        except RubricOverallFeedback.DoesNotExist:
            pass
    
    # === BUILD COMPREHENSIVE TIMELINE ===
    timeline_events = []
    
    # Add initial discussion view (approximated by first comment/like)
    first_activity = None
    if student_comments.exists():
        first_activity = student_comments.first().created_at
    elif student_likes:
        first_activity = min(like['liked_at'] for like in student_likes)
    
    if first_activity:
        timeline_events.append({
            'type': 'discussion_view',
            'timestamp': first_activity,
            'actor': student,
            'title': 'Viewed Discussion',
            'description': f'Student accessed discussion: {discussion.title}',
            'data': {
                'discussion_title': discussion.title,
                'discussion_content': strip_tags(discussion.content)[:200] + ('...' if len(strip_tags(discussion.content)) > 200 else ''),
                'activity_type': 'view'
            }
        })
    
    # Add comment events
    for comment in student_comments:
        timeline_events.append({
            'type': 'comment_post',
            'timestamp': comment.created_at,
            'actor': comment.created_by,
            'title': 'Posted Comment',
            'description': f'Student posted a comment in discussion',
            'data': {
                'comment_id': comment.id,
                'content': strip_tags(comment.content)[:300] + ('...' if len(strip_tags(comment.content)) > 300 else ''),
                'is_reply': comment.parent is not None,
                'reply_to': comment.parent.created_by.get_full_name() if comment.parent else None,
                'attachments_count': comment.attachments.count()
            }
        })
        
        # Add comment update events if updated
        if comment.updated_at > comment.created_at:
            timeline_events.append({
                'type': 'comment_edit',
                'timestamp': comment.updated_at,
                'actor': comment.created_by,
                'title': 'Edited Comment',
                'description': f'Student edited their comment',
                'data': {
                    'comment_id': comment.id,
                    'content': strip_tags(comment.content)[:300] + ('...' if len(strip_tags(comment.content)) > 300 else ''),
                    'edit_time_diff': (comment.updated_at - comment.created_at).total_seconds() / 60  # minutes
                }
            })
    
    # Add reply events
    for reply in student_replies:
        timeline_events.append({
            'type': 'reply_post',
            'timestamp': reply.created_at,
            'actor': reply.created_by,
            'title': 'Posted Reply',
            'description': f'Student replied to {reply.parent.created_by.get_full_name()}',
            'data': {
                'reply_id': reply.id,
                'content': strip_tags(reply.content)[:300] + ('...' if len(strip_tags(reply.content)) > 300 else ''),
                'parent_comment': strip_tags(reply.parent.content)[:100] + ('...' if len(strip_tags(reply.parent.content)) > 100 else ''),
                'replied_to': reply.parent.created_by.get_full_name(),
                'attachments_count': reply.attachments.count()
            }
        })
    
    # Add like events
    for like in student_likes:
        timeline_events.append({
            'type': 'like_action',
            'timestamp': like['liked_at'],
            'actor': student,
            'title': f'Liked {like["type"].title()}',
            'description': f'Student liked a {like["type"]} in discussion',
            'data': {
                'liked_type': like['type'],
                'liked_content': strip_tags(like['object'].content)[:200] + ('...' if len(strip_tags(like['object'].content)) > 200 else '') if hasattr(like['object'], 'content') else like['object'].title if hasattr(like['object'], 'title') else 'N/A',
                'liked_author': like['object'].created_by.get_full_name() if hasattr(like['object'], 'created_by') else 'N/A'
            }
        })
    
    # Add attachment events
    for attachment in student_attachments:
        timeline_events.append({
            'type': 'attachment_upload',
            'timestamp': attachment.uploaded_at,
            'actor': attachment.uploaded_by,
            'title': 'Uploaded Attachment',
            'description': f'Student uploaded {attachment.get_file_type_display().lower()} attachment',
            'data': {
                'attachment_id': attachment.id,
                'file_name': (
                    attachment.file.name.split('/')[-1] 
                    if attachment.file and hasattr(attachment.file, 'name') 
                    and attachment.file.name else 'Unknown file'
                ),
                'file_type': attachment.file_type,
                'file_size': get_safe_file_size(attachment.file),
                'attached_to': 'Discussion' if attachment.discussion else f'Comment #{attachment.comment.id}' if attachment.comment else 'Unknown'
            }
        })
    
    # Add rubric evaluation events
    for evaluation in rubric_evaluations:
        timeline_events.append({
            'type': 'rubric_evaluation',
            'timestamp': evaluation.created_at,
            'actor': evaluation.evaluated_by,
            'title': 'Rubric Evaluation',
            'description': f'Evaluated {evaluation.criterion.description}',
            'data': {
                'criterion': evaluation.criterion.description,
                'points': evaluation.points,
                'max_points': evaluation.criterion.points,
                'rating': evaluation.rating.title if evaluation.rating else None,
                'comments': strip_tags(evaluation.comments) if evaluation.comments else None
            }
        })
    
    # Add overall feedback event
    if overall_feedback:
        timeline_events.append({
            'type': 'overall_feedback',
            'timestamp': overall_feedback.created_at,
            'actor': overall_feedback.created_by,
            'title': 'Overall Feedback',
            'description': f'Instructor provided overall feedback',
            'data': {
                'feedback_text': strip_tags(overall_feedback.feedback),
                'has_audio': bool(overall_feedback.audio_feedback),
                'has_video': bool(overall_feedback.video_feedback),
                'is_private': overall_feedback.is_private
            }
        })
    
    # Sort timeline events by timestamp (most recent first)
    timeline_events.sort(key=lambda x: x['timestamp'], reverse=True)
    
    # Calculate participation metrics
    participation_stats = {
        'total_comments': student_comments.count(),
        'total_replies': student_replies.count(),
        'total_likes_given': len(student_likes),
        'total_attachments': student_attachments.count(),
        'first_activity': first_activity,
        'last_activity': max([event['timestamp'] for event in timeline_events]) if timeline_events else None,
        'engagement_score': (student_comments.count() * 3) + (student_replies.count() * 2) + len(student_likes) + student_attachments.count()
    }
    
    # Build breadcrumbs
    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': reverse('discussions:discussion_list'), 'label': 'Discussions', 'icon': 'fa-comments'},
        {'url': reverse('discussions:discussion_detail', args=[discussion.id]), 'label': discussion.title[:30] + ('...' if len(discussion.title) > 30 else ''), 'icon': 'fa-comment'},
        {'label': f'Print Report: {student.get_full_name()}', 'icon': 'fa-print'}
    ]
    
    context = {
        'discussion': discussion,
        'student': student,
        'student_comments': student_comments,
        'student_replies': student_replies,
        'student_likes': student_likes,
        'student_attachments': student_attachments,
        'rubric_evaluations': rubric_evaluations,
        'rubric_total_score': rubric_total_score,
        'overall_feedback': overall_feedback,
        'timeline_events': timeline_events,
        'participation_stats': participation_stats,
        'breadcrumbs': breadcrumbs,
        'is_print_view': True,  # Flag to indicate this is the print view
    }
    
    return render(request, 'discussions/detailed_report_print.html', context)

@login_required
def bulk_evaluate_discussion(request, discussion_id):
    """View to evaluate multiple students at once for a discussion"""
    discussion = get_object_or_404(Discussion, id=discussion_id)
    
    # Only allow non-learner users to evaluate rubrics
    if request.user.role not in ['instructor', 'admin', 'superadmin', 'globaladmin'] and not request.user.is_superuser:
        return HttpResponseForbidden("You don't have permission to evaluate rubrics")
    
    # Check if the discussion has a rubric
    if not discussion.rubric:
        messages.error(request, 'This discussion does not have a rubric attached.')
        return redirect('discussions:discussion_detail', discussion_id=discussion_id)
    
    # Define breadcrumbs for this view
    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': reverse('discussions:discussion_list'), 'label': 'Discussions', 'icon': 'fa-comments'},
        {'url': reverse('discussions:discussion_detail', kwargs={'discussion_id': discussion_id}), 'label': discussion.title, 'icon': 'fa-file-alt'},
        {'label': 'Bulk Evaluate', 'icon': 'fa-users'}
    ]
    
    # Get all enrolled students
    enrolled_students = []
    if discussion.course:
        enrolled_students = discussion.course.courseenrollment_set.filter(
            user__role='learner'
        ).select_related('user').values_list('user', flat=True)
        enrolled_students = CustomUser.objects.filter(id__in=enrolled_students)
    
    # Also include students who have participated in the discussion (commented)
    participating_students = CustomUser.objects.filter(
        discussion_comments__discussion=discussion,
        role='learner'
    ).distinct()
    
    # Combine enrolled and participating students
    if enrolled_students:
        enrolled_students = enrolled_students.union(participating_students).distinct()
    else:
        enrolled_students = participating_students
    
    # Get students interaction data
    student_interaction_data = {}
    for student in enrolled_students:
        comments = Comment.objects.filter(discussion=discussion, created_by=student)
        
        # Count interactions
        student_interaction_data[student.id] = {
            'student': student,
            'comment_count': comments.filter(parent__isnull=True).count(),
            'reply_count': comments.filter(parent__isnull=False).count(),
            'likes_given': student.liked_comments.filter(discussion=discussion).count() + (1 if student in discussion.likes.all() else 0),
        }
    
    if request.method == 'POST':
        # Extract the student IDs that were selected
        selected_student_ids = request.POST.getlist('selected_students')
        students = CustomUser.objects.filter(id__in=selected_student_ids)
        
        # Process each criterion for each student
        for student in students:
            for criterion in discussion.rubric.criteria.all():
                criterion_id = criterion.id
                
                # Get form data for this criterion and student
                rating_id = request.POST.get(f'rating_{criterion_id}_{student.id}')
                points_str = request.POST.get(f'points_{criterion_id}_{student.id}', '0')
                comments = request.POST.get(f'comments_{criterion_id}_{student.id}', '')
                
                # Validate points
                try:
                    points = float(points_str)
                    if points < 0:
                        points = 0
                    if points > criterion.points:
                        points = criterion.points
                except (ValueError, TypeError):
                    points = 0
                
                # Delete any existing evaluation
                RubricEvaluation.objects.filter(
                    discussion=discussion, 
                    criterion=criterion,
                    student=student
                ).delete()
                
                # Create a new evaluation
                evaluation = RubricEvaluation.objects.create(
                    discussion=discussion,
                    criterion=criterion,
                    points=points,
                    comments=comments,
                    evaluated_by=request.user,
                    student=student
                )
                
                # Set the rating if one was selected
                if rating_id:
                    try:
                        rating = RubricRating.objects.get(id=rating_id, criterion=criterion)
                        evaluation.rating = rating
                        # Keep the instructor-entered points, don't overwrite with rating points
                        # This allows instructors to select a rating but adjust points as needed
                        evaluation.save()
                    except RubricRating.DoesNotExist:
                        pass
        
        messages.success(request, f'Bulk evaluation saved successfully for {len(students)} students.')
        return redirect('discussions:discussion_scores', discussion_id=discussion_id)
    
    context = {
        'discussion': discussion,
        'rubric': discussion.rubric,
        'enrolled_students': enrolled_students,
        'student_interaction_data': student_interaction_data,
        'title': f'Bulk Evaluate: {discussion.title}',
        'description': 'Evaluate multiple students at once',
        'breadcrumbs': breadcrumbs
    }
    
    return render(request, 'discussions/bulk_evaluate.html', context)

@login_required
def get_student_evaluation_data(request, discussion_id, student_id):
    """AJAX endpoint to get existing rubric evaluation data for a student"""
    discussion = get_object_or_404(Discussion, id=discussion_id)
    student = get_object_or_404(CustomUser, id=student_id)
    
    # Check permissions
    if request.user.role not in ['instructor', 'admin', 'superadmin', 'globaladmin'] and not request.user.is_superuser:
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    # Get existing evaluations for this student and discussion
    evaluations = RubricEvaluation.objects.filter(
        discussion=discussion,
        student=student
    ).select_related('criterion', 'rating')
    
    # Get student interaction data
    student_comments = Comment.objects.filter(
        discussion=discussion,
        created_by=student
    ).select_related('parent')
    
    # Prepare evaluation data
    evaluation_data = {}
    total_points = 0
    
    for evaluation in evaluations:
        evaluation_data[evaluation.criterion.id] = {
            'points': evaluation.points,
            'rating_id': evaluation.rating.id if evaluation.rating else None,
            'comments': evaluation.comments
        }
        total_points += evaluation.points
    
    # Prepare interaction data
    interaction_data = {
        'comment_count': student_comments.filter(parent__isnull=True).count(),
        'reply_count': student_comments.filter(parent__isnull=False).count(),
        'likes_given': student.liked_comments.filter(discussion=discussion).count() + (1 if student in discussion.likes.all() else 0),
    }
    interaction_data['total_interactions'] = (
        interaction_data['comment_count'] + 
        interaction_data['reply_count'] + 
        interaction_data['likes_given']
    )
    
    # Get existing overall feedback for this student
    overall_feedback = None
    try:
        feedback_obj = RubricOverallFeedback.objects.get(
            discussion=discussion,
            student=student
        )
        overall_feedback = {
            'feedback': feedback_obj.feedback,
            'audio_feedback': feedback_obj.audio_feedback.url if feedback_obj.audio_feedback else None,
            'video_feedback': feedback_obj.video_feedback.url if feedback_obj.video_feedback else None,
        }
    except RubricOverallFeedback.DoesNotExist:
        overall_feedback = {'feedback': '', 'audio_feedback': None, 'video_feedback': None}
    
    return JsonResponse({
        'success': True,
        'evaluation_data': evaluation_data,
        'interaction_data': interaction_data,
        'total_points': total_points,
        'overall_feedback': overall_feedback
    })

# Add this new function for image uploads from TinyMCE editor
@login_required
@require_POST
@ensure_csrf_cookie
def upload_image(request):
    """Handle image uploads from TinyMCE editor"""
    if request.method != 'POST' or 'file' not in request.FILES:
        return JsonResponse({'error': 'No file provided'}, status=400)
    
    # Get the uploaded file
    file = request.FILES['file']
    
    # Validate file type
    allowed_types = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
    if file.content_type not in allowed_types:
        return JsonResponse({'error': 'File type not allowed'}, status=400)
    
    # Generate a unique filename
    ext = os.path.splitext(file.name)[1]
    unique_filename = f"{uuid.uuid4()}{ext}"
    
    # Use Django's default storage (works with both local and S3)
    from django.core.files.storage import default_storage
    
    # Save the file using default storage
    file_path = f"discussions/uploads/{unique_filename}"
    saved_path = default_storage.save(file_path, file)
    
    # Generate the URL using default storage
    file_url = default_storage.url(saved_path)
    
    # Return the response in TinyMCE expected format
    return JsonResponse({
        'location': file_url,
    })

@login_required
def user_autocomplete_api(request):
    """API endpoint for user autocomplete in discussion comments"""
    query = request.GET.get('q', '').strip()
    discussion_id = request.GET.get('discussion_id')
    
    if len(query) < 2:
        return JsonResponse({'users': []})
    
    try:
        # Get the discussion to determine which users have access
        discussion = get_object_or_404(Discussion, id=discussion_id) if discussion_id else None
        
        # Base queryset - start with active users
        users_queryset = CustomUser.objects.filter(
            is_active=True
        ).exclude(
            id=request.user.id  # Exclude current user
        )
        
        # Filter by search query (username, first_name, last_name, email)
        users_queryset = users_queryset.filter(
            models.Q(username__icontains=query) |
            models.Q(first_name__icontains=query) |
            models.Q(last_name__icontains=query) |
            models.Q(email__icontains=query)
        )
        
        # If we have a discussion and course context, prioritize users from that course
        if discussion and discussion.course:
            # Get enrolled users in the course
            course_users = discussion.course.courseenrollment_set.filter(
                user__in=users_queryset
            ).values_list('user_id', flat=True)
            
            # Order results to show course users first
            users_queryset = users_queryset.extra(
                select={'is_in_course': f'CASE WHEN id IN ({",".join(map(str, course_users))}) THEN 1 ELSE 0 END'}
            ).order_by('-is_in_course', 'first_name', 'last_name')
        else:
            users_queryset = users_queryset.order_by('first_name', 'last_name')
        
        # Limit results to prevent performance issues
        users = users_queryset[:10]
        
        # Format response
        user_list = []
        for user in users:
            display_name = user.get_full_name() if user.get_full_name().strip() else user.username
            user_list.append({
                'id': user.id,
                'username': user.username,
                'display_name': display_name,
                'full_name': user.get_full_name(),
                'avatar_initial': user.first_name[0].upper() if user.first_name else user.username[0].upper(),
            })
        
        return JsonResponse({'users': user_list})
        
    except Exception as e:
        logger.error(f"Error in user autocomplete: {str(e)}")
        return JsonResponse({'error': 'Failed to fetch users'}, status=500)
