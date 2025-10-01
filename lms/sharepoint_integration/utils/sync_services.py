"""
SharePoint Synchronization Services

This module provides services for synchronizing different types of data
between the LMS and SharePoint/Power BI platforms.
"""

import logging
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.db import transaction
from django.core.files.base import ContentFile
from django.db import models

from .sharepoint_api import SharePointAPI, SharePointAPIError
from users.models import CustomUser

logger = logging.getLogger(__name__)
User = get_user_model()


class SharePointSyncService:
    """Base synchronization service for SharePoint integration"""
    
    def __init__(self, integration_config):
        """
        Initialize sync service
        
        Args:
            integration_config: SharePointIntegration model instance
        """
        self.config = integration_config
        self.api = SharePointAPI(integration_config)
        self.sync_status = {
            'success': False,
            'processed': 0,
            'created': 0,
            'updated': 0,
            'errors': 0,
            'error_messages': []
        }
    
    def log_sync_result(self, operation: str, success: bool, message: str = ""):
        """Log synchronization result"""
        status = "SUCCESS" if success else "ERROR"
        logger.info(f"SharePoint Sync [{operation}] - {status}: {message}")
        
        if not success:
            self.sync_status['errors'] += 1
            self.sync_status['error_messages'].append(f"{operation}: {message}")
    
    def update_integration_sync_status(self, success: bool, error_message: str = None):
        """Update integration model with sync status"""
        try:
            self.config.last_sync_datetime = timezone.now()
            self.config.last_sync_status = 'success' if success else 'error'
            if error_message:
                self.config.sync_error_message = error_message[:1000]  # Limit error message length
            else:
                self.config.sync_error_message = None
            self.config.save()
        except Exception as e:
            logger.error(f"Failed to update sync status: {str(e)}")


class UserSyncService(SharePointSyncService):
    """Service for synchronizing user data between LMS and SharePoint"""
    
    def sync_users_to_sharepoint(self) -> Dict:
        """
        Sync LMS users to SharePoint list
        
        Returns:
            Dictionary with sync results
        """
        try:
            logger.info(f"Starting user sync to SharePoint for {self.config.name}")
            
            if not self.config.enable_user_sync:
                return {'success': False, 'message': 'User sync is disabled'}
            
            # Get branch users if branch is specified
            if self.config.branch:
                users = CustomUser.objects.filter(branch=self.config.branch, is_active=True)
            else:
                users = CustomUser.objects.filter(is_active=True)
            
            # Ensure SharePoint list exists
            self._ensure_user_list_exists()
            
            # Get existing SharePoint users for comparison
            existing_sp_users = self._get_sharepoint_users()
            existing_sp_users_dict = {user['fields'].get('UniqueLMSuseridentifier'): user for user in existing_sp_users}
            
            for user in users:
                try:
                    user_data = self._prepare_user_data(user)
                    
                    if str(user.id) in existing_sp_users_dict:
                        # Update existing user
                        sp_user = existing_sp_users_dict[str(user.id)]
                        result = self.api.update_list_item(
                            self.config.user_list_name,
                            sp_user['id'],
                            user_data
                        )
                        if result:
                            self.sync_status['updated'] += 1
                            self.log_sync_result('USER_UPDATE', True, f"Updated user {user.username}")
                        else:
                            self.log_sync_result('USER_UPDATE', False, f"Failed to update user {user.username}")
                    else:
                        # Create new user
                        result = self.api.create_list_item(
                            self.config.user_list_name,
                            user_data
                        )
                        if result:
                            self.sync_status['created'] += 1
                            self.log_sync_result('USER_CREATE', True, f"Created user {user.username}")
                        else:
                            self.log_sync_result('USER_CREATE', False, f"Failed to create user {user.username}")
                    
                    self.sync_status['processed'] += 1
                    
                except Exception as e:
                    self.log_sync_result('USER_SYNC', False, f"Error syncing user {user.username}: {str(e)}")
            
            # Update sync statistics
            self.config.total_synced_users = self.sync_status['processed']
            success = self.sync_status['errors'] == 0
            self.sync_status['success'] = success
            
            error_message = '; '.join(self.sync_status['error_messages']) if self.sync_status['error_messages'] else None
            self.update_integration_sync_status(success, error_message)
            
            logger.info(f"User sync completed: {self.sync_status}")
            return self.sync_status
            
        except Exception as e:
            error_msg = f"User sync failed: {str(e)}"
            logger.error(error_msg)
            self.update_integration_sync_status(False, error_msg)
            return {'success': False, 'message': error_msg}
    
    def sync_users_from_sharepoint(self) -> Dict:
        """
        Sync user data from SharePoint to LMS
        
        Returns:
            Dictionary with sync results
        """
        try:
            logger.info(f"Starting user sync from SharePoint for {self.config.name}")
            
            if not self.config.enable_user_sync:
                return {'success': False, 'message': 'User sync is disabled'}
            
            # Get SharePoint users
            sp_users = self._get_sharepoint_users()
            
            for sp_user in sp_users:
                try:
                    fields = sp_user.get('fields', {})
                    lms_user_id = fields.get('UniqueLMSuseridentifier')
                    email = fields.get('Primaryemailaddress')
                    
                    if not email:
                        continue
                    
                    # Find or create user
                    user = None
                    if lms_user_id:
                        try:
                            user = CustomUser.objects.get(id=lms_user_id)
                        except CustomUser.DoesNotExist:
                            pass
                    
                    if not user:
                        try:
                            user = CustomUser.objects.get(email=email)
                        except CustomUser.DoesNotExist:
                            # Create new user if auto-creation is enabled
                            # (This would need additional configuration)
                            continue
                    
                    # Update user with SharePoint data
                    updated = self._update_user_from_sharepoint_data(user, fields)
                    
                    if updated:
                        self.sync_status['updated'] += 1
                        self.log_sync_result('USER_UPDATE_FROM_SP', True, f"Updated user {user.username} from SharePoint")
                    
                    self.sync_status['processed'] += 1
                    
                except Exception as e:
                    self.log_sync_result('USER_SYNC_FROM_SP', False, f"Error syncing user from SharePoint: {str(e)}")
            
            success = self.sync_status['errors'] == 0
            self.sync_status['success'] = success
            
            error_message = '; '.join(self.sync_status['error_messages']) if self.sync_status['error_messages'] else None
            self.update_integration_sync_status(success, error_message)
            
            logger.info(f"User sync from SharePoint completed: {self.sync_status}")
            return self.sync_status
            
        except Exception as e:
            error_msg = f"User sync from SharePoint failed: {str(e)}"
            logger.error(error_msg)
            self.update_integration_sync_status(False, error_msg)
            return {'success': False, 'message': error_msg}
    
    def _ensure_user_list_exists(self):
        """Ensure the user list exists in SharePoint"""
        try:
            lists = self.api.get_lists()
            user_list_exists = any(lst.get('displayName') == self.config.user_list_name for lst in lists)
            
            if not user_list_exists:
                # Create user list with appropriate columns
                columns = [
                    {
                        "name": "LMSUserID",
                        "text": {}
                    },
                    {
                        "name": "Username",
                        "text": {}
                    },
                    {
                        "name": "Email",
                        "text": {}
                    },
                    {
                        "name": "FirstName",
                        "text": {}
                    },
                    {
                        "name": "LastName",
                        "text": {}
                    },
                    {
                        "name": "Role",
                        "text": {}
                    },
                    {
                        "name": "Branch",
                        "text": {}
                    },
                    {
                        "name": "LastLogin",
                        "dateTime": {}
                    },
                    {
                        "name": "IsActive",
                        "boolean": {}
                    }
                ]
                
                result = self.api.create_list(self.config.user_list_name, columns)
                if result:
                    logger.info(f"Created SharePoint user list: {self.config.user_list_name}")
                else:
                    raise SharePointAPIError(f"Failed to create user list: {self.config.user_list_name}")
        
        except Exception as e:
            logger.error(f"Error ensuring user list exists: {str(e)}")
            raise
    
    def _get_sharepoint_users(self) -> List[Dict]:
        """Get users from SharePoint list"""
        return self.api.get_list_items(self.config.user_list_name)
    
    def _prepare_user_data(self, user) -> Dict:
        """Prepare user data for SharePoint using actual SharePoint column names"""
        data = {
            'Title': f"{user.first_name} {user.last_name}".strip() or user.username,
            'UniqueLMSuseridentifier': str(user.id),
            'Userloginname': user.username,
            'Primaryemailaddress': user.email,
            'Userfirstname': user.first_name or '',
            'Userlastname': user.last_name or '',
            'UserroleinLMS_x002d_Choices': user.role,
            'Branch': user.branch.name if user.branch else ''
        }
        
        # Add LastLogin only if it exists (avoid None/null issues)
        if user.last_login:
            data['LastLogin'] = user.last_login.isoformat()
            
        # Skip IsActive field as it causes SharePoint API errors
        # SharePoint boolean format handling
        
        return data
    
    def _update_user_from_sharepoint_data(self, user, sp_data: Dict) -> bool:
        """Update LMS user with SharePoint data"""
        try:
            updated = False
            
            # Update basic fields if they exist in SharePoint
            if sp_data.get('FirstName') and user.first_name != sp_data['FirstName']:
                user.first_name = sp_data['FirstName']
                updated = True
            
            if sp_data.get('LastName') and user.last_name != sp_data['LastName']:
                user.last_name = sp_data['LastName']
                updated = True
            
            # Add other field mappings as needed
            
            if updated:
                user.save()
            
            return updated
            
        except Exception as e:
            logger.error(f"Error updating user from SharePoint data: {str(e)}")
            return False


