"""
Comprehensive Test Suite for Role and Permission System
Tests all role and permission scenarios to ensure proper functionality
"""

from django.test import TestCase, TransactionTestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import IntegrityError, transaction
from django.utils import timezone
from datetime import timedelta
import logging

from role_management.models import Role, RoleCapability, UserRole, RoleAuditLog
from core.unified_permissions import UnifiedPermissionManager
from users.models import CustomUser
from branches.models import Branch
from business.models import Business

User = get_user_model()
logger = logging.getLogger(__name__)

class RolePermissionTestCase(TestCase):
    """Test cases for role and permission system"""
    
    def setUp(self):
        """Set up test data"""
        # Create test business
        self.business = Business.objects.create(
            name="Test Business",
            description="Test business for role testing"
        )
        
        # Create test branch
        self.branch = Branch.objects.create(
            name="Test Branch",
            business=self.business,
            description="Test branch for role testing"
        )
        
        # Create test users with different roles
        self.global_admin = CustomUser.objects.create_user(
            username='globaladmin',
            email='globaladmin@test.com',
            password='testpass123',
            role='globaladmin',
            branch=self.branch
        )
        
        self.super_admin = CustomUser.objects.create_user(
            username='superadmin',
            email='superadmin@test.com',
            password='testpass123',
            role='superadmin',
            branch=self.branch
        )
        
        self.admin = CustomUser.objects.create_user(
            username='admin',
            email='admin@test.com',
            password='testpass123',
            role='admin',
            branch=self.branch
        )
        
        self.instructor = CustomUser.objects.create_user(
            username='instructor',
            email='instructor@test.com',
            password='testpass123',
            role='instructor',
            branch=self.branch
        )
        
        self.learner = CustomUser.objects.create_user(
            username='learner',
            email='learner@test.com',
            password='testpass123',
            role='learner',
            branch=self.branch
        )
    
    def test_role_hierarchy(self):
        """Test role hierarchy validation"""
        # Test that higher roles can manage lower roles
        self.assertTrue(UnifiedPermissionManager.can_manage_role(self.global_admin, 'superadmin'))
        self.assertTrue(UnifiedPermissionManager.can_manage_role(self.global_admin, 'admin'))
        self.assertTrue(UnifiedPermissionManager.can_manage_role(self.super_admin, 'admin'))
        
        # Test that lower roles cannot manage higher roles
        self.assertFalse(UnifiedPermissionManager.can_manage_role(self.admin, 'superadmin'))
        self.assertFalse(UnifiedPermissionManager.can_manage_role(self.instructor, 'admin'))
        self.assertFalse(UnifiedPermissionManager.can_manage_role(self.learner, 'instructor'))
    
    def test_role_assignment_permissions(self):
        """Test role assignment permissions"""
        # Global admin can assign any role
        self.assertTrue(UnifiedPermissionManager.can_assign_role(self.global_admin, 'superadmin', self.admin))
        self.assertTrue(UnifiedPermissionManager.can_assign_role(self.global_admin, 'admin', self.instructor))
        
        # Super admin can assign admin and lower roles
        self.assertTrue(UnifiedPermissionManager.can_assign_role(self.super_admin, 'admin', self.instructor))
        self.assertFalse(UnifiedPermissionManager.can_assign_role(self.super_admin, 'globaladmin', self.admin))
        
        # Admin cannot assign superadmin or globaladmin roles
        self.assertFalse(UnifiedPermissionManager.can_assign_role(self.admin, 'superadmin', self.instructor))
        self.assertFalse(UnifiedPermissionManager.can_assign_role(self.admin, 'globaladmin', self.instructor))
    
    def test_branch_access_permissions(self):
        """Test branch access permissions"""
        # Global admin can access any branch
        self.assertTrue(UnifiedPermissionManager.can_access_branch(self.global_admin, self.branch))
        
        # Users can access their own branch
        self.assertTrue(UnifiedPermissionManager.can_access_branch(self.admin, self.branch))
        
        # Create another branch
        other_branch = Branch.objects.create(
            name="Other Branch",
            business=self.business,
            description="Other branch for testing"
        )
        
        # Admin cannot access other branch
        self.assertFalse(UnifiedPermissionManager.can_access_branch(self.admin, other_branch))
    
    def test_business_management_permissions(self):
        """Test business management permissions"""
        # Global admin can manage any business
        self.assertTrue(UnifiedPermissionManager.can_manage_business(self.global_admin, self.business))
        
        # Super admin can manage their assigned business
        if hasattr(self.super_admin, 'business_assignments'):
            self.super_admin.business_assignments.create(business=self.business, is_active=True)
            self.assertTrue(UnifiedPermissionManager.can_manage_business(self.super_admin, self.business))
        
        # Admin cannot manage business
        self.assertFalse(UnifiedPermissionManager.can_manage_business(self.admin, self.business))
    
    def test_user_role_creation(self):
        """Test user role creation and validation"""
        # Create a custom role
        custom_role = Role.objects.create(
            name='custom',
            custom_name='Test Custom Role',
            description='Test custom role for testing'
        )
        
        # Add capabilities to the role
        RoleCapability.objects.create(
            role=custom_role,
            capability='view_courses',
            description='View courses capability'
        )
        
        # Test role assignment
        user_role = UserRole.objects.create(
            user=self.instructor,
            role=custom_role,
            assigned_by=self.admin,
            is_active=True
        )
        
        self.assertTrue(user_role.is_active)
        self.assertEqual(user_role.user, self.instructor)
        self.assertEqual(user_role.role, custom_role)
    
    def test_role_conflicts(self):
        """Test role conflict resolution"""
        # Create conflicting role assignments
        admin_role = Role.objects.get(name='admin')
        instructor_role = Role.objects.get(name='instructor')
        
        # Assign admin role to instructor
        UserRole.objects.create(
            user=self.instructor,
            role=admin_role,
            assigned_by=self.global_admin,
            is_active=True
        )
        
        # Assign instructor role to admin (should conflict)
        with self.assertRaises(ValidationError):
            UserRole.objects.create(
                user=self.admin,
                role=instructor_role,
                assigned_by=self.global_admin,
                is_active=True
            )
    
    def test_expired_role_cleanup(self):
        """Test expired role cleanup"""
        # Create a role with expiration
        expired_role = UserRole.objects.create(
            user=self.learner,
            role=Role.objects.get(name='instructor'),
            assigned_by=self.admin,
            is_active=True,
            expires_at=timezone.now() - timedelta(days=1)  # Expired yesterday
        )
        
        # Run cleanup
        cleaned_count = UserRole.deactivate_expired_roles()
        
        # Check that expired role was deactivated
        expired_role.refresh_from_db()
        self.assertFalse(expired_role.is_active)
        self.assertEqual(cleaned_count, 1)
    
    def test_orphaned_assignment_cleanup(self):
        """Test orphaned assignment cleanup"""
        # Create an orphaned assignment
        orphaned_role = UserRole.objects.create(
            user=None,  # Orphaned user
            role=Role.objects.get(name='learner'),
            assigned_by=self.admin,
            is_active=True
        )
        
        # Run cleanup
        cleaned_count = UserRole.cleanup_orphaned_assignments()
        
        # Check that orphaned assignment was cleaned up
        self.assertEqual(cleaned_count, 1)
        self.assertFalse(UserRole.objects.filter(id=orphaned_role.id).exists())
    
    def test_permission_capabilities(self):
        """Test permission capabilities"""
        # Test that users have appropriate capabilities
        global_admin_caps = UnifiedPermissionManager.get_user_capabilities(self.global_admin)
        self.assertIn('manage_users', global_admin_caps)
        self.assertIn('manage_roles', global_admin_caps)
        
        admin_caps = UnifiedPermissionManager.get_user_capabilities(self.admin)
        self.assertIn('manage_users', admin_caps)
        self.assertNotIn('manage_roles', admin_caps)  # Admin cannot manage roles
        
        instructor_caps = UnifiedPermissionManager.get_user_capabilities(self.instructor)
        self.assertIn('view_courses', instructor_caps)
        self.assertNotIn('manage_users', instructor_caps)
    
    def test_self_assignment_restrictions(self):
        """Test self-assignment restrictions"""
        # Test that users cannot assign themselves higher roles
        with self.assertRaises(ValidationError):
            UserRole.objects.create(
                user=self.admin,
                role=Role.objects.get(name='superadmin'),
                assigned_by=self.admin,  # Self-assignment
                is_active=True
            )
    
    def test_branch_switching_validation(self):
        """Test branch switching validation"""
        # Create another branch
        other_branch = Branch.objects.create(
            name="Other Branch",
            business=self.business,
            description="Other branch for testing"
        )
        
        # Admin should not be able to switch to other branch
        from branches.views import switch_branch
        from django.test import RequestFactory
        
        factory = RequestFactory()
        request = factory.post('/switch-branch/', {'branch_id': other_branch.id})
        request.user = self.admin
        
        # This should fail validation
        with self.assertRaises(Exception):
            switch_branch(request)
    
    def test_audit_logging(self):
        """Test audit logging functionality"""
        # Create a role assignment
        user_role = UserRole.objects.create(
            user=self.learner,
            role=Role.objects.get(name='instructor'),
            assigned_by=self.admin,
            is_active=True
        )
        
        # Check that audit log was created
        audit_logs = RoleAuditLog.objects.filter(target_user=self.learner)
        self.assertTrue(audit_logs.exists())
        
        # Check audit log details
        audit_log = audit_logs.first()
        self.assertEqual(audit_log.action, 'assign')
        self.assertEqual(audit_log.target_user, self.learner)
        self.assertEqual(audit_log.user, self.admin)
    
    def test_input_validation(self):
        """Test input validation for role names"""
        # Test valid custom role name
        valid_role = Role.objects.create(
            name='custom',
            custom_name='Valid Role Name',
            description='Valid role description'
        )
        self.assertTrue(valid_role.is_active)
        
        # Test invalid custom role names
        invalid_names = [
            'Admin Role',  # Contains 'admin'
            'Super Role',  # Contains 'super'
            'System Role',  # Contains 'system'
            'Role<script>',  # Contains script tag
            'Role<script>alert("xss")</script>',  # XSS attempt
            'Role; DROP TABLE users;',  # SQL injection attempt
        ]
        
        for invalid_name in invalid_names:
            with self.assertRaises(ValidationError):
                Role.objects.create(
                    name='custom',
                    custom_name=invalid_name,
                    description='Invalid role description'
                )
    
    def test_performance_optimization(self):
        """Test performance optimization"""
        # Create multiple users and roles
        users = []
        for i in range(100):
            user = CustomUser.objects.create_user(
                username=f'user{i}',
                email=f'user{i}@test.com',
                password='testpass123',
                role='learner',
                branch=self.branch
            )
            users.append(user)
        
        # Test that permission checking is efficient
        import time
        start_time = time.time()
        
        for user in users[:10]:  # Test with first 10 users
            caps = UnifiedPermissionManager.get_user_capabilities(user)
            self.assertIsInstance(caps, list)
        
        end_time = time.time()
        execution_time = end_time - start_time
        
        # Should complete in reasonable time (less than 1 second for 10 users)
        self.assertLess(execution_time, 1.0)
    
    def test_concurrent_role_assignment(self):
        """Test concurrent role assignment handling"""
        # This test would require threading, but we can test the atomic nature
        with transaction.atomic():
            # Create role assignment
            user_role = UserRole.objects.create(
                user=self.learner,
                role=Role.objects.get(name='instructor'),
                assigned_by=self.admin,
                is_active=True
            )
            
            # Try to create duplicate assignment (should fail)
            with self.assertRaises(ValidationError):
                UserRole.objects.create(
                    user=self.learner,
                    role=Role.objects.get(name='instructor'),
                    assigned_by=self.admin,
                    is_active=True
                )
    
    def test_error_handling(self):
        """Test error handling and sanitization"""
        # Test that errors are properly sanitized
        from role_management.utils import SessionErrorHandler
        
        # Test generic error message
        generic_error = SessionErrorHandler.sanitize_error_message(
            Exception("Database error with password=secret123"), 
            'database', 
            show_details=False
        )
        self.assertIn('Unable to process request', generic_error)
        self.assertNotIn('password=secret123', generic_error)
        
        # Test detailed error message for admin
        detailed_error = SessionErrorHandler.sanitize_error_message(
            Exception("Database error with password=secret123"), 
            'database', 
            show_details=True
        )
        self.assertIn('Database error', detailed_error)
        self.assertNotIn('password=secret123', detailed_error)  # Should be redacted


