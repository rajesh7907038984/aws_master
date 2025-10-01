from django.urls import resolve, reverse
from django.shortcuts import get_object_or_404
from django.urls.exceptions import Resolver404
from .models import Course, Topic, CourseTopic

def breadcrumbs(request):
    """
    Context processor to provide breadcrumbs data to all templates.
    """
    breadcrumbs = []
    current_url = request.path
    
    try:
        url_name = resolve(current_url).url_name
    except Resolver404:
        # Handle cases where URL doesn't resolve (like favicon.ico, static files, etc.)
        return {'breadcrumbs': breadcrumbs}
    
    # Skip breadcrumbs for URLs without url_name (like static files)
    if not url_name:
        return {'breadcrumbs': breadcrumbs}
    
    # Add breadcrumbs based on the current URL
    if url_name == 'dashboard':
        breadcrumbs = []
    elif url_name == 'course_list':
        breadcrumbs = [
            {'title': 'Courses', 'url': reverse('courses:course_list')}
        ]
    elif url_name == 'course_details':
        course_id = resolve(current_url).kwargs.get('course_id')
        course = get_object_or_404(Course, id=course_id)
        breadcrumbs = [
            {'title': 'Courses', 'url': reverse('courses:course_list')},
            {'title': course.title, 'url': reverse('courses:course_details', kwargs={'course_id': course.id})}
        ]
    elif url_name == 'topic_view':
        topic_id = resolve(current_url).kwargs.get('topic_id')
        topic = get_object_or_404(Topic, id=topic_id)
        # Get the first course associated with this topic
        course_topic = get_object_or_404(CourseTopic, topic=topic)
        course = course_topic.course
        breadcrumbs = [
            {'title': 'Courses', 'url': reverse('courses:course_list')},
            {'title': course.title, 'url': reverse('courses:course_details', kwargs={'course_id': course.id})},
            {'title': topic.title}
        ]
    elif url_name == 'create_course':
        breadcrumbs = [
            {'title': 'Courses', 'url': reverse('courses:course_list')},
            {'title': 'Create Course'}
        ]
    
    return {'breadcrumbs': breadcrumbs}

def get_topic_course(topic):
    """Helper function to get course for a topic through CourseTopic"""
    return Course.objects.filter(coursetopic__topic=topic).first() 