class EnrollmentSyncService(SharePointSyncService):
    """Service for synchronizing course enrollments between LMS and SharePoint"""
    
    def sync_enrollments_to_sharepoint(self) -> Dict:
        """Sync course enrollments to SharePoint"""
        try:
            logger.info(f"Starting enrollment sync to SharePoint for {self.config.name}")
            
            if not self.config.enable_enrollment_sync:
                return {'success': False, 'message': 'Enrollment sync is disabled'}
            
            # Import here to avoid circular imports
            from courses.models import CourseEnrollment
            
            # Get enrollments for the branch
            if self.config.branch:
                enrollments = CourseEnrollment.objects.filter(
                    user__branch=self.config.branch
                ).select_related('user', 'course')
            else:
                enrollments = CourseEnrollment.objects.all().select_related('user', 'course')
            
            # Ensure SharePoint list exists
            self._ensure_enrollment_list_exists()
            
            # Get existing SharePoint enrollments
            existing_sp_enrollments = self._get_sharepoint_enrollments()
            existing_sp_enrollments_dict = {
                f"{enr['fields'].get('UserID')}_{enr['fields'].get('CourseID')}": enr 
                for enr in existing_sp_enrollments
            }
            
            for enrollment in enrollments:
                try:
                    enrollment_data = self._prepare_enrollment_data(enrollment)
                    enrollment_key = f"{enrollment.user.id}_{enrollment.course.id}"
                    
                    if enrollment_key in existing_sp_enrollments_dict:
                        # Update existing enrollment
                        sp_enrollment = existing_sp_enrollments_dict[enrollment_key]
                        result = self.api.update_list_item(
                            self.config.enrollment_list_name,
                            sp_enrollment['id'],
                            enrollment_data
                        )
                        if result:
                            self.sync_status['updated'] += 1
                    else:
                        # Create new enrollment
                        result = self.api.create_list_item(
                            self.config.enrollment_list_name,
                            enrollment_data
                        )
                        if result:
                            self.sync_status['created'] += 1
                    
                    self.sync_status['processed'] += 1
                    
                except Exception as e:
                    self.log_sync_result('ENROLLMENT_SYNC', False, f"Error syncing enrollment: {str(e)}")
            
            # Update sync statistics
            self.config.total_synced_enrollments = self.sync_status['processed']
            success = self.sync_status['errors'] == 0
            self.sync_status['success'] = success
            
            error_message = '; '.join(self.sync_status['error_messages']) if self.sync_status['error_messages'] else None
            self.update_integration_sync_status(success, error_message)
            
            logger.info(f"Enrollment sync completed: {self.sync_status}")
            return self.sync_status
            
        except Exception as e:
            error_msg = f"Enrollment sync failed: {str(e)}"
            logger.error(error_msg)
            self.update_integration_sync_status(False, error_msg)
            return {'success': False, 'message': error_msg}
    
    def _ensure_enrollment_list_exists(self):
        """Ensure enrollment list exists in SharePoint"""
        try:
            lists = self.api.get_lists()
            enrollment_list_exists = any(lst.get('displayName') == self.config.enrollment_list_name for lst in lists)
            
            if not enrollment_list_exists:
                columns = [
                    {"name": "LMSUserID", "text": {}},
                    {"name": "LMSCourseID", "text": {}},
                    {"name": "UserEmail", "text": {}},
                    {"name": "CourseTitle", "text": {}},
                    {"name": "EnrollmentDate", "dateTime": {}},
                    {"name": "Status", "text": {}},
                    {"name": "Progress", "number": {}},
                    {"name": "CompletionDate", "dateTime": {}},
                    {"name": "Branch", "text": {}}
                ]
                
                result = self.api.create_list(self.config.enrollment_list_name, columns)
                if result:
                    logger.info(f"Created SharePoint enrollment list: {self.config.enrollment_list_name}")
                else:
                    raise SharePointAPIError(f"Failed to create enrollment list: {self.config.enrollment_list_name}")
        
        except Exception as e:
            logger.error(f"Error ensuring enrollment list exists: {str(e)}")
            raise
    
    def _get_sharepoint_enrollments(self) -> List[Dict]:
        """Get enrollments from SharePoint list"""
        return self.api.get_list_items(self.config.enrollment_list_name)
    
    def _prepare_enrollment_data(self, enrollment) -> Dict:
        """Prepare enrollment data for SharePoint using actual SharePoint column names"""
        return {
            'Title': f"{enrollment.user.username} - {enrollment.course.title}",
            'UserID': str(enrollment.user.id),
            'CourseID': str(enrollment.course.id),
            'UserEmail': enrollment.user.email,
            'CourseTitle': enrollment.course.title,
            'EnrollmentDate': enrollment.enrolled_at.isoformat() if enrollment.enrolled_at else None,
            'Status': 'completed' if enrollment.completed else 'enrolled',
            'ProgressPercentage': enrollment.progress_percentage,
            'CompletionDate': enrollment.completion_date.isoformat() if enrollment.completion_date else None,
            'CourseBranch': enrollment.user.branch.name if enrollment.user.branch else ''
        }