class RolePermissionIntegrationTestCase(TransactionTestCase):
    """Integration tests for role and permission system"""
    
    def setUp(self):
        """Set up integration test data"""
        # Create test business
        self.business = Business.objects.create(
            name="Integration Test Business",
            description="Business for integration testing"
        )
        
        # Create test branch
        self.branch = Branch.objects.create(
            name="Integration Test Branch",
            business=self.business,
            description="Branch for integration testing"
        )
    
    def test_full_role_lifecycle(self):
        """Test complete role lifecycle from creation to deletion"""
        # Create global admin
        global_admin = CustomUser.objects.create_user(
            username='globaladmin',
            email='globaladmin@test.com',
            password='testpass123',
            role='globaladmin',
            branch=self.branch
        )
        
        # Create custom role
        custom_role = Role.objects.create(
            name='custom',
            custom_name='Integration Test Role',
            description='Role for integration testing'
        )
        
        # Add capabilities
        RoleCapability.objects.create(
            role=custom_role,
            capability='view_courses',
            description='View courses'
        )
        
        # Create user
        user = CustomUser.objects.create_user(
            username='testuser',
            email='testuser@test.com',
            password='testpass123',
            role='learner',
            branch=self.branch
        )
        
        # Assign role
        user_role = UserRole.objects.create(
            user=user,
            role=custom_role,
            assigned_by=global_admin,
            is_active=True
        )
        
        # Verify assignment
        self.assertTrue(user_role.is_active)
        self.assertEqual(user_role.user, user)
        self.assertEqual(user_role.role, custom_role)
        
        # Test capabilities
        caps = UnifiedPermissionManager.get_user_capabilities(user)
        self.assertIn('view_courses', caps)
        
        # Deactivate role
        user_role.is_active = False
        user_role.save()
        
        # Verify deactivation
        user_role.refresh_from_db()
        self.assertFalse(user_role.is_active)
        
        # Delete role
        user_role.delete()
        
        # Verify deletion
        self.assertFalse(UserRole.objects.filter(id=user_role.id).exists())
    
    def test_role_hierarchy_enforcement(self):
        """Test that role hierarchy is properly enforced"""
        # Create users with different roles
        global_admin = CustomUser.objects.create_user(
            username='globaladmin',
            email='globaladmin@test.com',
            password='testpass123',
            role='globaladmin',
            branch=self.branch
        )
        
        super_admin = CustomUser.objects.create_user(
            username='superadmin',
            email='superadmin@test.com',
            password='testpass123',
            role='superadmin',
            branch=self.branch
        )
        
        admin = CustomUser.objects.create_user(
            username='admin',
            email='admin@test.com',
            password='testpass123',
            role='admin',
            branch=self.branch
        )
        
        # Test that hierarchy is enforced
        self.assertTrue(UnifiedPermissionManager.can_assign_role(global_admin, 'superadmin', super_admin))
        self.assertTrue(UnifiedPermissionManager.can_assign_role(super_admin, 'admin', admin))
        self.assertFalse(UnifiedPermissionManager.can_assign_role(admin, 'superadmin', super_admin))
        self.assertFalse(UnifiedPermissionManager.can_assign_role(super_admin, 'globaladmin', global_admin))
    
    def test_business_assignment_validation(self):
        """Test business assignment validation"""
        # Create super admin with business assignment
        super_admin = CustomUser.objects.create_user(
            username='superadmin',
            email='superadmin@test.com',
            password='testpass123',
            role='superadmin',
            branch=self.branch
        )
        
        # Create business assignment
        if hasattr(super_admin, 'business_assignments'):
            super_admin.business_assignments.create(
                business=self.business,
                is_active=True
            )
        
        # Test business access
        self.assertTrue(UnifiedPermissionManager.can_manage_business(super_admin, self.business))
        
        # Create another business
        other_business = Business.objects.create(
            name="Other Business",
            description="Other business for testing"
        )
        
        # Super admin should not have access to other business
        self.assertFalse(UnifiedPermissionManager.can_manage_business(super_admin, other_business))