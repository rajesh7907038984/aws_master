from django.contrib import admin
from django.db import models
from .widgets import TinyMCEWidget, TinyMCEAdvancedWidget, TinyMCESimpleWidget


class TinyMCEAdminMixin:
    """
    Mixin for Django admin classes to easily add TinyMCE widgets.
    """
    
    formfield_overrides = {
        models.TextField: {'widget': TinyMCEWidget},
    }
    
    class Media:
        js = (
            'tinymce_editor/tinymce/tinymce.min.js',
            'tinymce_editor/js/tinymce-widget.js',
        )
        css = {
            'all': (
                'tinymce_editor/css/tinymce-widget.css',
            )
        }


class TinyMCEAdvancedAdminMixin:
    """
    Mixin for Django admin classes with advanced TinyMCE features.
    """
    
    formfield_overrides = {
        models.TextField: {'widget': TinyMCEAdvancedWidget},
    }
    
    class Media:
        js = (
            'tinymce_editor/tinymce/tinymce.min.js',
            'tinymce_editor/js/tinymce-widget.js',
        )
        css = {
            'all': (
                'tinymce_editor/css/tinymce-widget.css',
            )
        }


class TinyMCESimpleAdminMixin:
    """
    Mixin for Django admin classes with simple TinyMCE features.
    """
    
    formfield_overrides = {
        models.TextField: {'widget': TinyMCESimpleWidget},
    }
    
    class Media:
        js = (
            'tinymce_editor/tinymce/tinymce.min.js',
            'tinymce_editor/js/tinymce-widget.js',
        )
        css = {
            'all': (
                'tinymce_editor/css/tinymce-widget.css',
            )
        }


# Base admin classes that can be inherited
class TinyMCEModelAdmin(TinyMCEAdminMixin, admin.ModelAdmin):
    """
    ModelAdmin with TinyMCE integration.
    """
    pass


class TinyMCEAdvancedModelAdmin(TinyMCEAdvancedAdminMixin, admin.ModelAdmin):
    """
    ModelAdmin with advanced TinyMCE integration.
    """
    pass


class TinyMCESimpleModelAdmin(TinyMCESimpleAdminMixin, admin.ModelAdmin):
    """
    ModelAdmin with simple TinyMCE integration.
    """
    pass


class TinyMCEStackedInline(TinyMCEAdminMixin, admin.StackedInline):
    """
    StackedInline with TinyMCE integration.
    """
    pass


class TinyMCETabularInline(TinyMCEAdminMixin, admin.TabularInline):
    """
    TabularInline with TinyMCE integration.
    """
    pass


# Custom admin field override function
def get_tinymce_formfield_overrides(widget_type='default'):
    """
    Get formfield overrides for different TinyMCE widget types.
    
    Args:
        widget_type (str): 'default', 'advanced', or 'simple'
    
    Returns:
        dict: Formfield overrides dictionary
    """
    widgets = {
        'default': TinyMCEWidget,
        'advanced': TinyMCEAdvancedWidget,
        'simple': TinyMCESimpleWidget,
    }
    
    widget_class = widgets.get(widget_type, TinyMCEWidget)
    
    return {
        models.TextField: {'widget': widget_class},
    }


# Utility function to add TinyMCE to existing admin classes
def register_tinymce_for_model(model_class, admin_class=None, widget_type='default'):
    """
    Register a model with TinyMCE-enabled admin.
    
    Args:
        model_class: The Django model class
        admin_class: Optional custom admin class (will create one if not provided)
        widget_type: 'default', 'advanced', or 'simple'
    """
    if admin_class is None:
        # Create a dynamic admin class
        class_name = f'{model_class.__name__}TinyMCEAdmin'
        admin_class = type(class_name, (TinyMCEModelAdmin,), {
            'formfield_overrides': get_tinymce_formfield_overrides(widget_type)
        })
    
    # Unregister if already registered
    if admin.site.is_registered(model_class):
        admin.site.unregister(model_class)
    
    # Register with TinyMCE admin
    admin.site.register(model_class, admin_class)


# Register AI token management models
from .models import BranchAITokenLimit, AITokenUsage

@admin.register(BranchAITokenLimit)
class BranchAITokenLimitAdmin(admin.ModelAdmin):
    list_display = ['branch', 'monthly_token_limit', 'is_unlimited', 'get_current_usage', 'get_usage_percentage', 'updated_at', 'updated_by']
    list_filter = ['is_unlimited', 'updated_at', 'branch__business']
    search_fields = ['branch__name', 'branch__business__name']
    readonly_fields = ['created_at', 'updated_at', 'get_current_usage', 'get_usage_percentage']
    
    def get_current_usage(self, obj):
        """Display current month's token usage"""
        return f"{obj.get_current_month_usage():,}"
    get_current_usage.short_description = 'Current Usage'
    
    def get_usage_percentage(self, obj):
        """Display usage percentage"""
        if obj.is_unlimited:
            return "Unlimited"
        return f"{obj.get_usage_percentage():.1f}%"
    get_usage_percentage.short_description = 'Usage %'
    
    def save_model(self, request, obj, form, change):
        """Set the updated_by field to current user"""
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)

@admin.register(AITokenUsage)
class AITokenUsageAdmin(admin.ModelAdmin):
    list_display = ['user', 'get_branch', 'tokens_used', 'model_used', 'success', 'created_at']
    list_filter = ['success', 'model_used', 'created_at', 'user__branch']
    search_fields = ['user__username', 'user__email', 'user__branch__name', 'prompt_text']
    readonly_fields = ['user', 'tokens_used', 'prompt_text', 'response_length', 'model_used', 'success', 'error_message', 'created_at']
    date_hierarchy = 'created_at'
    
    def get_branch(self, obj):
        """Display user's branch"""
        return obj.user.branch.name if obj.user.branch else 'No Branch'
    get_branch.short_description = 'Branch'
    
    def has_add_permission(self, request):
        """Prevent manual addition of usage records"""
        return False
    
    def has_change_permission(self, request, obj=None):
        """Prevent editing of usage records"""
        return False
