from django.contrib import admin
from .models import (
    IndividualLearningPlan, SENDAccommodation, StrengthWeakness,
    LearningPreference, StatementOfPurpose, CareerGoal,
    LearningGoal, LearningProgress, EducatorNote,
    InductionChecklist, InductionDocument, InductionDocumentReadReceipt,
    InductionChecklistSection, InductionChecklistQuestion, InductionChecklistDocument,
    HealthSafetyQuestionnaire, HealthSafetyDocument, HealthSafetyDocumentReadReceipt,
    HealthSafetySection, HealthSafetyQuestion, HealthSafetySectionDocument,
    LearningNeeds, LearningNeedsSection, LearningNeedsQuestion, LearningNeedsSectionDocument,
    StrengthsWeaknessesSection, StrengthsWeaknessesQuestion, StrengthsWeaknessesSectionDocument,
    StrengthWeaknessFeedback, SimpleStrengthsWeaknesses, InternalCourseReview
)


class SENDAccommodationInline(admin.TabularInline):
    model = SENDAccommodation
    extra = 0
    fields = ('accommodation_type', 'description', 'is_active')


class StrengthWeaknessInline(admin.TabularInline):
    model = StrengthWeakness
    extra = 0
    fields = ('type', 'description', 'source', 'confidence_score')


class LearningPreferenceInline(admin.TabularInline):
    model = LearningPreference
    extra = 0
    fields = ('preference_type', 'preference_level', 'notes')


class LearningGoalInline(admin.TabularInline):
    model = LearningGoal
    extra = 0
    fields = ('goal_type', 'title', 'status', 'target_completion_date')


class EducatorNoteInline(admin.TabularInline):
    model = EducatorNote
    extra = 0
    fields = ('note', 'is_private')


@admin.register(IndividualLearningPlan)
class IndividualLearningPlanAdmin(admin.ModelAdmin):
    list_display = ('user', 'created_at', 'updated_at', 'created_by')
    list_filter = ('created_at', 'updated_at')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'user__email')
    readonly_fields = ('created_at', 'updated_at')
    
    inlines = [
        SENDAccommodationInline,
        StrengthWeaknessInline,
        LearningPreferenceInline,
        LearningGoalInline,
        EducatorNoteInline,
    ]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('user', 'created_by')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(SENDAccommodation)
class SENDAccommodationAdmin(admin.ModelAdmin):
    list_display = ('ilp', 'accommodation_type', 'is_active', 'created_at')
    list_filter = ('accommodation_type', 'is_active', 'created_at')
    search_fields = ('ilp__user__username', 'description')


@admin.register(StrengthWeakness)
class StrengthWeaknessAdmin(admin.ModelAdmin):
    list_display = ('ilp', 'type', 'source', 'confidence_score', 'created_at')
    list_filter = ('type', 'source', 'created_at')
    search_fields = ('ilp__user__username', 'description')


@admin.register(LearningPreference)
class LearningPreferenceAdmin(admin.ModelAdmin):
    list_display = ('ilp', 'preference_type', 'preference_level', 'identified_by')
    list_filter = ('preference_type', 'preference_level', 'created_at')
    search_fields = ('ilp__user__username',)


