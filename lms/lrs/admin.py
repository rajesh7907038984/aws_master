from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
import json

from .models import (
    LRS, Statement, ActivityProfile, AgentProfile, State,
    CMI5AU, CMI5Registration, CMI5Session,
    SCORM2004Sequencing, SCORM2004ActivityState
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


@admin.register(CMI5AU)
class CMI5AUAdmin(admin.ModelAdmin):
    list_display = ['au_id', 'title', 'move_on', 'launch_method', 'created_at']
    list_filter = ['move_on', 'launch_method', 'created_at']
    search_fields = ['au_id', 'title', 'description']
    readonly_fields = ['created_at', 'updated_at', 'au_metadata_formatted']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('au_id', 'title', 'description')
        }),
        ('Launch Configuration', {
            'fields': ('launch_url', 'launch_method', 'launch_parameters')
        }),
        ('Completion Criteria', {
            'fields': ('mastery_score', 'move_on')
        }),
        ('Metadata', {
            'fields': ('au_metadata_formatted',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def au_metadata_formatted(self, obj):
        if obj.au_metadata:
            formatted = json.dumps(obj.au_metadata, indent=2, ensure_ascii=False)
            return format_html('<pre style="max-height: 300px; overflow-y: auto;">{}</pre>', formatted)
        return '-'
    au_metadata_formatted.short_description = 'AU Metadata'


@admin.register(CMI5Registration)
class CMI5RegistrationAdmin(admin.ModelAdmin):
    list_display = ['registration_id', 'learner', 'au', 'course_id', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['registration_id', 'learner__username', 'au__title', 'course_id']
    readonly_fields = ['registration_id', 'created_at', 'updated_at', 'launch_parameters_formatted']
    
    def launch_parameters_formatted(self, obj):
        if obj.launch_parameters:
            formatted = json.dumps(obj.launch_parameters, indent=2, ensure_ascii=False)
            return format_html('<pre style="max-height: 200px; overflow-y: auto;">{}</pre>', formatted)
        return '-'
    launch_parameters_formatted.short_description = 'Launch Parameters'


@admin.register(CMI5Session)
class CMI5SessionAdmin(admin.ModelAdmin):
    list_display = ['session_id', 'registration', 'launch_time', 'exit_time', 'is_active']
    list_filter = ['is_active', 'launch_time']
    search_fields = ['session_id', 'registration__learner__username']
    readonly_fields = ['session_id', 'created_at', 'updated_at']


@admin.register(SCORM2004Sequencing)
class SCORM2004SequencingAdmin(admin.ModelAdmin):
    list_display = ['activity_id', 'title', 'created_at']
    search_fields = ['activity_id', 'title', 'description']
    readonly_fields = ['created_at', 'updated_at', 'sequencing_rules_formatted', 'rollup_rules_formatted', 'objectives_formatted']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('activity_id', 'parent_id', 'title', 'description')
        }),
        ('Sequencing Rules', {
            'fields': ('sequencing_rules_formatted',),
            'classes': ('collapse',)
        }),
        ('Rollup Rules', {
            'fields': ('rollup_rules_formatted',),
            'classes': ('collapse',)
        }),
        ('Navigation Rules', {
            'fields': ('navigation_rules',),
            'classes': ('collapse',)
        }),
        ('Objectives', {
            'fields': ('objectives_formatted',),
            'classes': ('collapse',)
        }),
        ('Completion Criteria', {
            'fields': ('completion_threshold', 'mastery_score')
        }),
        ('Prerequisites', {
            'fields': ('prerequisites',),
            'classes': ('collapse',)
        }),
        ('Delivery Controls', {
            'fields': ('delivery_controls',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def sequencing_rules_formatted(self, obj):
        if obj.sequencing_rules:
            formatted = json.dumps(obj.sequencing_rules, indent=2, ensure_ascii=False)
            return format_html('<pre style="max-height: 300px; overflow-y: auto;">{}</pre>', formatted)
        return '-'
    sequencing_rules_formatted.short_description = 'Sequencing Rules'
    
    def rollup_rules_formatted(self, obj):
        if obj.rollup_rules:
            formatted = json.dumps(obj.rollup_rules, indent=2, ensure_ascii=False)
            return format_html('<pre style="max-height: 300px; overflow-y: auto;">{}</pre>', formatted)
        return '-'
    rollup_rules_formatted.short_description = 'Rollup Rules'
    
    def objectives_formatted(self, obj):
        if obj.objectives:
            formatted = json.dumps(obj.objectives, indent=2, ensure_ascii=False)
            return format_html('<pre style="max-height: 300px; overflow-y: auto;">{}</pre>', formatted)
        return '-'
    objectives_formatted.short_description = 'Objectives'


@admin.register(SCORM2004ActivityState)
class SCORM2004ActivityStateAdmin(admin.ModelAdmin):
    list_display = ['activity_id', 'learner', 'completion_status', 'success_status', 'last_launch']
    list_filter = ['completion_status', 'success_status', 'last_launch']
    search_fields = ['activity_id', 'learner__username', 'registration_id']
    readonly_fields = ['created_at', 'updated_at', 'objectives_formatted', 'interactions_formatted', 'raw_data_formatted']
    
    fieldsets = (
        ('Activity Information', {
            'fields': ('activity_id', 'learner', 'registration_id')
        }),
        ('Status', {
            'fields': ('completion_status', 'success_status', 'progress_measure', 'completion_threshold')
        }),
        ('Score', {
            'fields': ('score_scaled', 'score_raw', 'score_min', 'score_max')
        }),
        ('Time', {
            'fields': ('total_time', 'session_time')
        }),
        ('Location and Data', {
            'fields': ('location', 'suspend_data')
        }),
        ('Objectives', {
            'fields': ('objectives_formatted',),
            'classes': ('collapse',)
        }),
        ('Interactions', {
            'fields': ('interactions_formatted',),
            'classes': ('collapse',)
        }),
        ('Raw Data', {
            'fields': ('raw_data_formatted',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('first_launch', 'last_launch', 'completion_date', 'created_at', 'updated_at')
        })
    )
    
    def objectives_formatted(self, obj):
        if obj.objectives:
            formatted = json.dumps(obj.objectives, indent=2, ensure_ascii=False)
            return format_html('<pre style="max-height: 300px; overflow-y: auto;">{}</pre>', formatted)
        return '-'
    objectives_formatted.short_description = 'Objectives'
    
    def interactions_formatted(self, obj):
        if obj.interactions:
            formatted = json.dumps(obj.interactions, indent=2, ensure_ascii=False)
            return format_html('<pre style="max-height: 300px; overflow-y: auto;">{}</pre>', formatted)
        return '-'
    interactions_formatted.short_description = 'Interactions'
    
    def raw_data_formatted(self, obj):
        if obj.raw_data:
            formatted = json.dumps(obj.raw_data, indent=2, ensure_ascii=False)
            return format_html('<pre style="max-height: 300px; overflow-y: auto;">{}</pre>', formatted)
        return '-'
    raw_data_formatted.short_description = 'Raw Data'
