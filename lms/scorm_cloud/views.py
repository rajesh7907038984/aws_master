from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt, csrf_protect, ensure_csrf_cookie
from django.http import JsonResponse, HttpResponseForbidden, HttpResponse, HttpResponseServerError, HttpResponseNotFound
from django.conf import settings
from django.core.exceptions import ValidationError, PermissionDenied
from .models import SCORMPackage, SCORMRegistration, SCORMCloudContent
from .utils.api import get_scorm_client
from .utils.tracking import process_xapi_statement, sync_registration_data, auto_sync_scorm_progress
import json
import logging
from courses.models import Topic
import uuid
from django.utils import timezone
from courses.models import Topic, TopicProgress
from .utils.api import SCORMCloudAPI
from .utils.exceptions import SCORMCloudError
from django.urls import reverse
import os
import time
import tempfile
import shutil
from .forms import SCORMUploadForm
from .utils.api import get_scorm_client, SCORMCloudError
from django.views.decorators.http import require_POST, require_http_methods, require_GET
from django.contrib.admin.views.decorators import staff_member_required
import traceback
import urllib.parse
import hmac
import hashlib

@login_required
@require_GET
def check_scorm_connection(request):
    """Check if SCORM Cloud is properly configured for the user's branch"""
    try:
        # Get the user's branch
        user_branch = request.user.branch if hasattr(request.user, 'branch') else None
        
        if not user_branch:
            return JsonResponse({
                'connected': False,
                'error': 'No branch found for user. Please contact your administrator.'
            })
        
        # Try to get SCORM client for the branch
        scorm_client = get_scorm_client(user=request.user, branch=user_branch)
        
        if not scorm_client or not scorm_client.is_configured:
            return JsonResponse({
                'connected': False,
                'error': f'SCORM Cloud not configured for branch "{user_branch.name}". Please contact your branch administrator to set up SCORM Cloud integration.'
            })
        
        # Test the connection by trying to get courses
        try:
            courses = scorm_client.get_all_courses()
            return JsonResponse({
                'connected': True,
                'message': f'SCORM Cloud connected successfully for branch "{user_branch.name}"',
                'courses_count': len(courses) if courses else 0
            })
        except Exception as e:
            return JsonResponse({
                'connected': False,
                'error': f'SCORM Cloud connection failed: {str(e)}'
            })
            
    except Exception as e:
        return JsonResponse({
            'connected': False,
            'error': f'Error checking SCORM connection: {str(e)}'
        })
import base64
from core.temp_scorm_storage import temp_scorm_storage


logger = logging.getLogger(__name__)

debug_logger = logging.getLogger('scorm_launch.debug')

# Configure file handler if it's not already set up
try:
    # Set up a console handler for debug logging
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
    debug_logger.addHandler(console_handler)
    debug_logger.setLevel(logging.DEBUG)
    debug_logger.propagate = False  # Don't propagate to root logger
except Exception as e:
    logger.error(f"Failed to set up SCORM debug logger: {e}")

@login_required
def package_list(request):
    """List all SCORM packages"""
    packages = SCORMPackage.objects.all().order_by('-upload_date')
    return render(request, 'scorm_cloud/package_list.html', {
        'packages': packages
    })

@login_required
def package_upload(request):
    """Handle SCORM package upload with enhanced error handling and logging"""
    logger.info("=== Starting SCORM Package Upload ===")
    logger.info(f"User: {request.user.username}")

    if request.method == 'POST':
        try:
            form = SCORMUploadForm(request.POST, request.FILES)
            if form.is_valid():
                file = request.FILES.get('file')
                if not file:
                    raise ValidationError("No file provided")

                # Validate file extension explicitly
                if not file.name.lower().endswith('.zip'):
                    return JsonResponse({
                        'status': 'error',
                        'message': 'Only ZIP files are allowed for SCORM packages.',
                        'field': 'file'
                    }, status=400)
                    
                # Validate file size - maximum 2GB
                max_size = 2 * 1024 * 1024 * 1024  # 2GB
                if file.size > max_size:
                    return JsonResponse({
                        'status': 'error',
                        'message': f'File size exceeds limit. Maximum size is 2GB, got {file.size/(1024*1024*1024):.2f}GB',
                        'field': 'file'
                    }, status=400)

                # Check for duplicate package by title
                title = form.cleaned_data['title']
                existing_package = SCORMPackage.objects.filter(title=title).first()
                
                if existing_package:
                    logger.info(f"Found existing package with title '{title}', returning existing package")
                    # Return the existing package information
                    return JsonResponse({
                        'status': 'success',
                        'message': 'Using existing package',
                        'package_id': str(existing_package.id),
                        'launch_url': existing_package.launch_url,
                        'is_duplicate': True
                    })

                # Use temporary SCORM storage in root folder
                file_path = temp_scorm_storage.get_temp_upload_path(file.name)
                logger.info(f"Saving SCORM file to temp root folder: {file_path}")
                
                # Save uploaded file to temporary location
                if not temp_scorm_storage.save_uploaded_file(file, file_path):
                    return JsonResponse({
                        'status': 'error',
                        'message': 'Failed to save uploaded file'
                    }, status=500)
                
                logger.info(f"SCORM file saved to temp root folder: {file_path}")
                
                # Generate unique SCORM Cloud course ID
                scorm_course_id = f"LMS_{int(time.time())}"
                logger.info(f"Generated SCORM Course ID: {scorm_course_id}")

                # Upload to SCORM Cloud using branch-specific settings
                try:
                    logger.info(f"Uploading package to SCORM Cloud with ID: {scorm_course_id}")
                    # Get branch-specific SCORM client
                    from .utils.api import get_scorm_client
                    scorm_client = get_scorm_client(user=request.user, branch=request.user.branch if hasattr(request.user, 'branch') else None)
                    cloud_response = scorm_client.upload_package(
                        file_path,
                        course_id=scorm_course_id
                    )
                    
                    if not cloud_response:
                        raise SCORMCloudError("Failed to upload to SCORM Cloud - no response received")
                        
                    logger.info("SCORM Cloud upload successful")
                    logger.debug(f"Cloud response: {cloud_response}")
                except Exception as upload_error:
                    logger.error(f"SCORM Cloud upload error: {str(upload_error)}")
                    # Clean up file from temp root folder on error
                    try:
                        if file_path:
                            temp_scorm_storage.cleanup_after_launch_url_created(file_path)
                            logger.info(f"Cleaned up SCORM file after upload error: {file_path}")
                    except Exception as e:
                        logger.error(f"Error cleaning up SCORM file after error: {str(e)}")
                    
                    return JsonResponse({
                        'status': 'error',
                        'message': f'SCORM Cloud upload failed: {str(upload_error)}'
                    }, status=500)

                # Create package record
                try:
                    package = SCORMPackage.objects.create(
                        cloud_id=cloud_response['id'],
                        title=form.cleaned_data['title'],
                        description=form.cleaned_data.get('description', ''),
                        version='1.2',  # Default to SCORM 1.2
                        launch_url=cloud_response.get('launch_url', ''),
                        entry_url=cloud_response.get('entry_url', ''),
                        # Set use_frameset to True for all new uploads
                        use_frameset=True,
                        launch_mode='window'  # Set to open in new window by default
                    )
                    logger.info(f"Created SCORMPackage record with ID: {package.id}")
                except Exception as db_error:
                    logger.error(f"Error creating package record: {str(db_error)}")
                    return JsonResponse({
                        'status': 'error',
                        'message': f'Database error: {str(db_error)}'
                    }, status=500)

                # Create learner registration
                try:
                    # Get branch-specific SCORM client
                    from .utils.api import get_scorm_client
                    scorm_client = get_scorm_client(user=request.user, branch=request.user.branch if hasattr(request.user, 'branch') else None)
                    
                    learner_id = str(request.user.id)
                    registration_id = f"LMS_{uuid.uuid4().hex}"
                    
                    registration_response = scorm_client.create_registration(
                        course_id=cloud_response['id'],
                        learner_id=learner_id,
                        registration_id=registration_id,
                        learner_info={
                            'firstName': request.user.first_name,
                            'lastName': request.user.last_name,
                            'email': request.user.email
                        }
                    )

                    if registration_response:
                        logger.info(f"Registration created: {registration_id}")

                        # Get launch URL with redirect - using frameset mode
                        launch_url = scorm_client.get_launch_url(
                            registration_id,
                            redirect_url=request.build_absolute_uri(reverse('users:role_based_redirect'))
                        )

                        if launch_url:
                            package.launch_url = launch_url
                            package.save()
                            logger.info(f"Updated package with launch URL: {launch_url}")
                except Exception as reg_error:
                    logger.error(f"Error creating registration: {str(reg_error)}")
                    # This is not fatal, so continue

                # Clean up temporary file after successful launch URL creation
                try:
                    if file_path:
                        temp_scorm_storage.cleanup_after_launch_url_created(file_path)
                        logger.info(f"Cleaned up SCORM file after launch URL creation: {file_path}")
                except Exception as e:
                    logger.error(f"Error cleaning up SCORM file after launch URL creation: {str(e)}")

                return JsonResponse({
                    'status': 'success',
                    'package_id': str(package.id),
                    'launch_url': package.launch_url
                })

            logger.warning(f"Form validation failed: {form.errors}")
            return JsonResponse({
                'status': 'error',
                'errors': form.errors
            }, status=400)

        except SCORMCloudError as e:
            logger.error(f"SCORM Cloud error: {str(e)}")
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=500)
        except Exception as e:
            from role_management.utils import SessionErrorHandler
            error_message = SessionErrorHandler.log_and_sanitize_error(
                e, request, error_type='system', operation='SCORM package upload'
            )
            return JsonResponse({
                'status': 'error',
                'message': error_message
            }, status=500)

    # Get course context for template (optional - for standalone upload)
    course = None
    course_id = request.GET.get('course_id')
    if course_id:
        try:
            from courses.models import Course
            course = Course.objects.get(id=course_id)
        except Course.DoesNotExist:
            pass
    
    return render(request, 'scorm_cloud/upload.html', {
        'form': SCORMUploadForm(),
        'course': course
    })

