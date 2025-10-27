from django.shortcuts import render
import os
import uuid
import json
import requests
import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_protect, csrf_exempt
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.views.decorators.http import require_POST, require_http_methods
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
import magic
from . import settings as tinymce_settings
from .models import BranchAITokenLimit, AITokenUsage

# Set up logging
logger = logging.getLogger(__name__)

# Create your views here.

@login_required
@require_POST
@ensure_csrf_cookie
def upload_image(request):
    """
    Handle image uploads from TinyMCE editor.
    Returns JSON with location URL of the uploaded image.
    """
    if 'file' not in request.FILES:
        logger.error("Image upload failed: No file uploaded")
        return JsonResponse({
            'error': 'No file uploaded'
        }, status=400)
    
    uploaded_file = request.FILES['file']
    logger.info(f"Received image upload: {uploaded_file.name}, size: {uploaded_file.size}, type: {uploaded_file.content_type}")
    
    # Validate file type using both MIME type and file signature
    allowed_types = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
    if uploaded_file.content_type not in allowed_types:
        logger.warning(f"Image upload rejected: File type not allowed: {uploaded_file.content_type}")
        return JsonResponse({
            'error': 'File type not allowed. Please upload JPEG, PNG, GIF, or WebP.'
        }, status=400)
    
    # Validate actual file content using python-magic
    try:
        file_signature = magic.from_buffer(uploaded_file.read(1024), mime=True)
        uploaded_file.seek(0)  # Reset file pointer
        
        if file_signature not in allowed_types:
            logger.warning(f"Image upload rejected: File signature mismatch. MIME: {uploaded_file.content_type}, Signature: {file_signature}")
            return JsonResponse({
                'error': 'File content does not match declared type.'
            }, status=400)
    except Exception as e:
        logger.error(f"Error validating file signature: {str(e)}")
        return JsonResponse({
            'error': 'Unable to validate file content.'
        }, status=400)
    
    # Validate file size (max 10MB to match frontend validation)
    max_size = 10 * 1024 * 1024  # 10MB in bytes
    if uploaded_file.size > max_size:
        logger.warning(f"Image upload rejected: File too large: {uploaded_file.size} bytes")
        return JsonResponse({
            'error': 'File too large. Maximum size is 10MB.'
        }, status=400)
    
    # Preserve original extension but sanitize filename
    original_name = uploaded_file.name
    file_ext = os.path.splitext(original_name)[1].lower()
    
    # Additional extension validation
    allowed_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp']
    if file_ext not in allowed_extensions:
        return JsonResponse({
            'error': f'File extension {file_ext} not allowed.'
        }, status=400)
    
    timestamp = uuid.uuid4().hex[:8]
    
    # Create a sanitized filename that preserves original name but adds uniqueness
    sanitized_name = ''.join(c for c in os.path.splitext(original_name)[0] if c.isalnum() or c in '-_')
    sanitized_name = sanitized_name[:50]  # Limit length
    unique_filename = f"{timestamp}_{sanitized_name}{file_ext}"
    
    # Define upload path - either use a specific TINYMCE_UPLOAD_PATH or default
    upload_path = tinymce_settings.TINYMCE_UPLOAD_PATH
    
    # Ensure the path ends with a slash
    if not upload_path.endswith('/'):
        upload_path += '/'
    
    # Full path for the file
    file_path = os.path.join(upload_path, unique_filename)
    logger.info(f"Saving uploaded image to: {file_path}")
    
    try:
        # Save file using Django's storage API
        saved_path = default_storage.save(file_path, ContentFile(uploaded_file.read()))
        
        # Register the file upload in storage tracking system
        try:
            from core.utils.storage_manager import StorageManager
            StorageManager.register_file_upload(
                user=request.user,
                file_path=saved_path,
                original_filename=original_name,
                file_size_bytes=uploaded_file.size,
                content_type=uploaded_file.content_type,
                source_app='tinymce_editor',
                source_model='Image',
            )
        except Exception as e:
            logger.error(f"Error registering file in storage tracking: {str(e)}")
            # Continue with upload even if registration fails
        
        # Generate URL for the saved file
        file_url = default_storage.url(saved_path)
        logger.info(f"Image saved successfully at URL: {file_url}")
        
        # Return success response with URL
        return JsonResponse({
            'location': file_url,  # For TinyMCE 5.x compatibility
            'url': file_url,       # For TinyMCE 6.x compatibility
            'filename': unique_filename,
            'alt': os.path.splitext(original_name)[0],  # Use original filename as alt text
            'title': os.path.splitext(original_name)[0],  # Use original filename as title
            'success': True
        })
    except Exception as e:
        logger.error(f"Error saving uploaded image: {str(e)}")
        return JsonResponse({
            'error': f'Error saving file: {str(e)}',
            'success': False
        }, status=500)

