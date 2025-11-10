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
        
        url = urljoin(self.base_url, endpoint)
        
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
                'error': str(e)
            }
            
            # Special handling for common errors
            if hasattr(response, 'status_code'):
                if response.status_code == 404:
                    error_msg = (
                        f"API request failed: 404 Not Found for endpoint {endpoint}. "
                        "This usually indicates missing API permissions in Azure AD. "
                        "Please ensure 'Calendars.ReadWrite' application permission is configured "
                        "and admin consent is granted. See TEAMS_INTEGRATION_FIX.md for details."
                    )
                elif response.status_code == 403:
                    error_msg = (
                        f"API request failed: 403 Forbidden for endpoint {endpoint}. "
                        "This indicates insufficient permissions. Verify API permissions and admin consent."
                    )
                elif response.status_code == 401:
                    error_msg = (
                        f"API request failed: 401 Unauthorized for endpoint {endpoint}. "
                        "Token might be invalid or expired."
                    )
                else:
                    error_msg = f"API request failed: {str(e)}"
            else:
                error_msg = f"API request failed: {str(e)}"
            
            logger.error(f"Teams API request failed: {error_msg}", extra=error_details)
            raise TeamsAPIError(error_msg)
    
    def create_meeting(self, title, start_time, end_time, description=None, user_email=None):
        """
        Create a Teams meeting
        
        Args:
            title: Meeting title
            start_time: Meeting start time
            end_time: Meeting end time
            description: Meeting description
            user_email: User's email address (userPrincipalName) for application permissions.
                       If None, uses integration owner's email.
            
        Returns:
            dict: Meeting details
        """
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
            
            # Determine user email for application permissions
            # With client credentials flow, we need to specify the user
            if not user_email and self.integration.user and self.integration.user.email:
                user_email = self.integration.user.email
                logger.info(f"Using integration owner email: {user_email}")
            
            if not user_email:
                error_msg = (
                    "User email is required for creating calendar events with application permissions. "
                    "Please ensure the integration owner or request user has a valid email address configured."
                )
                logger.error(error_msg)
                raise TeamsAPIError(error_msg)
            
            # Use /users/{userPrincipalName}/calendar/events for application permissions
            # instead of /me/events which requires delegated permissions
            endpoint = f'/users/{user_email}/calendar/events'
            logger.info(f"Creating Teams meeting for user: {user_email}, title: {title}")
            
            # Create the meeting
            response = self._make_request(
                'POST',
                endpoint,
                data=meeting_data
            )
            
            # Extract meeting details
            meeting_id = response.get('id')
            join_url = response.get('onlineMeeting', {}).get('joinUrl')
            
            logger.info(f"Created Teams meeting: {meeting_id}")
            
            return {
                'success': True,
                'meeting_id': meeting_id,
                'meeting_link': join_url,
                'meeting_details': response
            }
            
        except Exception as e:
            logger.error(f"Error creating Teams meeting: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_meeting_attendance(self, meeting_id, user_email=None):
        """
        Get meeting attendance data
        
        Args:
            meeting_id: Teams meeting ID (calendar event ID)
            user_email: User's email address (userPrincipalName) for application permissions.
                       If None, uses integration owner's email.
            
        Returns:
            dict: Attendance data
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
            
        except Exception as e:
            logger.error(f"Error getting Teams meeting attendance: {str(e)}")
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