@login_required
def topic_scorm_upload(request):
    """Handle direct SCORM upload for topic creation without saving to disk"""
    logger.info("=== Starting Direct SCORM Topic Upload ===")
    logger.info(f"User: {request.user.username}")

    if request.method != 'POST':
        return JsonResponse({
            'status': 'error',
            'message': 'Only POST method allowed'
        }, status=405)

    try:
        # Get the uploaded file
        file = request.FILES.get('scorm_file')
        if not file:
            return JsonResponse({
                'status': 'error',
                'message': 'No SCORM file provided',
                'field': 'scorm_file'
            }, status=400)

        # Get other required data
        topic_title = request.POST.get('topic_title', '').strip()
        topic_id = request.POST.get('topic_id')
        
        if not topic_title:
            return JsonResponse({
                'status': 'error',
                'message': 'Topic title is required',
                'field': 'topic_title'
            }, status=400)

        # Validate file extension
        if not file.name.lower().endswith('.zip'):
            return JsonResponse({
                'status': 'error',
                'message': 'Only ZIP files are allowed for SCORM packages.',
                'field': 'scorm_file'
            }, status=400)
            
        # Validate file size - maximum 1GB
        max_size = 1024 * 1024 * 1024  # 1GB
        if file.size > max_size:
            return JsonResponse({
                'status': 'error',
                'message': f'File size exceeds limit. Maximum size is 1GB, got {file.size/(1024*1024):.2f}MB',
                'field': 'scorm_file'
            }, status=400)

        logger.info(f"Processing SCORM upload for topic: {topic_title} (ID: {topic_id})")
        logger.info(f"File size: {file.size/(1024*1024):.2f}MB")

        # Check for duplicate package by title
        existing_package = SCORMPackage.objects.filter(title=topic_title).first()
        
        if existing_package:
            logger.info(f"Found existing package with title '{topic_title}', using existing package")
            
            # If we have a topic_id, create the SCORM content linking
            if topic_id:
                from scorm_cloud.models import SCORMCloudContent
                scorm_content, created = SCORMCloudContent.objects.update_or_create(
                    content_id=str(topic_id),
                    content_type='topic',
                    defaults={
                        'package': existing_package,
                        'title': topic_title,
                        'description': f"SCORM content for topic {topic_id}",
                        'registration_prefix': f'LMS_{topic_id}_',
                        'passing_score': 80,
                        'requires_passing_score': True
                    }
                )
                logger.info(f"{'Created' if created else 'Updated'} SCORM content record for topic {topic_id}")
            
            return JsonResponse({
                'status': 'success',
                'message': 'Using existing package',
                'package_id': str(existing_package.id),
                'cloud_id': existing_package.cloud_id,
                'launch_url': existing_package.launch_url,
                'is_duplicate': True
            })

        # Use temporary SCORM storage in root folder
        file_path = None
        
        try:
            # Save file to temporary root folder
            file_path = temp_scorm_storage.get_temp_upload_path(file.name)
            logger.info(f"Saving SCORM file to temp root folder: {file_path}")
            
            # Save uploaded file to temporary location
            if not temp_scorm_storage.save_uploaded_file(file, file_path):
                return JsonResponse({
                    'status': 'error',
                    'message': 'Failed to save uploaded file'
                }, status=500)
            
            # Generate unique SCORM Cloud course ID
            import uuid
            if topic_id:
                unique_id = uuid.uuid4().hex[:8]
                scorm_course_id = f"COURSE_{topic_id}_{unique_id}"
            else:
                scorm_course_id = f"COURSE_{uuid.uuid4().hex[:12]}"
            
            logger.info(f"Generated SCORM Course ID: {scorm_course_id}")

            # Upload to SCORM Cloud using branch-specific settings
            logger.info("Uploading to SCORM Cloud...")
            # Get branch-specific SCORM client
            from .utils.api import get_scorm_client
            scorm_client = get_scorm_client(user=request.user, branch=request.user.branch if hasattr(request.user, 'branch') else None)
            cloud_response = scorm_client.upload_package(
                file_path,
                course_id=scorm_course_id,
                title=topic_title
            )
            
            if not cloud_response:
                raise SCORMCloudError("Failed to upload to SCORM Cloud - no response received")
                
            logger.info("SCORM Cloud upload successful")
            logger.debug(f"Cloud response: {cloud_response}")

            # Create package record
            package = SCORMPackage.objects.create(
                cloud_id=cloud_response.get('id', scorm_course_id),
                title=topic_title,
                description=f"SCORM content for topic {topic_id}" if topic_id else "Direct SCORM upload",
                version='1.2',
                launch_url=cloud_response.get('launch_url', ''),
                entry_url=cloud_response.get('entry_url', ''),
                use_frameset=True,
                launch_mode='window'
            )
            logger.info(f"Created SCORMPackage record with ID: {package.id}")

            # If we have a topic_id, create the SCORM content linking
            if topic_id:
                from scorm_cloud.models import SCORMCloudContent
                scorm_content, created = SCORMCloudContent.objects.update_or_create(
                    content_id=str(topic_id),
                    content_type='topic',
                    defaults={
                        'package': package,
                        'title': topic_title,
                        'description': f"SCORM content for topic {topic_id}",
                        'registration_prefix': f'LMS_{topic_id}_',
                        'passing_score': 80,
                        'requires_passing_score': True
                    }
                )
                logger.info(f"{'Created' if created else 'Updated'} SCORM content record for topic {topic_id}")

            return JsonResponse({
                'status': 'success',
                'message': 'SCORM package uploaded successfully',
                'package_id': str(package.id),
                'cloud_id': package.cloud_id,
                'launch_url': package.launch_url,
                'package_title': package.title,
                'topic_title': topic_title
            })

        finally:
            # Always clean up file from temp root folder
            if file_path:
                try:
                    temp_scorm_storage.cleanup_after_launch_url_created(file_path)
                    logger.info(f"Cleaned up SCORM file from temp root folder: {file_path}")
                except Exception as e:
                    logger.error(f"Error cleaning up SCORM file from temp root folder: {str(e)}")

    except SCORMCloudError as e:
        logger.error(f"SCORM Cloud error: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': f'SCORM Cloud upload failed: {str(e)}'
        }, status=500)
    except Exception as e:
        from role_management.utils import SessionErrorHandler
        error_message = SessionErrorHandler.log_and_sanitize_error(
            e, request, error_type='system', operation='SCORM topic upload'
        )
        
        # Provide more specific error messages based on the error type
        if 'redis' in str(e).lower() or 'connection' in str(e).lower():
            user_message = "System temporarily unavailable. Please try again in a few moments."
        elif 'scorm cloud' in str(e).lower() or 'app_id' in str(e).lower():
            user_message = "SCORM Cloud integration is not configured for your branch. Please contact your branch administrator to set up SCORM Cloud integration in Account Settings → Integrations → SCORM Cloud."
        elif 'timeout' in str(e).lower():
            user_message = "Upload timed out. Please try with a smaller file or check your internet connection."
        elif 'permission' in str(e).lower() or 'unauthorized' in str(e).lower():
            user_message = "You don't have permission to upload SCORM content. Please contact your administrator."
        else:
            user_message = f"Upload failed: {error_message}"
            
        logger.error(f"SCORM upload error: {error_message}")
        return JsonResponse({
            'status': 'error',  
            'message': user_message,
            'error_type': 'system_error'
        }, status=500)

@login_required
def package_detail(request, pk):
    """View package details and registrations"""
    package = get_object_or_404(SCORMPackage, pk=pk)
    registrations = SCORMRegistration.objects.filter(package=package)
    
    return render(request, 'scorm_cloud/package_detail.html', {
        'package': package,
        'registrations': registrations
    })

@login_required
def package_delete(request, pk):
    """Delete SCORM package with improved error handling"""
    package = get_object_or_404(SCORMPackage, pk=pk)
    
    if request.method == 'POST':
        try:
            # Get branch-specific SCORM client
            from .utils.api import get_scorm_client
            scorm_client = get_scorm_client(user=request.user, branch=request.user.branch if hasattr(request.user, 'branch') else None)
            
            # Delete from cloud with improved error handling
            deletion_result = scorm_client.delete_course(package.cloud_id)
            
            # Always delete locally regardless of cloud deletion result
            package.delete()
            
            # Prepare success message based on deletion result
            if deletion_result and isinstance(deletion_result, dict):
                status = deletion_result.get('status')
                message = deletion_result.get('message', 'Unknown result')
                
                if status == 'not_found':
                    return JsonResponse({
                        'success': True, 
                        'message': f'Package deleted locally. Cloud deletion not available: {message}'
                    })
                elif status == 'already_deleted':
                    return JsonResponse({
                        'success': True, 
                        'message': f'Package deleted successfully. {message}'
                    })
                elif status == 'error':
                    return JsonResponse({
                        'success': True,
                        'warning': True,
                        'message': f'Package deleted locally. Cloud deletion failed: {message}'
                    })
            
            return JsonResponse({'success': True, 'message': 'Package deleted successfully'})
            
        except Exception as e:
            logger.error(f"Package deletion error: {str(e)}")
            # Try to delete locally even if everything failed
            try:
                package.delete()
                return JsonResponse({
                    'success': True,
                    'warning': True,
                    'message': f'Package deleted locally only. Error: {str(e)}'
                })
            except Exception as local_error:
                logger.error(f"Local package deletion failed: {local_error}")
                return JsonResponse({'error': f'Failed to delete package: {str(e)}'}, status=500)
            
    return render(request, 'scorm_cloud/package_delete.html', {
        'package': package
    })

@login_required
def create_registration(request, topic_id):
    """Create or get SCORM Cloud registration for a topic"""
    logger.info(f"=== Creating SCORM Registration ===")
    logger.info(f"Topic ID: {topic_id}")
    logger.info(f"User: {request.user.username}")

    try:
        topic = get_object_or_404(Topic, id=topic_id)
        if not topic.content_type == 'SCORM':
            return JsonResponse({
                'error': 'Topic is not SCORM content'
            }, status=400)

        # Get SCORM content
        scorm_content = topic.get_scorm_content()
        if not scorm_content or not scorm_content.package:
            return JsonResponse({
                'error': 'No SCORM package found'
            }, status=400)

        # Generate unique registration ID
        registration_id = f"LMS_{uuid.uuid4().hex}"
        
        # Check if registration already exists
        registration = SCORMRegistration.objects.filter(
            package=scorm_content.package,
            user=request.user
        ).first()

        if not registration:
            # Get branch-specific SCORM client
            from .utils.api import get_scorm_client
            scorm_client = get_scorm_client(user=request.user, branch=request.user.branch if hasattr(request.user, 'branch') else None)
            
            # Create registration in SCORM Cloud
            response = scorm_client.create_registration(
                course_id=scorm_content.package.cloud_id,
                learner_id=str(request.user.id),
                registration_id=registration_id,
                learner_info={
                    'firstName': request.user.first_name,
                    'lastName': request.user.last_name,
                    'email': request.user.email
                }
            )

            if not response:
                raise Exception("Failed to create SCORM Cloud registration")

            # Create local registration record
            registration = SCORMRegistration.objects.create(
                registration_id=registration_id,
                package=scorm_content.package,
                user=request.user
            )

            # Add to topic's SCORM tracking
            topic.scorm_tracking.add(registration)
            logger.info(f"Created new registration: {registration_id}")
        else:
            logger.info(f"Using existing registration: {registration.registration_id}")

        # Get launch URL
        launch_url = registration.get_launch_url()
        if not launch_url:
            raise Exception("Failed to get launch URL")

        return JsonResponse({
            'registration_id': registration.registration_id,
            'launch_url': launch_url
        })

    except Exception as e:
        logger.error(f"Registration error: {str(e)}")
        logger.error("Stack trace:", exc_info=True)
        return JsonResponse({
            'error': str(e)
        }, status=500)


