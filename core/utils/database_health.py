"""
Database Health Check Utilities
Prevents database-related 500 errors with connection monitoring
"""

import logging
import time
from typing import Dict, Any, Optional
from django.db import connection, transaction
from django.core.cache import cache
from django.conf import settings

logger = logging.getLogger(__name__)

class DatabaseHealthChecker:
    """Database health monitoring and connection management"""
    
    def __init__(self):
        self.connection_timeout = getattr(settings, 'DATABASE_CONNECTION_TIMEOUT', 30)
        self.max_retries = getattr(settings, 'DATABASE_MAX_RETRIES', 3)
        self.retry_delay = getattr(settings, 'DATABASE_RETRY_DELAY', 1)
    
    def check_connection(self) -> Dict[str, Any]:
        """Check database connection health"""
        try:
            start_time = time.time()
            
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                result = cursor.fetchone()
            
            response_time = time.time() - start_time
            
            return {
                'status': 'healthy',
                'response_time': response_time,
                'timestamp': time.time(),
                'connection_id': connection.connection_id if hasattr(connection, 'connection_id') else None
            }
            
        except Exception as e:
            logger.error(f"Database connection check failed: {str(e)}")
            return {
                'status': 'unhealthy',
                'error': str(e),
                'timestamp': time.time()
            }
    
    def test_transaction(self) -> Dict[str, Any]:
        """Test database transaction capability"""
        try:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("SELECT 1")
                    result = cursor.fetchone()
                
                # Test rollback capability
                raise Exception("Test rollback")
                
        except Exception as e:
            if "Test rollback" in str(e):
                return {
                    'status': 'healthy',
                    'transaction_support': True,
                    'timestamp': time.time()
                }
            else:
                return {
                    'status': 'unhealthy',
                    'error': str(e),
                    'transaction_support': False,
                    'timestamp': time.time()
                }
    
    def get_connection_info(self) -> Dict[str, Any]:
        """Get database connection information"""
        try:
            with connection.cursor() as cursor:
                # Get database version
                cursor.execute("SELECT version()")
                version = cursor.fetchone()[0]
                
                # Get connection count (if supported)
                try:
                    cursor.execute("SELECT count(*) FROM pg_stat_activity WHERE state = 'active'")
                    active_connections = cursor.fetchone()[0]
                except:
                    active_connections = None
                
                return {
                    'version': version,
                    'active_connections': active_connections,
                    'connection_id': connection.connection_id if hasattr(connection, 'connection_id') else None,
                    'timestamp': time.time()
                }
                
        except Exception as e:
            logger.error(f"Error getting connection info: {str(e)}")
            return {
                'error': str(e),
                'timestamp': time.time()
            }
    
    def safe_database_operation(self, operation_func, *args, **kwargs):
        """Safely execute database operations with retry logic"""
        last_exception = None
        
        for attempt in range(self.max_retries):
            try:
                return operation_func(*args, **kwargs)
            except (OperationalError, DatabaseError) as e:
                last_exception = e
                logger.warning(f"Database operation failed (attempt {attempt + 1}/{self.max_retries}): {str(e)}")
                
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay * (attempt + 1))  # Exponential backoff
                    continue
                else:
                    break
            except Exception as e:
                # Non-database errors should not be retried
                raise e
        
        # If we get here, all retries failed
        logger.error(f"Database operation failed after {self.max_retries} attempts: {str(last_exception)}")
        raise last_exception
    
    def monitor_connection_pool(self) -> Dict[str, Any]:
        """Monitor database connection pool health"""
        try:
            # This is a simplified version - in production you might want to use
            # more sophisticated connection pool monitoring
            health_check = self.check_connection()
            
            return {
                'pool_status': 'healthy' if health_check['status'] == 'healthy' else 'unhealthy',
                'last_check': health_check['timestamp'],
                'response_time': health_check.get('response_time', 0)
            }
            
        except Exception as e:
            logger.error(f"Error monitoring connection pool: {str(e)}")
            return {
                'pool_status': 'unhealthy',
                'error': str(e),
                'timestamp': time.time()
            }

# Global database health checker
db_health_checker = DatabaseHealthChecker()

def safe_db_operation(operation_func, *args, **kwargs):
    """Convenience function for safe database operations"""
    return db_health_checker.safe_database_operation(operation_func, *args, **kwargs)

def check_db_health() -> Dict[str, Any]:
    """Convenience function to check database health"""
    return db_health_checker.check_connection()