@login_required
@require_POST
@ensure_csrf_cookie
def upload_media_file(request):
    """
    Handle media file uploads from TinyMCE editor.
    Returns JSON with location URL of the uploaded file.
    """
    if 'file' not in request.FILES:
        return JsonResponse({
            'error': 'No file uploaded'
        }, status=400)
    
    uploaded_file = request.FILES['file']
    
    # Validate file type
    allowed_types = [
        # Images
        'image/jpeg', 'image/png', 'image/gif', 'image/webp',
        # Audio
        'audio/mpeg', 'audio/ogg', 'audio/wav', 
        # Video
        'video/mp4', 'video/webm', 'video/ogg',
        # Documents
        'application/pdf', 'application/msword', 
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'application/vnd.ms-excel',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'application/vnd.ms-powerpoint',
        'application/vnd.openxmlformats-officedocument.presentationml.presentation',
        # Other common types
        'text/plain', 'application/zip', 'application/octet-stream', 'application/x-zip-compressed'
    ]
    
    if uploaded_file.content_type not in allowed_types:
        return JsonResponse({
            'error': 'File type not allowed. Please upload a supported file type.'
        }, status=400)
    
    # Validate actual file content using python-magic
    try:
        file_signature = magic.from_buffer(uploaded_file.read(1024), mime=True)
        uploaded_file.seek(0)  # Reset file pointer
        
        # Allow common MIME type variations for ZIP files
        if file_signature not in allowed_types:
            # Check if this is a ZIP file variation
            if (uploaded_file.content_type == 'application/zip' and 
                file_signature in ['application/octet-stream', 'application/x-zip-compressed']):
                # This is acceptable - ZIP files are often detected as octet-stream
                pass
            elif (file_signature == 'application/zip' and 
                  uploaded_file.content_type in ['application/octet-stream', 'application/x-zip-compressed']):
                # Also acceptable - reverse case
                pass
            else:
                logger.warning(f"Media upload rejected: File signature mismatch. MIME: {uploaded_file.content_type}, Signature: {file_signature}")
                return JsonResponse({
                    'error': 'File content does not match declared type.'
                }, status=400)
    except Exception as e:
        logger.error(f"Error validating file signature: {str(e)}")
        return JsonResponse({
            'error': 'Unable to validate file content.'
        }, status=400)
    
    # Validate file size based on file type
    # Default max size: 20MB for most files, 100MB for videos, 600MB for SCORM packages
    file_ext = os.path.splitext(uploaded_file.name)[1].lower()
    
    # Video file extensions
    video_extensions = ['.mp4', '.mov', '.avi', '.wmv', '.mkv', '.webm', '.flv', '.m4v']
    
    if file_ext == '.zip':
        # SCORM packages or archives - allow up to 600MB
        max_size = 600 * 1024 * 1024  # 600MB in bytes
        size_description = "600MB"
    elif file_ext in video_extensions:
        # Video files - 600MB limit
        max_size = 600 * 1024 * 1024  # 600MB in bytes
        size_description = "600MB"
    else:
        # Regular media files - 600MB limit
        max_size = 600 * 1024 * 1024  # 600MB in bytes
        size_description = "600MB"
    
    if uploaded_file.size > max_size:
        return JsonResponse({
            'error': f'File too large. Maximum size is {size_description}.'
        }, status=400)
    
    # Preserve original extension but sanitize filename
    original_name = uploaded_file.name
    file_ext = os.path.splitext(original_name)[1].lower()
    timestamp = uuid.uuid4().hex[:8]
    
    # Create a sanitized filename that preserves original name but adds uniqueness
    sanitized_name = ''.join(c for c in os.path.splitext(original_name)[0] if c.isalnum() or c in '-_')
    sanitized_name = sanitized_name[:50]  # Limit length
    unique_filename = f"{timestamp}_{sanitized_name}{file_ext}"
    
    # Define upload path - either use a specific path for media or default
    upload_path = getattr(tinymce_settings, 'TINYMCE_MEDIA_UPLOAD_PATH', 
                          tinymce_settings.TINYMCE_UPLOAD_PATH)
    
    # Ensure the path ends with a slash
    if not upload_path.endswith('/'):
        upload_path += '/'
    
    # Full path for the file
    file_path = os.path.join(upload_path, unique_filename)
    
    try:
        # Save file using Django's storage API
        saved_path = default_storage.save(file_path, ContentFile(uploaded_file.read()))
        
        # Register file in media database for tracking
        try:
            from lms_media.utils import register_media_file
            register_media_file(
                file_path=saved_path,
                uploaded_by=request.user,
                source_type='editor_upload',
                filename=original_name,
                description=f'Uploaded via TinyMCE editor on {timezone.now().date()}'
            )
        except ImportError:
            # lms_media module not available, skip registration
            pass
        except Exception as e:
            logger.error(f"Error registering media file: {str(e)}")
            # Continue with upload even if registration fails
        
        # Register file in storage tracking system
        try:
            from core.utils.storage_manager import StorageManager
            StorageManager.register_file_upload(
                user=request.user,
                file_path=saved_path,
                original_filename=original_name,
                file_size_bytes=uploaded_file.size,
                content_type=uploaded_file.content_type,
                source_app='tinymce_editor',
                source_model='MediaFile',
            )
        except Exception as e:
            logger.error(f"Error registering file in storage tracking: {str(e)}")
            # Continue with upload even if registration fails
        
        # Generate URL for the saved file
        file_url = default_storage.url(saved_path)
        
        # Return success response with URL
        return JsonResponse({
            'location': file_url,  # For TinyMCE 5.x compatibility
            'url': file_url,       # For TinyMCE 6.x compatibility
            'filename': unique_filename,
            'title': os.path.splitext(original_name)[0],
            'success': True
        })
    except Exception as e:
        logger.error(f"Error saving uploaded media file: {str(e)}")
        return JsonResponse({
            'error': f'Error saving file: {str(e)}',
            'success': False
        }, status=500)

