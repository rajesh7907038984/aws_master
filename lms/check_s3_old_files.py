#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
S3 Old Files Checker
Analyzes S3 bucket for old, unused, or orphaned files
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
from django.db import connection
from media_library.models import MediaFile
from courses.models import Course, Topic, Attachment
from assignments.models import Assignment
from quiz.models import Quiz
from certificates.models import CertificateTemplate, IssuedCertificate
from discussions.models import Attachment as DiscussionAttachment
from reports.models import ReportAttachment
from lms_messages.models import MessageAttachment
from conferences.models import ConferenceFile

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class S3OldFilesChecker:
    """Check for old and unused files in S3"""
    
    def __init__(self):
        self.s3_client = None
        self.bucket_name = getattr(settings, 'AWS_STORAGE_BUCKET_NAME', None)
        self.media_location = getattr(settings, 'AWS_S3_MEDIA_LOCATION', 'media')
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
    
    def get_all_s3_files(self):
        """Get all files from S3 bucket"""
        if not self.s3_client:
            logger.error("S3 client not initialized")
            return []
        
        files = []
        try:
            paginator = self.s3_client.get_paginator('list_objects_v2')
            pages = paginator.paginate(Bucket=self.bucket_name)
            
            for page in pages:
                if 'Contents' in page:
                    for obj in page['Contents']:
                        files.append({
                            'key': obj['Key'],
                            'size': obj['Size'],
                            'last_modified': obj['LastModified'],
                            'storage_class': obj.get('StorageClass', 'STANDARD')
                        })
            
            logger.info("Found {} files in S3 bucket".format(len(files)))
            return files
        except Exception as e:
            logger.error("Error listing S3 files: {}".format(e))
            return []
    
    def get_database_file_paths(self):
        """Get all file paths referenced in database"""
        file_paths = set()
        
        try:
            # MediaFile model
            media_files = MediaFile.objects.values_list('file_path', flat=True)
            file_paths.update(media_files)
            logger.info("Found {} MediaFile records".format(len(media_files)))
            
            # Course attachments
            course_attachments = Attachment.objects.exclude(file__isnull=True).exclude(file='').values_list('file', flat=True)
            file_paths.update(course_attachments)
            logger.info("Found {} Course attachments".format(len(course_attachments)))
            
            # Assignment attachments
            assignment_files = Assignment.objects.exclude(attachment__isnull=True).exclude(attachment='').values_list('attachment', flat=True)
            file_paths.update(assignment_files)
            logger.info("Found {} Assignment files".format(len(assignment_files)))
            
            # Quiz files
            quiz_files = Quiz.objects.exclude(attachment__isnull=True).exclude(attachment='').values_list('attachment', flat=True)
            file_paths.update(quiz_files)
            logger.info("Found {} Quiz files".format(len(quiz_files)))
            
            # Certificate templates
            cert_files = CertificateTemplate.objects.exclude(template_file__isnull=True).exclude(template_file='').values_list('template_file', flat=True)
            file_paths.update(cert_files)
            logger.info("Found {} Certificate template files".format(len(cert_files)))
            
            # Issued certificates
            issued_cert_files = IssuedCertificate.objects.exclude(certificate_file__isnull=True).exclude(certificate_file='').values_list('certificate_file', flat=True)
            file_paths.update(issued_cert_files)
            logger.info("Found {} Issued certificate files".format(len(issued_cert_files)))
            
            # Discussion attachments
            discussion_files = DiscussionAttachment.objects.exclude(file__isnull=True).exclude(file='').values_list('file', flat=True)
            file_paths.update(discussion_files)
            logger.info("Found {} Discussion attachments".format(len(discussion_files)))
            
            # Report attachments
            report_files = ReportAttachment.objects.exclude(file__isnull=True).exclude(file='').values_list('file', flat=True)
            file_paths.update(report_files)
            logger.info("Found {} Report attachments".format(len(report_files)))
            
            # Message attachments
            message_files = MessageAttachment.objects.exclude(file__isnull=True).exclude(file='').values_list('file', flat=True)
            file_paths.update(message_files)
            logger.info("Found {} Message attachments".format(len(message_files)))
            
            # Conference files
            conference_files = ConferenceFile.objects.exclude(local_file__isnull=True).exclude(local_file='').values_list('local_file', flat=True)
            file_paths.update(conference_files)
            logger.info("Found {} Conference files".format(len(conference_files)))
            
            logger.info("Total database file references: {}".format(len(file_paths)))
            return file_paths
            
        except Exception as e:
            logger.error("Error getting database file paths: {}".format(e))
            return set()
    
    def find_orphaned_files(self, s3_files, db_files):
        """Find files in S3 that are not referenced in database"""
        orphaned = []
        
        for s3_file in s3_files:
            s3_key = s3_file['key']
            
            # Remove media/ prefix for comparison
            if s3_key.startswith("{}".format(self.media_location)):
                db_key = s3_key[len("{}".format(self.media_location)):]
            else:
                db_key = s3_key
            
            # Check if file is referenced in database
            is_referenced = False
            for db_file in db_files:
                if db_file and (db_key in db_file or db_file in db_key):
                    is_referenced = True
                    break
            
            if not is_referenced:
                orphaned.append(s3_file)
        
        return orphaned
    
    def find_old_files(self, s3_files, days_old=90):
        """Find files older than specified days"""
        cutoff_date = datetime.now() - timedelta(days=days_old)
        old_files = []
        
        for s3_file in s3_files:
            if s3_file['last_modified'].replace(tzinfo=None) < cutoff_date:
                old_files.append(s3_file)
        
        return old_files
    
    def find_large_files(self, s3_files, size_mb=100):
        """Find files larger than specified size in MB"""
        size_bytes = size_mb * 1024 * 1024
        large_files = []
        
        for s3_file in s3_files:
            if s3_file['size'] > size_bytes:
                large_files.append(s3_file)
        
        return large_files
    
    def calculate_storage_usage(self, files):
        """Calculate total storage usage"""
        total_size = sum(file['size'] for file in files)
        return {
            'total_files': len(files),
            'total_size_bytes': total_size,
            'total_size_mb': total_size / (1024 * 1024),
            'total_size_gb': total_size / (1024 * 1024 * 1024)
        }
    
    def generate_report(self):
        """Generate comprehensive report of S3 files"""
        print("=" * 80)
        print("S3 OLD FILES ANALYSIS REPORT")
        print("=" * 80)
        print("Bucket: {}".format(self.bucket_name))
        print("Media Location: {}".format(self.media_location))
        print("Analysis Date: {}".format(datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        print()
        
        # Get all S3 files
        print("1. Fetching S3 files...")
        s3_files = self.get_all_s3_files()
        if not s3_files:
            print("ERROR: No S3 files found or error accessing S3")
            return
        
        # Get database file references
        print("2. Fetching database file references...")
        db_files = self.get_database_file_paths()
        
        # Calculate storage usage
        print("3. Calculating storage usage...")
        storage_stats = self.calculate_storage_usage(s3_files)
        
        print("STORAGE STATISTICS:")
        print("   Total Files: {:,}".format(storage_stats['total_files']))
        print("   Total Size: {:.2f} GB ({:.2f} MB)".format(storage_stats['total_size_gb'], storage_stats['total_size_mb']))
        print()
        
        # Find orphaned files
        print("4. Finding orphaned files...")
        orphaned_files = self.find_orphaned_files(s3_files, db_files)
        orphaned_stats = self.calculate_storage_usage(orphaned_files)
        
        print("ORPHANED FILES (not referenced in database):")
        print("   Count: {:,}".format(orphaned_stats['total_files']))
        print("   Size: {:.2f} GB ({:.2f} MB)".format(orphaned_stats['total_size_gb'], orphaned_stats['total_size_mb']))
        if orphaned_files:
            print("   Potential savings: {:.2f} GB".format(orphaned_stats['total_size_gb']))
        print()
        
        # Find old files
        print("5. Finding old files (older than 90 days)...")
        old_files = self.find_old_files(s3_files, days_old=90)
        old_stats = self.calculate_storage_usage(old_files)
        
        print("OLD FILES (older than 90 days):")
        print("   Count: {:,}".format(old_stats['total_files']))
        print("   Size: {:.2f} GB ({:.2f} MB)".format(old_stats['total_size_gb'], old_stats['total_size_mb']))
        print()
        
        # Find large files
        print("6. Finding large files (larger than 100 MB)...")
        large_files = self.find_large_files(s3_files, size_mb=100)
        large_stats = self.calculate_storage_usage(large_files)
        
        print("LARGE FILES (larger than 100 MB):")
        print("   Count: {:,}".format(large_stats['total_files']))
        print("   Size: {:.2f} GB ({:.2f} MB)".format(large_stats['total_size_gb'], large_stats['total_size_mb']))
        print()
        
        # Show sample orphaned files
        if orphaned_files:
            print("SAMPLE ORPHANED FILES (first 20):")
            for i, file in enumerate(orphaned_files[:20]):
                size_mb = file['size'] / (1024 * 1024)
                print("   {:2d}. {} ({:.2f} MB, {})".format(i+1, file['key'], size_mb, file['last_modified'].strftime('%Y-%m-%d')))
            if len(orphaned_files) > 20:
                print("   ... and {} more files".format(len(orphaned_files) - 20))
            print()
        
        # Show sample old files
        if old_files:
            print("SAMPLE OLD FILES (first 20):")
            for i, file in enumerate(old_files[:20]):
                size_mb = file['size'] / (1024 * 1024)
                print("   {:2d}. {} ({:.2f} MB, {})".format(i+1, file['key'], size_mb, file['last_modified'].strftime('%Y-%m-%d')))
            if len(old_files) > 20:
                print("   ... and {} more files".format(len(old_files) - 20))
            print()
        
        # Show sample large files
        if large_files:
            print("SAMPLE LARGE FILES (first 20):")
            for i, file in enumerate(large_files[:20]):
                size_mb = file['size'] / (1024 * 1024)
                print("   {:2d}. {} ({:.2f} MB, {})".format(i+1, file['key'], size_mb, file['last_modified'].strftime('%Y-%m-%d')))
            if len(large_files) > 20:
                print("   ... and {} more files".format(len(large_files) - 20))
            print()
        
        # Recommendations
        print("RECOMMENDATIONS:")
        if orphaned_stats['total_size_gb'] > 1:
            print("   WARNING: Consider cleaning up {:.2f} GB of orphaned files".format(orphaned_stats['total_size_gb']))
        if old_stats['total_size_gb'] > 5:
            print("   WARNING: Consider archiving {:.2f} GB of old files".format(old_stats['total_size_gb']))
        if large_stats['total_size_gb'] > 2:
            print("   WARNING: Review {:.2f} GB of large files for optimization".format(large_stats['total_size_gb']))
        
        if orphaned_stats['total_size_gb'] < 0.1 and old_stats['total_size_gb'] < 1:
            print("   OK: S3 storage appears to be well-maintained")
        
        print()
        print("=" * 80)
        print("ANALYSIS COMPLETE")
        print("=" * 80)

def main():
    """Main function"""
    try:
        checker = S3OldFilesChecker()
        if not checker.s3_client:
            print("ERROR: Failed to initialize S3 client. Check AWS credentials and bucket configuration.")
            return
        
        checker.generate_report()
        
    except Exception as e:
        logger.error("Error during analysis: {}".format(e))
        print("ERROR: {}".format(e))

if __name__ == "__main__":
    main()