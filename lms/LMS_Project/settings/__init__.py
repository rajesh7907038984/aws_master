"""
Django settings for LMS_Project
Dynamically loads settings based on DJANGO_ENV environment variable
"""

import os
import logging

logger = logging.getLogger(__name__)

# Get environment from environment variable, default to staging
DJANGO_ENV = os.environ.get('DJANGO_ENV', 'staging').lower()

# Load appropriate settings based on environment
if DJANGO_ENV == 'staging':
    from .production import *
    # Override for staging environment
    ENVIRONMENT = 'staging'
    DEBUG = os.environ.get('DEBUG', 'False').lower() == 'true'  # Use environment variable
    # Get allowed hosts from environment, default to specific staging domains
    staging_hosts = os.environ.get('STAGING_ALLOWED_HOSTS', 'localhost,127.0.0.1,staging.nexsy.io').split(',')
    ALLOWED_HOSTS = [host.strip() for host in staging_hosts if host.strip()]
    
    logger.info("🏗️ Loading STAGING environment configuration")
    logger.info("🔧 Using STAGING instance connected services")
    
elif DJANGO_ENV == 'test':
    from .test import *
    logger.info("🧪 Loading TEST environment configuration")
    
else:  # production or default
    from .production import *
    logger.info("🏗️ Loading PRODUCTION environment configuration")
