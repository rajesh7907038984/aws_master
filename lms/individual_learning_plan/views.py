from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, Http404, HttpResponse
from django.urls import reverse
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.contrib.auth import get_user_model
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
import json

from .models import (
    IndividualLearningPlan, SENDAccommodation, StrengthWeakness,
    LearningPreference, StatementOfPurpose, CareerGoal,
    LearningGoal, LearningProgress, EducatorNote,
    InductionChecklist, InductionDocument, InductionDocumentReadReceipt,
    HealthSafetyQuestionnaire, HealthSafetyDocument, HealthSafetyDocumentReadReceipt
)
from .forms import (
    SENDAccommodationForm, StrengthWeaknessForm, LearningPreferenceForm,
    StatementOfPurposeForm, CareerGoalForm, LearningGoalForm,
    LearningProgressForm, EducatorNoteForm, LearningGoalTeacherInputForm,
    LearningProgressTeacherForm, SENDAccommodationFormSet,
    StrengthWeaknessFormSet, LearningPreferenceFormSet,
    LearningGoalFormSet, EducatorNoteFormSet,
    InductionChecklistForm, InductionDocumentForm, InductionLearnerResponseForm,
    InductionDocumentFormSet,
    HealthSafetyQuestionnaireForm, HealthSafetyLearnerResponseForm,
    HealthSafetyDocumentForm, HealthSafetyDocumentFormSet
)

User = get_user_model()


def check_ilp_permissions(user, target_user, action='view'):
    """
    Enhanced permission checker for ILP with detailed role-based access control
    
    Args:
        user: The requesting user
        target_user: The user whose ILP is being accessed
        action: 'view', 'edit', 'create', or specific component actions
    
    Returns:
        dict: {'allowed': bool, 'role': str, 'permissions': dict}
    """
    if not user.is_authenticated:
        return {'allowed': False, 'role': None, 'permissions': {}}
    
    user_role = user.role
    
    # Define comprehensive permissions structure
    permissions = {
        'view': {
            'send_accommodations': False,
            'strengths_weaknesses': False,
            'learning_preferences': False,
            'statement_of_purpose': False,
            'career_goal': False,
            'learning_goals': False,
            'progress_tracking': False,
            'educator_notes': False,
            'custom_targets': False,
            'induction_checklist': False,
            'health_safety_questionnaire': False
        },
        'edit': {
            'send_accommodations': False,
            'strengths_weaknesses': False,
            'learning_preferences': False,
            'statement_of_purpose': False,
            'career_goal': False,
            'learning_goals': False,
            'progress_tracking': False,
            'educator_notes': False,
            'custom_targets': False,
            'induction_checklist': False,
            'health_safety_questionnaire': False
        },
        'create': {
            'send_accommodations': False,
            'strengths_weaknesses': False,
            'learning_preferences': False,
            'statement_of_purpose': False,
            'career_goal': False,
            'learning_goals': False,
            'progress_tracking': False,
            'educator_notes': False,
            'custom_targets': False,
            'induction_checklist': False,
            'health_safety_questionnaire': False
        }
    }
    
    allowed = False
    
    # SuperAdmin and Admin have full access to all ILPs
    if user_role in ['superadmin', 'admin']:
        allowed = True
        for action_type in permissions:
            for component in permissions[action_type]:
                permissions[action_type][component] = True
    
    # Instructors can access their assigned students
    elif user_role == 'instructor':
        # Check if target_user is assigned to this instructor
        if (target_user == user or 
            target_user in user.assigned_students.all() or
            hasattr(target_user, 'assigned_instructor') and target_user.assigned_instructor == user):
            allowed = True
            
            # Full view access
            for component in permissions['view']:
                permissions['view'][component] = True
            
            # Full edit access except learner-specific items
            for component in permissions['edit']:
                if component not in ['custom_targets']:  # Custom targets are learner-only
                    permissions['edit'][component] = True
            
            # Full create access except learner-specific items
            for component in permissions['create']:
                if component not in ['custom_targets']:
                    permissions['create'][component] = True
    
    # Learners can only access their own ILP with limited permissions
    elif user_role == 'learner':
        if target_user == user:
            allowed = True
            
            # View access to most components
            view_allowed = ['strengths_weaknesses', 'learning_preferences', 'statement_of_purpose', 
                          'career_goal', 'learning_goals', 'progress_tracking', 'custom_targets', 'induction_checklist', 'health_safety_questionnaire']
            for component in view_allowed:
                permissions['view'][component] = True
            
            # Limited edit access - strengths/weaknesses, custom targets and progress updates
            edit_allowed = ['strengths_weaknesses', 'custom_targets', 'progress_tracking', 'health_safety_questionnaire']
            for component in edit_allowed:
                permissions['edit'][component] = True
            
            # Can create their own strengths/weaknesses, custom targets and progress updates
            create_allowed = ['strengths_weaknesses', 'custom_targets', 'progress_tracking']
            for component in create_allowed:
                permissions['create'][component] = True
    
    return {
        'allowed': allowed,
        'role': user_role,
        'permissions': permissions
    }


