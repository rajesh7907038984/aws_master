import requests
import json
import logging
import base64
import os
import time
import uuid
from urllib.parse import urljoin, urlparse, parse_qs, urlencode
from django.conf import settings
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from django.contrib.auth import get_user_model
import hmac
import hashlib
import urllib.parse
import socket
import ssl

logger = logging.getLogger(__name__)

# Configure global socket timeouts for large file uploads
socket.setdefaulttimeout(2700)  # 45 minutes for socket operations

class SCORMCloudError(Exception):
    """Base exception for SCORM Cloud errors"""
    pass

class SCORMCloudAPI:
    def __init__(self, app_id=None, secret_key=None):
        """Initialize the API client with credentials
        
        Args:
            app_id: SCORM Cloud App ID
            secret_key: SCORM Cloud Secret Key
        """
        self.is_configured = False
        
        try:
            # Use provided parameters - no fallback to global settings
            self.app_id = app_id or ''
            self.secret_key = secret_key or ''
            self.base_url = 'https://cloud.scorm.com/api/v2'
            self.verify_ssl = True
            self.request_timeout = 900
            
            # Check if credentials are valid
            if self.app_id and self.secret_key and self.app_id != 'your_app_id_here' and self.secret_key != 'your_secret_key_here':
                self.is_configured = True
                logger.info("SCORM Cloud API initialized successfully")
            else:
                self.is_configured = False
                logger.warning("SCORM Cloud API not properly configured - missing or invalid credentials")
            
        except Exception as e:
            logger.error(f"Error initializing SCORM Cloud API: {str(e)}")
            self.app_id = app_id or ''
            self.secret_key = secret_key or ''
            self.base_url = 'https://cloud.scorm.com/api/v2'
            self.verify_ssl = True
            self.request_timeout = 900
        
        self._last_response = None
        
        # Initialize requests session with retries
        self.session = self._create_session()
    
    def _is_configured(self):
        """Check if SCORM Cloud is properly configured"""
        return getattr(self, 'is_configured', False)
    
    def cleanup_orphaned_registrations(self):
        """Clean up orphaned registrations that no longer exist in the database"""
        try:
            from scorm_cloud.models import SCORMRegistration
            from courses.models import Topic
            
            # Get all registrations that reference non-existent topics
            orphaned_registrations = []
            
            for registration in SCORMRegistration.objects.all():
                # Check if the registration's topic still exists
                topic_id = None
                try:
                    # Try to extract topic ID from registration ID (format: REG_{topic_id}_{user_id}_{hash})
                    if registration.registration_id.startswith('REG_'):
                        parts = registration.registration_id.split('_')
                        if len(parts) >= 3:
                            topic_id = int(parts[1])
                except (ValueError, IndexError):
                    continue
                
                if topic_id:
                    # Check if topic exists
                    if not Topic.objects.filter(id=topic_id).exists():
                        orphaned_registrations.append(registration)
            
            # Log orphaned registrations
            if orphaned_registrations:
                logger.info(f"Found {len(orphaned_registrations)} orphaned registrations")
                for reg in orphaned_registrations:
                    logger.info(f"Orphaned registration: {reg.registration_id} (topic may have been deleted)")
            
            return orphaned_registrations
            
        except Exception as e:
            logger.error(f"Error cleaning up orphaned registrations: {str(e)}")
            return []
        
        # Set up HTTP retry configuration with safe methods only
        retry = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[408, 429, 500, 502, 503, 504],
            # Only retry safe methods to avoid issues with method conflicts
            allowed_methods=["HEAD", "GET", "OPTIONS"]
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # Attempt to test connectivity if credentials are available
        if self.is_configured:
            try:
                # Simple connectivity test using GET
                test_response = self.session.get(
                    f"{self.base_url}/ping",
                    headers=self._get_headers(),
                    timeout=5,
                    verify=self.verify_ssl
                )
                
                if test_response.status_code == 200:
                    logger.info("SCORM Cloud API connectivity test successful")
                else:
                    logger.warning(f"SCORM Cloud API connectivity test failed: {test_response.status_code}")
            except Exception as conn_error:
                logger.warning(f"SCORM Cloud API connectivity test failed: {str(conn_error)}")
        else:
            logger.warning("Missing or invalid SCORM Cloud credentials - SCORM features will not be available")

    def _merge_dicts(self, dict1, dict2):
        """Recursively merge two dictionaries, with dict2 values taking priority
        Used for merging configuration settings"""
        result = dict1.copy()
        
        for key, value in dict2.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                # Recursively merge nested dictionaries
                result[key] = self._merge_dicts(result[key], value)
            else:
                # Otherwise just use the value from dict2
                result[key] = value
                
        return result

    def _create_session(self):
        session = requests.Session()
        
        # Configure retry strategy for different request types
        retries = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[408, 429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "PUT", "DELETE", "OPTIONS", "POST"]
        )
        
        # Configure HTTP adapter with proper timeout settings
        adapter = HTTPAdapter(max_retries=retries)
        
        # Configure underlying urllib3 pool settings for large uploads
        adapter.init_poolmanager(
            connections=10,
            maxsize=10,
            block=False
        )
        
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        return session
    
    def _should_attempt_chunked_upload(self, file_size):
        """Determine if file should use chunked upload based on size"""
        # For files larger than 200MB, recommend chunked upload if available
        return file_size > (200 * 1024 * 1024)

    def _get_headers(self, content_type=None):
        """Get headers with proper authentication"""
        headers = {}
        
        # Add content type if specified
        if content_type:
            headers['Content-Type'] = content_type
            
        # Add basic auth header
        auth_string = base64.b64encode(f"{self.app_id}:{self.secret_key}".encode()).decode()
        headers['Authorization'] = f'Basic {auth_string}'
        
        return headers

    def _make_request(self, method, endpoint, params=None, data=None, files=None, retry_count=0, max_retries=3):
        """Make request to SCORM Cloud API with robust error handling and retry logic"""
        
        # Check if API is properly configured
        if not self.is_configured:
            logger.warning("SCORM Cloud API not configured - skipping request")
            raise SCORMCloudError(
                "SCORM Cloud is not configured. Please contact your administrator to set up SCORM Cloud integration. "
                "Required: SCORM Cloud App ID and Secret Key must be configured in the system settings."
            )
            
        try:
            # Clean up endpoint slashes
            endpoint = endpoint.strip('/')
            url = f"{self.base_url.rstrip('/')}/{endpoint}"
            
            # Get proper headers with authentication
            headers = self._get_headers('application/json' if not files else None)
            
            # Log request details (only at debug level for performance)
            logger.debug(f"=== Making {method} request to {url} ===")
            logger.debug(f"Headers: {headers}")
            if params:
                logger.debug(f"Query params: {params}")
                logger.debug(f"Request data: {json.dumps(data, indent=2)}")
            
            # Use a session with retry logic for transient errors
            if not hasattr(self, 'session') or self.session is None:
                self.session = self._create_session()
                
            # For file uploads, use streaming and longer timeouts
            if files:
                # Use tuple format for timeout: (connect_timeout, read_timeout)
                # For large files, even connection might take longer
                connect_timeout = 120  # 2 minutes for connection
                read_timeout = self.request_timeout  # Full upload timeout
                timeout = (connect_timeout, read_timeout)
                stream = True
                logger.info(f"Using file upload timeout: connect={connect_timeout}s, read={read_timeout}s")
            else:
                timeout = self.request_timeout
                stream = False
                
            response = self.session.request(
                method,
                url,
                params=params,
                json=data if not files else None,
                files=files,
                headers=headers,
                verify=self.verify_ssl,
                timeout=timeout,
                stream=stream
            )
            
            # Store last response for debugging
            self._last_response = response
            
            # For streaming responses (file uploads), ensure content is read
            if stream and response.content:
                # Force reading the complete response for streaming uploads
                _ = response.content
            
            # Log response status
            logger.debug(f"Response status: {response.status_code}")
            
            # Handle error responses
            if response.status_code >= 400:
                error_content = response.content.decode() if response.content else "No error details"
                logger.error(f"HTTP Error: {response.status_code} {response.reason} for url: {url}")
                logger.error(f"Response content: {error_content}")
                
                # Special case for rate limiting - retry with exponential backoff
                if response.status_code == 429 and retry_count < max_retries:
                    retry_after = int(response.headers.get('Retry-After', 1))
                    logger.warning(f"Rate limited by SCORM Cloud API. Retrying after {retry_after} seconds.")
                    time.sleep(retry_after * (2 ** retry_count))  # Exponential backoff
                    return self._make_request(method, endpoint, params, data, files, retry_count + 1, max_retries)
                
                # Special case for server errors - retry with exponential backoff
                if response.status_code >= 500 and retry_count < max_retries:
                    backoff_time = 1 * (2 ** retry_count)
                    logger.warning(f"SCORM Cloud server error. Retrying after {backoff_time} seconds.")
                    time.sleep(backoff_time)
                    return self._make_request(method, endpoint, params, data, files, retry_count + 1, max_retries)
                    
                # Try to parse error response for better error message
                try:
                    error_data = response.json()
                    if 'message' in error_data:
                        error_msg = f"SCORM Cloud API Error: {error_data['message']}"
                    else:
                        error_msg = f"SCORM Cloud API Error: {error_content}"
                except (ValueError, KeyError):
                    error_msg = f"SCORM Cloud API Error: HTTP {response.status_code}"
                
                raise SCORMCloudError(error_msg)
                
            # Handle 204 No Content response
            if response.status_code == 204:
                return None
            
            # Parse JSON response, with error handling
            if response.content:
                try:
                    return response.json()
                except json.JSONDecodeError as e:
                    logger.error(f"JSON parse error: {str(e)}")
                    logger.error(f"Response content: {response.content.decode()}")
                    raise SCORMCloudError(f"Invalid JSON response from SCORM Cloud API: {str(e)}")
            
            return None
            
        except requests.exceptions.Timeout as e:
            # Timeout issues - for file uploads, don't retry as they're likely to timeout again
            if files and retry_count == 0:
                logger.error(f"File upload timeout after {self.request_timeout} seconds - not retrying large file upload: {str(e)}")
                logger.error(f"Timeout details: connect_timeout={timeout[0] if isinstance(timeout, tuple) else 'N/A'}s, read_timeout={timeout[1] if isinstance(timeout, tuple) else timeout}s")
                raise SCORMCloudError(f"SCORM Cloud file upload timed out after {self.request_timeout} seconds. The file may be too large or your internet connection too slow. Consider using a smaller file or trying during off-peak hours.")
            elif retry_count < max_retries:
                backoff_time = 2 * (2 ** retry_count)
                logger.warning(f"SCORM Cloud request timeout. Retrying after {backoff_time} seconds.")
                time.sleep(backoff_time)
                return self._make_request(method, endpoint, params, data, files, retry_count + 1, max_retries)
            else:
                logger.error(f"Request timeout after {max_retries} retries: {str(e)}")
                raise SCORMCloudError(f"SCORM Cloud API request timed out after {max_retries} retries")
                
        except requests.exceptions.ConnectionError as e:
            # Connection issues - likely due to large file uploads
            if files and retry_count == 0:
                file_size_mb = 0
                if 'file' in files and hasattr(files['file'], 'seek'):
                    # Try to get file size for better error message
                    try:
                        current_pos = files['file'].tell()
                        files['file'].seek(0, 2)  # Seek to end
                        file_size_mb = files['file'].tell() / (1024 * 1024)
                        files['file'].seek(current_pos)  # Restore position
                    except:
                        pass
                
                logger.error(f"File upload connection error - not retrying large file upload: {str(e)}")
                
                if file_size_mb > 300:
                    raise SCORMCloudError(f"SCORM Cloud file upload failed due to connection issues with large file ({file_size_mb:.1f}MB). "
                                        f"Recommendations: 1) Try compressing the SCORM package, 2) Split content into smaller modules, "
                                        f"3) Check your internet connection stability, 4) Try uploading during off-peak hours.")
                else:
                    raise SCORMCloudError(f"SCORM Cloud file upload failed due to connection issues. Please check your internet connection and try again.")
            elif retry_count < max_retries:
                backoff_time = 2 * (2 ** retry_count)
                logger.warning(f"SCORM Cloud connection error. Retrying after {backoff_time} seconds.")
                time.sleep(backoff_time)
                return self._make_request(method, endpoint, params, data, files, retry_count + 1, max_retries)
            else:
                logger.error(f"SCORM Cloud API connection failed after {max_retries} retries: {str(e)}")
                raise SCORMCloudError(f"SCORM Cloud connection failed after multiple retries.")
                
        except requests.exceptions.RequestException as e:
            logger.error(f"API request error: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Error response content: {e.response.content.decode()}")
            raise SCORMCloudError(f"SCORM Cloud API request failed: {str(e)}")
        
        except Exception as e:
            logger.error(f"Unexpected error in SCORM Cloud API request: {str(e)}")
            raise SCORMCloudError(f"Unexpected error in SCORM Cloud API request: {str(e)}")

    def upload_package(self, file_path, course_id=None, may_create_new_version=True, title=None, retry_count=0, max_retries=2):
        """Upload SCORM package to SCORM Cloud with enhanced error handling and duplicate detection"""
        try:
            logger.info("=== Starting SCORM Package Upload ===")
            logger.info(f"File: {file_path}")
            
            # Generate a unique course ID if not provided
            if not course_id:
                import uuid
                course_id = f"LMS_{uuid.uuid4().hex[:12]}"
            else:
                # Ensure the provided course ID is unique by checking for existing courses
                try:
                    existing_course = self._make_request('GET', f'courses/{course_id}')
                    if existing_course:
                        logger.warning(f"Course ID {course_id} already exists, generating unique ID")
                        import uuid
                        unique_suffix = uuid.uuid4().hex[:8]
                        course_id = f"{course_id}_{unique_suffix}"
                        logger.info(f"Using unique course ID: {course_id}")
                except Exception as e:
                    # If we can't check, assume it's safe to use
                    logger.debug(f"Could not check for existing course {course_id}: {str(e)}")
            
            logger.info(f"Course ID: {course_id}")

            if not os.path.exists(file_path):
                raise SCORMCloudError(f"File not found: {file_path}")
            
            # Check file size - SCORM Cloud has a limit
            file_size = os.path.getsize(file_path)
            max_size = 600 * 1024 * 1024  # Default 600MB
            if file_size > max_size:
                raise SCORMCloudError(f"File too large ({file_size / (1024*1024):.2f}MB). Maximum size is {max_size / (1024*1024):.0f}MB.")
            
            # Check file extension (now using local storage)
            _, ext = os.path.splitext(file_path)
            if ext.lower() not in ['.zip', '.pif']:
                logger.warning(f"Unusual file extension: {ext}. SCORM packages are usually .zip files.")

            # Validate that the file is actually a valid ZIP file (now using local storage)
            import zipfile
            with zipfile.ZipFile(file_path, 'r') as zip_file:
                # Test the ZIP file integrity
                zip_file.testzip()
                # Check if it contains typical SCORM files
                file_list = zip_file.namelist()
                has_manifest = any('imsmanifest.xml' in f.lower() for f in file_list)
            
            # Check for SCORM manifest
            if not has_manifest:
                logger.warning(f"ZIP file does not contain imsmanifest.xml - may not be a valid SCORM package")
            
            logger.info(f"File validation passed - valid ZIP file with {file_size/(1024*1024):.2f}MB")

            logger.info(f"Starting file upload of {file_size/(1024*1024):.2f}MB")
            
            # Estimate upload time and warn user
            # Use more conservative speed for very large files (0.5 Mbps for >500MB files)
            file_size_mb = file_size / (1024 * 1024)
            if file_size > 500 * 1024 * 1024:
                estimated_minutes = (file_size * 8) / (512 * 1024) / 60  # Convert to minutes at 0.5 Mbps
            else:
                estimated_minutes = (file_size * 8) / (1024 * 1024) / 60  # Convert to minutes at 1 Mbps
                
            if estimated_minutes > 5:
                logger.warning(f"Large file upload estimated to take {estimated_minutes:.1f} minutes. Please be patient and do not close the browser.")
            
            # Special warning for extremely large files
            if file_size_mb > 800:
                logger.warning(f"⚠️  EXTREMELY LARGE FILE: {file_size_mb:.1f}MB - Upload may take 90-120 minutes. Ensure stable connection!")
            
            # Check if file is extremely large and might fail
            if file_size > (800 * 1024 * 1024):  # > 800MB
                logger.warning(f"File size ({file_size/(1024*1024):.1f}MB) is very large. Consider compressing the SCORM package or splitting into smaller modules.")
                
                # Show specific recommendations for large files
                recommendations = self._get_large_file_recommendations(file_size / (1024 * 1024))
                for rec in recommendations:
                    logger.warning(rec)

            # Prepare upload parameters
            params = {
                'courseId': course_id,
                'mayCreateNewVersion': 'true' if may_create_new_version else 'false'
            }
            
            if title:
                params['title'] = title

            # Upload the file
            with open(file_path, 'rb') as f:
                files = {'file': f}
                logger.info(f"Uploading to https://cloud.scorm.com/api/v2/courses/importJobs/upload with params: {params}")
                
                # Use dynamic timeout for file uploads based on file size
                # Base timeout: 30 minutes, add 2 minutes per 100MB
                base_timeout = 1800  # 30 minutes
                size_based_timeout = (file_size / (100 * 1024 * 1024)) * 120  # 2 minutes per 100MB
                upload_timeout = max(base_timeout, int(base_timeout + size_based_timeout))
                
                # Cap at 4 hours for very large files
                upload_timeout = min(upload_timeout, 14400)  # 4 hours max
                
                logger.info(f"Using upload timeout: {upload_timeout} seconds ({upload_timeout/60:.1f} minutes)")
                original_timeout = self.request_timeout
                self.request_timeout = upload_timeout
                
                try:
                    response = self._make_request(
                        'POST',
                        'courses/importJobs/upload',
                        params=params,
                        files=files
                    )
                finally:
                    # Restore original timeout
                    self.request_timeout = original_timeout

            if not response:
                raise SCORMCloudError("No response from upload endpoint")

            # Handle different response formats - sometimes SCORM Cloud returns string, sometimes JSON
            import_job_id = None
            
            try:
                if isinstance(response, dict):
                    # Standard JSON response format
                    import_job_id = response.get('result', {}).get('importJobId')
                    if not import_job_id:
                        # Try alternative response format
                        import_job_id = response.get('importJobId')
                    if not import_job_id:
                        # Try simple 'result' key - SCORM Cloud sometimes returns {'result': 'importJobId'}
                        result_value = response.get('result')
                        if result_value:
                            # Handle case where result is a string or dict
                            if isinstance(result_value, str):
                                import_job_id = result_value
                            elif isinstance(result_value, dict) and 'importJobId' in result_value:
                                import_job_id = result_value['importJobId']
                            else:
                                import_job_id = result_value
                            logger.info(f"Got import job ID from 'result' key: {import_job_id}")
                elif isinstance(response, str):
                    # Sometimes SCORM Cloud returns just the import job ID as a string
                    # Remove any quotes and whitespace
                    import_job_id = response.strip().strip('"')
                    logger.info(f"Got import job ID as string: {import_job_id}")
                else:
                    logger.error(f"Unexpected response type: {type(response)}, content: {response}")
            except Exception as parse_error:
                logger.error(f"Error parsing upload response: {parse_error}")
                logger.error(f"Response type: {type(response)}, content: {response}")
                # Try to extract import job ID from dict if it's a dict with 'result' key
                if isinstance(response, dict) and 'result' in response:
                    result_value = response['result']
                    if isinstance(result_value, str):
                        import_job_id = result_value
                    elif isinstance(result_value, dict) and 'importJobId' in result_value:
                        import_job_id = result_value['importJobId']
                    else:
                        import_job_id = result_value
                    logger.info(f"Fallback: extracted import job ID from result key: {import_job_id}")
                elif response:
                    import_job_id = str(response).strip().strip('"')
                    logger.info(f"Fallback: extracted import job ID as string: {import_job_id}")
            
            if not import_job_id:
                logger.error(f"No import job ID in response: {response} (type: {type(response)})")
                raise SCORMCloudError("No import job ID returned from upload")

            logger.info(f"Upload successful, import job ID: {import_job_id}")

            # Wait for import to complete with extended timeout
            try:
                logger.info(f"Waiting for import job {import_job_id} to complete...")
                # Dynamic import timeout based on file size (minimum 10 minutes, add 1 minute per 100MB)
                import_timeout = max(600, int(600 + (file_size / (100 * 1024 * 1024)) * 60))
                import_timeout = min(import_timeout, 3600)  # Cap at 1 hour
                logger.info(f"Using import timeout: {import_timeout} seconds ({import_timeout/60:.1f} minutes)")
                import_result = self._wait_for_import(import_job_id, timeout=import_timeout)
                if not import_result:
                    raise SCORMCloudError("Import job timed out or returned no result")
                logger.info(f"Import completed successfully: {import_result}")
            except Exception as e:
                error_msg = str(e)
                logger.error(f"Import process failed: {error_msg}")
                
                # Check for specific duplicate error
                if 'duplicate external package id' in error_msg.lower():
                    logger.warning("Duplicate package detected, checking if course exists anyway")
                    
                    # Try to get the course details to see if it was created despite the error
                    try:
                        course = self._make_request('GET', f'courses/{course_id}')
                        if course:
                            logger.warning(f"Import had duplicate error but course exists. Proceeding with course ID: {course_id}")
                            return {'id': course_id, 'title': course.get('title', title or 'Unknown')}
                    except Exception as check_error:
                        logger.error(f"Failed to check if course exists after duplicate error: {str(check_error)}")
                    
                    # If the original course_id exists, try with a unique suffix
                    if retry_count < max_retries:
                        import uuid
                        unique_suffix = uuid.uuid4().hex[:8]
                        new_course_id = f"{course_id.split('_')[0]}_{uuid.uuid4().hex[:12]}"
                        logger.info(f"Retrying with unique course ID: {new_course_id}")
                        return self.upload_package(file_path, new_course_id, may_create_new_version, title, retry_count + 1, max_retries)
                    else:
                        raise SCORMCloudError(f"Failed to upload due to duplicates after {max_retries} retries")
                
                # Check if course was created despite import issues
                try:
                    course = self._make_request('GET', f'courses/{course_id}')
                    if course:
                        logger.warning(f"Import had issues but course exists. Proceeding with course ID: {course_id}")
                        return {'id': course_id, 'title': course.get('title', title or 'Unknown')}
                except Exception as check_error:
                    logger.error(f"Failed to check if course exists: {str(check_error)}")
                    
                # Retry import if possible
                if retry_count < max_retries and 'duplicate' not in error_msg.lower():
                    backoff_time = 10 * (2 ** retry_count)
                    logger.warning(f"Import failed. Retrying entire upload after {backoff_time} seconds.")
                    time.sleep(backoff_time)
                    return self.upload_package(file_path, course_id, may_create_new_version, title, retry_count + 1, max_retries)
                
                raise SCORMCloudError(f"SCORM package import failed: {error_msg}")

            # Get course details with retry logic
            max_retries_course_detail = 3
            for attempt in range(max_retries_course_detail):
                try:
                    course = self._make_request('GET', f'courses/{course_id}')
                    if not course:
                        logger.error(f"No course details returned for ID: {course_id}")
                        if attempt == max_retries_course_detail - 1:
                            # Last attempt, return minimal info
                            return {'id': course_id, 'title': title or 'Unknown'}
                        time.sleep(2 * (attempt + 1))
                        continue
                        
                    logger.info(f"Course created successfully: {course_id}")
                    return course
                    
                except Exception as e:
                    logger.error(f"Failed to get course details (attempt {attempt+1}/{max_retries_course_detail}): {str(e)}")
                    if attempt == max_retries_course_detail - 1:
                        # Last attempt, return minimal info
                        return {'id': course_id, 'title': title or 'Unknown'}
                    time.sleep(2 * (attempt + 1))
            
            # Fallback in case of issues
            return {'id': course_id, 'title': title or 'Unknown'}
                
        except Exception as e:
            logger.error(f"Unexpected error in upload_package: {str(e)}")
            logger.exception("Full traceback:")
            
            # Last attempt to retry with a completely new course ID
            if retry_count < max_retries and 'duplicate' not in str(e).lower():
                backoff_time = 15 * (2 ** retry_count)
                logger.warning(f"Unexpected error. Retrying after {backoff_time} seconds.")
                time.sleep(backoff_time)
                
                # Generate a completely new course ID for retry
                import uuid
                new_course_id = f"LMS_{uuid.uuid4().hex[:12]}"
                return self.upload_package(file_path, new_course_id, may_create_new_version, title, retry_count + 1, max_retries)
                
            raise SCORMCloudError(f"Failed to upload SCORM package: {str(e)}")

    def _wait_for_import(self, import_job_id, timeout=600):
        """Wait for import job completion with enhanced error handling and recovery"""
        start_time = time.time()
        initial_wait = 2  # Start with 2 seconds
        max_wait = 30     # Max wait of 30 seconds
        current_wait = initial_wait
        error_count = 0
        max_errors = 5    # Allow some errors before giving up
        
        logger.info(f"Waiting for import job {import_job_id} to complete (timeout: {timeout}s)...")
        
        while time.time() - start_time < timeout:
            try:
                result = self._make_request('GET', f'courses/importJobs/{import_job_id}')
                
                if not result:
                    error_count += 1
                    logger.warning(f"Empty response checking import status (error {error_count}/{max_errors})")
                    if error_count >= max_errors:
                        logger.error("Too many empty responses, giving up")
                        break
                    time.sleep(current_wait)
                    current_wait = min(current_wait * 1.5, max_wait)
                    continue
                
                # Reset error count on successful response
                error_count = 0
                
                status = result.get('status', '').upper()
                
                logger.info(f"Import status: {status}")
                
                if status == 'COMPLETE':
                    logger.info(f"Import job {import_job_id} completed successfully")
                    return result
                elif status == 'ERROR':
                    error_msg = result.get('message', 'Unknown error')
                    logger.error(f"Import job {import_job_id} failed: {error_msg}")
                    raise SCORMCloudError(f"Import failed: {error_msg}")
                elif status == 'CANCELLED':
                    logger.error(f"Import job {import_job_id} was cancelled")
                    raise SCORMCloudError("Import was cancelled")
                elif status in ['RUNNING', 'CREATED', 'QUEUED']:
                    # Normal processing status, continue waiting
                    pass
                else:
                    logger.warning(f"Unknown import status: {status}")
                
                # Adaptive wait times - start small and increase
                time.sleep(current_wait)
                current_wait = min(current_wait * 1.2, max_wait)  # Gentle increase
                
            except SCORMCloudError:
                # Re-raise SCORMCloudErrors (these are final)
                raise
            except Exception as e:
                error_count += 1
                logger.warning(f"Error checking import status (error {error_count}/{max_errors}): {str(e)}")
                
                if error_count >= max_errors:
                    logger.error(f"Too many errors checking import status, giving up")
                    raise SCORMCloudError(f"Import status check failed after {max_errors} errors: {str(e)}")
                
                # Exponential backoff on errors
                error_wait = min(current_wait * (2 ** error_count), max_wait)
                time.sleep(error_wait)
        
        # Timeout reached
        elapsed_time = time.time() - start_time
        logger.error(f"Import job {import_job_id} timed out after {elapsed_time:.0f} seconds")
        
        # Before giving up, try one final status check
        try:
            logger.info("Performing final status check before timeout...")
            result = self._make_request('GET', f'courses/importJobs/{import_job_id}')
            if result:
                status = result.get('status', '').upper()
                logger.info(f"Final status check - Import status: {status}")
                
                if status == 'COMPLETE':
                    logger.warning("Import actually completed during timeout, returning success")
                    return result
                elif status == 'ERROR':
                    error_msg = result.get('message', 'Unknown error')
                    logger.error(f"Import failed during timeout: {error_msg}")
                    raise SCORMCloudError(f"Import failed: {error_msg}")
        except Exception as final_check_error:
            logger.error(f"Final status check failed: {str(final_check_error)}")
        
        raise SCORMCloudError(f"Import timeout exceeded ({timeout} seconds)")

    def create_registration(self, course_id, learner_id, registration_id=None):
        """Create registration for learner with proper user information"""
        try:
            # CRITICAL FIX: Ensure we're using the correct course_id parameter
            if not course_id:
                raise SCORMCloudError("Course ID is required for registration creation")
            
            logger.info(f"Creating registration: course_id={course_id}, learner_id={learner_id}, registration_id={registration_id}")
            
            # Get or create dispatch
            dispatch = self._ensure_dispatch(course_id, "default_lms_destination")
            
            # Get user info from Django User model
            User = get_user_model()
            try:
                user = User.objects.get(id=learner_id)
                # Create registration with full learner info
                registration_data = {
                    'courseId': course_id,  # Use the provided course_id
                    'learner': {
                        'id': str(learner_id),
                        'firstName': user.first_name or user.username,
                        'lastName': user.last_name or '',
                        'email': user.email
                    }
                }
            except User.DoesNotExist:
                # Fallback to basic registration if user not found
                registration_data = {
                    'courseId': course_id,  # Use the provided course_id
                    'learner': {'id': str(learner_id)}
                }
            
            if registration_id:
                registration_data['registrationId'] = registration_id
            if dispatch:
                registration_data['dispatchId'] = dispatch['id']

            logger.info(f"Creating registration with data: {json.dumps(registration_data, indent=2)}")
            response = self._make_request('POST', 'registrations', data=registration_data)
            
            # A 204 response means success for registration creation
            if response is None:
                return registration_data
            
            return response
            
        except Exception as e:
            logger.error(f"Registration creation failed: {str(e)}")
            raise SCORMCloudError(str(e))

    def _create_dispatch(self, course_id, destination_id):
        """Create a new dispatch for a course"""
        try:
            dispatch_data = {
                "courseId": course_id,
                "destinationId": destination_id,
                "enabled": True,
                "allowNewRegistrations": True
            }
            
            response = self._make_request('POST', 'dispatch/dispatches', data=dispatch_data)
            if response:
                return response
            return None
            
        except Exception as e:
            logger.error(f"Failed to create dispatch: {str(e)}")
            return None

    def _ensure_dispatch(self, course_id, destination_id):
        try:
            # First ensure destination exists
            destination = self._ensure_destination(destination_id)
            if not destination:
                logger.warning(f"Could not ensure destination {destination_id}, creating default")
                # Create a default destination if the specified one fails
                default_dest_id = f"d_default_{uuid.uuid4().hex[:8]}"
                destination = self._ensure_destination(default_dest_id)
                if not destination:
                    logger.error("Could not create any destination")
                    return None
                destination_id = default_dest_id
            
            # Add retry logic for dispatch creation
            max_retries = 3
            for attempt in range(max_retries):
                # Check existing dispatches
                try:
                    dispatches = self._make_request(
                        'GET',
                        'dispatch/dispatches',
                        params={
                            'courseId': course_id,
                            'destinationId': destination_id
                        }
                    )

                    if dispatches and dispatches.get('dispatches'):
                        logger.info(f"Found existing dispatch for course {course_id}")
                        return dispatches['dispatches'][0]
                except Exception as e:
                    logger.warning(f"Error checking existing dispatches: {str(e)}")

                # Create new dispatch with explicit verification
                dispatch = self._create_dispatch(course_id, destination_id)
                if dispatch:
                    logger.info(f"Successfully created dispatch for course {course_id}")
                    return dispatch
                    
                if attempt < max_retries - 1:
                    time.sleep(2)  # Add delay between retries
                
            logger.warning(f"Failed to create dispatch after {max_retries} attempts, returning None")
            return None

        except Exception as e:
            logger.error(f"Dispatch verification failed: {str(e)}")
            return None

    def _ensure_destination(self, destination_id):
        """Ensure destination exists, create if it doesn't"""
        try:
            # Check if destination exists
            response = self._make_request(
                'GET',
                'dispatch/destinations',
                params={'destinationId': destination_id}
            )
            
            if response and response.get('destinations'):
                for dest in response['destinations']:
                    if dest.get('id') == destination_id:
                        logger.info(f"Found existing destination: {destination_id}")
                        return dest
                        
            # Create destination if it doesn't exist
            logger.info(f"Creating destination: {destination_id}")
            destination_name = f"LMS Destination {destination_id}"
            destination_data = {
                "destinations": [{
                    "id": destination_id,
                    "name": destination_name,
                    "data": {
                        "name": destination_name,  # Include name in data object as required by API
                        "launchAuth": {
                            "type": "cookies",
                            "options": {}
                        },
                        "hashUserInfo": False,
                        "tags": []
                    }
                }]
            }
            
            response = self._make_request('POST', 'dispatch/destinations', data=destination_data)
            
            if response and response.get('destinations'):
                logger.info(f"Successfully created destination: {destination_id}")
                return response['destinations'][0]
                
            logger.error(f"Failed to create destination {destination_id}")
            return None
            
        except Exception as e:
            logger.error(f"Error ensuring destination {destination_id}: {str(e)}")
            return None

    def build_launch_link(self, registration_id, redirect_on_exit_url=None, additional_settings=None):
        """Build a launch link for a registration with improved error handling and configuration"""
        try:
            if not registration_id:
                logger.error("No registration ID provided")
                return None
            
            # Check if SCORM Cloud is properly configured
            if not self._is_configured():
                logger.warning(f"SCORM Cloud not configured - cannot build launch link for {registration_id}")
                return None
                
            # Try to get registration first to verify it exists and get course ID
            try:
                registration_data = self._make_request(
                    'GET',
                    f'registrations/{registration_id}'
                )
                
                if not registration_data:
                    logger.warning(f"Registration {registration_id} not found in SCORM Cloud - may be orphaned")
                    return None
                    
                if 'courseId' not in registration_data:
                    course_id = None
                    logger.warning(f"Registration {registration_id} exists but has no courseId - may be orphaned")
                else:
                    course_id = registration_data.get('courseId')
                    logger.info(f"Found course ID {course_id} for registration {registration_id}")
                
            except Exception as e:
                logger.warning(f"Error getting registration {registration_id}: {str(e)} - may be orphaned")
                # Try to continue without registration data check
                course_id = None
                
            # Fallback to direct content URL if we have a course ID but can't get registration data
            if (not registration_data or 'courseId' not in registration_data) and course_id:
                logger.info(f"Falling back to direct content URL for course {course_id}")
                return self.get_direct_launch_url(
                    course_id=course_id, 
                    redirect_url=redirect_on_exit_url
                )
            
            # Default settings
            launch_settings = {
                "launchMode": "Normal",
                "tracking": True,
                "startSco": "",
                "openWindowSettings": {}
            }
            
            # Set redirect URL
            if redirect_on_exit_url:
                launch_settings["redirectOnExitUrl"] = redirect_on_exit_url
                
            # Add additional settings if provided
            if additional_settings:
                self._deep_merge_settings(launch_settings, additional_settings)
            
            # Ensure redirect URL settings format is correct
            if "redirectOnExitUrl" in launch_settings and isinstance(launch_settings["redirectOnExitUrl"], dict):
                redirect_object = launch_settings["redirectOnExitUrl"]
                if "url" in redirect_object:
                    launch_settings["redirectOnExitUrl"] = redirect_object["url"]
            
            # Build and return the launch URL
            launch_response = self._make_request(
                'POST', 
                f'registrations/{registration_id}/launchLink',
                data=launch_settings
            )
            
            if launch_response and 'launchLink' in launch_response:
                return launch_response.get('launchLink')
                
            # If we couldn't get a launch link and we have a course ID, try direct content URL
            if course_id:
                logger.info(f"Falling back to direct content URL for course {course_id}")
                return self.get_direct_launch_url(
                    course_id=course_id, 
                    redirect_url=redirect_on_exit_url
                )
                
            return None
            
        except Exception as e:
            logger.error(f"Error building launch link: {str(e)}")
            
            # Try to extract course ID from registration ID
            try:
                # Check if it's a database model registration with a related package
                from django.db import models
                if registration_id.startswith('LMS_'):
                    # Try to get the registration from the database
                    from ..models import SCORMRegistration
                    reg_obj = SCORMRegistration.objects.filter(registration_id=registration_id).first()
                    if reg_obj and reg_obj.package and reg_obj.package.cloud_id:
                        course_id = reg_obj.package.cloud_id
                        logger.info(f"Found course ID {course_id} from database for registration {registration_id}")
                        return self.get_direct_launch_url(
                            course_id=course_id, 
                            redirect_url=redirect_on_exit_url
                        )
            except Exception as db_error:
                logger.error(f"Error attempting database fallback: {str(db_error)}")
                
            return None

    def _deep_merge_settings(self, target, source):
        """Helper function to deep merge settings dictionaries"""
        for key in source:
            if key in target and isinstance(target[key], dict) and isinstance(source[key], dict):
                self._deep_merge_settings(target[key], source[key])
            else:
                target[key] = source[key]

    def get_launch_url(self, registration_id, redirect_on_exit_url=None):
        """Get launch URL for a registration with optional redirect"""
        try:
            logger.info(f"Getting launch URL for registration: {registration_id}")
            launch_url = self.build_launch_link(registration_id, redirect_on_exit_url)
            
            if not launch_url:
                logger.error("Failed to build launch URL")
                raise SCORMCloudError("Failed to build launch URL")
                
            logger.info(f"Launch URL: {launch_url}")
            return launch_url
            
        except Exception as e:
            logger.error(f"Failed to get launch URL: {str(e)}")
            raise SCORMCloudError(str(e))

    def get_result_for_registration(self, registration_id):
        """Get registration progress details"""
        try:
            return self._make_request(
                'GET',
                f'registrations/{registration_id}',
                params={
                    'includeChildResults': 'true',
                    'includeInteractionsAndObjectives': 'true',
                    'includeRuntime': 'true'
                }
            )
        except Exception as e:
            logger.error(f"Failed to get registration results: {str(e)}")
            return None

    def get_all_courses(self):
        """Get all courses"""
        try:
            courses = []
            response = self._make_request('GET', 'courses')
            
            while True:
                if response.get('courses'):
                    courses.extend(response['courses'])
                
                if not response.get('more'):
                    break
                    
                response = self._make_request('GET', 'courses', params={'more': response['more']})
            
            return courses
            
        except Exception as e:
            logger.error(f"Failed to get courses: {str(e)}")
            return []

    def get_all_registrations(self):
        """Get all registrations"""
        try:
            registrations = []
            response = self._make_request('GET', 'registrations')
            
            while True:
                if response.get('registrations'):
                    registrations.extend(response['registrations'])
                
                if not response.get('more'):
                    break
                    
                response = self._make_request('GET', 'registrations', params={'more': response['more']})
            
            return registrations
            
        except Exception as e:
            logger.error(f"Failed to get registrations: {str(e)}")
            return []

    def clean_up(self, course_id, registration_id):
        """Delete course and registration"""
        try:
            if registration_id:
                self._make_request('DELETE', f'registrations/{registration_id}')
            if course_id:
                self._make_request('DELETE', f'courses/{course_id}')
        except Exception as e:
            logger.error(f"Cleanup failed: {str(e)}")

    def get_dispatch_launch_url(self, dispatch_id, registration_id):
        """Get launch URL for a dispatch"""
        try:
            response = self._make_request(
                'GET',
                f'dispatch/dispatches/{dispatch_id}/registrations/{registration_id}/launchLink'
            )
            return response.get('launchLink')
        except Exception as e:
            logger.error(f"Failed to get dispatch launch URL: {str(e)}")
            return None

    def reset_dispatch_registration_count(self, dispatch_id):
        """Reset registration count for a dispatch"""
        try:
            return self._make_request('POST', f'dispatch/dispatches/{dispatch_id}/reset')
        except Exception as e:
            logger.error(f"Failed to reset dispatch registration count: {str(e)}")
            return None

    def create_destination(self, destination_data):
        """Create a new destination in SCORM Cloud.
        
        Args:
            destination_data (dict): Dictionary containing destination data with required structure:
                {
                    "destinations": [
                        {
                            "name": "string",
                            "data": {
                                "launchAuth": {
                                    "type": "string",
                                    "options": {}
                                },
                                "tags": []
                            }
                        }
                    ]
                }
        """
        try:
            # Ensure destination_data has proper structure
            if not isinstance(destination_data, dict):
                raise SCORMCloudError("Destination data must be a dictionary")
                
            if 'destinations' not in destination_data:
                destination_data = {'destinations': [destination_data]}
                
            # Validate each destination
            for dest in destination_data['destinations']:
                # Ensure name exists and is valid
                if 'name' not in dest or not dest['name'] or not dest['name'].strip():
                    # Generate a fallback name if missing or empty
                    dest['name'] = f"LMS_Destination_{uuid.uuid4().hex[:8]}"
                    logger.warning(f"Missing destination name, using generated name: {dest['name']}")
                
                # Ensure name is properly formatted (at least 3 chars)
                if len(dest['name'].strip()) < 3:
                    dest['name'] = f"{dest['name'].strip()}_extended_{uuid.uuid4().hex[:6]}"
                    logger.warning(f"Destination name too short, extended to: {dest['name']}")
                
                # Ensure data structure exists
                if 'data' not in dest:
                    dest['data'] = {}
                
                # Copy name to data.name as the API expects it there
                dest['data']['name'] = dest['name'].strip()
                
                if 'launchAuth' not in dest['data']:
                    dest['data']['launchAuth'] = {'type': 'cookies', 'options': {}}
                if 'options' not in dest['data']['launchAuth']:
                    dest['data']['launchAuth']['options'] = {}
                if 'tags' not in dest['data']:
                    dest['data']['tags'] = []
                    
            logger.info(f"Creating destination with data: {json.dumps(destination_data, indent=2)}")
            return self._make_request('POST', 'dispatch/destinations', data=destination_data)
            
        except Exception as e:
            logger.error(f"Error creating destination: {str(e)}")
            raise SCORMCloudError(f"Failed to create destination: {str(e)}")

    def get_destination(self, destination_id):
        """Get destination details"""
        try:
            logger.info(f"Getting destination: {destination_id}")
            response = self._make_request(
                'GET',
                'dispatch/destinations',
                params={'destinationId': destination_id}
            )
            
            if response and isinstance(response.get('destinations'), list):
                for dest in response['destinations']:
                    if dest.get('id') == destination_id:
                        logger.info(f"Found destination: {dest}")
                        return dest
            logger.error(f"Destination {destination_id} not found in response: {response}")
            return None
        except Exception as e:
            logger.error(f"Failed to get destination: {str(e)}")
            return None

    def update_destination(self, destination_id, name=None, data=None):
        """Update destination settings"""
        try:
            # Get current destination data first
            current = self.get_destination(destination_id)
            if not current:
                logger.error(f"Destination {destination_id} not found")
                return None

            # Validate name
            if name is not None:
                if not name.strip() or len(name.strip()) < 3:
                    logger.warning(f"Invalid destination name provided: '{name}'. Using fallback.")
                    name = f"LMS_Destination_{uuid.uuid4().hex[:8]}"
            
            # Use validated name or current name
            final_name = name if name is not None else current.get('name', f"LMS_Destination_{uuid.uuid4().hex[:8]}")

            # Prepare update data
            destination_data = {
                "id": destination_id,
                "name": final_name,
                "data": {
                    "name": final_name,  # Add name to data object as required by the API
                    "launchAuth": {
                        "type": "cookies"
                    },
                    "hashUserInfo": False
                }
            }

            # Add additional data if provided
            if data:
                if not isinstance(data, dict):
                    data = {}
                destination_data["data"].update(data)

            logger.info(f"Updating destination with data: {destination_data}")
            response = self._make_request(
                'POST', 
                'dispatch/destinations', 
                data={"destinations": [destination_data]}
            )
            
            if response and isinstance(response.get('destinations'), list) and response['destinations']:
                logger.info(f"Successfully updated destination: {response['destinations'][0]}")
                return response['destinations'][0]
            logger.error(f"Invalid response format when updating destination: {response}")
            return None
            
        except Exception as e:
            logger.error(f"Failed to update destination: {str(e)}")
            return None

    def delete_destination(self, destination_id):
        """Delete a destination"""
        try:
            return self._make_request('DELETE', f'dispatch/destinations/{destination_id}')
        except Exception as e:
            logger.error(f"Failed to delete destination: {str(e)}")
            return None

    def get_all_destinations(self):
        """Get all destinations"""
        try:
            response = self._make_request('GET', 'dispatch/destinations')
            if response and response.get('destinations'):
                return response['destinations']
            return []
        except Exception as e:
            logger.error(f"Failed to get destinations: {str(e)}")
            return []

    def get_dispatch(self, dispatch_id):
        """Get dispatch details"""
        try:
            response = self._make_request('GET', f'dispatch/dispatches/{dispatch_id}')
            return response
        except Exception as e:
            logger.error(f"Failed to get dispatch: {str(e)}")
            return None

    def update_dispatch(self, dispatch_id, enabled=None, allow_new_registrations=None):
        """Update dispatch settings"""
        try:
            dispatch = self.get_dispatch(dispatch_id)
            if not dispatch:
                return None

            update_data = {
                "enabled": enabled if enabled is not None else dispatch['enabled'],
                "allowNewRegistrations": allow_new_registrations if allow_new_registrations is not None else dispatch['allowNewRegistrations']
            }

            return self._make_request(
                'PUT',
                f'dispatch/dispatches/{dispatch_id}',
                data=update_data
            )
        except Exception as e:
            logger.error(f"Failed to update dispatch: {str(e)}")
            return None

    def get_registration_status(self, registration_id):
        """Get detailed registration status from SCORM Cloud"""
        try:
            return self._make_request(
                'GET',
                f'registrations/{registration_id}',
                params={
                    'includeChildResults': 'true',
                    'includeInteractionsAndObjectives': 'true',
                    'includeRuntime': 'true',
                    'includeProgress': 'true'
                }
            )
        except Exception as e:
            logger.error(f"Failed to get registration status: {str(e)}")
            return None
            
    def get_registration_progress(self, registration_id):
        """
        Get detailed registration progress data from SCORM Cloud
        This is an alias for get_registration_status to maintain API compatibility
        """
        try:
            return self.get_registration_status(registration_id)
        except Exception as e:
            logger.error(f"Failed to get registration progress: {str(e)}")
            return None

    def get_direct_launch_url(self, course_id, redirect_url=None, auth_token=None):
        """Get direct SCORM content URL with proper authentication params"""
        logger.info(f"Generating direct launch URL for course {course_id}")
        
        # Check if we're using test credentials
        if self.app_id in ['test_app_id_12345', 'temp'] or self.secret_key in ['test_secret_key_67890', 'temp']:
            raise SCORMCloudError("Cannot generate launch URL with test credentials. Please configure valid SCORM Cloud credentials.")
        
        try:
            # First try to get a preview URL, which is more reliable
            preview_data = {
                "redirectOnExitUrl": redirect_url or self.base_url
            }
            
            preview_response = self._make_request('POST', f'courses/{course_id}/preview', data=preview_data)
            if preview_response and 'launchLink' in preview_response:
                launch_url = preview_response['launchLink']
                logger.info(f"Successfully generated preview launch URL: {launch_url}")
                return launch_url
            
            # If preview fails, build a direct URL with proper authentication
            app_id = self.app_id
            secret_key = self.secret_key
            
            if not app_id:
                raise SCORMCloudError("SCORM Cloud APP_ID not configured")
            
            # Generate timestamp for auth
            timestamp = int(time.time())
            
            # Create message to sign - this is the critical part
            # Use the exact format required by SCORM Cloud
            message = f"{app_id}{timestamp}"
            
            # Generate signature using HMAC-SHA1
            signature = base64.b64encode(
                hmac.new(
                    secret_key.encode('utf-8'),
                    message.encode('utf-8'),
                    hashlib.sha1
                ).digest()
            ).decode('utf-8')
            
            # URL encode the signature
            encoded_signature = urllib.parse.quote_plus(signature)
            
            # Include all necessary authentication parameters
            auth_params = f"appId={app_id}&timestamp={timestamp}&signature={encoded_signature}"
            if redirect_url:
                auth_params += f"&redirectOnExitUrl={urllib.parse.quote_plus(redirect_url)}"
                
            # Add parameters to force launch in same window
            auth_params += "&launchMethod=OwnWindow&targetWindow=_self"
            
            # Build the complete URL
            direct_url = f"https://cloud.scorm.com/content/courses/{app_id}/{course_id}/0/scormdriver/indexAPI.html?{auth_params}"
            
            logger.info(f"Generated direct content URL: {direct_url}")
            return direct_url
            
        except Exception as e:
            logger.error(f"Failed to generate direct launch URL: {str(e)}", exc_info=True)
            return None

    def delete_course(self, course_id):
        """Delete a course from SCORM Cloud with improved error handling"""
        try:
            # First check if deletion operations are enabled
            logger.info(f"Attempting to delete SCORM course: {course_id}")
            response = self._make_request('DELETE', f'courses/{course_id}')
            logger.info(f"Successfully deleted SCORM course: {course_id}")
            return response
        except SCORMCloudError as e:
            error_str = str(e).lower()
            
            # Handle the specific case where deletion operations are not enabled
            if 'deletion operations are not enabled' in error_str:
                # Don't raise an exception - this is a configuration issue, not a failure
                logger.warning(f"SCORM Cloud deletion operations not enabled for course {course_id}")
                return {'status': 'deletion_disabled', 'message': 'Deletion operations not enabled in SCORM Cloud'}
            
            # Handle permission denied errors
            elif 'permission' in error_str or '403' in error_str:
                logger.warning(f"Permission denied when deleting SCORM course {course_id}: {error_str}")
                return {'status': 'permission_denied', 'message': 'Permission denied by SCORM Cloud'}
            
            # Handle course not found errors (already deleted)
            elif 'not found' in error_str or '404' in error_str:
                logger.info(f"SCORM course {course_id} not found in cloud (already deleted). Continuing with local cleanup.")
                return {'status': 'already_deleted', 'message': 'Course was already deleted from cloud'}
            
            # For other SCORM Cloud errors, log but don't fail
            else:
                logger.error(f"SCORM Cloud error deleting course {course_id}: {str(e)}")
                return {'status': 'error', 'message': f'Cloud deletion failed: {str(e)}'}
                
        except Exception as e:
            logger.error(f"Unexpected error deleting SCORM course {course_id}: {str(e)}")
            return {'status': 'error', 'message': f'Deletion failed: {str(e)}'}

    def _get_large_file_recommendations(self, file_size_mb):
        """Provide recommendations for handling large SCORM files"""
        recommendations = []
        
        if file_size_mb > 600:
            recommendations.extend([
                "🚨 SCORM package is EXTREMELY large (>600MB)",
                "⚠️  WARNING: Upload may take 60-90 minutes",
                "💡 Critical Recommendations:",
                "   1. Ensure stable internet connection (use wired connection)",
                "   2. Upload during off-peak hours",
                "   3. Compress ALL videos using H.264 with high compression",
                "   4. Split into 2-3 smaller SCORM modules (<300MB each)",
                "   5. Use external video hosting (YouTube, Vimeo, CDN)",
                "   6. Remove ALL unnecessary development files",
                "   7. Consider progressive loading for content"
            ])
        elif file_size_mb > 500:
            recommendations.extend([
                "📦 SCORM package is extremely large (>500MB)",
                "💡 Recommendations:",
                "   1. Compress videos/images in the package",
                "   2. Split into multiple smaller SCORM modules", 
                "   3. Use external video hosting (YouTube, Vimeo)",
                "   4. Remove unnecessary large assets",
                "   5. Check if package contains uncompressed media files"
            ])
        elif file_size_mb > 200:
            recommendations.extend([
                "⚠️  Large SCORM package detected (>200MB)",
                "💡 Consider compressing media files or splitting content"
            ])
            
        return recommendations