class ProgressSyncService(SharePointSyncService):
    """Service for synchronizing learning progress to SharePoint"""
    
    def sync_progress_to_sharepoint(self) -> Dict:
        """Sync learning progress to SharePoint"""
        try:
            logger.info(f"Starting progress sync to SharePoint for {self.config.name}")
            
            if not self.config.enable_progress_sync:
                return {'success': False, 'message': 'Progress sync is disabled'}
            
            # Import here to avoid circular imports
            from courses.models import TopicProgress
            
            # Get progress records for the branch
            if self.config.branch:
                progress_records = TopicProgress.objects.filter(
                    user__branch=self.config.branch
                ).select_related('user', 'topic')
            else:
                progress_records = TopicProgress.objects.all().select_related('user', 'topic')
            
            # Ensure SharePoint list exists
            self._ensure_progress_list_exists()
            
            for progress in progress_records:
                try:
                    progress_data = self._prepare_progress_data(progress)
                    
                    # Create or update progress record
                    result = self.api.create_list_item(
                        self.config.progress_list_name,
                        progress_data
                    )
                    
                    if result:
                        self.sync_status['created'] += 1
                    
                    self.sync_status['processed'] += 1
                    
                except Exception as e:
                    self.log_sync_result('PROGRESS_SYNC', False, f"Error syncing progress: {str(e)}")
            
            success = self.sync_status['errors'] == 0
            self.sync_status['success'] = success
            
            error_message = '; '.join(self.sync_status['error_messages']) if self.sync_status['error_messages'] else None
            self.update_integration_sync_status(success, error_message)
            
            logger.info(f"Progress sync completed: {self.sync_status}")
            return self.sync_status
            
        except Exception as e:
            error_msg = f"Progress sync failed: {str(e)}"
            logger.error(error_msg)
            self.update_integration_sync_status(False, error_msg)
            return {'success': False, 'message': error_msg}
    
    def _ensure_progress_list_exists(self):
        """Ensure progress list exists in SharePoint"""
        try:
            lists = self.api.get_lists()
            progress_list_exists = any(lst.get('displayName') == self.config.progress_list_name for lst in lists)
            
            if not progress_list_exists:
                columns = [
                    {"name": "LMSUserID", "text": {}},
                    {"name": "LMSTopicID", "text": {}},
                    {"name": "LMSCourseID", "text": {}},
                    {"name": "UserEmail", "text": {}},
                    {"name": "TopicTitle", "text": {}},
                    {"name": "CourseTitle", "text": {}},
                    {"name": "Progress", "number": {}},
                    {"name": "Score", "number": {}},
                    {"name": "TimeSpent", "number": {}},
                    {"name": "Attempts", "number": {}},
                    {"name": "IsCompleted", "boolean": {}},
                    {"name": "LastAccessed", "dateTime": {}},
                    {"name": "CompletedAt", "dateTime": {}},
                    {"name": "Branch", "text": {}}
                ]
                
                result = self.api.create_list(self.config.progress_list_name, columns)
                if result:
                    logger.info(f"Created SharePoint progress list: {self.config.progress_list_name}")
                else:
                    raise SharePointAPIError(f"Failed to create progress list: {self.config.progress_list_name}")
        
        except Exception as e:
            logger.error(f"Error ensuring progress list exists: {str(e)}")
            raise
    
    def _prepare_progress_data(self, progress) -> Dict:
        """Prepare progress data for SharePoint using actual SharePoint column names"""
        # Get course information through topic relationships
        course_id = ''
        course_title = ''
        if hasattr(progress.topic, 'coursetopic_set') and progress.topic.coursetopic_set.exists():
            course_topic = progress.topic.coursetopic_set.first()
            if course_topic and course_topic.course:
                course_id = str(course_topic.course.id)
                course_title = course_topic.course.title
        
        data = {
            'Title': f"{progress.user.username} - {progress.topic.title}",
            'LMSProgressID': str(progress.id),
            'UserID': str(progress.user.id),
            'UserEmail': progress.user.email,
            'CourseID': course_id,
            'CourseName': course_title,
            'TopicID': str(progress.topic.id),
            'TopicName': progress.topic.title,
            'TopicType': getattr(progress.topic, 'topic_type', 'content'),
            'ProgressPercent': getattr(progress, 'progress_percentage', 0),
            'TimeSpent': getattr(progress, 'time_spent', 0),
            'Attempts': getattr(progress, 'attempts', 0),
            'Score': getattr(progress, 'score', 0),
            'MaxScore': getattr(progress, 'max_score', 0),
            'IsCompleted': bool(getattr(progress, 'completed', False))
        }
        
        # Add optional datetime fields only if they exist (to avoid null/format issues)
        if hasattr(progress, 'completed_at') and progress.completed_at:
            data['CompletionDate'] = progress.completed_at.isoformat()
            
        if hasattr(progress, 'updated_at') and progress.updated_at:
            data['UpdatedDate'] = progress.updated_at.isoformat()
            
        # Skip LastAccessed field as it causes SharePoint API errors
        # SharePoint datetime format handling for LastAccessed field
        
        return data


class CertificateSyncService(SharePointSyncService):
    """Service for synchronizing completion certificates to SharePoint libraries"""
    
    def sync_certificates_to_sharepoint(self) -> Dict:
        """Sync completion certificates to SharePoint document library"""
        try:
            logger.info(f"Starting certificate sync to SharePoint for {self.config.name}")
            
            if not self.config.enable_certificate_sync:
                return {'success': False, 'message': 'Certificate sync is disabled'}
            
            # Import here to avoid circular imports
            from certificates.models import IssuedCertificate
            
            # Get certificates for the branch
            if self.config.branch:
                certificates = IssuedCertificate.objects.filter(
                    recipient__branch=self.config.branch
                ).select_related('recipient')
            else:
                certificates = IssuedCertificate.objects.all().select_related('recipient')
            
            for certificate in certificates:
                try:
                    # Generate or get certificate file content
                    cert_content = self._get_certificate_content(certificate)
                    if not cert_content:
                        continue
                    
                    # Upload to SharePoint
                    file_name = f"certificate_{certificate.recipient.username}_{certificate.id}.pdf"
                    folder_path = f"{certificate.recipient.branch.name if certificate.recipient.branch else 'General'}/{datetime.now().year}"
                    
                    result = self.api.upload_file(
                        self.config.certificate_library_name,
                        file_name,
                        cert_content,
                        folder_path
                    )
                    
                    if result:
                        self.sync_status['created'] += 1
                        self.log_sync_result('CERTIFICATE_SYNC', True, f"Uploaded certificate for {certificate.recipient.username}")
                    
                    self.sync_status['processed'] += 1
                    
                except Exception as e:
                    self.log_sync_result('CERTIFICATE_SYNC', False, f"Error syncing certificate: {str(e)}")
            
            success = self.sync_status['errors'] == 0
            self.sync_status['success'] = success
            
            error_message = '; '.join(self.sync_status['error_messages']) if self.sync_status['error_messages'] else None
            self.update_integration_sync_status(success, error_message)
            
            logger.info(f"Certificate sync completed: {self.sync_status}")
            return self.sync_status
            
        except Exception as e:
            error_msg = f"Certificate sync failed: {str(e)}"
            logger.error(error_msg)
            self.update_integration_sync_status(False, error_msg)
            return {'success': False, 'message': error_msg}
    
    def _get_certificate_content(self, certificate) -> Optional[bytes]:
        """Get certificate file content"""
        try:
            if hasattr(certificate, 'certificate_file') and certificate.certificate_file:
                return certificate.certificate_file.read()
            else:
                # Generate certificate content if needed
                return self._generate_certificate_pdf(certificate)
        except Exception as e:
            logger.error(f"Error getting certificate content: {str(e)}")
            return None
    
    def _generate_certificate_pdf(self, certificate) -> Optional[bytes]:
        """Generate certificate PDF content"""
        # This would integrate with your certificate generation system
        # Return default value
        try:
            from reportlab.pdfgen import canvas
            from reportlab.lib.pagesizes import letter
            from io import BytesIO
            
            buffer = BytesIO()
            p = canvas.Canvas(buffer, pagesize=letter)
            
            # Simple certificate layout
            p.drawString(100, 750, f"Certificate of Completion")
            p.drawString(100, 700, f"This certifies that {certificate.user.get_full_name()}")
            p.drawString(100, 650, f"has successfully completed the course")
            p.drawString(100, 600, f"Date: {certificate.created_at.strftime('%B %d, %Y')}")
            
            p.showPage()
            p.save()
            
            buffer.seek(0)
            return buffer.read()
            
        except Exception as e:
            logger.error(f"Error generating certificate PDF: {str(e)}")
            return None