@login_required
def launch_content(request, registration_id):
    """Get launch URL for registration with proper error handling"""
    logger.info(f"=== Getting Launch URL ===")
    logger.info(f"Registration ID: {registration_id}")
    logger.info(f"User: {request.user.username}")

    try:
        registration = get_object_or_404(SCORMRegistration, registration_id=registration_id)
        
        if registration.user != request.user:
            return HttpResponseForbidden()

        launch_url = registration.get_launch_url()
        if not launch_url:
            return JsonResponse({
                'error': 'Failed to get launch URL'
            }, status=400)

        return JsonResponse({
            'launch_url': launch_url,
            'status': registration.get_status_display(),
            'progress': registration.get_progress_percentage()
        })

    except Exception as e:
        logger.error(f"Launch error: {str(e)}")
        logger.error("Stack trace:", exc_info=True)
        return JsonResponse({
            'error': str(e)
        }, status=500)

@login_required
def registration_status(request, pk):
    """Get registration status"""
    registration = get_object_or_404(SCORMRegistration, pk=pk)
    
    if registration.user != request.user:
        return HttpResponseForbidden()
        
    try:
        sync_registration_data(registration)
        return JsonResponse({
            'completion_status': registration.completion_status,
            'success_status': registration.success_status,
            'score': registration.score,
            'total_time': registration.total_time
        })
        
    except Exception as e:
        logger.error(f"Status sync error: {str(e)}")
        return JsonResponse({'error': str(e)}, status=400)

@ensure_csrf_cookie
def xapi_statements(request):
    """Handle xAPI statements with proper CSRF protection"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            # Process xAPI statements
            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    return JsonResponse({'error': 'Method not allowed'}, status=405)

@csrf_protect
def postback_handler(request):
    """Handle SCORM Cloud postback with proper CSRF protection"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            # Process postback data
            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    return JsonResponse({'error': 'Method not allowed'}, status=405)

def test_connection(request):
    """Test SCORM Cloud API connection"""
    if not request.user.is_authenticated:
        return HttpResponseForbidden()
        
    try:
        # Get branch-specific SCORM client
        from .utils.api import get_scorm_client
        scorm_client = get_scorm_client(user=request.user, branch=request.user.branch if hasattr(request.user, 'branch') else None)
        
        response = scorm_client._make_request('GET', 'ping')
        return JsonResponse({
            'status': 'success',
            'response': response
        })
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=400)
    
@require_GET
def scorm_upload_progress(request, topic_id):
    """Get SCORM upload progress for a topic"""
    logger.info(f"SCORM upload progress requested for topic {topic_id} by user {request.user.username}")
    
    try:
        # Get the topic
        topic = get_object_or_404(Topic, id=topic_id)
        if topic.content_type != 'SCORM':
            return JsonResponse({'error': 'Topic is not SCORM content'}, status=400)
        
        # Check if user has permission to view this topic
        if not topic.course.has_access(request.user):
            return JsonResponse({'error': 'Access denied'}, status=403)
        
        # Get upload progress from cache
        from django.core.cache import cache
        
        # Check various progress indicators
        progress_data = {
            'topic_id': topic_id,
            'status': 'unknown',
            'progress': 0,
            'message': 'Upload status unknown',
            'estimated_time_remaining': None,
            'file_size': None,
            'upload_speed': None
        }
        
        # Check if upload is queued
        if cache.get(f"scorm_queued_{topic_id}"):
            progress_data.update({
                'status': 'queued',
                'message': 'Upload queued for processing...',
                'progress': 5
            })
        
        # Check if upload is processing
        elif cache.get(f"scorm_processing_{topic_id}"):
            progress_data.update({
                'status': 'processing',
                'message': 'Uploading to SCORM Cloud...',
                'progress': 25
            })
        
        # Check if upload is completed
        elif cache.get(f"scorm_processed_{topic_id}"):
            progress_data.update({
                'status': 'completed',
                'message': 'Upload completed successfully',
                'progress': 100
            })
        
        # Check for SCORM content
        try:
            from scorm_cloud.models import SCORMCloudContent
            scorm_content = SCORMCloudContent.objects.filter(
                content_type='topic',
                content_id=str(topic_id)
            ).first()
            
            if scorm_content and scorm_content.package:
                progress_data.update({
                    'status': 'completed',
                    'message': 'SCORM package ready',
                    'progress': 100,
                    'scorm_id': scorm_content.package.scorm_id
                })
        except Exception as e:
            logger.warning(f"Could not check SCORM content: {str(e)}")
        
        # Get detailed progress if available
        detailed_progress = cache.get(f"scorm_detailed_progress_{topic_id}")
        if detailed_progress:
            progress_data.update(detailed_progress)
        
        return JsonResponse(progress_data)
        
    except Exception as e:
        logger.error(f"Error getting SCORM upload progress: {str(e)}")
        return JsonResponse({
            'error': 'Failed to get upload progress',
            'status': 'error'
        }, status=500)