def get_scorm_client(user=None, branch=None, integration=None):
    """Get a SCORM Cloud API client from branch-specific integration only"""
    logger.info(f"get_scorm_client called with user={user.username if user else None}, branch={branch.name if branch else None}")
    
    if integration:
        # Use provided integration directly
        logger.info(f"Using provided integration: {integration.name}")
        return SCORMCloudAPI(
            app_id=integration.app_id,
            secret_key=integration.secret_key
        )
    
    try:
        from account_settings.models import SCORMIntegration
        
        scorm_integration = None
        target_branch = None
        
        # Determine target branch
        if user and hasattr(user, 'branch') and user.branch:
            target_branch = user.branch
        elif branch:
            target_branch = branch
        else:
            logger.error("No branch specified and user has no branch - SCORM requires branch-specific configuration")
            logger.error("SCORM Cloud integration requires a valid branch. Please ensure the user has a branch assigned or pass a branch parameter.")
            return None
        
        if not target_branch:
            logger.error("No valid branch found for SCORM integration")
            return None
        
        logger.info(f"Looking for SCORM integration for branch: {target_branch.name}")
        
        # Strategy 1: Try user's own integration first (if user provided)
        if user:
            logger.info(f"Strategy 1: Looking for user's own integration for {user.username}")
            scorm_integration = SCORMIntegration.objects.filter(
                user=user, 
                is_active=True
            ).first()
            
            if scorm_integration:
                logger.info(f"✅ Found user's own integration: {scorm_integration.name}")
            else:
                logger.info(f"❌ No user integration found")
        
        # Strategy 2: Try branch integration (any user in the branch)
        if not scorm_integration:
            logger.info(f"Strategy 2: Looking for branch integration in {target_branch.name}")
            
            scorm_integration = SCORMIntegration.objects.filter(
                user__branch=target_branch,
                is_active=True
            ).first()
            
            if scorm_integration:
                logger.info(f"✅ Using branch SCORM integration from {scorm_integration.user.username}")
            else:
                logger.error(f"❌ No SCORM integration found for branch {target_branch.name}")
                logger.error("SCORM Cloud integration is not configured for this branch. Please contact your branch administrator to set up SCORM Cloud integration in Account Settings → Integrations → SCORM Cloud.")
                return None
        
        if not scorm_integration:
            logger.error(f"No SCORM integration found for branch {target_branch.name}. Branch admin must configure SCORM credentials.")
            logger.error("SCORM Cloud integration is not configured for this branch. Please contact your branch administrator to set up SCORM Cloud integration in Account Settings → Integrations → SCORM Cloud.")
            return None
        
        # Create client with found integration
        logger.info(f"✅ Creating SCORM client with integration: {scorm_integration.name} from user {scorm_integration.user.username}")
        return SCORMCloudAPI(
            app_id=scorm_integration.app_id,
            secret_key=scorm_integration.secret_key
        )
        
    except ImportError:
        logger.error("SCORMIntegration model not available")
        return None
    except Exception as e:
        logger.error(f"Error getting SCORM client: {str(e)}")
        logger.exception("Full traceback:")
        return None

