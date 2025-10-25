"""
Enhanced Course Management Views with Comprehensive Error Handling
This file contains upgraded versions of critical course management views
"""

import logging
import os
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse, StreamingHttpResponse, HttpResponseForbidden
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.views.generic import DetailView
from django.db import transaction, IntegrityError
from django.core.exceptions import ValidationError
from django.urls import reverse_lazy
from django.conf import settings

from core.mixins.enhanced_view_mixins import CourseViewMixin, RobustAtomicViewMixin, BaseErrorHandlingMixin
from .models import Course, Topic, Section, CourseEnrollment
from .forms import CourseForm

logger = logging.getLogger(__name__)


class EnhancedCourseCreateView(CourseViewMixin, CreateView):
    """
    Enhanced course creation view with comprehensive error handling
    """
    model = Course
    form_class = CourseForm
    template_name = 'courses/create_course.html'
    
    def get_form_kwargs(self):
        """Add user to form kwargs"""
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs
    
    def form_valid(self, form):
        """Enhanced course creation with better error handling"""
        try:
            with transaction.atomic():
                # Set the instructor
                form.instance.instructor = self.request.user
                
                # Validate permissions
                if not self.can_create_course():
                    form.add_error(None, "You don't have permission to create courses.")
                    return self.form_invalid(form)
                
                # Save the course
                course = form.save()
                
                # Create default section if needed
                if not course.sections.exists():
                    Section.objects.create(
                        course=course,
                        name="Course Introduction",
                        description="Welcome to the course",
                        order=0
                    )
                
                # Log successful course creation
                logger.info(f"Course created successfully: {course.title} by {self.request.user.username}")
                
                if self.is_ajax_request(self.request):
                    return JsonResponse({
                        'success': True,
                        'message': f'Course "{course.title}" created successfully.',
                        'redirect_url': f'/courses/{course.id}/edit/',
                        'course_id': course.id
                    })
                
                messages.success(self.request, f'Course "{course.title}" created successfully!')
                return redirect('courses:edit_course', course_id=course.id)
                
        except ValidationError as e:
            logger.warning(f"Course validation error: {str(e)}")
            form.add_error(None, f"Validation error: {str(e)}")
            return self.form_invalid(form)
        
        except IntegrityError as e:
            logger.error(f"Course creation integrity error: {str(e)}")
            form.add_error(None, "A course with similar information already exists.")
            return self.form_invalid(form)
        
        except OSError as e:
            logger.error(f"File system error creating course: {str(e)}")
            form.add_error(None, "File system error. Please try again or contact support.")
            return self.form_invalid(form)
        
        except Exception as e:
            logger.error(f"Unexpected error creating course: {str(e)}", exc_info=True)
            form.add_error(None, "An unexpected error occurred. Please try again.")
            return self.form_invalid(form)
    
    def can_create_course(self):
        """Check if user can create courses"""
        return (
            self.request.user.role in ['instructor', 'admin', 'superadmin', 'globaladmin'] or 
            self.request.user.is_superuser
        )
    
    def get_context_data(self, **kwargs):
        """Add additional context"""
        context = super().get_context_data(**kwargs)
        context['title'] = 'Create Course'
        context['button_text'] = 'Create Course'
        context['breadcrumbs'] = [
            {'url': '/dashboard/', 'label': 'Dashboard'},
            {'url': '/courses/', 'label': 'Courses'},
            {'label': 'Create Course'}
        ]
        return context


class EnhancedCourseUpdateView(CourseViewMixin, UpdateView):
    """
    Enhanced course update view with comprehensive error handling
    """
    model = Course
    form_class = CourseForm
    template_name = 'courses/edit_course.html'
    context_object_name = 'course'
    pk_url_kwarg = 'course_id'
    
    def get_form_kwargs(self):
        """Add user to form kwargs"""
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs
    
    def form_valid(self, form):
        """Enhanced course update with better error handling"""
        try:
            with transaction.atomic():
                # Validate permissions
                if not self.can_edit_course():
                    form.add_error(None, "You don't have permission to edit this course.")
                    return self.form_invalid(form)
                
                # Save the course
                course = form.save()
                
                # Log successful course update
                logger.info(f"Course updated successfully: {course.title} by {self.request.user.username}")
                
                # Handle AJAX requests
                if self.is_ajax_request(self.request):
                    return JsonResponse({
                        'success': True,
                        'message': f'Course "{course.title}" updated successfully.',
                        'course_id': course.id
                    })
                
                messages.success(self.request, f'Course "{course.title}" updated successfully!')
                return redirect('courses:course_details', course_id=course.id)
                
        except ValidationError as e:
            logger.warning(f"Course validation error: {str(e)}")
            form.add_error(None, f"Validation error: {str(e)}")
            return self.form_invalid(form)
        
        except Exception as e:
            logger.error(f"Error updating course {self.object.id}: {str(e)}", exc_info=True)
            form.add_error(None, "An error occurred while updating the course. Please try again.")
            return self.form_invalid(form)
    
    def can_edit_course(self):
        """Check if user can edit this course"""
        if self.request.user.is_superuser:
            return True
        
        if self.request.user.role == 'globaladmin':
            return True
        
        if self.request.user.role == 'superadmin':
            return self.object.instructor.business == self.request.user.business
        
        if self.request.user.role in ['admin', 'instructor']:
            return (
                self.object.instructor == self.request.user or
                self.object.instructor.branch == self.request.user.branch
            )
        
        return False


