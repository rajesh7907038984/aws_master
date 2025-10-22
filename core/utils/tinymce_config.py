
# Centralized TinyMCE Configuration
TINYMCE_STANDARD_CONFIG = {
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
    'content_style': 'body { font-family:Helvetica,Arial,sans-serif; font-size:14px }',
    'image_advtab': True,
    'image_uploadtab': True,
    'images_upload_url': '/tinymce/upload_image/',
    'automatic_uploads': True,
    'file_picker_types': 'image media',
    'media_upload_url': '/tinymce/upload_media_file/',
    'media_live_embeds': True,
    'media_filter_html': False,
    'external_plugins': {
        'aiwriter': '/static/tinymce_editor/js/plugins/aiwriter/plugin.min.js'
    },
    'branding': False,
    'promotion': False,
    'statusbar': True,
    'resize': True,
    'browser_spellcheck': True,
    'contextmenu': False
}

def get_standard_tinymce_config():
    """Get standardized TinyMCE configuration"""
    return TINYMCE_STANDARD_CONFIG.copy()
