"""
Cache headers utilities for static files
"""

def add_cache_headers(headers, path, url):
    """
    Add cache-busting headers for development
    """
    # Disable caching for development
    headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    headers['Pragma'] = 'no-cache'
    headers['Expires'] = '0'
    return headers
