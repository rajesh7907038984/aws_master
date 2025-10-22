from django import forms
from django.forms import inlineformset_factory
from .models import (
    IndividualLearningPlan, SENDAccommodation, StrengthWeakness,
    LearningPreference, StatementOfPurpose, CareerGoal,
    LearningGoal, LearningProgress, EducatorNote,
    InductionChecklist, InductionDocument,
    HealthSafetyQuestionnaire, HealthSafetyDocument, LearningNeeds,
    InternalCourseReview, InductionChecklistSection, InductionChecklistQuestion,
    InductionChecklistDocument
)
from courses.models import Course


class SENDAccommodationForm(forms.ModelForm):
    accommodation_type_other = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Please specify'}),
        help_text="If 'Other' is selected above, please specify"
    )
    
    class Meta:
        model = SENDAccommodation
        fields = ['accommodation_type', 'accommodation_type_other', 'description', 'is_active']
        widgets = {
            'accommodation_type': forms.Select(attrs={'class': 'form-select'}),
            'accommodation_type_other': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Please specify'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
    
    def clean(self):
        cleaned_data = super().clean()
        accommodation_type = cleaned_data.get('accommodation_type')
        accommodation_type_other = cleaned_data.get('accommodation_type_other')
        
        # Check if "Other" is selected but no custom value is provided
        if accommodation_type == 'other' and not accommodation_type_other:
            self.add_error('accommodation_type_other', "This field is required when 'Other' is selected.")
            
        return cleaned_data


class StrengthWeaknessForm(forms.ModelForm):
    class Meta:
        model = StrengthWeakness
        fields = ['type', 'description', 'source']
        widgets = {
            'type': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'source': forms.Select(attrs={'class': 'form-select'}),
        }
        
    def __init__(self, *args, **kwargs):
        user_role = kwargs.pop('user_role', None)
        self.ilp = kwargs.pop('ilp', None)
        super().__init__(*args, **kwargs)
        
        # Restrict source options based on user role
        if user_role == 'learner':
            self.fields['source'].choices = [('self_assessment', 'Self Assessment')]
        elif user_role in ['instructor', 'admin', 'superadmin']:
            self.fields['source'].choices = [
                ('teacher_input', 'Teacher Input'),
                ('ai_analysis', 'AI Analysis'),
            ]
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.ilp and not instance.ilp_id:
            instance.ilp = self.ilp
        if commit:
            instance.save()
        return instance


class LearningPreferenceForm(forms.ModelForm):
    class Meta:
        model = LearningPreference
        fields = ['preference_type', 'preference_level', 'notes']
        widgets = {
            'preference_type': forms.Select(attrs={'class': 'form-select'}),
            'preference_level': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }


class StatementOfPurposeForm(forms.ModelForm):
    class Meta:
        model = StatementOfPurpose
        fields = [
            'sop_file', 'reason_for_course', 'career_objectives',
            'relevant_experience', 'additional_info'
        ]
        widgets = {
            'sop_file': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': '.pdf,.doc,.docx'
            }),
            'reason_for_course': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Why are you pursuing this course?'
            }),
            'career_objectives': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'What are your career objectives?'
            }),
            'relevant_experience': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Describe any relevant past work or experience'
            }),
            'additional_info': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Any additional information you\'d like to share'
            }),
        }
        
    def clean(self):
        cleaned_data = super().clean()
        sop_file = cleaned_data.get('sop_file')
        reason_for_course = cleaned_data.get('reason_for_course')
        career_objectives = cleaned_data.get('career_objectives')
        
        # Ensure at least some content is provided
        if not any([sop_file, reason_for_course, career_objectives]):
            raise forms.ValidationError(
                "Please provide either a Statement of Purpose file or fill in the form questions."
            )
        
        return cleaned_data


class CareerGoalForm(forms.ModelForm):
    class Meta:
        model = CareerGoal
        fields = ['short_term_goal', 'long_term_goal', 'target_industry', 'required_skills']
        widgets = {
            'short_term_goal': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Describe your short-term career goal (1-2 years)'
            }),
            'long_term_goal': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Describe your long-term career goal (5+ years)'
            }),
            'target_industry': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Healthcare, Technology, Education'
            }),
            'required_skills': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'List skills needed to achieve these goals'
            }),
        }