def get_component_permissions(user, target_user, component):
    """Get detailed permissions for a specific ILP component"""
    perm_check = check_ilp_permissions(user, target_user, 'view')
    
    if not perm_check['allowed']:
        return {'can_view': False, 'can_edit': False, 'can_create': False}
    
    user_role = user.role
    
    # Standard permissions for most components
    standard_permissions = {
        'superadmin': {'can_view': True, 'can_edit': True, 'can_create': True},
        'admin': {'can_view': True, 'can_edit': True, 'can_create': True},
        'instructor': {'can_view': True, 'can_edit': True, 'can_create': True},
        'learner': {'can_view': False, 'can_edit': False, 'can_create': False}
    }
    
    # Component-specific overrides
    component_specific = {
        'induction_checklist': {
            'learner': {'can_view': True, 'can_edit': True, 'can_create': False} if target_user == user else {'can_view': False, 'can_edit': False, 'can_create': False}
        },
        'health_safety_questionnaire': {
            'learner': {'can_view': True, 'can_edit': True, 'can_create': False} if target_user == user else {'can_view': False, 'can_edit': False, 'can_create': False}
        },
        'strengths_weaknesses': {
            'learner': {'can_view': True, 'can_edit': True, 'can_create': True} if target_user == user else {'can_view': False, 'can_edit': False, 'can_create': False}
        },
        'custom_targets': {
            'learner': {'can_view': True, 'can_edit': True, 'can_create': True} if target_user == user else {'can_view': False, 'can_edit': False, 'can_create': False}
        },
        'progress_tracking': {
            'learner': {'can_view': True, 'can_edit': True, 'can_create': True} if target_user == user else {'can_view': False, 'can_edit': False, 'can_create': False}
        }
    }
    
    # Get base permissions
    permissions = standard_permissions.get(user_role, {'can_view': False, 'can_edit': False, 'can_create': False})
    
    # Apply component-specific overrides
    if component in component_specific and user_role in component_specific[component]:
        permissions.update(component_specific[component][user_role])
    
    return permissions








