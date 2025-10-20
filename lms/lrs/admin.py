from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
import json

from .models import (
    LRS, Statement, ActivityProfile, AgentProfile, State
)


@admin.register(LRS)
class LRSAdmin(admin.ModelAdmin):
    list_display = ['name', 'endpoint', 'version', 'is_active', 'created_at']
    list_filter = ['is_active', 'version', 'created_at']
    search_fields = ['name', 'endpoint']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'endpoint', 'version', 'is_active')
        }),
        ('Authentication', {
            'fields': ('username', 'password', 'api_key'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )


@admin.register(Statement)
class StatementAdmin(admin.ModelAdmin):
    list_display = ['statement_id', 'actor_name', 'verb_display_short', 'object_definition_name_short', 'timestamp']
    list_filter = ['actor_type', 'object_type', 'timestamp', 'version']
    search_fields = ['statement_id', 'actor_name', 'actor_mbox', 'object_id']
    readonly_fields = ['statement_id', 'stored', 'raw_statement_formatted']
    date_hierarchy = 'timestamp'
    
    fieldsets = (
        ('Statement Information', {
            'fields': ('statement_id', 'timestamp', 'stored', 'version')
        }),
        ('Actor', {
            'fields': ('actor_type', 'actor_name', 'actor_mbox', 'actor_mbox_sha1sum', 'actor_openid', 'actor_account_homepage', 'actor_account_name')
        }),
        ('Verb', {
            'fields': ('verb_id', 'verb_display')
        }),
        ('Object', {
            'fields': ('object_type', 'object_id', 'object_definition_name', 'object_definition_description', 'object_definition_type')
        }),
        ('Result', {
            'fields': ('result_score_scaled', 'result_score_raw', 'result_score_min', 'result_score_max', 'result_success', 'result_completion', 'result_response', 'result_duration')
        }),
        ('Context', {
            'fields': ('context_registration', 'context_platform', 'context_language'),
            'classes': ('collapse',)
        }),
        ('Raw Statement', {
            'fields': ('raw_statement_formatted',),
            'classes': ('collapse',)
        })
    )
    
    def verb_display_short(self, obj):
        display = obj.verb_display
        if isinstance(display, dict):
            return display.get('en-US', str(display)[:50])
        return str(display)[:50]
    verb_display_short.short_description = 'Verb'
    
    def object_definition_name_short(self, obj):
        name = obj.object_definition_name
        if isinstance(name, dict):
            return name.get('en-US', str(name)[:50])
        return str(name)[:50]
    object_definition_name_short.short_description = 'Object'
    
    def raw_statement_formatted(self, obj):
        if obj.raw_statement:
            formatted = json.dumps(obj.raw_statement, indent=2, ensure_ascii=False)
            return format_html('<pre style="max-height: 300px; overflow-y: auto;">{}</pre>', formatted)
        return '-'
    raw_statement_formatted.short_description = 'Raw Statement'


@admin.register(ActivityProfile)
class ActivityProfileAdmin(admin.ModelAdmin):
    list_display = ['activity_id', 'profile_id', 'content_type', 'updated_at']
    list_filter = ['content_type', 'updated_at']
    search_fields = ['activity_id', 'profile_id']
    readonly_fields = ['updated_at', 'content_formatted']
    
    def content_formatted(self, obj):
        if obj.content:
            formatted = json.dumps(obj.content, indent=2, ensure_ascii=False)
            return format_html('<pre style="max-height: 300px; overflow-y: auto;">{}</pre>', formatted)
        return '-'
    content_formatted.short_description = 'Content'


@admin.register(AgentProfile)
class AgentProfileAdmin(admin.ModelAdmin):
    list_display = ['profile_id', 'agent_short', 'content_type', 'updated_at']
    list_filter = ['content_type', 'updated_at']
    search_fields = ['profile_id', 'agent']
    readonly_fields = ['updated_at', 'agent_formatted', 'content_formatted']
    
    def agent_short(self, obj):
        agent = obj.agent
        if isinstance(agent, dict):
            return agent.get('name', str(agent)[:50])
        return str(agent)[:50]
    agent_short.short_description = 'Agent'
    
    def agent_formatted(self, obj):
        if obj.agent:
            formatted = json.dumps(obj.agent, indent=2, ensure_ascii=False)
            return format_html('<pre style="max-height: 200px; overflow-y: auto;">{}</pre>', formatted)
        return '-'
    agent_formatted.short_description = 'Agent'
    
    def content_formatted(self, obj):
        if obj.content:
            formatted = json.dumps(obj.content, indent=2, ensure_ascii=False)
            return format_html('<pre style="max-height: 300px; overflow-y: auto;">{}</pre>', formatted)
        return '-'
    content_formatted.short_description = 'Content'


@admin.register(State)
class StateAdmin(admin.ModelAdmin):
    list_display = ['activity_id', 'state_id', 'agent_short', 'updated_at']
    list_filter = ['content_type', 'updated_at']
    search_fields = ['activity_id', 'state_id', 'agent']
    readonly_fields = ['updated_at', 'agent_formatted', 'content_formatted']
    
    def agent_short(self, obj):
        agent = obj.agent
        if isinstance(agent, dict):
            return agent.get('name', str(agent)[:50])
        return str(agent)[:50]
    agent_short.short_description = 'Agent'
    
    def agent_formatted(self, obj):
        if obj.agent:
            formatted = json.dumps(obj.agent, indent=2, ensure_ascii=False)
            return format_html('<pre style="max-height: 200px; overflow-y: auto;">{}</pre>', formatted)
        return '-'
    agent_formatted.short_description = 'Agent'
    
    def content_formatted(self, obj):
        if obj.content:
            formatted = json.dumps(obj.content, indent=2, ensure_ascii=False)
            return format_html('<pre style="max-height: 300px; overflow-y: auto;">{}</pre>', formatted)
        return '-'
    content_formatted.short_description = 'Content'


