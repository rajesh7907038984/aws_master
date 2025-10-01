from django.contrib import admin
from .models import OutcomeGroup, Outcome, OutcomeAlignment, RubricCriterionOutcome, OutcomeEvaluation

class OutcomeAdmin(admin.ModelAdmin):
    list_display = ('title', 'group', 'branch', 'created_at')
    list_filter = ('group', 'branch', 'created_at')
    search_fields = ('title', 'description', 'friendly_name')
    autocomplete_fields = ('group',)
    date_hierarchy = 'created_at'

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser or request.user.role in ['globaladmin', 'superadmin']:
            return qs
        # Branch admins can only see outcomes from their branch
        if request.user.role == 'admin' and request.user.branch:
            return qs.filter(branch=request.user.branch)
        return qs.none()

    def save_model(self, request, obj, form, change):
        # Automatically set branch for non-superusers
        if not (request.user.is_superuser or request.user.role in ['globaladmin', 'superadmin']):
            if request.user.branch:
                obj.branch = request.user.branch
        super().save_model(request, obj, form, change)

class OutcomeGroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'parent', 'branch', 'created_at')
    list_filter = ('parent', 'branch', 'created_at')
    search_fields = ('name', 'description')
    date_hierarchy = 'created_at'

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser or request.user.role in ['globaladmin', 'superadmin']:
            return qs
        # Branch admins can only see outcome groups from their branch
        if request.user.role == 'admin' and request.user.branch:
            return qs.filter(branch=request.user.branch)
        return qs.none()

    def save_model(self, request, obj, form, change):
        # Automatically set branch for non-superusers
        if not (request.user.is_superuser or request.user.role in ['globaladmin', 'superadmin']):
            if request.user.branch:
                obj.branch = request.user.branch
        super().save_model(request, obj, form, change)

@admin.register(OutcomeAlignment)
class OutcomeAlignmentAdmin(admin.ModelAdmin):
    list_display = ('outcome', 'content_type', 'object_id', 'created_at')
    list_filter = ('content_type', 'created_at')
    search_fields = ('outcome__title', 'object_id')
    autocomplete_fields = ('outcome',)
    date_hierarchy = 'created_at'

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser or request.user.role in ['globaladmin', 'superadmin']:
            return qs
        # Branch admins can only see alignments for outcomes from their branch
        if request.user.role == 'admin' and request.user.branch:
            return qs.filter(outcome__branch=request.user.branch)
        return qs.none()

@admin.register(RubricCriterionOutcome)
class RubricCriterionOutcomeAdmin(admin.ModelAdmin):
    list_display = ('criterion', 'outcome', 'weight', 'created_at')
    list_filter = ('weight', 'created_at')
    search_fields = ('criterion__description', 'outcome__title')
    autocomplete_fields = ('criterion', 'outcome')
    date_hierarchy = 'created_at'

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser or request.user.role in ['globaladmin', 'superadmin']:
            return qs
        # Branch admins can only see connections for outcomes from their branch
        if request.user.role == 'admin' and request.user.branch:
            return qs.filter(outcome__branch=request.user.branch)
        return qs.none()


@admin.register(OutcomeEvaluation)
class OutcomeEvaluationAdmin(admin.ModelAdmin):
    list_display = ('student', 'outcome', 'score', 'proficiency_level', 'evidence_count', 'calculation_date')
    list_filter = ('proficiency_level', 'outcome', 'calculation_date')
    search_fields = ('student__first_name', 'student__last_name', 'outcome__title')
    autocomplete_fields = ('student', 'outcome')
    date_hierarchy = 'calculation_date'
    readonly_fields = ('score', 'proficiency_level', 'evidence_count', 'calculation_date')

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser or request.user.role in ['globaladmin', 'superadmin']:
            return qs
        # Branch admins can only see evaluations for students from their branch
        if request.user.role == 'admin' and request.user.branch:
            return qs.filter(student__branch=request.user.branch)
        return qs.none()

    def has_add_permission(self, request):
        # Prevent manual creation - these should be calculated automatically
        return False

    def has_change_permission(self, request, obj=None):
        # Allow viewing but not editing calculated fields
        return True

    def has_delete_permission(self, request, obj=None):
        # Allow deletion for recalculation purposes
        return True


admin.site.register(OutcomeGroup, OutcomeGroupAdmin)
admin.site.register(Outcome, OutcomeAdmin) 