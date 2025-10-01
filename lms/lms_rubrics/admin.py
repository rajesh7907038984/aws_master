from django.contrib import admin
from lms_rubrics.models import Rubric, RubricCriterion, RubricRating, RubricEvaluation, RubricEvaluationHistory, RubricOverallFeedback
from django.db import models


class RubricRatingInline(admin.TabularInline):
    model = RubricRating
    extra = 2


class RubricCriterionInline(admin.TabularInline):
    model = RubricCriterion
    extra = 3
    ordering = ['position']


@admin.register(Rubric)
class RubricAdmin(admin.ModelAdmin):
    list_display = ('title', 'total_points', 'course', 'branch', 'created_by', 'created_at')
    search_fields = ('title', 'description')
    list_filter = ('course', 'branch', 'created_at')
    inlines = [RubricCriterionInline]
    readonly_fields = ['total_points', 'created_at', 'updated_at']

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser or request.user.role in ['globaladmin', 'superadmin']:
            return qs
        # Branch admins can only see rubrics from their branch
        if request.user.role == 'admin' and request.user.branch:
            return qs.filter(branch=request.user.branch)
        # Instructors can see rubrics they created or from their branch
        elif request.user.role == 'instructor' and request.user.branch:
            return qs.filter(
                models.Q(created_by=request.user) |
                models.Q(branch=request.user.branch)
            )
        return qs.none()

    def save_model(self, request, obj, form, change):
        # Automatically set branch and created_by for non-superusers
        if not (request.user.is_superuser or request.user.role in ['globaladmin', 'superadmin']):
            if not obj.created_by:
                obj.created_by = request.user
            if not obj.branch and request.user.branch:
                obj.branch = request.user.branch
        super().save_model(request, obj, form, change)


@admin.register(RubricCriterion)
class RubricCriterionAdmin(admin.ModelAdmin):
    list_display = ('description', 'rubric', 'points', 'position')
    search_fields = ('description', 'rubric__title')
    list_filter = ('rubric',)
    inlines = [RubricRatingInline]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser or request.user.role in ['globaladmin', 'superadmin']:
            return qs
        # Filter criteria based on rubric branch access
        if request.user.role == 'admin' and request.user.branch:
            return qs.filter(rubric__branch=request.user.branch)
        elif request.user.role == 'instructor' and request.user.branch:
            return qs.filter(
                models.Q(rubric__created_by=request.user) |
                models.Q(rubric__branch=request.user.branch)
            )
        return qs.none()


class RubricRatingAdmin(admin.ModelAdmin):
    list_display = ['title', 'criterion', 'description', 'points', 'position']
    list_filter = ['criterion__rubric']
    ordering = ['criterion', 'position']


class RubricEvaluationAdmin(admin.ModelAdmin):
    list_display = ['get_submission_or_discussion', 'criterion', 'rating', 'points', 'evaluated_by', 'created_at']
    list_filter = ['created_at', 'evaluated_by']
    search_fields = ['submission__assignment__title', 'discussion__title', 'criterion__description']
    readonly_fields = ['created_at', 'updated_at']
    
    def get_submission_or_discussion(self, obj):
        if obj.submission:
            return f"Assignment: {obj.submission.assignment.title} - {obj.submission.user.get_full_name()}"
        elif obj.discussion:
            return f"Discussion: {obj.discussion.title}"
        return "N/A"
    get_submission_or_discussion.short_description = 'Context'


class RubricEvaluationHistoryAdmin(admin.ModelAdmin):
    list_display = ['get_context', 'criterion', 'version', 'points', 'evaluated_by', 'evaluation_date', 'is_current']
    list_filter = ['evaluation_date', 'is_current', 'version', 'evaluated_by']
    search_fields = ['submission__assignment__title', 'discussion__title', 'criterion__description']
    readonly_fields = ['created_at']
    ordering = ['-evaluation_date', 'criterion', '-version']
    
    def get_context(self, obj):
        if obj.submission:
            return f"Assignment: {obj.submission.assignment.title} - {obj.submission.user.get_full_name()}"
        elif obj.discussion:
            return f"Discussion: {obj.discussion.title}"
        return "N/A"
    get_context.short_description = 'Context'