class LearningGoalForm(forms.ModelForm):
    class Meta:
        model = LearningGoal
        fields = [
            'course', 'goal_type', 'title', 'description',
            'target_completion_date', 'status'
        ]
        widgets = {
            'course': forms.Select(attrs={'class': 'form-select'}),
            'goal_type': forms.Select(attrs={'class': 'form-select'}),
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter goal title'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Describe the learning goal in detail'
            }),
            'target_completion_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }
        
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        user_role = kwargs.pop('user_role', None)
        super().__init__(*args, **kwargs)
        
        # Filter courses based on user access
        if user and hasattr(user, 'enrolled_courses'):
            self.fields['course'].queryset = user.enrolled_courses
        
        # Restrict goal types for learners (only custom targets)
        if user_role == 'learner':
            self.fields['goal_type'].choices = [('custom', 'Custom Target')]


class LearningGoalTeacherInputForm(forms.ModelForm):
    """Form for teachers to add input to learning goals"""
    class Meta:
        model = LearningGoal
        fields = ['teacher_input', 'ai_input']
        widgets = {
            'teacher_input': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Add your input or guidance for this learning goal'
            }),
            'ai_input': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'AI-generated suggestions (auto-filled)'
            }),
        }


class LearningProgressForm(forms.ModelForm):
    class Meta:
        model = LearningProgress
        fields = [
            'progress_percentage', 'learner_comment', 'evidence_file',
            'review_requested'
        ]
        widgets = {
            'progress_percentage': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 0,
                'max': 100,
                'step': 1
            }),
            'learner_comment': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Add your comment about the progress'
            }),
            'evidence_file': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': '.pdf,.doc,.docx,.jpg,.jpeg,.png'
            }),
            'review_requested': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }


class LearningProgressTeacherForm(forms.ModelForm):
    """Form for teachers to respond to progress updates"""
    class Meta:
        model = LearningProgress
        fields = ['teacher_comment', 'review_completed']
        widgets = {
            'teacher_comment': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Add your feedback on the learner\'s progress'
            }),
            'review_completed': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }


class EducatorNoteForm(forms.ModelForm):
    class Meta:
        model = EducatorNote
        fields = ['note', 'is_private']
        widgets = {
            'note': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Add a note about this learner\'s ILP'
            }),
            'is_private': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }


class LearningNeedsForm(forms.ModelForm):
    class Meta:
        model = LearningNeeds
        fields = [
            'job_search_skills', 'effective_cvs', 'improving_it_skills',
            'interview_skills', 'team_skills', 'jcp_universal_jobmatch',
            'job_application_skills', 'communication_skills', 'other_skills',
            'other_skills_details', 'prior_learning_experience', 'learning_challenges',
            'support_needed', 'preferred_learning_environment'
        ]
        widgets = {
            'job_search_skills': forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
            'effective_cvs': forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
            'improving_it_skills': forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
            'interview_skills': forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
            'team_skills': forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
            'jcp_universal_jobmatch': forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
            'job_application_skills': forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
            'communication_skills': forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
            'other_skills': forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
            'other_skills_details': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Please state other skills below'
            }),
            'prior_learning_experience': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Describe relevant prior learning or experience'
            }),
            'learning_challenges': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Describe any learning challenges or difficulties'
            }),
            'support_needed': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'What kind of support would help your learning?'
            }),
            'preferred_learning_environment': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Describe your preferred learning environment'
            }),
        }


