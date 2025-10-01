"""
Utility functions for handling default business and branch assignments
"""
from django.db import transaction
from business.models import Business, BusinessUserAssignment, BusinessLimits
from branches.models import Branch
import logging

logger = logging.getLogger(__name__)

class DefaultAssignmentManager:
    """
    Manages default business and branch assignments for users
    """
    
    @staticmethod
    def is_default_business(business):
        """
        Check if a business is the default business (reserved for global admin only)
        """
        if not business:
            return False
        return business.name == "Default Business"
    
    @staticmethod
    def is_default_branch(branch):
        """
        Check if a branch is a default branch (reserved for global admin only)
        """
        if not branch:
            return False
        # Default branches have the pattern "{business_name} - Default Branch"
        return branch.name.endswith(" - Default Branch")
    
    @staticmethod
    def get_default_business():
        """
        Get the default business (if it exists)
        """
        return Business.objects.filter(name="Default Business").first()
    
    @staticmethod
    def get_default_branch():
        """
        Get the default branch (if it exists)
        """
        default_business = DefaultAssignmentManager.get_default_business()
        if default_business:
            return default_business.get_default_branch()
        return None
    
    @staticmethod
    def get_non_default_branches():
        """
        Get all branches that are NOT default branches (safe for non-global admin users)
        """
        return Branch.objects.exclude(name__endswith=" - Default Branch").filter(is_active=True)
    
    @staticmethod
    def get_non_default_businesses():
        """
        Get all businesses that are NOT the default business (safe for non-global admin users)
        """
        return Business.objects.exclude(name="Default Business").filter(is_active=True)
    
    @staticmethod
    def can_user_access_default_business(user):
        """
        Check if a user can be assigned to the default business
        Only global admin users are allowed
        """
        return user and user.role == 'globaladmin'
    
    @staticmethod
    def can_user_access_default_branch(user):
        """
        Check if a user can be assigned to a default branch
        Only global admin users are allowed
        """
        return user and user.role == 'globaladmin'
    
    @staticmethod
    def get_or_create_default_business():
        """
        Get or create the default business for users without specific assignments
        """
        default_business_name = "Default Business"
        
        try:
            default_business, created = Business.objects.get_or_create(
                name=default_business_name,
                defaults={
                    'description': "Default business for users without specific business assignment",
                    'is_active': True,
                    'address_line1': "Not Specified",
                    'city': "Not Specified", 
                    'country': "United Kingdom"
                }
            )
            
            if created:
                logger.info(f"Created default business: {default_business.name}")
                
                # Create business limits for the default business
                BusinessLimits.objects.get_or_create(
                    business=default_business,
                    defaults={
                        'total_user_limit': 1000,  # Higher limit for default business
                        'branch_creation_limit': 50,
                    }
                )
            
            return default_business
            
        except Exception as e:
            logger.error(f"Error creating default business: {str(e)}")
            raise
    
    @staticmethod
    def get_or_create_default_branch(business=None):
        """
        Get or create the default branch for a business
        """
        if not business:
            business = DefaultAssignmentManager.get_or_create_default_business()
        
        try:
            # Use the business's built-in method for default branch
            default_branch = business.get_default_branch()
            if not default_branch:
                default_branch = business.create_default_branch()
                logger.info(f"Created default branch: {default_branch.name}")
            
            return default_branch
            
        except Exception as e:
            logger.error(f"Error creating default branch: {str(e)}")
            raise
    
    @staticmethod
    def get_safe_branch_for_user(user):
        """
        Get a safe branch for user assignment (excludes default branch for non-global admins)
        """
        if DefaultAssignmentManager.can_user_access_default_branch(user):
            # Global admin can access any branch, including default
            return Branch.objects.filter(is_active=True).first()
        else:
            # Non-global admin users can only access non-default branches
            non_default_branches = DefaultAssignmentManager.get_non_default_branches()
            return non_default_branches.first() if non_default_branches.exists() else None
    
    @staticmethod
    def get_safe_business_for_user(user):
        """
        Get a safe business for user assignment (excludes default business for non-global admins)
        """
        if DefaultAssignmentManager.can_user_access_default_business(user):
            # Global admin can access any business, including default
            return Business.objects.filter(is_active=True).first()
        else:
            # Non-global admin users can only access non-default businesses
            non_default_businesses = DefaultAssignmentManager.get_non_default_businesses()
            return non_default_businesses.first() if non_default_businesses.exists() else None
    
    @staticmethod
    def assign_user_to_default_business(user):
        """
        Assign a user to the default business (only allowed for global admin)
        """
        if not DefaultAssignmentManager.can_user_access_default_business(user):
            raise ValueError(f"Only Global Admin users can be assigned to the default business. User {user.username} has role: {user.role}")
        
        try:
            with transaction.atomic():
                default_business = DefaultAssignmentManager.get_or_create_default_business()
                
                # Check if user is already assigned to this business
                existing_assignment = BusinessUserAssignment.objects.filter(
                    user=user,
                    business=default_business,
                    is_active=True
                ).first()
                
                if not existing_assignment:
                    assignment = BusinessUserAssignment.objects.create(
                        business=default_business,
                        user=user,
                        is_active=True
                    )
                    logger.info(f"Assigned Super Admin {user.username} to default business")
                    return assignment
                else:
                    logger.info(f"Super Admin {user.username} already assigned to default business")
                    return existing_assignment
                    
        except Exception as e:
            logger.error(f"Error assigning user to default business: {str(e)}")
            raise
    
    @staticmethod
    def assign_user_to_default_branch(user):
        """
        Assign a user to the default branch
        """
        if user.role not in ['admin', 'instructor', 'learner']:
            raise ValueError("Only Admin, Instructor, and Learner users can be assigned to branches")
        
        try:
            with transaction.atomic():
                default_branch = DefaultAssignmentManager.get_or_create_default_branch()
                
                if not user.branch:
                    user.branch = default_branch
                    user.save()
                    logger.info(f"Assigned {user.role} {user.username} to default branch")
                else:
                    logger.info(f"{user.role} {user.username} already has branch assignment: {user.branch.name}")
                    
                return user.branch
                    
        except Exception as e:
            logger.error(f"Error assigning user to default branch: {str(e)}")
            raise
    
    @staticmethod
    def ensure_proper_user_assignments(user):
        """
        Ensure a user has proper business/branch assignments based on their role
        """
        try:
            with transaction.atomic():
                if user.role == 'globaladmin':
                    # Global admins should not have branch assignments
                    if user.branch:
                        user.branch = None
                        user.save()
                        logger.info(f"Removed branch assignment from Global Admin {user.username}")
                
                elif user.role == 'superadmin':
                    # Super admins need business assignment
                    if not user.business_assignments.filter(is_active=True).exists():
                        DefaultAssignmentManager.assign_user_to_default_business(user)
                
                elif user.role in ['admin', 'instructor', 'learner']:
                    # These roles need branch assignment
                    if not user.branch:
                        DefaultAssignmentManager.assign_user_to_default_branch(user)
                
                logger.info(f"Ensured proper assignments for {user.role} {user.username}")
                
        except Exception as e:
            logger.error(f"Error ensuring user assignments: {str(e)}")
            raise
    
    @staticmethod
    def validate_user_assignments(user):
        """
        Validate that a user has the correct assignments for their role
        """
        validation_errors = []
        
        if user.role == 'globaladmin':
            if user.branch:
                validation_errors.append("Global Admin users should not have branch assignments")
        
        elif user.role == 'superadmin':
            if not user.business_assignments.filter(is_active=True).exists():
                validation_errors.append("Super Admin users must be assigned to at least one business")
        
        elif user.role in ['admin', 'instructor', 'learner']:
            if not user.branch:
                validation_errors.append(f"{user.get_role_display()} users must be assigned to a branch")
        
        return validation_errors
    
    @staticmethod
    def get_available_assignments_for_user(current_user):
        """
        Get available business and branch assignments based on the current user's role
        """
        available_businesses = []
        available_branches = []
        
        if current_user.role == 'globaladmin':
            # Global admins can see all businesses and branches
            available_businesses = Business.objects.filter(is_active=True)
            available_branches = Branch.objects.filter(is_active=True)
        
        elif current_user.role == 'superadmin':
            # Super admins can see their assigned businesses and related branches
            assigned_businesses = current_user.business_assignments.filter(
                is_active=True
            ).values_list('business', flat=True)
            
            available_businesses = Business.objects.filter(
                id__in=assigned_businesses,
                is_active=True
            )
            available_branches = Branch.objects.filter(
                business__in=assigned_businesses,
                is_active=True
            )
        
        elif current_user.role in ['admin', 'instructor']:
            # Admins and instructors can only see their own branch
            if current_user.branch:
                available_businesses = [current_user.branch.business] if current_user.branch.business else []
                available_branches = [current_user.branch]
            else:
                available_businesses = []
                available_branches = []
        
        return {
            'businesses': available_businesses,
            'branches': available_branches
        }

# Convenience functions
def ensure_default_structures():
    """Ensure default business and branch structures exist"""
    DefaultAssignmentManager.get_or_create_default_business()
    DefaultAssignmentManager.get_or_create_default_branch()

def assign_user_to_defaults(user):
    """Assign user to appropriate default structures based on role"""
    DefaultAssignmentManager.ensure_proper_user_assignments(user)
