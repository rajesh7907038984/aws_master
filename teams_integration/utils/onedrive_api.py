"""
OneDrive API client for Teams meeting recordings
Handles recording retrieval, download, and management from OneDrive
"""

import logging
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from django.utils import timezone

logger = logging.getLogger(__name__)


class OneDriveAPIError(Exception):
    """Custom exception for OneDrive API errors"""
    pass


class OneDriveAPI:
    """OneDrive API client for accessing Teams meeting recordings"""
    
    def __init__(self, integration):
        """
        Initialize OneDrive API client
        
        Args:
            integration: TeamsIntegration model instance (uses same Graph API credentials)
        """
        self.integration = integration
        self.base_url = "https://graph.microsoft.com/v1.0"
        self.access_token = None
        self.token_expiry = None
        
        # Initialize MSAL client for OAuth
        try:
            import msal
            self.msal_app = msal.ConfidentialClientApplication(
                client_id=integration.client_id,
                client_credential=integration.client_secret,
                authority=f"https://login.microsoftonline.com/{integration.tenant_id}"
            )
        except ImportError:
            logger.error("MSAL library not available. OneDrive integration will not work.")
            raise OneDriveAPIError("MSAL library not available")
    
    def get_access_token(self, force_refresh=False):
        """
        Get or refresh access token for Microsoft Graph API
        
        Args:
            force_refresh: Force token refresh even if current token is valid
            
        Returns:
            str: Access token
        """
        try:
            # Check if we have a valid cached token
            if not force_refresh and self.access_token and self.token_expiry:
                if timezone.now() < self.token_expiry:
                    return self.access_token
            
            # Request new token
            scopes = ["https://graph.microsoft.com/.default"]
            result = self.msal_app.acquire_token_for_client(scopes=scopes)
            
            if "access_token" in result:
                self.access_token = result["access_token"]
                expires_in = result.get("expires_in", 3600)
                self.token_expiry = timezone.now() + timedelta(seconds=expires_in - 300)  # 5 min buffer
                
                logger.info("✓ Successfully obtained OneDrive access token")
                return self.access_token
            else:
                error = result.get("error", "unknown_error")
                error_desc = result.get("error_description", "No description")
                logger.error(f"✗ Failed to obtain access token: {error} - {error_desc}")
                raise OneDriveAPIError(f"Authentication failed: {error}")
                
        except Exception as e:
            logger.error(f"Error getting access token: {str(e)}")
            raise OneDriveAPIError(f"Token acquisition failed: {str(e)}")
    
    def _make_request(self, method, endpoint, data=None, params=None, stream=False):
        """
        Make HTTP request to Microsoft Graph API
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint
            data: Request payload
            params: Query parameters
            stream: Whether to stream the response
            
        Returns:
            Response object or dict
        """
        try:
            token = self.get_access_token()
            headers = {
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            }
            
            url = f"{self.base_url}/{endpoint.lstrip('/')}"
            
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                json=data,
                params=params,
                stream=stream,
                timeout=30
            )
            
            if stream:
                return response
            
            response.raise_for_status()
            
            if response.status_code == 204:  # No content
                return {'success': True}
            
            return response.json()
            
        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code
            error_msg = f"HTTP {status_code}: {e.response.text}"
            
            # Handle specific error codes with appropriate logging level
            if status_code == 403:
                # Access denied - likely permission issue, log as warning not error
                logger.warning(f"OneDrive API access denied (403). Please verify API permissions are granted. Endpoint: {endpoint}")
                raise OneDriveAPIError("Access denied. Please ensure the app has 'Files.Read.All' or 'Sites.Read.All' permissions and admin consent is granted.")
            elif status_code == 404:
                # Not found - expected for missing resources, log as info
                logger.info(f"OneDrive API resource not found (404): {endpoint}")
                raise OneDriveAPIError(f"Resource not found: {endpoint}")
            elif status_code == 429:
                # Rate limit - log as warning
                logger.warning(f"OneDrive API rate limit exceeded (429). Retry after: {e.response.headers.get('Retry-After', 'unknown')}")
                raise OneDriveAPIError("API rate limit exceeded. Please try again later.")
            else:
                # Other errors
                logger.error(f"OneDrive API request failed: {error_msg}")
                raise OneDriveAPIError(error_msg)
        except OneDriveAPIError:
            # Re-raise our custom errors
            raise
        except Exception as e:
            logger.error(f"OneDrive API request error: {str(e)}")
            raise OneDriveAPIError(str(e))
    
    def get_user_recordings_folder(self, user_email):
        """
        Get the Recordings folder from user's OneDrive
        
        Args:
            user_email: Email of the user whose OneDrive to access
            
        Returns:
            dict: Folder information
        """
        try:
            # Get user's drive
            user_drive = self._make_request('GET', f'/users/{user_email}/drive')
            drive_id = user_drive.get('id')
            
            if not drive_id:
                raise OneDriveAPIError(f"Could not find drive for user {user_email}")
            
            # Search for Recordings folder
            search_endpoint = f'/users/{user_email}/drive/root/children'
            params = {'$filter': "name eq 'Recordings'"}
            
            results = self._make_request('GET', search_endpoint, params=params)
            folders = results.get('value', [])
            
            if folders:
                return {
                    'success': True,
                    'folder': folders[0],
                    'drive_id': drive_id
                }
            
            # If Recordings folder doesn't exist, return root
            return {
                'success': True,
                'folder': {'id': 'root', 'name': 'Root'},
                'drive_id': drive_id
            }
            
        except Exception as e:
            logger.error(f"Error getting recordings folder: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def search_recordings_for_meeting(self, user_email, meeting_id, meeting_title=None, meeting_date=None, meeting_start_time=None):
        """
        Search for recordings related to a specific meeting
        
        Args:
            user_email: Email of the admin/organizer whose OneDrive stores recordings
            meeting_id: Teams meeting ID
            meeting_title: Optional meeting title for search
            meeting_date: Optional meeting date for filtering recordings
            meeting_start_time: Optional meeting start time for filtering recordings
            
        Returns:
            dict: Search results with list of recordings
        """
        try:
            logger.info(f"🔍 Searching recordings for meeting {meeting_id} in {user_email}'s OneDrive")
            
            # Get user's drive
            user_drive = self._make_request('GET', f'/users/{user_email}/drive')
            drive_id = user_drive.get('id')
            
            # ✅ FIX: Try multiple methods to find recordings
            items = []
            results = None
            
            # Method 1: Try direct access to Recordings folder (more reliable with app permissions)
            try:
                recordings_folder_endpoint = f'/users/{user_email}/drive/root:/Recordings:/children'
                results = self._make_request('GET', recordings_folder_endpoint)
                items = results.get('value', [])
                logger.info(f"✓ Accessed Recordings folder directly, found {len(items)} items")
            except Exception as e:
                logger.info(f"Direct Recordings folder access failed: {str(e)}, trying search method")
                
                # Method 2: Fallback to search (might not work with app permissions)
                try:
                    search_query = f'.mp4'
                    if meeting_title:
                        clean_title = meeting_title.replace(' ', '_')[:50]
                        search_query = clean_title
                    
                    search_endpoint = f'/users/{user_email}/drive/root/search(q=\'{search_query}\')'
                    results = self._make_request('GET', search_endpoint)
                    items = results.get('value', [])
                    logger.info(f"✓ Search method found {len(items)} items")
                except Exception as search_error:
                    logger.warning(f"Search method also failed: {str(search_error)}")
                    items = []
            
            # Filter for video files and match by date/time if provided
            recordings = []
            
            # Calculate time window for matching recordings (meeting time ± 2 hours)
            time_window_start = None
            time_window_end = None
            if meeting_date and meeting_start_time:
                try:
                    from dateutil import parser as date_parser
                    # Parse meeting date/time
                    if isinstance(meeting_date, str):
                        meeting_date_obj = date_parser.parse(meeting_date).date()
                    else:
                        meeting_date_obj = meeting_date
                    
                    if isinstance(meeting_start_time, str):
                        meeting_start_time_obj = date_parser.parse(meeting_start_time).time()
                    else:
                        meeting_start_time_obj = meeting_start_time
                    
                    meeting_datetime = timezone.datetime.combine(meeting_date_obj, meeting_start_time_obj)
                    if not timezone.is_aware(meeting_datetime):
                        meeting_datetime = timezone.make_aware(meeting_datetime)
                    
                    # Create time window: 2 hours before meeting start to 6 hours after (more lenient)
                    time_window_start = meeting_datetime - timedelta(hours=2)
                    time_window_end = meeting_datetime + timedelta(hours=6)
                    logger.info(f"Filtering recordings created between {time_window_start} and {time_window_end}")
                except Exception as e:
                    logger.warning(f"Could not parse meeting date/time for filtering: {str(e)}")
            
            for item in items:
                if item.get('file') and item.get('name', '').lower().endswith(('.mp4', '.mkv', '.avi', '.mov')):
                    # Check if in Recordings folder path
                    parent_path = item.get('parentReference', {}).get('path', '')
                    if 'Recordings' in parent_path or 'recordings' in parent_path.lower():
                        # Filter by date/time if meeting date/time provided
                        if time_window_start and time_window_end:
                            created_str = item.get('createdDateTime')
                            if created_str:
                                try:
                                    from dateutil import parser as date_parser
                                    created_dt = date_parser.parse(created_str)
                                    if not timezone.is_aware(created_dt):
                                        created_dt = timezone.make_aware(created_dt)
                                    
                                    # Check if recording was created within time window
                                    if created_dt < time_window_start or created_dt > time_window_end:
                                        logger.debug(f"Skipping recording {item.get('name')} - created {created_dt} outside time window")
                                        continue
                                except Exception as e:
                                    logger.debug(f"Could not parse recording date {created_str}: {str(e)}")
                                    # Include recording if we can't parse date (better to include than exclude)
                        
                        recordings.append({
                            'id': item.get('id'),
                            'name': item.get('name'),
                            'size': item.get('size', 0),
                            'created': item.get('createdDateTime'),
                            'modified': item.get('lastModifiedDateTime'),
                            'webUrl': item.get('webUrl'),
                            'downloadUrl': item.get('@microsoft.graph.downloadUrl'),
                            'path': parent_path,
                            'drive_id': drive_id,
                            'mime_type': item.get('file', {}).get('mimeType', 'video/mp4')
                        })
            
            logger.info(f"✓ Found {len(recordings)} recordings for meeting")
            
            return {
                'success': True,
                'recordings': recordings,
                'drive_id': drive_id,
                'total_count': len(recordings)
            }
            
        except OneDriveAPIError as e:
            # Error already logged in _make_request, just return failure
            return {'success': False, 'error': str(e), 'recordings': []}
        except Exception as e:
            logger.error(f"Error searching recordings: {str(e)}")
            return {'success': False, 'error': str(e), 'recordings': []}
    
    def get_all_recordings(self, user_email, folder_name='Recordings', days_back=30):
        """
        Get all recordings from a user's OneDrive folder
        
        Args:
            user_email: Email of the user whose OneDrive to access
            folder_name: Name of the folder containing recordings
            days_back: How many days back to search
            
        Returns:
            dict: List of all recordings
        """
        try:
            logger.info(f"📁 Fetching all recordings from {user_email}'s OneDrive/{folder_name}")
            
            # Calculate date filter
            cutoff_date = (timezone.now() - timedelta(days=days_back)).isoformat()
            
            # Get user's drive
            user_drive = self._make_request('GET', f'/users/{user_email}/drive')
            drive_id = user_drive.get('id')
            
            # Get Recordings folder
            folder_info = self.get_user_recordings_folder(user_email)
            if not folder_info['success']:
                raise OneDriveAPIError("Could not access Recordings folder")
            
            folder_id = folder_info['folder']['id']
            
            # Get all items in the folder
            items_endpoint = f'/users/{user_email}/drive/items/{folder_id}/children'
            results = self._make_request('GET', items_endpoint)
            
            items = results.get('value', [])
            
            # Filter for video recordings
            recordings = []
            for item in items:
                if item.get('file') and item.get('name', '').lower().endswith(('.mp4', '.mkv', '.avi', '.mov')):
                    created_date = item.get('createdDateTime', '')
                    
                    # Apply date filter
                    if created_date and created_date >= cutoff_date:
                        recordings.append({
                            'id': item.get('id'),
                            'name': item.get('name'),
                            'size': item.get('size', 0),
                            'created': created_date,
                            'modified': item.get('lastModifiedDateTime'),
                            'webUrl': item.get('webUrl'),
                            'downloadUrl': item.get('@microsoft.graph.downloadUrl'),
                            'drive_id': drive_id,
                            'mime_type': item.get('file', {}).get('mimeType', 'video/mp4')
                        })
            
            logger.info(f"✓ Found {len(recordings)} recordings from last {days_back} days")
            
            return {
                'success': True,
                'recordings': recordings,
                'drive_id': drive_id,
                'total_count': len(recordings)
            }
            
        except Exception as e:
            logger.error(f"Error fetching all recordings: {str(e)}")
            return {'success': False, 'error': str(e), 'recordings': []}
    
    def get_recording_download_url(self, user_email, item_id):
        """
        Get a temporary download URL for a recording
        
        Args:
            user_email: Email of the user whose OneDrive contains the file
            item_id: OneDrive item ID
            
        Returns:
            dict: Download URL information
        """
        try:
            # Get item with download URL
            item = self._make_request('GET', f'/users/{user_email}/drive/items/{item_id}')
            
            download_url = item.get('@microsoft.graph.downloadUrl')
            
            if not download_url:
                raise OneDriveAPIError("Download URL not available")
            
            return {
                'success': True,
                'download_url': download_url,
                'name': item.get('name'),
                'size': item.get('size'),
                'expires': 'URL valid for 1 hour'
            }
            
        except Exception as e:
            logger.error(f"Error getting download URL: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def download_recording(self, user_email, item_id):
        """
        Stream download a recording file
        
        Args:
            user_email: Email of the user whose OneDrive contains the file
            item_id: OneDrive item ID
            
        Returns:
            Response object for streaming
        """
        try:
            # Get download URL
            endpoint = f'/users/{user_email}/drive/items/{item_id}/content'
            response = self._make_request('GET', endpoint, stream=True)
            
            return response
            
        except Exception as e:
            logger.error(f"Error downloading recording: {str(e)}")
            raise OneDriveAPIError(f"Download failed: {str(e)}")
    
    def get_recording_metadata(self, user_email, item_id):
        """
        Get metadata for a specific recording
        
        Args:
            user_email: Email of the user whose OneDrive contains the file
            item_id: OneDrive item ID
            
        Returns:
            dict: Recording metadata
        """
        try:
            item = self._make_request('GET', f'/users/{user_email}/drive/items/{item_id}')
            
            return {
                'success': True,
                'metadata': {
                    'id': item.get('id'),
                    'name': item.get('name'),
                    'size': item.get('size'),
                    'created': item.get('createdDateTime'),
                    'modified': item.get('lastModifiedDateTime'),
                    'created_by': item.get('createdBy', {}).get('user', {}).get('displayName'),
                    'webUrl': item.get('webUrl'),
                    'download_url': item.get('@microsoft.graph.downloadUrl'),
                    'mime_type': item.get('file', {}).get('mimeType')
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting recording metadata: {str(e)}")
            return {'success': False, 'error': str(e)}