class InductionChecklistForm(forms.ModelForm):
    """Form for managing induction checklist questionnaire"""
    
    class Meta:
        model = InductionChecklist
        fields = [
            'programme_content_delivery_assessment',
            'equality_diversity', 
            'disciplinary_grievance_procedures',
            'esf_cofinancing',
            'information_advice_guidance',
            'health_safety_safe_learner',
            'safeguarding_prevent_duty',
            'terms_conditions_learning',
            'assessor_notes'
        ]
        
        widgets = {
            'programme_content_delivery_assessment': forms.RadioSelect(
                choices=[('yes', 'Yes'), ('no', 'No')],
                attrs={'class': 'form-radio-input'}
            ),
            'equality_diversity': forms.RadioSelect(
                choices=[('yes', 'Yes'), ('no', 'No')],
                attrs={'class': 'form-radio-input'}
            ),
            'disciplinary_grievance_procedures': forms.RadioSelect(
                choices=[('yes', 'Yes'), ('no', 'No')],
                attrs={'class': 'form-radio-input'}
            ),
            'esf_cofinancing': forms.RadioSelect(
                choices=[('yes', 'Yes'), ('no', 'No')],
                attrs={'class': 'form-radio-input'}
            ),
            'information_advice_guidance': forms.RadioSelect(
                choices=[('yes', 'Yes'), ('no', 'No')],
                attrs={'class': 'form-radio-input'}
            ),
            'health_safety_safe_learner': forms.RadioSelect(
                choices=[('yes', 'Yes'), ('no', 'No')],
                attrs={'class': 'form-radio-input'}
            ),
            'safeguarding_prevent_duty': forms.RadioSelect(
                choices=[('yes', 'Yes'), ('no', 'No')],
                attrs={'class': 'form-radio-input'}
            ),
            'terms_conditions_learning': forms.RadioSelect(
                choices=[('yes', 'Yes'), ('no', 'No')],
                attrs={'class': 'form-radio-input'}
            ),
            'assessor_notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Additional notes about the induction process'
            }),
        }


class InductionDocumentForm(forms.ModelForm):
    """Form for uploading induction documents"""
    
    class Meta:
        model = InductionDocument
        fields = [
            'title',
            'category',
            'document_file',
            'description',
            'is_mandatory'
        ]
        
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter document title'
            }),
            'category': forms.Select(attrs={
                'class': 'form-select'
            }),
            'document_file': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': '.pdf,.doc,.docx,.txt'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Optional description of the document'
            }),
            'is_mandatory': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }


class InductionLearnerResponseForm(forms.ModelForm):
    """Simplified form for learners to respond to induction checklist"""
    
    class Meta:
        model = InductionChecklist
        fields = [
            'programme_content_delivery_assessment',
            'equality_diversity', 
            'disciplinary_grievance_procedures',
            'esf_cofinancing',
            'information_advice_guidance',
            'health_safety_safe_learner',
            'safeguarding_prevent_duty',
            'terms_conditions_learning',
            'completed_by_learner'
        ]
        
        widgets = {
            'programme_content_delivery_assessment': forms.RadioSelect(
                choices=[('yes', 'Yes'), ('no', 'No')],
                attrs={'class': 'form-radio-input induction-response'}
            ),
            'equality_diversity': forms.RadioSelect(
                choices=[('yes', 'Yes'), ('no', 'No')],
                attrs={'class': 'form-radio-input induction-response'}
            ),
            'disciplinary_grievance_procedures': forms.RadioSelect(
                choices=[('yes', 'Yes'), ('no', 'No')],
                attrs={'class': 'form-radio-input induction-response'}
            ),
            'esf_cofinancing': forms.RadioSelect(
                choices=[('yes', 'Yes'), ('no', 'No')],
                attrs={'class': 'form-radio-input induction-response'}
            ),
            'information_advice_guidance': forms.RadioSelect(
                choices=[('yes', 'Yes'), ('no', 'No')],
                attrs={'class': 'form-radio-input induction-response'}
            ),
            'health_safety_safe_learner': forms.RadioSelect(
                choices=[('yes', 'Yes'), ('no', 'No')],
                attrs={'class': 'form-radio-input induction-response'}
            ),
            'safeguarding_prevent_duty': forms.RadioSelect(
                choices=[('yes', 'Yes'), ('no', 'No')],
                attrs={'class': 'form-radio-input induction-response'}
            ),
            'terms_conditions_learning': forms.RadioSelect(
                choices=[('yes', 'Yes'), ('no', 'No')],
                attrs={'class': 'form-radio-input induction-response'}
            ),
            'completed_by_learner': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }


