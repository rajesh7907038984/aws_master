from django.contrib import admin
from .models import TeamsIntegration

@admin.register(TeamsIntegration)
class TeamsIntegrationAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'is_active', 'created_at', 'updated_at')
    search_fields = ('name', 'user__username')
    list_filter = ('is_active',)

 