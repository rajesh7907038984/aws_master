"""
Intelligent SCORM Launch URL Auto-Detection System
Automatically detects the correct launch URL for different SCORM package types
"""

import boto3
import logging
from django.conf import settings
from core.env_loader import get_env

logger = logging.getLogger(__name__)

class ScormLaunchDetector:
    """
    Intelligent system to auto-detect correct launch URLs for different SCORM package types
    """
    
    def __init__(self):
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=get_env('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=get_env('AWS_SECRET_ACCESS_KEY'),
            region_name=get_env('AWS_S3_REGION_NAME', 'eu-west-2')
        )
        self.bucket_name = get_env('AWS_STORAGE_BUCKET_NAME', 'lms-staging-nexsy-io')
        
        # Package type detection patterns
        self.package_patterns = {
            'articulate_storyline': {
                'indicators': ['story.html', 'story_content/', 'mobile/', 'html5/'],
                'launch_files': ['story.html', 'index_lms.html', 'index.html'],
                'priority': 1
            },
            'articulate_rise': {
                'indicators': ['index_lms.html', 'lms/', 'scormdriver/'],
                'launch_files': ['index_lms.html', 'index.html'],
                'priority': 2
            },
            'captivate': {
                'indicators': ['index.html', 'scormcontent/', 'data/'],
                'launch_files': ['index.html', 'scormcontent/index.html'],
                'priority': 3
            },
            'lectora': {
                'indicators': ['index.html', 'content/', 'assets/'],
                'launch_files': ['index.html'],
                'priority': 4
            },
            'generic_scorm': {
                'indicators': ['imsmanifest.xml', 'index.html'],
                'launch_files': ['index.html', 'launch.html', 'start.html'],
                'priority': 5
            },
            'xapi_tincan': {
                'indicators': ['tincan.xml', 'xapi/', 'data/'],
                'launch_files': ['index.html', 'launch.html'],
                'priority': 6
            }
        }
    
    def detect_package_type(self, files):
        """
        Detect SCORM package type based on file structure
        """
        if not files:
            return 'unknown', []
        
        # Convert to lowercase for case-insensitive matching
        files_lower = [f.lower() for f in files]
        
        package_scores = {}
        
        for package_type, config in self.package_patterns.items():
            score = 0
            matched_indicators = []
            
            # Check for indicators
            for indicator in config['indicators']:
                if any(indicator.lower() in f for f in files_lower):
                    score += 1
                    matched_indicators.append(indicator)
            
            # Apply priority weighting
            score *= config['priority']
            package_scores[package_type] = {
                'score': score,
                'indicators': matched_indicators,
                'launch_files': config['launch_files']
            }
        
        # Find the best match
        best_match = max(package_scores.items(), key=lambda x: x[1]['score'])
        
        if best_match[1]['score'] > 0:
            logger.info(f"Detected package type: {best_match[0]} (score: {best_match[1]['score']})")
            return best_match[0], best_match[1]['launch_files']
        else:
            logger.warning("Could not detect package type, using generic fallback")
            return 'generic_scorm', ['index.html', 'launch.html', 'start.html']
    
    def find_best_launch_file(self, files, package_type, suggested_launch_files):
        """
        Find the best launch file from available files
        """
        if not files:
            return None
        
        # Priority order: suggested files first, then common patterns
        launch_priorities = suggested_launch_files + [
            'index.html', 'launch.html', 'start.html', 'main.html',
            'scormcontent/index.html', 'content/index.html'
        ]
        
        # Check each priority file
        for launch_file in launch_priorities:
            if launch_file in files:
                logger.info(f"Found launch file: {launch_file}")
                return launch_file
        
        # If no exact match, look for HTML files
        html_files = [f for f in files if f.lower().endswith('.html')]
        if html_files:
            # Prefer files in root directory
            root_html = [f for f in html_files if '/' not in f]
            if root_html:
                logger.info(f"Found root HTML file: {root_html[0]}")
                return root_html[0]
            else:
                logger.info(f"Found HTML file: {html_files[0]}")
                return html_files[0]
        
        logger.warning("No suitable launch file found")
        return None
    
    def auto_detect_launch_url(self, scorm_package):
        """
        Automatically detect and set the correct launch URL for a SCORM package
        """
        try:
            # Get files from S3
            files = self.list_package_files(scorm_package)
            
            if not files:
                logger.error(f"No files found for package {scorm_package.id}")
                return None, "No files found in package"
            
            # Detect package type
            package_type, suggested_launch_files = self.detect_package_type(files)
            
            # Find best launch file
            launch_file = self.find_best_launch_file(files, package_type, suggested_launch_files)
            
            if launch_file:
                # Update the package with the detected launch URL
                old_launch_url = scorm_package.launch_url
                scorm_package.launch_url = launch_file
                scorm_package.save()
                
                logger.info(f"Auto-detected launch URL: {launch_file} (was: {old_launch_url})")
                return launch_file, f"Auto-detected {package_type} launch file"
            else:
                return None, "Could not find suitable launch file"
                
        except Exception as e:
            logger.error(f"Error auto-detecting launch URL: {str(e)}")
            return None, f"Error: {str(e)}"
    
    def list_package_files(self, scorm_package):
        """
        List all files in a SCORM package from S3
        """
        try:
            base_path = f"{scorm_package.extracted_path}/"
            
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=base_path
            )
            
            files = []
            if 'Contents' in response:
                for obj in response['Contents']:
                    # Remove the base path to get relative file path
                    relative_path = obj['Key'].replace(base_path, '')
                    if relative_path:  # Skip empty paths (directories)
                        files.append(relative_path)
            
            return files
            
        except Exception as e:
            logger.error(f"Error listing package files: {str(e)}")
            return []
    
    def fix_all_packages(self):
        """
        Auto-detect and fix launch URLs for all SCORM packages
        """
        from scorm.models import ScormPackage
        
        results = []
        
        for package in ScormPackage.objects.all():
            try:
                launch_file, message = self.auto_detect_launch_url(package)
                results.append({
                    'package_id': package.id,
                    'title': package.title,
                    'launch_file': launch_file,
                    'message': message,
                    'success': launch_file is not None
                })
            except Exception as e:
                results.append({
                    'package_id': package.id,
                    'title': package.title,
                    'launch_file': None,
                    'message': f"Error: {str(e)}",
                    'success': False
                })
        
        return results

# Singleton instance
launch_detector = ScormLaunchDetector()
