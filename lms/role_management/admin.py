from django.contrib import admin
from .models import Role, RoleCapability, UserRole

class RoleCapabilityInline(admin.TabularInline):
    model = RoleCapability
    extra = 1

class UserRoleInline(admin.TabularInline):
    model = UserRole
    extra = 1

@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ('name', 'description', 'created_at', 'updated_at')
    search_fields = ('name', 'description')
    inlines = [RoleCapabilityInline, UserRoleInline]

@admin.register(RoleCapability)
class RoleCapabilityAdmin(admin.ModelAdmin):
    list_display = ('role', 'capability', 'description', 'created_at')
    search_fields = ('role__name', 'capability', 'description')
    list_filter = ('role',)

@admin.register(UserRole)
class UserRoleAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'assigned_at')
    search_fields = ('user__username', 'role__name')
    list_filter = ('role',)
