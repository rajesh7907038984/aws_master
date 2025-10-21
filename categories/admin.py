from django.contrib import admin
from .models import CourseCategory

@admin.register(CourseCategory)
class CourseCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'branch', 'is_active', 'created_at')
    list_filter = ('is_active', 'branch')
    search_fields = ('name', 'description')
    prepopulated_fields = {'slug': ('name',)}
    ordering = ('name',)

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser or request.user.role == 'admin'

    def has_change_permission(self, request, obj=None):
        if request.user.is_superuser or request.user.role in ['globaladmin', 'superadmin']:
            return True
        if request.user.role == 'admin' and obj:
            return obj.branch == request.user.branch
        return request.user.role == 'admin'

    def has_add_permission(self, request):
        return request.user.is_superuser or request.user.role == 'admin'

    def has_delete_permission(self, request, obj=None):
        if request.user.is_superuser or request.user.role in ['globaladmin', 'superadmin']:
            return True
        if request.user.role == 'admin' and obj:
            return obj.branch == request.user.branch
        return False

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser or request.user.role in ['globaladmin', 'superadmin']:
            return qs
        # Branch admins can only see categories from their branch
        if request.user.role == 'admin' and request.user.branch:
            return qs.filter(branch=request.user.branch)
        return qs.none()

    def save_model(self, request, obj, form, change):
        # Automatically set branch for non-superusers
        if not (request.user.is_superuser or request.user.role in ['globaladmin', 'superadmin']):
            if request.user.branch:
                obj.branch = request.user.branch
        super().save_model(request, obj, form, change)
