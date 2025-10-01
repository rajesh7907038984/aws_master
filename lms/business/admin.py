from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.contrib.auth.models import AnonymousUser
from .models import Business, BusinessUserAssignment
from users.models import CustomUser

class BusinessUserAssignmentInline(admin.TabularInline):
    model = BusinessUserAssignment
    extra = 1
    fields = ('user', 'is_active', 'assigned_by')
    readonly_fields = ('assigned_by', 'assigned_at')
    autocomplete_fields = ('user',)
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('user', 'assigned_by')
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "user":
            # Only show Super Admin users for assignment
            kwargs["queryset"] = CustomUser.objects.filter(role='superadmin')
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

@admin.register(Business)
class BusinessAdmin(admin.ModelAdmin):
    list_display = ['name', 'description', 'get_branches_count', 'get_super_admins_count', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at', 'country']
    search_fields = ['name', 'description', 'email', 'phone']
    readonly_fields = ('created_at', 'updated_at')
    inlines = [BusinessUserAssignmentInline]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'description', 'is_active')
        }),
        ('Contact Information', {
            'fields': ('address_line1', 'address_line2', 'city', 'state_province', 'postal_code', 'country', 'phone', 'email', 'website'),
            'classes': ['collapse']
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ['collapse']
        })
    )
    
    def get_branches_count(self, obj):
        return obj.get_business_branch_count()
    get_branches_count.short_description = 'Branches'
    
    def get_super_admins_count(self, obj):
        return obj.get_business_super_admins().count()
    get_super_admins_count.short_description = 'Super Admins'
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # Only Global Admins can see all businesses
        if request.user.role == 'globaladmin' or request.user.is_superuser:
            return qs
        # Super Admins can only see their assigned businesses
        elif request.user.role in ['globaladmin', 'superadmin']:
            return qs.filter(user_assignments__user=request.user, user_assignments__is_active=True)
        else:
            return qs.none()
    
    def has_add_permission(self, request):
        # Only Global Admins can create businesses
        return request.user.role == 'globaladmin' or request.user.is_superuser
    
    def has_change_permission(self, request, obj=None):
        if request.user.role == 'globaladmin' or request.user.is_superuser:
            return True
        if obj and request.user.role in ['globaladmin', 'superadmin']:
            # Super Admins can only edit businesses they're assigned to
            return obj.user_assignments.filter(user=request.user, is_active=True).exists()
        return False
    
    def has_delete_permission(self, request, obj=None):
        # Only Global Admins can delete businesses
        return request.user.role == 'globaladmin' or request.user.is_superuser
    
    def save_formset(self, request, form, formset, change):
        """Handle saving of inline formsets"""
        if formset.model == BusinessUserAssignment:
            instances = formset.save(commit=False)
            for instance in instances:
                if not instance.assigned_by:
                    instance.assigned_by = request.user
                instance.save()
            formset.save_m2m()
        else:
            formset.save()

@admin.register(BusinessUserAssignment)
class BusinessUserAssignmentAdmin(admin.ModelAdmin):
    list_display = ['user', 'business', 'is_active', 'assigned_by', 'assigned_at']
    list_filter = ['is_active', 'assigned_at', 'business']
    search_fields = ['user__username', 'user__email', 'business__name']
    readonly_fields = ('assigned_at',)
    autocomplete_fields = ('user', 'business', 'assigned_by')
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.role == 'globaladmin' or request.user.is_superuser:
            return qs
        # Super Admins can only see assignments for businesses they're assigned to
        elif request.user.role in ['globaladmin', 'superadmin']:
            user_businesses = Business.objects.filter(
                user_assignments__user=request.user, 
                user_assignments__is_active=True
            )
            return qs.filter(business__in=user_businesses)
        else:
            return qs.none()
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "user":
            kwargs["queryset"] = CustomUser.objects.filter(role='superadmin')
        elif db_field.name == "business":
            if request.user.role in ['globaladmin', 'superadmin']:
                # Super Admins can only assign users to businesses they manage
                kwargs["queryset"] = Business.objects.filter(
                    user_assignments__user=request.user,
                    user_assignments__is_active=True
                )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
    
    def has_add_permission(self, request):
        return request.user.role in ['globaladmin', 'superadmin'] or request.user.is_superuser
    
    def has_change_permission(self, request, obj=None):
        if request.user.role == 'globaladmin' or request.user.is_superuser:
            return True
        if obj and request.user.role in ['globaladmin', 'superadmin']:
            # Super Admins can only modify assignments for businesses they manage
            return obj.business.user_assignments.filter(user=request.user, is_active=True).exists()
        return False
    
    def has_delete_permission(self, request, obj=None):
        return self.has_change_permission(request, obj)
    
    def save_model(self, request, obj, form, change):
        if not change and not obj.assigned_by:
            obj.assigned_by = request.user
        super().save_model(request, obj, form, change)
