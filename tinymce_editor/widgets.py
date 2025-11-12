from django import forms
from django.conf import settings
from django.template.loader import render_to_string
from django.utils.safestring import mark_safe
from django.forms.widgets import Media
from django.urls import reverse


class TinyMCEWidget(forms.Textarea):
    """
    TinyMCE Widget for Django forms with customizable configuration.
    """
    
    def __init__(self, attrs=None, config=None):
        self.config = config or {}
        super().__init__(attrs)
        
    class Media:
        js = (
            'tinymce_editor/tinymce/tinymce.min.js',
            'tinymce_editor/js/tinymce-widget.js',
        )
        css = {
            'all': (
                'tinymce_editor/css/tinymce-widget.css',
                'tinymce_editor/css/aiwriter.css',
            )
        }
    
    def render(self, name, value, attrs=None, renderer=None):
        if attrs is None:
            attrs = {}
        
        attrs['class'] = attrs.get('class', '') + ' tinymce-editor'
        attrs['data-tinymce-config'] = self.get_config_json()
        
        textarea = super().render(name, value, attrs, renderer)
        
        return mark_safe(textarea)
    
    def get_config_json(self):
        """Return TinyMCE configuration as JSON string."""
        import json
        
        default_config = {
            'height': 400,
            'menubar': 'edit view insert format tools',
            'plugins': [
                'advlist', 'autolink', 'lists', 'link', 'image', 'charmap', 'preview',
                'anchor', 'searchreplace', 'visualblocks', 'code', 'fullscreen',
                'insertdatetime', 'media', 'table', 'wordcount', 'aiwriter'
            ],
            'toolbar': 'undo redo | blocks | ' +
                      'bold italic forecolor | alignleft aligncenter ' +
                      'alignright alignjustify | bullist numlist outdent indent | ' +
                      'removeformat | image media | code fullscreen | aiwriter',
            'toolbar_sticky': True,
            'toolbar_sticky_offset': 0,
            'content_style': 'body { font-family:Helvetica,Arial,sans-serif; font-size:14px }',
            'image_advtab': True,
            'image_uploadtab': True,
            'images_upload_url': '/tinymce/upload_image/',
            'automatic_uploads': True,
            'file_picker_types': 'image media',
            'media_upload_url': '/tinymce/upload_media_file/',
            'media_live_embeds': True,
            'media_filter_html': False,
            'media_url_resolver': None,  # Will be set via JavaScript
            'images_upload_handler': None,  # Will be set via JavaScript
            'media_upload_handler': None,  # Will be set via JavaScript
            'browser_spellcheck': True,
            'contextmenu': False,
            'mobile': {
                'menubar': False,
                'toolbar_mode': 'floating',
                'toolbar': 'undo redo | bold italic | link image | bullist numlist',
                'plugins': ['autosave', 'lists', 'autolink', 'link', 'image']
            },
            'statusbar': True,
            'resize': True,
            'branding': False,
            'promotion': False,
            'file_picker_callback': None,  # Will be set via JavaScript
            'external_plugins': {
                'aiwriter': '/static/tinymce_editor/js/plugins/aiwriter/plugin.js'
            },
            'paste_as_text': True,
            'paste_data_images': True,
            # TinyMCE 7.0 compatible paste options
            'paste_preprocess': None,  # Custom paste preprocessing if needed
            'paste_postprocess': None,  # Custom paste postprocessing if needed
        }
        
        # Merge with custom config
        config = {**default_config, **self.config}
        return json.dumps(config)