class ReportsSyncService(SharePointSyncService):
    """Service for synchronizing LMS analytics to Power BI via SharePoint"""
    
    def sync_reports_to_powerbi(self) -> Dict:
        """Sync LMS analytics data to Power BI via SharePoint"""
        try:
            logger.info(f"Starting reports sync to Power BI for {self.config.name}")
            
            if not self.config.enable_reports_sync:
                return {'success': False, 'message': 'Reports sync is disabled'}
            
            # Generate analytics data
            analytics_data = self._generate_analytics_data()
            
            # Upload to SharePoint as JSON for Power BI consumption
            file_name = f"lms_analytics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            file_content = json.dumps(analytics_data, indent=2, default=str).encode('utf-8')
            
            result = self.api.upload_file(
                self.config.reports_library_name,
                file_name,
                file_content,
                "Analytics"
            )
            
            if result:
                self.sync_status['created'] += 1
                self.log_sync_result('REPORTS_SYNC', True, f"Uploaded analytics data: {file_name}")
            
            self.sync_status['processed'] += 1
            
            success = self.sync_status['errors'] == 0
            self.sync_status['success'] = success
            
            error_message = '; '.join(self.sync_status['error_messages']) if self.sync_status['error_messages'] else None
            self.update_integration_sync_status(success, error_message)
            
            logger.info(f"Reports sync completed: {self.sync_status}")
            return self.sync_status
            
        except Exception as e:
            error_msg = f"Reports sync failed: {str(e)}"
            logger.error(error_msg)
            self.update_integration_sync_status(False, error_msg)
            return {'success': False, 'message': error_msg}
    
    def _generate_analytics_data(self) -> Dict:
        """Generate analytics data for Power BI"""
        try:
            # Import here to avoid circular imports
            from courses.models import Course, CourseEnrollment
            from assignments.models import AssignmentSubmission
            from quiz.models import QuizAttempt
            
            analytics = {
                'timestamp': timezone.now().isoformat(),
                'branch': self.config.branch.name if self.config.branch else 'All',
                'users': self._get_user_analytics(),
                'courses': self._get_course_analytics(),
                'enrollments': self._get_enrollment_analytics(),
                'assignments': self._get_assignment_analytics(),
                'quizzes': self._get_quiz_analytics(),
                'activity': self._get_activity_analytics()
            }
            
            return analytics
            
        except Exception as e:
            logger.error(f"Error generating analytics data: {str(e)}")
            return {}
    
    def _get_user_analytics(self) -> Dict:
        """Get user analytics data"""
        if self.config.branch:
            users = CustomUser.objects.filter(branch=self.config.branch)
        else:
            users = CustomUser.objects.all()
        
        return {
            'total_users': users.count(),
            'active_users': users.filter(is_active=True).count(),
            'by_role': {
                'learners': users.filter(role='learner').count(),
                'instructors': users.filter(role='instructor').count(),
                'admins': users.filter(role='admin').count()
            },
            'recent_logins': users.filter(last_login__gte=timezone.now() - timedelta(days=30)).count()
        }
    
    def _get_course_analytics(self) -> Dict:
        """Get course analytics data"""
        from courses.models import Course
        
        if self.config.branch:
            courses = Course.objects.filter(branch=self.config.branch)
        else:
            courses = Course.objects.all()
        
        return {
            'total_courses': courses.count(),
            'active_courses': courses.filter(status='active').count(),
            'draft_courses': courses.filter(status='draft').count()
        }
    
    def _get_enrollment_analytics(self) -> Dict:
        """Get enrollment analytics data"""
        from courses.models import CourseEnrollment
        
        if self.config.branch:
            enrollments = CourseEnrollment.objects.filter(user__branch=self.config.branch)
        else:
            enrollments = CourseEnrollment.objects.all()
        
        return {
            'total_enrollments': enrollments.count(),
                            'recent_enrollments': enrollments.filter(enrolled_at__gte=timezone.now() - timedelta(days=30)).count()
        }
    
    def _get_assignment_analytics(self) -> Dict:
        """Get assignment analytics data"""
        from assignments.models import AssignmentSubmission
        
        if self.config.branch:
            submissions = AssignmentSubmission.objects.filter(user__branch=self.config.branch)
        else:
            submissions = AssignmentSubmission.objects.all()
        
        return {
            'total_submissions': submissions.count(),
            'graded_submissions': submissions.filter(status='graded').count(),
            'pending_submissions': submissions.filter(status='submitted').count()
        }
    
    def _get_quiz_analytics(self) -> Dict:
        """Get quiz analytics data"""
        from quiz.models import QuizAttempt
        
        if self.config.branch:
            attempts = QuizAttempt.objects.filter(user__branch=self.config.branch)
        else:
            attempts = QuizAttempt.objects.all()
        
        return {
            'total_attempts': attempts.count(),
            'completed_attempts': attempts.filter(is_completed=True).count(),
            'average_score': attempts.filter(is_completed=True).aggregate(
                avg_score=models.Avg('score')
            )['avg_score'] or 0
        }
    
    def _get_activity_analytics(self) -> Dict:
        """Get activity analytics data"""
        return {
            'last_24_hours': {
                'logins': CustomUser.objects.filter(
                    last_login__gte=timezone.now() - timedelta(hours=24)
                ).count(),
                'submissions': self._get_recent_submissions_count(24),
                'quiz_attempts': self._get_recent_quiz_attempts_count(24)
            },
            'last_7_days': {
                'logins': CustomUser.objects.filter(
                    last_login__gte=timezone.now() - timedelta(days=7)
                ).count(),
                'submissions': self._get_recent_submissions_count(7 * 24),
                'quiz_attempts': self._get_recent_quiz_attempts_count(7 * 24)
            }
        }
    
    def _get_recent_submissions_count(self, hours: int) -> int:
        """Get recent submissions count"""
        try:
            from assignments.models import AssignmentSubmission
            
            if self.config.branch:
                return AssignmentSubmission.objects.filter(
                    user__branch=self.config.branch,
                    submitted_at__gte=timezone.now() - timedelta(hours=hours)
                ).count()
            else:
                return AssignmentSubmission.objects.filter(
                    submitted_at__gte=timezone.now() - timedelta(hours=hours)
                ).count()
        except:
            return 0
    
    def _get_recent_quiz_attempts_count(self, hours: int) -> int:
        """Get recent quiz attempts count"""
        try:
            from quiz.models import QuizAttempt
            
            if self.config.branch:
                return QuizAttempt.objects.filter(
                    user__branch=self.config.branch,
                    start_time__gte=timezone.now() - timedelta(hours=hours)
                ).count()
            else:
                return QuizAttempt.objects.filter(
                    start_time__gte=timezone.now() - timedelta(hours=hours)
                ).count()
        except:
            return 0 

    def sync_single_enrollment_to_sharepoint(self, enrollment) -> bool:
        """Sync a single enrollment to SharePoint"""
        try:
            # Prepare enrollment data
            enrollment_data = {
                'LMSEnrollmentID': str(enrollment.id),
                'UserEmail': enrollment.user.email,
                'UserID': str(enrollment.user.id),
                'CourseID': str(enrollment.course.id),
                'CourseTitle': enrollment.course.title,
                'CourseBranch': enrollment.course.branch.name if enrollment.course.branch else '',
                'EnrollmentDate': enrollment.enrollment_date.isoformat() if hasattr(enrollment, 'enrollment_date') else timezone.now().isoformat(),
                'Status': getattr(enrollment, 'status', 'enrolled'),
                'ProgressPercentage': getattr(enrollment, 'progress_percentage', 0),
                'UpdatedDate': timezone.now().isoformat()
            }
            
            # Create or update in SharePoint
            result = self.api.create_list_item(self.config.enrollment_list_name, enrollment_data)
            return result is not None
            
        except Exception as e:
            logger.error(f"Error syncing single enrollment to SharePoint: {str(e)}")
            return False

    def mark_enrollment_withdrawn_in_sharepoint(self, enrollment) -> bool:
        """Mark enrollment as withdrawn in SharePoint"""
        try:
            # Update enrollment status to withdrawn in SharePoint
            enrollment_data = {
                'Status': 'withdrawn',
                'UpdatedDate': timezone.now().isoformat()
            }
            
            # You would need to implement finding the enrollment by LMS ID first
            # This is a simplified version
            result = self.api.create_list_item(self.config.enrollment_list_name, {
                'LMSEnrollmentID': str(enrollment.id),
                'UserEmail': enrollment.user.email,
                'Status': 'withdrawn',
                'UpdatedDate': timezone.now().isoformat()
            })
            return result is not None
            
        except Exception as e:
            logger.error(f"Error marking enrollment as withdrawn in SharePoint: {str(e)}")
            return False


