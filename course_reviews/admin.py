from django.contrib import admin
from .models import Survey, SurveyField, SurveyResponse, CourseReview


class SurveyFieldInline(admin.TabularInline):
    model = SurveyField
    extra = 1
    fields = ['label', 'field_type', 'is_required', 'order', 'max_rating']
    ordering = ['order']


@admin.register(Survey)
class SurveyAdmin(admin.ModelAdmin):
    list_display = ['title', 'created_by', 'branch', 'is_active', 'get_fields_count', 'get_responses_count', 'created_at']
    list_filter = ['is_active', 'branch', 'created_at']
    search_fields = ['title', 'description', 'created_by__username']
    readonly_fields = ['created_at', 'updated_at']
    inlines = [SurveyFieldInline]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('title', 'description', 'created_by', 'branch')
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def save_model(self, request, obj, form, change):
        if not change:  # If creating new survey
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(SurveyField)
class SurveyFieldAdmin(admin.ModelAdmin):
    list_display = ['label', 'survey', 'field_type', 'is_required', 'order']
    list_filter = ['field_type', 'is_required', 'survey']
    search_fields = ['label', 'survey__title']
    ordering = ['survey', 'order']


@admin.register(SurveyResponse)
class SurveyResponseAdmin(admin.ModelAdmin):
    list_display = ['user', 'course', 'survey_field', 'response_value', 'submitted_at']
    list_filter = ['submitted_at', 'course', 'survey_field__survey']
    search_fields = ['user__username', 'course__title', 'text_response']
    readonly_fields = ['submitted_at']
    date_hierarchy = 'submitted_at'
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('survey_field', 'user', 'course')
        }),
        ('Response Data', {
            'fields': ('text_response', 'rating_response')
        }),
        ('Metadata', {
            'fields': ('submitted_at',),
            'classes': ('collapse',)
        }),
    )


@admin.register(CourseReview)
class CourseReviewAdmin(admin.ModelAdmin):
    list_display = ['user', 'course', 'average_rating', 'is_published', 'submitted_at']
    list_filter = ['is_published', 'submitted_at', 'course']
    search_fields = ['user__username', 'course__title', 'review_text']
    readonly_fields = ['submitted_at', 'updated_at']
    date_hierarchy = 'submitted_at'
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('course', 'user', 'survey')
        }),
        ('Review Data', {
            'fields': ('average_rating', 'review_text')
        }),
        ('Status', {
            'fields': ('is_published',)
        }),
        ('Metadata', {
            'fields': ('submitted_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )