"""
Role Management Utilities

This module provides utility functions for role management including
permission checking, caching, and role validation.
"""

from django.core.cache import cache
from django.contrib.auth import get_user_model
from django.db.models import Q, Prefetch
from django.utils import timezone
from functools import wraps
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect
from django.contrib import messages
from .models import Role, RoleCapability, UserRole, RoleAuditLog
import logging

logger = logging.getLogger(__name__)
User = get_user_model()

def safe_cache_operation(operation, *args, **kwargs):
    """
    Safely execute cache operations with proper error handling for Redis connection issues.
    Returns tuple (success, result) where success is boolean and result is the operation result or None.
    """
    try:
        result = operation(*args, **kwargs)
        return True, result
    except Exception as e:
        # Check if this is a Redis connection error
        error_str = str(e).lower()
        redis_error_indicators = [
            'connecting to', 'connection refused', 'connection error',
            'redis', 'timeout', 'connection timed out', 'error 111',
            'connectionerror', 'connecttimeouterror', 'redisconnectionerror',
            'unable to connect', 'failed to connect', 'no route to host'
        ]
        
        if any(indicator in error_str for indicator in redis_error_indicators):
            logger.warning(f"Redis connection issue during cache operation: {str(e)}")
        else:
            logger.error(f"Unexpected cache error: {str(e)}")
        
        return False, None

class PermissionManager:
    """Centralized permission management system"""
    
    @staticmethod
    def get_user_capabilities(user, use_cache=True, session_id=None):
        """Get all capabilities for a user with enhanced Session and integrity validation"""
        if not user or not user.is_authenticated:
            return []
        
        import hashlib
        import json
        
        # Create session-aware cache keys to prevent session fixation
        session_suffix = f"_{hashlib.md5(str(session_id).encode()).hexdigest()[:8]}" if session_id else ""
        cache_key = f"user_capabilities_{user.pk}{session_suffix}"
        cache_version_key = f"user_capabilities_version_{user.pk}{session_suffix}"
        cache_integrity_key = f"user_capabilities_integrity_{user.pk}{session_suffix}"
        
        capabilities = []
        
        if use_cache:
            # Try to get cached capabilities with enhanced validation
            success, cached_data = safe_cache_operation(
                cache.get_many, 
                [cache_key, cache_version_key, cache_integrity_key]
            )
            
            if success and cached_data:
                capabilities = cached_data.get(cache_key)
                cache_version = cached_data.get(cache_version_key)
                cache_integrity = cached_data.get(cache_integrity_key)
                
                # Enhanced cache integrity validation
                if capabilities is not None and cache_version is not None and cache_integrity is not None:
                    from core.utils.type_guards import validate_cache_capabilities
                    
                    # Use type-safe cache validation
                    validated_capabilities = validate_cache_capabilities(capabilities)
                    if validated_capabilities is None:
                        logger.warning(f"Cache validation failed for user {user.pk}")
                        PermissionManager._clear_corrupted_cache(user, session_suffix)
                    # Integrity checksum validation
                    elif not PermissionManager._validate_cache_integrity(validated_capabilities, cache_version, cache_integrity):
                        logger.warning(f"Cache integrity validation failed for user {user.pk}: checksum mismatch")
                        PermissionManager._clear_corrupted_cache(user, session_suffix)
                    else:
                        # Cache is valid, return capabilities
                        return capabilities
            elif not success:
                logger.info(f"Cache unavailable for user {user.pk}, proceeding without cache")
        
        # Fresh lookup - build capabilities from scratch
        capabilities = set()
        
        # Get capabilities from primary role with validation
        if hasattr(user, 'role') and user.role:
            try:
                primary_role_capabilities = Role.objects.get_default_capabilities(user.role)
                if isinstance(primary_role_capabilities, list):
                    # Validate each capability
                    validated_caps = [
                        cap for cap in primary_role_capabilities 
                        if isinstance(cap, str) and cap.strip() and len(cap) <= 100
                    ]
                    capabilities.update(validated_caps)
                else:
                    logger.error(f"Invalid primary role capabilities type for user {user.pk}: {type(primary_role_capabilities)}")
            except Exception as e:
                logger.error(f"Error getting primary role capabilities for user {user.pk}: {str(e)}")
        
        # Get capabilities from assigned roles with enhanced validation
        try:
            user_roles = UserRole.objects.filter(
                user=user, 
                is_active=True,
                role__is_active=True
            ).select_related('role').prefetch_related('role__capabilities')
            
            for user_role in user_roles:
                # Skip expired roles
                if user_role.is_expired:
                    continue
                
                # Validate role assignment integrity
                if not user_role.role or not user_role.role.is_active:
                    logger.warning(f"Inactive role found in user {user.pk} assignments: {user_role.role}")
                    continue
                    
                role_capabilities = user_role.role.get_capabilities()
                if isinstance(role_capabilities, list):
                    # Validate each capability from role
                    validated_caps = [
                        cap for cap in role_capabilities 
                        if isinstance(cap, str) and cap.strip() and len(cap) <= 100
                    ]
                    capabilities.update(validated_caps)
                else:
                    logger.error(f"Invalid role capabilities type for role {user_role.role.pk}: {type(role_capabilities)}")
        except Exception as e:
            logger.error(f"Error getting assigned role capabilities for user {user.pk}: {str(e)}")
        
        # Convert to validated list
        capabilities = list(capabilities)
        
        # Final validation before caching
        if len(capabilities) > 500:
            logger.error(f"User {user.pk} has excessive capabilities ({len(capabilities)}), truncating to prevent abuse")
            capabilities = capabilities[:500]
        
        # Cache with enhanced Session
        if use_cache and capabilities:
            cache_version = timezone.now().timestamp()
            cache_integrity = PermissionManager._generate_cache_integrity(capabilities, cache_version)
            
            cache_data = {
                cache_key: capabilities,
                cache_version_key: cache_version,
                cache_integrity_key: cache_integrity
            }
            
            # Use shorter cache duration for Session-sensitive data
            success, _ = safe_cache_operation(cache.set_many, cache_data, 1800)  # 30 minutes instead of 1 hour
            if not success:
                logger.info(f"Unable to cache capabilities for user {user.pk}, continuing without cache")
        
        return capabilities
    
    @staticmethod
    def _validate_cache_integrity(capabilities, cache_version, cached_integrity):
        """Validate cache integrity using checksums"""
        expected_integrity = PermissionManager._generate_cache_integrity(capabilities, cache_version)
        return expected_integrity == cached_integrity
    
    @staticmethod 
    def _generate_cache_integrity(capabilities, cache_version):
        """Generate integrity checksum for cache validation"""
        import hashlib
        import json
        
        # Create deterministic string for hashing
        content = json.dumps({
            'capabilities': sorted(capabilities),  # Sort for consistency
            'version': cache_version,
            'salt': 'lms_role_Session_2024'  # Add salt to prevent rainbow table attacks
        }, sort_keys=True)
        
        return hashlib.sha256(content.encode()).hexdigest()
    
    @staticmethod
    def _clear_corrupted_cache(user, session_suffix=""):
        """Clear corrupted cache entries for a user"""
        cache_keys = [
            f"user_capabilities_{user.pk}{session_suffix}",
            f"user_capabilities_version_{user.pk}{session_suffix}",
            f"user_capabilities_integrity_{user.pk}{session_suffix}"
        ]
        
        success, _ = safe_cache_operation(cache.delete_many, cache_keys)
        if not success:
            for key in cache_keys:
                safe_cache_operation(cache.delete, key)
    
    @staticmethod
    def user_has_capability(user, capability):
        """Check if user has a specific capability"""
        if not user or not user.is_authenticated:
            return False
        
        # Superuser and global admin always have all capabilities
        if user.is_superuser or (hasattr(user, 'role') and user.role in ['globaladmin', 'superadmin']):
            return True
        
        user_capabilities = PermissionManager.get_user_capabilities(user)
        result = capability in user_capabilities
        
        # If capability not found and cache enabled, try fresh lookup once
        if not result:
            fresh_capabilities = PermissionManager.get_user_capabilities(user, use_cache=False)
            result = capability in fresh_capabilities
            # If fresh lookup finds the capability, clear and refresh cache
            if result:
                PermissionManager.clear_user_cache(user)
                PermissionManager.get_user_capabilities(user)  # Rebuild cache
        
        return result
    
    @staticmethod
    def user_has_any_capability(user, capabilities):
        """Check if user has any of the specified capabilities"""
        if not user or not user.is_authenticated:
            return False
        
        if user.is_superuser or (hasattr(user, 'role') and user.role in ['globaladmin', 'superadmin']):
            return True
        
        user_capabilities = PermissionManager.get_user_capabilities(user)
        result = any(cap in user_capabilities for cap in capabilities)
        
        # If no capabilities found and cache enabled, try fresh lookup once
        if not result:
            fresh_capabilities = PermissionManager.get_user_capabilities(user, use_cache=False)
            result = any(cap in fresh_capabilities for cap in capabilities)
            # If fresh lookup finds capabilities, clear and refresh cache
            if result:
                PermissionManager.clear_user_cache(user)
                PermissionManager.get_user_capabilities(user)  # Rebuild cache
        
        return result
    
    @staticmethod
    def user_has_all_capabilities(user, capabilities):
        """Check if user has all of the specified capabilities"""
        if not user or not user.is_authenticated:
            return False
        
        if user.is_superuser or (hasattr(user, 'role') and user.role in ['globaladmin', 'superadmin']):
            return True
        
        user_capabilities = PermissionManager.get_user_capabilities(user)
        result = all(cap in user_capabilities for cap in capabilities)
        
        # If not all capabilities found and cache enabled, try fresh lookup once
        if not result:
            fresh_capabilities = PermissionManager.get_user_capabilities(user, use_cache=False)
            result = all(cap in fresh_capabilities for cap in capabilities)
            # If fresh lookup finds all capabilities, clear and refresh cache
            if result:
                PermissionManager.clear_user_cache(user)
                PermissionManager.get_user_capabilities(user)  # Rebuild cache
        
        return result
    
    @staticmethod
    def get_user_highest_role(user):
        """Get the highest hierarchical role for a user"""
        if not user or not user.is_authenticated:
            return None
        
        # Start with primary role
        highest_role = None
        highest_level = -1
        
        if hasattr(user, 'role') and user.role:
            try:
                primary_role = Role.objects.get(name=user.role)
                highest_role = primary_role
                highest_level = primary_role.hierarchy_level
            except Role.DoesNotExist:
                pass
        
        # Check assigned roles
        user_roles = UserRole.objects.filter(
            user=user, 
            is_active=True,
            role__is_active=True
        ).select_related('role')
        
        for user_role in user_roles:
            if user_role.is_expired:
                continue
                
            if user_role.role.hierarchy_level > highest_level:
                highest_role = user_role.role
                highest_level = user_role.role.hierarchy_level
        
        return highest_role
    
    @staticmethod
    def can_user_manage_role(user, target_role):
        """Check if user can manage (create/edit/delete) a specific role"""
        if not user or not user.is_authenticated:
            return False
        
        # Superuser can manage all roles
        if user.is_superuser:
            return True
        
        user_highest_role = PermissionManager.get_user_highest_role(user)
        if not user_highest_role:
            return False
        
        # Can only manage roles of lower hierarchy
        if isinstance(target_role, str):
            target_role_level = Role.ROLE_HIERARCHY.get(target_role, 0)
            target_role_name = target_role
        else:
            target_role_level = target_role.hierarchy_level
            target_role_name = target_role.name
        
        # Additional business rules for role management restrictions
        # Super admin users cannot manage globaladmin roles
        if user_highest_role.name == 'superadmin' and target_role_name == 'globaladmin':
            return False
        
        # Admin users cannot manage superadmin or globaladmin roles
        if user_highest_role.name == 'admin' and target_role_name in ['superadmin', 'globaladmin', 'admin']:
            return False
        
        # Admin users can only create and manage custom roles
        if user_highest_role.name == 'admin' and not (
            target_role_name == 'custom' or 
            (isinstance(target_role, Role) and target_role.name == 'custom')
        ):
            return False
        
        # Must have manage_roles capability and higher hierarchy
        return (
            PermissionManager.user_has_capability(user, 'manage_roles') and
            user_highest_role.hierarchy_level > target_role_level
        )
    
    @staticmethod
    def can_user_assign_role(user, target_role, target_user):
        """Check if user can assign a role to another user with enhanced Session"""
        if not user or not user.is_authenticated:
            return False
        
        # Must be able to manage the role
        if not PermissionManager.can_user_manage_role(user, target_role):
            return False
        
        # Additional checks for specific role assignments
        if isinstance(target_role, str):
            role_name = target_role
        else:
            role_name = target_role.name
        
        # Get user's highest role for hierarchy validation
        user_highest_role = PermissionManager.get_user_highest_role(user)
        if not user_highest_role:
            return False
        
        # Enhanced hierarchy check: assigner must have higher role than target role
        # Exception: global admin can assign global admin roles (same level)
        if isinstance(target_role, str):
            target_role_level = Role.ROLE_HIERARCHY.get(target_role, 0)
        else:
            target_role_level = target_role.hierarchy_level
            
        # Allow global admin to assign global admin roles (same hierarchy level)
        if user_highest_role.hierarchy_level < target_role_level:
            return False
        elif user_highest_role.hierarchy_level == target_role_level:
            # Only allow same-level assignment if both are global admin
            if not (user_highest_role.name == 'globaladmin' and role_name == 'globaladmin'):
                return False
        
        # Only globaladmin can assign globaladmin roles
        if role_name == 'globaladmin':
            if not (user.role == 'globaladmin' or 
                    UserRole.objects.filter(
                        user=user, 
                        role__name='globaladmin', 
                        is_active=True
                    ).exists()):
                return False
        
        # Only superadmin or globaladmin can assign superadmin roles
        if role_name == 'superadmin':
            if not (user.role in ['superadmin', 'globaladmin'] or 
                    UserRole.objects.filter(
                        user=user, 
                        role__name__in=['superadmin', 'globaladmin'], 
                        is_active=True
                    ).exists()):
                return False
        
        # Super admin users cannot assign globaladmin roles
        if role_name == 'globaladmin' and user.role == 'superadmin':
            return False
        
        # Super admin users cannot assign ANY role to global admin users
        if user.role == 'superadmin' and target_user and target_user.role == 'globaladmin':
            return False
        
        # Admin users cannot assign superadmin, globaladmin, or admin roles
        if role_name in ['superadmin', 'globaladmin', 'admin'] and user.role == 'admin':
            return False
        
        # Admin users can only assign custom roles to users within their branch
        if user.role == 'admin':
            # Ensure target user is in the same branch as the admin
            if not (hasattr(user, 'branch') and hasattr(target_user, 'branch') and user.branch == target_user.branch):
                return False
            # Admin users can only assign custom roles
            if not (role_name == 'custom' or 
                    (hasattr(target_role, 'name') and target_role.name == 'custom')):
                return False
        
        # Prevent privilege escalation: users cannot assign roles higher than their own
        if role_name in ['superadmin', 'admin'] and user.role not in ['superadmin', 'globaladmin']:
            # Check if user has superadmin or globaladmin role assignment
            has_higher_role = UserRole.objects.filter(
                user=user,
                role__name__in=['superadmin', 'globaladmin'],
                is_active=True
            ).exists()
            if not has_higher_role:
                return False
        
        # Branch-based restrictions with enhanced validation
        if hasattr(user, 'branch') and hasattr(target_user, 'branch'):
            # Non-superadmins can only assign roles within their branch
            if user.branch_id != target_user.branch_id:
                # Allow only if user has superadmin role (primary or assigned)
                if user.role != 'superadmin':
                    has_superadmin_role = UserRole.objects.filter(
                        user=user,
                        role__name='superadmin',
                        is_active=True
                    ).exists()
                    if not has_superadmin_role:
                        return False
        
        # Prevent self-assignment unless user is superadmin
        if user.pk == target_user.pk:
            if not (user.role == 'superadmin' or 
                    UserRole.objects.filter(
                        user=user, 
                        role__name='superadmin', 
                        is_active=True
                    ).exists()):
                return False
        
        # Check for conflicting role assignments
        if target_user and role_name:
            conflicting_roles = {
                'superadmin': ['admin', 'instructor', 'learner'],
                'admin': ['superadmin', 'learner'],
                'instructor': ['superadmin'],
                'learner': ['superadmin', 'admin']
            }
            
            if role_name in conflicting_roles:
                existing_conflicting = UserRole.objects.filter(
                    user=target_user,
                    role__name__in=conflicting_roles[role_name],
                    is_active=True
                ).exists()
                
                if existing_conflicting:
                    # This will need to be handled by deactivating conflicting roles
                    pass  # Allow the assignment, conflicts will be resolved in UserRole.save()
        
        return True
    
    @staticmethod
    def clear_user_cache(user, session_id=None):
        """Clear all cached data for a user with enhanced session support"""
        if user and user.pk:
            import hashlib
            
            # Clear both session-specific and general caches
            cache_keys = [
                f"user_capabilities_{user.pk}",
                f"user_capabilities_version_{user.pk}",
                f"user_session_capabilities_{user.pk}"
            ]
            
            # Add session-specific cache keys if session provided
            if session_id:
                session_suffix = f"_{hashlib.md5(str(session_id).encode()).hexdigest()[:8]}"
                cache_keys.extend([
                    f"user_capabilities_{user.pk}{session_suffix}",
                    f"user_capabilities_version_{user.pk}{session_suffix}",
                    f"user_capabilities_integrity_{user.pk}{session_suffix}"
                ])
            else:
                # If no specific session, try to clear common session patterns
                import re
                try:
                    from django.core.cache import cache
                    # Get all cache keys matching user pattern (if supported by cache backend)
                    if hasattr(cache, 'keys'):
                        pattern = f"user_capabilities_{user.pk}_*"
                        matching_keys = [key for key in cache.keys(pattern) if re.match(f"user_capabilities_{user.pk}_[a-f0-9]{{8}}", key)]
                        cache_keys.extend(matching_keys)
                except:
                    pass  # Some cache backends don't support key listing
            
            # Use safe cache operations
            success, _ = safe_cache_operation(cache.delete_many, cache_keys)
            if not success:
                # Fallback to individual deletions
                for key in cache_keys:
                    safe_cache_operation(cache.delete, key)
    
    @staticmethod
    def clear_role_cache(role):
        """Clear all cached data for a role with safe operations"""
        if role and role.pk:
            # Clear role capabilities cache
            success, _ = safe_cache_operation(cache.delete, f"role_capabilities_{role.pk}")
            
            # Also clear cache for all users with this role
            try:
                user_roles = UserRole.objects.filter(role=role).values_list('user_id', flat=True)
                user_cache_keys = []
                for user_id in user_roles:
                    user_cache_keys.extend([
                        f"user_capabilities_{user_id}",
                        f"user_capabilities_version_{user_id}"
                    ])
                
                if user_cache_keys:
                    success, _ = safe_cache_operation(cache.delete_many, user_cache_keys)
                    if not success:
                        # Try individual deletions as fallback
                        for key in user_cache_keys:
                            safe_cache_operation(cache.delete, key)
            except Exception as e:
                logger.error(f"Error clearing user caches for role {role.pk}: {str(e)}")

class RoleValidator:
    """Role validation utilities"""
    
    @staticmethod
    def validate_role_assignment(user, role, target_user, assigned_by=None):
        """Validate if a role can be assigned to a user"""
        errors = []
        
        # Check if user exists and is active
        if not target_user or not target_user.is_active:
            errors.append("Target user does not exist or is inactive")
        
        # Check if role exists and is active
        if not role or not role.is_active:
            errors.append("Role does not exist or is inactive")
        
        # Check if assignment is allowed
        if assigned_by and not PermissionManager.can_user_assign_role(assigned_by, role, target_user):
            errors.append("You do not have permission to assign this role")
        
        # Check for conflicts
        if target_user and role:
            existing_role = UserRole.objects.filter(user=target_user, role=role, is_active=True).first()
            if existing_role:
                errors.append("User already has this role assigned")
        
        return errors
    
    @staticmethod
    def validate_role_creation(role_data, created_by=None):
        """Validate role creation data"""
        return RoleValidator.validate_role_data(role_data, created_by, exclude_role_id=None)
    
    @staticmethod
    def validate_role_editing(role_data, edited_by=None, exclude_role_id=None):
        """Validate role editing data"""
        return RoleValidator.validate_role_data(role_data, edited_by, exclude_role_id=exclude_role_id)
    
    @staticmethod
    def validate_role_data(role_data, user=None, exclude_role_id=None):
        """Validate role data for both creation and editing"""
        errors = []
        
        name = role_data.get('name')
        custom_name = role_data.get('custom_name')
        
        # Check required fields
        if not name:
            errors.append("Role name is required")
        
        if name == 'custom' and not custom_name:
            errors.append("Custom name is required for custom roles")
        
        # Check permissions
        if user and not PermissionManager.can_user_manage_role(user, name):
            errors.append("You do not have permission to manage this type of role")
        
        # Enhanced input sanitization and validation
        if custom_name:
            import re
            import html
            from django.utils.html import strip_tags
            
            # Sanitize custom name
            original_custom_name = custom_name
            custom_name = strip_tags(html.unescape(custom_name))
            custom_name = re.sub(r'[<>"\'\(\)\[\]{}\\;]+', '', custom_name)
            custom_name = custom_name.strip()[:50]
            
            # Update the role_data if sanitization changed the input
            if custom_name != original_custom_name:
                role_data['custom_name'] = custom_name
                errors.append("Custom name contained invalid characters and was sanitized")
            
            # Enhanced pattern validation
            if not re.match(r'^[a-zA-Z0-9\s\-_]+$', custom_name):
                errors.append("Custom name can only contain letters, numbers, spaces, hyphens, and underscores")
            
            if len(custom_name) < 3:
                errors.append("Custom name must be at least 3 characters long")
            
            # Enhanced forbidden pattern detection
            forbidden_patterns = [
                r'(?i)\b(global|admin|super|system|root|administrator)\b',
                r'(?i)\b(select|insert|update|delete|drop|union|exec|script)\b',
                r'(?i)\b(script|javascript|vbscript|onload|onerror)\b',
                r'(?i)\b(cmd|bash|sh|powershell|eval)\b',
                r'\.\./|\.\.\\',
            ]
            
            for pattern in forbidden_patterns:
                if re.search(pattern, custom_name):
                    errors.append("Custom name contains forbidden words or dangerous patterns")
                    break
            
            # Check for system role variations
            normalized_custom = re.sub(r'\s+', '', custom_name.lower())
            dangerous_variations = [
                'globaladmin', 'global_admin', 'global-admin', 'globadmin',
                'superadmin', 'super_admin', 'super-admin', 'supadmin',
                'administrator', 'admin_user', 'admin-user', 'sysadmin',
                'system_admin', 'system-admin', 'systemadmin'
            ]
            
            for variation in dangerous_variations:
                if normalized_custom == variation or variation in normalized_custom:
                    errors.append("Custom name cannot resemble system administrator roles")
                    break

        # Branch Admin specific validations
        if user and user.role == 'admin':
            # Branch admins can only create/edit custom roles
            if name != 'custom':
                errors.append("Branch Admins can only manage custom roles")
        
        # Check for duplicates
        if name and name != 'custom':
            query = Role.objects.filter(name=name)
            if exclude_role_id:
                query = query.exclude(id=exclude_role_id)
            if query.exists():
                errors.append(f"Role '{name}' already exists")
        
        if custom_name:
            query = Role.objects.filter(custom_name=custom_name)
            if exclude_role_id:
                query = query.exclude(id=exclude_role_id)
            if query.exists():
                errors.append(f"Custom role '{custom_name}' already exists")
        
        return errors

    @staticmethod
    def validate_role_assignment_Session(user, target_role, target_user, assigned_by):
        """Comprehensive Session validation for role assignments"""
        from django.core.exceptions import ValidationError
        
        violations = []
        
        # 1. Basic validation
        if not user or not user.is_active:
            violations.append("Target user is not active")
        
        if not target_role or not target_role.is_active:
            violations.append("Target role is not active") 
        
        # 2. Permission validation
        if not PermissionManager.can_user_assign_role(assigned_by, target_role, user):
            violations.append("Insufficient permissions to assign this role")
        
        # 3. Hierarchy validation
        assigned_by_highest = PermissionManager.get_user_highest_role(assigned_by)
        if not assigned_by_highest:
            violations.append("Assigner has no valid role")
        elif assigned_by_highest.hierarchy_level <= target_role.hierarchy_level:
            violations.append(f"Cannot assign role {target_role.name} - assigner role {assigned_by_highest.name} is not higher in hierarchy")
        
        # 4. Branch isolation validation for non-global admins
        if assigned_by.role not in ['globaladmin']:
            if (hasattr(user, 'branch') and hasattr(assigned_by, 'branch') and 
                user.branch_id != assigned_by.branch_id):
                if assigned_by.role == 'superadmin':
                    # Super admins can assign roles across branches within their businesses
                    if hasattr(user.branch, 'business') and hasattr(assigned_by, 'business_assignments'):
                        user_business = user.branch.business if user.branch else None
                        if user_business:
                            has_business_access = assigned_by.business_assignments.filter(
                                business=user_business,
                                is_active=True
                            ).exists()
                            if not has_business_access:
                                violations.append("Cannot assign roles to users in branches outside your business scope")
                    else:
                        violations.append("Cannot assign roles across branches without proper business assignment")
                else:
                    violations.append("Cannot assign roles across branches without superadmin privileges")
        
        # 5. Self-assignment validation
        if user.pk == assigned_by.pk:
            if assigned_by.role != 'superadmin':
                has_superadmin = UserRole.objects.filter(
                    user=assigned_by,
                    role__name='superadmin',
                    is_active=True
                ).exists()
                if not has_superadmin:
                    violations.append("Self-assignment not allowed without superadmin privileges")
        
        # 6. Duplicate assignment check
        if UserRole.objects.filter(user=user, role=target_role, is_active=True).exists():
            violations.append(f"User already has active {target_role.name} role assignment")
        
        return violations

def require_capability(capability, redirect_url=None, message="You don't have permission to access this page."):
    """Decorator to require a specific capability for view access"""
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            
            if not PermissionManager.user_has_capability(request.user, capability):
                if redirect_url:
                    messages.error(request, message)
                    return redirect(redirect_url)
                else:
                    return HttpResponseForbidden(message)
            
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator

def require_any_capability(capabilities, redirect_url=None, message="You don't have permission to access this page."):
    """Decorator to require any of the specified capabilities for view access"""
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            
            if not PermissionManager.user_has_any_capability(request.user, capabilities):
                if redirect_url:
                    messages.error(request, message)
                    return redirect(redirect_url)
                else:
                    return HttpResponseForbidden(message)
            
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator

def require_role_hierarchy(min_role_level, redirect_url=None, message="You don't have sufficient permissions."):
    """Decorator to require minimum role hierarchy level"""
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            
            user_highest_role = PermissionManager.get_user_highest_role(request.user)
            if not user_highest_role or user_highest_role.hierarchy_level < min_role_level:
                if redirect_url:
                    messages.error(request, message)
                    return redirect(redirect_url)
                else:
                    return HttpResponseForbidden(message)
            
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def enhanced_csrf_protect(view_func):
    """Enhanced CSRF protection with additional Session measures"""
    from django.views.decorators.csrf import csrf_protect
    
    @csrf_protect
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        # Additional Session checks
        if request.method in ['POST', 'PUT', 'PATCH', 'DELETE']:
            # Check for suspicious request patterns (more specific XSS patterns)
            suspicious_patterns = [
                '<script', 'javascript:', 'vbscript:', 'onload=', 'onerror=',
                'eval(', 'expression(', 'document.cookie', 'alert(', 'confirm(',
                'prompt(', '<iframe', '<object', '<embed'
            ]
            
            # Check request data for suspicious content (safer approach)
            try:
                # Check POST data instead of raw body to avoid RawPostDataException
                content_to_check = ""
                
                # Check POST data
                if hasattr(request, 'POST') and request.POST:
                    content_to_check += " ".join(str(value) for value in request.POST.values())
                
                # Check GET data
                if hasattr(request, 'GET') and request.GET:
                    content_to_check += " ".join(str(value) for value in request.GET.values())
                
                content_to_check = content_to_check.lower()
                
                for pattern in suspicious_patterns:
                    if pattern in content_to_check:
                        logger.warning(f"Suspicious request content detected from {AuditLogger.get_client_ip(request)}: {pattern}")
                        
                        # Log Session event
                        try:
                            RoleAuditLog.objects.create(
                                user=request.user if request.user.is_authenticated else None,
                                action='suspicious_request',
                                description=f"Suspicious content detected: {pattern}",
                                metadata={
                                    'suspicious_pattern': pattern,
                                    'view_name': view_func.__name__,
                                    'Session_event': True
                                },
                                ip_address=AuditLogger.get_client_ip(request)
                            )
                        except:
                            pass
                        
                        return JsonResponse({'success': False, 'error': 'Invalid request content'}, status=400)
                        
            except Exception as e:
                # If anything goes wrong with Session checks, log it but don't block the request
                logger.warning(f"Session check failed in enhanced_csrf_protect: {str(e)}")
                pass
            
            # Validate referrer for additional CSRF protection
            referer = request.META.get('HTTP_REFERER', '')
            host = request.META.get('HTTP_HOST', '')
            
            if referer and host:
                from urllib.parse import urlparse
                referer_host = urlparse(referer).netloc
                if referer_host and referer_host != host:
                    logger.warning(f"Cross-origin request from {referer_host} to {host}")
                    return JsonResponse({'success': False, 'error': 'Invalid request origin'}, status=403)
        
        return view_func(request, *args, **kwargs)
    return wrapper

class SessionMonitor:
    """Monitor and track Session events for role management"""
    
    @staticmethod
    def log_Session_event(event_type, user, details, severity='medium', request=None):
        """Log a Session event with proper categorization"""
        try:
            metadata = {
                'event_type': event_type,
                'severity': severity,
                'details': details,
                'timestamp': timezone.now().isoformat(),
                'Session_event': True
            }
            
            if request:
                metadata.update({
                    'user_agent': request.META.get('HTTP_USER_AGENT', ''),
                    'method': request.method,
                    'path': request.path,
                    'query_params': dict(request.GET),
                    'session_key': request.session.session_key if hasattr(request, 'session') else None
                })
            
            RoleAuditLog.objects.create(
                user=user,
                action='Session_event',
                description=f"Session Event: {event_type}",
                metadata=metadata,
                ip_address=AuditLogger.get_client_ip(request) if request else None
            )
            
            # Log to system logger based on severity
            if severity == 'critical':
                logger.error(f"CRITICAL Session EVENT: {event_type} - {details}")
            elif severity == 'high':
                logger.warning(f"HIGH Session EVENT: {event_type} - {details}")
            else:
                logger.info(f"Session Event: {event_type} - {details}")
                
        except Exception as e:
            logger.error(f"Failed to log Session event: {str(e)}")
    
    @staticmethod
    def check_for_anomalies(user):
        """Check for anomalous behavior patterns"""
        anomalies = []
        
        try:
            # Check recent failed attempts (database-agnostic approach for JSON field)
            recent_audit_logs = RoleAuditLog.objects.filter(
                user=user,
                timestamp__gte=timezone.now() - timezone.timedelta(hours=1)
            )
            
            # Filter in Python to avoid database-specific JSON operations
            recent_failures = 0
            for log in recent_audit_logs:
                if log.metadata and log.metadata.get('Session_event') is True:
                    recent_failures += 1
            
            if recent_failures > 5:
                anomalies.append(f"Excessive Session events: {recent_failures} in past hour")
            
            # Check for rapid role changes
            recent_role_changes = RoleAuditLog.objects.filter(
                target_user=user,
                action__in=['assign', 'unassign'],
                timestamp__gte=timezone.now() - timezone.timedelta(minutes=30)
            ).count()
            
            if recent_role_changes > 3:
                anomalies.append(f"Rapid role changes: {recent_role_changes} in 30 minutes")
                
        except Exception as e:
            logger.error(f"Error checking anomalies for user {user.pk}: {str(e)}")
        
        return anomalies

class SessionErrorHandler:
    """Handle errors securely without information disclosure"""
    
    # Generic error messages for different error types
    GENERIC_MESSAGES = {
        'validation': 'Invalid input provided. Please check your data and try again.',
        'permission': 'You do not have permission to perform this action.',
        'not_found': 'The requested resource was not found.',
        'rate_limit': 'Too many requests. Please try again later.',
        'system': 'A system error occurred. Please try again or contact support.',
        'database': 'Unable to process request due to data constraints.',
        'authentication': 'Authentication required to access this resource.',
        'network': 'Network error occurred. Please check your connection.',
        'timeout': 'Request timed out. Please try again.',
        'maintenance': 'System is temporarily unavailable for maintenance.'
    }
    
    @staticmethod
    def sanitize_error_message(error, error_type='system', show_details=False):
        """
        Sanitize error messages to prevent information disclosure
        
        Args:
            error: The original error (Exception or string)
            error_type: Type of error for generic message selection
            show_details: Whether to show detailed error (only for authorized users)
        """
        if show_details:
            # For authorized users (admins), show more details but still sanitized
            if isinstance(error, Exception):
                error_str = str(error)
                # Remove sensitive patterns
                sensitive_patterns = [
                    r'password[=:]\s*[^\s]+',
                    r'token[=:]\s*[^\s]+',
                    r'key[=:]\s*[^\s]+',
                    r'secret[=:]\s*[^\s]+',
                    r'\/[a-zA-Z0-9\-_]+\/[a-zA-Z0-9\-_]+\/[a-zA-Z0-9\-_]+',  # file paths
                    r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}',  # IP addresses
                ]
                
                import re
                for pattern in sensitive_patterns:
                    error_str = re.sub(pattern, '[REDACTED]', error_str, flags=re.IGNORECASE)
                
                return error_str[:500]  # Limit length
            else:
                return str(error)[:500]
        else:
            # For regular users, return generic message
            return SessionErrorHandler.GENERIC_MESSAGES.get(error_type, 
                SessionErrorHandler.GENERIC_MESSAGES['system'])
    
    @staticmethod
    def log_and_sanitize_error(error, request, error_type='system', operation=''):
        """Log error with full details and return sanitized message"""
        # Determine if user should see detailed errors
        show_details = False
        if request and request.user.is_authenticated:
            # Show details only to superadmin and globaladmin
            if (hasattr(request.user, 'role') and 
                request.user.role in ['globaladmin', 'superadmin']):
                show_details = True
        
        # Log full error details for debugging
        logger.error(f"Error in {operation}: {str(error)}", exc_info=True)
        
        # Return sanitized message
        return SessionErrorHandler.sanitize_error_message(error, error_type, show_details)
    
    @staticmethod
    def handle_validation_error(error, request=None):
        """Handle Django ValidationError securely"""
        if hasattr(error, 'message_dict'):
            # Multiple field errors
            if request and request.user.is_authenticated and hasattr(request.user, 'role') and request.user.role in ['globaladmin', 'superadmin']:
                # For admins, show field-specific errors but sanitized
                sanitized_errors = {}
                for field, messages in error.message_dict.items():
                    sanitized_errors[field] = [
                        SessionErrorHandler.sanitize_error_message(msg, 'validation', True)[:200]
                        for msg in messages
                    ]
                return sanitized_errors
            else:
                # For regular users, generic message
                return {'error': SessionErrorHandler.GENERIC_MESSAGES['validation']}
        else:
            # Single error message
            return SessionErrorHandler.sanitize_error_message(error, 'validation', 
                request and request.user.is_authenticated and 
                hasattr(request.user, 'role') and 
                request.user.role in ['globaladmin', 'superadmin'])

class AuditLogger:
    """Audit logging utilities for role management"""
    
    @staticmethod
    def log_role_action(user, action, role=None, target_user=None, description="", metadata=None, request=None):
        """Log a role-related action with optional request context"""
        ip_address = None
        if request:
            ip_address = AuditLogger.get_client_ip(request)
        
        return RoleAuditLog.log_action(
            user=user,
            action=action,
            role=role,
            target_user=target_user,
            description=description,
            metadata=metadata,
            ip_address=ip_address
        )
    
    @staticmethod
    def get_client_ip(request):
        """Get client IP address from request"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
    
    @staticmethod
    def get_role_audit_history(role, limit=100):
        """Get audit history for a specific role"""
        return RoleAuditLog.objects.filter(role=role).order_by('-timestamp')[:limit]
    
    @staticmethod
    def get_user_role_audit_history(user, limit=100):
        """Get role audit history for a specific user"""
        return RoleAuditLog.objects.filter(
            Q(user=user) | Q(target_user=user)
        ).order_by('-timestamp')[:limit]

def get_available_capabilities():
    """Get all available capabilities in the system"""
    return [
        # User Management
        'view_users', 'manage_users', 'create_users', 'delete_users',
        'view_groups', 'manage_groups', 'create_groups', 'delete_groups', 'manage_group_members',
        
        # Course Management  
        'view_courses', 'manage_courses', 'create_courses', 'delete_courses',
        'view_topics', 'manage_topics', 'create_topics', 'delete_topics',
        'view_categories', 'manage_categories', 'create_categories', 'delete_categories',
        
        # Assessment Management
        'view_assignments', 'manage_assignments', 'create_assignments', 'delete_assignments',
        'grade_assignments', 'submit_assignments',
        'view_quizzes', 'manage_quizzes', 'create_quizzes', 'delete_quizzes',
        'grade_quizzes', 'take_quizzes',
        'view_rubrics', 'manage_rubrics', 'create_rubrics', 'delete_rubrics',
        
        # Communication Management
        'view_discussions', 'manage_discussions', 'create_discussions', 'delete_discussions',
        'view_conferences', 'manage_conferences', 'create_conferences', 'delete_conferences',
        'view_messages', 'manage_messages', 'create_messages', 'delete_messages',
        'send_notifications', 'manage_notifications',
        
        # Branch Management
        'view_branches', 'manage_branches', 'create_branches', 'delete_branches',
        
        # Role Management
        'view_roles', 'manage_roles', 'create_roles', 'delete_roles',
        
        # Reports and Analytics
        'view_reports', 'manage_reports', 'export_reports',
        'view_analytics', 'view_progress', 'manage_progress',
        
        # System Management
        'manage_system_settings', 'view_system_logs',
        'view_certificates_templates', 'manage_certificates',
    ]

def get_capability_categories():
    """Get capabilities organized by categories"""
    return {
        'User Management': [
            'view_users', 'manage_users', 'create_users', 'delete_users',
            'view_groups', 'manage_groups', 'create_groups', 'delete_groups', 'manage_group_members',
        ],
        'Course Management': [
            'view_courses', 'manage_courses', 'create_courses', 'delete_courses',
            'view_topics', 'manage_topics', 'create_topics', 'delete_topics',
            'view_categories', 'manage_categories', 'create_categories', 'delete_categories',
        ],
        'Assessment Management': [
            'view_assignments', 'manage_assignments', 'create_assignments', 'delete_assignments',
            'grade_assignments', 'submit_assignments',
            'view_quizzes', 'manage_quizzes', 'create_quizzes', 'delete_quizzes',
            'grade_quizzes', 'take_quizzes',
            'view_rubrics', 'manage_rubrics', 'create_rubrics', 'delete_rubrics',
        ],
        'Communication Management': [
            'view_discussions', 'manage_discussions', 'create_discussions', 'delete_discussions',
            'view_conferences', 'manage_conferences', 'create_conferences', 'delete_conferences',
            'view_messages', 'manage_messages', 'create_messages', 'delete_messages',
            'send_notifications', 'manage_notifications',
        ],
        'Branch Management': [
            'view_branches', 'manage_branches', 'create_branches', 'delete_branches',
        ],
        'Role Management': [
            'view_roles', 'manage_roles', 'create_roles', 'delete_roles',
        ],
        'Reports and Analytics': [
            'view_reports', 'manage_reports', 'export_reports',
            'view_analytics', 'view_progress', 'manage_progress',
        ],
        'System Management': [
            'manage_system_settings', 'view_system_logs',
            'view_certificates_templates', 'manage_certificates',
        ]
    } 