class SharePointBidirectionalSync:
    """
    Comprehensive bidirectional sync service between LMS and SharePoint
    Handles automatic data synchronization in both directions
    """
    
    def __init__(self, integration_config):
        """Initialize the bidirectional sync service"""
        self.config = integration_config
        self.api = SharePointAPI(integration_config)
        self.logger = logging.getLogger(__name__)
    
    def sync_lms_user_to_sharepoint(self, user) -> bool:
        """Sync a single LMS user to SharePoint"""
        try:
            # Prepare user data for SharePoint
            user_data = {
                'LMSUserID': str(user.id),
                'Username': user.username,
                'Email': user.email,
                'FirstName': user.first_name,
                'LastName': user.last_name,
                'Role': user.role,
                'Branch': user.branch.name if user.branch else '',
                'DateOfBirth': user.date_of_birth.isoformat() if user.date_of_birth else '',
                'Gender': user.sex if hasattr(user, 'sex') else '',
                'Phone': user.phone_number or '',
                'StudyArea': user.study_area or '',
                'JobRole': user.job_role or '',
                'Industry': user.industry or '',
                'LastLogin': user.last_login.isoformat() if user.last_login else '',
                'IsActive': user.is_active,
                'CreatedDate': user.date_joined.isoformat(),
                'UpdatedDate': timezone.now().isoformat()
            }
            
            # Create or update in SharePoint
            result = self.api.create_list_item(self.config.user_list_name, user_data)
            return result is not None
            
        except Exception as e:
            logger.error(f"Error syncing user to SharePoint: {str(e)}")
            return False

    def mark_user_inactive_in_sharepoint(self, user_email: str) -> bool:
        """Mark user as inactive in SharePoint"""
        try:
            # Update user status to inactive in SharePoint
            user_data = {
                'IsActive': False,
                'UpdatedDate': timezone.now().isoformat()
            }
            
            # Note: In a real implementation, you'd find the user by email first
            # and then update the specific item
            result = self.api.create_list_item(self.config.user_list_name, {
                'Email': user_email,
                'IsActive': False,
                'UpdatedDate': timezone.now().isoformat()
            })
            return result is not None
            
        except Exception as e:
            logger.error(f"Error marking user inactive in SharePoint: {str(e)}")
            return False

    def sync_course_to_sharepoint(self, course) -> bool:
        """Sync a course to SharePoint"""
        try:
            course_data = {
                'LMSCourseID': str(course.id),
                'CourseTitle': course.title,
                'CourseDescription': course.description or '',
                'Branch': course.branch.name if course.branch else '',
                'Language': course.language or 'en',
                'Status': course.status if hasattr(course, 'status') else 'active',
                'IsVisible': course.is_visible if hasattr(course, 'is_visible') else True,
                'CreatedDate': course.created_at.isoformat() if hasattr(course, 'created_at') else timezone.now().isoformat(),
                'UpdatedDate': timezone.now().isoformat()
            }
            
            result = self.api.create_list_item("LMS Course Groups", course_data)
            return result is not None
            
        except Exception as e:
            logger.error(f"Error syncing course to SharePoint: {str(e)}")
            return False

    def sync_topic_progress_to_sharepoint(self, progress) -> bool:
        """Sync topic progress to SharePoint"""
        try:
            progress_data = {
                'LMSProgressID': str(progress.id),
                'UserEmail': progress.user.email,
                'UserID': str(progress.user.id),
                'CourseID': str(progress.topic.course.id) if hasattr(progress.topic, 'course') else '',
                'TopicID': str(progress.topic.id) if hasattr(progress, 'topic') else '',
                'TopicName': progress.topic.title if hasattr(progress.topic, 'title') else '',
                'ProgressPercent': progress.progress_percentage if hasattr(progress, 'progress_percentage') else 0,
                'CompletionDate': progress.completed_at.isoformat() if hasattr(progress, 'completed_at') and progress.completed_at else '',
                'TimeSpent': progress.time_spent if hasattr(progress, 'time_spent') else 0,
                'Score': progress.score if hasattr(progress, 'score') else 0,
                'IsCompleted': progress.is_completed if hasattr(progress, 'is_completed') else False,
                'UpdatedDate': timezone.now().isoformat()
            }
            
            result = self.api.create_list_item(self.config.progress_list_name, progress_data)
            return result is not None
            
        except Exception as e:
            logger.error(f"Error syncing topic progress to SharePoint: {str(e)}")
            return False

    def sync_assignment_submission_to_sharepoint(self, submission) -> bool:
        """Sync assignment submission to SharePoint"""
        try:
            submission_data = {
                'LMSAssessmentID': f"assignment_{submission.id}",
                'UserEmail': submission.user.email,
                'UserID': str(submission.user.id),
                'CourseID': str(submission.assignment.course.id) if hasattr(submission.assignment, 'course') else '',
                'AssignmentID': str(submission.assignment.id),
                'AssignmentTitle': submission.assignment.title,
                'Score': submission.score if hasattr(submission, 'score') else 0,
                'Grade': submission.grade if hasattr(submission, 'grade') else '',
                'SubmissionDate': submission.submitted_at.isoformat() if hasattr(submission, 'submitted_at') else timezone.now().isoformat(),
                'UpdatedDate': timezone.now().isoformat()
            }
            
            result = self.api.create_list_item("LMS Assessment Results", submission_data)
            return result is not None
            
        except Exception as e:
            logger.error(f"Error syncing assignment submission to SharePoint: {str(e)}")
            return False

    def sync_grade_to_sharepoint(self, grade) -> bool:
        """Sync grade to SharePoint"""
        try:
            grade_data = {
                'LMSAssessmentID': f"grade_{grade.id}",
                'UserEmail': grade.student.email,
                'UserID': str(grade.student.id),
                'CourseID': str(grade.course.id) if hasattr(grade, 'course') else '',
                'AssignmentID': str(grade.assignment.id) if hasattr(grade, 'assignment') else '',
                'Score': float(grade.score) if grade.score else 0,
                'Grade': str(grade.grade) if hasattr(grade, 'grade') else '',
                'Feedback': grade.feedback if hasattr(grade, 'feedback') else '',
                'GradedDate': grade.updated_at.isoformat() if hasattr(grade, 'updated_at') else timezone.now().isoformat(),
                'UpdatedDate': timezone.now().isoformat()
            }
            
            result = self.api.create_list_item("LMS Assessment Results", grade_data)
            return result is not None
            
        except Exception as e:
            logger.error(f"Error syncing grade to SharePoint: {str(e)}")
            return False

    def sync_quiz_attempt_to_sharepoint(self, attempt) -> bool:
        """Sync quiz attempt to SharePoint"""
        try:
            attempt_data = {
                'LMSAssessmentID': f"quiz_{attempt.id}",
                'UserEmail': attempt.user.email,
                'UserID': str(attempt.user.id),
                'QuizID': str(attempt.quiz.id),
                'QuizTitle': attempt.quiz.title if hasattr(attempt.quiz, 'title') else '',
                'Score': attempt.score if hasattr(attempt, 'score') else 0,
                'MaxScore': attempt.quiz.total_marks if hasattr(attempt.quiz, 'total_marks') else 0,
                'Percentage': attempt.percentage if hasattr(attempt, 'percentage') else 0,
                'IsPassed': attempt.passed if hasattr(attempt, 'passed') else False,
                'TimeSpent': attempt.time_spent if hasattr(attempt, 'time_spent') else 0,
                'SubmissionDate': attempt.end_time.isoformat() if hasattr(attempt, 'end_time') and attempt.end_time else timezone.now().isoformat(),
                'UpdatedDate': timezone.now().isoformat()
            }
            
            result = self.api.create_list_item("LMS Assessment Results", attempt_data)
            return result is not None
            
        except Exception as e:
            logger.error(f"Error syncing quiz attempt to SharePoint: {str(e)}")
            return False

    def sync_certificate_to_sharepoint(self, certificate) -> bool:
        """Sync certificate to SharePoint"""
        try:
            certificate_data = {
                'LMSCertificateID': str(certificate.id),
                'StudentName': certificate.user.get_full_name() if hasattr(certificate.user, 'get_full_name') else f"{certificate.user.first_name} {certificate.user.last_name}",
                'StudentEmail': certificate.user.email,
                'StudentID': str(certificate.user.id),
                'CourseID': str(certificate.course.id) if hasattr(certificate, 'course') else '',
                'CourseName': certificate.course.title if hasattr(certificate, 'course') else '',
                'Branch': certificate.user.branch.name if certificate.user.branch else '',
                'CertificateNumber': certificate.certificate_number if hasattr(certificate, 'certificate_number') else '',
                'IssueDate': certificate.issued_at.isoformat() if hasattr(certificate, 'issued_at') else timezone.now().isoformat(),
                'Status': 'issued',
                'UpdatedDate': timezone.now().isoformat()
            }
            
            result = self.api.create_list_item("LMS Certificate Registry", certificate_data)
            return result is not None
            
        except Exception as e:
            logger.error(f"Error syncing certificate to SharePoint: {str(e)}")
            return False

    def sync_group_to_sharepoint(self, group) -> bool:
        """Sync group to SharePoint"""
        try:
            group_data = {
                'LMSGroupID': str(group.id),
                'GroupName': group.name,
                'GroupDescription': group.description if hasattr(group, 'description') else '',
                'Branch': group.branch.name if group.branch else '',
                'GroupType': 'branch_group',
                'IsActive': group.is_active if hasattr(group, 'is_active') else True,
                'CreatedDate': group.created_at.isoformat() if hasattr(group, 'created_at') else timezone.now().isoformat(),
                'UpdatedDate': timezone.now().isoformat()
            }
            
            result = self.api.create_list_item("LMS User Groups", group_data)
            return result is not None
            
        except Exception as e:
            logger.error(f"Error syncing group to SharePoint: {str(e)}")
            return False

    def sync_group_membership_to_sharepoint(self, membership) -> bool:
        """Sync group membership to SharePoint"""
        try:
            # This could be stored as part of user data or as a separate relationship table
            # For now, we'll update the user's group information
            user_data = {
                'UserEmail': membership.user.email,
                'GroupMembership': membership.group.name,
                'UpdatedDate': timezone.now().isoformat()
            }
            
            # In a real implementation, you might update the user record
            # or create a separate membership tracking list
            return True  # Placeholder
            
        except Exception as e:
            logger.error(f"Error syncing group membership to SharePoint: {str(e)}")
            return False
    
    def sync_user_from_sharepoint_to_lms(self, sharepoint_user_data: Dict) -> bool:
        """
        Sync a user from SharePoint to LMS (auto-add to branch)
        
        Args:
            sharepoint_user_data: User data from SharePoint list
            
        Returns:
            Boolean indicating success
        """
        try:
            from users.models import CustomUser
            from branches.models import Branch
            
            # Extract user data
            email = sharepoint_user_data.get('Email', '')
            username = sharepoint_user_data.get('Username', email.split('@')[0] if email else '')
            first_name = sharepoint_user_data.get('FirstName', '')
            last_name = sharepoint_user_data.get('LastName', '')
            role = sharepoint_user_data.get('Role', 'learner')
            branch_name = sharepoint_user_data.get('Branch', '')
            
            if not email:
                self.logger.warning("Cannot sync user without email address")
                return False
            
            # Get or create branch
            try:
                branch = Branch.objects.get(name=branch_name) if branch_name else None
                if not branch and branch_name:
                    # Create branch if it doesn't exist
                    from business.models import Business
                    default_business = Business.objects.first()
                    if default_business:
                        branch = Branch.objects.create(
                            name=branch_name,
                            business=default_business,
                            description=f"Auto-created from SharePoint: {branch_name}"
                        )
                        self.logger.info(f"Created new branch: {branch_name}")
            except Branch.DoesNotExist:
                branch = None
            
            # Check if user already exists
            user, created = CustomUser.objects.get_or_create(
                email=email,
                defaults={
                    'username': username,
                    'first_name': first_name,
                    'last_name': last_name,
                    'role': role,
                    'branch': branch,
                    'is_active': sharepoint_user_data.get('IsActive', True),
                    'phone': sharepoint_user_data.get('Phone', ''),
                    'address': sharepoint_user_data.get('Address', ''),
                    'study_area': sharepoint_user_data.get('StudyArea', ''),
                    'qualifications': sharepoint_user_data.get('Qualifications', ''),
                    'job_role': sharepoint_user_data.get('JobRole', ''),
                    'industry': sharepoint_user_data.get('Industry', ''),
                    'skills': sharepoint_user_data.get('Skills', ''),
                    'date_of_birth': self._parse_date(sharepoint_user_data.get('DateOfBirth')),
                    'gender': sharepoint_user_data.get('Gender', ''),
                }
            )
            
            if created:
                self.logger.info(f"Created new user from SharePoint: {email} in branch {branch_name}")
                return True
            else:
                # Update existing user with SharePoint data
                user.first_name = first_name or user.first_name
                user.last_name = last_name or user.last_name
                user.role = role or user.role
                user.branch = branch or user.branch
                user.is_active = sharepoint_user_data.get('IsActive', user.is_active)
                user.phone = sharepoint_user_data.get('Phone', '') or user.phone
                user.address = sharepoint_user_data.get('Address', '') or user.address
                user.save()
                self.logger.info(f"Updated existing user from SharePoint: {email}")
                return True
                
        except Exception as e:
            self.logger.error(f"Error syncing user from SharePoint to LMS: {str(e)}")
            return False
    
    def sync_lms_user_to_sharepoint(self, user) -> bool:
        """
        Sync an LMS user to SharePoint user list
        
        Args:
            user: LMS User model instance
            
        Returns:
            Boolean indicating success
        """
        try:
            user_data = {
                'LMSUserID': str(user.id),
                'Username': user.username,
                'Email': user.email,
                'FirstName': user.first_name,
                'LastName': user.last_name,
                'Role': user.role,
                'Branch': user.branch.name if user.branch else '',
                'DateOfBirth': user.date_of_birth.isoformat() if user.date_of_birth else '',
                'Gender': user.gender or '',
                'Phone': user.phone or '',
                'Address': user.address or '',
                'StudyArea': user.study_area or '',
                'Qualifications': user.qualifications or '',
                'JobRole': user.job_role or '',
                'Industry': user.industry or '',
                'Skills': user.skills or '',
                'LastLogin': user.last_login.isoformat() if user.last_login else '',
                'IsActive': user.is_active,
                'ProfileCompletion': getattr(user, 'profile_completion_percentage', 0),
                'CreatedDate': user.date_joined.isoformat(),
                'UpdatedDate': timezone.now().isoformat()
            }
            
            # Check if user already exists in SharePoint
            existing_users = self.api.get_list_items(
                self.config.user_list_name,
                f"Email eq '{user.email}'"
            )
            
            if existing_users:
                # Update existing user
                sharepoint_user_id = existing_users[0]['id']
                result = self.api.update_list_item(
                    self.config.user_list_name,
                    sharepoint_user_id,
                    user_data
                )
                self.logger.info(f"Updated SharePoint user: {user.email}")
            else:
                # Create new user
                result = self.api.create_list_item(
                    self.config.user_list_name,
                    user_data
                )
                self.logger.info(f"Created SharePoint user: {user.email}")
            
            return result is not None
            
        except Exception as e:
            self.logger.error(f"Error syncing LMS user to SharePoint: {str(e)}")
            return False
    
    def sync_course_groups_to_sharepoint(self) -> bool:
        """
        Sync all LMS course groups to SharePoint
        
        Returns:
            Boolean indicating overall success
        """
        try:
            from courses.models import Course
            
            courses = Course.objects.filter(branch=self.config.user.branch)
            success_count = 0
            
            for course in courses:
                try:
                    course_data = {
                        'LMSCourseID': str(course.id),
                        'CourseTitle': course.title,
                        'CourseDescription': course.description[:255] if course.description else '',
                        'Branch': course.branch.name if course.branch else '',
                        'Category': course.category.name if hasattr(course, 'category') and course.category else '',
                        'Language': course.language or 'English',
                        'DurationHours': getattr(course, 'duration_hours', 0),
                        'EnrollmentCount': course.enrolled_users.count() if hasattr(course, 'enrolled_users') else 0,
                        'CompletionCount': course.completed_users.count() if hasattr(course, 'completed_users') else 0,
                        'Status': course.status if hasattr(course, 'status') else 'active',
                        'IsVisible': course.is_visible if hasattr(course, 'is_visible') else True,
                        'HasPrerequisites': course.prerequisites.exists() if hasattr(course, 'prerequisites') else False,
                        'CreatedDate': course.created_at.isoformat() if hasattr(course, 'created_at') else timezone.now().isoformat(),
                        'UpdatedDate': timezone.now().isoformat()
                    }
                    
                    # Check if course already exists in SharePoint
                    existing_courses = self.api.get_list_items(
                        "LMS Course Groups",
                        f"LMSCourseID eq '{course.id}'"
                    )
                    
                    if existing_courses:
                        # Update existing course
                        sharepoint_course_id = existing_courses[0]['id']
                        result = self.api.update_list_item(
                            "LMS Course Groups",
                            sharepoint_course_id,
                            course_data
                        )
                    else:
                        # Create new course
                        result = self.api.create_list_item(
                            "LMS Course Groups",
                            course_data
                        )
                    
                    if result:
                        success_count += 1
                        
                except Exception as e:
                    self.logger.error(f"Error syncing course {course.id} to SharePoint: {str(e)}")
            
            self.logger.info(f"Synced {success_count}/{courses.count()} courses to SharePoint")
            return success_count > 0
            
        except Exception as e:
            self.logger.error(f"Error syncing course groups to SharePoint: {str(e)}")
            return False
    
    def sync_user_groups_to_sharepoint(self) -> bool:
        """
        Sync all LMS user groups to SharePoint
        
        Returns:
            Boolean indicating overall success
        """
        try:
            from groups.models import BranchGroup
            
            groups = BranchGroup.objects.filter(branch=self.config.user.branch)
            success_count = 0
            
            for group in groups:
                try:
                    group_data = {
                        'LMSGroupID': str(group.id),
                        'GroupName': group.name,
                        'GroupDescription': group.description[:255] if group.description else '',
                        'Branch': group.branch.name if group.branch else '',
                        'GroupType': 'branch_group',
                        'MemberCount': group.members.count() if hasattr(group, 'members') else 0,
                        'CreatedBy': group.created_by.get_full_name() if hasattr(group, 'created_by') and group.created_by else '',
                        'IsActive': getattr(group, 'is_active', True),
                        'HasCourseAccess': hasattr(group, 'course_access'),
                        'CanCreateTopics': getattr(group, 'can_create_topics', False),
                        'CanManageMembers': getattr(group, 'can_manage_members', False),
                        'CreatedDate': group.created_at.isoformat() if hasattr(group, 'created_at') else timezone.now().isoformat(),
                        'UpdatedDate': timezone.now().isoformat()
                    }
                    
                    # Check if group already exists in SharePoint
                    existing_groups = self.api.get_list_items(
                        "LMS User Groups",
                        f"LMSGroupID eq '{group.id}'"
                    )
                    
                    if existing_groups:
                        # Update existing group
                        sharepoint_group_id = existing_groups[0]['id']
                        result = self.api.update_list_item(
                            "LMS User Groups",
                            sharepoint_group_id,
                            group_data
                        )
                    else:
                        # Create new group
                        result = self.api.create_list_item(
                            "LMS User Groups",
                            group_data
                        )
                    
                    if result:
                        success_count += 1
                        
                except Exception as e:
                    self.logger.error(f"Error syncing group {group.id} to SharePoint: {str(e)}")
            
            self.logger.info(f"Synced {success_count}/{groups.count()} user groups to SharePoint")
            return success_count > 0
            
        except Exception as e:
            self.logger.error(f"Error syncing user groups to SharePoint: {str(e)}")
            return False
    
    def sync_assessment_results_to_sharepoint(self, assessment_data: Dict) -> bool:
        """
        Sync assessment results from LMS gradebook to SharePoint
        
        Args:
            assessment_data: Dictionary containing assessment information
            
        Returns:
            Boolean indicating success
        """
        try:
            assessment_record = {
                'LMSAssessmentID': assessment_data.get('assessment_id', ''),
                'UserEmail': assessment_data.get('user_email', ''),
                'UserID': assessment_data.get('user_id', ''),
                'CourseID': assessment_data.get('course_id', ''),
                'CourseName': assessment_data.get('course_name', ''),
                'AssignmentID': assessment_data.get('assignment_id', ''),
                'AssignmentTitle': assessment_data.get('assignment_title', ''),
                'QuizID': assessment_data.get('quiz_id', ''),
                'QuizTitle': assessment_data.get('quiz_title', ''),
                'Score': assessment_data.get('score', 0),
                'MaxScore': assessment_data.get('max_score', 100),
                'Percentage': assessment_data.get('percentage', 0),
                'Grade': assessment_data.get('grade', ''),
                'PassingScore': assessment_data.get('passing_score', 70),
                'IsPassed': assessment_data.get('is_passed', False),
                'Attempts': assessment_data.get('attempts', 1),
                'TimeSpent': assessment_data.get('time_spent', 0),
                'SubmissionDate': assessment_data.get('submission_date', timezone.now().isoformat()),
                'GradedDate': assessment_data.get('graded_date', timezone.now().isoformat()),
                'Feedback': assessment_data.get('feedback', '')[:500] if assessment_data.get('feedback') else '',
                'UpdatedDate': timezone.now().isoformat()
            }
            
            # Check if assessment already exists
            existing_assessments = self.api.get_list_items(
                "LMS Assessment Results",
                f"LMSAssessmentID eq '{assessment_data.get('assessment_id')}'"
            )
            
            if existing_assessments:
                # Update existing assessment
                sharepoint_assessment_id = existing_assessments[0]['id']
                result = self.api.update_list_item(
                    "LMS Assessment Results",
                    sharepoint_assessment_id,
                    assessment_record
                )
            else:
                # Create new assessment record
                result = self.api.create_list_item(
                    "LMS Assessment Results",
                    assessment_record
                )
            
            self.logger.info(f"Synced assessment result to SharePoint: {assessment_data.get('assessment_id')}")
            return result is not None
            
        except Exception as e:
            self.logger.error(f"Error syncing assessment results to SharePoint: {str(e)}")
            return False
    
    def auto_upload_certificate(self, certificate_data: Dict, file_content: bytes) -> bool:
        """
        Automatically upload generated certificate to SharePoint
        
        Args:
            certificate_data: Certificate information
            file_content: PDF certificate content
            
        Returns:
            Boolean indicating success
        """
        try:
            filename = f"{certificate_data.get('certificate_number', 'cert')}_{certificate_data.get('student_id', 'student')}.pdf"
            
            result = self.api.upload_certificate(file_content, filename, certificate_data)
            
            if result and result.get('success'):
                self.logger.info(f"Successfully uploaded certificate for {certificate_data.get('student_name')}")
                
                # Update certificate download count tracking if registry was created
                if result.get('registry_entry'):
                    self._track_certificate_usage(certificate_data.get('certificate_id'))
                
                return True
            else:
                self.logger.error(f"Failed to upload certificate for {certificate_data.get('student_name')}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error auto-uploading certificate: {str(e)}")
            return False
    
    def export_lms_analytics_to_sharepoint(self) -> bool:
        """
        Export LMS analytics data to SharePoint for Power BI integration
        
        Returns:
            Boolean indicating success
        """
        try:
            # Gather analytics data
            analytics_data = self._gather_analytics_data()
            
            # Create filename with timestamp
            timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
            filename = f"lms_analytics_{timestamp}.json"
            
            result = self.api.export_analytics_data(analytics_data, filename)
            
            if result:
                self.logger.info(f"Successfully exported analytics data to SharePoint: {filename}")
                return True
            else:
                self.logger.error("Failed to export analytics data to SharePoint")
                return False
                
        except Exception as e:
            self.logger.error(f"Error exporting analytics data to SharePoint: {str(e)}")
            return False
    
    def monitor_sharepoint_changes(self) -> Dict:
        """
        Monitor SharePoint lists for changes and sync back to LMS
        
        Returns:
            Dictionary with sync results
        """
        results = {
            'users_synced': 0,
            'courses_synced': 0,
            'groups_synced': 0,
            'errors': []
        }
        
        try:
            # Check for new/updated users in SharePoint
            if self.config.enable_user_sync:
                sharepoint_users = self.api.get_list_items(
                    self.config.user_list_name,
                    f"UpdatedDate ge '{(timezone.now() - timedelta(hours=1)).isoformat()}'"
                )
                
                for sp_user in sharepoint_users:
                    if self.sync_user_from_sharepoint_to_lms(sp_user):
                        results['users_synced'] += 1
            
            # Additional monitoring logic can be added here for courses and groups
            
        except Exception as e:
            self.logger.error(f"Error monitoring SharePoint changes: {str(e)}")
            results['errors'].append(str(e))
        
        return results
    
    def _parse_date(self, date_string: str):
        """Parse date string from SharePoint"""
        if not date_string:
            return None
        try:
            return datetime.fromisoformat(date_string.replace('Z', '+00:00'))
        except:
            return None
    
    def _gather_analytics_data(self) -> Dict:
        """Gather comprehensive analytics data from LMS"""
        try:
            from users.models import CustomUser
            from courses.models import Course, CourseEnrollment, TopicProgress
            from gradebook.models import Grade
            from django.db.models import Count, Avg
            
            # User analytics
            user_stats = CustomUser.objects.filter(branch=self.config.user.branch).aggregate(
                total_users=Count('id'),
                active_users=Count('id', filter=models.Q(is_active=True)),
                learners=Count('id', filter=models.Q(role='learner')),
                instructors=Count('id', filter=models.Q(role='instructor')),
                admins=Count('id', filter=models.Q(role='admin'))
            )
            
            # Course analytics
            course_stats = Course.objects.filter(branch=self.config.user.branch).aggregate(
                total_courses=Count('id'),
                active_courses=Count('id', filter=models.Q(status='active'))
            )
            
            # Enrollment analytics
            enrollment_stats = CourseEnrollment.objects.filter(
                course__branch=self.config.user.branch
            ).aggregate(
                total_enrollments=Count('id'),
                completed_enrollments=Count('id', filter=models.Q(completed=True))
            )
            
            # Grade analytics
            grade_stats = Grade.objects.filter(
                assignment__course__branch=self.config.user.branch
            ).aggregate(
                average_score=Avg('score'),
                total_assessments=Count('id')
            )
            
            return {
                'timestamp': timezone.now().isoformat(),
                'branch': self.config.user.branch.name if self.config.user.branch else '',
                'user_statistics': user_stats,
                'course_statistics': course_stats,
                'enrollment_statistics': enrollment_stats,
                'grade_statistics': grade_stats,
                'export_type': 'comprehensive_analytics'
            }
            
        except Exception as e:
            self.logger.error(f"Error gathering analytics data: {str(e)}")
            return {
                'timestamp': timezone.now().isoformat(),
                'error': str(e),
                'export_type': 'error_export'
            }
    
    def _track_certificate_usage(self, certificate_id: str):
        """Track certificate download/usage in SharePoint registry"""
        try:
            # This would be called when someone downloads a certificate from SharePoint
            # Implementation would depend on SharePoint webhook or periodic sync
            pass
        except Exception as e:
            self.logger.error(f"Error tracking certificate usage: {str(e)}") 