@login_required
def enhanced_course_delete(request, course_id):
    """
    Enhanced course deletion with comprehensive error handling
    """
    course = get_object_or_404(Course, id=course_id)
    
    # Check permissions
    if not has_course_delete_permission(request.user, course):
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False,
                'error': "You don't have permission to delete this course.",
                'error_type': 'permission_denied'
            }, status=403)
        
        messages.error(request, "You don't have permission to delete this course.")
        return redirect('courses:course_details', course_id=course_id)
    
    if request.method == 'POST':
        try:
            with transaction.atomic():
                course_title = course.title
                
                # Check if course has enrollments
                if course.enrollments.exists():
                    # Soft delete - mark as inactive
                    course.is_active = False
                    course.save()
                    action = 'deactivated'
                    logger.info(f"Course soft deleted: {course_title} by {request.user.username}")
                else:
                    # Hard delete
                    course.delete()
                    action = 'deleted'
                    logger.info(f"Course hard deleted: {course_title} by {request.user.username}")
                
                success_msg = f'Course "{course_title}" has been {action} successfully.'
                
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': True,
                        'message': success_msg,
                        'redirect_url': '/courses/'
                    })
                
                messages.success(request, success_msg)
                return redirect('courses:course_list')
                
        except Exception as e:
            logger.error(f"Error deleting course {course_id}: {str(e)}", exc_info=True)
            
            error_msg = 'An error occurred while deleting the course. Please try again.'
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'error': error_msg,
                    'error_type': 'deletion_error'
                }, status=500)
            
            messages.error(request, error_msg)
            return redirect('courses:course_details', course_id=course_id)
    
    # GET request - show confirmation
    context = {
        'course': course,
        'has_enrollments': course.enrollments.exists(),
        'enrollments_count': course.enrollments.count()
    }
    return render(request, 'courses/course_delete_confirm.html', context)


@login_required
def enhanced_topic_create(request, course_id):
    """
    Enhanced topic creation with comprehensive error handling
    """
    course = get_object_or_404(Course, id=course_id)
    
    # Check permissions
    if not has_course_edit_permission(request.user, course):
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False,
                'error': "You don't have permission to add topics to this course.",
                'error_type': 'permission_denied'
            }, status=403)
        
        messages.error(request, "You don't have permission to add topics to this course.")
        return redirect('courses:course_details', course_id=course_id)
    
    if request.method == 'POST':
        try:
            with transaction.atomic():
                # Extract form data
                title = request.POST.get('title', '').strip()
                description = request.POST.get('description', '').strip()
                content_type = request.POST.get('content_type')
                section_id = request.POST.get('section_id')
                
                # Validate required fields
                if not title:
                    raise ValidationError("Topic title is required.")
                
                if not content_type:
                    raise ValidationError("Content type is required.")
                
                # Get section
                section = None
                if section_id:
                    section = get_object_or_404(Section, id=section_id, course=course)
                
                # Create topic
                topic = Topic.objects.create(
                    title=title,
                    description=description,
                    course=course,
                    section=section,
                    content_type=content_type,
                    created_by=request.user,
                    order=get_next_topic_order(course, section)
                )
                
                # Process content based on type
                process_topic_content(topic, request)
                
                # Log successful topic creation
                logger.info(f"Topic created: {title} in course {course.title} by {request.user.username}")
                
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': True,
                        'message': f'Topic "{title}" created successfully.',
                        'topic_id': topic.id,
                        'redirect_url': f'/courses/topic/{topic.id}/'
                    })
                
                messages.success(request, f'Topic "{title}" created successfully!')
                return redirect('courses:topic_view', topic_id=topic.id)
                
        except ValidationError as e:
            logger.warning(f"Topic creation validation error: {str(e)}")
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'error': str(e),
                    'error_type': 'validation_error'
                }, status=400)
            
            messages.error(request, str(e))
            return redirect('courses:add_topic', course_id=course_id)
        
        except Exception as e:
            logger.error(f"Error creating topic in course {course_id}: {str(e)}", exc_info=True)
            
            error_msg = 'An error occurred while creating the topic. Please try again.'
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'error': error_msg,
                    'error_type': 'creation_error'
                }, status=500)
            
            messages.error(request, error_msg)
            return redirect('courses:add_topic', course_id=course_id)
    
    # GET request - show form
    context = {
        'course': course,
        'sections': course.sections.all().order_by('order')
    }
    return render(request, 'courses/add_topic.html', context)