@login_required
@require_POST
@csrf_protect
def generate_ai_content(request):
    """
    Generate content using the Anthropic Claude API with token limit checking.
    Returns JSON with the generated content.
    """
    try:
        # Log request details for debugging
        logger.info(f"AI content generation request from user: {request.user.username}")
        logger.info(f"Request method: {request.method}")
        logger.info(f"Content type: {request.content_type}")
        
        # Parse request body
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in request body: {str(e)}")
            return JsonResponse({
                'error': 'Invalid JSON in request body',
                'success': False
            }, status=400)
        
        prompt = data.get('prompt', '').strip()
        
        if not prompt:
            logger.warning("AI content generation: No prompt provided")
            return JsonResponse({
                'error': 'No prompt provided',
                'success': False
            }, status=400)
        
        logger.info(f"AI prompt received: {prompt[:100]}...")  # Log first 100 chars
        
        # Get API key and configuration from database first, then fallback to settings
        # This needs to be done early so max_tokens is available for token limit calculations
        api_key = None
        model = None
        max_tokens = None
        
        try:
            from account_settings.models import GlobalAdminSettings
            global_settings = GlobalAdminSettings.get_settings()
            if global_settings.anthropic_ai_enabled and global_settings.anthropic_api_key:
                api_key = global_settings.anthropic_api_key
                model = global_settings.anthropic_model
                max_tokens = global_settings.anthropic_max_tokens
                logger.info(f"Using Anthropic AI configuration from database")
        except Exception as e:
            logger.warning(f"Could not load Anthropic AI settings from database: {str(e)}")
        
        # Fallback to Django settings if database config not available
        if not api_key:
            api_key = getattr(settings, 'ANTHROPIC_API_KEY', None)
            model = getattr(settings, 'ANTHROPIC_MODEL', 'claude-3-5-sonnet-20241022')
            max_tokens = getattr(settings, 'ANTHROPIC_MAX_TOKENS', 1000)
            logger.info(f"Using Anthropic AI configuration from Django settings")
        
        # Ensure max_tokens has a default value
        if max_tokens is None:
            max_tokens = 1000
        
        # Check if user has a branch (required for token limits)
        if not request.user.branch:
            logger.warning(f"User {request.user.username} has no branch assigned")
            return JsonResponse({
                'error': 'Your account is not associated with a branch. Please contact your administrator.',
                'success': False
            }, status=403)
        
        # Check token limits for the user's branch
        try:
            branch_limits, created = BranchAITokenLimit.objects.get_or_create(
                branch=request.user.branch,
                defaults={
                    'monthly_token_limit': 10000,  # Default limit
                    'is_unlimited': False
                }
            )
            
            if created:
                logger.info(f"Created default AI token limits for branch: {request.user.branch.name}")
            
            # Check if branch has unlimited tokens (Global Admin privilege)  
            if not branch_limits.is_unlimited:
                # Estimate tokens needed for this request (prompt + expected response)
                estimated_prompt_tokens = AITokenUsage.estimate_tokens_from_text(prompt)
                estimated_response_tokens = max_tokens or 1000  # Use configured max_tokens or default
                estimated_total_tokens = estimated_prompt_tokens + estimated_response_tokens
                
                # Check current usage
                current_usage = branch_limits.get_current_month_usage()
                remaining_tokens = branch_limits.get_remaining_tokens()
                
                # Check if this request would exceed the limit
                if current_usage >= branch_limits.monthly_token_limit:
                    logger.warning(f"Token limit exceeded for branch {request.user.branch.name}: {current_usage}/{branch_limits.monthly_token_limit}")
                    return JsonResponse({
                        'error': 'Your token limit has been exceeded. Please contact your administrator to increase the limit.',
                        'success': False,
                        'token_limit_exceeded': True,
                        'current_usage': current_usage,
                        'monthly_limit': branch_limits.monthly_token_limit,
                        'usage_percentage': branch_limits.get_usage_percentage()
                    }, status=429)
                
                # Warn if usage is high (>90%) but allow the request
                usage_percentage = branch_limits.get_usage_percentage()
                if usage_percentage > 90:
                    logger.warning(f"High token usage for branch {request.user.branch.name}: {usage_percentage:.1f}%")
                
            logger.info(f"Token limit check passed for branch: {request.user.branch.name}")
            
        except Exception as e:
            logger.error(f"Error checking token limits: {str(e)}")
            # Continue with request but log the error
        
        # More thorough API key validation (API key and config already loaded above)
        if not api_key:
            logger.error("ANTHROPIC_API_KEY not configured in database or Django settings")
            return JsonResponse({
                'error': 'AI service not configured - missing API key. Please configure via Global Admin Settings.',
                'success': False
            }, status=503)
        
        if api_key.startswith('sk-ant-api01-sample'):
            logger.error("Using sample API key - not valid for production")
            return JsonResponse({
                'error': 'Using sample API key - please configure a real Anthropic API key',
                'success': False
            }, status=503)
        
        # Validate API key format - should start with sk-ant-
        if not api_key.startswith('sk-ant-'):
            logger.error(f"Invalid ANTHROPIC_API_KEY format: {api_key[:8]}...")
            return JsonResponse({
                'error': 'AI service not properly configured - invalid API key format',
                'success': False
            }, status=503)
        
        logger.info(f"Using Anthropic model: {model}")
        
        logger.info("Making request to Anthropic API...")
        
        # Prepare request payload
        request_payload = {
            'model': model,
            'max_tokens': max_tokens,
            'messages': [
                {
                    'role': 'user',
                    'content': prompt
                }
            ]
        }
        
        # Track token usage (before API call for error cases)
        tokens_used = 0
        api_success = False
        api_error_message = None
        generated_text = ""
        
        # Make request to Anthropic API with timeout
        try:
            response = requests.post(
                'https://api.anthropic.com/v1/messages',
                headers={
                    'Content-Type': 'application/json',
                    'x-api-key': api_key,
                    'anthropic-version': '2023-06-01'
                },
                json=request_payload,
                timeout=30  # 30 second timeout
            )
            
            logger.info(f"Anthropic API response status: {response.status_code}")
            
            # Check if request was successful
            if response.status_code != 200:
                error_text = response.text[:500]  # Limit error text length
                logger.error(f"Anthropic API error {response.status_code}: {error_text}")
                api_error_message = f"API Error {response.status_code}: {error_text}"
                
                # Handle specific error cases
                if response.status_code == 401:
                    error_msg = 'AI service authentication failed. Please check API key configuration.'
                elif response.status_code == 429:
                    error_msg = 'AI service rate limit exceeded. Please try again later.'
                elif response.status_code == 400:
                    error_msg = 'Invalid request to AI service. Please try a different prompt.'
                else:
                    error_msg = f'AI service error ({response.status_code}): {error_text}'
                
                # Record failed usage
                AITokenUsage.objects.create(
                    user=request.user,
                    tokens_used=AITokenUsage.estimate_tokens_from_text(prompt),  # Count prompt tokens at least
                    prompt_text=prompt,
                    response_length=0,
                    model_used=model,
                    success=False,
                    error_message=api_error_message
                )
                
                return JsonResponse({
                    'error': error_msg,
                    'success': False
                }, status=500)
            
            # Parse successful response
            try:
                result = response.json()
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON response from Anthropic API: {str(e)}")
                api_error_message = f"Invalid JSON response: {str(e)}"
                
                # Record failed usage
                AITokenUsage.objects.create(
                    user=request.user,
                    tokens_used=AITokenUsage.estimate_tokens_from_text(prompt),
                    prompt_text=prompt,
                    response_length=0,
                    model_used=model,
                    success=False,
                    error_message=api_error_message
                )
                
                return JsonResponse({
                    'error': 'Invalid response from AI service',
                    'success': False
                }, status=500)
            
            content = result.get('content', [])
            logger.info(f"Received {len(content)} content blocks from Anthropic API")
            
            # Extract text from the content blocks
            generated_text = ""
            for block in content:
                if block.get('type') == 'text':
                    generated_text += block.get('text', '')
            
            if not generated_text:
                logger.warning("No text content generated by Anthropic API")
                api_error_message = "No text content in API response"
                
                # Record failed usage
                AITokenUsage.objects.create(
                    user=request.user,
                    tokens_used=AITokenUsage.estimate_tokens_from_text(prompt),
                    prompt_text=prompt,
                    response_length=0,
                    model_used=model,
                    success=False,
                    error_message=api_error_message
                )
                
                return JsonResponse({
                    'error': 'No content generated by AI service',
                    'success': False
                }, status=500)
            
            api_success = True
            
            # Calculate actual tokens used (estimate from prompt + response)
            prompt_tokens = AITokenUsage.estimate_tokens_from_text(prompt)
            response_tokens = AITokenUsage.estimate_tokens_from_text(generated_text)
            tokens_used = prompt_tokens + response_tokens
            
            # Get usage from API response if available
            usage_info = result.get('usage', {})
            if usage_info:
                input_tokens = usage_info.get('input_tokens', prompt_tokens)
                output_tokens = usage_info.get('output_tokens', response_tokens)
                tokens_used = input_tokens + output_tokens
                logger.info(f"Actual token usage from API: {input_tokens} input + {output_tokens} output = {tokens_used} total")
            
            logger.info(f"Generated content length: {len(generated_text)} characters, Estimated tokens: {tokens_used}")
            
        except requests.exceptions.Timeout:
            logger.error("Anthropic API request timed out")
            api_error_message = "API request timeout"
            
            # Record failed usage
            AITokenUsage.objects.create(
                user=request.user,
                tokens_used=AITokenUsage.estimate_tokens_from_text(prompt),
                prompt_text=prompt,
                response_length=0,
                model_used=model,
                success=False,
                error_message=api_error_message
            )
            
            return JsonResponse({
                'error': 'AI service request timed out. Please try again.',
                'success': False
            }, status=504)
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Connection error to Anthropic API: {str(e)}")
            api_error_message = f"Connection error: {str(e)}"
            
            # Record failed usage
            AITokenUsage.objects.create(
                user=request.user,
                tokens_used=AITokenUsage.estimate_tokens_from_text(prompt),
                prompt_text=prompt,
                response_length=0,
                model_used=model,
                success=False,
                error_message=api_error_message
            )
            
            return JsonResponse({
                'error': 'Unable to connect to AI service. Please check your internet connection.',
                'success': False
            }, status=503)
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error to Anthropic API: {str(e)}")
            api_error_message = f"Request error: {str(e)}"
            
            # Record failed usage
            AITokenUsage.objects.create(
                user=request.user,
                tokens_used=AITokenUsage.estimate_tokens_from_text(prompt),
                prompt_text=prompt,
                response_length=0,
                model_used=model,
                success=False,
                error_message=api_error_message
            )
            
            return JsonResponse({
                'error': f'Network error: {str(e)}',
                'success': False
            }, status=503)
        
        # Record successful usage
        if api_success:
            try:
                AITokenUsage.objects.create(
                    user=request.user,
                    tokens_used=tokens_used,
                    prompt_text=prompt,
                    response_length=len(generated_text),
                    model_used=model,
                    success=True
                )
                logger.info(f"Recorded AI token usage: {tokens_used} tokens for user {request.user.username}")
            except Exception as e:
                logger.error(f"Failed to record token usage: {str(e)}")
                # Continue with response even if tracking fails
        
        # Process the generated text to ensure proper paragraph formatting
        paragraphs = generated_text.split('\n\n')
        formatted_content = ""
        
        for paragraph in paragraphs:
            # Skip empty paragraphs
            if not paragraph.strip():
                continue
                
            # Check if paragraph contains line breaks
            if '\n' in paragraph:
                # Handle lists and other multi-line content
                lines = paragraph.split('\n')
                formatted_lines = []
                
                for line in lines:
                    if line.strip():
                        formatted_lines.append(f'<div style="margin: 0; line-height: 1.5;">{line}</div>')
                
                formatted_content += ''.join(formatted_lines)
            else:
                # Regular paragraph
                formatted_content += f'<p style="margin: 0 0 1em 0; line-height: 1.5;">{paragraph}</p>'
        
        logger.info("AI content generation completed successfully")
        
        # Get updated usage stats for response
        try:
            updated_branch_limits = BranchAITokenLimit.objects.get(branch=request.user.branch)
            current_usage = updated_branch_limits.get_current_month_usage()
            usage_percentage = updated_branch_limits.get_usage_percentage()
            remaining_tokens = updated_branch_limits.get_remaining_tokens()
        except:
            current_usage = 0
            usage_percentage = 0
            remaining_tokens = float('inf')
        
        # Return the properly formatted content with usage stats
        response_data = {
            'content': formatted_content,
            'success': True,
            'tokens_used': tokens_used,
            'current_usage': current_usage,
            'usage_percentage': round(usage_percentage, 1),
        }
        
        # Only include limit info if not unlimited
        if not getattr(updated_branch_limits, 'is_unlimited', False):
            response_data['monthly_limit'] = updated_branch_limits.monthly_token_limit
            response_data['remaining_tokens'] = remaining_tokens
        
        return JsonResponse(response_data)
        
    except Exception as e:
        logger.error(f"Unexpected error in generate_ai_content: {str(e)}", exc_info=True)
        
        # Try to record the error
        try:
            AITokenUsage.objects.create(
                user=request.user,
                response_length=0,
                model_used=getattr(tinymce_settings, 'ANTHROPIC_MODEL', 'claude-3-opus-20240229'),
                success=False,
                error_message=f"Unexpected error: {str(e)}"
            )
        except:
            pass  # Don't fail if we can't record the error
        
        return JsonResponse({
            'error': f'Unexpected error: {str(e)}',
            'success': False
        }, status=500)