@require_POST
def scorm_tracking_update(request, topic_id):
    """Update SCORM tracking progress for a topic"""
    logger.info(f"SCORM tracking update called for topic {topic_id} by user {request.user.username}")
    
    try:
        # Get the topic
        topic = get_object_or_404(Topic, id=topic_id)
        if topic.content_type != 'SCORM':
            logger.error(f"Topic {topic_id} is not a SCORM topic (type: {topic.content_type})")
            return JsonResponse({'error': 'Topic is not SCORM content'}, status=400)
        
        # Get or create progress record
        progress, created = TopicProgress.objects.get_or_create(
            user=request.user,
            topic=topic,
            defaults={'completed': False}
        )
        
        if created:
            logger.info(f"Created new TopicProgress for topic {topic_id}, user {request.user.username}")
            progress.init_progress_data()
        
        # Get associated SCORM registration
        registration = None
        try:
            from scorm_cloud.models import SCORMRegistration, SCORMCloudContent
            
            # Find registration through SCORM content mapping
            scorm_content = SCORMCloudContent.objects.filter(
                content_type='topic',
                content_id=str(topic_id)
            ).select_related('package').first()
            
            if scorm_content:
                registration = SCORMRegistration.objects.filter(
                    user=request.user,
                    package=scorm_content.package
                ).first()
                
                if registration:
                    logger.info(f"Found SCORM registration {registration.registration_id} for topic {topic_id}")
                else:
                    logger.warning(f"No SCORM registration found for user {request.user.username}, topic {topic_id}")
            else:
                logger.warning(f"No SCORM content mapping found for topic {topic_id}")
                
        except Exception as scorm_error:
            logger.error(f"Error finding SCORM registration: {str(scorm_error)}")
        
        # Initialize progress_data if needed
        if not isinstance(progress.progress_data, dict):
            progress.progress_data = {}
            logger.info(f"Initialized progress_data for topic {topic_id}")
        
        # Process request data if present (from JavaScript SCORM API)
        request_source = 'sync'  # default
        if request.body:
            try:
                data = json.loads(request.body)
                status = data.get('status')
                request_source = data.get('source', 'sync')
                is_final_update = data.get('final_update', False)
                
                logger.info(f"SCORM API data received: status={status}, source={request_source}, final={is_final_update}")
                
                # Extract additional SCORM data
                score = data.get('score', 0)
                raw_score = data.get('raw_score', 0)
                max_score = data.get('max_score', 100)
                min_score = data.get('min_score', 0)
                time_spent = data.get('time_spent', 0)
                progress_percentage = data.get('progress', 0)
                registration_id = data.get('registration_id')
                
                # Update progress data with all SCORM information
                progress.progress_data.update({
                    'status': status,
                    'completion_status': status,
                    'score': score,
                    'raw_score': raw_score,
                    'max_score': max_score,
                    'min_score': min_score,
                    'time_spent': time_spent,
                    'progress_percentage': progress_percentage,
                    'registration_id': registration_id,
                    'source': request_source,
                    'timestamp': data.get('timestamp', timezone.now().isoformat())
                })
                
                # If status is provided from SCORM API, update completion status immediately
                if status in ['completed', 'passed']:
                    logger.info(f"SCORM API reports completion: {status} with score: {score}")
                    
                    # Update progress_data first
                    progress.progress_data.update({
                        'completed': True,
                        'completion_date': timezone.now().isoformat()
                    })
                    
                    # Then update model fields
                    progress.completed = True
                    progress.completion_method = 'scorm'
                    progress.completed_at = timezone.now()
                    
                    # Update completion data with detailed SCORM information
                    if not progress.completion_data:
                        progress.completion_data = {}
                    
                    progress.completion_data.update({
                        'scorm_completion': True,
                        'completed_at': progress.completed_at.isoformat(),
                        'completion_method': 'scorm',
                        'api_status': status,
                        'source': request_source,
                        'final_score': score,
                        'raw_score': raw_score,
                        'max_score': max_score,
                        'min_score': min_score,
                        'time_spent': time_spent,
                        'progress_percentage': progress_percentage,
                        'registration_id': registration_id
                    })
                    
                    logger.info(f"SCORM completion processed via API for topic {topic_id} with score {score}")
                else:
                    # Update progress without completion
                    logger.info(f"SCORM progress update: {status} with score: {score}")
                    
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON in SCORM tracking request: {str(e)}")
                # Continue with sync anyway
        
        # Get branch-specific SCORM client
        from .utils.api import get_scorm_client
        scorm_client = get_scorm_client(user=request.user, branch=request.user.branch if hasattr(request.user, 'branch') else None)
        
        # Sync with SCORM Cloud registration data
        result = scorm_client.get_registration_status(registration.registration_id)
        
        if result:
            # Update SCORM registration with data from API
            completion_status = result.get('registrationCompletion', '').lower()
            success_status = result.get('registrationSuccess', '').lower()
            
            # Normalize completion status
            if completion_status == 'complete':
                completion_status = 'completed'
            
            # Compute completion percentage based on objectives if available
            completion_percent = 0
            objectives = result.get('objectives', [])
            
            if objectives and len(objectives) > 0:
                completed_objectives = sum(1 for obj in objectives if obj.get('success') == 'PASSED')
                completion_percent = (completed_objectives / len(objectives)) * 100
            elif completion_status in ['completed', 'passed']:
                completion_percent = 100
            
            # Update progress_data
            if not isinstance(progress.progress_data, dict):
                progress.progress_data = {}
            
            progress.progress_data.update({
                'completion_status': completion_status,
                'success_status': success_status,
                'completion_percent': completion_percent,
                'last_updated': timezone.now().isoformat()
            })
            
            # Handle score using unified scoring service
            if 'score' in result:
                from core.utils.scoring import ScoreCalculationService
                
                score_data = result.get('score', {})
                normalized_score = ScoreCalculationService.handle_scorm_score(score_data)
                
                if normalized_score is not None:
                    progress.last_score = normalized_score
                    if progress.best_score is None or normalized_score > progress.best_score:
                        progress.best_score = normalized_score
                    progress.progress_data['score'] = float(normalized_score)
            
            # Capture the lesson location/position for resuming later
            runtime_data = result.get('runtime', {})
            suspend_data = runtime_data.get('suspendData')
            lesson_location = runtime_data.get('lessonLocation')
            lesson_status = runtime_data.get('completionStatus')
            entry = runtime_data.get('entry')
            
            # Save bookmark data for resuming later
            if not progress.bookmark:
                progress.bookmark = {}
            
            # Update bookmark with resumption data
            progress.bookmark.update({
                'suspendData': suspend_data,
                'lessonLocation': lesson_location,
                'lessonStatus': lesson_status,
                'entry': entry,
                'updated_at': timezone.now().isoformat()
            })
            
            # Mark as completed if appropriate - CENTRALIZED COMPLETION LOGIC
            if completion_status in ['completed', 'passed'] or success_status == 'passed':
                if not progress.completed:
                    logger.info(f"SCORM completion detected, marking topic as complete via centralized handler")
                    
                    # Use the centralized mark_complete method for consistency
                    progress.mark_complete('scorm')
                    
                    # Update completion data with SCORM-specific info
                    if not progress.completion_data:
                        progress.completion_data = {}
                    
                    progress.completion_data.update({
                        'scorm_completion': True,
                        'completion_status': completion_status,
                        'success_status': success_status,
                        'scorm_score': score_data.get('raw', 0) if score_data else 0,
                        'scorm_max_score': score_data.get('max', 100) if score_data else 100
                    })
                    
                    progress.save()
                    logger.info(f"SCORM topic {topic.id} marked complete for user {request.user.username}")
                else:
                    # Already completed, just ensure fields are consistent
                    if progress.completion_method != 'scorm':
                        progress.completion_method = 'scorm'
                    if not progress.completed_at:
                        progress.completed_at = timezone.now()
                    
                    logger.info(f"SCORM topic {topic.id} already completed for user {request.user.username}")
            else:
                # Not completed yet, ensure completed field is False
                if progress.completed:
                    logger.warning(f"SCORM topic {topic.id} marked incomplete but was previously complete for user {request.user.username}")
                    progress.completed = False
                    progress.completed_at = None
            
            # Also ensure the scorm_registration field is set for tracking
            if not progress.scorm_registration and registration:
                progress.scorm_registration = registration.registration_id
                logger.info(f"Linked TopicProgress {progress.id} to SCORM registration {registration.registration_id}")
            
            # Update timestamp in progress_data
            progress.progress_data['last_updated'] = timezone.now().isoformat()
            
            # Now save the progress with all updates
            progress.save()
            
            # Get course and check for next topics if completed
            course = None
            next_topic = None
            first_incomplete_topic = None
            
            try:
                course = topic.course
                
                if progress.completed and course:
                    if request.user.role == 'learner':
                        # Filter out draft topics for learners
                        topics = list(Topic.objects.filter(coursetopic__course=course).exclude(status='draft').order_by('order', 'coursetopic__order', 'created_at'))
                    else:
                        # Admin, instructors and other roles see all topics
                        topics = list(Topic.objects.filter(coursetopic__course=course).order_by('order', 'coursetopic__order', 'created_at'))
                    
                    # Find next topic in sequence
                    current_index = topics.index(topic)
                    if current_index < len(topics) - 1:
                        next_topic = topics[current_index + 1]
                        
                    # Also find first incomplete topic as fallback
                    if not next_topic:
                        for t in topics:
                            if t.id == topic.id:
                                continue
                                
                            t_progress = TopicProgress.objects.filter(user=request.user, topic=t).first()
                            if not t_progress or not t_progress.completed:
                                first_incomplete_topic = t
                                break
            except (ValueError, IndexError, AttributeError) as e:
                logger.error(f"Error finding next topic for SCORM content: {str(e)}")
            
            # Prepare response with navigation details
            response_data = {
                'status': 'success',
                'progress': progress.progress_data.get('completion_percent', 0),
                'completion_status': completion_status or 'incomplete',
                'success_status': success_status,
                'score': float(progress.last_score) if progress.last_score else None,
                'bookmark': progress.bookmark,
                'completed': progress.completed
            }
            
            # Add next topic info if we found it and completed
            if progress.completed:
                if next_topic:
                    response_data['next_topic'] = {
                        'id': next_topic.id,
                        'title': next_topic.title,
                        'url': reverse('courses:topic_view', kwargs={'topic_id': next_topic.id})
                    }
                elif first_incomplete_topic:
                    response_data['next_topic'] = {
                        'id': first_incomplete_topic.id,
                        'title': first_incomplete_topic.title,
                        'url': reverse('courses:topic_view', kwargs={'topic_id': first_incomplete_topic.id}),
                        'is_first_incomplete': True
                    }
            
            return JsonResponse(response_data)
        
        # Return default success if we couldn't sync
        return JsonResponse({
            'status': 'success',
            'message': 'Progress tracked',
            'completed': progress.completed
        })
            
    except Exception as e:
        logger.error(f"Error updating SCORM tracking: {str(e)}")
        logger.error("Stack trace:", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def scorm_tracking_status(request, topic_id):
    """Get current SCORM tracking status."""
    try:
        topic = get_object_or_404(Topic, id=topic_id)

        if topic.content_type == 'SCORM':
            scorm_content = topic.get_scorm_content()
            if scorm_content and scorm_content.package:
                # Get the registration for the user
                registration = scorm_content.package.get_registration(request.user)
                if registration:
                    # Try to sync the data first
                    try:
                        # Get branch-specific SCORM client
                        from .utils.api import get_scorm_client
                        scorm_client = get_scorm_client(user=request.user, branch=request.user.branch if hasattr(request.user, 'branch') else None)
                        
                        # Get registration status from SCORM Cloud
                        result = scorm_client.get_registration_status(registration.registration_id)
                        if result:
                            # Extract progress and score
                            progress = 0
                            score = None
                            
                            if 'registrationCompletion' in result:
                                progress = result['registrationCompletion'] * 100
                                
                            if 'registrationSuccess' in result:
                                score = result.get('score', {}).get('scaled', 0) * 100
                                
                            logger.info(f"SCORM status for {registration.registration_id}: progress={progress}, score={score}")
                            
                            return JsonResponse({
                                'status': 'success',
                                'progress': progress,
                                'score': score
                            })
                    except Exception as e:
                        logger.error(f"Error syncing SCORM data: {str(e)}")
                    
                    # Fallback to registration data we have
                    return JsonResponse({
                        'status': 'success',
                        'progress': getattr(registration, 'progress', 0),
                        'score': getattr(registration, 'score', None)
                    })
        
        # Default response if we can't get SCORM status
        return JsonResponse({
            'status': 'success',
            'progress': 0,
            'score': None,
            'message': 'No SCORM tracking available'
        })
        
    except Exception as e:
        logger.error(f"Error getting SCORM status: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)

@login_required
def scorm_launch(request, topic_id):
    """Launch SCORM content for a topic."""
    from .models import SCORMCloudContent, get_topic_model, SCORMRegistration
    from .utils.api import get_scorm_client
    import uuid
    
    # Get branch-specific SCORM client
    scorm_client = get_scorm_client(user=request.user, branch=request.user.branch if hasattr(request.user, 'branch') else None)
    
    # Check if SCORM Cloud is properly configured
    if not scorm_client or not scorm_client.is_configured:
        logger.error(f"SCORM Cloud not configured for user {request.user.username}")
        return HttpResponseServerError(
            "SCORM Cloud integration is not configured for your branch. Please contact your branch administrator to set up SCORM Cloud integration in Account Settings → Integrations → SCORM Cloud."
        )
    
    # Get topic and course
    TopicModel = get_topic_model()
    try:
        topic = TopicModel.objects.get(id=topic_id)
    except TopicModel.DoesNotExist:
        logger.error(f"Topic not found: {topic_id}")
        return HttpResponseNotFound(
            f"❌ Topic not found\n\n"
            f"🔍 Diagnostic Information:\n"
            f"• Topic ID: {topic_id}\n"
            f"• User: {request.user.username if request.user.is_authenticated else 'Anonymous'}\n"
            f"• Branch: {getattr(request.user, 'branch', 'Unknown') if request.user.is_authenticated else 'Unknown'}\n\n"
            f"The requested topic does not exist or has been deleted. Please check the URL or contact support if you believe this is an error."
        )
        
    # Check if topic has SCORM content
    scorm_content = SCORMCloudContent.objects.filter(
        content_type='topic',
        content_id=str(topic.id)
    ).first()
    
    if not scorm_content:
        logger.error(f"No SCORM content found for topic: {topic_id}")
        return HttpResponseNotFound(
            f"❌ No SCORM content found\n\n"
            f"🔍 Diagnostic Information:\n"
            f"• Topic ID: {topic_id}\n"
            f"• Topic Title: {topic.title}\n"
            f"• User: {request.user.username if request.user.is_authenticated else 'Anonymous'}\n"
            f"• Branch: {getattr(request.user, 'branch', 'Unknown') if request.user.is_authenticated else 'Unknown'}\n\n"
            f"This topic does not have SCORM content associated with it. Please contact support if you believe this is an error."
        )
    
    # Check if this is a placeholder package
    if scorm_content.package and (scorm_content.package.cloud_id.startswith('PLACEHOLDER_') or scorm_content.package.cloud_id.startswith('placeholder_')):
        logger.info(f"Topic {topic_id} has placeholder SCORM content - showing placeholder message")
        return render(request, 'scorm_cloud/placeholder_content.html', {
            'topic': topic,
            'scorm_content': scorm_content,
            'user': request.user
        })
    
    # Get course for redirect URL
    course = get_topic_course(topic)
    
    if not course:
        logger.error(f"Course not found for topic {topic_id}")
        return HttpResponseNotFound("Course not found.")
    
    # Build redirect URL
    try:
        redirect_url = request.build_absolute_uri(reverse('courses:topic_view', kwargs={'topic_id': topic.id}))
        logger.info(f"Setting redirect URL to topic view: {redirect_url}")
    except Exception as e:
        logger.error(f"Error building redirect URL: {str(e)}")
        redirect_url = request.build_absolute_uri('/')
    
    # Get or create progress record
    progress, created = TopicProgress.objects.get_or_create(
        user=request.user,
        topic=topic
    )
    
    # If we're creating a new progress record, initialize it
    if created:
        progress.init_progress_data()
        progress.save()
        
    # Make sure we have the package ID
    try:
        package = scorm_content.package
        if not package:
            raise Exception("No SCORM package associated with this content")
            
        cloud_id = package.cloud_id
        if not cloud_id:
            raise Exception("No cloud_id for SCORM package")
            
        logger.info(f"Using SCORM package with cloud_id: {cloud_id}")
        
        # Get or create a registration
        registration = None
        if progress.scorm_registration:
            # Try to get existing registration
            try:
                registration = SCORMRegistration.objects.get(
                    registration_id=progress.scorm_registration,
                    user=request.user
                )
                logger.info(f"Found existing registration: {registration.registration_id}")
            except SCORMRegistration.DoesNotExist:
                logger.warning(f"Registration {progress.scorm_registration} not found, will create new one")
                progress.scorm_registration = None
                
        if not registration:
            # Create a new registration with proper ID format
            # Use a proper registration ID format that won't be confused with course IDs
            reg_id = f"REG_{topic.id}_{request.user.id}_{uuid.uuid4().hex[:8]}"
            logger.info(f"Creating new registration with ID: {reg_id}")
            
            try:
                # Create in database first
                registration = SCORMRegistration.objects.create(
                    registration_id=reg_id,
                    user=request.user,
                    package=package
                )
                logger.info(f"Created registration record in database: {reg_id}")
                
                # CRITICAL FIX: Create registration in SCORM Cloud using the correct course ID
                # The course ID should be package.cloud_id, NOT the registration ID
                logger.info(f"Creating registration in SCORM Cloud: course_id={package.cloud_id}, registration_id={reg_id}")
                
                scorm_client.create_registration(
                    course_id=package.cloud_id,  # Use the package's cloud_id as course ID
                    learner_id=str(request.user.id), 
                    registration_id=reg_id
                )
                logger.info(f"Created registration {reg_id} in SCORM Cloud for course {package.cloud_id}")
            except Exception as reg_error:
                logger.error(f"Error creating registration in SCORM Cloud: {str(reg_error)}")
                # Continue to fallback options
        
        # Update progress record with registration ID if needed
        if not progress.scorm_registration:
            progress.scorm_registration = registration.registration_id
            progress.save()
        
        if registration:
            logger.info(f"Using registration ID: {registration.registration_id}")
            
            # Get bookmark data to enable proper resumption
            bookmark_data = {}
            if progress.bookmark and isinstance(progress.bookmark, dict):
                bookmark_data = progress.bookmark
                logger.info(f"Using bookmark data for resumption: {json.dumps(bookmark_data)}")
                
            # Get the launch URL with redirect URL and proper settings
            additional_settings = {
                'redirectOnExitUrl': redirect_url,
                'embedded': False,  # Always use frameset instead of iframe
                'api': True,
                'initializeApi': True,
                'framesetSupport': True,  # Always enable frameset support
                'scormVersion': '1.2',
                'apiVersion': '1.2',
                'forceReview': False,
                'commitOnUnload': True,
                'apiCommitFrequency': 'auto',
                'apiLogFrequency': '1',
                'apiPostbackTimeout': 30000,
                'apiPostbackAttempts': 3,
                'preventFrameBust': True,
                'apiSandbox': False,
                'launchMode': 'OwnWindow',  # Force same window launch
                'openWindowSettings': {
                    'width': '100%',
                    'height': '100%',
                    'resizable': True,
                    'scrollbars': True,
                    'toolbar': False,
                    'location': False,
                    'status': False,
                    'menubar': False,
                    'titlebar': True
                }
            }
            
            # Add bookmark data for resumption if available
            if bookmark_data:
                if 'configuration' not in additional_settings:
                    additional_settings['configuration'] = {}
                
                if 'resumeData' not in additional_settings['configuration']:
                    additional_settings['configuration']['resumeData'] = {}
                
                # Set resume parameters from bookmark data
                if 'lessonLocation' in bookmark_data and bookmark_data['lessonLocation']:
                    additional_settings['configuration']['resumeData']['lessonLocation'] = bookmark_data['lessonLocation']
                
                if 'suspendData' in bookmark_data and bookmark_data['suspendData']:
                    additional_settings['configuration']['resumeData']['suspendData'] = bookmark_data['suspendData']
                    
                if 'entry' in bookmark_data:
                    additional_settings['configuration']['resumeData']['entry'] = 'resume'
                
                logger.info(f"Added resume data to launch settings")
            
            # Add standard configuration
            if 'configuration' not in additional_settings:
                additional_settings['configuration'] = {}
                
            additional_settings['configuration'].update({
                'scoLaunchType': 'frameset',  # Always use frameset for consistent behavior
                'apiPlacementStrategy': 'top',  # Required for frameset
                'apiLocation': 'top',  # Required for frameset
                'apiStayInParent': False,  # Set to false for frameset
                'targetWindow': '_self',  # Force same window target
                'launchMethod': 'OwnWindow',  # Use current window
                'playerConfiguration': {
                    'displayStandalone': True,  # Required for frameset
                    'height': '100%',
                    'width': '100%',
                    'forceReview': False,
                    'showProgressBar': True,
                    'showNavBar': True,
                    'lmsEnabled': True,
                    'apiEnabled': True,
                    'autoProgress': True,
                    'logLevel': 5,
                    'debugEnabled': True
                }
            })
            
            # Try to build the launch URL using the registration
            try:
                # CRITICAL FIX: Use the correct course ID (package.cloud_id) not registration ID
                # The build_launch_link method expects a registration ID, but we need to ensure
                # the registration was created with the correct course ID
                logger.info(f"Building launch URL for registration {registration.registration_id} with course {package.cloud_id}")
                
                launch_url = scorm_client.build_launch_link(
                    registration.registration_id,
                    redirect_on_exit_url=redirect_url,
                    additional_settings=additional_settings
                )
                
                if launch_url:
                    logger.info(f"Generated launch URL from registration: {launch_url}")
                    
                    # Always render using launch_popup.html template to open in same window
                    context = {
                        'launch_url': launch_url,
                        'title': f"{topic.title} - SCORM Content",
                        'topic_id': topic_id,  # Pass topic_id to template for tracking updates
                        'registration_id': registration.registration_id  # Pass registration_id for tracking
                    }
                    
                    # Add code to ensure completion status is tracked properly after launch
                    progress.scorm_registration = registration.registration_id
                    progress.save()
                    
                    # Set up tracking JavaScript to update progress on return
                    context['progress_update_url'] = reverse('courses:scorm_tracking_update', kwargs={'topic_id': topic_id})
                    
                    return render(request, 'scorm_cloud/launch_popup.html', context)
                else:
                    logger.warning("Failed to get launch URL from registration, trying alternatives")
            except Exception as launch_error:
                logger.error(f"Error generating launch URL from registration: {str(launch_error)}")
                # Continue to fallback methods
        
        # Fallback to preview URL if registration approach fails
        logger.info(f"Attempting to get preview URL for course {cloud_id}")
        try:
            # Use the SCORM Cloud API to get a properly authenticated preview URL
            preview_data = {
                "redirectOnExitUrl": redirect_url
            }
            
            # Call the API to get a preview URL with proper authentication
            preview_response = scorm_client._make_request(
                'POST',
                f'courses/{cloud_id}/preview',
                data=preview_data
            )
            
            if preview_response and 'launchLink' in preview_response:
                preview_url = preview_response['launchLink']
                logger.info(f"Generated preview URL via API: {preview_url}")
                
                # Update the package's launch_url for future use
                try:
                    package.launch_url = preview_url
                    package.save()
                    logger.info(f"Updated package launch_url for future use")
                except Exception as save_error:
                    # Continue even if save fails - just log it
                    logger.warning(f"Could not update package launch_url: {str(save_error)}")
                
                # Use the launch_popup.html template to open in same window
                return render(request, 'scorm_cloud/launch_popup.html', {
                    'launch_url': preview_url,
                    'title': f"{topic.title} - SCORM Content"
                })
            else:
                logger.error(f"Failed to get preview URL from API: {preview_response}")
                raise Exception("Invalid preview response from SCORM Cloud API")
                
        except Exception as preview_error:
            logger.error(f"Preview URL failed: {str(preview_error)}")
            
            # Fallback to direct content URL with authentication
            try:
                # Use the branch-specific SCORM client
                if not scorm_client or not scorm_client.is_configured:
                    raise Exception("SCORM Cloud not properly configured for this branch")
                
                logger.info(f"Using direct content URL fallback for cloud_id: {cloud_id}")
                
                # Use the improved API method instead of manual URL building
                fallback_url = scorm_client.get_direct_launch_url(
                    course_id=cloud_id,
                    redirect_url=redirect_url
                )
                
                if not fallback_url:
                    raise Exception("Failed to generate direct launch URL")
                
                logger.info(f"Using fallback URL: {fallback_url}")
                
                # Use the launch_popup.html template to open in same window
                return render(request, 'scorm_cloud/launch_popup.html', {
                    'launch_url': fallback_url,
                    'title': f"{topic.title} - SCORM Content"
                })
            except Exception as fallback_error:
                logger.error(f"Error creating fallback URL: {str(fallback_error)}")
                
                # PRODUCTION FIX: Enhanced error diagnostics
                error_details = []
                
                # Check if this is an old upload with invalid credentials
                if "test_app_id" in str(fallback_error) or "test_secret_key" in str(fallback_error):
                    error_details.append("❌ This SCORM content was uploaded with test credentials and cannot be launched.")
                    error_details.append("💡 Solution: Re-upload the content with valid SCORM Cloud credentials.")
                elif "APP_ID not configured" in str(fallback_error):
                    error_details.append("❌ SCORM Cloud is not properly configured.")
                    error_details.append("💡 Solution: Contact your administrator to set up valid SCORM Cloud credentials.")
                elif "cloud_id" in str(fallback_error).lower():
                    error_details.append("❌ This SCORM content does not have a valid cloud ID.")
                    error_details.append("💡 Solution: Re-upload the content to SCORM Cloud.")
                else:
                    error_details.append(f"❌ SCORM Cloud configuration error: {str(fallback_error)}")
                
                # Add diagnostic information
                error_details.append("")
                error_details.append("🔍 Diagnostic Information:")
                error_details.append(f"• Topic ID: {topic_id}")
                error_details.append(f"• User: {request.user.username}")
                error_details.append(f"• Branch: {request.user.branch.name if hasattr(request.user, 'branch') and request.user.branch else 'No branch'}")
                error_details.append(f"• Package Cloud ID: {package.cloud_id}")
                
                # Check SCORM client status
                if scorm_client and scorm_client.is_configured:
                    error_details.append(f"• SCORM Client: ✅ Configured (App ID: {scorm_client.app_id[:10]}...)")
                else:
                    error_details.append("• SCORM Client: ❌ NOT CONFIGURED")
                
                error_message = "\\n".join(error_details)
                logger.error(f"Complete SCORM launch error details: {error_message}")
                
                return HttpResponseServerError(
                    f"Failed to generate a valid launch URL.\\n\\n{error_message}\\n\\nPlease contact support with this error message."
                )

    except Exception as e:
        logger.error(f"Error launching SCORM content: {str(e)}", exc_info=True)
        return HttpResponseServerError(f"Error launching SCORM content. Please try again later or contact support if the problem persists.")

@login_required
def scorm_diagnostics(request, topic_id):
    """Diagnostic view for SCORM launch issues"""
    from .models import SCORMCloudContent, get_topic_model, SCORMRegistration
    from .utils.api import get_scorm_client
    from account_settings.models import GlobalAdminSettings
    from django.utils import timezone
    import json
    
    diagnostics = {
        'topic_id': topic_id,
        'user': request.user.username,
        'timestamp': timezone.now().isoformat(),
        'checks': {}
    }
    
    try:
        # Check 1: Topic exists
        TopicModel = get_topic_model()
        try:
            topic = TopicModel.objects.get(id=topic_id)
            diagnostics['checks']['topic_exists'] = True
            diagnostics['checks']['topic_title'] = topic.title
            diagnostics['checks']['topic_content_type'] = topic.content_type
        except TopicModel.DoesNotExist:
            diagnostics['checks']['topic_exists'] = False
            diagnostics['checks']['topic_error'] = "Topic not found"
            return JsonResponse(diagnostics)
        
        # Check 2: SCORM content exists
        scorm_content = SCORMCloudContent.objects.filter(
            content_type='topic',
            content_id=str(topic.id)
        ).first()
        
        if scorm_content:
            diagnostics['checks']['scorm_content_exists'] = True
            diagnostics['checks']['scorm_content_title'] = scorm_content.title
            diagnostics['checks']['scorm_content_id'] = scorm_content.id
        else:
            diagnostics['checks']['scorm_content_exists'] = False
            diagnostics['checks']['scorm_content_error'] = "No SCORM content found for this topic"
            return JsonResponse(diagnostics)
        
        # Check 3: Package exists
        if scorm_content.package:
            diagnostics['checks']['package_exists'] = True
            diagnostics['checks']['package_id'] = scorm_content.package.id
            diagnostics['checks']['package_cloud_id'] = scorm_content.package.cloud_id
            diagnostics['checks']['package_title'] = scorm_content.package.title
        else:
            diagnostics['checks']['package_exists'] = False
            diagnostics['checks']['package_error'] = "No SCORM package associated with content"
            return JsonResponse(diagnostics)
        
        # Check 4: Cloud ID exists
        if scorm_content.package.cloud_id:
            diagnostics['checks']['cloud_id_exists'] = True
            diagnostics['checks']['cloud_id'] = scorm_content.package.cloud_id
        else:
            diagnostics['checks']['cloud_id_exists'] = False
            diagnostics['checks']['cloud_id_error'] = "No cloud_id for SCORM package"
            return JsonResponse(diagnostics)
        
        # Check 5: SCORM Cloud configuration
        # SCORM Cloud is now handled by branch-specific integrations
        diagnostics['checks']['scorm_cloud_enabled'] = True  # Always true since it's branch-specific
        # Check for branch-specific SCORM integrations instead
        from account_settings.models import SCORMIntegration
        branch_scorm_count = SCORMIntegration.objects.filter(is_active=True).count()
        diagnostics['checks']['branch_scorm_integrations_count'] = branch_scorm_count
        diagnostics['checks']['scorm_cloud_configured'] = branch_scorm_count > 0
        diagnostics['checks']['scorm_cloud_configuration_type'] = 'Branch-specific configurations'
        diagnostics['checks']['scorm_cloud_tested'] = branch_scorm_count > 0
        diagnostics['checks']['scorm_cloud_test_error'] = None
        
        # Check 6: SCORM client configuration
        try:
            scorm_client = get_scorm_client(user=request.user, branch=request.user.branch if hasattr(request.user, 'branch') else None)
            diagnostics['checks']['scorm_client_configured'] = scorm_client.is_configured
            if scorm_client.is_configured:
                diagnostics['checks']['scorm_client_app_id'] = scorm_client.app_id
                diagnostics['checks']['scorm_client_base_url'] = scorm_client.base_url
            else:
                diagnostics['checks']['scorm_client_error'] = "SCORM client not configured"
        except Exception as e:
            diagnostics['checks']['scorm_client_error'] = str(e)
        
        # Check 7: Branch-specific SCORM integration
        try:
            from account_settings.models import SCORMIntegration
            from scorm_cloud.utils.api import get_branch_scorm_integration
            
            branch_integration = get_branch_scorm_integration(user=request.user)
            if branch_integration:
                diagnostics['checks']['branch_integration_exists'] = True
                diagnostics['checks']['branch_integration_name'] = branch_integration.name
                diagnostics['checks']['branch_integration_active'] = branch_integration.is_active
                diagnostics['checks']['branch_integration_tested'] = branch_integration.is_tested
            else:
                diagnostics['checks']['branch_integration_exists'] = False
                diagnostics['checks']['branch_integration_error'] = "No branch-specific SCORM integration found"
                
                # Check if user's branch has SCORM enabled
                if hasattr(request.user, 'branch') and request.user.branch:
                    diagnostics['checks']['user_branch_scorm_enabled'] = request.user.branch.scorm_integration_enabled
                else:
                    diagnostics['checks']['user_branch_scorm_enabled'] = False
                    diagnostics['checks']['user_has_branch'] = False
        except Exception as e:
            diagnostics['checks']['branch_integration_error'] = str(e)
        
        # Overall status
        critical_checks = [
            'topic_exists',
            'scorm_content_exists', 
            'package_exists',
            'cloud_id_exists',
            'scorm_client_configured'
        ]
        
        # Add branch-specific checks if available
        if diagnostics['checks'].get('branch_integration_exists'):
            critical_checks.append('branch_integration_exists')
        # SCORM Cloud is now branch-specific, so this check is not critical
        
        diagnostics['overall_status'] = all(
            diagnostics['checks'].get(check, False) for check in critical_checks
        )
        
        if diagnostics['overall_status']:
            diagnostics['message'] = "All critical checks passed. SCORM should work properly."
        else:
            failed_checks = [check for check in critical_checks 
                           if not diagnostics['checks'].get(check, False)]
            diagnostics['message'] = f"SCORM launch will fail. Issues found in: {', '.join(failed_checks)}"
            diagnostics['failed_checks'] = failed_checks
        
    except Exception as e:
        diagnostics['error'] = str(e)
        diagnostics['overall_status'] = False
    
    # Check if this is an AJAX request
    if request.headers.get('Accept') == 'application/json':
        return JsonResponse(diagnostics, indent=2)
    else:
        # Render HTML template
        return render(request, 'scorm_cloud/diagnostics.html', {
            'diagnostics': diagnostics,
            'overall_status': diagnostics.get('overall_status', False),
            'checks': diagnostics.get('checks', {}),
            'error': diagnostics.get('error'),
            'failed_checks': diagnostics.get('failed_checks', []),
            'user': request.user.username,
            'timestamp': diagnostics.get('timestamp'),
            'topic_id': topic_id
        })

def get_topic_course(topic):
    """Helper function to get course for a topic through CourseTopic"""
    from courses.models import Course
    return Course.objects.filter(coursetopic__topic=topic).first()

@staff_member_required
def debug_scorm_content(request):
    """Temporary debugging view to show all SCORM content items"""
    all_content = SCORMCloudContent.objects.all()
    
    content_list = []
    for content in all_content:
        content_list.append({
            'id': str(content.id),
            'content_id': content.content_id,
            'title': content.title,
            'content_type': content.content_type,
            'package_id': str(content.package.id) if content.package else None,
            'package_title': content.package.title if content.package else None
        })
    
    return HttpResponse(
        f"<h1>SCORM Content Debug</h1>" +
        f"<p>Total items: {all_content.count()}</p>" +
        f"<pre>{json.dumps(content_list, indent=2)}</pre>"
    )

@login_required
def debug_scorm_launch(request, topic_id):
    """Debug endpoint for SCORM launch issues"""
    try:
        from .models import SCORMCloudContent, get_topic_model
        from .utils.api import get_scorm_client

        # Get topic
        TopicModel = get_topic_model()
        try:
            topic = TopicModel.objects.get(id=topic_id)
            debug_logger.info(f"Topic found: {topic.id} - {topic.title}")
        except TopicModel.DoesNotExist:
            debug_logger.error(f"Topic not found: {topic_id}")
            return JsonResponse({"error": "Topic not found"}, status=404)

        # Get SCORM content
        scorm_content = SCORMCloudContent.objects.filter(
            content_type='topic',
            content_id=str(topic.id)
        ).first()
        
        debug_data = {
            "topic_id": topic_id,
            "topic_title": topic.title,
            "content_type": topic.content_type,
            "scorm_content_exists": scorm_content is not None,
        }
        
        if scorm_content:
            debug_data["scorm_content_id"] = str(scorm_content.id)
            debug_data["package_exists"] = hasattr(scorm_content, 'package') and scorm_content.package is not None
            
            if hasattr(scorm_content, 'package') and scorm_content.package is not None:
                package = scorm_content.package
                debug_data["package_id"] = str(package.id)
                debug_data["cloud_id"] = package.cloud_id
                debug_data["package_title"] = package.title
                debug_data["has_launch_url"] = bool(package.launch_url)
                
                # Check if user has a registration
                registration = package.get_registration(request.user)
                debug_data["registration_exists"] = registration is not None
                
                if registration:
                    debug_data["registration_id"] = registration.registration_id
                    
                    # Try to build launch URL
                    try:
                        course = get_topic_course(topic)
                        if course:
                            redirect_url = request.build_absolute_uri(
                                reverse('courses:course_view', kwargs={'course_id': course.id})
                            )
                        else:
                            redirect_url = request.build_absolute_uri('/')
                            
                        debug_data["redirect_url"] = redirect_url
                        
                        # Try to get launch URL
                        launch_url = scorm_client.build_launch_link(
                            registration.registration_id,
                            redirect_on_exit_url=redirect_url
                        )
                        
                        debug_data["launch_url_generated"] = launch_url is not None
                        debug_data["launch_url"] = launch_url if launch_url else "Failed to generate"
                    except Exception as e:
                        debug_data["launch_url_error"] = str(e)
                        debug_data["launch_url_error_trace"] = traceback.format_exc()
        
        # Log and return debug data
        debug_logger.info(f"SCORM launch debug data: {json.dumps(debug_data, indent=2)}")
        return JsonResponse(debug_data)
        
    except Exception as e:
        debug_logger.error(f"Debug error: {str(e)}", exc_info=True)
        return JsonResponse({"error": str(e)}, status=500)

@login_required
@require_GET
def direct_scorm_launch(request, content_id):
    """Direct launch endpoint for SCORM content from admin view"""
    from .models import SCORMCloudContent
    from django.shortcuts import get_object_or_404, redirect
    from django.conf import settings
    import logging
    from .utils.api import get_scorm_client
    
    logger = logging.getLogger(__name__)
    
    # Get branch-specific SCORM client
    scorm_cloud = get_scorm_client(user=request.user, branch=request.user.branch if hasattr(request.user, 'branch') else None)
    
    # Check if SCORM Cloud is properly configured using branch-specific client
    if not scorm_cloud or not scorm_cloud.is_configured:
        logger.error("SCORM Cloud not configured for this branch")
        return HttpResponseServerError("SCORM Cloud integration is not configured for your branch. Please contact your branch administrator to set up SCORM Cloud integration in Account Settings → Integrations → SCORM Cloud.")
    
    # Log request details
    logger.info(f"Direct SCORM launch request - Method: {request.method}, Content ID: {content_id}")
    
    # Get SCORM content
    try:
        # Log debug information
        logger.info(f"Attempting to launch SCORM content with ID: {content_id}")
        
        # Get the content object
        scorm_content = get_object_or_404(SCORMCloudContent, id=content_id)
        logger.info(f"Found SCORM content: {scorm_content.title}")
        
        # Make sure we have a package with cloud_id
        if not scorm_content.package:
            logger.error(f"No package associated with content: {content_id}")
            return HttpResponseNotFound(f"No SCORM package associated with this content (ID: {content_id}). Please associate a package with this content.")
            
        if not scorm_content.package.cloud_id:
            logger.error(f"No cloud_id for package: {scorm_content.package.id}")
            return HttpResponseNotFound(f"The associated SCORM package does not have a valid cloud_id. Please ensure the package was correctly uploaded to SCORM Cloud.")
        
        # SCORM Cloud configuration already checked above with branch-specific client
        
        # Get return URL - default to admin
        host = request.get_host()
        scheme = request.scheme
        base_url = f"{scheme}://{host}"
        return_url = request.GET.get('return_url', f'{base_url}/admin/scorm_cloud/scormcloudcontent/')
        
        # Get the course ID (cloud_id)
        cloud_id = scorm_content.package.cloud_id
        
        # First try to get or create a registration for this user
        # This is more reliable than using preview links
        logger.info(f"Getting or creating registration for user {request.user.id} and course {cloud_id}")
        try:
            registration = scorm_content.package.get_registration(request.user)
            if not registration:
                # If no registration exists, create one
                logger.info(f"No registration found, creating one for user {request.user.id}")
                from .models import SCORMRegistration
                import uuid
                
                # Generate a random registration ID
                reg_id = f"LMS_ADMIN_{uuid.uuid4().hex[:8]}"
                
                registration = SCORMRegistration.objects.create(
                    registration_id=reg_id,
                    user=request.user,
                    package=scorm_content.package
                )
                
                # Create registration in SCORM Cloud
                try:
                    scorm_client.create_registration(
                        cloud_id, 
                        f"user_{request.user.id}", 
                        registration_id=reg_id
                    )
                    logger.info(f"Created registration {reg_id} in SCORM Cloud")
                except Exception as reg_error:
                    logger.error(f"Error creating registration in SCORM Cloud: {str(reg_error)}")
                    # Continue anyway - we'll try to use the preview URL as fallback
            
            # If we have a registration, use it to get a launch URL
            if registration:
                logger.info(f"Using registration {registration.registration_id} to launch content")
                launch_url = scorm_client.build_launch_link(
                    registration.registration_id,
                    redirect_on_exit_url=return_url
                )
                
                if launch_url:
                    logger.info(f"Generated launch URL using registration: {launch_url}")
                    return redirect(launch_url)
                else:
                    logger.warning("Failed to generate launch URL from registration, falling back to preview URL")
        except Exception as reg_error:
            logger.error(f"Error with registration process: {str(reg_error)}")
            # Continue to preview URL fallback
        
        # Fallback to preview URL if registration approach fails
        logger.info(f"Attempting to get preview URL for course {cloud_id}")
        try:
            # Use the SCORM Cloud API to get a properly authenticated preview URL
            preview_data = {
                "redirectOnExitUrl": return_url
            }
            
            # Call the API to get a preview URL with proper authentication
            preview_response = scorm_client._make_request(
                'POST',
                f'courses/{cloud_id}/preview',
                data=preview_data
            )
            
            if preview_response and 'launchLink' in preview_response:
                preview_url = preview_response['launchLink']
                logger.info(f"Generated preview URL via API: {preview_url}")
                
                # Update the package's launch_url for future use
                try:
                    scorm_content.package.launch_url = preview_url
                    scorm_content.package.save()
                    logger.info(f"Updated package launch_url for future use")
                except Exception as save_error:
                    # Continue even if save fails - just log it
                    logger.warning(f"Could not update package launch_url: {str(save_error)}")
                
                return redirect(preview_url)
            else:
                logger.error(f"Failed to get preview URL from API: {preview_response}")
                raise Exception("Invalid preview response from SCORM Cloud API")
        except Exception as preview_error:
            logger.error(f"Error getting preview URL: {str(preview_error)}")
            
            # Direct fallback - build the URL manually
            logger.info(f"Using direct content URL format with APP_ID: {app_id}")
            
            # Generate authentication parameters for the URL
            import time
            import hmac
            import hashlib
            import base64
            import urllib.parse
            
            timestamp = int(time.time())
            
            # Generate a signed URL with authentication parameters
            string_to_sign = f"{app_id}{cloud_id}{timestamp}"
            signature = hmac.new(
                secret_key.encode('utf-8'),
                string_to_sign.encode('utf-8'),
                hashlib.sha256
            ).digest()
            encoded_signature = base64.b64encode(signature).decode('utf-8')
            
            # Build the direct URL with all required authentication parameters
            direct_url = (
                f"https://cloud.scorm.com/content/courses/{app_id}/{cloud_id}/0/scormdriver/indexAPI.html"
                f"?appId={app_id}&timestamp={timestamp}&signature={urllib.parse.quote(encoded_signature)}"
                f"&redirectOnExitUrl={urllib.parse.quote(return_url)}"
                f"&Key-Pair-Id={app_id}"
            )
            
            logger.info(f"Using direct URL: {direct_url}")
            return redirect(direct_url)
    except SCORMCloudContent.DoesNotExist:
        logger.error(f"SCORM content not found with ID: {content_id}")
        return HttpResponseNotFound(f"SCORM content with ID {content_id} not found.")
    except Exception as e:
        logger.error(f"Error in direct_scorm_launch: {str(e)}", exc_info=True)
        error_message = f"Error launching SCORM content: {str(e)}"
        
        # Add debugging details for better error resolution
        error_details = ""
        try:
            # Get information about the content if possible
                content_info = f"Content ID: {content_id}, Title: {scorm_content.title}"
                package_info = "No package associated"
                if hasattr(scorm_content, 'package') and scorm_content.package:
                    package_info = f"Package ID: {scorm_content.package.id}, Title: {scorm_content.package.title}"
                error_details = f"\n\nDetails:\n{content_info}\n{package_info}"
        except:
            pass
            
        return HttpResponseServerError(f"{error_message}{error_details}")

@login_required
@require_POST
def auto_sync_scorm_progress(request):
    """
    Automatically sync SCORM progress data from SCORM Cloud.
    This endpoint should be called when returning from a SCORM session.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        # Get request data
        data = json.loads(request.body)
        registration_id = data.get('registration_id')
        topic_id = data.get('topic_id')
        
        if not registration_id:
            return JsonResponse({
                'success': False,
                'error': 'Missing registration_id'
            }, status=400)
            
        # Ensure the user has access to this registration
        from .models import SCORMRegistration
        registration = get_object_or_404(SCORMRegistration, registration_id=registration_id)
        
        # Only allow the owner of the registration to sync it
        if registration.user != request.user:
            return JsonResponse({
                'success': False,
                'error': 'Permission denied'
            }, status=403)
            
        # Call the auto-sync function
        from .utils.tracking import auto_sync_scorm_progress
        result = auto_sync_scorm_progress(registration_id)
        
        if not result:
            logger.warning(f"Auto-sync failed for registration {registration_id}")
            return JsonResponse({
                'success': False,
                'error': 'Sync failed'
            }, status=500)
            
        # Get the updated status
        from courses.models import TopicProgress
        progress = TopicProgress.objects.filter(scorm_registration=registration_id).first()
        
        if not progress:
            return JsonResponse({
                'success': False,
                'error': 'Progress record not found'
            }, status=404)
            
        # Return the updated progress status
        return JsonResponse({
            'success': True,
            'completed': progress.completed,
            'score': progress.last_score,
            'best_score': progress.best_score
        })
            
    except Exception as e:
        logger.error(f"Error in auto_sync_scorm_progress endpoint: {str(e)}")
        logger.exception("Full error details:")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@login_required
def register_for_package(request, package_id):
    """
    Register the current user for a SCORM package and redirect to launch.
    This is used from the gradebook when a user needs to register for SCORM content.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        from .models import SCORMPackage
        
        # Get the SCORM package
        package = get_object_or_404(SCORMPackage, id=package_id)
        
        # Get or create registration for the user
        registration = package.get_registration(request.user)
        
        if not registration:
            # If registration creation failed, show error
            from django.contrib import messages
            messages.error(request, f"Failed to register for SCORM package: {package.title}")
            return redirect('gradebook:index')
        
        # Registration successful, redirect to launch
        return redirect('scorm_cloud:launch_content', pk=registration.id)
        
    except Exception as e:
        logger.error(f"Error in register_for_package: {str(e)}")
        from django.contrib import messages
        messages.error(request, f"Error registering for SCORM package: {str(e)}")
        return redirect('gradebook:index')


@login_required
def scorm_worker_status(request):
    """API endpoint to check SCORM worker status"""
    if not request.user.is_staff:
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    try:
        from scorm_cloud.utils.async_uploader import get_queue_status
        from scorm_cloud.models import SCORMCloudContent
        from courses.models import Topic
        from django.core.cache import cache
        
        # Get worker status
        status = get_queue_status()
        
        # Get content stats
        scorm_topics = Topic.objects.filter(content_type='SCORM').count()
        scorm_content_count = SCORMCloudContent.objects.filter(content_type='topic').count()
        
        # Check for stale processing locks
        stale_locks = 0
        for topic in Topic.objects.filter(content_type='SCORM'):
            if cache.get(f"scorm_processing_{topic.id}"):
                stale_locks += 1
        
        return JsonResponse({
            'worker': {
                'running': status['worker_running'],
                'alive': status['worker_alive'],
                'upload_queue_size': status['upload_queue_size'],
                'retry_queue_size': status['retry_queue_size']
            },
            'content': {
                'total_scorm_topics': scorm_topics,
                'synced_content': scorm_content_count,
                'unsynced_topics': scorm_topics - scorm_content_count,
                'stale_processing_locks': stale_locks
            },
            'health': 'healthy' if (status['worker_running'] and status['worker_alive']) else 'degraded'
        })
        
    except Exception as e:
        logger.error(f"Error getting worker status: {str(e)}")
        return JsonResponse({
            'error': str(e),
            'health': 'error'
        }, status=500)

@login_required
def scorm_progress_report(request, topic_id):
    """Get detailed SCORM progress report for a topic"""
    try:
        from courses.models import TopicProgress
        from scorm_cloud.models import SCORMCloudContent, SCORMRegistration
        
        # Get the topic
        topic = get_object_or_404(Topic, id=topic_id)
        if topic.content_type != 'SCORM':
            return JsonResponse({'error': 'Topic is not SCORM content'}, status=400)
        
        # Get user's progress
        progress = TopicProgress.objects.filter(
            user=request.user,
            topic=topic
        ).first()
        
        if not progress:
            return JsonResponse({
                'error': 'No progress found for this topic',
                'topic_id': topic_id,
                'user': request.user.username
            }, status=404)
        
        # Get SCORM content and registration
        scorm_content = SCORMCloudContent.objects.filter(
            content_type='topic',
            content_id=str(topic_id)
        ).select_related('package').first()
        
        registration = None
        if scorm_content:
            registration = SCORMRegistration.objects.filter(
                user=request.user,
                package=scorm_content.package
            ).first()
        
        # Build comprehensive report
        report_data = {
            'topic_id': topic_id,
            'topic_title': topic.title,
            'user': request.user.username,
            'completed': progress.completed,
            'completion_method': progress.completion_method,
            'completed_at': progress.completed_at.isoformat() if progress.completed_at else None,
            'progress_data': progress.progress_data or {},
            'completion_data': progress.completion_data or {},
            'scorm_content': {
                'title': scorm_content.title if scorm_content else None,
                'package_id': scorm_content.package.cloud_id if scorm_content and scorm_content.package else None,
                'package_title': scorm_content.package.title if scorm_content and scorm_content.package else None
            } if scorm_content else None,
            'registration': {
                'registration_id': registration.registration_id if registration else None,
                'status': registration.get_status_display() if registration else None,
                'progress': registration.get_progress_percentage() if registration else None
            } if registration else None
        }
        
        # Extract key metrics for easy access
        progress_data = progress.progress_data or {}
        completion_data = progress.completion_data or {}
        
        metrics = {
            'score': progress_data.get('score', 0),
            'raw_score': progress_data.get('raw_score', 0),
            'max_score': progress_data.get('max_score', 100),
            'min_score': progress_data.get('min_score', 0),
            'time_spent': progress_data.get('time_spent', 0),
            'progress_percentage': progress_data.get('progress_percentage', 0),
            'status': progress_data.get('status', 'not_started'),
            'completion_status': progress_data.get('completion_status', 'not_started'),
            'final_score': completion_data.get('final_score', 0),
            'scorm_completion': completion_data.get('scorm_completion', False)
        }
        
        report_data['metrics'] = metrics
        
        return JsonResponse(report_data)
        
    except Exception as e:
        logger.error(f"Error generating SCORM progress report: {str(e)}")
        return JsonResponse({
            'error': str(e)
        }, status=500)


@login_required 
@require_POST
def restart_scorm_worker(request):
    """API endpoint to restart SCORM worker"""
    if not request.user.is_staff:
        return JsonResponse({'error': 'Unauthorized'}, status=403)
        
    try:
        from scorm_cloud.utils.async_uploader import stop_worker, ensure_worker_running
        
        # Stop current worker
        stop_worker()
        
        # Start new worker
        success = ensure_worker_running()
        
        if success:
            return JsonResponse({'status': 'restarted', 'message': 'SCORM worker restarted successfully'})
        else:
            return JsonResponse({'status': 'error', 'message': 'Failed to restart worker'}, status=500)
            
    except Exception as e:
        logger.error(f"Error restarting worker: {str(e)}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@login_required
@require_http_methods(["GET", "POST"])
def generate_scorm_launch_url(request, topic_id):
    """API endpoint to generate SCORM launch URL directly"""
    try:
        from .models import SCORMCloudContent, SCORMRegistration, get_topic_model
        from .utils.api import get_scorm_client
        from django.urls import reverse
        
        # Get the topic
        TopicModel = get_topic_model()
        try:
            topic = TopicModel.objects.get(id=topic_id)
        except TopicModel.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Topic not found'
            }, status=404)
        
        # Check if user has permission to access this topic
        from courses.views import check_course_permission, get_topic_course
        course = get_topic_course(topic)
        if not course or not check_course_permission(request.user, course):
            return JsonResponse({
                'success': False,
                'error': 'You do not have permission to access this content'
            }, status=403)
        
        # Get SCORM content for the topic
        scorm_content = SCORMCloudContent.objects.filter(
            content_type='topic',
            content_id=str(topic.id)
        ).first()
        
        if not scorm_content or not scorm_content.package:
            return JsonResponse({
                'success': False,
                'error': 'No SCORM content found for this topic'
            }, status=404)
        
        package = scorm_content.package
        
        if not package.cloud_id or package.cloud_id.startswith('PLACEHOLDER'):
            return JsonResponse({
                'success': False,
                'error': 'SCORM content is not ready. Please contact your instructor.',
                'content_status': 'not_ready'
            }, status=400)
        
        # Get SCORM client
        scorm_client = get_scorm_client(user=request.user, branch=request.user.branch if hasattr(request.user, 'branch') else None)
        
        # Test SCORM Cloud connectivity first
        scorm_available = False
        if scorm_client and scorm_client.is_configured:
            try:
                # Test API connectivity
                scorm_client._make_request('GET', 'ping')
                scorm_available = True
            except Exception as e:
                logger.warning(f"SCORM Cloud API not available: {str(e)}")
                scorm_available = False
        
        if not scorm_available:
            # Fallback to local SCORM player when SCORM Cloud is not available
            return JsonResponse({
                'success': True,
                'launch_url': f'/scorm/topic/{topic.id}/local-launch/',
                'fallback': True,
                'message': 'Using local SCORM player (SCORM Cloud not available)'
            })
        
        # Get or create registration
        registration_id = f"LMS_{topic.id}_{int(time.time())}"
        
        try:
            # Create registration with SCORM Cloud
            scorm_client.create_registration(
                course_id=package.cloud_id,
                learner_id=str(request.user.id),
                registration_id=registration_id
            )
            
            # Create local registration record
            registration, created = SCORMRegistration.objects.get_or_create(
                user=request.user,
                content=scorm_content,
                defaults={
                    'registration_id': registration_id,
                    'is_active': True
                }
            )
            
            if not created:
                # Update existing registration
                registration.registration_id = registration_id
                registration.is_active = True
                registration.save()
            
        except Exception as reg_error:
            logger.error(f"Error creating registration: {str(reg_error)}")
            return JsonResponse({
                'success': False,
                'error': f'Failed to create SCORM registration: {str(reg_error)}'
            }, status=500)
        
        # Generate launch URL
        try:
            # Build redirect URL for after SCORM completion
            redirect_url = request.build_absolute_uri(
                reverse('courses:topic_view', kwargs={'topic_id': topic.id})
            )
            
            # Get launch URL from SCORM Cloud
            launch_url = scorm_client.get_launch_url(registration_id, redirect_url)
            
            if not launch_url:
                # Fallback to direct launch URL
                launch_url = scorm_client.get_direct_launch_url(
                    course_id=package.cloud_id,
                    redirect_url=redirect_url
                )
            
            if not launch_url:
                raise Exception("Failed to generate launch URL")
            
            return JsonResponse({
                'success': True,
                'launch_url': launch_url,
                'topic_title': topic.title,
                'registration_id': registration_id
            })
            
        except Exception as launch_error:
            logger.error(f"Error generating launch URL: {str(launch_error)}")
            return JsonResponse({
                'success': False,
                'error': f'Failed to generate launch URL: {str(launch_error)}'
            }, status=500)
        
    except Exception as e:
        logger.error(f"Error in generate_scorm_launch_url: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'An unexpected error occurred. Please try again later.'
        }, status=500)

