from django.contrib import admin
from django.db import models
from .models import Assignment, AssignmentSubmission, AssignmentFeedback, TextQuestion, TextQuestionAnswer, TextQuestionAnswerIteration, TextQuestionIterationFeedback, TextSubmissionAnswerIteration, TextSubmissionIterationFeedback, AssignmentCourse, TextSubmissionField, TextSubmissionAnswer, GradeHistory, SupportingDocQuestion, StudentAnswer, AssignmentAttachment, TopicAssignment, AssignmentComment, AssignmentInteractionLog, AssignmentSessionLog, AssignmentReportConfirmation, AdminApprovalHistory

class AssignmentSubmissionInline(admin.TabularInline):
    model = AssignmentSubmission
    extra = 0
    readonly_fields = ['submitted_at', 'user', 'graded_by', 'graded_at']
    fields = ['user', 'status', 'grade', 'submitted_at', 'graded_by', 'graded_at']

class TextQuestionInline(admin.TabularInline):
    model = TextQuestion
    extra = 1
    fields = ['question_text', 'order']

class TextQuestionAnswerInline(admin.TabularInline):
    model = TextQuestionAnswer
    extra = 0
    readonly_fields = ['created_at']
    fields = ['question', 'answer_text', 'created_at']

@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ['title', 'course', 'due_date', 'is_active', 'created_at']
    list_filter = ['is_active', 'due_date', 'created_at', 'course__branch']
    search_fields = ['title', 'description']
    inlines = [TextQuestionInline, AssignmentSubmissionInline]
    fieldsets = (
        (None, {
            'fields': ('title', 'description', 'instructions', 'course')
        }),
        ('Settings', {
            'fields': ('due_date', 'max_score', 'submission_type', 'allowed_file_types', 'max_file_size', 'rubric', 'is_active')
        }),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser or request.user.role in ['globaladmin', 'superadmin']:
            return qs
        # Branch admins can only see assignments from their effective branch (supports branch switching)
        if request.user.role == 'admin':
            from core.branch_filters import BranchFilterManager
            effective_branch = BranchFilterManager.get_effective_branch(request.user, request)
            if effective_branch:
                return qs.filter(course__branch=effective_branch)
        # Instructors can see assignments they created or from courses they teach
        elif request.user.role == 'instructor' and request.user.branch:
            return qs.filter(
                models.Q(user=request.user) |
                models.Q(course__instructor=request.user) |
                models.Q(course__branch=request.user.branch)
            )
        return qs.none()

@admin.register(AssignmentSubmission)
class AssignmentSubmissionAdmin(admin.ModelAdmin):
    list_display = ['assignment', 'user', 'status', 'grade', 'submitted_at']
    list_filter = ['status', 'submitted_at', 'graded_at', 'assignment__course__branch']
    search_fields = ['user__username', 'user__email', 'assignment__title']
    readonly_fields = ['assignment', 'user', 'submitted_at', 'last_modified']
    inlines = [TextQuestionAnswerInline]
    fieldsets = (
        (None, {
            'fields': ('assignment', 'user', 'status')
        }),
        ('Submission', {
            'fields': ('submission_file', 'submission_text', 'submitted_at', 'last_modified')
        }),
        ('Grading', {
            'fields': ('grade', 'graded_by', 'graded_at')
        }),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser or request.user.role in ['globaladmin', 'superadmin']:
            return qs
        # Branch admins can only see submissions from their effective branch (supports branch switching)
        if request.user.role == 'admin':
            from core.branch_filters import BranchFilterManager
            effective_branch = BranchFilterManager.get_effective_branch(request.user, request)
            if effective_branch:
                return qs.filter(assignment__course__branch=effective_branch)
        # Instructors can see submissions for courses they teach
        elif request.user.role == 'instructor' and request.user.branch:
            return qs.filter(
                models.Q(assignment__user=request.user) |
                models.Q(assignment__course__instructor=request.user) |
                models.Q(assignment__course__branch=request.user.branch)
            )
        return qs.none()

@admin.register(AssignmentFeedback)
class AssignmentFeedbackAdmin(admin.ModelAdmin):
    list_display = ['submission', 'created_by', 'created_at', 'is_private', 'has_multimedia']
    list_filter = ['is_private', 'created_at', 'submission__assignment__course__branch']
    search_fields = ['feedback', 'created_by__username', 'submission__user__username']
    readonly_fields = ['created_at']
    fieldsets = (
        ('Basic Information', {
            'fields': ('submission', 'created_by', 'is_private')
        }),
        ('Text Feedback', {
            'fields': ('feedback',)
        }),
        ('Multimedia Feedback', {
            'fields': ('audio_feedback', 'video_feedback'),
            'description': 'Upload audio or video feedback files'
        }),
        ('Metadata', {
            'fields': ('created_at',)
        }),
    )
    
    def has_multimedia(self, obj):
        """Show whether feedback has audio or video"""
        multimedia_types = []
        if obj.audio_feedback:
            multimedia_types.append('Audio')
        if obj.video_feedback:
            multimedia_types.append('Video')
        return ', '.join(multimedia_types) if multimedia_types else 'Text only'
    has_multimedia.short_description = 'Multimedia'

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser or request.user.role in ['globaladmin', 'superadmin']:
            return qs
        # Branch admins can only see feedback from their effective branch (supports branch switching)
        if request.user.role == 'admin':
            from core.branch_filters import BranchFilterManager
            effective_branch = BranchFilterManager.get_effective_branch(request.user, request)
            if effective_branch:
                return qs.filter(submission__assignment__course__branch=effective_branch)
        # Instructors can see feedback they created or for courses they teach
        elif request.user.role == 'instructor' and request.user.branch:
            return qs.filter(
                models.Q(created_by=request.user) |
                models.Q(submission__assignment__course__instructor=request.user) |
                models.Q(submission__assignment__course__branch=request.user.branch)
            )
        return qs.none()

@admin.register(TextQuestion)
class TextQuestionAdmin(admin.ModelAdmin):
    list_display = ['assignment', 'question_text', 'order', 'created_at']
    list_filter = ['created_at', 'assignment__course__branch']
    search_fields = ['question_text', 'assignment__title']
    ordering = ['assignment', 'order']

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser or request.user.role in ['globaladmin', 'superadmin']:
            return qs
        # Filter based on assignment branch access (supports branch switching)
        if request.user.role == 'admin':
            from core.branch_filters import BranchFilterManager
            effective_branch = BranchFilterManager.get_effective_branch(request.user, request)
            if effective_branch:
                return qs.filter(assignment__course__branch=effective_branch)
        elif request.user.role == 'instructor' and request.user.branch:
            return qs.filter(
                models.Q(assignment__user=request.user) |
                models.Q(assignment__course__instructor=request.user) |
                models.Q(assignment__course__branch=request.user.branch)
            )
        return qs.none()

@admin.register(TextQuestionAnswer)
class TextQuestionAnswerAdmin(admin.ModelAdmin):
    list_display = ['question', 'submission', 'created_at']
    list_filter = ['created_at', 'submission__assignment__course__branch']
    search_fields = ['answer_text', 'question__question_text', 'submission__user__username']
    readonly_fields = ['created_at', 'updated_at']

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser or request.user.role in ['globaladmin', 'superadmin']:
            return qs
        # Filter based on assignment branch access
        if request.user.role == 'admin':
            from core.branch_filters import BranchFilterManager
            effective_branch = BranchFilterManager.get_effective_branch(request.user, request)
            if effective_branch:
                return qs.filter(submission__assignment__course__branch=effective_branch)
        elif request.user.role == 'instructor' and request.user.branch:
            return qs.filter(
                models.Q(submission__assignment__user=request.user) |
                models.Q(submission__assignment__course__instructor=request.user) |
                models.Q(submission__assignment__course__branch=request.user.branch)
            )
        return qs.none()

@admin.register(TextQuestionAnswerIteration)
class TextQuestionAnswerIterationAdmin(admin.ModelAdmin):
    list_display = ['question', 'submission', 'iteration_number', 'is_submitted', 'submitted_at']
    list_filter = ['is_submitted', 'iteration_number', 'created_at', 'submission__assignment__course__branch']
    search_fields = ['answer_text', 'question__question_text', 'submission__user__username']
    readonly_fields = ['created_at', 'updated_at']
    fieldsets = (
        ('Basic Information', {
            'fields': ('question', 'submission', 'iteration_number')
        }),
        ('Answer', {
            'fields': ('answer_text', 'is_submitted', 'submitted_at')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at')
        }),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser or request.user.role in ['globaladmin', 'superadmin']:
            return qs
        # Filter based on assignment branch access
        if request.user.role == 'admin':
            from core.branch_filters import BranchFilterManager
            effective_branch = BranchFilterManager.get_effective_branch(request.user, request)
            if effective_branch:
                return qs.filter(submission__assignment__course__branch=effective_branch)
        elif request.user.role == 'instructor' and request.user.branch:
            return qs.filter(
                models.Q(submission__assignment__user=request.user) |
                models.Q(submission__assignment__course__instructor=request.user) |
                models.Q(submission__assignment__course__branch=request.user.branch)
            )
        return qs.none()


@admin.register(TextQuestionIterationFeedback)
class TextQuestionIterationFeedbackAdmin(admin.ModelAdmin):
    list_display = ['iteration', 'created_by', 'allows_new_iteration', 'created_at', 'feedback_preview']
    list_filter = ['allows_new_iteration', 'created_at', 'iteration__submission__assignment__course__branch']
    search_fields = ['feedback_text', 'created_by__username', 'iteration__submission__user__username']
    readonly_fields = ['created_at']
    fieldsets = (
        ('Basic Information', {
            'fields': ('iteration', 'created_by', 'allows_new_iteration')
        }),
        ('Feedback', {
            'fields': ('feedback_text',)
        }),
        ('Metadata', {
            'fields': ('created_at',)
        }),
    )
    
    def feedback_preview(self, obj):
        """Show a preview of the feedback text"""
        return obj.feedback_text[:100] + "..." if len(obj.feedback_text) > 100 else obj.feedback_text
    feedback_preview.short_description = 'Feedback Preview'

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser or request.user.role in ['globaladmin', 'superadmin']:
            return qs
        # Filter based on assignment branch access
        if request.user.role == 'admin':
            from core.branch_filters import BranchFilterManager
            effective_branch = BranchFilterManager.get_effective_branch(request.user, request)
            if effective_branch:
                return qs.filter(iteration__submission__assignment__course__branch=effective_branch)
        elif request.user.role == 'instructor' and request.user.branch:
            return qs.filter(
                models.Q(created_by=request.user) |
                models.Q(iteration__submission__assignment__course__instructor=request.user) |
                models.Q(iteration__submission__assignment__course__branch=request.user.branch)
            )
        return qs.none()


@admin.register(TextSubmissionAnswerIteration)
class TextSubmissionAnswerIterationAdmin(admin.ModelAdmin):
    list_display = ['field', 'submission', 'iteration_number', 'is_submitted', 'submitted_at']
    list_filter = ['is_submitted', 'iteration_number', 'created_at', 'submission__assignment__course__branch']
    search_fields = ['answer_text', 'field__label', 'submission__user__username']
    readonly_fields = ['created_at', 'updated_at']
    fieldsets = (
        ('Basic Information', {
            'fields': ('field', 'submission', 'iteration_number')
        }),
        ('Answer', {
            'fields': ('answer_text', 'is_submitted', 'submitted_at')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at')
        }),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser or request.user.role in ['globaladmin', 'superadmin']:
            return qs
        # Filter based on assignment branch access
        if request.user.role == 'admin':
            from core.branch_filters import BranchFilterManager
            effective_branch = BranchFilterManager.get_effective_branch(request.user, request)
            if effective_branch:
                return qs.filter(submission__assignment__course__branch=effective_branch)
        elif request.user.role == 'instructor' and request.user.branch:
            return qs.filter(
                models.Q(submission__assignment__user=request.user) |
                models.Q(submission__assignment__course__instructor=request.user) |
                models.Q(submission__assignment__course__branch=request.user.branch)
            )
        return qs.none()


@admin.register(TextSubmissionIterationFeedback)
class TextSubmissionIterationFeedbackAdmin(admin.ModelAdmin):
    list_display = ['iteration', 'created_by', 'allows_new_iteration', 'created_at', 'feedback_preview']
    list_filter = ['allows_new_iteration', 'created_at', 'iteration__submission__assignment__course__branch']
    search_fields = ['feedback_text', 'created_by__username', 'iteration__submission__user__username']
    readonly_fields = ['created_at']
    fieldsets = (
        ('Basic Information', {
            'fields': ('iteration', 'created_by', 'allows_new_iteration')
        }),
        ('Feedback', {
            'fields': ('feedback_text',)
        }),
        ('Metadata', {
            'fields': ('created_at',)
        }),
    )
    
    def feedback_preview(self, obj):
        """Show a preview of the feedback text"""
        return obj.feedback_text[:100] + "..." if len(obj.feedback_text) > 100 else obj.feedback_text
    feedback_preview.short_description = 'Feedback Preview'

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser or request.user.role in ['globaladmin', 'superadmin']:
            return qs
        # Filter based on assignment branch access
        if request.user.role == 'admin':
            from core.branch_filters import BranchFilterManager
            effective_branch = BranchFilterManager.get_effective_branch(request.user, request)
            if effective_branch:
                return qs.filter(iteration__submission__assignment__course__branch=effective_branch)
        elif request.user.role == 'instructor' and request.user.branch:
            return qs.filter(
                models.Q(created_by=request.user) |
                models.Q(iteration__submission__assignment__course__instructor=request.user) |
                models.Q(iteration__submission__assignment__course__branch=request.user.branch)
            )
        return qs.none()

@admin.register(AssignmentInteractionLog)
class AssignmentInteractionLogAdmin(admin.ModelAdmin):
    """Admin interface for Assignment Interaction Logs"""
    list_display = [
        'assignment', 'user', 'interaction_type', 'created_at', 
        'ip_address', 'duration_seconds'
    ]
    list_filter = [
        'interaction_type', 'created_at', 'assignment__title'
    ]
    search_fields = [
        'user__username', 'user__email', 'user__first_name', 'user__last_name',
        'assignment__title', 'ip_address'
    ]
    readonly_fields = [
        'assignment', 'user', 'interaction_type', 'submission',
        'interaction_data', 'ip_address', 'user_agent', 'session_key',
        'duration_seconds', 'created_at'
    ]
    date_hierarchy = 'created_at'
    ordering = ['-created_at']
    
    def has_add_permission(self, request):
        # Don't allow manual creation of interaction logs
        return False
    
    def has_change_permission(self, request, obj=None):
        # Don't allow editing of interaction logs
        return False
    
    def has_delete_permission(self, request, obj=None):
        # Only superusers can delete interaction logs
        return request.user.is_superuser

@admin.register(AssignmentSessionLog)
class AssignmentSessionLogAdmin(admin.ModelAdmin):
    """Admin interface for Assignment Session Logs"""
    list_display = [
        'assignment', 'user', 'start_time', 'end_time', 
        'total_duration_seconds', 'page_views', 'interactions_count',
        'is_active'
    ]
    list_filter = [
        'is_active', 'start_time', 'assignment__title'
    ]
    search_fields = [
        'user__username', 'user__email', 'user__first_name', 'user__last_name',
        'assignment__title', 'ip_address', 'session_key'
    ]
    readonly_fields = [
        'assignment', 'user', 'session_key', 'start_time', 'last_activity',
        'end_time', 'total_duration_seconds', 'page_views', 'interactions_count',
        'ip_address', 'user_agent'
    ]
    date_hierarchy = 'start_time'
    ordering = ['-start_time']
    
    def has_add_permission(self, request):
        # Don't allow manual creation of session logs
        return False
    
    def has_change_permission(self, request, obj=None):
        # Only allow changing is_active status for superusers
        return request.user.is_superuser
    
    def has_delete_permission(self, request, obj=None):
        # Only superusers can delete session logs
        return request.user.is_superuser


@admin.register(AdminApprovalHistory)
class AdminApprovalHistoryAdmin(admin.ModelAdmin):
    """Admin interface for Admin Approval History"""
    list_display = [
        'submission', 'approval_status', 'approved_by', 'approval_date', 
        'is_current', 'trigger_reason'
    ]
    list_filter = [
        'approval_status', 'is_current', 'approval_date', 'trigger_reason'
    ]
    search_fields = [
        'submission__user__username', 'submission__user__email', 
        'submission__assignment__title', 'approved_by__username',
        'admin_feedback'
    ]
    readonly_fields = [
        'submission', 'approval_date', 'approved_by'
    ]
    fieldsets = (
        ('Basic Information', {
            'fields': ('submission', 'approval_status', 'approved_by', 'approval_date')
        }),
        ('Details', {
            'fields': ('admin_feedback', 'trigger_reason', 'is_current'),
            'description': 'Internal verifier feedback and additional details'
        }),
    )
    date_hierarchy = 'approval_date'
    ordering = ['-approval_date']
    
    def has_add_permission(self, request):
        # Don't allow manual creation of approval history
        return False
    
    def has_change_permission(self, request, obj=None):
        # Only allow editing of feedback and current status
        return request.user.role in ['admin', 'superadmin'] or request.user.is_superuser
    
    def has_delete_permission(self, request, obj=None):
        # Only superusers can delete approval history
        return request.user.is_superuser