@admin.register(StatementOfPurpose)
class StatementOfPurposeAdmin(admin.ModelAdmin):
    list_display = ('ilp', 'has_content', 'created_at', 'updated_at')
    list_filter = ('created_at', 'updated_at')
    search_fields = ('ilp__user__username',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(CareerGoal)
class CareerGoalAdmin(admin.ModelAdmin):
    list_display = ('ilp', 'target_industry', 'created_at', 'updated_at')
    list_filter = ('target_industry', 'created_at', 'updated_at')
    search_fields = ('ilp__user__username', 'short_term_goal', 'long_term_goal')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(LearningGoal)
class LearningGoalAdmin(admin.ModelAdmin):
    list_display = ('ilp', 'course', 'goal_type', 'title', 'status', 'target_completion_date')
    list_filter = ('goal_type', 'status', 'course', 'created_at')
    search_fields = ('ilp__user__username', 'title', 'description')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(LearningProgress)
class LearningProgressAdmin(admin.ModelAdmin):
    list_display = ('learning_goal', 'progress_percentage', 'review_requested', 'review_completed', 'created_at')
    list_filter = ('review_requested', 'review_completed', 'created_at')
    search_fields = ('learning_goal__title', 'learning_goal__ilp__user__username')
    readonly_fields = ('created_at',)


@admin.register(EducatorNote)
class EducatorNoteAdmin(admin.ModelAdmin):
    list_display = ('ilp', 'is_private', 'created_by', 'created_at')
    list_filter = ('is_private', 'created_at')
    search_fields = ('ilp__user__username', 'note')
    readonly_fields = ('created_at',)


class InductionDocumentInline(admin.TabularInline):
    model = InductionDocument
    extra = 0
    fields = ('title', 'category', 'document_file', 'is_mandatory', 'uploaded_by')
    readonly_fields = ('uploaded_by',)


@admin.register(InductionChecklist)
class InductionChecklistAdmin(admin.ModelAdmin):
    list_display = ('ilp', 'completion_percentage', 'all_items_completed', 'completed_by_learner', 'created_at')
    list_filter = ('completed_by_learner', 'created_at', 'learner_completion_date')
    search_fields = ('ilp__user__username', 'ilp__user__first_name', 'ilp__user__last_name')
    readonly_fields = ('created_at', 'updated_at', 'completion_percentage', 'all_items_completed')
    
    inlines = [InductionDocumentInline]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('ilp', 'created_by')
        }),
        ('Checklist Items', {
            'fields': (
                'programme_content_delivery_assessment',
                'equality_diversity',
                'disciplinary_grievance_procedures',
                'esf_cofinancing',
                'information_advice_guidance',
                'health_safety_safe_learner',
                'safeguarding_prevent_duty',
                'terms_conditions_learning',
            )
        }),
        ('Completion Status', {
            'fields': ('completed_by_learner', 'learner_completion_date', 'assessor_notes')
        }),
        ('Progress', {
            'fields': ('completion_percentage', 'all_items_completed'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(InductionDocument)
class InductionDocumentAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'induction_checklist', 'is_mandatory', 'uploaded_by', 'created_at')
    list_filter = ('category', 'is_mandatory', 'created_at')
    search_fields = ('title', 'induction_checklist__ilp__user__username', 'description')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Document Information', {
            'fields': ('title', 'category', 'document_file', 'description', 'is_mandatory')
        }),
        ('Assignment', {
            'fields': ('induction_checklist', 'uploaded_by')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(InductionDocumentReadReceipt)
class InductionDocumentReadReceiptAdmin(admin.ModelAdmin):
    list_display = ('document', 'learner', 'read_at')
    list_filter = ('read_at', 'document__category')
    search_fields = ('document__title', 'learner__username', 'learner__first_name', 'learner__last_name')
    readonly_fields = ('read_at',)
    
    def has_add_permission(self, request):
        return False  # Read receipts are automatically created
    
    def has_change_permission(self, request, obj=None):
        return False  # Read receipts shouldn't be manually changed


class HealthSafetyDocumentInline(admin.TabularInline):
    model = HealthSafetyDocument
    extra = 0
    fields = ('title', 'document_file', 'is_mandatory', 'uploaded_by')
    readonly_fields = ('uploaded_by',)


@admin.register(HealthSafetyQuestionnaire)
class HealthSafetyQuestionnaireAdmin(admin.ModelAdmin):
    list_display = ('ilp', 'completion_percentage', 'is_fully_completed', 'learner_acknowledgment', 'created_at')
    list_filter = ('learner_acknowledgment', 'questionnaire_completed', 'created_at', 'acknowledgment_date')
    search_fields = ('ilp__user__username', 'ilp__user__first_name', 'ilp__user__last_name')
    readonly_fields = ('created_at', 'updated_at', 'completion_percentage', 'is_fully_completed')
    
    inlines = [HealthSafetyDocumentInline]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('ilp', 'created_by')
        }),
        ('Health & Safety Questions', {
            'fields': (
                'named_first_aider',
                'fire_extinguishers_location',
                'first_aid_box_location',
                'fire_assembly_point',
                'accident_book_location',
                'accident_reporting_person',
                'health_safety_policy_location',
                'health_safety_issue_reporting',
                'nearest_fire_exits',
                'health_safety_manager',
                'common_accidents',
                'prohibited_substances',
            )
        }),
        ('Completion Status', {
            'fields': ('questionnaire_completed', 'completed_at', 'learner_acknowledgment', 'acknowledgment_date', 'assessor_notes')
        }),
        ('Progress', {
            'fields': ('completion_percentage', 'is_fully_completed'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(HealthSafetyDocument)
class HealthSafetyDocumentAdmin(admin.ModelAdmin):
    list_display = ('title', 'health_safety_questionnaire', 'is_mandatory', 'uploaded_by', 'created_at')
    list_filter = ('is_mandatory', 'created_at')
    search_fields = ('title', 'health_safety_questionnaire__ilp__user__username', 'description')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Document Information', {
            'fields': ('title', 'document_file', 'description', 'is_mandatory')
        }),
        ('Assignment', {
            'fields': ('health_safety_questionnaire', 'uploaded_by')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(HealthSafetyDocumentReadReceipt)
class HealthSafetyDocumentReadReceiptAdmin(admin.ModelAdmin):
    list_display = ('learner', 'document', 'read_at')
    list_filter = ('read_at',)
    search_fields = ('learner__username', 'learner__email', 'document__title')
    readonly_fields = ('read_at',)


@admin.register(LearningNeeds)
class LearningNeedsAdmin(admin.ModelAdmin):
    list_display = ('ilp', 'selected_skills_count', 'created_at', 'updated_at')
    list_filter = ('created_at', 'updated_at')
    search_fields = ('ilp__user__username', 'ilp__user__email')
    readonly_fields = ('created_at', 'updated_at', 'selected_skills_count')
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('ilp',)
        }),
        ('Employability Skills', {
            'fields': (
                'job_search_skills', 'effective_cvs', 'improving_it_skills',
                'interview_skills', 'team_skills', 'jcp_universal_jobmatch',
                'job_application_skills', 'communication_skills', 
                'other_skills', 'other_skills_details'
            )
        }),
        ('Additional Assessment', {
            'fields': (
                'prior_learning_experience', 'learning_challenges', 
                'support_needed', 'preferred_learning_environment'
            )
        }),
        ('Metadata', {
            'fields': ('created_by', 'updated_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )


@admin.register(InternalCourseReview)
class InternalCourseReviewAdmin(admin.ModelAdmin):
    list_display = ('ilp', 'review_status', 'qualification_achieved', 'completion_percentage', 'review_completion_date', 'created_at')
    list_filter = ('review_status', 'qualification_achieved', 'review_completion_date', 'created_at')
    search_fields = ('ilp__user__username', 'ilp__user__email', 'review_completed_by')
    readonly_fields = ('created_at', 'updated_at', 'completion_percentage', 'is_complete')
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('ilp', 'review_status', 'review_completed_by', 'review_completion_date')
        }),
        ('Course Review Questions', {
            'fields': (
                'iag_session_review', 'action_completion_skills', 'careers_service_advice',
                'progression_routes', 'career_objectives'
            )
        }),
        ('Qualification Assessment', {
            'fields': ('qualification_achieved', 'qualification_details')
        }),
        ('Progress Tracking', {
            'fields': ('completion_percentage', 'is_complete'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_by', 'updated_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

# ========================================================================================
# Dynamic Sections and Questions Admin (following Induction Checklist pattern)
# ========================================================================================

# Induction Checklist Dynamic Sections
@admin.register(InductionChecklistSection)
class InductionChecklistSectionAdmin(admin.ModelAdmin):
    list_display = ('title', 'induction_checklist', 'order', 'created_at')
    list_filter = ('created_at', 'order')
    search_fields = ('title', 'description', 'induction_checklist__ilp__user__username')
    readonly_fields = ('created_at', 'updated_at')

@admin.register(InductionChecklistQuestion)
class InductionChecklistQuestionAdmin(admin.ModelAdmin):
    list_display = ('question_text_short', 'section', 'order', 'is_mandatory', 'student_confirmed', 'instructor_confirmed')
    list_filter = ('is_mandatory', 'student_confirmed', 'instructor_confirmed', 'created_at')
    search_fields = ('question_text', 'answer_text', 'section__title')
    readonly_fields = ('created_at', 'updated_at')
    
    def question_text_short(self, obj):
        return obj.question_text[:50] + '...' if len(obj.question_text) > 50 else obj.question_text
    question_text_short.short_description = 'Question'

@admin.register(InductionChecklistDocument)
class InductionChecklistDocumentAdmin(admin.ModelAdmin):
    list_display = ('title', 'section', 'is_mandatory', 'uploaded_by', 'created_at')
    list_filter = ('is_mandatory', 'created_at')
    search_fields = ('title', 'description', 'section__title')
    readonly_fields = ('created_at', 'updated_at')

# Health & Safety Dynamic Sections
@admin.register(HealthSafetySection)
class HealthSafetySectionAdmin(admin.ModelAdmin):
    list_display = ('title', 'health_safety_questionnaire', 'order', 'created_at')
    list_filter = ('created_at', 'order')
    search_fields = ('title', 'description', 'health_safety_questionnaire__ilp__user__username')
    readonly_fields = ('created_at', 'updated_at')

@admin.register(HealthSafetyQuestion)
class HealthSafetyQuestionAdmin(admin.ModelAdmin):
    list_display = ('question_text_short', 'section', 'order', 'is_mandatory', 'student_confirmed', 'instructor_confirmed')
    list_filter = ('is_mandatory', 'student_confirmed', 'instructor_confirmed', 'created_at')
    search_fields = ('question_text', 'answer_text', 'section__title')
    readonly_fields = ('created_at', 'updated_at')
    
    def question_text_short(self, obj):
        return obj.question_text[:50] + '...' if len(obj.question_text) > 50 else obj.question_text
    question_text_short.short_description = 'Question'

@admin.register(HealthSafetySectionDocument)
class HealthSafetySectionDocumentAdmin(admin.ModelAdmin):
    list_display = ('title', 'section', 'is_mandatory', 'uploaded_by', 'created_at')
    list_filter = ('is_mandatory', 'created_at')
    search_fields = ('title', 'description', 'section__title')
    readonly_fields = ('created_at', 'updated_at')

# Learning Needs Dynamic Sections
@admin.register(LearningNeedsSection)
class LearningNeedsSectionAdmin(admin.ModelAdmin):
    list_display = ('title', 'learning_needs', 'order', 'created_at')
    list_filter = ('created_at', 'order')
    search_fields = ('title', 'description', 'learning_needs__ilp__user__username')
    readonly_fields = ('created_at', 'updated_at')

@admin.register(LearningNeedsQuestion)
class LearningNeedsQuestionAdmin(admin.ModelAdmin):
    list_display = ('question_text_short', 'section', 'order', 'is_mandatory', 'student_confirmed', 'instructor_confirmed')
    list_filter = ('is_mandatory', 'student_confirmed', 'instructor_confirmed', 'created_at')
    search_fields = ('question_text', 'answer_text', 'section__title')
    readonly_fields = ('created_at', 'updated_at')
    
    def question_text_short(self, obj):
        return obj.question_text[:50] + '...' if len(obj.question_text) > 50 else obj.question_text
    question_text_short.short_description = 'Question'

@admin.register(LearningNeedsSectionDocument)
class LearningNeedsSectionDocumentAdmin(admin.ModelAdmin):
    list_display = ('title', 'section', 'is_mandatory', 'uploaded_by', 'created_at')
    list_filter = ('is_mandatory', 'created_at')
    search_fields = ('title', 'description', 'section__title')
    readonly_fields = ('created_at', 'updated_at')

# Strengths & Weaknesses Dynamic Sections
@admin.register(StrengthsWeaknessesSection)
class StrengthsWeaknessesSectionAdmin(admin.ModelAdmin):
    list_display = ('title', 'ilp', 'order', 'created_at')
    list_filter = ('created_at', 'order')
    search_fields = ('title', 'description', 'ilp__user__username')
    readonly_fields = ('created_at', 'updated_at')

@admin.register(StrengthsWeaknessesQuestion)
class StrengthsWeaknessesQuestionAdmin(admin.ModelAdmin):
    list_display = ('description_short', 'section', 'item_type', 'order', 'student_confirmed', 'instructor_confirmed')
    list_filter = ('item_type', 'student_confirmed', 'instructor_confirmed', 'created_at')
    search_fields = ('description', 'section__title')
    readonly_fields = ('created_at', 'updated_at')
    
    def description_short(self, obj):
        return obj.description[:50] + '...' if len(obj.description) > 50 else obj.description
    description_short.short_description = 'Description'

@admin.register(StrengthsWeaknessesSectionDocument)
class StrengthsWeaknessesSectionDocumentAdmin(admin.ModelAdmin):
    list_display = ('title', 'section', 'is_mandatory', 'uploaded_by', 'created_at')
    list_filter = ('is_mandatory', 'created_at')
    search_fields = ('title', 'description', 'section__title')
    readonly_fields = ('created_at', 'updated_at')

@admin.register(StrengthWeaknessFeedback)
class StrengthWeaknessFeedbackAdmin(admin.ModelAdmin):
    list_display = ('question', 'feedback_type', 'approval_status', 'created_by', 'created_at')
    list_filter = ('feedback_type', 'approval_status', 'created_at')
    search_fields = ('content', 'question__description', 'created_by__username')
    readonly_fields = ('created_at', 'updated_at')
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('question', 'created_by')


@admin.register(SimpleStrengthsWeaknesses)
class SimpleStrengthsWeaknessesAdmin(admin.ModelAdmin):
    list_display = ('ilp', 'completion_percentage', 'has_pending_approvals', 'created_at')
    list_filter = ('strengths_approval', 'development_approval', 'created_at')
    readonly_fields = ('created_at', 'updated_at', 'completion_percentage', 'has_pending_approvals')
    search_fields = ('ilp__user__username', 'ilp__user__email')
    
    fieldsets = (
        ('Strengths Assessment', {
            'fields': ('strengths_content', 'strengths_created_by', 'strengths_updated_at', 
                      'strengths_approval', 'strengths_learner_comment', 'strengths_instructor_reply')
        }),
        ('Development Areas Assessment', {
            'fields': ('development_content', 'development_created_by', 'development_updated_at',
                      'development_approval', 'development_learner_comment', 'development_instructor_reply')
        }),
        ('Metadata', {
            'fields': ('ilp', 'created_at', 'updated_at', 'completion_percentage', 'has_pending_approvals')
        }),
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('ilp__user', 'strengths_created_by', 'development_created_by')
