"""
Direct S3 Upload Handler
Generates pre-signed URLs for browser-to-S3 uploads
No AWS credentials needed in Django after initial setup
"""
import os
import uuid
import json
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
import boto3
from botocore.client import Config
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


@login_required
@require_http_methods(["POST"])
def get_presigned_upload_url(request):
    """
    Generate a pre-signed URL for direct browser-to-S3 upload
    """
    try:
        data = json.loads(request.body)
        filename = data.get('filename')
        content_type = data.get('content_type', 'application/octet-stream')
        file_type = data.get('file_type', 'document')  # video, audio, document
        
        if not filename:
            return JsonResponse({'error': 'Filename is required'}, status=400)
        
        # Generate unique filename to avoid collisions
        ext = os.path.splitext(filename)[1]
        unique_filename = f"{uuid.uuid4()}{ext}"
        
        # Determine S3 key based on file type
        if file_type == 'video':
            s3_key = f"media/topics/videos/{unique_filename}"
        elif file_type == 'audio':
            s3_key = f"media/topics/audio/{unique_filename}"
        else:
            s3_key = f"media/topics/documents/{unique_filename}"
        
        # Get S3 client - will use IAM role if available, otherwise credentials
        try:
            s3_client = boto3.client(
                's3',
                aws_access_key_id=getattr(settings, 'AWS_ACCESS_KEY_ID', None),
                aws_secret_access_key=getattr(settings, 'AWS_SECRET_ACCESS_KEY', None),
                region_name=settings.AWS_S3_REGION_NAME,
                config=Config(signature_version='s3v4')
            )
        except Exception as e:
            logger.error(f"Failed to create S3 client: {e}")
            return JsonResponse({
                'error': 'S3 configuration error. Please contact administrator.'
            }, status=500)
        
        # Generate pre-signed POST URL
        try:
            bucket_name = settings.AWS_STORAGE_BUCKET_NAME
            
            # Generate pre-signed POST
            presigned_post = s3_client.generate_presigned_post(
                Bucket=bucket_name,
                Key=s3_key,
                Fields={
                    'Content-Type': content_type,
                    'x-amz-meta-original-filename': filename,
                    'x-amz-meta-uploaded-by': str(request.user.id)
                },
                Conditions=[
                    {'Content-Type': content_type},
                    ['content-length-range', 1, 600 * 1024 * 1024]  # 1 byte to 600MB
                ],
                ExpiresIn=3600  # URL valid for 1 hour
            )
            
            # Build the full S3 URL
            s3_url = f"https://{bucket_name}.s3.{settings.AWS_S3_REGION_NAME}.amazonaws.com/{s3_key}"
            
            return JsonResponse({
                'success': True,
                'upload_url': presigned_post['url'],
                'form_data': presigned_post['fields'],
                's3_key': s3_key,
                's3_url': s3_url,
                'unique_filename': unique_filename
            })
            
        except Exception as e:
            logger.error(f"Failed to generate pre-signed URL: {e}")
            return JsonResponse({
                'error': f'Failed to generate upload URL: {str(e)}'
            }, status=500)
            
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"Error in get_presigned_upload_url: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_http_methods(["POST"])
def confirm_upload(request):
    """
    Confirm that upload was successful and file exists in S3
    """
    try:
        data = json.loads(request.body)
        s3_key = data.get('s3_key')
        
        if not s3_key:
            return JsonResponse({'error': 'S3 key is required'}, status=400)
        
        # Verify file exists in S3
        try:
            s3_client = boto3.client(
                's3',
                aws_access_key_id=getattr(settings, 'AWS_ACCESS_KEY_ID', None),
                aws_secret_access_key=getattr(settings, 'AWS_SECRET_ACCESS_KEY', None),
                region_name=settings.AWS_S3_REGION_NAME,
                config=Config(signature_version='s3v4')
            )
            
            bucket_name = settings.AWS_STORAGE_BUCKET_NAME
            s3_client.head_object(Bucket=bucket_name, Key=s3_key)
            
            return JsonResponse({
                'success': True,
                'message': 'File confirmed in S3'
            })
            
        except Exception as e:
            logger.error(f"File not found in S3: {e}")
            return JsonResponse({
                'error': 'File not found in S3',
                'details': str(e)
            }, status=404)
            
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"Error in confirm_upload: {e}")
        return JsonResponse({'error': str(e)}, status=500)

