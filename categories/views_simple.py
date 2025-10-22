"""
Simplified category views
Clean, simple implementations
"""
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from .models import CourseCategory
from django.utils.text import slugify
import logging

logger = logging.getLogger(__name__)

@login_required
def simple_category_create(request):
    """
    Simple category creation - clean implementation
    """
    if request.method == 'POST':
        try:
            name = request.POST.get('name', '').strip()
            description = request.POST.get('description', '').strip()
            
            if not name:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Category name is required'
                }, status=400)
            
            # Simple permission check
            if not (request.user.is_superuser or 
                    request.user.role in ['globaladmin', 'superadmin', 'admin', 'instructor']):
                return JsonResponse({
                    'status': 'error',
                    'message': 'Permission denied'
                }, status=403)
            
            # Generate slug
            slug = slugify(name)
            if not slug:
                slug = 'category'
            
            # Ensure unique slug
            base_slug = slug
            counter = 1
            while CourseCategory.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
                if counter > 1000:
                    return JsonResponse({
                        'status': 'error',
                        'message': 'Unable to create unique slug'
                    }, status=400)
            
            # Create category
            category = CourseCategory.objects.create(
                name=name,
                slug=slug,
                description=description,
                is_active=True,
                branch=request.user.branch if hasattr(request.user, 'branch') else None
            )
            
            return JsonResponse({
                'status': 'success',
                'id': category.id,
                'name': category.name,
                'slug': category.slug
            })
            
        except Exception as e:
            logger.error(f"Category creation error: {str(e)}")
            return JsonResponse({
                'status': 'error',
                'message': 'Failed to create category'
            }, status=500)
    
    return JsonResponse({
        'status': 'error',
        'message': 'Invalid request method'
    }, status=400)