# Formsets for handling multiple related objects
SENDAccommodationFormSet = inlineformset_factory(
    IndividualLearningPlan,
    SENDAccommodation,
    form=SENDAccommodationForm,
    extra=1,
    can_delete=True
)

StrengthWeaknessFormSet = inlineformset_factory(
    IndividualLearningPlan,
    StrengthWeakness,
    form=StrengthWeaknessForm,
    extra=1,
    can_delete=True
)

LearningPreferenceFormSet = inlineformset_factory(
    IndividualLearningPlan,
    LearningPreference,
    form=LearningPreferenceForm,
    extra=1,
    can_delete=True
)

LearningGoalFormSet = inlineformset_factory(
    IndividualLearningPlan,
    LearningGoal,
    form=LearningGoalForm,
    extra=1,
    can_delete=True
)

EducatorNoteFormSet = inlineformset_factory(
    IndividualLearningPlan,
    EducatorNote,
    form=EducatorNoteForm,
    extra=1,
    can_delete=True
)

# Formsets for handling multiple documents
InductionDocumentFormSet = inlineformset_factory(
    InductionChecklist,
    InductionDocument,
    form=InductionDocumentForm,
    extra=1,
    can_delete=True
)


class HealthSafetyQuestionnaireForm(forms.ModelForm):
    """Form for managing Health & Safety questionnaire"""
    
    class Meta:
        model = HealthSafetyQuestionnaire
        fields = [
            'named_first_aider', 'named_first_aider_confirmed',
            'fire_extinguishers_location', 'fire_extinguishers_confirmed',
            'first_aid_box_location', 'first_aid_box_confirmed',
            'fire_assembly_point', 'fire_assembly_confirmed',
            'accident_book_location', 'accident_book_confirmed',
            'accident_reporting_person', 'accident_reporting_confirmed',
            'health_safety_policy_location', 'health_safety_policy_confirmed',
            'health_safety_issue_reporting', 'health_safety_issue_confirmed',
            'nearest_fire_exits', 'nearest_fire_exits_confirmed',
            'health_safety_manager', 'health_safety_manager_confirmed',
            'common_accidents', 'common_accidents_confirmed',
            'prohibited_substances', 'prohibited_substances_confirmed',
            'learner_acknowledgment',
            'assessor_notes'
        ]
        
        widgets = {
            'named_first_aider': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Name of the first aider'
            }),
            'named_first_aider_confirmed': forms.Select(attrs={
                'class': 'form-select'
            }),
            'fire_extinguishers_location': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Location of fire extinguishers'
            }),
            'fire_extinguishers_confirmed': forms.Select(attrs={
                'class': 'form-select'
            }),
            'first_aid_box_location': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Location of first aid box'
            }),
            'first_aid_box_confirmed': forms.Select(attrs={
                'class': 'form-select'
            }),
            'fire_assembly_point': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Fire assembly point location'
            }),
            'fire_assembly_confirmed': forms.Select(attrs={
                'class': 'form-select'
            }),
            'accident_book_location': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Location of accident book'
            }),
            'accident_book_confirmed': forms.Select(attrs={
                'class': 'form-select'
            }),
            'accident_reporting_person': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Person to report accidents to'
            }),
            'accident_reporting_confirmed': forms.Select(attrs={
                'class': 'form-select'
            }),
            'health_safety_policy_location': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Where health & safety policy is displayed'
            }),
            'health_safety_policy_confirmed': forms.Select(attrs={
                'class': 'form-select'
            }),
            'health_safety_issue_reporting': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Person to report health & safety issues to'
            }),
            'health_safety_issue_confirmed': forms.Select(attrs={
                'class': 'form-select'
            }),
            'nearest_fire_exits': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Location of nearest fire exits'
            }),
            'nearest_fire_exits_confirmed': forms.Select(attrs={
                'class': 'form-select'
            }),
            'health_safety_manager': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Person responsible for health & safety'
            }),
            'health_safety_manager_confirmed': forms.Select(attrs={
                'class': 'form-select'
            }),
            'common_accidents': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Most common accidents in this environment'
            }),
            'common_accidents_confirmed': forms.Select(attrs={
                'class': 'form-select'
            }),
            'prohibited_substances': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Substances prohibited at this centre'
            }),
            'prohibited_substances_confirmed': forms.Select(attrs={
                'class': 'form-select'
            }),
            'learner_acknowledgment': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'assessor_notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Additional notes from assessor'
            }),
        }


