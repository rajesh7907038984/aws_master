from django.conf import settings

# Default settings for TinyMCE
DEFAULT_CONFIG = {
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
              'removeformat | image media | aiwriter',
    'content_style': 'body { font-family:Helvetica,Arial,sans-serif; font-size:14px }',
    'image_advtab': True,
    'image_uploadtab': True,
    'images_upload_url': '/tinymce/upload_image/',
    'automatic_uploads': True,
    'file_picker_types': 'image media',
    'media_upload_url': '/tinymce/upload_media_file/',
    'media_live_embeds': True,
    'external_plugins': {
        'aiwriter': '/static/tinymce_editor/js/plugins/aiwriter/plugin.min.js'
    }
}

# Anthropic API settings
ANTHROPIC_API_KEY = getattr(settings, 'ANTHROPIC_API_KEY', None)
ANTHROPIC_MODEL = getattr(settings, 'ANTHROPIC_MODEL', 'claude-3-5-sonnet-20241022')
ANTHROPIC_MAX_TOKENS = getattr(settings, 'ANTHROPIC_MAX_TOKENS', 1000)

# Override settings from Django project settings
TINYMCE_DEFAULT_CONFIG = getattr(settings, 'TINYMCE_DEFAULT_CONFIG', DEFAULT_CONFIG)
TINYMCE_UPLOAD_PATH = getattr(settings, 'TINYMCE_UPLOAD_PATH', 'tinymce_uploads/')
TINYMCE_MEDIA_UPLOAD_PATH = getattr(settings, 'TINYMCE_MEDIA_UPLOAD_PATH', 'tinymce_media_uploads/') 