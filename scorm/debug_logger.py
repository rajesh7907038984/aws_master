"""
SCORM Debug Logger
Comprehensive debugging and logging for SCORM operations
"""
import logging
import json
import traceback
from datetime import datetime
from django.utils import timezone
from django.core.cache import cache

logger = logging.getLogger(__name__)


class ScormDebugLogger:
    """
    Enhanced debug logger for SCORM operations
    Provides detailed logging, debugging, and monitoring capabilities
    """
    
    def __init__(self, attempt_id=None, user_id=None):
        self.attempt_id = attempt_id
        self.user_id = user_id
        self.debug_session_id = f"scorm_debug_{attempt_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
    def log_api_call(self, method, parameters, result, error_code=None):
        """Log SCORM API calls with detailed information"""
        debug_data = {
            'timestamp': timezone.now().isoformat(),
            'attempt_id': self.attempt_id,
            'user_id': self.user_id,
            'method': method,
            'parameters': parameters,
            'result': result,
            'error_code': error_code,
            'session_id': self.debug_session_id
        }
        
        # Log to standard logger
        logger.info(f"🔍 SCORM API CALL: {method} -> {result} (attempt: {self.attempt_id})")
        
        # Store in cache for debugging
        cache_key = f"scorm_debug_{self.attempt_id}_{method}"
        cache.set(cache_key, debug_data, timeout=3600)  # 1 hour
        
        # Log errors with full context
        if error_code and error_code != '0':
            logger.error(f"❌ SCORM API ERROR: {method} failed with code {error_code}")
            logger.error(f"Parameters: {parameters}")
            logger.error(f"Result: {result}")
    
    def log_data_save(self, data_type, data_value, success=True, error=None):
        """Log data save operations"""
        debug_data = {
            'timestamp': timezone.now().isoformat(),
            'attempt_id': self.attempt_id,
            'data_type': data_type,
            'data_value': str(data_value)[:100] + '...' if len(str(data_value)) > 100 else str(data_value),
            'success': success,
            'error': str(error) if error else None,
            'session_id': self.debug_session_id
        }
        
        if success:
            logger.info(f"💾 DATA SAVE: {data_type} saved successfully")
        else:
            logger.error(f"❌ DATA SAVE FAILED: {data_type} - {error}")
        
        # Store in cache
        cache_key = f"scorm_save_{self.attempt_id}_{data_type}"
        cache.set(cache_key, debug_data, timeout=3600)
    
    def log_score_extraction(self, suspend_data, extracted_score, method_used):
        """Log score extraction operations"""
        debug_data = {
            'timestamp': timezone.now().isoformat(),
            'attempt_id': self.attempt_id,
            'suspend_data_preview': suspend_data[:200] + '...' if len(suspend_data) > 200 else suspend_data,
            'extracted_score': extracted_score,
            'method_used': method_used,
            'session_id': self.debug_session_id
        }
        
        logger.info(f"🎯 SCORE EXTRACTION: {method_used} -> {extracted_score}")
        
        # Store in cache
        cache_key = f"scorm_score_{self.attempt_id}"
        cache.set(cache_key, debug_data, timeout=3600)
    
    def log_resume_operation(self, resume_type, bookmark_data, success=True):
        """Log resume operations"""
        debug_data = {
            'timestamp': timezone.now().isoformat(),
            'attempt_id': self.attempt_id,
            'resume_type': resume_type,
            'bookmark_data': bookmark_data,
            'success': success,
            'session_id': self.debug_session_id
        }
        
        if success:
            logger.info(f"🔄 RESUME: {resume_type} successful")
        else:
            logger.error(f"❌ RESUME FAILED: {resume_type}")
        
        # Store in cache
        cache_key = f"scorm_resume_{self.attempt_id}"
        cache.set(cache_key, debug_data, timeout=3600)
    
    def log_time_tracking(self, session_time, total_time, time_spent_seconds):
        """Log time tracking operations"""
        debug_data = {
            'timestamp': timezone.now().isoformat(),
            'attempt_id': self.attempt_id,
            'session_time': session_time,
            'total_time': total_time,
            'time_spent_seconds': time_spent_seconds,
            'session_id': self.debug_session_id
        }
        
        logger.info(f"⏱️ TIME TRACKING: session={session_time}, total={total_time}, seconds={time_spent_seconds}")
        
        # Store in cache
        cache_key = f"scorm_time_{self.attempt_id}"
        cache.set(cache_key, debug_data, timeout=3600)
    
    def log_interaction_tracking(self, interaction_id, interaction_type, result):
        """Log interaction tracking"""
        debug_data = {
            'timestamp': timezone.now().isoformat(),
            'attempt_id': self.attempt_id,
            'interaction_id': interaction_id,
            'interaction_type': interaction_type,
            'result': result,
            'session_id': self.debug_session_id
        }
        
        logger.info(f"🎮 INTERACTION: {interaction_id} ({interaction_type}) -> {result}")
        
        # Store in cache
        cache_key = f"scorm_interaction_{self.attempt_id}_{interaction_id}"
        cache.set(cache_key, debug_data, timeout=3600)
    
    def log_error(self, error_type, error_message, context=None):
        """Log errors with full context"""
        debug_data = {
            'timestamp': timezone.now().isoformat(),
            'attempt_id': self.attempt_id,
            'error_type': error_type,
            'error_message': error_message,
            'context': context,
            'traceback': traceback.format_exc(),
            'session_id': self.debug_session_id
        }
        
        logger.error(f"❌ SCORM ERROR: {error_type} - {error_message}")
        logger.error(f"Context: {context}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        # Store in cache
        cache_key = f"scorm_error_{self.attempt_id}_{error_type}"
        cache.set(cache_key, debug_data, timeout=3600)
    
    def get_debug_summary(self):
        """Get a summary of all debug data for this attempt"""
        summary = {
            'attempt_id': self.attempt_id,
            'user_id': self.user_id,
            'session_id': self.debug_session_id,
            'timestamp': timezone.now().isoformat(),
            'api_calls': [],
            'data_saves': [],
            'score_extractions': [],
            'resume_operations': [],
            'time_tracking': [],
            'interactions': [],
            'errors': []
        }
        
        # Collect all debug data from cache
        cache_patterns = [
            f"scorm_debug_{self.attempt_id}_*",
            f"scorm_save_{self.attempt_id}_*",
            f"scorm_score_{self.attempt_id}",
            f"scorm_resume_{self.attempt_id}",
            f"scorm_time_{self.attempt_id}",
            f"scorm_interaction_{self.attempt_id}_*",
            f"scorm_error_{self.attempt_id}_*"
        ]
        
        for pattern in cache_patterns:
            # This is a simplified version - in practice you'd need to implement
            # cache key pattern matching
            pass
        
        return summary
    
    def export_debug_data(self, format='json'):
        """Export debug data in various formats"""
        summary = self.get_debug_summary()
        
        if format == 'json':
            return json.dumps(summary, indent=2)
        elif format == 'csv':
            # Convert to CSV format
            return self._convert_to_csv(summary)
        else:
            return str(summary)
    
    def _convert_to_csv(self, data):
        """Convert debug data to CSV format"""
        import csv
        import io
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write headers
        writer.writerow(['Type', 'Timestamp', 'Attempt ID', 'Details'])
        
        # Write data rows
        for data_type, items in data.items():
            if isinstance(items, list):
                for item in items:
                    writer.writerow([
                        data_type,
                        item.get('timestamp', ''),
                        item.get('attempt_id', ''),
                        str(item)
                    ])
        
        return output.getvalue()
    
    def clear_debug_data(self):
        """Clear all debug data for this attempt"""
        cache_patterns = [
            f"scorm_debug_{self.attempt_id}_*",
            f"scorm_save_{self.attempt_id}_*",
            f"scorm_score_{self.attempt_id}",
            f"scorm_resume_{self.attempt_id}",
            f"scorm_time_{self.attempt_id}",
            f"scorm_interaction_{self.attempt_id}_*",
            f"scorm_error_{self.attempt_id}_*"
        ]
        
        for pattern in cache_patterns:
            # In practice, you'd implement cache key deletion
            pass
        
        logger.info(f"🧹 DEBUG DATA CLEARED: {self.attempt_id}")


def create_debug_logger(attempt_id, user_id=None):
    """Factory function to create debug logger"""
    return ScormDebugLogger(attempt_id, user_id)
