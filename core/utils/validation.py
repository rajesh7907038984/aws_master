"""
Comprehensive Validation Service for LMS
Provides robust validation for user data and bulk operations
"""

import re
import logging
from typing import Dict, List, Tuple, Any, Optional
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)

class ValidationService:
    """Centralized service for data validation across the LMS"""
    
    # Validation patterns
    USERNAME_PATTERN = re.compile(r'^[a-zA-Z0-9_.-]+$')
    PHONE_PATTERN = re.compile(r'^\+?[\d\s\-\(\)]+$')
    POSTCODE_PATTERN = re.compile(r'^[A-Z0-9\s]{2,8}$', re.IGNORECASE)
    
    # Valid role choices
    VALID_ROLES = ['learner', 'instructor', 'admin', 'superadmin']
    
    @classmethod
    def validate_email_format(cls, email: str) -> Tuple[bool, str]:
        """
        Validate email format and uniqueness
        
        Args:
            email: Email address to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not email or not email.strip():
            return False, "Email is required"
        
        email = email.strip().lower()
        
        try:
            validate_email(email)
        except ValidationError:
            return False, "Invalid email format"
        
        # Check uniqueness
        User = get_user_model()
        if User.objects.filter(email=email).exists():
            return False, "Email already exists in the system"
        
        return True, ""
    
    @classmethod
    def validate_username_format(cls, username: str) -> Tuple[bool, str]:
        """
        Validate username format and uniqueness
        
        Args:
            username: Username to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not username or not username.strip():
            return False, "Username is required"
        
        username = username.strip()
        
        # Check length
        if len(username) < 3:
            return False, "Username must be at least 3 characters long"
        
        if len(username) > 150:
            return False, "Username must be 150 characters or less"
        
        # Check format
        if not cls.USERNAME_PATTERN.match(username):
            return False, "Username can only contain letters, numbers, dots, hyphens, and underscores"
        
        # Check for reserved usernames
        reserved_usernames = ['admin', 'administrator', 'root', 'system', 'api', 'www', 'mail', 'ftp']
        if username.lower() in reserved_usernames:
            return False, "Username is reserved"
        
        # Check uniqueness
        User = get_user_model()
        if User.objects.filter(username=username).exists():
            return False, "Username already exists in the system"
        
        return True, ""
    
    @classmethod
    def validate_password_strength(cls, password: str, user_data: Optional[Dict] = None) -> Tuple[bool, List[str]]:
        """
        Validate password strength using Django validators
        
        Args:
            password: Password to validate
            user_data: Optional user data for validation context
            
        Returns:
            Tuple of (is_valid, error_messages)
        """
        if not password:
            return False, ["Password is required"]
        
        errors = []
        
        try:
            # Create a mock user object for validation context
            User = get_user_model()
            mock_user = User()
            
            if user_data:
                mock_user.username = user_data.get('username', '')
                mock_user.email = user_data.get('email', '')
                mock_user.first_name = user_data.get('first_name', '')
                mock_user.last_name = user_data.get('last_name', '')
            
            validate_password(password, mock_user)
            
        except ValidationError as e:
            errors.extend(e.messages)
        
        return len(errors) == 0, errors
    
    @classmethod
    def validate_role_assignment(cls, role: str, branch=None, user_role=None) -> Tuple[bool, str]:
        """
        Validate role assignment based on business rules
        
        Args:
            role: Role to assign
            branch: Target branch (if applicable)
            user_role: Role of user making the assignment
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not role:
            return False, "Role is required"
        
        if role not in cls.VALID_ROLES:
            return False, f"Invalid role. Must be one of: {', '.join(cls.VALID_ROLES)}"
        
        # Business rule: learners, instructors, and admins need a branch
        if role in ['learner', 'instructor', 'admin'] and not branch:
            return False, f"{role.title()} users must be assigned to a branch"
        
        # Business rule: only superadmins can create other superadmins
        if role == 'superadmin' and user_role != 'superadmin':
            return False, "Only Super Admin users can create other Super Admin users"
        
        return True, ""
    
    @classmethod
    def validate_branch_assignment(cls, branch_name: str, role: str) -> Tuple[bool, str]:
        """
        Validate branch assignment
        
        Args:
            branch_name: Name of branch to validate
            role: User role for validation
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not branch_name and role in ['learner', 'instructor', 'admin']:
            return False, f"{role.title()} users must be assigned to a branch"
        
        if branch_name:
            from branches.models import Branch
            
            if not Branch.objects.filter(name=branch_name.strip()).exists():
                return False, f"Branch '{branch_name}' does not exist"
        
        return True, ""
    
    @classmethod
    def validate_phone_number(cls, phone: str) -> Tuple[bool, str]:
        """
        Validate phone number format
        
        Args:
            phone: Phone number to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not phone:
            return True, ""  # Phone is optional
        
        phone = phone.strip()
        
        if len(phone) < 10:
            return False, "Phone number must be at least 10 characters"
        
        if len(phone) > 20:
            return False, "Phone number must be 20 characters or less"
        
        if not cls.PHONE_PATTERN.match(phone):
            return False, "Invalid phone number format"
        
        return True, ""
    
    @classmethod
    def validate_postcode(cls, postcode: str) -> Tuple[bool, str]:
        """
        Validate postcode format
        
        Args:
            postcode: Postcode to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not postcode:
            return True, ""  # Postcode is optional
        
        postcode = postcode.strip().upper()
        
        if not cls.POSTCODE_PATTERN.match(postcode):
            return False, "Invalid postcode format"
        
        return True, ""
    
    @classmethod
    def validate_bulk_user_data(cls, user_data: Dict[str, Any], requesting_user=None) -> Dict[str, Any]:
        """
        Comprehensive validation for bulk user import data
        
        Args:
            user_data: Dictionary containing user data
            requesting_user: User making the request (for permission checks)
            
        Returns:
            Dictionary with validation results
        """
        result = {
            'is_valid': True,
            'errors': {},
            'warnings': [],
            'normalized_data': {}
        }
        
        # Normalize and validate each field
        
        # First Name
        first_name = user_data.get('first_name', '').strip()
        if not first_name:
            result['errors']['first_name'] = 'First name is required'
            result['is_valid'] = False
        elif len(first_name) > 150:
            result['errors']['first_name'] = 'First name must be 150 characters or less'
            result['is_valid'] = False
        else:
            result['normalized_data']['first_name'] = first_name
        
        # Last Name  
        last_name = user_data.get('last_name', '').strip()
        if not last_name:
            result['errors']['last_name'] = 'Last name is required'
            result['is_valid'] = False
        elif len(last_name) > 150:
            result['errors']['last_name'] = 'Last name must be 150 characters or less'
            result['is_valid'] = False
        else:
            result['normalized_data']['last_name'] = last_name
        
        # Email validation
        email = user_data.get('email', '').strip().lower()
        email_valid, email_error = cls.validate_email_format(email)
        if not email_valid:
            result['errors']['email'] = email_error
            result['is_valid'] = False
        else:
            result['normalized_data']['email'] = email
        
        # Username validation
        username = user_data.get('username', '').strip()
        username_valid, username_error = cls.validate_username_format(username)
        if not username_valid:
            result['errors']['username'] = username_error
            result['is_valid'] = False
        else:
            result['normalized_data']['username'] = username
        
        # Password validation
        password = user_data.get('password', '')
        password_valid, password_errors = cls.validate_password_strength(
            password, 
            {
                'username': username,
                'email': email,
                'first_name': first_name,
                'last_name': last_name
            }
        )
        if not password_valid:
            result['errors']['password'] = '; '.join(password_errors)
            result['is_valid'] = False
        else:
            result['normalized_data']['password'] = password
        
        # Role validation
        role = user_data.get('role', '').strip().lower()
        branch_name = user_data.get('branch', '').strip()
        
        role_valid, role_error = cls.validate_role_assignment(
            role, 
            branch_name,
            requesting_user.role if requesting_user else None
        )
        if not role_valid:
            result['errors']['role'] = role_error
            result['is_valid'] = False
        else:
            result['normalized_data']['role'] = role
        
        # Branch validation
        branch_valid, branch_error = cls.validate_branch_assignment(branch_name, role)
        if not branch_valid:
            result['errors']['branch'] = branch_error
            result['is_valid'] = False
        elif branch_name:
            result['normalized_data']['branch'] = branch_name
        
        # Phone validation (optional)
        phone = user_data.get('phone_number', '').strip()
        if phone:
            phone_valid, phone_error = cls.validate_phone_number(phone)
            if not phone_valid:
                result['errors']['phone_number'] = phone_error
                result['is_valid'] = False
            else:
                result['normalized_data']['phone_number'] = phone
        
        # Groups validation (optional)
        groups = user_data.get('groups', '').strip()
        if groups:
            # Validate group names exist
            from groups.models import BranchGroup
            group_names = [g.strip() for g in groups.split(',') if g.strip()]
            invalid_groups = []
            
            for group_name in group_names:
                if not BranchGroup.objects.filter(name=group_name).exists():
                    invalid_groups.append(group_name)
            
            if invalid_groups:
                result['errors']['groups'] = f"Invalid groups: {', '.join(invalid_groups)}"
                result['is_valid'] = False
            else:
                result['normalized_data']['groups'] = group_names
        
        # Additional business rule validations
        
        # Check for role-branch compatibility
        if role == 'superadmin' and branch_name:
            result['warnings'].append("Super Admin users typically don't need branch assignment")
        
        # Check for reasonable name formats
        if first_name and not re.match(r'^[a-zA-Z\s\'-]+$', first_name):
            result['warnings'].append("First name contains unusual characters")
        
        if last_name and not re.match(r'^[a-zA-Z\s\'-]+$', last_name):
            result['warnings'].append("Last name contains unusual characters")
        
        return result
    
    @classmethod
    def validate_bulk_import_file(cls, file_path: str, max_rows: int = 1000) -> Tuple[bool, str, List[Dict]]:
        """
        Validate bulk import file structure and content
        
        Args:
            file_path: Path to the file to validate
            max_rows: Maximum number of rows allowed
            
        Returns:
            Tuple of (is_valid, error_message, parsed_data)
        """
        try:
            import pandas as pd
            
            # Try to read the file
            try:
                df = pd.read_excel(file_path)
            except Exception as e:
                return False, f"Failed to read Excel file: {str(e)}", []
            
            # Check if file is too large
            if len(df) > max_rows:
                return False, f"File contains too many rows ({len(df)}). Maximum allowed: {max_rows}", []
            
            # Required columns
            required_columns = ['First Name', 'Last Name', 'Email', 'Username', 'Password', 'Role']
            optional_columns = ['Branch', 'Group(s)', 'Phone Number']
            
            # Check for required columns
            missing_columns = [col for col in required_columns if col not in df.columns]
            if missing_columns:
                return False, f"Missing required columns: {', '.join(missing_columns)}", []
            
            # Convert to list of dictionaries for processing
            data = []
            for index, row in df.iterrows():
                if index == 0 and 'sample' in str(row['First Name']).lower():
                    # Skip sample row
                    continue
                
                user_data = {
                    'first_name': str(row['First Name']).strip() if pd.notna(row['First Name']) else '',
                    'last_name': str(row['Last Name']).strip() if pd.notna(row['Last Name']) else '',
                    'email': str(row['Email']).strip().lower() if pd.notna(row['Email']) else '',
                    'username': str(row['Username']).strip() if pd.notna(row['Username']) else '',
                    'password': str(row['Password']).strip() if pd.notna(row['Password']) else '',
                    'role': str(row['Role']).strip().lower() if pd.notna(row['Role']) else '',
                    'branch': str(row['Branch']).strip() if pd.notna(row.get('Branch', '')) else '',
                    'groups': str(row['Group(s)']).strip() if pd.notna(row.get('Group(s)', '')) else '',
                    'phone_number': str(row['Phone Number']).strip() if pd.notna(row.get('Phone Number', '')) else '',
                    'row_number': index + 1
                }
                
                data.append(user_data)
            
            return True, "", data
            
        except ImportError:
            return False, "pandas library not available for Excel processing", []
        except Exception as e:
            logger.error(f"Bulk import file validation failed: {e}")
            return False, f"File validation error: {str(e)}", []

# Backward compatibility functions
def validate_email(email):
    """Backward compatibility function"""
    valid, error = ValidationService.validate_email_format(email)
    return valid

def validate_username(username):
    """Backward compatibility function"""
    valid, error = ValidationService.validate_username_format(username)
    return valid

def validate_user_data(user_data, requesting_user=None):
    """Backward compatibility function"""
    return ValidationService.validate_bulk_user_data(user_data, requesting_user)
