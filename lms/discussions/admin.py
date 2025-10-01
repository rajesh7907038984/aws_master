from django.contrib import admin
from django.db import models
from .models import Discussion, Comment

@admin.register(Discussion)
class DiscussionAdmin(admin.ModelAdmin):
    list_display = ('title', 'course', 'created_by', 'created_at', 'updated_at', 'visibility')
    list_filter = ('visibility', 'course__branch', 'created_at', 'updated_at')
    search_fields = ('title', 'content', 'instructions', 'created_by__username')
    date_hierarchy = 'created_at'

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser or request.user.role in ['globaladmin', 'superadmin']:
            return qs
        # Branch admins can only see discussions from their branch
        if request.user.role == 'admin' and request.user.branch:
            return qs.filter(course__branch=request.user.branch)
        # Instructors can see discussions they created or from courses they teach
        elif request.user.role == 'instructor' and request.user.branch:
            return qs.filter(
                models.Q(created_by=request.user) |
                models.Q(course__instructor=request.user) |
                models.Q(course__branch=request.user.branch)
            )
        return qs.none()

@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ('discussion', 'created_by', 'created_at', 'updated_at')
    list_filter = ('discussion__course__branch', 'created_at', 'updated_at')
    search_fields = ('content', 'created_by__username', 'discussion__title')
    date_hierarchy = 'created_at'

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser or request.user.role in ['globaladmin', 'superadmin']:
            return qs
        # Filter comments based on discussion branch access
        if request.user.role == 'admin' and request.user.branch:
            return qs.filter(discussion__course__branch=request.user.branch)
        elif request.user.role == 'instructor' and request.user.branch:
            return qs.filter(
                models.Q(created_by=request.user) |
                models.Q(discussion__created_by=request.user) |
                models.Q(discussion__course__instructor=request.user) |
                models.Q(discussion__course__branch=request.user.branch)
            )
        return qs.none()
