"""
Enhanced Conference Sync Resilience Utilities
Provides robust sync mechanisms with retry logic, error handling, and recovery
"""
import time
import logging
import requests
from functools import wraps
from typing import Dict, Any, Optional, Callable
from django.core.cache import cache
from django.utils import timezone
from conferences.models import Conference, ConferenceSyncLog

logger = logging.getLogger(__name__)

class SyncError(Exception):
    """Custom exception for sync-related errors"""
    pass

class RetryConfig:
    """Configuration for retry mechanisms"""
    def __init__(self, max_attempts=3, base_delay=1.0, max_delay=30.0, backoff_factor=2.0):
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor

def with_retry(config: RetryConfig = None):
    """Decorator for adding retry logic to functions"""
    if config is None:
        config = RetryConfig()
    
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(config.max_attempts):
                try:
                    return func(*args, **kwargs)
                except (requests.RequestException, SyncError) as e:
                    last_exception = e
                    if attempt == config.max_attempts - 1:
                        break
                    
                    delay = min(
                        config.base_delay * (config.backoff_factor ** attempt),
                        config.max_delay
                    )
                    logger.warning(
                        f"Attempt {attempt + 1}/{config.max_attempts} failed for {func.__name__}: {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    time.sleep(delay)
                except Exception as e:
                    # Don't retry for unexpected errors
                    logger.error(f"Unexpected error in {func.__name__}: {e}")
                    raise
            
            logger.error(f"All {config.max_attempts} attempts failed for {func.__name__}")
            raise last_exception
        
        return wrapper
    return decorator

class SyncHealthChecker:
    """Monitors sync health and detects issues"""
    
    @staticmethod
    def check_conference_sync_health(conference_id: int) -> Dict[str, Any]:
        """Check the sync health of a specific conference"""
        try:
            conference = Conference.objects.get(id=conference_id)
        except Conference.DoesNotExist:
            return {'status': 'error', 'message': 'Conference not found'}
        
        health_data = {
            'conference_id': conference_id,
            'conference_title': conference.title,
            'last_sync': None,
            'sync_status': 'unknown',
            'recordings_status': 'unknown',
            'chat_status': 'unknown',
            'issues': [],
            'recommendations': []
        }
        
        # Check last sync log
        last_sync = ConferenceSyncLog.objects.filter(
            conference=conference
        ).order_by('-sync_started_at').first()
        
        if last_sync:
            health_data['last_sync'] = last_sync.sync_started_at
            health_data['sync_status'] = last_sync.sync_status
            
            # Check if sync is recent
            time_since_sync = timezone.now() - last_sync.sync_started_at
            if time_since_sync.total_seconds() > 86400:  # 24 hours
                health_data['issues'].append('No recent sync (>24 hours)')
                health_data['recommendations'].append('Run manual sync')
        else:
            health_data['issues'].append('No sync logs found')
            health_data['recommendations'].append('Initialize sync for this conference')
        
        # Check recordings
        from conferences.models import ConferenceRecording
        total_recordings = ConferenceRecording.objects.filter(conference=conference).count()
        visible_recordings = ConferenceRecording.objects.filter(
            conference=conference,
            status='available'
        ).exclude(
            title__iexact='timeline'
        ).exclude(
            title__iexact='chat_file'
        ).exclude(
            title__icontains='transcript'
        ).exclude(
            title__icontains='poll'
        ).count()
        
        health_data['recordings_status'] = f"{visible_recordings}/{total_recordings} visible"
        
        if total_recordings > 0 and visible_recordings == 0:
            health_data['issues'].append('Recordings synced but none visible to users')
            health_data['recommendations'].append('Check recording filters and status')
        
        # Check chat messages
        from conferences.models import ConferenceChat
        total_chat = ConferenceChat.objects.filter(conference=conference).count()
        matched_chat = ConferenceChat.objects.filter(
            conference=conference,
            sender__isnull=False
        ).count()
        unmatched_chat = total_chat - matched_chat
        
        health_data['chat_status'] = f"{matched_chat}/{total_chat} matched"
        
        if unmatched_chat > 0:
            health_data['issues'].append(f'{unmatched_chat} unmatched chat messages')
            health_data['recommendations'].append('Run chat re-matching')
        
        # Overall health assessment
        if not health_data['issues']:
            health_data['overall_status'] = 'healthy'
        elif len(health_data['issues']) <= 2:
            health_data['overall_status'] = 'warning'
        else:
            health_data['overall_status'] = 'critical'
        
        return health_data
    
    @staticmethod
    def get_system_wide_health() -> Dict[str, Any]:
        """Get overall sync health across all conferences"""
        from conferences.models import Conference
        
        recent_conferences = Conference.objects.filter(
            date__gte=timezone.now().date() - timezone.timedelta(days=30)
        ).order_by('-date')[:50]
        
        health_summary = {
            'total_conferences': recent_conferences.count(),
            'healthy': 0,
            'warning': 0,
            'critical': 0,
            'issues_by_type': {},
            'recommendations': set()
        }
        
        for conference in recent_conferences:
            conf_health = SyncHealthChecker.check_conference_sync_health(conference.id)
            
            # Count by status
            status = conf_health.get('overall_status', 'unknown')
            if status in health_summary:
                health_summary[status] += 1
            
            # Aggregate issues
            for issue in conf_health.get('issues', []):
                if issue not in health_summary['issues_by_type']:
                    health_summary['issues_by_type'][issue] = 0
                health_summary['issues_by_type'][issue] += 1
            
            # Collect recommendations
            for rec in conf_health.get('recommendations', []):
                health_summary['recommendations'].add(rec)
        
        health_summary['recommendations'] = list(health_summary['recommendations'])
        
        return health_summary

class SyncRecoveryManager:
    """Handles automatic recovery from sync failures"""
    
    @staticmethod
    def auto_recover_conference(conference_id: int) -> Dict[str, Any]:
        """Attempt automatic recovery for a conference with sync issues"""
        try:
            conference = Conference.objects.get(id=conference_id)
        except Conference.DoesNotExist:
            return {'success': False, 'error': 'Conference not found'}
        
        recovery_log = {
            'conference_id': conference_id,
            'recovery_started': timezone.now(),
            'actions_taken': [],
            'success': False,
            'errors': []
        }
        
        try:
            # Check current health
            health = SyncHealthChecker.check_conference_sync_health(conference_id)
            
            # Action 1: Re-sync if needed
            if 'No recent sync' in str(health.get('issues', [])):
                try:
                    from conferences.views import sync_zoom_meeting_data
                    sync_result = sync_zoom_meeting_data(conference)
                    if sync_result.get('success'):
                        recovery_log['actions_taken'].append('Performed full sync')
                    else:
                        recovery_log['errors'].append(f"Sync failed: {sync_result.get('error', 'Unknown error')}")
                except Exception as e:
                    recovery_log['errors'].append(f"Sync error: {str(e)}")
            
            # Action 2: Re-match chat messages if needed
            if 'unmatched chat messages' in str(health.get('issues', [])):
                try:
                    from conferences.views import rematch_unmatched_chat_messages
                    matched_count = rematch_unmatched_chat_messages(conference)
                    recovery_log['actions_taken'].append(f'Re-matched {matched_count} chat messages')
                except Exception as e:
                    recovery_log['errors'].append(f"Chat re-matching error: {str(e)}")
            
            # Action 3: Clear cache if needed
            cache_keys = [
                f'conference_sync_{conference_id}',
                f'conference_recordings_{conference_id}',
                f'conference_chat_{conference_id}'
            ]
            for key in cache_keys:
                cache.delete(key)
            recovery_log['actions_taken'].append('Cleared related caches')
            
            # Determine success
            recovery_log['success'] = len(recovery_log['actions_taken']) > 0 and len(recovery_log['errors']) == 0
            recovery_log['recovery_completed'] = timezone.now()
            
            return recovery_log
            
        except Exception as e:
            recovery_log['errors'].append(f"Recovery process error: {str(e)}")
            recovery_log['success'] = False
            return recovery_log

@with_retry(RetryConfig(max_attempts=3, base_delay=2.0))
def robust_api_call(url: str, headers: dict, method: str = 'GET', **kwargs) -> requests.Response:
    """Make a robust API call with retry logic"""
    try:
        if method.upper() == 'GET':
            response = requests.get(url, headers=headers, timeout=30, **kwargs)
        elif method.upper() == 'POST':
            response = requests.post(url, headers=headers, timeout=30, **kwargs)
        else:
            raise SyncError(f"Unsupported HTTP method: {method}")
        
        # Check for rate limiting
        if response.status_code == 429:
            retry_after = int(response.headers.get('Retry-After', 60))
            logger.warning(f"Rate limited, waiting {retry_after} seconds")
            time.sleep(retry_after)
            raise requests.RequestException("Rate limited, retrying")
        
        # Check for server errors that might be temporary
        if 500 <= response.status_code < 600:
            raise requests.RequestException(f"Server error: {response.status_code}")
        
        return response
        
    except requests.Timeout:
        raise SyncError("API call timed out")
    except requests.ConnectionError:
        raise SyncError("Connection error to API")
    except requests.RequestException as e:
        raise SyncError(f"API request failed: {str(e)}")

def enhanced_recording_parser(recordings_data: dict, conference) -> Dict[str, Any]:
    """Enhanced recording parser with better error handling"""
    parse_result = {
        'recordings_processed': 0,
        'recordings_created': 0,
        'recordings_updated': 0,
        'errors': [],
        'warnings': []
    }
    
    try:
        if not recordings_data or 'recording_files' not in recordings_data:
            parse_result['warnings'].append('No recording_files found in response')
            return parse_result
        
        from conferences.models import ConferenceRecording
        
        for recording_file in recordings_data['recording_files']:
            try:
                parse_result['recordings_processed'] += 1
                
                # Extract recording data with defaults
                recording_data = {
                    'conference': conference,
                    'recording_id': recording_file.get('id', ''),
                    'title': recording_file.get('recording_type', 'unknown'),
                    'file_type': recording_file.get('file_type', '').lower(),
                    'file_size': recording_file.get('file_size', 0),
                    'recording_type': recording_file.get('recording_type', 'unknown'),
                    'status': 'available' if recording_file.get('status') == 'completed' else 'processing',
                    'download_url': recording_file.get('download_url', ''),
                    'play_url': recording_file.get('play_url', ''),
                    'duration_minutes': 0,
                    'created_at': timezone.now()
                }
                
                # Parse duration if available
                if 'recording_start' in recording_file and 'recording_end' in recording_file:
                    try:
                        start_time = timezone.datetime.fromisoformat(
                            recording_file['recording_start'].replace('Z', '+00:00')
                        )
                        end_time = timezone.datetime.fromisoformat(
                            recording_file['recording_end'].replace('Z', '+00:00')
                        )
                        duration = (end_time - start_time).total_seconds() / 60
                        recording_data['duration_minutes'] = int(duration)
                    except (ValueError, KeyError) as e:
                        parse_result['warnings'].append(f"Could not parse duration for recording {recording_data['recording_id']}: {e}")
                
                # Create or update recording
                recording, created = ConferenceRecording.objects.update_or_create(
                    conference=conference,
                    recording_id=recording_data['recording_id'],
                    defaults=recording_data
                )
                
                if created:
                    parse_result['recordings_created'] += 1
                else:
                    parse_result['recordings_updated'] += 1
                
                logger.info(f"{'Created' if created else 'Updated'} recording: {recording.title}")
                
            except Exception as e:
                error_msg = f"Error processing recording {recording_file.get('id', 'unknown')}: {str(e)}"
                parse_result['errors'].append(error_msg)
                logger.error(error_msg)
        
    except Exception as e:
        error_msg = f"Error in enhanced_recording_parser: {str(e)}"
        parse_result['errors'].append(error_msg)
        logger.error(error_msg)
    
    return parse_result

def enhanced_chat_parser(chat_content: str, conference) -> Dict[str, Any]:
    """Enhanced chat parser with better user matching and error handling"""
    parse_result = {
        'messages_processed': 0,
        'messages_created': 0,
        'messages_matched': 0,
        'messages_unmatched': 0,
        'errors': [],
        'warnings': []
    }
    
    try:
        if not chat_content or not chat_content.strip():
            parse_result['warnings'].append('No chat content to parse')
            return parse_result
        
        from conferences.models import ConferenceChat
        from django.contrib.auth import get_user_model
        from django.db.models import Q
        
        User = get_user_model()
        chat_lines = chat_content.strip().split('\n')
        
        # Pre-load potential users for better performance
        potential_users = {}
        if hasattr(conference.created_by, 'branch') and conference.created_by.branch:
            branch_users = User.objects.filter(branch=conference.created_by.branch)
            for user in branch_users:
                # Index by various name formats
                full_name = user.get_full_name()
                if full_name:
                    potential_users[full_name.lower()] = user
                potential_users[user.username.lower()] = user
                potential_users[f"{user.first_name} {user.last_name}".lower()] = user
        
        for line in chat_lines:
            try:
                line = line.strip()
                if not line or ':' not in line:
                    continue
                
                parse_result['messages_processed'] += 1
                
                # Parse chat message
                sender_name = None
                message_text = None
                timestamp_str = None
                
                # Try different parsing patterns
                if ' From ' in line and ' to ' in line and ': ' in line:
                    # Format: "HH:MM:SS From Sender Name to Everyone: Message"
                    timestamp_sender_part, message_text = line.split(': ', 1)
                    timestamp_str = timestamp_sender_part.split(' From ')[0].strip()
                    from_to_part = timestamp_sender_part.split(' From ')[1]
                    if ' to ' in from_to_part:
                        sender_name = from_to_part.split(' to ')[0].strip()
                elif ': ' in line:
                    # Simple format: "Sender Name: Message"
                    parts = line.split(': ', 1)
                    if len(parts) == 2:
                        sender_name = parts[0].strip()
                        message_text = parts[1].strip()
                
                if not sender_name or not message_text:
                    continue
                
                # Enhanced user matching
                matched_user = None
                sender_name_lower = sender_name.lower()
                
                # 1. Direct lookup in pre-loaded users
                if sender_name_lower in potential_users:
                    matched_user = potential_users[sender_name_lower]
                
                # 2. Check if it's the instructor (exact match only)
                if not matched_user:
                    instructor = conference.created_by
                    instructor_variations = [
                        instructor.get_full_name(),
                        f"{instructor.first_name} {instructor.last_name}",
                        instructor.username
                    ]
                    
                    for variation in instructor_variations:
                        if variation and variation.lower() == sender_name_lower:
                            matched_user = instructor
                            break
                
                # Create chat message
                chat_message, created = ConferenceChat.objects.get_or_create(
                    conference=conference,
                    sender_name=sender_name,
                    message_text=message_text,
                    defaults={
                        'sender': matched_user,
                        'sent_at': conference.created_at,  # Fallback timestamp
                        'message_type': 'text',
                        'metadata': {
                            'timestamp_str': timestamp_str,
                            'parse_source': 'enhanced_chat_parser'
                        }
                    }
                )
                
                if created:
                    parse_result['messages_created'] += 1
                    
                if matched_user:
                    parse_result['messages_matched'] += 1
                else:
                    parse_result['messages_unmatched'] += 1
                    parse_result['warnings'].append(f"Could not match user: {sender_name}")
                
            except Exception as e:
                error_msg = f"Error parsing chat line '{line[:50]}...': {str(e)}"
                parse_result['errors'].append(error_msg)
                logger.error(error_msg)
        
    except Exception as e:
        error_msg = f"Error in enhanced_chat_parser: {str(e)}"
        parse_result['errors'].append(error_msg)
        logger.error(error_msg)
    
    return parse_result 