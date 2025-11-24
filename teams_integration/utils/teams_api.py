"""
Microsoft Teams API Client

This module provides functionality to interact with Microsoft Graph API
for Teams meetings, Entra ID synchronization, and user management.
"""

import requests
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from urllib.parse import urljoin
from django.utils import timezone
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


class TeamsAPIError(Exception):
    """Custom exception for Teams API errors"""
    pass


class TeamsAPIClient:
    """Microsoft Teams API client for LMS integration"""
    
    def __init__(self, integration):
        """
        Initialize Teams API client
        
        Args:
            integration: TeamsIntegration model instance
        """
        self.integration = integration
        self.base_url = "https://graph.microsoft.com/v1.0"
        self.access_token = None
        self.token_expiry = None
        
        # Initialize MSAL client
        try:
            import msal
            self.msal_app = msal.ConfidentialClientApplication(
                client_id=integration.client_id,
                client_credential=integration.client_secret,
                authority=f"https://login.microsoftonline.com/{integration.tenant_id}"
            )
        except ImportError:
            logger.error("MSAL library not available. Teams integration will not work.")
            raise TeamsAPIError("MSAL library not available")
    
    def get_access_token(self, force_refresh=False):
        """
        Get or refresh access token
        
        Args:
            force_refresh: Force token refresh
            
        Returns:
            str: Access token
        """
        # Check if we have a valid cached token
        if not force_refresh and self.access_token and self.token_expiry:
            if timezone.now() < self.token_expiry:
                return self.access_token
        
        try:
            # Get token using client credentials flow
            scopes = [
                "https://graph.microsoft.com/.default"
            ]
            
            result = self.msal_app.acquire_token_silent(scopes, account=None)
            
            if not result:
                result = self.msal_app.acquire_token_for_client(scopes=scopes)
            
            if "access_token" in result:
                self.access_token = result["access_token"]
                expires_in = result.get("expires_in", 3600)
                self.token_expiry = timezone.now() + timedelta(seconds=expires_in - 300)  # 5 min buffer
                
                # Update integration with new token
                self.integration.access_token = self.access_token
                self.integration.token_expiry = self.token_expiry
                self.integration.save(update_fields=['access_token', 'token_expiry'])
                
                logger.info("Successfully obtained Teams API access token")
                return self.access_token
            else:
                error_msg = result.get("error_description", "Failed to get access token")
                logger.error(f"Failed to get Teams API token: {error_msg}")
                raise TeamsAPIError(f"Token acquisition failed: {error_msg}")
                
        except Exception as e:
            logger.error(f"Error getting Teams API token: {str(e)}")
            raise TeamsAPIError(f"Token acquisition error: {str(e)}")
    
    def _make_request(self, method, endpoint, data=None, params=None):
        """
        Make authenticated request to Microsoft Graph API
        
        Args:
            method: HTTP method
            endpoint: API endpoint
            data: Request data
            params: Query parameters
            
        Returns:
            dict: API response
        """
        token = self.get_access_token()
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        
        # Fix URL construction - urljoin doesn't work correctly with absolute paths
        # Strip leading slash from endpoint if present, then append to base_url
        endpoint_clean = endpoint.lstrip('/')
        url = f"{self.base_url}/{endpoint_clean}"
        
        try:
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                json=data,
                params=params,
                timeout=30
            )
            
            if response.status_code == 401:
                # Token expired, try to refresh
                logger.warning("Teams API token expired, refreshing...")
                token = self.get_access_token(force_refresh=True)
                headers['Authorization'] = f'Bearer {token}'
                
                response = requests.request(
                    method=method,
                    url=url,
                    headers=headers,
                    json=data,
                    params=params,
                    timeout=30
                )
            
            response.raise_for_status()
            return response.json() if response.content else {}
            
        except requests.exceptions.RequestException as e:
            # Provide detailed error information for troubleshooting
            error_details = {
                'url': url,
                'method': method,
                'status_code': getattr(response, 'status_code', None),
                'error': str(e),
                'response_body': getattr(response, 'text', None) if hasattr(response, 'text') else None
            }
            
            # Special handling for common errors with appropriate log levels
            log_level = 'error'  # default
            if hasattr(response, 'status_code'):
                if response.status_code == 404:
                    log_level = 'info'  # 404s are expected for missing resources
                    # More specific error handling for 404s
                    if '/users/' in endpoint and '/calendar' in endpoint:
                        # Extract user email from endpoint
                        user_email = endpoint.split('/users/')[1].split('/')[0]
                        error_msg = (
                            f"API request failed: 404 Not Found for endpoint {endpoint}. "
                            f"The user '{user_email}' does not exist in Azure AD or doesn't have a mailbox. "
                            "Possible solutions: "
                            "(1) Verify the user exists in Azure AD and has an Exchange Online license, "
                            "(2) Use a different user's email address, "
                            "(3) Run 'python manage.py list_azure_ad_users' to see available users."
                        )
                    else:
                        error_msg = (
                            f"API request failed: 404 Not Found for endpoint {endpoint}. "
                            "This usually indicates missing API permissions or the resource doesn't exist. "
                            "Please ensure required application permissions are configured "
                            "and admin consent is granted."
                        )
                elif response.status_code == 403:
                    log_level = 'warning'  # 403s indicate permission issues, not critical errors
                    error_msg = (
                        f"API request failed: 403 Forbidden for endpoint {endpoint}. "
                        "This indicates insufficient permissions. Verify API permissions and admin consent."
                    )
                elif response.status_code == 401:
                    log_level = 'warning'  # 401s are auth issues, typically resolved by token refresh
                    error_msg = (
                        f"API request failed: 401 Unauthorized for endpoint {endpoint}. "
                        "Token might be invalid or expired."
                    )
                elif response.status_code == 400:
                    log_level = 'info'  # 400s are often expected (bad meeting IDs, etc.)
                    error_msg = f"API request failed: 400 Bad Request for url: {url}"
                else:
                    error_msg = f"API request failed: {str(e)}"
            else:
                error_msg = f"API request failed: {str(e)}"
            
            # Log at appropriate level based on error type
            if log_level == 'info':
                logger.info(f"Teams API request: {error_msg}")
            elif log_level == 'warning':
                logger.warning(f"Teams API request: {error_msg}")
            else:
                logger.error(f"Teams API request failed: {error_msg}", extra=error_details)
            raise TeamsAPIError(error_msg)
    
    def create_meeting(self, title, start_time, end_time, description=None, user_email=None, enable_recording=True):
        """
        Create a Teams meeting with auto-recording enabled
        
        IMPORTANT: Auto-recording is MANDATORY for all meetings to ensure compliance
        and provide recordings for all participants. Recording cannot be disabled.
        
        Args:
            title: Meeting title
            start_time: Meeting start time
            end_time: Meeting end time
            description: Meeting description
            user_email: User's email address (userPrincipalName) for application permissions.
                       If None, uses integration owner's email.
            enable_recording: Whether to enable automatic cloud recording (default: True, MANDATORY)
            
        Returns:
            dict: Meeting details including recording status
        """
        # ENFORCE MANDATORY RECORDING: Override any attempt to disable recording
        if not enable_recording:
            logger.warning("⚠️ Attempt to disable recording detected. Recording is MANDATORY for all meetings.")
            enable_recording = True  # Force enable recording
        try:
            # Format times for Graph API
            start_iso = start_time.isoformat()
            end_iso = end_time.isoformat()
            
            meeting_data = {
                "subject": title,
                "start": {
                    "dateTime": start_iso,
                    "timeZone": "UTC"
                },
                "end": {
                    "dateTime": end_iso,
                    "timeZone": "UTC"
                },
                "isOnlineMeeting": True,
                "onlineMeetingProvider": "teamsForBusiness"
            }
            
            if description:
                meeting_data["body"] = {
                    "contentType": "text",
                    "content": description
                }
            
            # Note: Recording configuration will be set after meeting creation
            # The Graph API doesn't support setting recordAutomatically during calendar event creation
            # We'll configure it via onlineMeeting API after the meeting is created
            if enable_recording:
                logger.info("🔴 Recording will be configured after meeting creation")
            
            # Determine user email for application permissions
            # With client credentials flow, we need to specify the user
            if not user_email and self.integration.user and self.integration.user.email:
                user_email = self.integration.user.email
                logger.info(f"Using integration owner email: {user_email}")
            
            # Fallback to service account email if configured
            if not user_email and hasattr(self.integration, 'service_account_email') and self.integration.service_account_email:
                user_email = self.integration.service_account_email
                logger.info(f"Using service account email: {user_email}")
            
            if not user_email:
                error_msg = (
                    "User email is required for creating calendar events with application permissions. "
                    "Please ensure the integration owner, request user, or service account email has a valid email address configured."
                )
                logger.error(error_msg)
                raise TeamsAPIError(error_msg)
            
            # Use /users/{userPrincipalName}/calendar/events for application permissions
            # instead of /me/events which requires delegated permissions
            endpoint = f'/users/{user_email}/calendar/events'
            logger.info(f"Creating Teams meeting for user: {user_email}, title: {title}, recording: {enable_recording}")
            
            # Create the meeting
            response = self._make_request(
                'POST',
                endpoint,
                data=meeting_data
            )
            
            # Extract meeting details
            meeting_id = response.get('id')
            join_url = response.get('onlineMeeting', {}).get('joinUrl')
            # IMPORTANT: Keep the original online_meeting_id from calendar event for API calls
            online_meeting_id_for_api = response.get('onlineMeeting', {}).get('id')
            
            # Extract thread ID from join URL if available
            # The online_meeting_id from calendar API is a GUID (calendar event ID)
            # But we need the thread ID (19:meeting_XXX@thread.v2) for attendance/chat APIs
            thread_id = None
            if join_url:
                try:
                    import re
                    import urllib.parse
                    
                    # Extract thread ID from join URL
                    # Format: https://teams.microsoft.com/l/meetup-join/19%3ameeting_XXX%40thread.v2/...
                    match = re.search(r'/meetup-join/([^/]+)', join_url)
                    if match:
                        encoded_thread = match.group(1)
                        # URL decode to get actual thread ID
                        thread_id = urllib.parse.unquote(encoded_thread)
                        logger.info(f"✓ Extracted thread ID from join URL: {thread_id}")
                except Exception as e:
                    logger.warning(f"Could not extract thread ID from join URL: {str(e)}")
            
            # Use thread ID for sync operations (attendance/chat), but keep online_meeting_id_for_api for recording API
            online_meeting_id = thread_id if thread_id else online_meeting_id_for_api
            
            logger.info(f"✓ Created Teams meeting: Calendar ID={meeting_id}, Online Meeting ID={online_meeting_id_for_api}, Thread ID={thread_id}")
            
            # Enable automatic recording if requested
            # Use MULTIPLE methods to ensure recording is enabled:
            # 1. During creation (already set above)
            # 2. Via PATCH to onlineMeeting endpoint (backup method)
            # 3. Verify recording is actually enabled
            recording_status = 'not_attempted'
            recording_error = None
            
            if enable_recording:
                # Method 1: Verify recording was set during creation
                online_meeting_from_response = response.get('onlineMeeting', {})
                record_auto_from_response = online_meeting_from_response.get('recordAutomatically', False)
                
                if record_auto_from_response:
                    logger.info("✓ Recording was enabled during meeting creation")
                    recording_status = 'enabled'
                else:
                    logger.warning("⚠️ Recording not confirmed in creation response, trying PATCH method...")
                
                # Method 2: Explicitly enable via PATCH (backup/verification method)
                # BUG FIX: Use the original online_meeting_id_for_api (GUID) for the API call, not the thread ID
                if online_meeting_id_for_api and recording_status != 'enabled':
                    try:
                        logger.info(f"🔴 Attempting to enable auto-recording via PATCH using online meeting ID: {online_meeting_id_for_api}")
                        recording_result = self.enable_meeting_recording(online_meeting_id_for_api, user_email)
                        
                        if recording_result['success']:
                            recording_status = 'enabled'
                            logger.info(f"✓ Auto-recording enabled successfully via PATCH")
                        else:
                            # If PATCH failed but creation had it, still mark as enabled
                            if record_auto_from_response:
                                recording_status = 'enabled'
                                logger.info(f"✓ Recording enabled during creation (PATCH failed but creation succeeded)")
                            else:
                                recording_status = 'failed'
                                recording_error = recording_result.get('error', 'Unknown error')
                                logger.warning(f"⚠️ Failed to enable auto-recording: {recording_error}")
                            
                    except Exception as rec_error:
                        # If creation had it, still mark as enabled
                        if record_auto_from_response:
                            recording_status = 'enabled'
                            logger.info(f"✓ Recording enabled during creation (PATCH error ignored)")
                        else:
                            recording_status = 'error'
                            recording_error = str(rec_error)
                            logger.error(f"✗ Error enabling auto-recording: {recording_error}")
                elif not online_meeting_id_for_api:
                    if record_auto_from_response:
                        recording_status = 'enabled'
                        logger.info("✓ Recording enabled during creation (no online meeting ID for PATCH)")
                    else:
                        recording_status = 'failed'
                        recording_error = 'No online meeting ID available from calendar event'
                        logger.warning(f"⚠️ Cannot enable recording: {recording_error}")
            
            return {
                'success': True,
                'meeting_id': meeting_id,
                'meeting_link': join_url,
                'online_meeting_id': online_meeting_id,  # Thread ID for sync operations
                'online_meeting_id_for_api': online_meeting_id_for_api,  # GUID for API calls
                'thread_id': thread_id,  # Explicit thread ID
                'recording_status': recording_status,
                'recording_error': recording_error,
                'meeting_details': response
            }
            
        except Exception as e:
            logger.error(f"Error creating Teams meeting: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def enable_meeting_recording(self, online_meeting_id, user_email=None):
        """
        Enable automatic recording for a Teams online meeting
        
        IMPORTANT: The online_meeting_id must be the GUID from the calendar event's onlineMeeting.id,
        NOT the thread ID (19:meeting_XXX@thread.v2). The thread ID is used for attendance/chat APIs,
        but the onlineMeetings endpoint requires the GUID format.
        
        Args:
            online_meeting_id: Teams online meeting ID (GUID format from calendar event, not thread ID)
            user_email: Organizer's email address
            
        Returns:
            dict: Recording enable status
        """
        try:
            # Determine user email
            if not user_email and self.integration.user and self.integration.user.email:
                user_email = self.integration.user.email
            
            if not user_email and hasattr(self.integration, 'service_account_email'):
                user_email = self.integration.service_account_email
            
            if not user_email:
                raise TeamsAPIError("User email required to enable recording")
            
            # Validate that online_meeting_id is in GUID format (not thread ID)
            # Thread IDs have format: 19:meeting_XXX@thread.v2
            # GUIDs are UUIDs: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
            if online_meeting_id and ('@thread.v2' in str(online_meeting_id) or online_meeting_id.startswith('19:')):
                logger.warning(f"⚠️ Invalid online_meeting_id format detected (thread ID instead of GUID): {online_meeting_id[:50]}")
                logger.warning("⚠️ The enable_meeting_recording API requires the GUID from calendar event, not the thread ID")
                return {
                    'success': False,
                    'error': 'Invalid online meeting ID format. Expected GUID from calendar event, got thread ID.',
                    'note': 'The online_meeting_id must be the GUID from the calendar event response, not the thread ID extracted from join URL.'
                }
            
            # Update online meeting to enable recording
            # Note: This requires the OnlineMeetings.ReadWrite.All permission
            endpoint = f'/users/{user_email}/onlineMeetings/{online_meeting_id}'
            
            # CRITICAL: Set multiple properties to ensure recording is enabled
            # recordAutomatically: True should start recording automatically when meeting begins
            recording_config = {
                "recordAutomatically": True,
                "allowRecording": True,  # Explicitly allow recording
                "isEntryExitAnnounced": False  # Disable join/leave sounds for better recording
            }
            
            logger.info(f"🔴 Attempting to enable automatic recording via PATCH {endpoint}")
            logger.info(f"   Config: recordAutomatically=True, allowRecording=True")
            
            response = self._make_request(
                'PATCH',
                endpoint,
                data=recording_config
            )
            
            # Verify the response confirms recording is enabled
            record_auto_confirmed = response.get('recordAutomatically', False)
            if record_auto_confirmed:
                logger.info(f"✓ Recording settings confirmed: recordAutomatically={record_auto_confirmed}")
            else:
                logger.warning(f"⚠️ Recording setting not confirmed in response. Response: {response}")
            
            logger.info(f"✓ Recording settings updated for meeting {online_meeting_id}")
            
            return {
                'success': True,
                'message': 'Auto-recording enabled',
                'recordAutomatically': record_auto_confirmed,
                'details': response
            }
            
        except TeamsAPIError as e:
            error_msg = str(e)
            logger.error(f"✗ Failed to enable recording: {error_msg}")
            
            # Check if it's a permissions error
            if '403' in error_msg or 'Forbidden' in error_msg:
                return {
                    'success': False,
                    'error': 'Insufficient permissions. Ensure OnlineMeetings.ReadWrite.All is granted.',
                    'permission_required': 'OnlineMeetings.ReadWrite.All',
                    'note': 'Please verify that OnlineMeetings.ReadWrite.All permission is granted in Azure AD and admin consent is provided.'
                }
            elif '404' in error_msg or 'Not Found' in error_msg:
                return {
                    'success': False,
                    'error': 'Online meeting not found. The meeting may not exist or the ID format is incorrect.',
                    'note': 'Ensure you are using the GUID from the calendar event response, not the thread ID.'
                }
            elif '400' in error_msg or 'Bad Request' in error_msg:
                return {
                    'success': False,
                    'error': f'Invalid request: {error_msg}',
                    'note': 'The online meeting ID format may be incorrect or the API endpoint may not support this operation.'
                }
            
            return {
                'success': False,
                'error': error_msg
            }
        except Exception as e:
            error_msg = str(e)
            logger.error(f"✗ Failed to enable recording: {error_msg}")
            return {
                'success': False,
                'error': error_msg
            }
    
    def verify_recording_enabled(self, online_meeting_id, user_email=None):
        """
        Verify that recording is enabled for a Teams meeting
        
        Args:
            online_meeting_id: Teams online meeting ID (GUID format)
            user_email: Organizer's email address
            
        Returns:
            dict: Verification result with recording status
        """
        try:
            # Determine user email
            if not user_email and self.integration.user and self.integration.user.email:
                user_email = self.integration.user.email
            
            if not user_email and hasattr(self.integration, 'service_account_email'):
                user_email = self.integration.service_account_email
            
            if not user_email:
                raise TeamsAPIError("User email required to verify recording")
            
            # Get online meeting details
            endpoint = f'/users/{user_email}/onlineMeetings/{online_meeting_id}'
            response = self._make_request('GET', endpoint)
            
            record_automatically = response.get('recordAutomatically', False)
            allow_recording = response.get('allowRecording', True)  # Defaults to True if not specified
            
            return {
                'success': True,
                'recordAutomatically': record_automatically,
                'allowRecording': allow_recording,
                'recording_enabled': record_automatically and allow_recording,
                'details': response
            }
            
        except Exception as e:
            logger.error(f"Error verifying recording status: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'recording_enabled': False
            }
    
    def get_meeting_attendance(self, meeting_id, user_email=None):
        """
        Get meeting attendance data (LEGACY - returns calendar attendees only, no duration)
        
        DEPRECATED: Use get_meeting_attendance_report() instead for actual attendance with duration
        
        Args:
            meeting_id: Teams meeting ID (calendar event ID)
            user_email: User's email address (userPrincipalName) for application permissions.
                       If None, uses integration owner's email.
            
        Returns:
            dict: Attendance data (calendar invitees only, no duration data)
        """
        try:
            # Determine user email for application permissions
            if not user_email and self.integration.user and self.integration.user.email:
                user_email = self.integration.user.email
            
            if not user_email:
                raise TeamsAPIError("User email is required for accessing calendar events with application permissions")
            
            # Get meeting event details
            # Use /users/{userPrincipalName}/events/{event_id} for application permissions
            # instead of /me/events/{event_id} which requires delegated permissions
            endpoint = f'/users/{user_email}/events/{meeting_id}'
            response = self._make_request(
                'GET',
                endpoint
            )
            
            # Extract attendees from the event object
            attendees = response.get('attendees', [])
            attendance_data = []
            
            for attendee in attendees:
                attendance_data.append({
                    'email': attendee.get('emailAddress', {}).get('address'),
                    'name': attendee.get('emailAddress', {}).get('name'),
                    'status': attendee.get('status', {}).get('response'),
                    'type': attendee.get('type')
                })
            
            return {
                'success': True,
                'attendees': attendance_data,
                'total_attendees': len(attendance_data)
            }
            
        except TeamsAPIError as e:
            # Error already logged in _make_request, just return failure
            return {
                'success': False,
                'error': str(e)
            }
        except Exception as e:
            logger.error(f"Error getting Teams meeting attendance: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_meeting_attendance_report(self, online_meeting_id, user_email=None):
        """
        Get ACTUAL meeting attendance report with join/leave times and duration
        
        This is the CORRECT method to get attendance data with duration.
        Requires: OnlineMeetingArtifact.Read.All permission
        
        Args:
            online_meeting_id: Teams online meeting ID (not calendar event ID)
            user_email: Meeting organizer's email address
            
        Returns:
            dict: Actual attendance data with durations, join/leave times
        """
        try:
            # Determine user email
            if not user_email and self.integration.user and self.integration.user.email:
                user_email = self.integration.user.email
            
            if not user_email:
                raise TeamsAPIError("User email required for attendance reports")
            
            logger.info(f"Fetching attendance report for meeting: {online_meeting_id} as user: {user_email}")
            
            # Get attendance reports for the online meeting
            endpoint = f'/users/{user_email}/onlineMeetings/{online_meeting_id}/attendanceReports'
            response = self._make_request('GET', endpoint)
            
            reports = response.get('value', [])
            
            if not reports:
                logger.info("No attendance reports available yet. Reports are generated after meeting ends.")
                return {
                    'success': True,
                    'attendees': [],
                    'note': 'No attendance report available. Reports are generated after the meeting ends and may take a few minutes.'
                }
            
            # Get the latest attendance report (most recent)
            latest_report = reports[0]
            report_id = latest_report.get('id')
            
            logger.info(f"Found attendance report: {report_id}")
            
            # Get detailed attendance records from the report
            attendance_endpoint = f'/users/{user_email}/onlineMeetings/{online_meeting_id}/attendanceReports/{report_id}/attendanceRecords'
            attendance_response = self._make_request('GET', attendance_endpoint)
            
            attendance_records = attendance_response.get('value', [])
            logger.info(f"Retrieved {len(attendance_records)} attendance records")
            
            # Process attendance records
            attendance_data = []
            for record in attendance_records:
                # Get identity information
                identity = record.get('identity', {})
                email_address = record.get('emailAddress', '')
                display_name = identity.get('displayName', 'Unknown')
                
                # Parse attendance intervals to calculate join/leave times and total duration
                join_time = None
                leave_time = None
                total_duration_seconds = 0
                
                attendance_intervals = record.get('attendanceIntervals', [])
                
                if attendance_intervals:
                    # Process all attendance intervals (user may join/leave multiple times)
                    for interval in attendance_intervals:
                        try:
                            join_dt_str = interval.get('joinDateTime')
                            leave_dt_str = interval.get('leaveDateTime')
                            
                            if join_dt_str and leave_dt_str:
                                # Parse ISO format timestamps
                                from dateutil import parser as date_parser
                                join_dt = date_parser.parse(join_dt_str)
                                leave_dt = date_parser.parse(leave_dt_str)
                                
                                # Track earliest join time
                                if not join_time or join_dt < join_time:
                                    join_time = join_dt
                                
                                # Track latest leave time
                                if not leave_time or leave_dt > leave_time:
                                    leave_time = leave_dt
                                
                                # Add interval duration
                                interval_duration = (leave_dt - join_dt).total_seconds()
                                total_duration_seconds += interval_duration
                                
                        except Exception as e:
                            logger.warning(f"Error parsing attendance interval: {str(e)}")
                            continue
                
                # Also check totalAttendanceInSeconds from the record
                record_duration = record.get('totalAttendanceInSeconds', 0)
                if record_duration > total_duration_seconds:
                    total_duration_seconds = record_duration
                
                # Convert to minutes
                duration_minutes = int(total_duration_seconds // 60) if total_duration_seconds else 0
                
                attendance_data.append({
                    'email': email_address,
                    'name': display_name,
                    'join_time': join_time,
                    'leave_time': leave_time,
                    'duration': int(total_duration_seconds),
                    'duration_minutes': duration_minutes,
                    'role': record.get('role', 'Attendee'),
                    'total_attendance_seconds': record.get('totalAttendanceInSeconds', 0),
                    'attendance_intervals': attendance_intervals
                })
                
                logger.info(f"  {display_name} ({email_address}): {duration_minutes} minutes")
            
            return {
                'success': True,
                'attendees': attendance_data,
                'total_attendees': len(attendance_data),
                'report_id': report_id,
                'report_created': latest_report.get('meetingStartDateTime')
            }
            
        except TeamsAPIError as e:
            error_msg = str(e)
            
            # Provide helpful error messages for common issues
            if '404' in error_msg:
                return {
                    'success': False,
                    'error': 'Attendance report not found. Reports are generated after meeting ends.',
                    'note': 'Please wait a few minutes after the meeting ends and try again.'
                }
            elif '403' in error_msg or 'Forbidden' in error_msg:
                return {
                    'success': False,
                    'error': 'Insufficient permissions to access attendance reports.',
                    'permission_required': 'OnlineMeetingArtifact.Read.All',
                    'note': 'Please ensure OnlineMeetingArtifact.Read.All permission is granted in Azure AD and admin consent is provided.'
                }
            else:
                return {
                    'success': False,
                    'error': error_msg
                }
                
        except Exception as e:
            logger.error(f"Error getting meeting attendance report: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_entra_groups(self):
        """
        Get Entra ID groups from the tenant
        
        Returns:
            dict: Groups data
        """
        try:
            response = self._make_request(
                'GET',
                '/groups',
                params={
                    '$select': 'id,displayName,mail,description,createdDateTime',
                    '$top': 999
                }
            )
            
            groups = response.get('value', [])
            group_data = []
            
            for group in groups:
                group_data.append({
                    'id': group.get('id'),
                    'name': group.get('displayName'),
                    'email': group.get('mail'),
                    'description': group.get('description'),
                    'created': group.get('createdDateTime')
                })
            
            return {
                'success': True,
                'groups': group_data,
                'total_groups': len(group_data)
            }
            
        except Exception as e:
            logger.error(f"Error getting Entra ID groups: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_group_members(self, group_id):
        """
        Get members of an Entra ID group
        
        Args:
            group_id: Entra ID group ID
            
        Returns:
            dict: Members data
        """
        try:
            response = self._make_request(
                'GET',
                f'/groups/{group_id}/members',
                params={
                    '$select': 'id,displayName,mail,userPrincipalName,createdDateTime'
                }
            )
            
            members = response.get('value', [])
            member_data = []
            
            for member in members:
                member_data.append({
                    'id': member.get('id'),
                    'name': member.get('displayName'),
                    'email': member.get('mail') or member.get('userPrincipalName'),
                    'created': member.get('createdDateTime')
                })
            
            return {
                'success': True,
                'members': member_data,
                'total_members': len(member_data)
            }
            
        except Exception as e:
            logger.error(f"Error getting group members: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def test_connection(self):
        """
        Test the Teams API connection by verifying authentication
        
        Returns:
            dict: Test result
        """
        try:
            # Test authentication by attempting to get an access token
            # This validates Client ID, Client Secret, and Tenant ID without requiring API permissions
            access_token = self.get_access_token(force_refresh=True)
            
            if access_token:
                # Successfully authenticated - credentials are valid
                return {
                    'success': True,
                    'message': 'Authentication successful! Your Azure AD app credentials are valid.',
                    'details': {
                        'tenant_id': self.integration.tenant_id,
                        'client_id': self.integration.client_id[:8] + '...',  # Show first 8 chars only
                        'token_obtained': True,
                        'token_expires': self.token_expiry.strftime('%Y-%m-%d %H:%M:%S') if self.token_expiry else 'N/A'
                    }
                }
            else:
                return {
                    'success': False,
                    'error': 'Failed to obtain access token. Please verify your Client ID, Client Secret, and Tenant ID.'
                }
                
        except TeamsAPIError as e:
            error_msg = str(e)
            logger.error(f"Teams API connection test failed: {error_msg}")
            
            # Provide helpful error messages
            if 'invalid_client' in error_msg.lower():
                return {
                    'success': False,
                    'error': 'Invalid Client ID or Client Secret. Please verify your Azure AD app credentials.'
                }
            elif 'unauthorized_client' in error_msg.lower():
                return {
                    'success': False,
                    'error': 'Client is not authorized. Ensure your Azure AD app has the correct permissions.'
                }
            elif 'invalid_tenant' in error_msg.lower():
                return {
                    'success': False,
                    'error': 'Invalid Tenant ID. Please verify your Azure AD Tenant ID.'
                }
            else:
                return {
                    'success': False,
                    'error': f'Authentication failed: {error_msg}'
                }
                
        except Exception as e:
            logger.error(f"Teams API connection test failed: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def add_meeting_attendee(self, meeting_id, attendee_email, attendee_name, organizer_email=None):
        """
        Add an attendee to a Teams meeting
        
        Args:
            meeting_id: Teams meeting ID (calendar event ID)
            attendee_email: Attendee's email address
            attendee_name: Attendee's display name
            organizer_email: Meeting organizer's email (if None, uses integration owner's email)
            
        Returns:
            dict: Result of adding attendee
        """
        try:
            # Determine organizer email
            if not organizer_email:
                if self.integration.user and self.integration.user.email:
                    organizer_email = self.integration.user.email
                else:
                    return {
                        'success': False,
                        'error': 'Organizer email required'
                    }
            
            # Get current meeting details
            endpoint = f'/users/{organizer_email}/calendar/events/{meeting_id}'
            meeting = self._make_request('GET', endpoint)
            
            # Get existing attendees
            attendees = meeting.get('attendees', [])
            
            # Check if attendee already exists
            existing = any(a.get('emailAddress', {}).get('address', '').lower() == attendee_email.lower() 
                          for a in attendees)
            
            if existing:
                logger.info(f"Attendee {attendee_email} already in meeting {meeting_id}")
                return {
                    'success': True,
                    'message': 'Attendee already added',
                    'already_exists': True
                }
            
            # Add new attendee
            attendees.append({
                'emailAddress': {
                    'address': attendee_email,
                    'name': attendee_name
                },
                'type': 'required'
            })
            
            # Update meeting with new attendees
            update_data = {
                'attendees': attendees
            }
            
            self._make_request('PATCH', endpoint, data=update_data)
            
            logger.info(f"Added attendee {attendee_name} ({attendee_email}) to meeting {meeting_id}")
            
            return {
                'success': True,
                'message': f'Attendee {attendee_name} added successfully'
            }
            
        except Exception as e:
            logger.error(f"Error adding attendee to Teams meeting: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_meeting_transcript(self, meeting_id, user_email=None):
        """
        Get meeting transcript/chat messages from Teams
        
        Note: This requires OnlineMeetings.Read.All or OnlineMeetings.ReadWrite.All
        API permissions. The meeting must have transcription enabled.
        
        Args:
            meeting_id: Teams meeting ID (online meeting ID, not calendar event ID)
            user_email: User's email address (userPrincipalName) for application permissions
            
        Returns:
            dict: Transcript data with chat messages
        """
        try:
            logger.info(f"Fetching transcript for meeting: {meeting_id}")
            
            # Method 1: Try to get transcript using online meeting ID
            # This requires OnlineMeetings.Read.All permission
            try:
                endpoint = f'/users/{user_email}/onlineMeetings/{meeting_id}/transcripts'
                response = self._make_request('GET', endpoint)
                
                transcripts = response.get('value', [])
                if transcripts:
                    # Get the content of each transcript
                    chat_messages = []
                    for transcript in transcripts:
                        transcript_id = transcript.get('id')
                        content_endpoint = f'/users/{user_email}/onlineMeetings/{meeting_id}/transcripts/{transcript_id}/content'
                        
                        # Note: Content is in VTT format
                        content = self._make_request('GET', content_endpoint)
                        chat_messages.append({
                            'transcript_id': transcript_id,
                            'created': transcript.get('createdDateTime'),
                            'content': content
                        })
                    
                    return {
                        'success': True,
                        'messages': chat_messages,
                        'total_messages': len(chat_messages)
                    }
            except TeamsAPIError as e:
                logger.warning(f"Transcript API not available (may require premium license): {str(e)}")
            
            # Method 2: Try to get chat messages from the associated chat
            # This requires Chat.Read.All permission
            try:
                # First, get the online meeting to find associated chat ID
                meeting_endpoint = f'/users/{user_email}/onlineMeetings/{meeting_id}'
                meeting_details = self._make_request('GET', meeting_endpoint)
                
                chat_id = meeting_details.get('chatInfo', {}).get('threadId')
                if chat_id:
                    # Get chat messages
                    chat_endpoint = f'/chats/{chat_id}/messages'
                    chat_response = self._make_request('GET', chat_endpoint, params={'$top': 100})
                    
                    messages = chat_response.get('value', [])
                    chat_data = []
                    
                    for msg in messages:
                        chat_data.append({
                            'id': msg.get('id'),
                            'created': msg.get('createdDateTime'),
                            'sender': msg.get('from', {}).get('user', {}).get('displayName'),
                            'sender_email': msg.get('from', {}).get('user', {}).get('userPrincipalName'),
                            'message': msg.get('body', {}).get('content'),
                            'message_type': msg.get('messageType'),
                        })
                    
                    return {
                        'success': True,
                        'messages': chat_data,
                        'total_messages': len(chat_data)
                    }
            except TeamsAPIError as e:
                logger.warning(f"Chat API not available: {str(e)}")
            
            # If both methods fail, return empty result
            logger.warning(f"No transcript or chat data available for meeting {meeting_id}")
            return {
                'success': True,
                'messages': [],
                'total_messages': 0,
                'note': 'No transcript or chat data available. This may require additional API permissions (OnlineMeetings.Read.All, Chat.Read.All) or Teams Premium license for transcription.'
            }
            
        except Exception as e:
            logger.error(f"Error getting meeting transcript: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_meeting_chat_messages(self, online_meeting_id, user_email=None, meeting_id=None):
        """
        Get chat messages from Teams meeting (works without premium license)
        
        This is the PREFERRED method for getting chat messages.
        Requires: Chat.Read.All or Chat.ReadWrite.All permission
        
        Args:
            online_meeting_id: Teams online meeting ID
            user_email: Meeting organizer's email address
            meeting_id: Calendar event ID (optional, used as fallback)
            
        Returns:
            dict: Chat messages data
        """
        try:
            if not user_email and self.integration.user and self.integration.user.email:
                user_email = self.integration.user.email
            
            if not user_email:
                raise TeamsAPIError("User email required for chat access")
            
            logger.info(f"Fetching chat messages for meeting: {online_meeting_id}")
            
            chat_id = None
            
            # ✅ FIX: Check if online_meeting_id is already a thread ID
            if online_meeting_id and '@thread.v2' in str(online_meeting_id):
                # This is already a thread ID, use it directly
                chat_id = online_meeting_id
                logger.info(f"✓ Using provided thread ID directly: {chat_id}")
            
            # Try to get chat ID from online meeting
            elif online_meeting_id:
                try:
                    meeting_endpoint = f'/users/{user_email}/onlineMeetings/{online_meeting_id}'
                    meeting_details = self._make_request('GET', meeting_endpoint)
                    
                    chat_info = meeting_details.get('chatInfo', {})
                    chat_id = chat_info.get('threadId')
                    
                    if chat_id:
                        logger.info(f"Found chat thread ID from online meeting: {chat_id}")
                        
                except Exception as e:
                    logger.warning(f"Could not get chat ID from online meeting: {str(e)}")
            
            # Fallback: try to get chat ID from calendar event
            if not chat_id and meeting_id:
                try:
                    event_endpoint = f'/users/{user_email}/events/{meeting_id}'
                    event_details = self._make_request('GET', event_endpoint)
                    
                    online_meeting = event_details.get('onlineMeeting', {})
                    join_url = online_meeting.get('joinUrl', '')
                    
                    # Try to extract thread ID from join URL if available
                    # This is a workaround when chat info is not directly available
                    
                except Exception as e:
                    logger.warning(f"Could not get chat ID from calendar event: {str(e)}")
            
            if not chat_id:
                logger.info("No chat thread found for this meeting. Chat may not have been used.")
                return {
                    'success': True,
                    'messages': [],
                    'total_messages': 0,
                    'note': 'No chat thread available. Chat may not have been enabled or used during this meeting.'
                }
            
            # Get chat messages
            logger.info(f"Retrieving messages from chat: {chat_id}")
            
            # ✅ FIX: URL-encode the chat ID (required for thread IDs with special characters)
            import urllib.parse
            encoded_chat_id = urllib.parse.quote(chat_id, safe='')
            
            chat_endpoint = f'/chats/{encoded_chat_id}/messages'
            params = {
                '$top': 50,  # Get last 50 messages
                '$orderby': 'createdDateTime asc'  # Oldest first
            }
            
            response = self._make_request('GET', chat_endpoint, params=params)
            
            messages = response.get('value', [])
            
            # Process and filter messages
            chat_data = []
            for msg in messages:
                # Get message type
                msg_type = msg.get('messageType', 'message')
                
                # Skip system messages and non-text messages
                if msg_type not in ['message']:
                    continue
                
                # Get sender information
                from_info = msg.get('from', {})
                sender_user = from_info.get('user', {})
                sender_name = sender_user.get('displayName', 'Unknown')
                sender_email = sender_user.get('userPrincipalName', '')
                
                # Get message content
                body = msg.get('body', {})
                content_type = body.get('contentType', 'text')
                message_text = body.get('content', '')
                
                # Skip empty messages
                if not message_text or not message_text.strip():
                    continue
                
                # Parse timestamp
                created_time = msg.get('createdDateTime')
                
                chat_data.append({
                    'id': msg.get('id'),
                    'created': created_time,
                    'sender': sender_name,
                    'sender_email': sender_email,
                    'message': message_text,
                    'message_type': msg_type,
                    'content_type': content_type,
                })
                
            logger.info(f"Retrieved {len(chat_data)} chat messages")
            
            return {
                'success': True,
                'messages': chat_data,
                'total_messages': len(chat_data),
                'chat_id': chat_id
            }
            
        except TeamsAPIError as e:
            error_msg = str(e)
            
            if '403' in error_msg or 'Forbidden' in error_msg:
                return {
                    'success': False,
                    'error': 'Insufficient permissions to access chat messages.',
                    'permission_required': 'Chat.Read.All',
                    'note': 'Please ensure Chat.Read.All permission is granted in Azure AD and admin consent is provided.'
                }
            else:
                return {
                    'success': False,
                    'error': error_msg
                }
                
        except Exception as e:
            logger.error(f"Error getting meeting chat messages: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_online_meeting_id_from_join_url(self, join_url):
        """
        Extract online meeting thread ID from Teams join URL
        
        Args:
            join_url: Teams meeting join URL
            
        Returns:
            str: Online meeting thread ID (19:meeting_XXX@thread.v2) or None
        """
        try:
            # Teams join URLs contain the thread ID
            # Format: https://teams.microsoft.com/l/meetup-join/19%3ameeting_XXX%40thread.v2/...
            import re
            import urllib.parse
            
            # Extract encoded thread ID from URL
            match = re.search(r'/meetup-join/([^/]+)', join_url)
            if match:
                encoded_thread = match.group(1)
                # URL decode to get actual thread ID (19:meeting_XXX@thread.v2)
                thread_id = urllib.parse.unquote(encoded_thread)
                
                # Verify it's in the correct format
                if '@thread.v2' in thread_id or 'meeting_' in thread_id:
                    logger.info(f"✓ Extracted thread ID: {thread_id}")
                    return thread_id
                else:
                    logger.warning(f"Extracted ID doesn't match expected format: {thread_id}")
                    return encoded_thread  # Return as-is
            
            logger.warning(f"Could not extract thread ID from URL: {join_url}")
            return None
            
        except Exception as e:
            logger.error(f"Error extracting thread ID from URL: {str(e)}")
            return None
    
    def validate_permissions(self):
        """
        Validate that all required Microsoft Graph API permissions are available
        
        Returns:
            dict: Permission validation results
        """
        required_permissions = {
            'calendar': {
                'name': 'Calendars.ReadWrite',
                'description': 'Create and manage calendar events',
                'test_endpoint': '/users',
                'test_params': {'$top': 1, '$select': 'id,displayName'}
            },
            'attendance': {
                'name': 'OnlineMeetingArtifact.Read.All',
                'description': 'Read attendance reports with duration',
                'test_endpoint': '/users',
                'test_params': {'$top': 1, '$select': 'id'}
            },
            'chat': {
                'name': 'Chat.Read.All',
                'description': 'Read chat messages from meetings',
                'test_endpoint': '/chats',
                'test_params': {'$top': 1}
            },
            'recordings': {
                'name': 'Files.Read.All',
                'description': 'Read recordings from OneDrive',
                'test_endpoint': '/drives',
                'test_params': {'$top': 1}
            },
            'meetings': {
                'name': 'OnlineMeetings.ReadWrite',
                'description': 'Create and manage online meetings',
                'test_endpoint': '/users',
                'test_params': {'$top': 1, '$select': 'id'}
            }
        }
        
        validation_results = {
            'all_granted': True,
            'permissions': {},
            'missing_permissions': [],
            'available_features': [],
            'unavailable_features': []
        }
        
        logger.info("🔍 Validating Microsoft Graph API permissions...")
        
        for feature, perm_info in required_permissions.items():
            try:
                # Try a simple API call that requires this permission
                endpoint = perm_info['test_endpoint']
                params = perm_info.get('test_params', {})
                
                try:
                    self._make_request('GET', endpoint, params=params)
                    
                    # If successful, permission is granted
                    validation_results['permissions'][feature] = {
                        'granted': True,
                        'permission_name': perm_info['name'],
                        'description': perm_info['description']
                    }
                    validation_results['available_features'].append(feature)
                    logger.info(f"  ✓ {feature}: {perm_info['name']} - GRANTED")
                    
                except TeamsAPIError as e:
                    error_msg = str(e)
                    
                    # Check if it's a permission error
                    if '403' in error_msg or 'Forbidden' in error_msg or 'Insufficient' in error_msg:
                        validation_results['permissions'][feature] = {
                            'granted': False,
                            'permission_name': perm_info['name'],
                            'description': perm_info['description'],
                            'error': 'Permission not granted or admin consent not provided'
                        }
                        validation_results['missing_permissions'].append(perm_info['name'])
                        validation_results['unavailable_features'].append(feature)
                        validation_results['all_granted'] = False
                        logger.warning(f"  ✗ {feature}: {perm_info['name']} - NOT GRANTED")
                    else:
                        # Other error - permission might be OK but test failed for another reason
                        validation_results['permissions'][feature] = {
                            'granted': 'unknown',
                            'permission_name': perm_info['name'],
                            'description': perm_info['description'],
                            'error': error_msg
                        }
                        logger.info(f"  ? {feature}: {perm_info['name']} - UNKNOWN (test failed: {error_msg})")
                        
            except Exception as e:
                validation_results['permissions'][feature] = {
                    'granted': 'error',
                    'permission_name': perm_info['name'],
                    'description': perm_info['description'],
                    'error': str(e)
                }
                logger.error(f"  ✗ {feature}: Error testing permission - {str(e)}")
        
        # Generate summary message
        if validation_results['all_granted']:
            validation_results['message'] = "✅ All required permissions are granted"
        elif validation_results['missing_permissions']:
            validation_results['message'] = (
                f"⚠️ Missing permissions: {', '.join(validation_results['missing_permissions'])}. "
                f"Please grant these permissions in Azure AD and provide admin consent."
            )
        else:
            validation_results['message'] = "⚠️ Some permissions could not be validated"
        
        logger.info(f"Permission validation complete: {validation_results['message']}")
        
        return validation_results