# AI Token Management Views for Global Admins
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Sum, Count
from branches.models import Branch
from django.contrib.auth.decorators import user_passes_test


def is_global_admin(user):
    """Check if user is a global admin"""
    return user.is_authenticated and user.role == 'globaladmin'


@login_required
@user_passes_test(is_global_admin)
def ai_token_dashboard(request):
    """Dashboard for AI token management - for global admins only"""
    try:
        # Get all branches with their token limits
        branches = Branch.objects.select_related('business').prefetch_related('ai_token_limits').filter(is_active=True)
        
        # Get search parameters
        search_query = request.GET.get('search', '')
        business_filter = request.GET.get('business', '')
        
        # Apply filters
        if search_query:
            branches = branches.filter(
                Q(name__icontains=search_query) |
                Q(business__name__icontains=search_query)
            )
        
        if business_filter:
            branches = branches.filter(business__id=business_filter)
        
        # Get business list for filter dropdown
        businesses = Branch.objects.select_related('business').values('business__id', 'business__name').distinct().order_by('business__name')
        
        # Prepare branch data with usage statistics
        branch_data = []
        total_branches = 0
        unlimited_branches = 0
        total_monthly_limit = 0
        total_current_usage = 0
        
        for branch in branches:
            try:
                # Get or create token limits for this branch
                token_limits, created = BranchAITokenLimit.objects.get_or_create(
                    branch=branch,
                    defaults={'monthly_token_limit': 10000, 'is_unlimited': False}
                )
                
                current_usage = token_limits.get_current_month_usage()
                usage_percentage = token_limits.get_usage_percentage()
                remaining_tokens = token_limits.get_remaining_tokens()
                
                # Get user count for this branch
                user_count = branch.users.filter(is_active=True).count()
                
                branch_info = {
                    'branch': branch,
                    'token_limits': token_limits,
                    'current_usage': current_usage,
                    'usage_percentage': usage_percentage,
                    'remaining_tokens': remaining_tokens if not token_limits.is_unlimited else float('inf'),
                    'user_count': user_count,
                    'status': 'unlimited' if token_limits.is_unlimited else ('exceeded' if token_limits.is_limit_exceeded() else ('warning' if usage_percentage > 80 else 'normal'))
                }
                
                branch_data.append(branch_info)
                
                # Aggregate statistics
                total_branches += 1
                if token_limits.is_unlimited:
                    unlimited_branches += 1
                else:
                    total_monthly_limit += token_limits.monthly_token_limit
                    total_current_usage += current_usage
                    
            except Exception as e:
                logger.error(f"Error processing branch {branch.name}: {str(e)}")
                continue
        
        # Pagination
        paginator = Paginator(branch_data, 20)  # 20 branches per page
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)
        
        # Overall statistics
        overall_usage_percentage = (total_current_usage / total_monthly_limit) * 100 if total_monthly_limit > 0 else 0
        
        context = {
            'page_obj': page_obj,
            'businesses': businesses,
            'search_query': search_query,
            'business_filter': business_filter,
            'total_branches': total_branches,
            'unlimited_branches': unlimited_branches,
            'limited_branches': total_branches - unlimited_branches,
            'total_monthly_limit': total_monthly_limit,
            'total_current_usage': total_current_usage,
            'overall_usage_percentage': round(overall_usage_percentage, 1),
        }
        
        return render(request, 'tinymce_editor/ai_token_dashboard.html', context)
        
    except Exception as e:
        logger.error(f"Error in ai_token_dashboard: {str(e)}", exc_info=True)
        messages.error(request, f"Error loading AI token dashboard: {str(e)}")
        return redirect('admin:index')


