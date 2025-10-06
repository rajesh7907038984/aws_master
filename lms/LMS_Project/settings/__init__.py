"""
Django settings for LMS_Project
Dynamically loads settings based on DJANGO_ENV environment variable
"""

import os

# Get environment from environment variable, default to staging
DJANGO_ENV = os.environ.get('DJANGO_ENV', 'staging').lower()

# Load appropriate settings based on environment
if DJANGO_ENV == 'staging':
    from .production import *
    # Override for staging environment
    ENVIRONMENT = 'staging'
    
    print(" Loading STAGING environment configuration")
    print(" Using STAGING instance connected services")
    
elif DJANGO_ENV == 'test':
    from .test import *
    print("🧪 Loading TEST environment configuration")
    
else:  # production or default
    from .production import *
    print(" Loading PRODUCTION environment configuration")
