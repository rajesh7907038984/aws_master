# Environment Variables Setup Guide

## Overview
All hardcoded database and AWS details have been replaced with environment variables to ensure proper configuration management and security.

## Changes Made

### 1. Database Configuration
**Files Modified:**
- `LMS_Project/settings/production.py`
- `LMS_Project/settings/test.py`

**Changes:**
- Removed hardcoded database host: `lms-staging-db.c1wwcwuwq2pa.eu-west-2.rds.amazonaws.com`
- Added validation for required database environment variables
- All database settings now use environment variables with proper error handling

### 2. AWS S3 Configuration
**Files Modified:**
- `LMS_Project/settings/production.py`
- `scorm/views_old.py`
- `scorm/s3_direct.py`
- `certificates/verify_s3_permissions.sh`

**Changes:**
- Removed hardcoded S3 bucket name: `lms-staging-nexsy-io`
- Removed hardcoded fallback bucket: `elasticbeanstalk-eu-west-2-006619321740`
- All S3 configurations now use environment variables

### 3. Nginx Configuration
**Files Modified:**
- `config/nginx.conf`

**Changes:**
- Removed hardcoded load balancer URL: `lms-alb-222670874.eu-west-2.elb.amazonaws.com`
- Now uses `${NGINX_SERVER_NAME}` environment variable

## Required Environment Variables

### Database Configuration
```bash
AWS_DB_HOST=your-rds-endpoint.amazonaws.com
AWS_DB_NAME=your-database-name
AWS_DB_USER=your-database-user
AWS_DB_PASSWORD=your-database-password
AWS_DB_PORT=5432
```

### AWS S3 Configuration
```bash
AWS_ACCESS_KEY_ID=your-aws-access-key
AWS_SECRET_ACCESS_KEY=your-aws-secret-key
AWS_STORAGE_BUCKET_NAME=your-s3-bucket-name
AWS_S3_REGION_NAME=eu-west-2
```

### Application Configuration
```bash
DJANGO_SECRET_KEY=your-secret-key
PRIMARY_DOMAIN=your-domain.com
ALB_DOMAIN=your-alb-domain.com
```

### Nginx Configuration
```bash
NGINX_SERVER_NAME=your-server-name.com
```

## Environment Template
A comprehensive environment template has been created at `env.template` with all required variables documented.

## Validation
The production settings now include validation for critical environment variables:
- Database credentials are validated on startup
- Missing database variables will cause the application to fail with clear error messages
- AWS S3 variables show warnings if missing but won't crash the application

## Benefits
1. **Security**: No hardcoded credentials in the codebase
2. **Flexibility**: Easy to change configurations without code changes
3. **Environment-specific**: Different values for development, staging, and production
4. **Error Handling**: Clear error messages for missing required variables
5. **Maintainability**: Centralized configuration management

## Next Steps
1. Copy `env.template` to `.env` and fill in your actual values
2. Ensure all required environment variables are set in your deployment environment
3. Test the application to ensure all configurations work correctly
4. Update your deployment scripts to use environment variables instead of hardcoded values