@login_required
@user_passes_test(is_global_admin)
def manage_branch_tokens(request, branch_id):
    """Manage AI token limits for a specific branch"""
    try:
        branch = get_object_or_404(Branch, id=branch_id)
        
        # Get or create token limits for this branch
        token_limits, created = BranchAITokenLimit.objects.get_or_create(
            branch=branch,
            defaults={'monthly_token_limit': 10000, 'is_unlimited': False}
        )
        
        if request.method == 'POST':
            # Handle form submission
            action = request.POST.get('action')
            
            if action == 'update_limits':
                try:
                    is_unlimited = request.POST.get('is_unlimited') == 'on'
                    monthly_limit = int(request.POST.get('monthly_token_limit', 10000))
                    
                    if not is_unlimited and monthly_limit <= 0:
                        messages.error(request, "Monthly token limit must be greater than 0 if not unlimited.")
                    else:
                        token_limits.is_unlimited = is_unlimited
                        token_limits.monthly_token_limit = monthly_limit
                        token_limits.updated_by = request.user
                        token_limits.save()
                        
                        limit_text = "unlimited" if is_unlimited else f"{monthly_limit:,} tokens/month"
                        messages.success(request, f"AI token limit for {branch.name} updated to {limit_text}.")
                        
                except ValueError:
                    messages.error(request, "Invalid token limit value.")
                except Exception as e:
                    logger.error(f"Error updating token limits: {str(e)}")
                    messages.error(request, f"Error updating token limits: {str(e)}")
            
            return redirect('tinymce_editor:manage_branch_tokens', branch_id=branch_id)
        
        # Get usage statistics for current month
        current_usage = token_limits.get_current_month_usage()
        usage_percentage = token_limits.get_usage_percentage()
        remaining_tokens = token_limits.get_remaining_tokens()
        
        # Get recent usage data (last 30 days)
        from datetime import timedelta
        thirty_days_ago = timezone.now() - timedelta(days=30)
        
        recent_usage = AITokenUsage.objects.filter(
            user__branch=branch,
            created_at__gte=thirty_days_ago
        ).order_by('-created_at')[:50]  # Last 50 requests
        
        # Get top users by token usage this month
        now = timezone.now()
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        top_users = AITokenUsage.objects.filter(
            user__branch=branch,
            created_at__gte=start_of_month
        ).values('user__username', 'user__email', 'user__id').annotate(
            total_tokens=Sum('tokens_used'),
            request_count=Count('id')
        ).order_by('-total_tokens')[:10]
        
        # Get daily usage for the current month (for chart)
        daily_usage = AITokenUsage.objects.filter(
            user__branch=branch,
            created_at__gte=start_of_month
        ).extra(
            select={'day': 'DATE(created_at)'}
        ).values('day').annotate(
            total_tokens=Sum('tokens_used'),
            request_count=Count('id')
        ).order_by('day')
        
        context = {
            'branch': branch,
            'token_limits': token_limits,
            'current_usage': current_usage,
            'usage_percentage': round(usage_percentage, 1),
            'remaining_tokens': remaining_tokens if not token_limits.is_unlimited else float('inf'),
            'recent_usage': recent_usage,
            'top_users': top_users,
            'daily_usage': list(daily_usage),
            'user_count': branch.users.filter(is_active=True).count(),
        }
        
        return render(request, 'tinymce_editor/manage_branch_tokens.html', context)
        
    except Exception as e:
        logger.error(f"Error in manage_branch_tokens: {str(e)}", exc_info=True)
        messages.error(request, f"Error managing branch tokens: {str(e)}")
        return redirect('tinymce_editor:ai_token_dashboard')