class RubricOverallFeedbackAdmin(admin.ModelAdmin):
    list_display = ['get_context', 'student', 'rubric', 'get_feedback_types', 'is_private', 'created_by', 'created_at']
    list_filter = ['is_private', 'created_at', 'created_by']
    search_fields = [
        'student__first_name', 'student__last_name', 'student__email',
        'rubric__title',
        'submission__assignment__title',
        'discussion__title',
        'conference__title',
        'quiz_attempt__quiz__title',
        'feedback'
    ]
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['-created_at']
    
    fieldsets = (
        ('Context', {
            'fields': ('submission', 'discussion', 'conference', 'quiz_attempt', 'student', 'rubric')
        }),
        ('Feedback Content', {
            'fields': ('feedback', 'audio_feedback', 'video_feedback', 'is_private')
        }),
        ('Metadata', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def get_context(self, obj):
        """Display the evaluation context in a human-readable format"""
        context_type = obj.get_context_type()
        context_obj = obj.get_context_object()
        
        if context_type == 'assignment' and context_obj:
            return f"Assignment: {context_obj.assignment.title} - {context_obj.user.get_full_name()}"
        elif context_type == 'discussion' and context_obj:
            return f"Discussion: {context_obj.title}"
        elif context_type == 'conference' and context_obj:
            return f"Conference: {context_obj.title}"
        elif context_type == 'quiz' and context_obj:
            return f"Quiz: {context_obj.quiz.title} - {context_obj.user.get_full_name()}"
        return "N/A"
    get_context.short_description = 'Context'
    
    def get_feedback_types(self, obj):
        """Display the types of feedback provided"""
        types = obj.get_feedback_types()
        if not types:
            return "No feedback"
        
        type_icons = {
            'text': '📝',
            'audio': '🎵',
            'video': '📹'
        }
        
        return ' '.join([type_icons.get(t, t) for t in types])
    get_feedback_types.short_description = 'Feedback Types'
    
    def get_queryset(self, request):
        """Filter queryset based on user permissions"""
        queryset = super().get_queryset(request)
        
        if request.user.is_superuser or request.user.role == 'globaladmin':
            return queryset
        
        if request.user.role == 'superadmin':
            # Super admin can see feedback from their business branches
            if hasattr(request.user, 'business_assignments'):
                business_ids = request.user.business_assignments.filter(
                    is_active=True
                ).values_list('business_id', flat=True)
                return queryset.filter(
                    rubric__branch__business_id__in=business_ids
                )
        
        if request.user.role in ['admin', 'instructor']:
            # Admin and instructors can see feedback from their branch
            if request.user.branch:
                return queryset.filter(rubric__branch=request.user.branch)
        
        return queryset.none()
    
    def save_model(self, request, obj, form, change):
        """Set created_by automatically"""
        if not change:  # Only set on creation
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
    
    def has_add_permission(self, request):
        """Allow add permission for instructors and above"""
        return request.user.role in ['globaladmin', 'superadmin', 'admin', 'instructor']
    
    def has_change_permission(self, request, obj=None):
        """Allow change permission for instructors and above"""
        if not request.user.role in ['globaladmin', 'superadmin', 'admin', 'instructor']:
            return False
        
        if obj is None:
            return True
        
        # Users can only edit their own feedback
        if request.user.role == 'instructor':
            return obj.created_by == request.user
        
        return True
    
    def has_delete_permission(self, request, obj=None):
        """Allow delete permission for admins and above"""
        if not request.user.role in ['globaladmin', 'superadmin', 'admin']:
            return False
        
        if obj is None:
            return True
        
        # Admins can delete feedback from their branch
        if request.user.role == 'admin':
            return obj.rubric.branch == request.user.branch
        
        return True


admin.site.register(RubricRating, RubricRatingAdmin)
admin.site.register(RubricEvaluation, RubricEvaluationAdmin)
admin.site.register(RubricEvaluationHistory, RubricEvaluationHistoryAdmin)
admin.site.register(RubricOverallFeedback, RubricOverallFeedbackAdmin) 