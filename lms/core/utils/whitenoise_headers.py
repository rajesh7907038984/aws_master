"""
WhiteNoise headers utilities for LMS application
"""

def whitenoise_headers(headers, path, url):
    """
    Custom headers function for WhiteNoise to properly handle CSS files
    """
    # Add proper headers for CSS files
    if path.endswith('.css'):
        headers['Content-Type'] = 'text/css; charset=utf-8'
        headers['Cache-Control'] = 'public, max-age=31536000'
        headers['Vary'] = 'Accept-Encoding'
        headers['X-Content-Type-Options'] = 'nosniff'
    
    # Add proper headers for JavaScript files
    elif path.endswith('.js'):
        headers['Content-Type'] = 'application/javascript; charset=utf-8'
        headers['Cache-Control'] = 'public, max-age=31536000'
        headers['Vary'] = 'Accept-Encoding'
    
    # Add proper headers for font files
    elif path.endswith(('.woff', '.woff2', '.ttf', '.eot')):
        headers['Cache-Control'] = 'public, max-age=31536000'
        headers['Access-Control-Allow-Origin'] = '*'
    
    # Add proper headers for images
    elif path.endswith(('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp')):
        headers['Cache-Control'] = 'public, max-age=31536000'
        headers['Vary'] = 'Accept-Encoding'
    
    return headers