@login_required
@user_passes_test(is_global_admin)
def bulk_update_tokens(request):
    """Bulk update token limits for multiple branches"""
    if request.method == 'POST':
        try:
            action = request.POST.get('action')
            branch_ids = request.POST.getlist('selected_branches')
            
            if not branch_ids:
                messages.error(request, "No branches selected.")
                return redirect('tinymce_editor:ai_token_dashboard')
            
            branches = Branch.objects.filter(id__in=branch_ids)
            updated_count = 0
            
            if action == 'set_unlimited':
                # Set selected branches to unlimited
                for branch in branches:
                    token_limits, created = BranchAITokenLimit.objects.get_or_create(
                        branch=branch,
                        defaults={'monthly_token_limit': 10000, 'is_unlimited': False}
                    )
                    token_limits.is_unlimited = True
                    token_limits.updated_by = request.user
                    token_limits.save()
                    updated_count += 1
                
                messages.success(request, f"Set {updated_count} branches to unlimited AI tokens.")
                
            elif action == 'set_limit':
                # Set custom limit for selected branches
                try:
                    new_limit = int(request.POST.get('new_limit', 10000))
                    if new_limit <= 0:
                        messages.error(request, "Token limit must be greater than 0.")
                        return redirect('tinymce_editor:ai_token_dashboard')
                    
                    for branch in branches:
                        token_limits, created = BranchAITokenLimit.objects.get_or_create(
                            branch=branch,
                            defaults={'monthly_token_limit': 10000, 'is_unlimited': False}
                        )
                        token_limits.is_unlimited = False
                        token_limits.monthly_token_limit = new_limit
                        token_limits.updated_by = request.user
                        token_limits.save()
                        updated_count += 1
                    
                    messages.success(request, f"Set {updated_count} branches to {new_limit:,} tokens per month.")
                    
                except ValueError:
                    messages.error(request, "Invalid token limit value.")
                    
            else:
                messages.error(request, "Invalid action.")
                
        except Exception as e:
            logger.error(f"Error in bulk_update_tokens: {str(e)}", exc_info=True)
            messages.error(request, f"Error updating token limits: {str(e)}")
    
    return redirect('tinymce_editor:ai_token_dashboard')


