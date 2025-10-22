"""
RBAC Validators for LMS System
Implements allocation limits and conditional access validation as per RBAC v0.1 specification
"""

from django.core.exceptions import ValidationError, PermissionDenied
from django.db.models import Q, Count
from django.db import transaction
from business.models import Business, BusinessLimits
from branches.models import BranchUserLimits
from users.models import CustomUser
import logging

logger = logging.getLogger(__name__)

class AllocationValidator:
    """Validates user and branch creation against business/branch allocation limits"""
    
    @staticmethod
    @transaction.atomic
    def validate_user_creation(user, target_branch, target_role):
        """
        Validate if a user can be created based on allocation limits
        Args:
            user: User creating the new user
            target_branch: Branch where new user will be assigned (not required for Super Admin)
            target_role: Role of the new user being created
        """
        from users.models import CustomUser  # Import here to avoid circular imports
        errors = []
        
        # Super Admin users don't need a branch - they need a business
        if target_role == 'superadmin':
            # For Super Admin creation, we don't validate branch requirements
            # The business validation is handled separately in the form validation
            return errors
            
        # For all other roles, branch is required
        if not target_branch:
            errors.append("Target branch is required for user creation")
            return errors
            
        # Get business limits
        business = target_branch.business if hasattr(target_branch, 'business') else None
        if not business:
            errors.append("Branch must belong to a business")
            return errors
            
        # Refresh business data to ensure we have the latest limits
        business.refresh_from_db()
        
        # Get business limits using a fresh query instead of cached relationship
        from business.models import BusinessLimits
        try:
            business_limits = BusinessLimits.objects.get(business=business)
        except BusinessLimits.DoesNotExist:
            # Create default limits if they don't exist
            business_limits = BusinessLimits.objects.create(
                business=business,
                total_user_limit=500,
                branch_creation_limit=10,
                updated_by=user
            )
        
        # Check business-level user limits (only for non-Super Admin roles)
        current_business_users = CustomUser.objects.filter(
            branch__business=business
        ).count()
        
        logger.info(f"Business limit validation: Business={business.name}, "
                   f"Limit={business_limits.total_user_limit}, "
                   f"Current users={current_business_users}")
        
        if current_business_users >= business_limits.total_user_limit:
            errors.append(
                f"Business '{business.name}' has reached its user limit of {business_limits.total_user_limit}. "
                f"Current users: {current_business_users}"
            )
        
        # Check branch-level limits if they exist
        from branches.models import BranchUserLimits
        try:
            branch_limits = BranchUserLimits.objects.get(branch=target_branch)
            current_branch_users = CustomUser.objects.filter(branch=target_branch).count()
            
            logger.info(f"Branch limit validation: Branch={target_branch.name}, "
                       f"Limit={branch_limits.user_limit}, "
                       f"Current users={current_branch_users}")
            
            if current_branch_users >= branch_limits.user_limit:
                errors.append(
                    f"Branch '{target_branch.name}' has reached its user limit of {branch_limits.user_limit}. "
                    f"Current users: {current_branch_users}"
                )
        except BranchUserLimits.DoesNotExist:
            # No branch limits set, so no restriction
            logger.info(f"No branch limits set for {target_branch.name}")
        
        # Role-specific validation
        if user.role == 'superadmin':
            # Super Admin: CONDITIONAL (within business allocation)
            user_businesses = user.business_assignments.filter(is_active=True).values_list('business', flat=True)
            if business.id not in user_businesses:
                errors.append("Super Admin can only create users in businesses they are assigned to")
                
        elif user.role == 'admin':
            # Branch Admin: CONDITIONAL (within branch allocation)
            if user.branch != target_branch:
                errors.append("Branch Admin can only create users in their own branch")
                
        elif user.role == 'instructor':
            # Instructor: CONDITIONAL (learner accounts only)
            if target_role != 'learner':
                errors.append("Instructors can only create learner accounts")
            if user.branch != target_branch:
                errors.append("Instructors can only create users in their own branch")
        
        return errors
    
    @staticmethod
    def validate_superadmin_business_creation(user, target_business):
        """
        Validate if a Super Admin user can be created based on business assignment
        Args:
            user: User creating the Super Admin user
            target_business: Business where Super Admin will be assigned
        """
        from users.models import CustomUser  # Import here to avoid circular imports
        errors = []
        
        if not target_business:
            errors.append("Target business is required for Super Admin user creation")
            return errors
            
        # Only Global Admin can create Super Admin users
        if user.role != 'globaladmin':
            errors.append("Only Global Admin can create Super Admin users")
            return errors
        
        # Check business limits for Super Admin users
        business_limits = getattr(target_business, 'business_limits', None)
        if not business_limits:
            # Create default limits if they don't exist
            from business.models import BusinessLimits
            business_limits = BusinessLimits.objects.create(
                business=target_business,
                total_user_limit=500,
                branch_creation_limit=10,
                updated_by=user
            )
        
        # Check how many Super Admin users are already assigned to this business
        current_superadmin_users = CustomUser.objects.filter(
            business_assignments__business=target_business,
            business_assignments__is_active=True,
            role='superadmin'
        ).count()
        
        # Set a reasonable limit for Super Admin users per business (e.g., 10)
        superadmin_limit = 10
        if current_superadmin_users >= superadmin_limit:
            errors.append(
                f"Business '{target_business.name}' has reached its Super Admin limit of {superadmin_limit}. "
                f"Current Super Admin users: {current_superadmin_users}"
            )
        
        return errors
    
    @staticmethod
    def validate_branch_creation(user, target_business):
        """
        Validate if a branch can be created based on allocation limits
        Args:
            user: User creating the branch
            target_business: Business where branch will be created
        """
        errors = []
        
        if not target_business:
            errors.append("Target business is required for branch creation")
            return errors
            
        # Only Super Admin and Global Admin can create branches per CSV
        if user.role not in ['globaladmin', 'superadmin']:
            errors.append("Only Global Admin and Super Admin can create branches")
            return errors
            
        # Super Admin: CONDITIONAL (within subscription allocation limit)
        if user.role == 'superadmin':
            # Check if user is assigned to this business
            if not user.business_assignments.filter(business=target_business, is_active=True).exists():
                errors.append("Super Admin can only create branches in businesses they are assigned to")
                return errors
        
        # Check business branch limits
        business_limits = getattr(target_business, 'business_limits', None)
        if not business_limits:
            # Create default limits if they don't exist
            from business.models import BusinessLimits
            business_limits = BusinessLimits.objects.create(
                business=target_business,
                total_user_limit=500,
                branch_creation_limit=10,
                updated_by=user
            )
        
        current_branches = target_business.branches.filter(is_active=True).count()
        if current_branches >= business_limits.branch_creation_limit:
            errors.append(
                f"Business '{target_business.name}' has reached its branch limit of {business_limits.branch_creation_limit}. "
                f"Current branches: {current_branches}"
            )
        
        return errors