@login_required
def create_ilp_component(request, user_id, component):
    """Enhanced create view with role-based permissions"""
    target_user = get_object_or_404(User, id=user_id)
    
    # Check permissions
    component_perms = get_component_permissions(request.user, target_user, component)
    if not component_perms['can_create']:
        raise PermissionDenied(f"You don't have permission to create {component.replace('_', ' ')}.")
    
    # Get or create ILP
    ilp, created = IndividualLearningPlan.objects.get_or_create(
        user=target_user,
        defaults={'created_by': request.user}
    )
    
    # Define breadcrumbs
    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'label': f'Create {component.replace("_", " ").title()}', 'icon': 'fa-plus'}
    ]
    
    # Handle different components
    if component == 'accommodation':
        form_class = SENDAccommodationForm
        template = 'individual_learning_plan/forms/accommodation_form.html'
        model_class = SENDAccommodation
        
    elif component == 'strength_weakness':
        form_class = StrengthWeaknessForm
        template = 'individual_learning_plan/forms/strength_weakness_form.html'
        model_class = StrengthWeakness
        
    elif component == 'learning_preference':
        form_class = LearningPreferenceForm
        template = 'individual_learning_plan/forms/learning_preference_form.html'
        model_class = LearningPreference
        
    elif component == 'statement_of_purpose':
        form_class = StatementOfPurposeForm
        template = 'individual_learning_plan/forms/statement_of_purpose_form.html'
        
        # Check if SOP already exists
        if hasattr(ilp, 'statement_of_purpose'):
            messages.info(request, 'Statement of Purpose already exists. Redirecting to edit.')
            return redirect('ilp:edit_component', user_id=user_id, component='statement_of_purpose')
            
    elif component == 'career_goal':
        form_class = CareerGoalForm
        template = 'individual_learning_plan/forms/career_goal_form.html'
        
        # Check if career goal already exists
        if hasattr(ilp, 'career_goal'):
            messages.info(request, 'Career Goal already exists. Redirecting to edit.')
            return redirect('ilp:edit_component', user_id=user_id, component='career_goal')
            
    elif component == 'learning_goal' or component == 'custom_targets':
        form_class = LearningGoalForm
        template = 'individual_learning_plan/forms/learning_goal_form.html'
        model_class = LearningGoal
        
    elif component == 'educator_note' and component_perms['can_create']:
        form_class = EducatorNoteForm
        template = 'individual_learning_plan/forms/educator_note_form.html'
        model_class = EducatorNote
        
    else:
        raise Http404("Invalid component or insufficient permissions")
    
    if request.method == 'POST':
        # Pass user role to form for role-based field restrictions
        form_kwargs = {}
        if component == 'strength_weakness':
            form_kwargs['user_role'] = request.user.role
            form_kwargs['ilp'] = ilp
        elif component in ['learning_goal', 'custom_targets']:
            form_kwargs['user'] = target_user
            form_kwargs['user_role'] = request.user.role
            
        form = form_class(request.POST, request.FILES, **form_kwargs)
        
        if form.is_valid():
            try:
                with transaction.atomic():
                    instance = form.save(commit=False)
                    
                    # Set ILP reference
                    if hasattr(instance, 'ilp_id') and instance.ilp_id is None:
                        instance.ilp = ilp
                    elif hasattr(instance, 'ilp') and instance.ilp is None:
                        instance.ilp = ilp
                    
                    # Print debug information for strength_weakness component
                    if component == 'strength_weakness':
                        print(f"Debug - ilp: {ilp.id}, instance.ilp: {getattr(instance, 'ilp_id', None)}")
                    
                    # Set creator/updater
                    if hasattr(instance, 'created_by'):
                        instance.created_by = request.user
                    if hasattr(instance, 'updated_by'):
                        instance.updated_by = request.user
                    
                    # Special handling for learning goals/custom targets
                    if component == 'custom_targets':
                        instance.goal_type = 'custom'
                        instance.created_by = request.user
                    
                    # Ensure ilp is set for all relevant components before saving
                    if component in ['accommodation', 'strength_weakness', 'learning_preference', 'learning_goal', 'educator_note']:
                        instance.ilp = ilp
                    
                    instance.save()
                    
                    messages.success(request, f'{component.replace("_", " ").title()} created successfully.')
                    return redirect('users:role_based_redirect')
                    
            except Exception as e:
                messages.error(request, f'Error creating {component}: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form_kwargs = {}
        if component == 'strength_weakness':
            form_kwargs['user_role'] = request.user.role
            form_kwargs['ilp'] = ilp
        elif component in ['learning_goal', 'custom_targets']:
            form_kwargs['user'] = target_user
            form_kwargs['user_role'] = request.user.role
            
        form = form_class(**form_kwargs)
    
    context = {
        'form': form,
        'ilp': ilp,
        'target_user': target_user,
        'component': component,
        'user_role': request.user.role,
        'component_permissions': component_perms,
        'breadcrumbs': breadcrumbs,
        'is_create': True,
    }
    
    return render(request, template, context)


@login_required
def edit_ilp_component(request, user_id, component, component_id=None):
    """Enhanced edit view with role-based permissions"""
    target_user = get_object_or_404(User, id=user_id)
    
    # Check permissions
    component_perms = get_component_permissions(request.user, target_user, component)
    if not component_perms['can_edit']:
        raise PermissionDenied(f"You don't have permission to edit {component.replace('_', ' ')}.")
    
    ilp = get_object_or_404(IndividualLearningPlan, user=target_user)
    
    # Define breadcrumbs
    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'label': f'Edit {component.replace("_", " ").title()}', 'icon': 'fa-edit'}
    ]
    
    # Get the specific instance to edit
    if component == 'accommodation':
        instance = get_object_or_404(SENDAccommodation, id=component_id, ilp=ilp)
        form_class = SENDAccommodationForm
        template = 'individual_learning_plan/forms/accommodation_form.html'
        
    elif component == 'strength_weakness':
        instance = get_object_or_404(StrengthWeakness, id=component_id, ilp=ilp)
        form_class = StrengthWeaknessForm
        template = 'individual_learning_plan/forms/strength_weakness_form.html'
        
    elif component == 'learning_preference':
        instance = get_object_or_404(LearningPreference, id=component_id, ilp=ilp)
        form_class = LearningPreferenceForm
        template = 'individual_learning_plan/forms/learning_preference_form.html'
        
    elif component == 'statement_of_purpose':
        instance = get_object_or_404(StatementOfPurpose, ilp=ilp)
        form_class = StatementOfPurposeForm
        template = 'individual_learning_plan/forms/statement_of_purpose_form.html'
        
    elif component == 'career_goal':
        instance = get_object_or_404(CareerGoal, ilp=ilp)
        form_class = CareerGoalForm
        template = 'individual_learning_plan/forms/career_goal_form.html'
        
    elif component == 'learning_goal':
        instance = get_object_or_404(LearningGoal, id=component_id, ilp=ilp)
        form_class = LearningGoalForm
        template = 'individual_learning_plan/forms/learning_goal_form.html'
        
    elif component == 'educator_note' and component_perms['can_edit']:
        instance = get_object_or_404(EducatorNote, id=component_id, ilp=ilp)
        form_class = EducatorNoteForm
        template = 'individual_learning_plan/forms/educator_note_form.html'
        
    else:
        raise Http404("Invalid component or insufficient permissions")
    
    if request.method == 'POST':
        # Pass user role to form for role-based field restrictions
        form_kwargs = {}
        if component == 'strength_weakness':
            form_kwargs['user_role'] = request.user.role
        elif component in ['learning_goal', 'custom_targets']:
            form_kwargs['user'] = target_user
            form_kwargs['user_role'] = request.user.role
            
        form = form_class(request.POST, request.FILES, instance=instance, **form_kwargs)
        
        if form.is_valid():
            try:
                with transaction.atomic():
                    instance = form.save(commit=False)
                    
                    # Update modification fields
                    if hasattr(instance, 'updated_by'):
                        instance.updated_by = request.user
                    
                    instance.save()
                    
                    messages.success(request, f'{component.replace("_", " ").title()} updated successfully.')
                    return redirect('users:role_based_redirect')
                    
            except Exception as e:
                messages.error(request, f'Error updating {component}: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form_kwargs = {}
        if component == 'strength_weakness':
            form_kwargs['user_role'] = request.user.role
        elif component in ['learning_goal', 'custom_targets']:
            form_kwargs['user'] = target_user
            form_kwargs['user_role'] = request.user.role
            
        form = form_class(instance=instance, **form_kwargs)
    
    context = {
        'form': form,
        'ilp': ilp,
        'target_user': target_user,
        'component': component,
        'instance': instance,
        'user_role': request.user.role,
        'component_permissions': component_perms,
        'breadcrumbs': breadcrumbs,
        'is_create': False,
    }
    
    return render(request, template, context)


@login_required
def delete_ilp_component(request, user_id, component, component_id):
    """Delete an ILP component"""
    target_user = get_object_or_404(User, id=user_id)
    
    # Check permissions
    perm_check = check_ilp_permissions(request.user, target_user, 'edit')
    if not perm_check['allowed']:
        raise PermissionDenied("You don't have permission to delete this ILP component.")
    
    ilp = get_object_or_404(IndividualLearningPlan, user=target_user)
    
    # Get the specific instance to delete
    if component == 'accommodation':
        instance = get_object_or_404(SENDAccommodation, id=component_id, ilp=ilp)
    elif component == 'strength_weakness':
        instance = get_object_or_404(StrengthWeakness, id=component_id, ilp=ilp)
    elif component == 'learning_preference':
        instance = get_object_or_404(LearningPreference, id=component_id, ilp=ilp)
    elif component == 'learning_goal':
        instance = get_object_or_404(LearningGoal, id=component_id, ilp=ilp)
    elif component == 'educator_note':
        instance = get_object_or_404(EducatorNote, id=component_id, ilp=ilp)
    else:
        raise Http404("Invalid component")
    
    if request.method == 'POST':
        try:
            component_name = component.replace('_', ' ').title()
            instance.delete()
            messages.success(request, f'{component_name} deleted successfully.')
        except Exception as e:
            messages.error(request, f'Error deleting {component}: {str(e)}')
    
    return redirect('users:role_based_redirect')


@login_required
def add_learning_progress(request, user_id, goal_id):
    """Add progress update to a learning goal"""
    target_user = get_object_or_404(User, id=user_id)
    
    # Check permissions
    perm_check = check_ilp_permissions(request.user, target_user, 'edit')
    if not perm_check['allowed']:
        raise PermissionDenied("You don't have permission to add progress to this ILP.")
    
    ilp = get_object_or_404(IndividualLearningPlan, user=target_user)
    learning_goal = get_object_or_404(LearningGoal, id=goal_id, ilp=ilp)
    
    if request.method == 'POST':
        if request.user.role == 'learner':
            form = LearningProgressForm(request.POST, request.FILES)
        else:
            form = LearningProgressTeacherForm(request.POST, request.FILES)
        
        if form.is_valid():
            try:
                with transaction.atomic():
                    progress = form.save(commit=False)
                    progress.learning_goal = learning_goal
                    progress.created_by = request.user
                    progress.save()
                    
                    messages.success(request, 'Progress update added successfully.')
                    return redirect('users:role_based_redirect')
                    
            except Exception as e:
                messages.error(request, f'Error adding progress: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        if request.user.role == 'learner':
            form = LearningProgressForm()
        else:
            form = LearningProgressTeacherForm()
    
    context = {
        'form': form,
        'ilp': ilp,
        'target_user': target_user,
        'learning_goal': learning_goal,
        'user_role': request.user.role,
        'permissions': perm_check['permissions'],
    }
    
    return render(request, 'individual_learning_plan/forms/progress_form.html', context)


@login_required
@require_http_methods(["GET"])
def ilp_api_data(request, user_id):
    """API endpoint to get ILP data for AJAX requests"""
    target_user = get_object_or_404(User, id=user_id)
    
    # Check permissions
    perm_check = check_ilp_permissions(request.user, target_user, 'view')
    if not perm_check['allowed']:
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    try:
        ilp = IndividualLearningPlan.objects.get(user=target_user)
        
        data = {
            'accommodations': [
                {
                    'id': acc.id,
                    'type': acc.get_accommodation_type_display(),
                    'description': acc.description,
                    'is_active': acc.is_active,
                }
                for acc in ilp.send_accommodations.filter(is_active=True)
            ],
            'learning_goals': [
                {
                    'id': goal.id,
                    'title': goal.title,
                    'type': goal.get_goal_type_display(),
                    'status': goal.get_status_display(),
                    'progress': goal.progress_entries.last().progress_percentage if goal.progress_entries.exists() else 0,
                }
                for goal in ilp.learning_goals.all()
            ],
        }
        
        return JsonResponse(data)
        
    except IndividualLearningPlan.DoesNotExist:
        return JsonResponse({'error': 'ILP not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def manage_induction_checklist(request, user_id):
    """Manage induction checklist for a user"""
    target_user = get_object_or_404(User, id=user_id)
    
    # Check permissions
    perm_check = check_ilp_permissions(request.user, target_user, 'edit')
    if not perm_check['allowed']:
        raise PermissionDenied("You don't have permission to manage this ILP.")
    
    # Get or create ILP
    ilp, created = IndividualLearningPlan.objects.get_or_create(
        user=target_user,
        defaults={'created_by': request.user}
    )
    
    # Get or create induction checklist
    induction_checklist, checklist_created = InductionChecklist.objects.get_or_create(
        ilp=ilp,
        defaults={'created_by': request.user}
    )
    
    if request.method == 'POST':
        # Handle different forms based on user role
        if request.user.role == 'learner':
            form = InductionLearnerResponseForm(request.POST, instance=induction_checklist)
        else:
            form = InductionChecklistForm(request.POST, instance=induction_checklist)
        
        document_formset = InductionDocumentFormSet(
            request.POST, 
            request.FILES, 
            instance=induction_checklist
        )
        
        if form.is_valid() and (request.user.role == 'learner' or document_formset.is_valid()):
            try:
                with transaction.atomic():
                    checklist = form.save(commit=False)
                    
                    # Set completion date if learner marks as complete
                    if (request.user.role == 'learner' and 
                        form.cleaned_data.get('completed_by_learner') and 
                        not checklist.learner_completion_date):
                        checklist.learner_completion_date = timezone.now()
                    
                    checklist.save()
                    
                    # Handle document uploads for admin/instructor
                    if request.user.role != 'learner' and document_formset.is_valid():
                        documents = document_formset.save(commit=False)
                        for document in documents:
                            document.uploaded_by = request.user
                            document.save()
                        
                        # Handle deletions
                        for obj in document_formset.deleted_objects:
                            obj.delete()
                    
                    messages.success(request, 'Induction checklist updated successfully.')
                    return redirect('users:role_based_redirect')
                    
            except Exception as e:
                messages.error(request, f'Error updating induction checklist: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        # Initialize forms
        if request.user.role == 'learner':
            form = InductionLearnerResponseForm(instance=induction_checklist)
            document_formset = None
        else:
            form = InductionChecklistForm(instance=induction_checklist)
            document_formset = InductionDocumentFormSet(instance=induction_checklist)
    
    context = {
        'form': form,
        'document_formset': document_formset,
        'induction_checklist': induction_checklist,
        'ilp': ilp,
        'target_user': target_user,
        'user_role': request.user.role,
        'is_create': checklist_created,
        'breadcrumbs': [
            {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
            {'label': 'Induction Checklist', 'icon': 'fa-clipboard-check'}
        ]
    }
    
    return render(request, 'individual_learning_plan/forms/induction_checklist_form.html', context)


@login_required
@require_http_methods(["POST"])
def mark_document_read(request, user_id, document_id):
    """Mark an induction document as read by the learner"""
    target_user = get_object_or_404(User, id=user_id)
    document = get_object_or_404(InductionDocument, id=document_id)
    
    # Only the learner themselves can mark documents as read
    if request.user != target_user:
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    # Check if document belongs to this user's induction checklist
    if document.induction_checklist.ilp.user != target_user:
        return JsonResponse({'error': 'Document not found'}, status=404)
    
    try:
        receipt, created = InductionDocumentReadReceipt.objects.get_or_create(
            document=document,
            learner=target_user
        )
        
        return JsonResponse({
            'success': True,
            'read_at': receipt.read_at.isoformat() if receipt.read_at else None,
            'created': created
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def download_induction_document(request, user_id, document_id):
    """Download an induction document"""
    target_user = get_object_or_404(User, id=user_id)
    document = get_object_or_404(InductionDocument, id=document_id)
    
    # Check permissions
    perm_check = check_ilp_permissions(request.user, target_user, 'view')
    if not perm_check['allowed']:
        raise PermissionDenied("You don't have permission to access this document.")
    
    # Check if document belongs to this user's induction checklist
    if document.induction_checklist.ilp.user != target_user:
        raise Http404("Document not found")
    
    try:
        # Mark as read if it's the learner accessing their own document
        if request.user == target_user and request.user.role == 'learner':
            InductionDocumentReadReceipt.objects.get_or_create(
                document=document,
                learner=target_user
            )
        
        response = HttpResponse(document.document_file.read(), content_type='application/octet-stream')
        response['Content-Disposition'] = f'attachment; filename="{document.document_file.name}"'
        return response
        
    except Exception as e:
        messages.error(request, f'Error downloading document: {str(e)}')
        return redirect('users:role_based_redirect')


@login_required
def manage_health_safety_questionnaire(request, user_id):
    """Manage Health & Safety questionnaire for a user"""
    target_user = get_object_or_404(User, id=user_id)
    
    # Check permissions
    perm_check = check_ilp_permissions(request.user, target_user, 'edit')
    if not perm_check['allowed']:
        raise PermissionDenied("You don't have permission to manage this ILP.")
    
    # Get or create ILP
    ilp, created = IndividualLearningPlan.objects.get_or_create(
        user=target_user,
        defaults={'created_by': request.user}
    )
    
    # Get or create health & safety questionnaire
    health_safety_questionnaire, questionnaire_created = HealthSafetyQuestionnaire.objects.get_or_create(
        ilp=ilp,
        defaults={'created_by': request.user}
    )
    
    if request.method == 'POST':
        # Handle different forms based on user role
        if request.user.role == 'learner':
            form = HealthSafetyLearnerResponseForm(request.POST, instance=health_safety_questionnaire)
        else:
            form = HealthSafetyQuestionnaireForm(request.POST, instance=health_safety_questionnaire)
        
        document_formset = HealthSafetyDocumentFormSet(
            request.POST, 
            request.FILES, 
            instance=health_safety_questionnaire
        )
        
        if form.is_valid() and (request.user.role == 'learner' or document_formset.is_valid()):
            try:
                with transaction.atomic():
                    questionnaire = form.save(commit=False)
                    
                    # Set completion date if learner acknowledges understanding
                    if (request.user.role == 'learner' and 
                        form.cleaned_data.get('learner_acknowledgment') and 
                        not questionnaire.acknowledgment_date):
                        questionnaire.acknowledgment_date = timezone.now()
                        
                    # Set questionnaire as completed if all fields are filled
                    if questionnaire.completion_percentage == 100:
                        questionnaire.questionnaire_completed = True
                        if not questionnaire.completed_at:
                            questionnaire.completed_at = timezone.now()
                    
                    questionnaire.save()
                    
                    # Handle document uploads for admin/instructor
                    if request.user.role != 'learner' and document_formset.is_valid():
                        documents = document_formset.save(commit=False)
                        for document in documents:
                            document.uploaded_by = request.user
                            document.save()
                        
                        # Handle deletions
                        for obj in document_formset.deleted_objects:
                            obj.delete()
                    
                    messages.success(request, 'Health & Safety questionnaire updated successfully.')
                    return redirect('users:role_based_redirect')
                    
            except Exception as e:
                messages.error(request, f'Error updating Health & Safety questionnaire: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        # Initialize forms
        if request.user.role == 'learner':
            form = HealthSafetyLearnerResponseForm(instance=health_safety_questionnaire)
            document_formset = None
        else:
            form = HealthSafetyQuestionnaireForm(instance=health_safety_questionnaire)
            document_formset = HealthSafetyDocumentFormSet(instance=health_safety_questionnaire)
    
    # Get read receipts for the current user if they're a learner
    read_documents = []
    if request.user.role == 'learner':
        read_receipts = HealthSafetyDocumentReadReceipt.objects.filter(
            learner=request.user,
            document__health_safety_questionnaire=health_safety_questionnaire
        ).values_list('document_id', flat=True)
        read_documents = list(read_receipts)
    
    context = {
        'form': form,
        'document_formset': document_formset,
        'health_safety_questionnaire': health_safety_questionnaire,
        'ilp': ilp,
        'target_user': target_user,
        'user_role': request.user.role,
        'is_create': questionnaire_created,
        'read_documents': read_documents,
        'breadcrumbs': [
            {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
            {'label': 'Health & Safety Questionnaire', 'icon': 'fa-hard-hat'}
        ]
    }
    
    return render(request, 'individual_learning_plan/forms/health_safety_questionnaire_form.html', context)


@login_required
@require_http_methods(["POST"])
def mark_health_safety_document_read(request, document_id):
    """Mark a health & safety document as read by the current user"""
    try:
        document = get_object_or_404(HealthSafetyDocument, id=document_id)
        
        # Create read receipt
        read_receipt, created = HealthSafetyDocumentReadReceipt.objects.get_or_create(
            document=document,
            learner=request.user
        )
        
        return JsonResponse({
            'success': True,
            'message': 'Document marked as read successfully.'
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Error marking document as read: {str(e)}'
        })


@login_required
def download_health_safety_document(request, user_id, document_id):
    """Download a Health & Safety document"""
    target_user = get_object_or_404(User, id=user_id)
    document = get_object_or_404(HealthSafetyDocument, id=document_id)
    
    # Check permissions
    perm_check = check_ilp_permissions(request.user, target_user, 'view')
    if not perm_check['allowed']:
        raise PermissionDenied("You don't have permission to access this document.")
    
    # Check if document belongs to this user's health & safety questionnaire
    if document.health_safety_questionnaire.ilp.user != target_user:
        raise Http404("Document not found")
    
    try:
        # Mark as read if it's the learner accessing their own document
        if request.user == target_user and request.user.role == 'learner':
            HealthSafetyDocumentReadReceipt.objects.get_or_create(
                document=document,
                learner=target_user
            )
        
        response = HttpResponse(document.document_file.read(), content_type='application/octet-stream')
        response['Content-Disposition'] = f'attachment; filename="{document.document_file.name}"'
        return response
        
    except Exception as e:
        messages.error(request, f'Error downloading document: {str(e)}')
        return redirect('users:role_based_redirect')