@login_required
def check_token_status(request):
    """API endpoint to check current token status for user's branch"""
    try:
        if not request.user.branch:
            return JsonResponse({
                'error': 'No branch assigned to user',
                'success': False
            }, status=403)
        
        # Get or create token limits for user's branch
        token_limits, created = BranchAITokenLimit.objects.get_or_create(
            branch=request.user.branch,
            defaults={'monthly_token_limit': 10000, 'is_unlimited': False}
        )
        
        current_usage = token_limits.get_current_month_usage()
        usage_percentage = token_limits.get_usage_percentage()
        remaining_tokens = token_limits.get_remaining_tokens()
        
        # Determine status
        if token_limits.is_unlimited:
            status = 'unlimited'
        elif token_limits.is_limit_exceeded():
            status = 'exceeded'
        elif usage_percentage > 90:
            status = 'critical'
        elif usage_percentage > 75:
            status = 'warning'
        else:
            status = 'normal'
        
        return JsonResponse({
            'success': True,
            'is_unlimited': token_limits.is_unlimited,
            'monthly_limit': token_limits.monthly_token_limit,
            'current_usage': current_usage,
            'remaining_tokens': remaining_tokens if not token_limits.is_unlimited else -1,
            'usage_percentage': round(usage_percentage, 1),
            'status': status,
            'limit_exceeded': token_limits.is_limit_exceeded(),
        })
        
    except Exception as e:
        logger.error(f"Error in check_token_status: {str(e)}", exc_info=True)
        return JsonResponse({
            'error': f'Error checking token status: {str(e)}',
            'success': False
        }, status=500)


