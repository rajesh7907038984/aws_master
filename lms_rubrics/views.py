from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse, HttpResponseForbidden
from django.template.context_processors import csrf
import json
import functools
# Import models directly rather than from .models to avoid circular imports
from lms_rubrics.models import Rubric, RubricCriterion, RubricRating
from django.core.exceptions import ValidationError
from django.db import models


def check_login(view_func):
    """Debug decorator to check login status without redirecting"""
    @functools.wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            # Return a helpful error message instead of redirecting
            return HttpResponse(f"Not authenticated. Session keys: {list(request.session.keys())}")
        return view_func(request, *args, **kwargs)
    return wrapper


@login_required
def rubric_list(request):
    """Display a list of all rubrics with RBAC v0.1 compliance"""
    # RBAC v0.1 Validation: Assessment_Management,Rubrics,View,FULL,CONDITIONAL,CONDITIONAL,CONDITIONAL,NONE
    
    # Learner: NONE - No access to rubrics
    if request.user.role == 'learner':
        return HttpResponseForbidden("Access denied: Learners cannot access rubrics")
    
    # Apply role-based filtering
    if request.user.role == 'globaladmin' or request.user.is_superuser:
        # Global Admin: FULL access
        rubrics = Rubric.objects.all()
        
    elif request.user.role == 'superadmin':
        # Super Admin: CONDITIONAL access (business-scoped rubrics)
        from core.utils.business_filtering import filter_queryset_by_business
        rubrics = filter_queryset_by_business(
            Rubric.objects.all(), 
            request.user, 
            business_field_path='branch__business'
        )
        
    elif request.user.role == 'admin':
        # Branch Admin: CONDITIONAL access (branch-scoped rubrics)
        if request.user.branch:
            rubrics = Rubric.objects.filter(branch=request.user.branch)
        else:
            rubrics = Rubric.objects.none()
            
    elif request.user.role == 'instructor':
        # Instructor: CONDITIONAL access (rubrics they created OR for courses assigned to them)
        if request.user.branch:
            # Get rubrics created by this instructor
            created_rubrics = Rubric.objects.filter(created_by=request.user)
            
            # Get rubrics for courses assigned to this instructor
            from courses.models import Course
            assigned_courses = Course.objects.filter(instructor=request.user)
            assigned_rubrics = Rubric.objects.filter(course__in=assigned_courses)
            
            # Get rubrics for courses accessible through groups (instructor groups)
            from groups.models import BranchGroup
            instructor_groups = BranchGroup.objects.filter(
                memberships__user=request.user,
                memberships__is_active=True,
                memberships__custom_role__name__icontains='instructor'
            )
            group_accessible_courses = Course.objects.filter(accessible_groups__in=instructor_groups)
            group_rubrics = Rubric.objects.filter(course__in=group_accessible_courses)
            
            # Also include branch-level rubrics without specific course assignment
            branch_rubrics = Rubric.objects.filter(branch=request.user.branch, course__isnull=True)
            
            # Combine all accessible rubrics and apply distinct at the end
            rubrics = (created_rubrics | assigned_rubrics | group_rubrics | branch_rubrics).distinct()
        else:
            rubrics = Rubric.objects.none()
    else:
        # Other roles: No access
        return HttpResponseForbidden("Access denied: Insufficient permissions for rubrics access")
    
    # Define breadcrumbs for this view
    breadcrumbs = [
        {'url': '/', 'label': 'Dashboard', 'icon': 'fa-home'},
        {'label': 'Rubrics', 'icon': 'fa-th'}
    ]
    
    context = {
        'rubrics': rubrics,
        'breadcrumbs': breadcrumbs,
    }
    context.update(csrf(request))  # Add CSRF token to context
    return render(request, 'lms_rubrics/rubric_list.html', context)


