"""
Ultra-Deep Data Integrity Validator
Provides comprehensive data integrity validation for all critical operations
"""

import logging
from typing import Dict, List, Any, Optional, Tuple
from django.db import transaction, IntegrityError
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal

logger = logging.getLogger(__name__)

class UltraDataIntegrityValidator:
    """Ultra-comprehensive data integrity validation"""
    
    @staticmethod
    def validate_enrollment_integrity(user, course) -> Dict[str, Any]:
        """Validate enrollment data integrity with comprehensive checks"""
        try:
            # Check for circular dependencies
            if UltraDataIntegrityValidator._has_circular_dependency(course):
                return {'valid': False, 'error': 'Circular dependency detected in prerequisites'}
            
            # Check for duplicate enrollments
            from courses.models import CourseEnrollment
            existing = CourseEnrollment.objects.filter(user=user, course=course).exists()
            if existing:
                return {'valid': False, 'error': 'User already enrolled in this course'}
            
            # Check for business rule violations
            business_validation = UltraDataIntegrityValidator._validate_business_rules(user, course)
            if not business_validation['valid']:
                return business_validation
            
            # Check for data consistency
            consistency_validation = UltraDataIntegrityValidator._validate_data_consistency(user, course)
            if not consistency_validation['valid']:
                return consistency_validation
            
            return {'valid': True, 'message': 'Enrollment integrity validated'}
            
        except Exception as e:
            logger.error(f"Enrollment integrity validation failed: {e}")
            return {'valid': False, 'error': f'Validation error: {str(e)}'}
    
    @staticmethod
    def _has_circular_dependency(course, visited=None, depth=0) -> bool:
        """Check for circular dependencies in course prerequisites"""
        if visited is None:
            visited = set()
        
        if depth > 10:  # Prevent infinite recursion
            logger.warning(f"Possible circular dependency detected at depth {depth}")
            return True
        
        if course.id in visited:
            return True
        
        visited.add(course.id)
        
        for prereq in course.prerequisites.all():
            if UltraDataIntegrityValidator._has_circular_dependency(prereq, visited.copy(), depth + 1):
                return True
        
        return False
    
    @staticmethod
    def _validate_business_rules(user, course) -> Dict[str, Any]:
        """Validate business rules for enrollment"""
        # Check if user is active
        if not user.is_active:
            return {'valid': False, 'error': 'User account is not active'}
        
        # Check if course is active
        if not course.is_active:
            return {'valid': False, 'error': 'Course is not active'}
        
        # Check branch compatibility
        if hasattr(user, 'branch') and hasattr(course, 'branch'):
            if user.branch and course.branch and user.branch != course.branch:
                # Allow if user has cross-branch permissions
                if not hasattr(user, 'can_access_cross_branch') or not user.can_access_cross_branch:
                    return {'valid': False, 'error': 'User branch does not match course branch'}
        
        # Check role compatibility
        if user.role == 'learner' and course.instructor == user:
            return {'valid': False, 'error': 'Learner cannot be enrolled in their own course'}
        
        return {'valid': True}
    
    @staticmethod
    def _validate_data_consistency(user, course) -> Dict[str, Any]:
        """Validate data consistency for enrollment"""
        # Check if user exists in database
        if not user.pk:
            return {'valid': False, 'error': 'User not saved to database'}
        
        # Check if course exists in database
        if not course.pk:
            return {'valid': False, 'error': 'Course not saved to database'}
        
        # Check for required fields
        if not user.username:
            return {'valid': False, 'error': 'User username is required'}
        
        if not course.title:
            return {'valid': False, 'error': 'Course title is required'}
        
        return {'valid': True}
    
    @staticmethod
    def validate_role_integrity(user, new_role) -> Dict[str, Any]:
        """Validate role change integrity with comprehensive checks"""
        try:
            # Check for permission escalation
            if UltraDataIntegrityValidator._is_permission_escalation(user.role, new_role):
                return {'valid': False, 'error': 'Permission escalation detected'}
            
            # Check for business rule violations
            if UltraDataIntegrityValidator._violates_business_rules(user, new_role):
                return {'valid': False, 'error': 'Business rule violation detected'}
            
            # Check for data consistency
            if UltraDataIntegrityValidator._validate_role_consistency(user, new_role):
                return {'valid': False, 'error': 'Role consistency violation detected'}
            
            return {'valid': True, 'message': 'Role integrity validated'}
            
        except Exception as e:
            logger.error(f"Role integrity validation failed: {e}")
            return {'valid': False, 'error': f'Validation error: {str(e)}'}
    
    @staticmethod
    def _is_permission_escalation(current_role: str, new_role: str) -> bool:
        """Check if role change is a permission escalation"""
        role_hierarchy = {
            'learner': 1,
            'instructor': 2,
            'admin': 3,
            'superadmin': 4,
            'globaladmin': 5
        }
        
        current_level = role_hierarchy.get(current_role, 0)
        new_level = role_hierarchy.get(new_role, 0)
        
        # Allow one level up, but not more
        return new_level > current_level + 1
    
    @staticmethod
    def _violates_business_rules(user, new_role: str) -> bool:
        """Check if role change violates business rules"""
        # Check if user has required permissions for new role
        if new_role == 'instructor' and not hasattr(user, 'can_instruct'):
            return True
        
        if new_role == 'admin' and not hasattr(user, 'can_admin'):
            return True
        
        # Check for conflicting roles
        if hasattr(user, 'conflicting_roles') and new_role in user.conflicting_roles:
            return True
        
        return False
    
    @staticmethod
    def _validate_role_consistency(user, new_role: str) -> bool:
        """Validate role consistency"""
        # Check if user has required data for new role
        if new_role == 'instructor' and not user.first_name:
            return True
        
        if new_role == 'admin' and not user.email:
            return True
        
        return False
    
    @staticmethod
    def validate_financial_integrity(amount: Decimal, currency: str = 'GBP') -> Dict[str, Any]:
        """Validate financial data integrity"""
        try:
            # Check amount is positive
            if amount <= 0:
                return {'valid': False, 'error': 'Amount must be positive'}
            
            # Check amount is within reasonable bounds
            if amount > Decimal('999999.99'):
                return {'valid': False, 'error': 'Amount exceeds maximum limit'}
            
            # Check currency is valid
            valid_currencies = ['GBP', 'USD', 'EUR']
            if currency not in valid_currencies:
                return {'valid': False, 'error': f'Invalid currency: {currency}'}
            
            # Check decimal places
            if amount.as_tuple().exponent < -2:
                return {'valid': False, 'error': 'Amount has too many decimal places'}
            
            return {'valid': True, 'message': 'Financial integrity validated'}
            
        except Exception as e:
            logger.error(f"Financial integrity validation failed: {e}")
            return {'valid': False, 'error': f'Validation error: {str(e)}'}
    
    @staticmethod
    def validate_file_integrity(file_path: str, expected_size: int = None) -> Dict[str, Any]:
        """Validate file integrity"""
        try:
            import os
            
            # Check if file exists
            if not os.path.exists(file_path):
                return {'valid': False, 'error': 'File does not exist'}
            
            # Check file size
            actual_size = os.path.getsize(file_path)
            if expected_size and actual_size != expected_size:
                return {'valid': False, 'error': f'File size mismatch: expected {expected_size}, got {actual_size}'}
            
            # Check file is readable
            if not os.access(file_path, os.R_OK):
                return {'valid': False, 'error': 'File is not readable'}
            
            # Check file is not empty
            if actual_size == 0:
                return {'valid': False, 'error': 'File is empty'}
            
            return {'valid': True, 'message': 'File integrity validated'}
            
        except Exception as e:
            logger.error(f"File integrity validation failed: {e}")
            return {'valid': False, 'error': f'Validation error: {str(e)}'}
    
    @staticmethod
    def validate_database_integrity() -> Dict[str, Any]:
        """Validate overall database integrity"""
        try:
            from django.db import connection
            
            with connection.cursor() as cursor:
                # Check for orphaned records
                orphaned_checks = [
                    "SELECT COUNT(*) FROM gradebook_grade g LEFT JOIN users_customuser u ON g.student_id = u.id WHERE u.id IS NULL",
                    "SELECT COUNT(*) FROM courses_courseenrollment e LEFT JOIN users_customuser u ON e.user_id = u.id WHERE u.id IS NULL",
                    "SELECT COUNT(*) FROM courses_courseenrollment e LEFT JOIN courses_course c ON e.course_id = c.id WHERE c.id IS NULL",
                ]
                
                orphaned_count = 0
                for check in orphaned_checks:
                    cursor.execute(check)
                    count = cursor.fetchone()[0]
                    orphaned_count += count
                
                if orphaned_count > 0:
                    return {'valid': False, 'error': f'Found {orphaned_count} orphaned records'}
                
                # Check for data consistency
                consistency_checks = [
                    "SELECT COUNT(*) FROM gradebook_grade g JOIN assignments_assignment a ON g.assignment_id = a.id WHERE g.course_id != a.course_id",
                    "SELECT COUNT(*) FROM quiz_quizattempt q JOIN quiz_quiz qu ON q.quiz_id = qu.id WHERE q.user_id IS NULL",
                ]
                
                consistency_count = 0
                for check in consistency_checks:
                    cursor.execute(check)
                    count = cursor.fetchone()[0]
                    consistency_count += count
                
                if consistency_count > 0:
                    return {'valid': False, 'error': f'Found {consistency_count} consistency violations'}
                
                return {'valid': True, 'message': 'Database integrity validated'}
                
        except Exception as e:
            logger.error(f"Database integrity validation failed: {e}")
            return {'valid': False, 'error': f'Validation error: {str(e)}'}

