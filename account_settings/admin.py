from django.contrib import admin
from .models import TeamsIntegration

@admin.register(TeamsIntegration)
class TeamsIntegrationAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'service_account_email', 'is_active', 'created_at', 'updated_at')
    search_fields = ('name', 'user__username', 'service_account_email')
    list_filter = ('is_active',)
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'user', 'branch', 'is_active')
        }),
        ('API Credentials', {
            'fields': ('client_id', 'client_secret', 'tenant_id')
        }),
        ('Service Account', {
            'fields': ('service_account_email',),
            'description': 'Service account email must exist in Azure AD with Exchange Online license. This email will be used for creating Teams meetings when user email is not available.'
        }),
        ('Token Information', {
            'fields': ('access_token', 'token_expiry'),
            'classes': ('collapse',)
        }),
    )

 