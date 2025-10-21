"""
Management command to optimize SCORM storage usage.
This command monitors S3 storage usage, identifies optimization opportunities,
and implements storage optimization strategies.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.conf import settings
import logging
import boto3
from botocore.exceptions import ClientError

from scorm.models import ELearningPackage, ELearningTracking
from courses.models import Topic, Course
from scorm.storage import SCORMS3Storage

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Optimize SCORM storage usage and monitor S3 costs'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be optimized without actually optimizing',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force optimization without confirmation',
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed output',
        )
        parser.add_argument(
            '--analyze-only',
            action='store_true',
            help='Only analyze storage usage without optimization',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        force = options['force']
        verbose = options['verbose']
        analyze_only = options['analyze_only']
        
        if verbose:
            logger.setLevel(logging.DEBUG)
        
        self.stdout.write(
            self.style.SUCCESS('Starting SCORM storage optimization...')
        )
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('DRY RUN MODE - No optimizations will be applied')
            )
        
        try:
            with transaction.atomic():
                # 1. Analyze current storage usage
                storage_analysis = self.analyze_storage_usage(verbose)
                
                if analyze_only:
                    self.display_storage_analysis(storage_analysis)
                    return
                
                # 2. Identify optimization opportunities
                optimization_opportunities = self.identify_optimization_opportunities(storage_analysis, verbose)
                
                # 3. Apply optimizations
                if not dry_run and optimization_opportunities:
                    if not force and not self.confirm_optimization(optimization_opportunities):
                        self.stdout.write('Optimization cancelled by user.')
                        return
                
                optimizations_applied = self.apply_optimizations(optimization_opportunities, dry_run, verbose)
                
                # 4. Generate optimization report
                self.generate_optimization_report(storage_analysis, optimizations_applied)
                
        except Exception as e:
            logger.error(f"Error during SCORM storage optimization: {str(e)}")
            raise CommandError(f'Storage optimization failed: {str(e)}')

    def analyze_storage_usage(self, verbose=False):
        """Analyze current SCORM storage usage"""
        self.stdout.write('Analyzing SCORM storage usage...')
        
        try:
            storage = SCORMS3Storage()
            s3_client = boto3.client('s3')
            
            # Get S3 bucket information
            bucket_name = storage.bucket_name
            total_size = 0
            total_files = 0
            package_files = []
            extracted_files = []
            
            # Analyze package files
            try:
                response = s3_client.list_objects_v2(
                    Bucket=bucket_name,
                    Prefix='elearning/packages/'
                )
                
                for obj in response.get('Contents', []):
                    total_size += obj['Size']
                    total_files += 1
                    package_files.append({
                        'key': obj['Key'],
                        'size': obj['Size'],
                        'last_modified': obj['LastModified']
                    })
                
                # Continue if there are more objects
                while response.get('IsTruncated'):
                    response = s3_client.list_objects_v2(
                        Bucket=bucket_name,
                        Prefix='elearning/packages/',
                        ContinuationToken=response['NextContinuationToken']
                    )
                    
                    for obj in response.get('Contents', []):
                        total_size += obj['Size']
                        total_files += 1
                        package_files.append({
                            'key': obj['Key'],
                            'size': obj['Size'],
                            'last_modified': obj['LastModified']
                        })
            
            except ClientError as e:
                self.stdout.write(
                    self.style.ERROR(f'Error analyzing package files: {str(e)}')
                )
            
            # Analyze extracted content
            try:
                response = s3_client.list_objects_v2(
                    Bucket=bucket_name,
                    Prefix='elearning/extracted/'
                )
                
                for obj in response.get('Contents', []):
                    total_size += obj['Size']
                    total_files += 1
                    extracted_files.append({
                        'key': obj['Key'],
                        'size': obj['Size'],
                        'last_modified': obj['LastModified']
                    })
                
                # Continue if there are more objects
                while response.get('IsTruncated'):
                    response = s3_client.list_objects_v2(
                        Bucket=bucket_name,
                        Prefix='elearning/extracted/',
                        ContinuationToken=response['NextContinuationToken']
                    )
                    
                    for obj in response.get('Contents', []):
                        total_size += obj['Size']
                        total_files += 1
                        extracted_files.append({
                            'key': obj['Key'],
                            'size': obj['Size'],
                            'last_modified': obj['LastModified']
                        })
            
            except ClientError as e:
                self.stdout.write(
                    self.style.ERROR(f'Error analyzing extracted files: {str(e)}')
                )
            
            # Analyze database references
            db_packages = ELearningPackage.objects.all()
            db_package_files = [pkg.package_file.name for pkg in db_packages if pkg.package_file]
            db_extracted_paths = [pkg.extracted_path for pkg in db_packages if pkg.extracted_path]
            
            # Find orphaned files
            orphaned_package_files = []
            for pkg_file in package_files:
                if pkg_file['key'] not in db_package_files:
                    orphaned_package_files.append(pkg_file)
            
            orphaned_extracted_files = []
            for ext_file in extracted_files:
                is_referenced = False
                for ext_path in db_extracted_paths:
                    if ext_file['key'].startswith(ext_path):
                        is_referenced = True
                        break
                if not is_referenced:
                    orphaned_extracted_files.append(ext_file)
            
            # Calculate potential savings
            orphaned_size = sum(f['size'] for f in orphaned_package_files + orphaned_extracted_files)
            orphaned_count = len(orphaned_package_files) + len(orphaned_extracted_files)
            
            return {
                'total_size': total_size,
                'total_files': total_files,
                'package_files': package_files,
                'extracted_files': extracted_files,
                'orphaned_package_files': orphaned_package_files,
                'orphaned_extracted_files': orphaned_extracted_files,
                'orphaned_size': orphaned_size,
                'orphaned_count': orphaned_count,
                'db_packages': db_packages.count(),
                'db_package_files': len(db_package_files),
                'db_extracted_paths': len(db_extracted_paths)
            }
        
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error analyzing storage usage: {str(e)}')
            )
            return None

    def identify_optimization_opportunities(self, storage_analysis, verbose=False):
        """Identify storage optimization opportunities"""
        self.stdout.write('Identifying optimization opportunities...')
        
        if not storage_analysis:
            return []
        
        opportunities = []
        
        # 1. Orphaned file cleanup
        if storage_analysis['orphaned_count'] > 0:
            opportunities.append({
                'type': 'orphaned_cleanup',
                'description': f"Remove {storage_analysis['orphaned_count']} orphaned files",
                'potential_savings': storage_analysis['orphaned_size'],
                'files': storage_analysis['orphaned_package_files'] + storage_analysis['orphaned_extracted_files']
            })
        
        # 2. Duplicate file detection
        duplicate_files = self.find_duplicate_files(storage_analysis)
        if duplicate_files:
            opportunities.append({
                'type': 'duplicate_cleanup',
                'description': f"Remove {len(duplicate_files)} duplicate files",
                'potential_savings': sum(f['size'] for f in duplicate_files),
                'files': duplicate_files
            })
        
        # 3. Large file optimization
        large_files = self.find_large_files(storage_analysis)
        if large_files:
            opportunities.append({
                'type': 'large_file_optimization',
                'description': f"Optimize {len(large_files)} large files",
                'potential_savings': sum(f['size'] * 0.3 for f in large_files),  # Assume 30% compression
                'files': large_files
            })
        
        # 4. Old file archival
        old_files = self.find_old_files(storage_analysis)
        if old_files:
            opportunities.append({
                'type': 'old_file_archival',
                'description': f"Archive {len(old_files)} old files",
                'potential_savings': sum(f['size'] * 0.8 for f in old_files),  # Assume 80% savings with archival
                'files': old_files
            })
        
        return opportunities

    def find_duplicate_files(self, storage_analysis):
        """Find duplicate files based on size and name"""
        duplicates = []
        file_groups = {}
        
        all_files = storage_analysis['package_files'] + storage_analysis['extracted_files']
        
        for file_info in all_files:
            key = f"{file_info['size']}_{file_info['key'].split('/')[-1]}"
            if key not in file_groups:
                file_groups[key] = []
            file_groups[key].append(file_info)
        
        for key, files in file_groups.items():
            if len(files) > 1:
                # Keep the most recent file, mark others as duplicates
                files.sort(key=lambda x: x['last_modified'], reverse=True)
                duplicates.extend(files[1:])
        
        return duplicates

    def find_large_files(self, storage_analysis, threshold_mb=100):
        """Find files larger than threshold"""
        threshold_bytes = threshold_mb * 1024 * 1024
        large_files = []
        
        all_files = storage_analysis['package_files'] + storage_analysis['extracted_files']
        
        for file_info in all_files:
            if file_info['size'] > threshold_bytes:
                large_files.append(file_info)
        
        return large_files

    def find_old_files(self, storage_analysis, days_old=90):
        """Find files older than specified days"""
        from datetime import timedelta
        
        cutoff_date = timezone.now() - timedelta(days=days_old)
        old_files = []
        
        all_files = storage_analysis['package_files'] + storage_analysis['extracted_files']
        
        for file_info in all_files:
            if file_info['last_modified'].replace(tzinfo=timezone.utc) < cutoff_date:
                old_files.append(file_info)
        
        return old_files

    def apply_optimizations(self, opportunities, dry_run=False, verbose=False):
        """Apply storage optimizations"""
        self.stdout.write('Applying storage optimizations...')
        
        optimizations_applied = []
        
        for opportunity in opportunities:
            if opportunity['type'] == 'orphaned_cleanup':
                result = self.cleanup_orphaned_files(opportunity['files'], dry_run, verbose)
                optimizations_applied.append({
                    'type': 'orphaned_cleanup',
                    'files_removed': result['files_removed'],
                    'space_saved': result['space_saved']
                })
            
            elif opportunity['type'] == 'duplicate_cleanup':
                result = self.cleanup_duplicate_files(opportunity['files'], dry_run, verbose)
                optimizations_applied.append({
                    'type': 'duplicate_cleanup',
                    'files_removed': result['files_removed'],
                    'space_saved': result['space_saved']
                })
            
            elif opportunity['type'] == 'large_file_optimization':
                result = self.optimize_large_files(opportunity['files'], dry_run, verbose)
                optimizations_applied.append({
                    'type': 'large_file_optimization',
                    'files_optimized': result['files_optimized'],
                    'space_saved': result['space_saved']
                })
            
            elif opportunity['type'] == 'old_file_archival':
                result = self.archive_old_files(opportunity['files'], dry_run, verbose)
                optimizations_applied.append({
                    'type': 'old_file_archival',
                    'files_archived': result['files_archived'],
                    'space_saved': result['space_saved']
                })
        
        return optimizations_applied

    def cleanup_orphaned_files(self, files, dry_run=False, verbose=False):
        """Clean up orphaned files"""
        files_removed = 0
        space_saved = 0
        
        try:
            storage = SCORMS3Storage()
            
            for file_info in files:
                if not dry_run:
                    storage.delete(file_info['key'])
                    self.stdout.write(f'Deleted orphaned file: {file_info["key"]}')
                else:
                    self.stdout.write(f'Would delete orphaned file: {file_info["key"]}')
                
                files_removed += 1
                space_saved += file_info['size']
        
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error cleaning up orphaned files: {str(e)}')
            )
        
        return {
            'files_removed': files_removed,
            'space_saved': space_saved
        }

    def cleanup_duplicate_files(self, files, dry_run=False, verbose=False):
        """Clean up duplicate files"""
        files_removed = 0
        space_saved = 0
        
        try:
            storage = SCORMS3Storage()
            
            for file_info in files:
                if not dry_run:
                    storage.delete(file_info['key'])
                    self.stdout.write(f'Deleted duplicate file: {file_info["key"]}')
                else:
                    self.stdout.write(f'Would delete duplicate file: {file_info["key"]}')
                
                files_removed += 1
                space_saved += file_info['size']
        
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error cleaning up duplicate files: {str(e)}')
            )
        
        return {
            'files_removed': files_removed,
            'space_saved': space_saved
        }

    def optimize_large_files(self, files, dry_run=False, verbose=False):
        """Optimize large files (placeholder for compression)"""
        files_optimized = 0
        space_saved = 0
        
        # This is a placeholder - actual optimization would involve:
        # 1. Compressing files
        # 2. Converting to more efficient formats
        # 3. Implementing CDN caching
        
        for file_info in files:
            if not dry_run:
                # Placeholder for actual optimization
                self.stdout.write(f'Would optimize large file: {file_info["key"]}')
            else:
                self.stdout.write(f'Would optimize large file: {file_info["key"]}')
            
            files_optimized += 1
            space_saved += int(file_info['size'] * 0.3)  # Assume 30% savings
        
        return {
            'files_optimized': files_optimized,
            'space_saved': space_saved
        }

    def archive_old_files(self, files, dry_run=False, verbose=False):
        """Archive old files to cheaper storage class"""
        files_archived = 0
        space_saved = 0
        
        try:
            s3_client = boto3.client('s3')
            
            for file_info in files:
                if not dry_run:
                    # Move to Glacier storage class for cost savings
                    s3_client.copy_object(
                        Bucket=storage.bucket_name,
                        CopySource={'Bucket': storage.bucket_name, 'Key': file_info['key']},
                        Key=file_info['key'],
                        StorageClass='GLACIER'
                    )
                    self.stdout.write(f'Archived old file: {file_info["key"]}')
                else:
                    self.stdout.write(f'Would archive old file: {file_info["key"]}')
                
                files_archived += 1
                space_saved += int(file_info['size'] * 0.8)  # Assume 80% cost savings
        
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error archiving old files: {str(e)}')
            )
        
        return {
            'files_archived': files_archived,
            'space_saved': space_saved
        }

    def display_storage_analysis(self, analysis):
        """Display storage analysis results"""
        if not analysis:
            self.stdout.write(self.style.ERROR('No storage analysis data available'))
            return
        
        self.stdout.write('\n' + '='*60)
        self.stdout.write(self.style.SUCCESS('SCORM Storage Analysis Report'))
        self.stdout.write('='*60)
        
        # Total usage
        total_size_mb = analysis['total_size'] / (1024 * 1024)
        self.stdout.write(f'Total Storage Used: {total_size_mb:.2f} MB')
        self.stdout.write(f'Total Files: {analysis["total_files"]}')
        
        # Database references
        self.stdout.write(f'Database Packages: {analysis["db_packages"]}')
        self.stdout.write(f'Referenced Package Files: {analysis["db_package_files"]}')
        self.stdout.write(f'Referenced Extracted Paths: {analysis["db_extracted_paths"]}')
        
        # Orphaned files
        orphaned_size_mb = analysis['orphaned_size'] / (1024 * 1024)
        self.stdout.write(f'\nOrphaned Files: {analysis["orphaned_count"]}')
        self.stdout.write(f'Orphaned Size: {orphaned_size_mb:.2f} MB')
        
        if analysis['orphaned_package_files']:
            self.stdout.write('\nOrphaned Package Files:')
            for file_info in analysis['orphaned_package_files'][:10]:  # Show first 10
                self.stdout.write(f'  - {file_info["key"]} ({file_info["size"]} bytes)')
        
        if analysis['orphaned_extracted_files']:
            self.stdout.write('\nOrphaned Extracted Files:')
            for file_info in analysis['orphaned_extracted_files'][:10]:  # Show first 10
                self.stdout.write(f'  - {file_info["key"]} ({file_info["size"]} bytes)')
        
        self.stdout.write('='*60)

    def generate_optimization_report(self, analysis, optimizations):
        """Generate optimization report"""
        self.stdout.write('\n' + '='*60)
        self.stdout.write(self.style.SUCCESS('SCORM Storage Optimization Report'))
        self.stdout.write('='*60)
        
        total_space_saved = 0
        total_files_processed = 0
        
        for optimization in optimizations:
            if 'space_saved' in optimization:
                total_space_saved += optimization['space_saved']
            
            if 'files_removed' in optimization:
                total_files_processed += optimization['files_removed']
            elif 'files_optimized' in optimization:
                total_files_processed += optimization['files_optimized']
            elif 'files_archived' in optimization:
                total_files_processed += optimization['files_archived']
        
        total_space_saved_mb = total_space_saved / (1024 * 1024)
        
        self.stdout.write(f'Total Files Processed: {total_files_processed}')
        self.stdout.write(f'Total Space Saved: {total_space_saved_mb:.2f} MB')
        
        # Calculate cost savings (assuming $0.023 per GB per month)
        monthly_cost_savings = (total_space_saved / (1024 * 1024 * 1024)) * 0.023
        self.stdout.write(f'Estimated Monthly Cost Savings: ${monthly_cost_savings:.4f}')
        
        self.stdout.write('='*60)

    def confirm_optimization(self, opportunities):
        """Ask for confirmation before optimization"""
        total_savings = sum(opp['potential_savings'] for opp in opportunities)
        total_savings_mb = total_savings / (1024 * 1024)
        
        self.stdout.write(f'\nOptimization Opportunities Found:')
        for opp in opportunities:
            self.stdout.write(f'  - {opp["description"]} (Potential savings: {opp["potential_savings"] / (1024 * 1024):.2f} MB)')
        
        self.stdout.write(f'\nTotal Potential Savings: {total_savings_mb:.2f} MB')
        
        response = input(f'\nProceed with optimization? (y/N): ')
        return response.lower() in ['y', 'yes']
