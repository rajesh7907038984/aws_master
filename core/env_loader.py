"""
Unified Environment Variable Loader for LMS Project
This module provides a centralized way to load environment variables from a single .env file
"""

import os
import logging
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class EnvironmentLoader:
    """
    Centralized environment variable loader that:
    1. Loads variables from a single .env file
    2. Provides fallback values
    3. Validates required variables
    4. Supports different environments (production, staging, development)
    """
    
    def __init__(self, env_file_path: Optional[str] = None):
        """
        Initialize the environment loader
        
        Args:
            env_file_path: Path to the .env file. If None, will look for .env in project root
        """
        if env_file_path is None:
            # Find project root (where manage.py is located)
            current_dir = Path(__file__).resolve()
            project_root = current_dir.parent.parent
            env_file_path = project_root / '.env'
        
        self.env_file_path = Path(env_file_path)
        self.loaded_variables = {}
        self._load_environment_variables()
    
    def _load_environment_variables(self):
        """Load environment variables from the .env file"""
        if not self.env_file_path.exists():
            logger.warning(f" Environment file not found: {self.env_file_path}")
            logger.info("Using system environment variables only")
            return
        
        logger.info(f"📋 Loading environment variables from: {self.env_file_path}")
        
        try:
            with open(self.env_file_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    
                    # Skip empty lines and comments
                    if not line or line.startswith('#'):
                        continue
                    
                    # Parse key=value pairs
                    if '=' in line:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip()
                        
                        # Remove quotes if present
                        if value.startswith('"') and value.endswith('"'):
                            value = value[1:-1]
                        elif value.startswith("'") and value.endswith("'"):
                            value = value[1:-1]
                        
                        # Always override environment variables from .env file
                        # This ensures production.env values take precedence over stale system env vars
                        if os.environ.get(key) and os.environ.get(key) != value:
                            logger.info(f"Overriding {key} with value from .env file")
                        os.environ[key] = value
                        self.loaded_variables[key] = value
                    else:
                        logger.warning(f"Invalid line format in {self.env_file_path}:{line_num}: {line}")
            
            logger.info(f" Loaded {len(self.loaded_variables)} environment variables")
            
            # Log key variables (without sensitive data)
            self._log_loaded_variables()
            
        except Exception as e:
            logger.error(f" Failed to load environment variables: {e}")
            raise
    
    def _log_loaded_variables(self):
        """Log loaded variables (without sensitive data)"""
        sensitive_keys = {
            'DJANGO_SECRET_KEY', 'AWS_DB_PASSWORD', 'AWS_SECRET_ACCESS_KEY',
            'OUTLOOK_CLIENT_SECRET', 'ANTHROPIC_API_KEY', 'IDEAL_POSTCODES_API_KEY'
        }
        
        for key, value in self.loaded_variables.items():
            if key in sensitive_keys:
                logger.info(f"🔐 {key}: {'✓ Set' if value else '✗ Not set'}")
            else:
                logger.info(f"📋 {key}: {value}")
    
    def get(self, key: str, default: Any = None, required: bool = False) -> Any:
        """
        Get an environment variable with optional default and validation
        
        Args:
            key: Environment variable name
            default: Default value if not found
            required: If True, raise error if variable is not set
            
        Returns:
            Environment variable value or default
        """
        value = os.environ.get(key, default)
        
        if required and not value:
            raise ValueError(f"Required environment variable {key} is not set")
        
        return value
    
    def get_bool(self, key: str, default: bool = False) -> bool:
        """Get a boolean environment variable"""
        value = os.environ.get(key, str(default)).lower()
        return value in ('true', '1', 'yes', 'on')
    
    def get_int(self, key: str, default: int = 0) -> int:
        """Get an integer environment variable"""
        try:
            return int(os.environ.get(key, str(default)))
        except ValueError:
            logger.warning(f"Invalid integer value for {key}, using default {default}")
            return default
    
    def get_list(self, key: str, separator: str = ',', default: list = None) -> list:
        """Get a list environment variable (comma-separated by default)"""
        if default is None:
            default = []
        
        value = os.environ.get(key, '')
        if not value:
            return default
        
        return [item.strip() for item in value.split(separator) if item.strip()]
    
    def validate_required_variables(self, required_vars: list):
        """
        Validate that all required variables are set
        
        Args:
            required_vars: List of required environment variable names
        """
        missing_vars = []
        
        for var in required_vars:
            if not os.environ.get(var):
                missing_vars.append(var)
        
        if missing_vars:
            raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")
        
        logger.info(" All required environment variables are set")
    
    def get_environment_info(self) -> Dict[str, Any]:
        """Get information about the current environment configuration"""
        return {
            'env_file_path': str(self.env_file_path),
            'env_file_exists': self.env_file_path.exists(),
            'loaded_variables_count': len(self.loaded_variables),
            'loaded_variables': list(self.loaded_variables.keys()),
            'django_env': os.environ.get('DJANGO_ENV', 'unknown'),
            'django_settings_module': os.environ.get('DJANGO_SETTINGS_MODULE', 'unknown'),
        }

# Global instance
env_loader = EnvironmentLoader()

# Convenience functions
def get_env(key: str, default: Any = None, required: bool = False) -> Any:
    """Get an environment variable"""
    return env_loader.get(key, default, required)

def get_bool_env(key: str, default: bool = False) -> bool:
    """Get a boolean environment variable"""
    return env_loader.get_bool(key, default)

def get_int_env(key: str, default: int = 0) -> int:
    """Get an integer environment variable"""
    return env_loader.get_int(key, default)

def get_list_env(key: str, separator: str = ',', default: list = None) -> list:
    """Get a list environment variable"""
    return env_loader.get_list(key, separator, default)

def validate_environment():
    """Validate that all required environment variables are set"""
    required_vars = [
        'DJANGO_SECRET_KEY',
        'AWS_DB_PASSWORD',
        'AWS_DB_HOST',
        'AWS_DB_USER',
        'AWS_DB_NAME',
    ]
    
    env_loader.validate_required_variables(required_vars)
