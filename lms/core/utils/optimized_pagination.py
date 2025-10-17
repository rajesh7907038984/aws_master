"""
Optimized Pagination for LMS
===========================

This module provides optimized pagination for large datasets
with intelligent caching and performance monitoring.
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from django.core.paginator import Paginator, Page
from django.db.models import QuerySet
from django.http import HttpRequest
from django.core.cache import cache
from django.utils import timezone
from .cache_manager import cache_manager
from .performance_monitor import PerformanceMonitor

logger = logging.getLogger(__name__)

class OptimizedPaginator:
    """Optimized paginator with caching and performance monitoring"""
    
    def __init__(self, queryset: QuerySet, per_page: int = 25, 
                 cache_key_prefix: str = None, enable_caching: bool = True):
        self.queryset = queryset
        self.per_page = per_page
        self.cache_key_prefix = cache_key_prefix or 'paginated'
        self.enable_caching = enable_caching
        self.performance_monitor = PerformanceMonitor()
    
    def get_page(self, page_number: int, request: HttpRequest = None) -> Page:
        """Get a page with optimization"""
        start_time = timezone.now()
        
        # Try to get from cache first
        if self.enable_caching:
            cached_page = self._get_cached_page(page_number, request)
            if cached_page:
                logger.info(f"Cache hit for page {page_number}")
                return cached_page
        
        # Create paginator
        paginator = Paginator(self.queryset, self.per_page)
        
        # Get the page
        try:
            page = paginator.get_page(page_number)
        except Exception as e:
            logger.error(f"Error getting page {page_number}: {e}")
            page = paginator.get_page(1)
        
        # Cache the page if caching is enabled
        if self.enable_caching:
            self._cache_page(page, page_number, request)
        
        # Log performance
        end_time = timezone.now()
        duration = (end_time - start_time).total_seconds()
        
        if duration > 1.0:  # Log slow pagination
            logger.warning(f"Slow pagination: {duration:.2f}s for page {page_number}")
        
        return page
    
    def _get_cached_page(self, page_number: int, request: HttpRequest = None) -> Optional[Page]:
        """Get cached page"""
        if not request:
            return None
        
        # Create cache key based on user and filters
        cache_key = self._generate_page_cache_key(page_number, request)
        cached_data = cache.get(cache_key)
        
        if cached_data:
            # Reconstruct page object from cached data
            return self._reconstruct_page(cached_data, page_number)
        
        return None
    
    def _cache_page(self, page: Page, page_number: int, request: HttpRequest = None):
        """Cache page data"""
        if not request:
            return
        
        cache_key = self._generate_page_cache_key(page_number, request)
        
        # Prepare data for caching
        cache_data = {
            'object_list': list(page.object_list.values()),
            'number': page.number,
            'paginator': {
                'num_pages': page.paginator.num_pages,
                'count': page.paginator.count,
                'per_page': page.paginator.per_page
            },
            'has_previous': page.has_previous(),
            'has_next': page.has_next(),
            'previous_page_number': page.previous_page_number() if page.has_previous() else None,
            'next_page_number': page.next_page_number() if page.has_next() else None,
            'timestamp': timezone.now().isoformat()
        }
        
        # Cache for 5 minutes
        cache.set(cache_key, cache_data, 300)
        logger.info(f"Cached page {page_number}")
    
    def _generate_page_cache_key(self, page_number: int, request: HttpRequest) -> str:
        """Generate cache key for page"""
        user_id = request.user.id if request.user.is_authenticated else 0
        filters = {
            'page': page_number,
            'per_page': self.per_page,
            'query': request.GET.get('q', ''),
            'category': request.GET.get('category', ''),
            'progress': request.GET.get('progress', ''),
            'instructor': request.GET.get('instructor', ''),
            'sort': request.GET.get('sort', '')
        }
        
        return cache_manager._generate_cache_key(
            self.cache_key_prefix, user_id, filters
        )
    
    def _reconstruct_page(self, cache_data: Dict, page_number: int) -> Page:
        """Reconstruct page object from cached data"""
        # This is a simplified reconstruction
        # In production, you'd want to properly reconstruct the QuerySet
        from django.core.paginator import Paginator
        
        # Create a mock queryset for the page
        class MockQuerySet:
            def __init__(self, objects):
                self.objects = objects
            
            def __getitem__(self, key):
                return self.objects[key]
            
            def __len__(self):
                return len(self.objects)
        
        mock_queryset = MockQuerySet(cache_data['object_list'])
        paginator = Paginator(mock_queryset, cache_data['paginator']['per_page'])
        
        # Create page object
        page = Page(cache_data['object_list'], page_number, paginator)
        return page

class SmartPaginationMixin:
    """Mixin for views with smart pagination"""
    
    def get_pagination_config(self, request: HttpRequest) -> Dict[str, Any]:
        """Get pagination configuration based on request"""
        # Determine per_page based on user role and data size
        user_role = request.user.role if request.user.is_authenticated else 'anonymous'
        
        # Default per_page values by role
        per_page_configs = {
            'globaladmin': 100,
            'superadmin': 50,
            'admin': 25,
            'instructor': 20,
            'learner': 15,
            'anonymous': 10
        }
        
        per_page = per_page_configs.get(user_role, 25)
        
        # Adjust based on request parameters
        requested_per_page = request.GET.get('per_page')
        if requested_per_page:
            try:
                per_page = min(int(requested_per_page), 200)  # Cap at 200
            except (ValueError, TypeError):
                pass
        
        return {
            'per_page': per_page,
            'enable_caching': True,
            'cache_timeout': 300  # 5 minutes
        }
    
    def get_optimized_paginator(self, queryset: QuerySet, request: HttpRequest, 
                               cache_key_prefix: str = None) -> OptimizedPaginator:
        """Get optimized paginator for queryset"""
        config = self.get_pagination_config(request)
        
        return OptimizedPaginator(
            queryset=queryset,
            per_page=config['per_page'],
            cache_key_prefix=cache_key_prefix,
            enable_caching=config['enable_caching']
        )

def optimize_queryset_for_pagination(queryset: QuerySet, max_results: int = 1000) -> QuerySet:
    """Optimize queryset for pagination"""
    # Add select_related for foreign keys
    if hasattr(queryset.model, '_meta'):
        related_fields = [
            field.name for field in queryset.model._meta.get_fields()
            if field.many_to_one and not field.null
        ]
        if related_fields:
            queryset = queryset.select_related(*related_fields[:5])
    
    # Add prefetch_related for many-to-many fields
    many_to_many_fields = [
        field.name for field in queryset.model._meta.get_fields()
        if field.many_to_many
    ]
    if many_to_many_fields:
        queryset = queryset.prefetch_related(*many_to_many_fields[:3])
    
    # Don't slice here - let the paginator handle it
    return queryset

def get_pagination_context(page: Page, request: HttpRequest) -> Dict[str, Any]:
    """Get pagination context for templates"""
    paginator = page.paginator
    
    # Calculate page range for navigation
    current_page = page.number
    total_pages = paginator.num_pages
    
    # Smart page range calculation
    if total_pages <= 10:
        page_range = range(1, total_pages + 1)
    else:
        # Show first 3, last 3, and current page with context
        start = max(1, current_page - 2)
        end = min(total_pages, current_page + 2)
        
        page_range = []
        if start > 1:
            page_range.extend([1, '...'])
        page_range.extend(range(start, end + 1))
        if end < total_pages:
            page_range.extend(['...', total_pages])
    
    return {
        'page': page,
        'page_range': page_range,
        'has_previous': page.has_previous(),
        'has_next': page.has_next(),
        'previous_page_number': page.previous_page_number() if page.has_previous() else None,
        'next_page_number': page.next_page_number() if page.has_next() else None,
        'total_pages': total_pages,
        'total_count': paginator.count,
        'per_page': paginator.per_page,
        'current_page': current_page
    }