class ConditionalAccessValidator:
    """Validates conditional access permissions as per RBAC v0.1"""
    
    @staticmethod
    def validate_business_access(user, business):
        """Validate if user can access a specific business"""
        if user.role == 'globaladmin':
            return True  # FULL access
            
        if user.role == 'superadmin':
            # CONDITIONAL: Only businesses within their assignment
            return user.business_assignments.filter(business=business, is_active=True).exists()
            
        return False  # Other roles don't have business-level access
    
    @staticmethod
    def validate_branch_access(user, branch):
        """Validate if user can access a specific branch"""
        if user.role == 'globaladmin':
            return True  # FULL access
            
        if user.role == 'superadmin':
            # CONDITIONAL: Only branches within their businesses
            if hasattr(branch, 'business'):
                return user.business_assignments.filter(business=branch.business, is_active=True).exists()
            return False
            
        if user.role == 'admin':
            # SELF: Own branch only
            return user.branch == branch
            
        if user.role in ['instructor', 'learner']:
            # Limited access within their branch
            return user.branch == branch
            
        return False
    
    @staticmethod
    def validate_user_access(user, target_user, action):
        """Validate if user can perform action on target user"""
        if user.role == 'globaladmin':
            return True  # FULL access
            
        if user.role == 'superadmin':
            # CONDITIONAL: Users within their business
            if hasattr(target_user, 'branch') and hasattr(target_user.branch, 'business'):
                can_access = user.business_assignments.filter(
                    business=target_user.branch.business, 
                    is_active=True
                ).exists()
                
                # Additional restriction: cannot delete other admins
                if action == 'delete' and target_user.role in ['admin', 'superadmin', 'globaladmin']:
                    return False
                    
                return can_access
            return False
            
        if user.role == 'admin':
            # CONDITIONAL: Users within their branch
            can_access = user.branch == target_user.branch
            
            # Additional restriction: cannot delete other admins/super admin
            if action == 'delete' and target_user.role in ['admin', 'superadmin', 'globaladmin']:
                return False
                
            return can_access
            
        if user.role == 'instructor':
            # CONDITIONAL: Assigned learners only
            if action in ['view', 'edit']:
                return target_user.assigned_instructor == user or target_user.role == 'learner'
            return False  # Instructors cannot delete users
            
        if user.role == 'learner':
            # SELF: Own profile only
            return user == target_user and action in ['view', 'edit']
            
        return False

