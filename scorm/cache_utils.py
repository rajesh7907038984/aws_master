"""
SCORM Cache Utilities
Enhanced caching for SCORM content with CDN support
"""
import logging
from django.core.cache import cache
from django.conf import settings

logger = logging.getLogger(__name__)


class ScormCacheManager:
    """
    Centralized cache manager for SCORM content
    Provides methods to cache and retrieve SCORM content with CDN support
    """
    
    # Cache prefixes
    PATH_PREFIX = "scorm_s3_path:"
    CONTENT_PREFIX = "scorm_content:"
    PROGRESS_PREFIX = "scorm_progress:"
    ATTEMPT_PREFIX = "scorm_attempt:"
    
    # Cache TTLs (in seconds)
    PATH_TTL = 86400  # 24 hours for S3 paths
    HTML_TTL = 3600   # 1 hour for HTML content
    STATIC_TTL = 604800  # 7 days for static assets
    PROGRESS_TTL = 300  # 5 minutes for progress data
    
    @staticmethod
    def get_cached_path(topic_id, path):
        """Get cached S3 path for a SCORM resource"""
        cache_key = f"{ScormCacheManager.PATH_PREFIX}{topic_id}:{path}"
        return cache.get(cache_key)
    
    @staticmethod
    def set_cached_path(topic_id, path, s3_key, ttl=None):
        """Cache S3 path for a SCORM resource"""
        if ttl is None:
            ttl = ScormCacheManager.PATH_TTL
        
        cache_key = f"{ScormCacheManager.PATH_PREFIX}{topic_id}:{path}"
        cache.set(cache_key, s3_key, ttl)
        logger.info(f"Cached S3 path for {path} -> {s3_key} (TTL: {ttl}s)")
    
    @staticmethod
    def get_cached_content(topic_id, path):
        """Get cached content for a SCORM resource"""
        cache_key = f"{ScormCacheManager.CONTENT_PREFIX}{topic_id}:{path}"
        return cache.get(cache_key)
    
    @staticmethod
    def set_cached_content(topic_id, path, content_data, ttl=None):
        """Cache content for a SCORM resource"""
        if ttl is None:
            # Auto-detect TTL based on file type
            if path.endswith(('.js', '.css', '.jpg', '.jpeg', '.png', '.gif', '.svg')):
                ttl = ScormCacheManager.STATIC_TTL
            else:
                ttl = ScormCacheManager.HTML_TTL
        
        cache_key = f"{ScormCacheManager.CONTENT_PREFIX}{topic_id}:{path}"
        cache.set(cache_key, content_data, ttl)
        logger.info(f"Cached content for {path} ({len(content_data.get('data', ''))} bytes, TTL: {ttl}s)")
    
    @staticmethod
    def invalidate_for_attempt(attempt_id, user_id=None, topic_id=None, course_ids=None):
        """
        Invalidate all relevant caches for a SCORM attempt
        This should be called when an attempt is updated
        """
        keys_to_delete = []
        
        # Attempt-specific caches
        keys_to_delete.append(f"{ScormCacheManager.ATTEMPT_PREFIX}{attempt_id}")
        
        # User-specific progress caches
        if user_id and topic_id:
            keys_to_delete.append(f"{ScormCacheManager.PROGRESS_PREFIX}{user_id}:{topic_id}")
        
        # Course-level gradebook caches
        if course_ids:
            for course_id in course_ids:
                keys_to_delete.append(f"gradebook_course_{course_id}")
        
        # Delete all keys
        cache.delete_many(keys_to_delete)
        logger.info(f"Invalidated {len(keys_to_delete)} cache keys for attempt {attempt_id}")
        
        return len(keys_to_delete)


# CDN Configuration Instructions
CDN_CONFIGURATION = """
# SCORM CDN Configuration

To further optimize SCORM content delivery, configure a CDN with the following settings:

## CloudFront Configuration (Recommended)

1. Create a new CloudFront distribution:
   - Origin: Your S3 bucket
   - Behaviors:
     - Path pattern: /scorm/content/*
     - Cache policy: 
       - Honor origin cache headers
       - Enable compression
       - Query string forwarding: attempt_id only
     - Origin request policy: 
       - Forward all headers
       - CORS support: Yes

2. Cache settings:
   - HTML files: Cache based on headers (1 hour)
   - JS/CSS: Cache based on headers (3 days)
   - Images/fonts: Cache based on headers (7-14 days)
   - Set default TTL to 86400 (1 day)

3. Add custom domain to settings.py:
```python
SCORM_CDN_DOMAIN = 'your-cdn-domain.cloudfront.net'
```

## Nginx Caching (Alternative)

If CloudFront is not available, add these settings to your nginx.conf:

```
# SCORM content caching
location /scorm/content/ {
    proxy_cache scorm_cache;
    proxy_cache_valid 200 302 7d;
    proxy_cache_valid 404 1m;
    proxy_cache_use_stale error timeout updating http_500 http_502 http_503 http_504;
    proxy_cache_bypass $cookie_nocache $arg_nocache;
    proxy_cache_key "$scheme$request_method$host$request_uri$arg_attempt_id";
    proxy_cache_lock on;
    add_header X-Cache-Status $upstream_cache_status;
    
    # Set varying cache times by file type
    location ~* \.(?:jpg|jpeg|gif|png|ico|woff2|woff)$ {
        proxy_cache_valid 200 14d;
        add_header Cache-Control "public, max-age=1209600, immutable";
    }
    
    location ~* \.(?:css|js)$ {
        proxy_cache_valid 200 7d;
        add_header Cache-Control "public, max-age=604800, immutable";
    }
    
    # Pass to Django
    proxy_pass http://localhost:8000;
}
```
"""

def print_cdn_configuration():
    """Print CDN configuration instructions"""
    print(CDN_CONFIGURATION)
