"""
Error Monitoring System for LMS
Comprehensive monitoring and alerting for 500 errors
"""

import logging
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from django.conf import settings
from django.core.cache import cache
from django.db import models
from django.contrib.auth.models import User

logger = logging.getLogger(__name__)

class ErrorMonitor:
    """Comprehensive error monitoring system"""
    
    def __init__(self):
        self.error_thresholds = {
            'critical': 10,  # 10 critical errors per hour
            'warning': 50,  # 50 warning errors per hour
            'info': 100     # 100 info errors per hour
        }
    
    def log_error(self, error_type: str, error_message: str, context: Dict[str, Any], 
                  severity: str = 'error', user_id: Optional[int] = None) -> None:
        """Log error with comprehensive context"""
        
        error_data = {
            'timestamp': datetime.now().isoformat(),
            'error_type': error_type,
            'error_message': error_message,
            'severity': severity,
            'user_id': user_id,
            'context': context,
            'server_info': self._get_server_info()
        }
        
        # Log to Django logger
        if severity == 'critical':
            logger.critical(f"CRITICAL ERROR: {error_type} - {error_message}", extra=error_data)
        elif severity == 'error':
            logger.error(f"ERROR: {error_type} - {error_message}", extra=error_data)
        elif severity == 'warning':
            logger.warning(f"WARNING: {error_type} - {error_message}", extra=error_data)
        else:
            logger.info(f"INFO: {error_type} - {error_message}", extra=error_data)
        
        # Store in cache for monitoring
        self._store_error_in_cache(error_data)
        
        # Check thresholds and send alerts
        self._check_error_thresholds(error_type, severity)
    
    def _get_server_info(self) -> Dict[str, Any]:
        """Get server information for error context"""
        import os
        import sys
        
        return {
            'python_version': sys.version,
            'django_version': getattr(settings, 'DJANGO_VERSION', 'Unknown'),
            'server_name': os.environ.get('SERVER_NAME', 'Unknown'),
            'environment': getattr(settings, 'ENVIRONMENT', 'Unknown')
        }
    
    def _store_error_in_cache(self, error_data: Dict[str, Any]) -> None:
        """Store error in cache for monitoring"""
        try:
            # Get current hour key
            current_hour = datetime.now().strftime('%Y-%m-%d-%H')
            cache_key = f"error_monitor_{current_hour}"
            
            # Get existing errors for this hour
            existing_errors = cache.get(cache_key, [])
            existing_errors.append(error_data)
            
            # Store back in cache (expire in 2 hours)
            cache.set(cache_key, existing_errors, 7200)
            
        except Exception as e:
            logger.error(f"Error storing error in cache: {str(e)}")
    
    def _check_error_thresholds(self, error_type: str, severity: str) -> None:
        """Check if error thresholds are exceeded and send alerts"""
        try:
            current_hour = datetime.now().strftime('%Y-%m-%d-%H')
            cache_key = f"error_monitor_{current_hour}"
            
            errors = cache.get(cache_key, [])
            
            # Count errors by severity
            error_counts = {}
            for error in errors:
                sev = error.get('severity', 'info')
                error_counts[sev] = error_counts.get(sev, 0) + 1
            
            # Check thresholds
            for sev, count in error_counts.items():
                threshold = self.error_thresholds.get(sev, 1000)
                if count >= threshold:
                    self._send_alert(sev, count, threshold, error_type)
                    
        except Exception as e:
            logger.error(f"Error checking thresholds: {str(e)}")
    
    def _send_alert(self, severity: str, count: int, threshold: int, error_type: str) -> None:
        """Send alert when thresholds are exceeded"""
        try:
            alert_message = f"ALERT: {severity.upper()} error threshold exceeded. {count} {severity} errors in the last hour (threshold: {threshold}). Error type: {error_type}"
            
            # Log the alert
            logger.critical(alert_message)
            
            # Here you could add email notifications, Slack alerts, etc.
            # For now, we'll just log it
            
        except Exception as e:
            logger.error(f"Error sending alert: {str(e)}")
    
    def get_error_summary(self, hours: int = 24) -> Dict[str, Any]:
        """Get error summary for the last N hours"""
        try:
            summary = {
                'total_errors': 0,
                'errors_by_type': {},
                'errors_by_severity': {},
                'recent_errors': []
            }
            
            # Check last N hours
            for i in range(hours):
                hour_time = datetime.now() - timedelta(hours=i)
                hour_key = hour_time.strftime('%Y-%m-%d-%H')
                cache_key = f"error_monitor_{hour_key}"
                
                errors = cache.get(cache_key, [])
                summary['total_errors'] += len(errors)
                
                for error in errors:
                    # Count by type
                    error_type = error.get('error_type', 'unknown')
                    summary['errors_by_type'][error_type] = summary['errors_by_type'].get(error_type, 0) + 1
                    
                    # Count by severity
                    severity = error.get('severity', 'info')
                    summary['errors_by_severity'][severity] = summary['errors_by_severity'].get(severity, 0) + 1
                    
                    # Add to recent errors (last 10)
                    if len(summary['recent_errors']) < 10:
                        summary['recent_errors'].append({
                            'timestamp': error.get('timestamp'),
                            'error_type': error_type,
                            'error_message': error.get('error_message', ''),
                            'severity': severity
                        })
            
            return summary
            
        except Exception as e:
            logger.error(f"Error getting error summary: {str(e)}")
            return {'error': str(e)}
    
    def clear_old_errors(self, hours: int = 48) -> None:
        """Clear errors older than specified hours"""
        try:
            cutoff_time = datetime.now() - timedelta(hours=hours)
            cutoff_key = cutoff_time.strftime('%Y-%m-%d-%H')
            
            # This is a simplified approach - in production you might want to use a more sophisticated cleanup
            logger.info(f"Clearing errors older than {hours} hours (before {cutoff_key})")
            
        except Exception as e:
            logger.error(f"Error clearing old errors: {str(e)}")

# Global error monitor instance
error_monitor = ErrorMonitor()

def monitor_error(error_type: str, error_message: str, context: Dict[str, Any] = None, 
                  severity: str = 'error', user_id: Optional[int] = None) -> None:
    """Convenience function to log errors with monitoring"""
    error_monitor.log_error(
        error_type=error_type,
        error_message=error_message,
        context=context or {},
        severity=severity,
        user_id=user_id
    )

def get_error_dashboard_data() -> Dict[str, Any]:
    """Get data for error monitoring dashboard"""
    return error_monitor.get_error_summary(hours=24)