class RBACValidator:
    """Main RBAC validator combining all validation rules"""
    
    def __init__(self):
        self.allocation_validator = AllocationValidator()
        self.conditional_access_validator = ConditionalAccessValidator()
    
    def validate_action(self, user, action, resource_type, resource=None, **kwargs):
        """
        Main validation method for any RBAC action
        Args:
            user: User performing the action
            action: Action being performed (create, view, edit, delete)
            resource_type: Type of resource (user, course, business, branch, etc.)
            resource: Specific resource instance (optional)
            **kwargs: Additional context for validation
        """
        errors = []
        
        try:
            if resource_type == 'user' and action == 'create':
                target_branch = kwargs.get('target_branch')
                target_role = kwargs.get('target_role')
                target_business = kwargs.get('target_business')
                
                # Special handling for Super Admin creation
                if target_role == 'superadmin':
                    errors.extend(self.allocation_validator.validate_superadmin_business_creation(user, target_business))
                else:
                    # For all other roles, use the regular validation
                    errors.extend(self.allocation_validator.validate_user_creation(user, target_branch, target_role))
                
            elif resource_type == 'branch' and action == 'create':
                target_business = kwargs.get('target_business')
                errors.extend(self.allocation_validator.validate_branch_creation(user, target_business))
                
            elif resource_type == 'business':
                if not self.conditional_access_validator.validate_business_access(user, resource):
                    errors.append(f"Access denied to business: insufficient permissions")
                    
            elif resource_type == 'branch':
                if not self.conditional_access_validator.validate_branch_access(user, resource):
                    errors.append(f"Access denied to branch: insufficient permissions")
                    
            elif resource_type == 'user' and resource:
                if not self.conditional_access_validator.validate_user_access(user, resource, action):
                    errors.append(f"Access denied to user: insufficient permissions for {action}")
                    
        except Exception as e:
            logger.error(f"RBAC validation error: {str(e)}")
            errors.append("Internal validation error")
        
        return errors
    
    def require_permission(self, user, action, resource_type, resource=None, **kwargs):
        """
        Decorator-style validation that raises PermissionDenied if validation fails
        """
        errors = self.validate_action(user, action, resource_type, resource, **kwargs)
        if errors:
            raise PermissionDenied("; ".join(errors))
        return True

# Global validator instance
rbac_validator = RBACValidator() 