@login_required
def create_rubric(request):
    """Create a new rubric - RBAC v0.1 Compliant"""
    # RBAC v0.1 Validation: Assessment_Management,Rubrics,Create,FULL,FULL,FULL,FULL,NONE
    
    # Learner: NONE - No access to rubric creation
    if request.user.role == 'learner':
        return HttpResponseForbidden("Access denied: Learners cannot create rubrics")
    
    # Check permissions for other roles
    if request.user.role not in ['globaladmin', 'superadmin', 'admin', 'instructor'] and not request.user.is_superuser:
        return HttpResponseForbidden("Access denied: Insufficient permissions for rubric creation")
    
    # Define breadcrumbs for this view
    breadcrumbs = [
        {'url': '/', 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': '/rubrics/', 'label': 'Rubrics', 'icon': 'fa-th'},
        {'label': 'Create Rubric', 'icon': 'fa-plus'}
    ]
    
    if request.method == 'POST':
        title = request.POST.get('title')
        
        # Create the rubric with proper branch assignment
        rubric_data = {
            'title': title,
            'created_by': request.user
        }
        
        # Auto-assign branch based on user role
        if request.user.role in ['admin', 'instructor'] and request.user.branch:
            rubric_data['branch'] = request.user.branch
        elif request.user.role == 'superadmin':
            # For Super Admin, they might specify a branch or it will be set later
            if request.user.branch:
                rubric_data['branch'] = request.user.branch
        
        rubric = Rubric.objects.create(**rubric_data)
        
        messages.success(request, f'Rubric "{title}" created successfully.')
        return redirect('lms_rubrics:edit', rubric_id=rubric.id)
    
    context = {
        'breadcrumbs': breadcrumbs,
    }
    context.update(csrf(request))  # Add CSRF token to context
    
    return render(request, 'lms_rubrics/create_rubric.html', context)


def rubric_detail(request, rubric_id):
    """Display details of a specific rubric - RBAC v0.1 Compliant"""
    # RBAC v0.1 Validation: Assessment_Management,Rubrics,View,FULL,CONDITIONAL,CONDITIONAL,CONDITIONAL,NONE
    
    # Check if rubric exists first before checking authentication
    # This ensures proper 404 responses instead of login redirects for non-existent rubrics
    rubric = get_object_or_404(Rubric, id=rubric_id)
    
    # Now check if user is authenticated
    if not request.user.is_authenticated:
        from django.contrib.auth.views import redirect_to_login
        return redirect_to_login(request.get_full_path())
    
    # Learner: NONE - No access to rubric details
    if request.user.role == 'learner':
        return HttpResponseForbidden("Access denied: Learners cannot access rubric details")
    
    # Validate rubric access based on user role
    if not _can_user_access_rubric(request.user, rubric):
        return HttpResponseForbidden("Access denied: You don't have permission to view this rubric")
    
    # Ensure all criteria have ratings
    ensure_criteria_have_ratings(rubric)
    
    # Define breadcrumbs for this view
    breadcrumbs = [
        {'url': '/', 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': '/rubrics/', 'label': 'Rubrics', 'icon': 'fa-th'},
        {'label': rubric.title, 'icon': 'fa-list-alt'}
    ]
    
    context = {
        'rubric': rubric,
        'breadcrumbs': breadcrumbs,
    }
    context.update(csrf(request))  # Add CSRF token to context
    return render(request, 'lms_rubrics/rubric_detail.html', context)


def _can_user_access_rubric(user, rubric):
    """
    Helper function to check if user can access a specific rubric
    Implements the RBAC v0.1 conditional access rules for rubrics
    """
    if user.role == 'globaladmin' or user.is_superuser:
        # Global Admin: FULL access
        return True
        
    elif user.role == 'superadmin':
        # Super Admin: CONDITIONAL access (business-scoped rubrics)
        if rubric.branch and hasattr(rubric.branch, 'business'):
            return user.business_assignments.filter(
                business=rubric.branch.business, 
                is_active=True
            ).exists()
        return False
        
    elif user.role == 'admin':
        # Branch Admin: CONDITIONAL access (branch-scoped rubrics)
        return user.branch and rubric.branch == user.branch
        
    elif user.role == 'instructor':
        # Instructor: CONDITIONAL access (rubrics they created OR for courses assigned to them)
        if not user.branch:
            return False
            
        # Check if instructor created this rubric
        if rubric.created_by == user:
            return True
            
        # Check if rubric is for a course assigned to this instructor
        if rubric.course:
            # Direct course assignment
            if rubric.course.instructor == user:
                return True
                
            # Course assignment through groups
            from groups.models import BranchGroup
            instructor_groups = BranchGroup.objects.filter(
                memberships__user=user,
                memberships__is_active=True,
                memberships__custom_role__name__icontains='instructor'
            )
            if rubric.course.accessible_groups.filter(id__in=instructor_groups).exists():
                return True
        
        # Check if it's a branch-level rubric without specific course assignment
        if not rubric.course and rubric.branch == user.branch:
            return True
            
        return False
    
    return False


def _can_user_edit_rubric(user, rubric):
    """
    Helper function to check if user can edit a specific rubric
    Implements the RBAC v0.1 conditional access rules for rubric editing
    """
    if user.role == 'globaladmin' or user.is_superuser:
        # Global Admin: FULL access
        return True
        
    elif user.role == 'superadmin':
        # Super Admin: CONDITIONAL access (business-scoped rubrics)
        if rubric.branch and hasattr(rubric.branch, 'business'):
            return user.business_assignments.filter(
                business=rubric.branch.business, 
                is_active=True
            ).exists()
        return False
        
    elif user.role == 'admin':
        # Branch Admin: CONDITIONAL access (branch-scoped rubrics)
        return user.branch and rubric.branch == user.branch
        
    elif user.role == 'instructor':
        # Instructor: CONDITIONAL access (rubrics they created OR for courses assigned to them)
        if not user.branch:
            return False
            
        # Check if instructor created this rubric
        if rubric.created_by == user:
            return True
            
        # Check if rubric is for a course assigned to this instructor
        if rubric.course:
            # Direct course assignment
            if rubric.course.instructor == user:
                return True
                
            # Course assignment through groups
            from groups.models import BranchGroup
            instructor_groups = BranchGroup.objects.filter(
                memberships__user=user,
                memberships__is_active=True,
                memberships__custom_role__name__icontains='instructor'
            )
            if rubric.course.accessible_groups.filter(id__in=instructor_groups).exists():
                return True
        
        # Branch-level rubrics can only be edited by their creators for instructors
        if not rubric.course and rubric.created_by == user:
            return True
            
        return False
    
    return False


def ensure_criteria_have_ratings(rubric):
    """Ensure all criteria in a rubric have at least default ratings."""
    for criterion in rubric.criteria.all():
        if criterion.ratings.count() == 0:
            # Create default ratings
            RubricRating.objects.create(
                criterion=criterion,
                title="Excellent",
                description="Full marks",
                points=criterion.points,
                position=0
            )
            
            RubricRating.objects.create(
                criterion=criterion,
                title="Needs Improvement",
                description="No marks",
                points=0,
                position=1
            )


def edit_rubric(request, rubric_id):
    """Edit an existing rubric - RBAC v0.1 Compliant"""
    # RBAC v0.1 Validation: Assessment_Management,Rubrics,Edit,FULL,CONDITIONAL,CONDITIONAL,CONDITIONAL,NONE
    
    # Check if rubric exists first before checking authentication
    rubric = get_object_or_404(Rubric, id=rubric_id)
    
    # Now check if user is authenticated
    if not request.user.is_authenticated:
        from django.contrib.auth.views import redirect_to_login
        return redirect_to_login(request.get_full_path())
    
    # Learner: NONE - No access to rubric editing
    if request.user.role == 'learner':
        return HttpResponseForbidden("Access denied: Learners cannot edit rubrics")
    
    # Validate rubric edit access based on user role
    if not _can_user_edit_rubric(request.user, rubric):
        return HttpResponseForbidden("Access denied: You don't have permission to edit this rubric")
    
    # Define breadcrumbs for this view
    breadcrumbs = [
        {'url': '/', 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': '/rubrics/', 'label': 'Rubrics', 'icon': 'fa-th'},
        {'url': f'/rubrics/{rubric.id}/', 'label': rubric.title, 'icon': 'fa-list-alt'},
        {'label': 'Edit', 'icon': 'fa-edit'}
    ]
    
    if request.method == 'POST':
        # Update the basic rubric information
        rubric.title = request.POST.get('title')
        rubric.save()
        
        # Handle updates to criteria and ratings
        for criterion in rubric.criteria.all():
            criterion_id = criterion.id
            
            # Update criterion description if it exists in the form
            description_key = f'criterion_description_{criterion_id}'
            if description_key in request.POST:
                criterion.description = request.POST.get(description_key)
            
            # Update criterion points if it exists in the form
            points_key = f'criterion_points_{criterion_id}'
            if points_key in request.POST:
                criterion.points = float(request.POST.get(points_key) or 0)
            
            # Update use_range if it exists
            use_range_key = f'use_range_{criterion_id}'
            criterion.use_range = use_range_key in request.POST
            
            criterion.save()
            
            # Update ratings if they exist in the form
            for rating in criterion.ratings.all():
                rating_id = rating.id
                
                # Update rating title
                rating_title_key = f'rating_{rating_id}_title'
                if rating_title_key in request.POST:
                    rating.title = request.POST.get(rating_title_key)
                
                # Update rating description
                rating_desc_key = f'rating_{rating_id}_description'
                if rating_desc_key in request.POST:
                    rating.description = request.POST.get(rating_desc_key)
                
                # Update rating points
                rating_points_key = f'rating_{rating_id}_points'
                if rating_points_key in request.POST:
                    rating.points = float(request.POST.get(rating_points_key) or 0)
                
                rating.save()
        
        messages.success(request, f'Rubric "{rubric.title}" updated successfully.')
        return redirect('lms_rubrics:detail', rubric_id=rubric.id)
    
    # Get outcome connections for this rubric's criteria
    from lms_outcomes.models import RubricCriterionOutcome
    outcome_connections = {}
    calculation_examples = {}
    
    for criterion in rubric.criteria.all():
        connections = RubricCriterionOutcome.objects.filter(
            criterion=criterion
        ).select_related('outcome')
        
        if connections.exists():
            outcome_connections[criterion.id] = connections
            
            # Generate calculation method examples for each connected outcome
            for connection in connections:
                outcome = connection.outcome
                if outcome.id not in calculation_examples:
                    calculation_examples[outcome.id] = _get_calculation_method_example(outcome)
    
    context = {
        'rubric': rubric,
        'breadcrumbs': breadcrumbs,
        'outcome_connections': outcome_connections,
        'calculation_examples': calculation_examples,
    }
    context.update(csrf(request))  # Add CSRF token to context
    return render(request, 'lms_rubrics/edit_rubric.html', context)


def _get_calculation_method_example(outcome):
    """Generate an example of how the calculation method works"""
    method = outcome.calculation_method
    examples = {
        'weighted_average': {
            'description': f'Recent evaluations get {outcome.last_item_weight}% weight, older ones share remaining {100-outcome.last_item_weight}%',
            'example': f'3 evaluations: [2.0, 3.0, 4.0] → Latest (4.0) × 0.{outcome.last_item_weight} + Others weighted → ~3.3'
        },
        'decaying_average': {
            'description': f'Exponential decay with {outcome.last_item_weight}% decay factor',
            'example': f'3 evaluations: [2.0, 3.0, 4.0] → 4.0×1.0 + 3.0×0.{outcome.last_item_weight} + 2.0×0.{outcome.last_item_weight}² → ~3.5'
        },
        'n_times': {
            'description': f'Must achieve mastery ({outcome.mastery_points}+ points) {outcome.times_to_achieve} times',
            'example': f'5 evaluations: [2.0, 3.5, 2.5, 4.0, 3.5] → 3 times ≥ {outcome.mastery_points}, need {outcome.times_to_achieve} → Not achieved'
        },
        'most_recent': {
            'description': 'Uses only the most recent evaluation score',
            'example': '3 evaluations: [2.0, 3.0, 4.0] → Result: 4.0'
        },
        'highest': {
            'description': 'Uses the highest score achieved',
            'example': '3 evaluations: [2.0, 4.0, 3.0] → Result: 4.0'
        },
        'average': {
            'description': 'Simple average of all evaluation scores',
            'example': '3 evaluations: [2.0, 3.0, 4.0] → (2.0+3.0+4.0)/3 = 3.0'
        },
        'no_point': {
            'description': f'Binary: Met if any evaluation ≥ {outcome.mastery_points}, otherwise Not Met',
            'example': f'3 evaluations: [2.0, 3.5, 2.5] → Highest: 3.5 ≥ {outcome.mastery_points} → Met'
        }
    }
    
    return examples.get(method, {
        'description': 'Custom calculation method',
        'example': 'Contact administrator for details'
    })


def delete_rubric(request, rubric_id):
    """Delete a rubric - RBAC v0.1 Compliant"""
    # RBAC v0.1 Validation: Assessment_Management,Rubrics,Delete,FULL,CONDITIONAL,CONDITIONAL,CONDITIONAL,NONE
    
    # Check if rubric exists first before checking authentication
    rubric = get_object_or_404(Rubric, id=rubric_id)
    
    # Now check if user is authenticated
    if not request.user.is_authenticated:
        from django.contrib.auth.views import redirect_to_login
        return redirect_to_login(request.get_full_path())
    
    # Learner: NONE - No access to rubric deletion
    if request.user.role == 'learner':
        return HttpResponseForbidden("Access denied: Learners cannot delete rubrics")
    
    # Enhanced delete permissions - instructors can only delete rubrics they created
    can_delete = False
    
    if request.user.role == 'globaladmin' or request.user.is_superuser:
        # Global Admin: FULL access
        can_delete = True
    elif request.user.role == 'superadmin':
        # Super Admin: CONDITIONAL access (business-scoped rubrics)
        if rubric.branch and hasattr(rubric.branch, 'business'):
            can_delete = request.user.business_assignments.filter(
                business=rubric.branch.business, 
                is_active=True
            ).exists()
    elif request.user.role == 'admin':
        # Branch Admin: CONDITIONAL access (branch-scoped rubrics)
        can_delete = request.user.branch and rubric.branch == request.user.branch
    elif request.user.role == 'instructor':
        # Instructor: Only rubrics they created
        can_delete = rubric.created_by == request.user
    
    if not can_delete:
        return HttpResponseForbidden("Access denied: You don't have permission to delete this rubric")
    
    # Define breadcrumbs for this view
    breadcrumbs = [
        {'url': '/', 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': '/rubrics/', 'label': 'Rubrics', 'icon': 'fa-th'},
        {'url': f'/rubrics/{rubric.id}/', 'label': rubric.title, 'icon': 'fa-list-alt'},
        {'label': 'Delete', 'icon': 'fa-trash'}
    ]
    
    if request.method == 'POST':
        rubric_title = rubric.title
        rubric.delete()
        messages.success(request, f'Rubric "{rubric_title}" deleted successfully.')
        return redirect('lms_rubrics:list')
    
    context = {
        'rubric': rubric,
        'breadcrumbs': breadcrumbs,
    }
    context.update(csrf(request))  # Add CSRF token to context
    return render(request, 'lms_rubrics/delete_rubric.html', context)


def add_criterion(request, rubric_id):
    """Add a criterion to a rubric - RBAC v0.1 Compliant"""
    # RBAC v0.1 Validation: Assessment_Management,Rubrics,Edit,FULL,CONDITIONAL,CONDITIONAL,CONDITIONAL,NONE
    
    # Check if rubric exists first before checking authentication
    rubric = get_object_or_404(Rubric, id=rubric_id)
    
    # Now check if user is authenticated
    if not request.user.is_authenticated:
        from django.contrib.auth.views import redirect_to_login
        return redirect_to_login(request.get_full_path())
    
    # Learner: NONE - No access to rubric editing
    if request.user.role == 'learner':
        return HttpResponseForbidden("Access denied: Learners cannot edit rubrics")
    
    # Validate rubric edit access based on user role
    if not _can_user_edit_rubric(request.user, rubric):
        return HttpResponseForbidden("Access denied: You don't have permission to edit this rubric")
    
    # Check if there's an outcome_id in the URL params and fetch it if available
    outcome_id = request.GET.get('outcome_id')
    outcome = None
    
    # Try to import the Outcome model only if outcome_id is provided
    if outcome_id:
        try:
            from lms_outcomes.models import Outcome
            outcome = Outcome.objects.get(id=outcome_id)
            
            # Validate outcome access based on user role (same RBAC rules as outcomes)
            if request.user.role == 'superadmin':
                from core.utils.business_filtering import filter_queryset_by_business
                accessible_outcomes = filter_queryset_by_business(
                    Outcome.objects.all(), 
                    request.user, 
                    business_field_path='branch__business'
                )
                if outcome not in accessible_outcomes:
                    outcome = None  # User can't access this outcome
            elif request.user.role in ['admin', 'instructor']:
                if not request.user.branch or outcome.branch != request.user.branch:
                    outcome = None  # User can't access this outcome
            # Global admin has full access, so no additional checks needed
        except:
            # Handle the case where the outcome doesn't exist or the app isn't installed
            outcome = None
    
    # Define breadcrumbs for this view
    breadcrumbs = [
        {'url': '/', 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': '/rubrics/', 'label': 'Rubrics', 'icon': 'fa-th'},
        {'url': f'/rubrics/{rubric.id}/', 'label': rubric.title, 'icon': 'fa-list-alt'},
        {'label': 'Add Criterion', 'icon': 'fa-plus'}
    ]
    
    if request.method == 'POST':
        description = request.POST.get('description')
        points = float(request.POST.get('points', 0)) if request.POST.get('points') else 0
        use_range = request.POST.get('use_range') == 'on'
        
        position = rubric.criteria.count()
        
        criterion = RubricCriterion.objects.create(
            rubric=rubric,
            description=description,
            points=points,
            position=position,
            use_range=use_range
        )
        
        # Determine which ratings to create based on the outcome if available
        ratings_data = []
        if outcome and outcome.proficiency_ratings and hasattr(outcome, 'calculation_method'):
            # Special handling for "no_point" calculation method
            if outcome.calculation_method == 'no_point':
                # Use the specific Met/Not met ratings for no_point outcomes
                ratings_data = [
                    {
                        "title": "Met",
                        "description": "Criteria met",
                        "points": 1,
                        "position": 0
                    },
                    {
                        "title": "Not met",
                        "description": "Criteria not met",
                        "points": 0,
                        "position": 1
                    }
                ]
            else:
                # For other calculation methods, import the proficiency ratings directly
                for i, rating in enumerate(outcome.proficiency_ratings):
                    # Ensure the rating points don't exceed the criterion points
                    rating_points = min(float(rating.get('points', 0)), points)
                    ratings_data.append({
                        "title": rating.get('name', f"Rating {i+1}"),
                        "description": f"{rating.get('name', 'Rating')} level achievement",
                        "points": rating_points,
                        "position": i
                    })
        
        # If no ratings were created from an outcome, use default ratings
        if not ratings_data:
            ratings_data = [
                {
                    "title": "Excellent",
                    "description": "Full marks",
                    "points": points,
                    "position": 0
                },
                {
                    "title": "Needs Improvement", 
                    "description": "No marks",
                    "points": 0,
                    "position": 1
                }
            ]
        
        for rating_data in ratings_data:
            RubricRating.objects.create(
                criterion=criterion,
                **rating_data
            )
        
        # No need to manually update points, the model's save method will handle it
        # The rubric.save() will be called by the criterion's save method
        
        messages.success(request, f'Criterion added to rubric "{rubric.title}".')
        return redirect('lms_rubrics:edit', rubric_id=rubric.id)
    
    context = {
        'rubric': rubric,
        'outcome': outcome,
        'breadcrumbs': breadcrumbs,
    }
    context.update(csrf(request))  # Add CSRF token to context
    return render(request, 'lms_rubrics/add_criterion.html', context)


def delete_criterion(request, criterion_id):
    """Delete a criterion from a rubric - RBAC v0.1 Compliant"""
    # RBAC v0.1 Validation: Assessment_Management,Rubrics,Edit,FULL,CONDITIONAL,CONDITIONAL,CONDITIONAL,NONE
    
    # Check if criterion exists first before checking authentication
    criterion = get_object_or_404(RubricCriterion, id=criterion_id)
    rubric = criterion.rubric
    
    # Now check if user is authenticated
    if not request.user.is_authenticated:
        from django.contrib.auth.views import redirect_to_login
        return redirect_to_login(request.get_full_path())
    
    # Learner: NONE - No access to rubric editing
    if request.user.role == 'learner':
        return HttpResponseForbidden("Access denied: Learners cannot edit rubrics")
    
    # Validate rubric edit access based on user role
    if not _can_user_edit_rubric(request.user, rubric):
        return HttpResponseForbidden("Access denied: You don't have permission to edit this rubric")
    
    if request.method == 'POST':
        criterion.delete()
        
        # Update positions for remaining criteria
        for i, crit in enumerate(rubric.criteria.all().order_by('position')):
            crit.position = i
            crit.save()
        
        messages.success(request, 'Criterion deleted successfully.')
        return redirect('lms_rubrics:edit', rubric_id=rubric.id)
    
    # Define breadcrumbs for this view
    breadcrumbs = [
        {'url': '/', 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': '/rubrics/', 'label': 'Rubrics', 'icon': 'fa-th'},
        {'url': f'/rubrics/{rubric.id}/', 'label': rubric.title, 'icon': 'fa-list-alt'},
        {'label': 'Delete Criterion', 'icon': 'fa-trash'}
    ]
    
    context = {
        'criterion': criterion,
        'rubric': rubric,
        'breadcrumbs': breadcrumbs,
    }
    context.update(csrf(request))  # Add CSRF token to context
    return render(request, 'lms_rubrics/delete_criterion.html', context)


def add_rating(request, criterion_id):
    """Add a rating to a criterion - RBAC v0.1 Compliant"""
    # RBAC v0.1 Validation: Assessment_Management,Rubrics,Edit,FULL,CONDITIONAL,CONDITIONAL,CONDITIONAL,NONE
    
    # Check if criterion exists first before checking authentication
    criterion = get_object_or_404(RubricCriterion, id=criterion_id)
    rubric = criterion.rubric
    
    # Now check if user is authenticated
    if not request.user.is_authenticated:
        from django.contrib.auth.views import redirect_to_login
        return redirect_to_login(request.get_full_path())
    
    # Learner: NONE - No access to rubric editing
    if request.user.role == 'learner':
        return HttpResponseForbidden("Access denied: Learners cannot edit rubrics")
    
    # Validate rubric edit access based on user role
    if not _can_user_edit_rubric(request.user, rubric):
        return HttpResponseForbidden("Access denied: You don't have permission to edit this rubric")
    
    # Define breadcrumbs for this view
    breadcrumbs = [
        {'url': '/', 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': '/rubrics/', 'label': 'Rubrics', 'icon': 'fa-th'},
        {'url': f'/rubrics/{rubric.id}/', 'label': rubric.title, 'icon': 'fa-list-alt'},
        {'label': 'Add Rating', 'icon': 'fa-plus'}
    ]
    
    if request.method == 'POST':
        title = request.POST.get('title')
        description = request.POST.get('description')
        points = float(request.POST.get('points', 0)) if request.POST.get('points') else 0
        
        # Validate that points don't exceed criterion maximum
        if points > criterion.points:
            messages.error(request, f'Rating points cannot exceed criterion maximum of {criterion.points}')
            return render(request, 'lms_rubrics/add_rating.html', {
                'criterion': criterion,
                'rubric': rubric,
                'breadcrumbs': breadcrumbs,
            })
        
        position = criterion.ratings.count()
        
        RubricRating.objects.create(
            criterion=criterion,
            title=title,
            description=description,
            points=points,
            position=position
        )
        
        messages.success(request, f'Rating "{title}" added to criterion.')
        return redirect('lms_rubrics:edit', rubric_id=rubric.id)
    
    context = {
        'criterion': criterion,
        'rubric': rubric,
        'breadcrumbs': breadcrumbs,
    }
    context.update(csrf(request))  # Add CSRF token to context
    return render(request, 'lms_rubrics/add_rating.html', context)


def delete_rating(request, rating_id):
    """Delete a rating from a criterion - RBAC v0.1 Compliant"""
    # RBAC v0.1 Validation: Assessment_Management,Rubrics,Edit,FULL,CONDITIONAL,CONDITIONAL,CONDITIONAL,NONE
    
    # Check if rating exists first before checking authentication
    rating = get_object_or_404(RubricRating, id=rating_id)
    criterion = rating.criterion
    rubric = criterion.rubric
    
    # Now check if user is authenticated
    if not request.user.is_authenticated:
        from django.contrib.auth.views import redirect_to_login
        return redirect_to_login(request.get_full_path())
    
    # Learner: NONE - No access to rubric editing
    if request.user.role == 'learner':
        return HttpResponseForbidden("Access denied: Learners cannot edit rubrics")
    
    # Validate rubric edit access based on user role
    if not _can_user_edit_rubric(request.user, rubric):
        return HttpResponseForbidden("Access denied: You don't have permission to edit this rubric")
    
    if request.method == 'POST':
        rating_title = rating.title
        rating.delete()
        
        # Update positions for remaining ratings
        for i, rat in enumerate(criterion.ratings.all().order_by('position')):
            rat.position = i
            rat.save()
        
        messages.success(request, f'Rating "{rating_title}" deleted successfully.')
        return redirect('lms_rubrics:edit', rubric_id=rubric.id)
    
    # Define breadcrumbs for this view
    breadcrumbs = [
        {'url': '/', 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': '/rubrics/', 'label': 'Rubrics', 'icon': 'fa-th'},
        {'url': f'/rubrics/{rubric.id}/', 'label': rubric.title, 'icon': 'fa-list-alt'},
        {'label': 'Delete Rating', 'icon': 'fa-trash'}
    ]
    
    context = {
        'rating': rating,
        'criterion': criterion,
        'rubric': rubric,
        'breadcrumbs': breadcrumbs,
    }
    context.update(csrf(request))  # Add CSRF token to context
    return render(request, 'lms_rubrics/delete_rating.html', context)


def edit_rating(request, rating_id):
    """Edit a rating - RBAC v0.1 Compliant"""
    # RBAC v0.1 Validation: Assessment_Management,Rubrics,Edit,FULL,CONDITIONAL,CONDITIONAL,CONDITIONAL,NONE
    
    # Check if rating exists first before checking authentication
    rating = get_object_or_404(RubricRating, id=rating_id)
    criterion = rating.criterion
    rubric = criterion.rubric
    
    # Now check if user is authenticated
    if not request.user.is_authenticated:
        from django.contrib.auth.views import redirect_to_login
        return redirect_to_login(request.get_full_path())
    
    # Learner: NONE - No access to rubric editing
    if request.user.role == 'learner':
        return HttpResponseForbidden("Access denied: Learners cannot edit rubrics")
    
    # Validate rubric edit access based on user role
    if not _can_user_edit_rubric(request.user, rubric):
        return HttpResponseForbidden("Access denied: You don't have permission to edit this rubric")
    
    # Define breadcrumbs for this view
    breadcrumbs = [
        {'url': '/', 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': '/rubrics/', 'label': 'Rubrics', 'icon': 'fa-th'},
        {'url': f'/rubrics/{rubric.id}/', 'label': rubric.title, 'icon': 'fa-list-alt'},
        {'label': f'Edit Rating: {rating.title}', 'icon': 'fa-edit'}
    ]
    
    if request.method == 'POST':
        rating.title = request.POST.get('title')
        rating.description = request.POST.get('description')
        new_points = float(request.POST.get('points', 0)) if request.POST.get('points') else 0
        
        # Validate that points don't exceed criterion maximum
        if new_points > criterion.points:
            messages.error(request, f'Rating points cannot exceed criterion maximum of {criterion.points}')
        else:
            rating.points = new_points
            rating.save()
            messages.success(request, f'Rating "{rating.title}" updated successfully.')
            return redirect('lms_rubrics:edit', rubric_id=rubric.id)
    
    context = {
        'rating': rating,
        'criterion': criterion,
        'rubric': rubric,
        'breadcrumbs': breadcrumbs,
    }
    context.update(csrf(request))  # Add CSRF token to context
    return render(request, 'lms_rubrics/edit_rating.html', context)


def update_criterion_range(request, criterion_id):
    """Update whether a criterion uses range scoring - RBAC v0.1 Compliant"""
    # RBAC v0.1 Validation: Assessment_Management,Rubrics,Edit,FULL,CONDITIONAL,CONDITIONAL,CONDITIONAL,NONE
    
    # Check if criterion exists first before checking authentication
    criterion = get_object_or_404(RubricCriterion, id=criterion_id)
    rubric = criterion.rubric
    
    # Now check if user is authenticated
    if not request.user.is_authenticated:
        return JsonResponse({'success': False, 'error': "Authentication required"})
    
    # Learner: NONE - No access to rubric editing
    if request.user.role == 'learner':
        return JsonResponse({'success': False, 'error': "Access denied: Learners cannot edit rubrics"})
    
    # Validate rubric edit access based on user role
    if not _can_user_edit_rubric(request.user, rubric):
        return JsonResponse({'success': False, 'error': "Access denied: You don't have permission to edit this rubric"})
    
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            use_range = data.get('use_range', False)
            
            criterion.use_range = use_range
            criterion.save()
            
            return JsonResponse({
                'success': True,
                'message': f'Criterion range setting updated successfully'
            })
        except json.JSONDecodeError:
            return JsonResponse({'success': False, 'error': 'Invalid JSON data'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'})


def edit_criterion(request, criterion_id):
    """Edit a criterion - RBAC v0.1 Compliant"""
    # RBAC v0.1 Validation: Assessment_Management,Rubrics,Edit,FULL,CONDITIONAL,CONDITIONAL,CONDITIONAL,NONE
    
    # Check if criterion exists first before checking authentication
    criterion = get_object_or_404(RubricCriterion, id=criterion_id)
    rubric = criterion.rubric
    
    # Now check if user is authenticated
    if not request.user.is_authenticated:
        from django.contrib.auth.views import redirect_to_login
        return redirect_to_login(request.get_full_path())
    
    # Learner: NONE - No access to rubric editing
    if request.user.role == 'learner':
        return HttpResponseForbidden("Access denied: Learners cannot edit rubrics")
    
    # Validate rubric edit access based on user role
    if not _can_user_edit_rubric(request.user, rubric):
        return HttpResponseForbidden("Access denied: You don't have permission to edit this rubric")
    
    # Define breadcrumbs for this view
    breadcrumbs = [
        {'url': '/', 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': '/rubrics/', 'label': 'Rubrics', 'icon': 'fa-th'},
        {'url': f'/rubrics/{rubric.id}/', 'label': rubric.title, 'icon': 'fa-list-alt'},
        {'label': f'Edit Criterion', 'icon': 'fa-edit'}
    ]
    
    if request.method == 'POST':
        criterion.description = request.POST.get('description')
        new_points = float(request.POST.get('points', 0)) if request.POST.get('points') else 0
        criterion.use_range = request.POST.get('use_range') == 'on'
        
        # Validate that the new points don't break existing ratings
        max_rating_points = criterion.ratings.aggregate(
            max_points=models.Max('points')
        )['max_points'] or 0
        
        if new_points < max_rating_points:
            messages.error(request, f'Criterion points cannot be less than the highest rating points ({max_rating_points})')
        else:
            criterion.points = new_points
            criterion.save()
            messages.success(request, 'Criterion updated successfully.')
            return redirect('lms_rubrics:edit', rubric_id=rubric.id)
    
    context = {
        'criterion': criterion,
        'rubric': rubric,
        'breadcrumbs': breadcrumbs,
    }
    context.update(csrf(request))  # Add CSRF token to context
    return render(request, 'lms_rubrics/edit_criterion.html', context) 