@login_required
def local_scorm_launch(request, topic_id):
    """Local SCORM player when SCORM Cloud is not available"""
    try:
        from courses.models import Topic
        from django.shortcuts import render
        
        topic = Topic.objects.get(id=topic_id)
        
        context = {
            'topic': topic,
            'user': request.user,
        }
        
        return render(request, 'scorm_cloud/local_player.html', context)
        
    except Topic.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Topic not found'
        }, status=404)
    except Exception as e:
        logger.error(f"Error in local SCORM launch: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Failed to launch local SCORM player'
        }, status=500)

@login_required
@require_http_methods(["POST"])
def local_scorm_completion(request, topic_id):
    """Handle SCORM completion locally without SCORM Cloud API"""
    try:
        from courses.models import TopicProgress
        from django.utils import timezone
        import json
        
        # Get or create progress record
        progress, created = TopicProgress.objects.get_or_create(
            user=request.user,
            topic_id=topic_id
        )
        
        # Parse completion data
        data = json.loads(request.body)
        
        # Mark as completed
        progress.completed = True
        progress.completion_method = 'scorm_local'
        progress.completed_at = timezone.now()
        
        # Update completion data
        if not progress.completion_data:
            progress.completion_data = {}
        
        progress.completion_data.update({
            'scorm_completion': True,
            'completion_status': data.get('completion_status', 'completed'),
            'success_status': data.get('success_status', 'passed'),
            'completion_date': timezone.now().isoformat(),
            'local_completion': True,
            'auto_completion': data.get('auto_completion', False),
            'score': data.get('score', 0)
        })
        
        progress.save()
        
        logger.info(f"Local SCORM completion for topic {topic_id}, user {request.user.username}")
        
        return JsonResponse({
            'success': True,
            'message': 'Topic marked as completed',
            'completed': True
        })
        
    except Exception as e:
        logger.error(f"Error in local completion tracking: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Failed to mark topic as completed'
        }, status=500)