@login_required
@user_passes_test(is_global_admin)
def get_branch_token_data(request, branch_id):
    """
    AJAX endpoint to get token data for a specific branch (JSON response for modal)
    """
    try:
        branch = get_object_or_404(Branch, id=branch_id)
        
        # Get or create token limits for this branch
        token_limits, created = BranchAITokenLimit.objects.get_or_create(
            branch=branch,
            defaults={'monthly_token_limit': 10000, 'is_unlimited': False}
        )
        
        # Get usage statistics for current month
        current_usage = token_limits.get_current_month_usage()
        usage_percentage = token_limits.get_usage_percentage()
        remaining_tokens = token_limits.get_remaining_tokens()
        
        # Get recent usage data (last 20 requests)
        from datetime import timedelta
        thirty_days_ago = timezone.now() - timedelta(days=30)
        
        recent_usage_data = AITokenUsage.objects.filter(
            user__branch=branch,
            created_at__gte=thirty_days_ago
        ).select_related('user').order_by('-created_at')[:20]
        
        # Format recent usage data for JSON response
        recent_usage = []
        for usage in recent_usage_data:
            recent_usage.append({
                'user__username': usage.user.username,
                'tokens_used': usage.tokens_used,
                'success': usage.success,
                'created_at': usage.created_at.isoformat(),
                'prompt_text': usage.prompt_text[:200] if usage.prompt_text else '',
                'error_message': usage.error_message if usage.error_message else ''
            })
        
        # Get user count for this branch
        user_count = branch.users.filter(is_active=True).count()
        
        # Prepare response data
        response_data = {
            'success': True,
            'branch_id': branch.id,
            'branch_name': branch.name,
            'current_usage': current_usage,
            'monthly_limit': token_limits.monthly_token_limit,
            'remaining_tokens': remaining_tokens if not token_limits.is_unlimited else -1,
            'usage_percentage': round(usage_percentage, 1),
            'is_unlimited': token_limits.is_unlimited,
            'user_count': user_count,
            'recent_usage': recent_usage,
        }
        
        return JsonResponse(response_data)
        
    except Exception as e:
        logger.error(f"Error in get_branch_token_data: {str(e)}", exc_info=True)
        return JsonResponse({
            'error': f'Error loading token data: {str(e)}',
            'success': False
        }, status=500)

@login_required
@require_http_methods(["GET", "POST"])
@ensure_csrf_cookie
def csrf_test(request):
    """
    Test endpoint to verify CSRF token functionality
    """
    if request.method == 'GET':
        return JsonResponse({
            'message': 'CSRF test endpoint - send POST request to test CSRF token',
            'csrf_token_available': bool(request.META.get('CSRF_COOKIE')),
            'user_authenticated': request.user.is_authenticated,
            'method': request.method
        })
    else:  # POST
        return JsonResponse({
            'message': 'CSRF token validation successful!',
            'csrf_token_available': bool(request.META.get('CSRF_COOKIE')),
            'user_authenticated': request.user.is_authenticated,
            'method': request.method,
            'success': True
        })
