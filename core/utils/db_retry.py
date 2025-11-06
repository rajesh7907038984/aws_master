"""
Database Retry Utility
Handles database connection errors with automatic retry logic
"""

import logging
import time
from functools import wraps
from django.db import OperationalError, DatabaseError, InterfaceError, connection
from django.db.utils import DatabaseError as DjangoDatabaseError

logger = logging.getLogger(__name__)

# Database errors that can be retried
RETRYABLE_DB_ERRORS = (
    OperationalError,
    InterfaceError,
    DjangoDatabaseError,
)

# Error messages that indicate connection issues
CONNECTION_ERROR_INDICATORS = [
    'SSL SYSCALL error',
    'EOF detected',
    'connection',
    'server closed the connection',
    'connection lost',
    'connection reset',
    'broken pipe',
    'connection refused',
    'timeout',
    'network',
]


def is_connection_error(error):
    """Check if an error is a connection-related error"""
    error_str = str(error).lower()
    return any(indicator in error_str for indicator in CONNECTION_ERROR_INDICATORS)


def retry_db_operation(max_attempts=3, delay=1.0, backoff_factor=2.0):
    """
    Decorator to retry database operations on connection errors
    
    Args:
        max_attempts: Maximum number of retry attempts (default: 3)
        delay: Initial delay between retries in seconds (default: 1.0)
        backoff_factor: Multiplier for delay on each retry (default: 2.0)
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_attempts):
                try:
                    # Close stale connections before retry
                    if attempt > 0:
                        try:
                            connection.close()
                        except Exception:
                            pass
                    
                    return func(*args, **kwargs)
                    
                except RETRYABLE_DB_ERRORS as e:
                    last_exception = e
                    
                    # Only retry if it's a connection error
                    if not is_connection_error(e):
                        logger.error(f"Non-retryable database error in {func.__name__}: {e}")
                        raise
                    
                    if attempt == max_attempts - 1:
                        logger.error(
                            f"All {max_attempts} attempts failed for {func.__name__}. "
                            f"Last error: {e}"
                        )
                        break
                    
                    # Calculate delay with exponential backoff
                    retry_delay = delay * (backoff_factor ** attempt)
                    logger.warning(
                        f"Database connection error in {func.__name__} (attempt {attempt + 1}/{max_attempts}): {e}. "
                        f"Retrying in {retry_delay:.1f}s..."
                    )
                    time.sleep(retry_delay)
                    
                except Exception as e:
                    # Don't retry for non-database errors
                    logger.error(f"Non-database error in {func.__name__}: {e}")
                    raise
            
            # If we exhausted all retries, raise the last exception
            if last_exception:
                raise last_exception
                
        return wrapper
    return decorator


def safe_db_query(query_func, max_attempts=3, delay=1.0, default=None):
    """
    Execute a database query with retry logic
    
    Args:
        query_func: Function that performs the database query
        max_attempts: Maximum number of retry attempts (default: 3)
        delay: Initial delay between retries in seconds (default: 1.0)
        default: Default value to return if all retries fail (optional)
    
    Returns:
        Result of query_func or default value if all retries fail
    """
    last_exception = None
    
    for attempt in range(max_attempts):
        try:
            # Close stale connections before retry
            if attempt > 0:
                try:
                    connection.close()
                except Exception:
                    pass
            
            return query_func()
            
        except RETRYABLE_DB_ERRORS as e:
            last_exception = e
            
            # Only retry if it's a connection error
            if not is_connection_error(e):
                logger.error(f"Non-retryable database error in safe_db_query: {e}")
                if default is not None:
                    return default
                raise
            
            if attempt == max_attempts - 1:
                logger.error(
                    f"All {max_attempts} attempts failed for safe_db_query. "
                    f"Last error: {e}"
                )
                break
            
            # Calculate delay with exponential backoff
            retry_delay = delay * (2.0 ** attempt)
            logger.warning(
                f"Database connection error in safe_db_query (attempt {attempt + 1}/{max_attempts}): {e}. "
                f"Retrying in {retry_delay:.1f}s..."
            )
            time.sleep(retry_delay)
            
        except Exception as e:
            # Don't retry for non-database errors
            logger.error(f"Non-database error in safe_db_query: {e}")
            raise
    
    # If we exhausted all retries and have a default, return it
    if default is not None:
        logger.warning(f"All retries failed for safe_db_query, returning default value")
        return default
    
    # Otherwise raise the last exception
    if last_exception:
        raise last_exception

