from django.contrib import admin
from .models import Branch, BranchUserLimits, AdminBranchAssignment

@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ('name', 'business', 'is_active', 'created_at', 'updated_at')
    list_filter = ('business', 'is_active', 'sharepoint_integration_enabled', 'order_management_enabled')
    search_fields = ('name', 'business__name')
    ordering = ('business__name', 'name')
    readonly_fields = ('created_at', 'updated_at')

@admin.register(BranchUserLimits)
class BranchUserLimitsAdmin(admin.ModelAdmin):
    list_display = ('branch', 'user_limit', 'admin_limit', 'instructor_limit', 'learner_limit', 'updated_by', 'updated_at')
    list_filter = ('branch__business',)
    search_fields = ('branch__name', 'branch__business__name')
    ordering = ('branch__business__name', 'branch__name')
    readonly_fields = ('created_at', 'updated_at')

@admin.register(AdminBranchAssignment)
class AdminBranchAssignmentAdmin(admin.ModelAdmin):
    list_display = ('user', 'branch', 'is_active', 'assigned_by', 'assigned_at')
    list_filter = ('is_active', 'branch__business', 'assigned_at')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'branch__name', 'branch__business__name')
    ordering = ('-assigned_at',)
    readonly_fields = ('assigned_at',)
    
    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.select_related('user', 'branch', 'branch__business', 'assigned_by')
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "user":
            kwargs["queryset"] = db_field.related_model.objects.filter(role='admin', is_active=True)
        elif db_field.name == "branch":
            kwargs["queryset"] = db_field.related_model.objects.filter(is_active=True)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)