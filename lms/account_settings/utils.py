"""
Utility functions for account settings validation
"""
import re
import logging

logger = logging.getLogger(__name__)

def validate_microsoft_client_secret(client_secret):
    """
    Validate Microsoft OAuth client secret format.
    
    Args:
        client_secret (str): The client secret to validate
        
    Returns:
        tuple: (is_valid, message)
    """
    if not client_secret:
        return False, "Client secret is required"
    
    # Remove whitespace
    client_secret = client_secret.strip()
    
    # Check length - Azure client secrets are typically 40+ characters
    if len(client_secret) < 32:
        return False, f"Client secret appears to be too short ({len(client_secret)} characters). Azure client secrets are typically 32+ characters. You may have entered the secret ID instead of the secret value."
    
    # Check if it looks like a UUID (which would be the secret ID)
    uuid_pattern = r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$'
    if re.match(uuid_pattern, client_secret.lower()):
        return False, "This appears to be a client secret ID (UUID format). Please use the client secret VALUE instead."
    
    # Check for common Azure secret value patterns
    # Azure secrets often contain alphanumeric chars with some special chars like . _ ~ -
    if not re.match(r'^[A-Za-z0-9._~-]+$', client_secret):
        logger.warning(f"Client secret contains unexpected characters: {client_secret[:10]}...")
    
    return True, "Client secret format appears valid"

def validate_microsoft_oauth_config(client_id, client_secret, tenant_id=None):
    """
    Validate complete Microsoft OAuth configuration.
    
    Args:
        client_id (str): The client ID
        client_secret (str): The client secret  
        tenant_id (str): The tenant ID (optional)
        
    Returns:
        tuple: (is_valid, messages_list)
    """
    messages = []
    is_valid = True
    
    # Validate client ID
    if not client_id:
        messages.append("Client ID is required")
        is_valid = False
    elif not re.match(r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$', client_id.lower()):
        messages.append("Client ID should be in UUID format (e.g., 12345678-1234-1234-1234-123456789012)")
        is_valid = False
    
    # Validate client secret
    secret_valid, secret_message = validate_microsoft_client_secret(client_secret)
    if not secret_valid:
        messages.append(secret_message)
        is_valid = False
    
    # Validate tenant ID if provided
    if tenant_id and tenant_id.lower() not in ['common', 'organizations', 'consumers']:
        if not re.match(r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$', tenant_id.lower()):
            messages.append("Tenant ID should be 'common', 'organizations', 'consumers', or a valid UUID")
            is_valid = False
    
    if is_valid:
        messages.append("Microsoft OAuth configuration appears valid")
    
    return is_valid, messages