@login_required
def enhanced_stream_video(request, path):
    """
    Enhanced video streaming with comprehensive error handling
    """
    try:
        # Validate file path
        if not path or '..' in path:
            logger.warning(f"Invalid video path requested: {path}")
            return HttpResponse('Invalid file path', status=400)
        
        # Construct full file path
        video_dir = getattr(settings, 'MEDIA_ROOT', '/tmp')
        file_path = os.path.join(video_dir, 'course_videos', path)
        
        # Check if file exists
        if not os.path.exists(file_path):
            logger.warning(f"Video file not found: {file_path}")
            return HttpResponse('Video not found', status=404)
        
        # Check permissions (implement your logic here)
        if not has_video_access_permission(request.user, path):
            logger.warning(f"Unauthorized video access attempt: {path} by user {request.user.id}")
            return HttpResponseForbidden('Access denied')
        
        # Stream the video
        def file_iterator(chunk_size=8192):
            try:
                with open(file_path, 'rb') as file:
                    while True:
                        chunk = file.read(chunk_size)
                        if not chunk:
                            break
                        yield chunk
            except IOError as e:
                logger.error(f"Error reading video file {file_path}: {str(e)}")
                raise
        
        # Get file size
        file_size = os.path.getsize(file_path)
        
        # Create streaming response
        response = StreamingHttpResponse(
            file_iterator(),
            content_type='video/mp4'
        )
        response['Content-Length'] = str(file_size)
        response['Accept-Ranges'] = 'bytes'
        
        return response
        
    except Exception as e:
        logger.error(f"Error streaming video {path}: {str(e)}", exc_info=True)
        return HttpResponse('Error streaming video', status=500)


def has_course_delete_permission(user, course):
    """Check if user can delete the course"""
    if user.is_superuser:
        return True
    
    if user.role == 'globaladmin':
        return True
    
    if user.role == 'superadmin':
        return course.instructor.business == user.business
    
    if user.role == 'admin':
        return course.instructor.branch == user.branch
    
    if user.role == 'instructor':
        return course.instructor == user
    
    return False


def has_course_edit_permission(user, course):
    """Check if user can edit the course"""
    return has_course_delete_permission(user, course)


def has_video_access_permission(user, video_path):
    """Check if user has permission to access the video"""
    # Implement your video access logic here
    # This could check course enrollment, permissions, etc.
    return user.is_authenticated


def get_next_topic_order(course, section=None):
    """Get the next order number for a topic"""
    if section:
        last_topic = Topic.objects.filter(section=section).order_by('-order').first()
    else:
        last_topic = Topic.objects.filter(course=course, section__isnull=True).order_by('-order').first()
    
    return (last_topic.order + 1) if last_topic else 0


def process_topic_content(topic, request):
    """Process topic content based on content type"""
    try:
        content_type = topic.content_type
        
        if content_type == 'video':
            video_file = request.FILES.get('video_file')
            if video_file:
                topic.video_file = video_file
                topic.save()
        
        elif content_type == 'document':
            document_file = request.FILES.get('document_file')
            if document_file:
                topic.document_file = document_file
                topic.save()
        
        elif content_type == 'text':
            content_text = request.POST.get('content_text', '')
            if content_text:
                topic.content_text = content_text
                topic.save()
        
        # Add other content type processing as needed
        
    except Exception as e:
        logger.error(f"Error processing topic content for topic {topic.id}: {str(e)}")
        raise ValidationError(f"Error processing {topic.content_type} content: {str(e)}")