class UltraTransactionValidator:
    """Ultra-comprehensive transaction validation"""
    
    @staticmethod
    def validate_atomic_operation(operation_func, *args, **kwargs) -> Dict[str, Any]:
        """Validate atomic operation with comprehensive checks"""
        try:
            with transaction.atomic():
                result = operation_func(*args, **kwargs)
                
                # Validate result
                if not result:
                    return {'valid': False, 'error': 'Operation returned no result'}
                
                return {'valid': True, 'result': result}
                
        except IntegrityError as e:
            logger.error(f"Integrity error in atomic operation: {e}")
            return {'valid': False, 'error': f'Integrity error: {str(e)}'}
        except Exception as e:
            logger.error(f"Error in atomic operation: {e}")
            return {'valid': False, 'error': f'Operation error: {str(e)}'}
    
    @staticmethod
    def validate_bulk_operation(operation_func, items: List[Any]) -> Dict[str, Any]:
        """Validate bulk operation with comprehensive checks"""
        try:
            with transaction.atomic():
                results = []
                for item in items:
                    result = operation_func(item)
                    results.append(result)
                
                # Validate all results
                if not all(results):
                    return {'valid': False, 'error': 'Some operations failed'}
                
                return {'valid': True, 'results': results}
                
        except IntegrityError as e:
            logger.error(f"Integrity error in bulk operation: {e}")
            return {'valid': False, 'error': f'Integrity error: {str(e)}'}
        except Exception as e:
            logger.error(f"Error in bulk operation: {e}")
            return {'valid': False, 'error': f'Operation error: {str(e)}'}