def get_branch_scorm_integration(user=None, branch=None):
    """Get the SCORM integration for a specific branch or user's branch - branch-specific only"""
    try:
        from account_settings.models import SCORMIntegration
        
        target_branch = None
        if branch:
            target_branch = branch
        elif user and hasattr(user, 'branch'):
            target_branch = user.branch
        else:
            logger.error("No branch specified for SCORM integration")
            return None
        
        if not target_branch:
            logger.error("No valid branch found for SCORM integration")
            return None
            
        # Check if branch has active SCORM integrations
        has_active_integrations = SCORMIntegration.objects.filter(
            user__branch=target_branch,
            is_active=True
        ).exists()
        
        if not has_active_integrations:
            logger.warning(f"No active SCORM integrations found for branch {target_branch.name}")
            return None
            
        # Get the first active SCORM integration for this branch
        integration = SCORMIntegration.objects.filter(
            user__branch=target_branch,
            is_active=True
        ).first()
        
        if integration:
            logger.info(f"Found SCORM integration for branch {target_branch.name}: {integration.name}")
        else:
            logger.error(f"No SCORM integration found for branch {target_branch.name}")
            
        return integration
        
    except Exception as e:
        logger.error(f"Error getting branch SCORM integration: {str(e)}")
        return None

def has_branch_scorm_enabled(user=None, branch=None):
    """Check if SCORM integration is enabled for a branch - branch-specific only"""
    target_branch = None
    if branch:
        target_branch = branch
    elif user and hasattr(user, 'branch'):
        target_branch = user.branch
    else:
        logger.warning("No branch specified for SCORM check")
        return False
        
    if not target_branch:
        logger.warning("No valid branch found for SCORM check")
        return False
    
    # Check if there are active SCORM integrations for this branch
    try:
        from account_settings.models import SCORMIntegration
        has_active_integrations = SCORMIntegration.objects.filter(
            user__branch=target_branch,
            is_active=True
        ).exists()
        
        if has_active_integrations:
            logger.info(f"SCORM integration enabled for branch {target_branch.name}")
        else:
            logger.warning(f"No active SCORM integrations found for branch {target_branch.name}")
            
        return has_active_integrations
        
    except Exception as e:
        logger.error(f"Error checking SCORM integration for branch {target_branch.name}: {str(e)}")
        return False

# Note: SCORM configuration is now branch-specific - always use get_scorm_client(user=request.user) 
# to get proper branch-specific configuration

# Export class and functions
__all__ = ['SCORMCloudAPI', 'SCORMCloudError', 'get_scorm_client', 'get_branch_scorm_integration', 'has_branch_scorm_enabled']