class HealthSafetyLearnerResponseForm(forms.ModelForm):
    """Simplified form for learners to respond to Health & Safety questionnaire"""
    
    class Meta:
        model = HealthSafetyQuestionnaire
        fields = [
            'named_first_aider', 'named_first_aider_confirmed',
            'fire_extinguishers_location', 'fire_extinguishers_confirmed',
            'first_aid_box_location', 'first_aid_box_confirmed',
            'fire_assembly_point', 'fire_assembly_confirmed',
            'accident_book_location', 'accident_book_confirmed',
            'accident_reporting_person', 'accident_reporting_confirmed',
            'health_safety_policy_location', 'health_safety_policy_confirmed',
            'health_safety_issue_reporting', 'health_safety_issue_confirmed',
            'nearest_fire_exits', 'nearest_fire_exits_confirmed',
            'health_safety_manager', 'health_safety_manager_confirmed',
            'common_accidents', 'common_accidents_confirmed',
            'prohibited_substances', 'prohibited_substances_confirmed',
            'learner_acknowledgment'
        ]
        
        widgets = {
            'named_first_aider': forms.TextInput(attrs={
                'class': 'form-control health-safety-input',
                'placeholder': 'Enter name...'
            }),
            'named_first_aider_confirmed': forms.Select(attrs={
                'class': 'form-select health-safety-confirmation'
            }),
            'fire_extinguishers_location': forms.TextInput(attrs={
                'class': 'form-control health-safety-input',
                'placeholder': 'Enter location...'
            }),
            'fire_extinguishers_confirmed': forms.Select(attrs={
                'class': 'form-select health-safety-confirmation'
            }),
            'first_aid_box_location': forms.TextInput(attrs={
                'class': 'form-control health-safety-input',
                'placeholder': 'Enter location...'
            }),
            'first_aid_box_confirmed': forms.Select(attrs={
                'class': 'form-select health-safety-confirmation'
            }),
            'fire_assembly_point': forms.TextInput(attrs={
                'class': 'form-control health-safety-input',
                'placeholder': 'Enter location...'
            }),
            'fire_assembly_confirmed': forms.Select(attrs={
                'class': 'form-select health-safety-confirmation'
            }),
            'accident_book_location': forms.TextInput(attrs={
                'class': 'form-control health-safety-input',
                'placeholder': 'Enter location...'
            }),
            'accident_book_confirmed': forms.Select(attrs={
                'class': 'form-select health-safety-confirmation'
            }),
            'accident_reporting_person': forms.TextInput(attrs={
                'class': 'form-control health-safety-input',
                'placeholder': 'Enter name/contact...'
            }),
            'accident_reporting_confirmed': forms.Select(attrs={
                'class': 'form-select health-safety-confirmation'
            }),
            'health_safety_policy_location': forms.TextInput(attrs={
                'class': 'form-control health-safety-input',
                'placeholder': 'Enter location...'
            }),
            'health_safety_policy_confirmed': forms.Select(attrs={
                'class': 'form-select health-safety-confirmation'
            }),
            'health_safety_issue_reporting': forms.TextInput(attrs={
                'class': 'form-control health-safety-input',
                'placeholder': 'Enter name/contact...'
            }),
            'health_safety_issue_confirmed': forms.Select(attrs={
                'class': 'form-select health-safety-confirmation'
            }),
            'nearest_fire_exits': forms.TextInput(attrs={
                'class': 'form-control health-safety-input',
                'placeholder': 'Enter location...'
            }),
            'nearest_fire_exits_confirmed': forms.Select(attrs={
                'class': 'form-select health-safety-confirmation'
            }),
            'health_safety_manager': forms.TextInput(attrs={
                'class': 'form-control health-safety-input',
                'placeholder': 'Enter name/contact...'
            }),
            'health_safety_manager_confirmed': forms.Select(attrs={
                'class': 'form-select health-safety-confirmation'
            }),
            'common_accidents': forms.Textarea(attrs={
                'class': 'form-control health-safety-input',
                'rows': 3,
                'placeholder': 'Describe common accidents...'
            }),
            'common_accidents_confirmed': forms.Select(attrs={
                'class': 'form-select health-safety-confirmation'
            }),
            'prohibited_substances': forms.Textarea(attrs={
                'class': 'form-control health-safety-input',
                'rows': 3,
                'placeholder': 'List prohibited substances...'
            }),
            'prohibited_substances_confirmed': forms.Select(attrs={
                'class': 'form-select health-safety-confirmation'
            }),
            'learner_acknowledgment': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }


class HealthSafetyDocumentForm(forms.ModelForm):
    """Form for uploading Health & Safety documents"""
    
    class Meta:
        model = HealthSafetyDocument
        fields = [
            'title',
            'document_file',
            'description',
            'is_mandatory'
        ]
        
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter document title'
            }),
            'document_file': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': '.pdf,.doc,.docx,.txt'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Optional description of the document'
            }),
            'is_mandatory': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }


# Formsets for Health & Safety documents
HealthSafetyDocumentFormSet = inlineformset_factory(
    HealthSafetyQuestionnaire,
    HealthSafetyDocument,
    form=HealthSafetyDocumentForm,
    extra=1,
    can_delete=True
)


# Enhanced Induction Checklist Forms

class InductionChecklistSectionForm(forms.ModelForm):
    """Form for creating/editing induction checklist sections"""
    
    class Meta:
        model = InductionChecklistSection
        fields = ['title', 'description', 'order', 'is_active']
        
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter section title (e.g., Health & Safety, Programme Information)'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Optional description of this section'
            }),
            'order': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }


class InductionChecklistQuestionForm(forms.ModelForm):
    """Form for creating/editing individual questions within sections"""
    
    class Meta:
        model = InductionChecklistQuestion
        fields = [
            'question_text', 'answer_text', 'student_confirmed', 
            'instructor_confirmed', 'order', 'is_mandatory'
        ]
        
        widgets = {
            'question_text': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Enter the question text'
            }),
            'answer_text': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Enter the answer or response'
            }),
            'student_confirmed': forms.Select(
                choices=[('', 'Not Set'), ('yes', 'Yes'), ('no', 'No')],
                attrs={'class': 'form-select'}
            ),
            'instructor_confirmed': forms.Select(
                choices=[('', 'Not Set'), ('yes', 'Yes'), ('no', 'No')],
                attrs={'class': 'form-select'}
            ),
            'order': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1
            }),
            'is_mandatory': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }


class InductionChecklistDocumentForm(forms.ModelForm):
    """Form for uploading documents to induction checklist sections"""
    
    class Meta:
        model = InductionChecklistDocument
        fields = ['title', 'document_file', 'description', 'is_mandatory']
        
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter document title'
            }),
            'document_file': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': '.pdf,.doc,.docx,.txt,.jpg,.jpeg,.png'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Optional description of the document'
            }),
            'is_mandatory': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }


# Enhanced Formsets for the new induction checklist system
InductionSectionFormSet = inlineformset_factory(
    InductionChecklist,
    InductionChecklistSection,
    form=InductionChecklistSectionForm,
    extra=1,
    can_delete=True
)

InductionQuestionFormSet = inlineformset_factory(
    InductionChecklistSection,
    InductionChecklistQuestion,
    form=InductionChecklistQuestionForm,
    extra=1,
    can_delete=True
)

InductionDocumentFormSet = inlineformset_factory(
    InductionChecklistSection,
    InductionChecklistDocument,
    form=InductionChecklistDocumentForm,
    extra=1,
    can_delete=True
) 