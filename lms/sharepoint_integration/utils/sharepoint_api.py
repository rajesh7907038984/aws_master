"""
SharePoint API Client for LMS Integration

This module provides functionality to interact with SharePoint Online using Microsoft Graph API
and SharePoint REST API for user synchronization, document management, and data exchange.
"""

import requests
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from urllib.parse import urljoin, quote
from django.utils import timezone
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


class SharePointAPIError(Exception):
    """Custom exception for SharePoint API errors"""
    pass


class SharePointAPI:
    """SharePoint API client for LMS integration"""
    
    def __init__(self, integration_config):
        """
        Initialize SharePoint API client
        
        Args:
            integration_config: SharePointIntegration model instance
        """
        self.config = integration_config
        self.tenant_id = integration_config.tenant_id
        self.client_id = integration_config.client_id
        self.client_secret = integration_config.client_secret
        self.site_url = integration_config.site_url
        
        # Microsoft Graph and SharePoint endpoints
        self.authority = f"https://login.microsoftonline.com/{self.tenant_id}"
        self.graph_endpoint = "https://graph.microsoft.com/v1.0"
        self.sharepoint_endpoint = f"{integration_config.get_site_domain()}/_api"
        
        # Common headers
        self.headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
    
    def get_access_token(self, force_refresh: bool = False) -> Optional[str]:
        """
        Get a valid access token for SharePoint API calls
        
        Args:
            force_refresh: Force token refresh even if current token is valid
            
        Returns:
            Access token string or None if authentication fails
        """
        try:
            # Check if we have a valid token and don't need to refresh
            if not force_refresh and self.config.is_token_valid() and not self.config.needs_token_refresh():
                return self.config.access_token
            
            # Prepare token request
            token_url = f"{self.authority}/oauth2/v2.0/token"
            
            # Use refresh token if available, otherwise use client credentials
            if self.config.refresh_token and not force_refresh:
                token_data = {
                    'grant_type': 'refresh_token',
                    'refresh_token': self.config.refresh_token,
                    'client_id': self.client_id,
                    'client_secret': self.client_secret,
                    'scope': 'https://graph.microsoft.com/.default'
                }
            else:
                # Client credentials flow for application permissions
                token_data = {
                    'grant_type': 'client_credentials',
                    'client_id': self.client_id,
                    'client_secret': self.client_secret,
                    'scope': 'https://graph.microsoft.com/.default'
                }
            
            response = requests.post(token_url, data=token_data)
            
            if response.status_code == 200:
                token_info = response.json()
                
                # Update integration config with new token
                self.config.access_token = token_info['access_token']
                self.config.token_expiry = timezone.now() + timedelta(seconds=token_info['expires_in'] - 300)  # 5 min buffer
                
                # Store refresh token if provided
                if 'refresh_token' in token_info:
                    self.config.refresh_token = token_info['refresh_token']
                
                self.config.save()
                
                logger.info(f"Successfully obtained access token for SharePoint integration {self.config.name}")
                return self.config.access_token
                
            else:
                error_msg = f"Failed to obtain access token: {response.status_code} - {response.text}"
                logger.error(error_msg)
                raise SharePointAPIError(error_msg)
                
        except Exception as e:
            logger.error(f"Error getting access token: {str(e)}")
            raise SharePointAPIError(f"Authentication failed: {str(e)}")
    
    def _make_request(self, method: str, url: str, data: Dict = None, files: Dict = None, use_sharepoint_api: bool = False) -> Optional[Dict]:
        """
        Make authenticated request to Microsoft Graph or SharePoint API
        
        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            url: API endpoint URL
            data: Request payload
            files: Files to upload
            use_sharepoint_api: Use SharePoint REST API instead of Graph API
            
        Returns:
            Response data as dictionary or None
        """
        try:
            # Get access token
            token = self.get_access_token()
            if not token:
                raise SharePointAPIError("Unable to obtain access token")
            
            # Prepare headers
            headers = self.headers.copy()
            headers['Authorization'] = f'Bearer {token}'
            
            # For SharePoint REST API, add additional headers
            if use_sharepoint_api:
                headers['Accept'] = 'application/json;odata=verbose'
                headers['X-RequestDigest'] = self._get_form_digest()
            
            # Prepare request
            if files:
                # For file uploads, don't set Content-Type (let requests handle it)
                del headers['Content-Type']
                response = requests.request(method, url, headers=headers, files=files, data=data)
            else:
                if data:
                    response = requests.request(method, url, headers=headers, json=data)
                else:
                    response = requests.request(method, url, headers=headers)
            
            # Check response
            if response.status_code in [200, 201, 202, 204]:
                try:
                    return response.json() if response.content else {}
                except json.JSONDecodeError:
                    return {}
            else:
                error_msg = f"API request failed: {response.status_code} - {response.text}"
                logger.error(f"SharePoint API Error: {error_msg}")
                
                # If token expired, try once more with fresh token
                if response.status_code == 401:
                    logger.info("Token expired, refreshing and retrying...")
                    token = self.get_access_token(force_refresh=True)
                    if token:
                        headers['Authorization'] = f'Bearer {token}'
                        response = requests.request(method, url, headers=headers, json=data)
                        if response.status_code in [200, 201, 202, 204]:
                            try:
                                return response.json() if response.content else {}
                            except json.JSONDecodeError:
                                return {}
                
                raise SharePointAPIError(error_msg)
                
        except requests.exceptions.RequestException as e:
            error_msg = f"Network error during API request: {str(e)}"
            logger.error(error_msg)
            raise SharePointAPIError(error_msg)
    
    def _get_form_digest(self) -> str:
        """Get form digest value for SharePoint REST API calls"""
        try:
            # Try to get from cache first
            cache_key = f"sharepoint_form_digest_{self.config.id}"
            digest = cache.get(cache_key)
            if digest:
                return digest
            
            # Get form digest from SharePoint
            digest_url = f"{self.sharepoint_endpoint}/contextinfo"
            response = self._make_request('POST', digest_url)
            
            if response and 'd' in response and 'GetContextWebInformation' in response['d']:
                digest = response['d']['GetContextWebInformation']['FormDigestValue']
                # Cache for 25 minutes (digest expires in 30 minutes)
                cache.set(cache_key, digest, 1500)
                return digest
            
            raise SharePointAPIError("Unable to get form digest")
            
        except Exception as e:
            logger.error(f"Error getting form digest: {str(e)}")
            raise SharePointAPIError(f"Form digest error: {str(e)}")
    
    def test_connection(self) -> Tuple[bool, str]:
        """
        Test SharePoint connection and authentication
        
        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            # Test SharePoint site access directly (works with application permissions)
            site_info = self.get_site_info()
            if site_info:
                # Try to get lists to ensure we have proper permissions
                lists = self.get_lists()
                if lists is not None:  # lists can be empty array, which is valid
                    return True, f"SharePoint connection successful. Found {len(lists)} lists in site."
                else:
                    return False, "Unable to access SharePoint lists"
            else:
                return False, "Unable to access SharePoint site"
                
        except SharePointAPIError as e:
            return False, str(e)
        except Exception as e:
            return False, f"Connection test failed: {str(e)}"
    
    def get_site_info(self) -> Optional[Dict]:
        """Get SharePoint site information"""
        try:
            # Parse site URL to get hostname and site path
            from urllib.parse import urlparse
            parsed_url = urlparse(self.site_url)
            hostname = parsed_url.netloc
            site_path = parsed_url.path.strip('/')
            
            # Get site info using Graph API
            if site_path:
                site_url = f"{self.graph_endpoint}/sites/{hostname}:/{site_path}"
            else:
                site_url = f"{self.graph_endpoint}/sites/{hostname}"
            
            return self._make_request('GET', site_url)
            
        except Exception as e:
            logger.error(f"Error getting site info: {str(e)}")
            return None
    
    def get_lists(self) -> List[Dict]:
        """Get all SharePoint lists in the site"""
        try:
            site_info = self.get_site_info()
            if not site_info or 'id' not in site_info:
                raise SharePointAPIError("Unable to get site information")
            
            site_id = site_info['id']
            lists_url = f"{self.graph_endpoint}/sites/{site_id}/lists"
            
            response = self._make_request('GET', lists_url)
            
            if response and 'value' in response:
                return response['value']
            else:
                return []
                
        except Exception as e:
            logger.error(f"Error getting SharePoint lists: {str(e)}")
            return []
    
    def create_list(self, list_name: str, columns: List[Dict]) -> Optional[Dict]:
        """
        Create a new SharePoint list with specified columns
        
        Args:
            list_name: Name of the list to create
            columns: List of column definitions
            
        Returns:
            Created list information or None
        """
        try:
            site_info = self.get_site_info()
            if not site_info or 'id' not in site_info:
                raise SharePointAPIError("Unable to get site information")
            
            site_id = site_info['id']
            lists_url = f"{self.graph_endpoint}/sites/{site_id}/lists"
            
            # Prepare list data
            list_data = {
                "displayName": list_name,
                "columns": columns,
                "list": {
                    "template": "genericList"
                }
            }
            
            return self._make_request('POST', lists_url, data=list_data)
            
        except Exception as e:
            logger.error(f"Error creating SharePoint list: {str(e)}")
            return None
    
    def get_list_items(self, list_name: str, filter_query: str = None) -> List[Dict]:
        """
        Get items from a SharePoint list
        
        Args:
            list_name: Name of the SharePoint list
            filter_query: OData filter query
            
        Returns:
            List of items
        """
        try:
            site_info = self.get_site_info()
            if not site_info or 'id' not in site_info:
                raise SharePointAPIError("Unable to get site information")
            
            site_id = site_info['id']
            
            # Get list ID first
            lists = self.get_lists()
            list_id = None
            for lst in lists:
                if lst.get('displayName') == list_name:
                    list_id = lst['id']
                    break
            
            if not list_id:
                logger.warning(f"List '{list_name}' not found")
                return []
            
            items_url = f"{self.graph_endpoint}/sites/{site_id}/lists/{list_id}/items?expand=fields"
            
            if filter_query:
                items_url += f"&$filter={filter_query}"
            
            response = self._make_request('GET', items_url)
            
            if response and 'value' in response:
                return response['value']
            else:
                return []
                
        except Exception as e:
            logger.error(f"Error getting list items: {str(e)}")
            return []
    
    def create_list_item(self, list_name: str, item_data: Dict) -> Optional[Dict]:
        """
        Create an item in a SharePoint list
        
        Args:
            list_name: Name of the SharePoint list
            item_data: Item field data
            
        Returns:
            Created item information or None
        """
        try:
            site_info = self.get_site_info()
            if not site_info or 'id' not in site_info:
                raise SharePointAPIError("Unable to get site information")
            
            site_id = site_info['id']
            
            # Get list ID
            lists = self.get_lists()
            list_id = None
            for lst in lists:
                if lst.get('displayName') == list_name:
                    list_id = lst['id']
                    break
            
            if not list_id:
                raise SharePointAPIError(f"List '{list_name}' not found")
            
            items_url = f"{self.graph_endpoint}/sites/{site_id}/lists/{list_id}/items"
            
            request_data = {
                "fields": item_data
            }
            
            return self._make_request('POST', items_url, data=request_data)
            
        except Exception as e:
            logger.error(f"Error creating list item: {str(e)}")
            return None
    
    def update_list_item(self, list_name: str, item_id: str, item_data: Dict) -> Optional[Dict]:
        """
        Update an item in a SharePoint list
        
        Args:
            list_name: Name of the SharePoint list
            item_id: ID of the item to update
            item_data: Updated field data
            
        Returns:
            Updated item information or None
        """
        try:
            site_info = self.get_site_info()
            if not site_info or 'id' not in site_info:
                raise SharePointAPIError("Unable to get site information")
            
            site_id = site_info['id']
            
            # Get list ID
            lists = self.get_lists()
            list_id = None
            for lst in lists:
                if lst.get('displayName') == list_name:
                    list_id = lst['id']
                    break
            
            if not list_id:
                raise SharePointAPIError(f"List '{list_name}' not found")
            
            item_url = f"{self.graph_endpoint}/sites/{site_id}/lists/{list_id}/items/{item_id}/fields"
            
            return self._make_request('PATCH', item_url, data=item_data)
            
        except Exception as e:
            logger.error(f"Error updating list item: {str(e)}")
            return None
    
    def upload_file(self, library_name: str, file_name: str, file_content: bytes, folder_path: str = None) -> Optional[Dict]:
        """
        Upload a file to a SharePoint document library
        
        Args:
            library_name: Name of the document library
            file_name: Name of the file
            file_content: File content as bytes
            folder_path: Optional folder path within the library
            
        Returns:
            Uploaded file information or None
        """
        try:
            site_info = self.get_site_info()
            if not site_info or 'id' not in site_info:
                raise SharePointAPIError("Unable to get site information")
            
            site_id = site_info['id']
            
            # Construct upload path
            upload_path = f"/sites/{self.config.get_site_path()}/{library_name}"
            if folder_path:
                upload_path += f"/{folder_path.strip('/')}"
            upload_path += f"/{file_name}"
            
            upload_url = f"{self.graph_endpoint}/sites/{site_id}/drive/root:{upload_path}:/content"
            
            # Upload file
            headers = {'Authorization': f'Bearer {self.get_access_token()}'}
            response = requests.put(upload_url, headers=headers, data=file_content)
            
            if response.status_code in [200, 201, 202]:
                return response.json()
            else:
                raise SharePointAPIError(f"File upload failed: {response.status_code} - {response.text}")
                
        except Exception as e:
            logger.error(f"Error uploading file: {str(e)}")
            return None

    def create_document_library(self, library_name: str, description: str = "") -> Optional[Dict]:
        """
        Create a new SharePoint document library
        
        Args:
            library_name: Name of the library to create
            description: Description of the library
            
        Returns:
            Created library information or None
        """
        try:
            site_info = self.get_site_info()
            if not site_info or 'id' not in site_info:
                raise SharePointAPIError("Unable to get site information")
            
            site_id = site_info['id']
            lists_url = f"{self.graph_endpoint}/sites/{site_id}/lists"
            
            # Prepare library data
            library_data = {
                "displayName": library_name,
                "description": description,
                "list": {
                    "template": "documentLibrary"
                }
            }
            
            return self._make_request('POST', lists_url, data=library_data)
            
        except Exception as e:
            logger.error(f"Error creating SharePoint document library: {str(e)}")
            return None

    def upload_certificate(self, file_content: bytes, filename: str, student_data: Dict) -> Optional[Dict]:
        """
        Upload a certificate file to SharePoint and create registry entry
        
        Args:
            file_content: Certificate file content as bytes
            filename: Name of the certificate file
            student_data: Dictionary containing student information
            
        Returns:
            Certificate information with SharePoint link or None
        """
        try:
            # 1. Upload file to certificate library
            site_info = self.get_site_info()
            if not site_info or 'id' not in site_info:
                raise SharePointAPIError("Unable to get site information")
            
            site_id = site_info['id']
            
            # Get certificate library
            lists = self.get_lists()
            cert_library = None
            for lst in lists:
                if lst.get('displayName') == self.config.certificate_library_name:
                    cert_library = lst
                    break
            
            if not cert_library:
                raise SharePointAPIError(f"Certificate library '{self.config.certificate_library_name}' not found")
            
            library_id = cert_library['id']
            
            # Upload file
            upload_url = f"{self.graph_endpoint}/sites/{site_id}/lists/{library_id}/drive/root:/{filename}:/content"
            
            headers = {'Authorization': f'Bearer {self.get_access_token()}'}
            response = requests.put(upload_url, headers=headers, data=file_content)
            
            if response.status_code in [200, 201]:
                file_info = response.json()
                
                # 2. Create registry entry
                registry_data = {
                    'LMSCertificateID': student_data.get('certificate_id', ''),
                    'StudentName': student_data.get('student_name', ''),
                    'StudentEmail': student_data.get('student_email', ''),
                    'StudentID': student_data.get('student_id', ''),
                    'CourseID': student_data.get('course_id', ''),
                    'CourseName': student_data.get('course_name', ''),
                    'Branch': student_data.get('branch', ''),
                    'CertificateNumber': student_data.get('certificate_number', ''),
                    'IssueDate': student_data.get('issue_date', datetime.now().isoformat()),
                    'ExpiryDate': student_data.get('expiry_date', ''),
                    'Status': 'issued',
                    'CertificateLink': file_info.get('webUrl', ''),
                    'DownloadCount': 0,
                    'FinalScore': student_data.get('final_score', 0),
                    'CompletionDate': student_data.get('completion_date', ''),
                    'UpdatedDate': datetime.now().isoformat()
                }
                
                # Add to certificate registry
                registry_result = self.create_list_item("LMS Certificate Registry", registry_data)
                
                if registry_result:
                    logger.info(f"Successfully uploaded certificate for {student_data.get('student_name')} and created registry entry")
                    return {
                        'file_info': file_info,
                        'registry_entry': registry_result,
                        'download_url': file_info.get('webUrl', ''),
                        'success': True
                    }
                else:
                    logger.warning(f"Certificate uploaded but failed to create registry entry for {student_data.get('student_name')}")
                    return {
                        'file_info': file_info,
                        'download_url': file_info.get('webUrl', ''),
                        'success': True,
                        'registry_warning': 'Failed to create registry entry'
                    }
            else:
                raise SharePointAPIError(f"Failed to upload certificate: {response.status_code} - {response.text}")
                
        except Exception as e:
            logger.error(f"Error uploading certificate: {str(e)}")
            return None

    def export_analytics_data(self, analytics_data: Dict, filename: str) -> Optional[Dict]:
        """
        Export LMS analytics data to SharePoint for Power BI integration
        
        Args:
            analytics_data: Dictionary containing analytics data
            filename: Name of the analytics file
            
        Returns:
            Upload result information or None
        """
        try:
            # Convert analytics data to JSON
            json_content = json.dumps(analytics_data, indent=2, default=str).encode('utf-8')
            
            # Upload to analytics library
            site_info = self.get_site_info()
            if not site_info or 'id' not in site_info:
                raise SharePointAPIError("Unable to get site information")
            
            site_id = site_info['id']
            
            # Get analytics library
            lists = self.get_lists()
            analytics_library = None
            for lst in lists:
                if lst.get('displayName') == "LMS Analytics Data":
                    analytics_library = lst
                    break
            
            if not analytics_library:
                raise SharePointAPIError("LMS Analytics Data library not found")
            
            library_id = analytics_library['id']
            
            # Upload file
            upload_url = f"{self.graph_endpoint}/sites/{site_id}/lists/{library_id}/drive/root:/{filename}:/content"
            
            headers = {'Authorization': f'Bearer {self.get_access_token()}'}
            response = requests.put(upload_url, headers=headers, data=json_content)
            
            if response.status_code in [200, 201]:
                file_info = response.json()
                logger.info(f"Successfully exported analytics data: {filename}")
                return file_info
            else:
                raise SharePointAPIError(f"Failed to export analytics data: {response.status_code} - {response.text}")
                
        except Exception as e:
            logger.error(f"Error exporting analytics data: {str(e)}")
            return None

    def setup_sharepoint_structure(self) -> Dict[str, bool]:
        """
        Auto-setup all required SharePoint lists and libraries for LMS integration
        
        Returns:
            Dictionary with setup status for each component
        """
        setup_results = {}
        
        try:
            # Get existing lists to avoid duplicates
            existing_lists = self.get_lists()
            existing_list_names = [lst.get('displayName', '') for lst in existing_lists]
            
            # 1. Setup LMS Users List
            if self.config.user_list_name not in existing_list_names:
                user_columns = [
                    {"name": "LMSUserID", "text": {}},
                    {"name": "Username", "text": {}},
                    {"name": "Email", "text": {}},
                    {"name": "FirstName", "text": {}},
                    {"name": "LastName", "text": {}},
                    {"name": "Role", "choice": {"choices": ["globaladmin", "superadmin", "admin", "instructor", "learner"]}},
                    {"name": "Branch", "text": {}},
                    {"name": "DateOfBirth", "dateTime": {}},
                    {"name": "Gender", "choice": {"choices": ["Male", "Female", "Other", "Prefer not to say"]}},
                    {"name": "Phone", "text": {}},
                    {"name": "Address", "text": {}},
                    {"name": "StudyArea", "text": {}},
                    {"name": "Qualifications", "text": {}},
                    {"name": "JobRole", "text": {}},
                    {"name": "Industry", "text": {}},
                    {"name": "Skills", "text": {}},
                    {"name": "LastLogin", "dateTime": {}},
                    {"name": "IsActive", "boolean": {}},
                    {"name": "ProfileCompletion", "number": {}},
                    {"name": "CreatedDate", "dateTime": {}},
                    {"name": "UpdatedDate", "dateTime": {}}
                ]
                result = self.create_list(self.config.user_list_name, user_columns)
                setup_results['user_list'] = result is not None
                logger.info(f"Created SharePoint user list: {self.config.user_list_name}")
            else:
                setup_results['user_list'] = True
                logger.info(f"SharePoint user list already exists: {self.config.user_list_name}")

            # 2. Setup Course Enrollments List
            if self.config.enrollment_list_name not in existing_list_names:
                enrollment_columns = [
                    {"name": "LMSEnrollmentID", "text": {}},
                    {"name": "UserEmail", "text": {}},
                    {"name": "UserID", "text": {}},
                    {"name": "CourseID", "text": {}},
                    {"name": "CourseTitle", "text": {}},
                    {"name": "CourseBranch", "text": {}},
                    {"name": "EnrollmentDate", "dateTime": {}},
                    {"name": "CompletionDate", "dateTime": {}},
                    {"name": "Status", "choice": {"choices": ["enrolled", "in_progress", "completed", "withdrawn", "expired"]}},
                    {"name": "ProgressPercentage", "number": {}},
                    {"name": "TimeSpent", "number": {}},
                    {"name": "LastAccessed", "dateTime": {}},
                    {"name": "CertificateIssued", "boolean": {}},
                    {"name": "Grade", "text": {}},
                    {"name": "PassingScore", "number": {}},
                    {"name": "FinalScore", "number": {}},
                    {"name": "UpdatedDate", "dateTime": {}}
                ]
                result = self.create_list(self.config.enrollment_list_name, enrollment_columns)
                setup_results['enrollment_list'] = result is not None
                logger.info(f"Created SharePoint enrollment list: {self.config.enrollment_list_name}")
            else:
                setup_results['enrollment_list'] = True
                logger.info(f"SharePoint enrollment list already exists: {self.config.enrollment_list_name}")

            # 3. Setup Learning Progress List
            if self.config.progress_list_name not in existing_list_names:
                progress_columns = [
                    {"name": "LMSProgressID", "text": {}},
                    {"name": "UserEmail", "text": {}},
                    {"name": "UserID", "text": {}},
                    {"name": "CourseID", "text": {}},
                    {"name": "CourseName", "text": {}},
                    {"name": "TopicID", "text": {}},
                    {"name": "TopicName", "text": {}},
                    {"name": "TopicType", "choice": {"choices": ["scorm", "video", "document", "text", "audio", "web", "quiz", "assignment", "discussion"]}},
                    {"name": "ProgressPercent", "number": {}},
                    {"name": "CompletionDate", "dateTime": {}},
                    {"name": "TimeSpent", "number": {}},
                    {"name": "Attempts", "number": {}},
                    {"name": "Score", "number": {}},
                    {"name": "MaxScore", "number": {}},
                    {"name": "LastAccessed", "dateTime": {}},
                    {"name": "IsCompleted", "boolean": {}},
                    {"name": "UpdatedDate", "dateTime": {}}
                ]
                result = self.create_list(self.config.progress_list_name, progress_columns)
                setup_results['progress_list'] = result is not None
                logger.info(f"Created SharePoint progress list: {self.config.progress_list_name}")
            else:
                setup_results['progress_list'] = True
                logger.info(f"SharePoint progress list already exists: {self.config.progress_list_name}")

            # 4. Setup Course Groups List
            course_groups_list = "LMS Course Groups"
            if course_groups_list not in existing_list_names:
                course_group_columns = [
                    {"name": "LMSCourseID", "text": {}},
                    {"name": "CourseTitle", "text": {}},
                    {"name": "CourseDescription", "text": {}},
                    {"name": "Branch", "text": {}},
                    {"name": "Category", "text": {}},
                    {"name": "Language", "text": {}},
                    {"name": "DurationHours", "number": {}},
                    {"name": "EnrollmentCount", "number": {}},
                    {"name": "CompletionCount", "number": {}},
                    {"name": "Status", "choice": {"choices": ["draft", "active", "inactive", "archived"]}},
                    {"name": "IsVisible", "boolean": {}},
                    {"name": "HasPrerequisites", "boolean": {}},
                    {"name": "CreatedDate", "dateTime": {}},
                    {"name": "UpdatedDate", "dateTime": {}}
                ]
                result = self.create_list(course_groups_list, course_group_columns)
                setup_results['course_groups_list'] = result is not None
                logger.info(f"Created SharePoint course groups list: {course_groups_list}")
            else:
                setup_results['course_groups_list'] = True
                logger.info(f"SharePoint course groups list already exists: {course_groups_list}")

            # 5. Setup User Groups List
            user_groups_list = "LMS User Groups"
            if user_groups_list not in existing_list_names:
                user_group_columns = [
                    {"name": "LMSGroupID", "text": {}},
                    {"name": "GroupName", "text": {}},
                    {"name": "GroupDescription", "text": {}},
                    {"name": "Branch", "text": {}},
                    {"name": "GroupType", "choice": {"choices": ["branch_group", "course_access", "custom"]}},
                    {"name": "MemberCount", "number": {}},
                    {"name": "CreatedBy", "text": {}},
                    {"name": "IsActive", "boolean": {}},
                    {"name": "HasCourseAccess", "boolean": {}},
                    {"name": "CanCreateTopics", "boolean": {}},
                    {"name": "CanManageMembers", "boolean": {}},
                    {"name": "CreatedDate", "dateTime": {}},
                    {"name": "UpdatedDate", "dateTime": {}}
                ]
                result = self.create_list(user_groups_list, user_group_columns)
                setup_results['user_groups_list'] = result is not None
                logger.info(f"Created SharePoint user groups list: {user_groups_list}")
            else:
                setup_results['user_groups_list'] = True
                logger.info(f"SharePoint user groups list already exists: {user_groups_list}")

            # 6. Setup Assessment Results List
            assessment_list = "LMS Assessment Results"
            if assessment_list not in existing_list_names:
                assessment_columns = [
                    {"name": "LMSAssessmentID", "text": {}},
                    {"name": "UserEmail", "text": {}},
                    {"name": "UserID", "text": {}},
                    {"name": "CourseID", "text": {}},
                    {"name": "CourseName", "text": {}},
                    {"name": "AssignmentID", "text": {}},
                    {"name": "AssignmentTitle", "text": {}},
                    {"name": "QuizID", "text": {}},
                    {"name": "QuizTitle", "text": {}},
                    {"name": "Score", "number": {}},
                    {"name": "MaxScore", "number": {}},
                    {"name": "Percentage", "number": {}},
                    {"name": "Grade", "text": {}},
                    {"name": "PassingScore", "number": {}},
                    {"name": "IsPassed", "boolean": {}},
                    {"name": "Attempts", "number": {}},
                    {"name": "TimeSpent", "number": {}},
                    {"name": "SubmissionDate", "dateTime": {}},
                    {"name": "GradedDate", "dateTime": {}},
                    {"name": "Feedback", "text": {}},
                    {"name": "UpdatedDate", "dateTime": {}}
                ]
                result = self.create_list(assessment_list, assessment_columns)
                setup_results['assessment_list'] = result is not None
                logger.info(f"Created SharePoint assessment results list: {assessment_list}")
            else:
                setup_results['assessment_list'] = True
                logger.info(f"SharePoint assessment results list already exists: {assessment_list}")

            # 7. Setup Certificate Registry List
            certificate_registry = "LMS Certificate Registry"
            if certificate_registry not in existing_list_names:
                certificate_columns = [
                    {"name": "LMSCertificateID", "text": {}},
                    {"name": "StudentName", "text": {}},
                    {"name": "StudentEmail", "text": {}},
                    {"name": "StudentID", "text": {}},
                    {"name": "CourseID", "text": {}},
                    {"name": "CourseName", "text": {}},
                    {"name": "Branch", "text": {}},
                    {"name": "CertificateNumber", "text": {}},
                    {"name": "IssueDate", "dateTime": {}},
                    {"name": "ExpiryDate", "dateTime": {}},
                    {"name": "Status", "choice": {"choices": ["issued", "revoked", "expired"]}},
                    {"name": "CertificateLink", "url": {}},
                    {"name": "DownloadCount", "number": {}},
                    {"name": "LastDownloaded", "dateTime": {}},
                    {"name": "FinalScore", "number": {}},
                    {"name": "CompletionDate", "dateTime": {}},
                    {"name": "UpdatedDate", "dateTime": {}}
                ]
                result = self.create_list(certificate_registry, certificate_columns)
                setup_results['certificate_registry'] = result is not None
                logger.info(f"Created SharePoint certificate registry list: {certificate_registry}")
            else:
                setup_results['certificate_registry'] = True
                logger.info(f"SharePoint certificate registry list already exists: {certificate_registry}")

            # 8. Setup Document Libraries
            libraries_to_create = [
                (self.config.certificate_library_name, "LMS generated certificates and completion documents"),
                (self.config.reports_library_name, "LMS analytics reports and data exports"),
                (self.config.assessment_library_name, "Assessment documents, submissions, and related files"),
                ("LMS Analytics Data", "Raw analytics data files for Power BI integration")
            ]
            
            for library_name, description in libraries_to_create:
                if library_name not in existing_list_names:
                    result = self.create_document_library(library_name, description)
                    setup_results[f'{library_name.lower().replace(" ", "_")}_library'] = result is not None
                    logger.info(f"Created SharePoint document library: {library_name}")
                else:
                    setup_results[f'{library_name.lower().replace(" ", "_")}_library'] = True
                    logger.info(f"SharePoint document library already exists: {library_name}")

            # Log overall setup status
            all_success = all(setup_results.values())
            if all_success:
                logger.info("Successfully completed SharePoint structure auto-setup")
            else:
                failed_components = [k for k, v in setup_results.items() if not v]
                logger.warning(f"SharePoint setup completed with some failures: {failed_components}")
            
            return setup_results
            
        except Exception as e:
            logger.error(f"Error during SharePoint structure setup: {str(e)}")
            raise SharePointAPIError(f"Failed to setup SharePoint structure: {str(e)}")


# Singleton instance for easy access
sharepoint_api = None

def get_sharepoint_api(integration_config) -> SharePointAPI:
    """Get SharePoint API instance for a specific integration configuration"""
    return SharePointAPI(integration_config) 