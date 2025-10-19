#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
S3 Old Files Cleanup Script
Safely removes old and unused files from S3 bucket
"""

import os
import sys
import django
from datetime import datetime, timedelta
import boto3
from botocore.exceptions import ClientError, NoCredentialsError
import logging

# Setup Django
sys.path.append('/home/ec2-user/lms')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings.production')
django.setup()

from django.conf import settings

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class S3CleanupManager:
    """Clean up old and unused files from S3"""
    
    def __init__(self):
        self.s3_client = None
        self.bucket_name = getattr(settings, 'AWS_STORAGE_BUCKET_NAME', None)
        self._initialize_s3_client()
        
    def _initialize_s3_client(self):
        """Initialize S3 client"""
        try:
            if self.bucket_name:
                access_key_id = getattr(settings, 'AWS_ACCESS_KEY_ID', None)
                secret_access_key = getattr(settings, 'AWS_SECRET_ACCESS_KEY', None)
                
                if access_key_id in ['your_access_key_here', None, ''] or \
                   secret_access_key in ['your_secret_key_here', None, '']:
                    # Use IAM role-based authentication
                    logger.info("Using IAM role-based authentication for S3")
                    self.s3_client = boto3.client(
                        's3',
                        region_name=getattr(settings, 'AWS_S3_REGION_NAME', 'us-east-1')
                    )
                else:
                    # Use explicit credentials
                    logger.info("Using explicit AWS credentials for S3")
                    self.s3_client = boto3.client(
                        's3',
                        aws_access_key_id=access_key_id,
                        aws_secret_access_key=secret_access_key,
                        region_name=getattr(settings, 'AWS_S3_REGION_NAME', 'us-east-1')
                    )
                
                # Test connection
                self.s3_client.head_bucket(Bucket=self.bucket_name)
                logger.info("S3 client initialized for bucket: {}".format(self.bucket_name))
            else:
                logger.error("No S3 bucket configured")
        except Exception as e:
            logger.error("S3 client initialization failed: {}".format(e))
            self.s3_client = None
    
    def get_temp_upload_files(self):
        """Get temporary upload files that are likely safe to delete"""
        if not self.s3_client:
            return []
        
        temp_files = []
        try:
            paginator = self.s3_client.get_paginator('list_objects_v2')
            pages = paginator.paginate(Bucket=self.bucket_name, Prefix='courses/temp_uploads/')
            
            for page in pages:
                if 'Contents' in page:
                    for obj in page['Contents']:
                        # Check if file is older than 1 day
                        if obj['LastModified'] < datetime.now().replace(tzinfo=obj['LastModified'].tzinfo) - timedelta(days=1):
                            temp_files.append({
                                'key': obj['Key'],
                                'size': obj['Size'],
                                'last_modified': obj['LastModified']
                            })
            
            logger.info("Found {} temporary upload files older than 1 day".format(len(temp_files)))
            return temp_files
        except Exception as e:
            logger.error("Error listing temp files: {}".format(e))
            return []
    
    def get_duplicate_files(self):
        """Find potential duplicate files based on size and name patterns"""
        if not self.s3_client:
            return []
        
        all_files = []
        try:
            paginator = self.s3_client.get_paginator('list_objects_v2')
            pages = paginator.paginate(Bucket=self.bucket_name)
            
            for page in pages:
                if 'Contents' in page:
                    for obj in page['Contents']:
                        all_files.append({
                            'key': obj['Key'],
                            'size': obj['Size'],
                            'last_modified': obj['LastModified']
                        })
            
            # Group files by size to find potential duplicates
            size_groups = {}
            for file in all_files:
                size = file['size']
                if size not in size_groups:
                    size_groups[size] = []
                size_groups[size].append(file)
            
            # Find groups with multiple files (potential duplicates)
            duplicates = []
            for size, files in size_groups.items():
                if len(files) > 1 and size > 1024:  # Only consider files larger than 1KB
                    # Sort by last modified date, keep the newest
                    files.sort(key=lambda x: x['last_modified'], reverse=True)
                    # Add all but the newest to duplicates list
                    duplicates.extend(files[1:])
            
            logger.info("Found {} potential duplicate files".format(len(duplicates)))
            return duplicates
        except Exception as e:
            logger.error("Error finding duplicates: {}".format(e))
            return []
    
    def delete_files(self, files_to_delete, dry_run=True):
        """Delete files from S3"""
        if not self.s3_client:
            logger.error("S3 client not initialized")
            return False
        
        if not files_to_delete:
            logger.info("No files to delete")
            return True
        
        deleted_count = 0
        error_count = 0
        total_size = 0
        
        for file_info in files_to_delete:
            try:
                if dry_run:
                    logger.info("DRY RUN: Would delete {}".format(file_info['key']))
                    deleted_count += 1
                    total_size += file_info['size']
                else:
                    self.s3_client.delete_object(Bucket=self.bucket_name, Key=file_info['key'])
                    logger.info("Deleted: {}".format(file_info['key']))
                    deleted_count += 1
                    total_size += file_info['size']
            except Exception as e:
                logger.error("Error deleting {}: {}".format(file_info['key'], e))
                error_count += 1
        
        logger.info("Cleanup completed: {} deleted, {} errors, {} MB freed".format(
            deleted_count, error_count, total_size / (1024 * 1024)))
        
        return error_count == 0
    
    def cleanup_temp_files(self, dry_run=True):
        """Clean up temporary upload files"""
        print("=" * 60)
        print("CLEANING UP TEMPORARY UPLOAD FILES")
        print("=" * 60)
        
        temp_files = self.get_temp_upload_files()
        if not temp_files:
            print("No temporary files found to clean up")
            return True
        
        print("Found {} temporary files to clean up:".format(len(temp_files)))
        total_size = sum(f['size'] for f in temp_files)
        print("Total size: {:.2f} MB".format(total_size / (1024 * 1024)))
        
        if dry_run:
            print("\nDRY RUN - Files that would be deleted:")
            for i, file in enumerate(temp_files[:10]):  # Show first 10
                size_mb = file['size'] / (1024 * 1024)
                print("  {}. {} ({:.2f} MB, {})".format(
                    i+1, file['key'], size_mb, file['last_modified'].strftime('%Y-%m-%d %H:%M')))
            if len(temp_files) > 10:
                print("  ... and {} more files".format(len(temp_files) - 10))
        else:
            print("\nDeleting temporary files...")
            success = self.delete_files(temp_files, dry_run=False)
            if success:
                print("✅ Successfully cleaned up temporary files")
            else:
                print("❌ Some errors occurred during cleanup")
            return success
        
        return True
    
    def cleanup_duplicates(self, dry_run=True):
        """Clean up duplicate files"""
        print("=" * 60)
        print("CLEANING UP DUPLICATE FILES")
        print("=" * 60)
        
        duplicate_files = self.get_duplicate_files()
        if not duplicate_files:
            print("No duplicate files found to clean up")
            return True
        
        print("Found {} potential duplicate files to clean up:".format(len(duplicate_files)))
        total_size = sum(f['size'] for f in duplicate_files)
        print("Total size: {:.2f} MB".format(total_size / (1024 * 1024)))
        
        if dry_run:
            print("\nDRY RUN - Files that would be deleted:")
            for i, file in enumerate(duplicate_files[:10]):  # Show first 10
                size_mb = file['size'] / (1024 * 1024)
                print("  {}. {} ({:.2f} MB, {})".format(
                    i+1, file['key'], size_mb, file['last_modified'].strftime('%Y-%m-%d %H:%M')))
            if len(duplicate_files) > 10:
                print("  ... and {} more files".format(len(duplicate_files) - 10))
        else:
            print("\nDeleting duplicate files...")
            success = self.delete_files(duplicate_files, dry_run=False)
            if success:
                print("✅ Successfully cleaned up duplicate files")
            else:
                print("❌ Some errors occurred during cleanup")
            return success
        
        return True
    
    def interactive_cleanup(self):
        """Interactive cleanup with user confirmation"""
        print("=" * 80)
        print("S3 CLEANUP INTERACTIVE MODE")
        print("=" * 80)
        print("Bucket: {}".format(self.bucket_name))
        print("This will help you clean up old and unused files from your S3 bucket.")
        print()
        
        if not self.s3_client:
            print("ERROR: Failed to initialize S3 client")
            return False
        
        # Check temp files
        temp_files = self.get_temp_upload_files()
        if temp_files:
            total_size = sum(f['size'] for f in temp_files)
            print("1. TEMPORARY UPLOAD FILES:")
            print("   Found {} files ({:.2f} MB)".format(len(temp_files), total_size / (1024 * 1024)))
            print("   These are temporary course upload files older than 1 day")
            
            response = input("   Delete these temporary files? (y/N): ").strip().lower()
            if response == 'y':
                success = self.delete_files(temp_files, dry_run=False)
                if success:
                    print("   ✅ Temporary files cleaned up")
                else:
                    print("   ❌ Some errors occurred")
            else:
                print("   Skipped temporary files cleanup")
        else:
            print("1. TEMPORARY UPLOAD FILES: None found")
        
        print()
        
        # Check duplicates
        duplicate_files = self.get_duplicate_files()
        if duplicate_files:
            total_size = sum(f['size'] for f in duplicate_files)
            print("2. DUPLICATE FILES:")
            print("   Found {} potential duplicates ({:.2f} MB)".format(len(duplicate_files), total_size / (1024 * 1024)))
            print("   These are files with the same size (potential duplicates)")
            
            response = input("   Delete these duplicate files? (y/N): ").strip().lower()
            if response == 'y':
                success = self.delete_files(duplicate_files, dry_run=False)
                if success:
                    print("   ✅ Duplicate files cleaned up")
                else:
                    print("   ❌ Some errors occurred")
            else:
                print("   Skipped duplicate files cleanup")
        else:
            print("2. DUPLICATE FILES: None found")
        
        print()
        print("=" * 80)
        print("CLEANUP COMPLETE")
        print("=" * 80)

def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Clean up old files from S3 bucket')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be deleted without actually deleting')
    parser.add_argument('--temp-files', action='store_true', help='Clean up temporary upload files')
    parser.add_argument('--duplicates', action='store_true', help='Clean up duplicate files')
    parser.add_argument('--interactive', action='store_true', help='Interactive cleanup mode')
    
    args = parser.parse_args()
    
    try:
        cleanup_manager = S3CleanupManager()
        if not cleanup_manager.s3_client:
            print("ERROR: Failed to initialize S3 client. Check AWS credentials and bucket configuration.")
            return
        
        if args.interactive:
            cleanup_manager.interactive_cleanup()
        else:
            if args.temp_files:
                cleanup_manager.cleanup_temp_files(dry_run=args.dry_run)
            if args.duplicates:
                cleanup_manager.cleanup_duplicates(dry_run=args.dry_run)
            
            if not args.temp_files and not args.duplicates:
                print("Please specify --temp-files, --duplicates, or --interactive")
                print("Use --help for more information")
        
    except Exception as e:
        logger.error("Error during cleanup: {}".format(e))
        print("ERROR: {}".format(e))

if __name__ == "__main__":
    main()