class TinyMCEAdvancedWidget(TinyMCEWidget):
    """
    Advanced TinyMCE Widget with more features enabled.
    """
    
    def get_config_json(self):
        import json
        
        advanced_config = {
            'height': 500,
            'menubar': 'edit view insert format tools table',
            'plugins': [
                'advlist', 'autolink', 'lists', 'link', 'image', 'charmap', 'preview',
                'anchor', 'searchreplace', 'visualblocks', 'visualchars', 'code',
                'fullscreen', 'insertdatetime', 'media', 'table', 'wordcount',
                'autosave', 'codesample', 'emoticons', 'importcss', 'nonbreaking',
                'pagebreak', 'quickbars', 'save', 'aiwriter'
            ],
            'toolbar': 'undo redo | blocks fontfamily fontsize | ' +
                      'bold italic underline strikethrough | ' +
                      'alignleft aligncenter alignright alignjustify | ' +
                      'outdent indent | numlist bullist | ' +
                      'forecolor backcolor | ' +
                      'link image media | ' +
                      'insertdatetime charmap emoticons | ' +
                      'code codesample | ' +
                      'searchreplace | ' +
                      'fullscreen preview | aiwriter',
            'toolbar_mode': 'sliding',
            'toolbar_sticky': True,
            'toolbar_sticky_offset': 0,
            'content_style': 'body { font-family:Helvetica,Arial,sans-serif; font-size:14px }',
            'quickbars_selection_toolbar': 'bold italic | quicklink h2 h3 blockquote quickimage quicktable',
            'quickbars_insert_toolbar': 'quickimage quicktable',
            'contextmenu': 'link image table',
            'skin': 'oxide',
            'content_css': 'default',
            'autosave_ask_before_unload': True,
            'autosave_interval': '30s',
            'autosave_prefix': '{path}{query}-{id}-',
            'autosave_restore_when_empty': False,
            'autosave_retention': '2m',
            'image_advtab': True,
            'image_uploadtab': True,
            'images_upload_url': '/tinymce/upload_image/',
            'automatic_uploads': True,
            'file_picker_types': 'image media',
            'media_upload_url': '/tinymce/upload_media_file/',
            'media_live_embeds': True,
            'media_filter_html': False,
            'media_url_resolver': None,  # Will be set via JavaScript
            'images_upload_handler': None,  # Will be set via JavaScript
            'media_upload_handler': None,  # Will be set via JavaScript
            'file_picker_callback': None,  # Will be set via JavaScript
            'external_plugins': {
                'aiwriter': '/static/tinymce_editor/js/plugins/aiwriter/plugin.min.js'
            },
            'paste_as_text': True,
            'paste_data_images': True,
            # TinyMCE 7.0 compatible paste options
            'paste_preprocess': None,  # Custom paste preprocessing if needed
            'paste_postprocess': None,  # Custom paste postprocessing if needed
        }
        
        # Merge with custom config
        config = {**advanced_config, **self.config}
        return json.dumps(config)


class TinyMCESimpleWidget(TinyMCEWidget):
    """
    Simple TinyMCE Widget with minimal features.
    """
    
    def get_config_json(self):
        import json
        
        simple_config = {
            'height': 300,
            'menubar': False,
            'plugins': [
                'autolink', 'lists', 'link', 'charmap',
                'searchreplace', 'visualblocks', 'code', 'fullscreen',
                'insertdatetime', 'media', 'wordcount', 'image', 'aiwriter'
            ],
            'toolbar': 'undo redo | bold italic | ' +
                      'alignleft aligncenter alignright | ' +
                      'bullist numlist | ' +
                      'link | image media | ' +
                      'removeformat | fullscreen | aiwriter',
            'content_style': 'body { font-family:Helvetica,Arial,sans-serif; font-size:14px }',
            'image_advtab': True,
            'image_uploadtab': True,
            'images_upload_url': '/tinymce/upload_image/',
            'automatic_uploads': True,
            'file_picker_types': 'image media',
            'media_upload_url': '/tinymce/upload_media_file/',
            'media_live_embeds': True,
            'media_filter_html': False,
            'media_url_resolver': None,  # Will be set via JavaScript
            'images_upload_handler': None,  # Will be set via JavaScript
            'media_upload_handler': None,  # Will be set via JavaScript
            'file_picker_callback': None,  # Will be set via JavaScript
            'external_plugins': {
                'aiwriter': '/static/tinymce_editor/js/plugins/aiwriter/plugin.js'
            },
            'paste_as_text': False,
            'paste_data_images': True,
            # TinyMCE 7.0 compatible paste options
            'paste_preprocess': None,  # Custom paste preprocessing if needed
            'paste_postprocess': None,  # Custom paste postprocessing if needed
        }
        
        # Merge with custom config
        config = {**simple_config, **self.config}
        return json.dumps(config) 