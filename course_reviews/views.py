from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponseForbidden, Http404
from django.db.models import Avg, Count, Q
from django.db import transaction
from django.views.decorators.http import require_http_methods, require_POST
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.utils import timezone
from django.urls import reverse
from decimal import Decimal

from .models import Survey, SurveyField, SurveyResponse, CourseReview
from .forms import SurveyForm, SurveyFieldForm, SurveyFieldFormSet, SurveyResponseForm
from courses.models import Course, CourseEnrollment
from role_management.utils import require_capability, require_any_capability


# ============================================
# Survey Management Views (Admin/Instructor)
# ============================================

@login_required
@require_any_capability(['manage_surveys', 'view_surveys'])
def survey_list(request):
    """List all surveys for instructors and admins"""
    user = request.user
    
    # Filter surveys based on user role and capabilities
    # Global admins and super admins can see all surveys
    if user.role in ['globaladmin', 'superadmin'] or user.is_superuser:
        surveys = Survey.objects.all()
    else:
        # Other users with the capability can see surveys from their branch or created by them
        surveys = Survey.objects.filter(
            Q(branch=user.branch) | Q(created_by=user)
        )
    
    # Add annotations
    surveys = surveys.annotate(
        fields_count=Count('fields'),
        responses_count=Count('fields__responses', distinct=True)
    ).select_related('created_by', 'branch').order_by('-created_at')
    
    # Search functionality
    search_query = request.GET.get('search', '')
    if search_query:
        surveys = surveys.filter(
            Q(title__icontains=search_query) |
            Q(description__icontains=search_query)
        )
    
    # Pagination
    paginator = Paginator(surveys, 10)
    page = request.GET.get('page', 1)
    try:
        surveys_page = paginator.page(page)
    except PageNotAnInteger:
        surveys_page = paginator.page(1)
    except EmptyPage:
        surveys_page = paginator.page(paginator.num_pages)
    
    # Breadcrumbs
    breadcrumbs = [
        {'url': reverse('home'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'label': 'Survey Management', 'icon': 'fa-poll'}
    ]
    
    context = {
        'surveys': surveys_page,
        'search_query': search_query,
        'breadcrumbs': breadcrumbs,
    }
    return render(request, 'course_reviews/survey_list.html', context)


@login_required
@require_capability('manage_surveys')
def survey_create(request):
    """Create a new survey"""
    if request.method == 'POST':
        form = SurveyForm(request.POST)
        if form.is_valid():
            survey = form.save(commit=False)
            survey.created_by = request.user
            survey.branch = request.user.branch
            survey.save()
            messages.success(request, f'Survey "{survey.title}" created successfully! Now add fields to it.')
            return redirect('course_reviews:survey_edit', survey_id=survey.id)
    else:
        form = SurveyForm()
    
    # Breadcrumbs
    breadcrumbs = [
        {'url': reverse('home'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': reverse('course_reviews:survey_list'), 'label': 'Survey Management', 'icon': 'fa-poll'},
        {'label': 'Create Survey', 'icon': 'fa-plus'}
    ]
    
    context = {
        'form': form,
        'action': 'Create',
        'breadcrumbs': breadcrumbs,
    }
    return render(request, 'course_reviews/survey_form.html', context)


@login_required
@require_capability('manage_surveys')
def survey_edit(request, survey_id):
    """Edit an existing survey with inline field management"""
    survey = get_object_or_404(Survey, id=survey_id)
    
    # Check permissions
    user = request.user
    if user.role not in ['globaladmin', 'superadmin']:
        if survey.branch != user.branch and survey.created_by != user:
            return HttpResponseForbidden("You don't have permission to edit this survey.")
    
    if request.method == 'POST':
        form = SurveyForm(request.POST, instance=survey)
        formset = SurveyFieldFormSet(request.POST, instance=survey)
        
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                survey = form.save()
                formset.save()
            messages.success(request, f'Survey "{survey.title}" updated successfully!')
            return redirect('course_reviews:survey_list')
    else:
        form = SurveyForm(instance=survey)
        formset = SurveyFieldFormSet(instance=survey)
        
    
    # Breadcrumbs
    breadcrumbs = [
        {'url': reverse('home'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': reverse('course_reviews:survey_list'), 'label': 'Survey Management', 'icon': 'fa-poll'},
        {'label': f'Edit: {survey.title}', 'icon': 'fa-edit'}
    ]
    
    context = {
        'form': form,
        'formset': formset,
        'survey': survey,
        'action': 'Edit',
        'breadcrumbs': breadcrumbs,
    }
    return render(request, 'course_reviews/survey_edit.html', context)


@login_required
@require_capability('manage_surveys')
@require_POST
def survey_delete(request, survey_id):
    """Delete a survey"""
    survey = get_object_or_404(Survey, id=survey_id)
    
    # Check permissions
    user = request.user
    if user.role not in ['globaladmin', 'superadmin']:
        if survey.branch != user.branch and survey.created_by != user:
            return HttpResponseForbidden("You don't have permission to delete this survey.")
    
    survey_title = survey.title
    survey.delete()
    messages.success(request, f'Survey "{survey_title}" deleted successfully!')
    return redirect('course_reviews:survey_list')


@login_required
@require_any_capability(['manage_surveys', 'view_surveys'])
def survey_preview(request, survey_id):
    """Preview a survey"""
    survey = get_object_or_404(Survey, id=survey_id)
    
    # Check permissions - users can preview if they have the capability and either:
    # 1. They are global/super admin
    # 2. The survey is from their branch or created by them
    user = request.user
    if user.role not in ['globaladmin', 'superadmin'] and not user.is_superuser:
        if survey.branch != user.branch and survey.created_by != user:
            return HttpResponseForbidden("You don't have permission to preview this survey.")
    
    fields = survey.fields.all().order_by('order')
    
    # Breadcrumbs
    breadcrumbs = [
        {'url': reverse('home'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': reverse('course_reviews:survey_list'), 'label': 'Survey Management', 'icon': 'fa-poll'},
        {'label': f'Preview: {survey.title}', 'icon': 'fa-eye'}
    ]
    
    context = {
        'survey': survey,
        'fields': fields,
        'is_preview': True,
        'breadcrumbs': breadcrumbs,
    }
    return render(request, 'course_reviews/survey_preview.html', context)


# ============================================
# Survey Field Management
# ============================================

@login_required
@require_capability('manage_surveys')
def survey_field_add(request, survey_id):
    """Add a field to a survey"""
    survey = get_object_or_404(Survey, id=survey_id)
    
    if request.method == 'POST':
        form = SurveyFieldForm(request.POST)
        if form.is_valid():
            field = form.save(commit=False)
            field.survey = survey
            field.save()
            messages.success(request, 'Field added successfully!')
            return redirect('course_reviews:survey_edit', survey_id=survey.id)
    else:
        # Set default order to be last
        last_order = survey.fields.aggregate(max_order=models.Max('order'))['max_order'] or 0
        form = SurveyFieldForm(initial={'order': last_order + 1})
    
    context = {
        'form': form,
        'survey': survey,
        'action': 'Add',
    }
    return render(request, 'course_reviews/survey_field_form.html', context)


@login_required
@require_capability('manage_surveys')
def survey_field_edit(request, survey_id, field_id):
    """Edit a survey field"""
    survey = get_object_or_404(Survey, id=survey_id)
    field = get_object_or_404(SurveyField, id=field_id, survey=survey)
    
    if request.method == 'POST':
        form = SurveyFieldForm(request.POST, instance=field)
        if form.is_valid():
            form.save()
            messages.success(request, 'Field updated successfully!')
            return redirect('course_reviews:survey_edit', survey_id=survey.id)
    else:
        form = SurveyFieldForm(instance=field)
    
    context = {
        'form': form,
        'survey': survey,
        'field': field,
        'action': 'Edit',
    }
    return render(request, 'course_reviews/survey_field_form.html', context)


@login_required
@require_capability('manage_surveys')
@require_POST
def survey_field_delete(request, survey_id, field_id):
    """Delete a survey field"""
    survey = get_object_or_404(Survey, id=survey_id)
    field = get_object_or_404(SurveyField, id=field_id, survey=survey)
    
    field.delete()
    messages.success(request, 'Field deleted successfully!')
    return redirect('course_reviews:survey_edit', survey_id=survey.id)


# ============================================
# Survey Submission Views (Learner)
# ============================================

@login_required
def submit_course_survey(request, course_id):
    """Submit a survey for a completed course"""
    course = get_object_or_404(Course, id=course_id)
    user = request.user
    
    # Check if user has completed the course
    try:
        enrollment = CourseEnrollment.objects.get(user=user, course=course)
        if not enrollment.completed:
            messages.error(request, 'You must complete the course before submitting a review.')
            return redirect('courses:course_details', course_id=course.id)
    except CourseEnrollment.DoesNotExist:
        messages.error(request, 'You are not enrolled in this course.')
        return redirect('courses:course_details', course_id=course.id)
    
    # Check if course has a survey
    if not hasattr(course, 'survey') or not course.survey:
        messages.error(request, 'This course does not have a survey.')
        return redirect('courses:course_details', course_id=course.id)
    
    survey = course.survey
    
    # Check if user has already submitted a review
    existing_review = CourseReview.objects.filter(
        user=user,
        course=course,
        survey=survey
    ).first()
    
    if request.method == 'POST':
        form = SurveyResponseForm(request.POST, survey=survey)
        if form.is_valid():
            with transaction.atomic():
                # Save all responses
                for field in survey.fields.all():
                    field_name = f'field_{field.id}'
                    response_value = form.cleaned_data.get(field_name)
                    
                    if response_value is not None and response_value != '':
                        # Delete existing response if any
                        SurveyResponse.objects.filter(
                            survey_field=field,
                            user=user,
                            course=course
                        ).delete()
                        
                        # Create new response
                        response = SurveyResponse(
                            survey_field=field,
                            user=user,
                            course=course
                        )
                        
                        if field.field_type == 'rating':
                            response.rating_response = int(response_value)
                        else:
                            response.text_response = str(response_value)
                        
                        response.save()
                
                # Create or update CourseReview
                CourseReview.create_from_responses(user, course, survey)
            
            messages.success(request, 'Thank you for your feedback! Your review has been submitted.')
            return redirect('courses:course_details', course_id=course.id)
    else:
        # Pre-populate form if editing existing review
        initial_data = {}
        if existing_review:
            responses = SurveyResponse.objects.filter(
                user=user,
                course=course,
                survey_field__survey=survey
            )
            for response in responses:
                field_name = f'field_{response.survey_field.id}'
                if response.survey_field.field_type == 'rating':
                    initial_data[field_name] = response.rating_response
                else:
                    initial_data[field_name] = response.text_response
        
        form = SurveyResponseForm(survey=survey, initial=initial_data)
    
    # Breadcrumbs
    breadcrumbs = [
        {'url': reverse('home'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': reverse('courses:course_details', kwargs={'course_id': course.id}), 'label': course.title, 'icon': 'fa-book'},
        {'label': 'Submit Review', 'icon': 'fa-star'}
    ]
    
    context = {
        'form': form,
        'survey': survey,
        'course': course,
        'is_editing': existing_review is not None,
        'breadcrumbs': breadcrumbs,
    }
    return render(request, 'course_reviews/submit_survey.html', context)


# ============================================
# Course Reviews Display Views
# ============================================

def course_reviews_list(request, course_id):
    """List all reviews for a course"""
    course = get_object_or_404(Course, id=course_id)
    
    reviews = CourseReview.objects.filter(
        course=course,
        is_published=True
    ).select_related('user', 'survey').order_by('-submitted_at')
    
    # Calculate average rating
    avg_rating = reviews.aggregate(avg=Avg('average_rating'))['avg'] or 0
    total_reviews = reviews.count()
    
    # Rating distribution
    rating_distribution = {i: 0 for i in range(1, 6)}
    for review in reviews:
        rating_rounded = round(review.average_rating)
        if 1 <= rating_rounded <= 5:
            rating_distribution[rating_rounded] += 1
    
    # Pagination
    paginator = Paginator(reviews, 10)
    page = request.GET.get('page', 1)
    try:
        reviews_page = paginator.page(page)
    except PageNotAnInteger:
        reviews_page = paginator.page(1)
    except EmptyPage:
        reviews_page = paginator.page(paginator.num_pages)
    
    # Breadcrumbs
    breadcrumbs = [
        {'url': reverse('home'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': reverse('courses:course_details', kwargs={'course_id': course.id}), 'label': course.title, 'icon': 'fa-book'},
        {'label': 'Course Reviews', 'icon': 'fa-star'}
    ]
    
    context = {
        'course': course,
        'reviews': reviews_page,
        'avg_rating': round(avg_rating, 2),
        'total_reviews': total_reviews,
        'rating_distribution': rating_distribution,
        'breadcrumbs': breadcrumbs,
    }
    return render(request, 'course_reviews/course_reviews_list.html', context)


def course_review_detail(request, course_id, review_id):
    """View detailed review"""
    course = get_object_or_404(Course, id=course_id)
    review = get_object_or_404(CourseReview, id=review_id, course=course, is_published=True)
    
    # Get all responses for this review
    responses = review.get_all_responses()
    
    # Breadcrumbs
    breadcrumbs = [
        {'url': reverse('home'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': reverse('courses:course_details', kwargs={'course_id': course.id}), 'label': course.title, 'icon': 'fa-book'},
        {'url': reverse('course_reviews:course_reviews_list', kwargs={'course_id': course.id}), 'label': 'Course Reviews', 'icon': 'fa-star'},
        {'label': 'Review Detail', 'icon': 'fa-eye'}
    ]
    
    context = {
        'course': course,
        'review': review,
        'responses': responses,
        'breadcrumbs': breadcrumbs,
    }
    return render(request, 'course_reviews/course_review_detail.html', context)


# ============================================
# API Views
# ============================================

def get_course_average_rating(request, course_id):
    """Get average rating for a course (API endpoint)"""
    course = get_object_or_404(Course, id=course_id)
    
    reviews = CourseReview.objects.filter(course=course, is_published=True)
    avg_rating = reviews.aggregate(avg=Avg('average_rating'))['avg'] or 0
    total_reviews = reviews.count()
    
    return JsonResponse({
        'average_rating': round(avg_rating, 2),
        'total_reviews': total_reviews,
    })


@login_required
@require_any_capability(['manage_surveys', 'view_surveys'])
def survey_responses(request, survey_id):
    """Get all responses for a survey (API endpoint)"""
    survey = get_object_or_404(Survey, id=survey_id)
    
    responses = SurveyResponse.objects.filter(
        survey_field__survey=survey
    ).select_related('user', 'course', 'survey_field').order_by('-submitted_at')
    
    # Group by user and course
    grouped_responses = {}
    for response in responses:
        key = f"{response.user.id}_{response.course.id}"
        if key not in grouped_responses:
            grouped_responses[key] = {
                'user': response.user.get_full_name() or response.user.username,
                'course': response.course.title,
                'submitted_at': response.submitted_at,
                'responses': []
            }
        grouped_responses[key]['responses'].append({
            'field': response.survey_field.label,
            'value': response.response_value
        })
    
    return JsonResponse({
        'survey': survey.title,
        'total_responses': len(grouped_responses),
        'responses': list(grouped_responses.values())
    })


# Import models here to avoid circular import
from django.db import models