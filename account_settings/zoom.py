import requests
import json
from datetime import datetime, timedelta
from django.conf import settings
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)

class ZoomAPI:
    """Zoom API client for creating and managing meetings"""
    
    def __init__(self, account_id, client_id, client_secret):
        self.account_id = account_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = None
        self.token_expires = None
        self.base_url = "https://api.zoom.us/v2"
    
    def get_access_token(self):
        """Get OAuth access token for Zoom API"""
        if self.access_token and self.token_expires and timezone.now() < self.token_expires:
            return self.access_token
        
        auth_url = "https://zoom.us/oauth/token"
        
        # Prepare authentication data
        auth_data = {
            'grant_type': 'account_credentials',
            'account_id': self.account_id
        }
        
        # Create basic auth header
        import base64
        credentials = f"{self.client_id}:{self.client_secret}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        
        headers = {
            'Authorization': f'Basic {encoded_credentials}',
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        
        try:
            response = requests.post(auth_url, data=auth_data, headers=headers)
            response.raise_for_status()
            
            token_data = response.json()
            self.access_token = token_data['access_token']
            
            # Set token expiration (usually 1 hour minus 5 minutes for safety)
            expires_in = token_data.get('expires_in', 3600)
            self.token_expires = timezone.now() + timedelta(seconds=expires_in - 300)
            
            return self.access_token
            
        except requests.RequestException as e:
            logger.error(f"Failed to get Zoom access token: {e}")
            raise Exception(f"Failed to authenticate with Zoom: {e}")
    
    def get_headers(self):
        """Get headers for API requests"""
        token = self.get_access_token()
        return {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
    
    def create_meeting(self, topic, start_time=None, duration=60, password=None, 
                      waiting_room=True, join_before_host=False, meeting_type=3):
        """Create a Zoom meeting
        
        Args:
            topic: Meeting topic/title
            start_time: Meeting start time (datetime object)
            duration: Meeting duration in minutes (used for scheduling only, not enforced for type 3)
            password: Meeting password
            waiting_room: Enable waiting room
            join_before_host: Allow joining before host
            meeting_type: Meeting type (2=Scheduled with fixed duration, 3=Recurring no fixed time - unlimited)
        """
        try:
            headers = self.get_headers()
            
            # Default to current time if no start time provided
            if start_time is None:
                start_time = timezone.now() + timedelta(minutes=5)
            
            # Format start time for Zoom API
            start_time_str = start_time.strftime('%Y-%m-%dT%H:%M:%S')
            
            meeting_data = {
                'topic': topic,
                'type': meeting_type,  # Type 3: Recurring meeting with no fixed time (unlimited duration)
                'start_time': start_time_str,
                'duration': duration,  # Duration is for scheduling reference only for type 3
                'timezone': 'UTC',
                'settings': {
                    'waiting_room': waiting_room,
                    'join_before_host': join_before_host,
                    'mute_upon_entry': True,
                    'approval_type': 2,  # No registration required
                    'audio': 'both',  # Both telephony and VoIP
                    'auto_recording': 'cloud'  # Enable cloud recording
                }
            }
            
            # For recurring meetings (type 3), add recurrence settings for "no fixed time"
            if meeting_type == 3:
                meeting_data['recurrence'] = {
                    'type': 1,  # Daily recurrence
                    'repeat_interval': 1,  # Every day
                    'end_times': 1  # Only one occurrence (this makes it "no fixed time")
                }
            
            if password:
                meeting_data['password'] = password
            
            # Get user ID (we'll use 'me' for the authenticated user)
            user_id = 'me'
            url = f"{self.base_url}/users/{user_id}/meetings"
            
            response = requests.post(url, json=meeting_data, headers=headers)
            response.raise_for_status()
            
            meeting_info = response.json()
            
            return {
                'success': True,
                'meeting_id': meeting_info['id'],
                'meeting_url': meeting_info['join_url'],
                'start_url': meeting_info['start_url'],
                'meeting_password': meeting_info.get('password', ''),
                'topic': meeting_info['topic'],
                'start_time': meeting_info['start_time'],
                'duration': meeting_info['duration']
            }
            
        except requests.RequestException as e:
            logger.error(f"Failed to create Zoom meeting: {e}")
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_data = e.response.json()
                    return {
                        'success': False,
                        'error': error_data.get('message', str(e))
                    }
                except:
                    return {
                        'success': False,
                        'error': str(e)
                    }
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_meeting(self, meeting_id):
        """Get meeting details"""
        try:
            headers = self.get_headers()
            url = f"{self.base_url}/meetings/{meeting_id}"
            
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            
            meeting_info = response.json()
            
            return {
                'success': True,
                'meeting_info': meeting_info
            }
            
        except requests.RequestException as e:
            logger.error(f"Failed to get Zoom meeting {meeting_id}: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def delete_meeting(self, meeting_id):
        """Delete a Zoom meeting"""
        try:
            headers = self.get_headers()
            url = f"{self.base_url}/meetings/{meeting_id}"
            
            response = requests.delete(url, headers=headers)
            response.raise_for_status()
            
            return {
                'success': True,
                'message': 'Meeting deleted successfully'
            }
            
        except requests.RequestException as e:
            logger.error(f"Failed to delete Zoom meeting {meeting_id}: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def test_connection(self):
        """Test the Zoom API connection"""
        try:
            headers = self.get_headers()
            url = f"{self.base_url}/users/me"
            
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            
            user_info = response.json()
            
            return {
                'success': True,
                'message': 'Connection successful',
                'user_email': user_info.get('email', 'N/A'),
                'user_type': user_info.get('type', 'N/A'),
                'account_id': user_info.get('account_id', 'N/A')
            }
            
        except requests.RequestException as e:
            logger.error(f"Failed to test Zoom connection: {e}")
            return {
                'success': False,
                'error': str(e)
            }


def get_zoom_client(integration):
    """Get a ZoomAPI client from an integration instance"""
    if not integration or not integration.is_active:
        raise ValueError("Zoom integration not available or inactive")
    
    if not all([integration.account_id, integration.api_key, integration.api_secret]):
        raise ValueError("Zoom integration missing required credentials")
    
    return ZoomAPI(
        account_id=integration.account_id,
        client_id=integration.api_key,
        client_secret=integration.api_secret
    ) 