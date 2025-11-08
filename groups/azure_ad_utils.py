"""
Azure AD Utilities for Group Import and Sync
"""
import logging
import requests
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
from typing import Optional, Dict, List, Tuple
from account_settings.models import TeamsIntegration

logger = logging.getLogger(__name__)


class AzureADAPIError(Exception):
    """Custom exception for Azure AD API errors"""
    pass


class AzureADGroupAPI:
    """
    Azure AD API client for fetching groups and users from Microsoft Graph API
    Uses the Teams Integration credentials configured by branch admin
    """
    
    def __init__(self, branch):
        """
        Initialize Azure AD API client
        
        Args:
            branch: Branch model instance
        """
        self.branch = branch
        self.base_url = "https://graph.microsoft.com/v1.0"
        self.access_token = None
        self.token_expiry = None
        
        # Get Teams Integration for this branch
        try:
            self.integration = TeamsIntegration.objects.get(branch=branch)
        except TeamsIntegration.DoesNotExist:
            raise AzureADAPIError(f"Microsoft Teams integration not configured for branch: {branch.name}")
    
    def get_access_token(self, force_refresh: bool = False) -> Optional[str]:
        """
        Get or refresh access token for Microsoft Graph API
        
        Args:
            force_refresh: Force token refresh
            
        Returns:
            str: Access token
        """
        # Check if we have a valid cached token
        if not force_refresh and self.integration.access_token and self.integration.token_expiry:
            if timezone.now() < self.integration.token_expiry:
                return self.integration.access_token
        
        try:
            # Get token using client credentials flow
            token_url = f"https://login.microsoftonline.com/{self.integration.tenant_id}/oauth2/v2.0/token"
            
            token_data = {
                'grant_type': 'client_credentials',
                'client_id': self.integration.client_id,
                'client_secret': self.integration.client_secret,
                'scope': 'https://graph.microsoft.com/.default'
            }
            
            response = requests.post(token_url, data=token_data, timeout=30)
            
            if response.status_code == 200:
                token_info = response.json()
                self.access_token = token_info['access_token']
                expires_in = token_info.get('expires_in', 3600)
                self.token_expiry = timezone.now() + timedelta(seconds=expires_in - 300)  # 5 min buffer
                
                # Update integration with new token
                self.integration.access_token = self.access_token
                self.integration.token_expiry = self.token_expiry
                self.integration.save(update_fields=['access_token', 'token_expiry'])
                
                logger.info(f"Successfully obtained Azure AD access token for branch: {self.branch.name}")
                return self.access_token
            else:
                error_msg = response.json().get('error_description', 'Failed to get access token')
                logger.error(f"Failed to get Azure AD token: {error_msg}")
                raise AzureADAPIError(f"Token acquisition failed: {error_msg}")
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting Azure AD token: {str(e)}")
            raise AzureADAPIError(f"Token acquisition error: {str(e)}")
    
    def _make_request(self, method: str, endpoint: str, params: Optional[Dict] = None) -> Dict:
        """
        Make request to Microsoft Graph API
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint
            params: Query parameters
            
        Returns:
            Dict: Response JSON
        """
        token = self.get_access_token()
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        
        url = f"{self.base_url}/{endpoint}"
        
        try:
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                params=params,
                timeout=30
            )
            
            if response.status_code == 401:  # Token expired, refresh and retry
                logger.info("Token expired, refreshing...")
                token = self.get_access_token(force_refresh=True)
                headers['Authorization'] = f'Bearer {token}'
                response = requests.request(
                    method=method,
                    url=url,
                    headers=headers,
                    params=params,
                    timeout=30
                )
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.HTTPError as e:
            error_msg = f"Azure AD API error: {e.response.status_code} - {e.response.text}"
            logger.error(error_msg)
            raise AzureADAPIError(error_msg)
        except requests.exceptions.RequestException as e:
            logger.error(f"Azure AD API request error: {str(e)}")
            raise AzureADAPIError(f"Request error: {str(e)}")
    
    def get_all_groups(self) -> List[Dict]:
        """
        Get all Azure AD groups
        
        Returns:
            List[Dict]: List of group objects with id, displayName, description
        """
        try:
            all_groups = []
            endpoint = "groups"
            params = {
                '$select': 'id,displayName,description,groupTypes',
                '$top': 999
            }
            
            while endpoint:
                response = self._make_request('GET', endpoint, params)
                groups = response.get('value', [])
                all_groups.extend(groups)
                
                # Handle pagination
                endpoint = response.get('@odata.nextLink', '').replace(self.base_url + '/', '')
                params = None  # Pagination link already contains parameters
            
            logger.info(f"Retrieved {len(all_groups)} groups from Azure AD")
            return all_groups
            
        except Exception as e:
            logger.error(f"Error fetching Azure AD groups: {str(e)}")
            raise AzureADAPIError(f"Failed to fetch groups: {str(e)}")
    
    def get_group_members(self, group_id: str) -> List[Dict]:
        """
        Get all members of an Azure AD group with full user details
        
        Args:
            group_id: Azure AD Group ID
            
        Returns:
            List[Dict]: List of user objects with id, displayName, mail, userPrincipalName
        """
        try:
            all_members = []
            
            # STEP 1: Get list of member IDs
            logger.info(f"Fetching member IDs from group: {group_id}")
            endpoint = f"groups/{group_id}/members"
            params = {
                '$select': 'id',
                '$top': 999
            }
            
            member_ids = []
            while endpoint:
                response = self._make_request('GET', endpoint, params)
                members = response.get('value', [])
                
                # Extract only user IDs
                for member in members:
                    if member.get('@odata.type') == '#microsoft.graph.user':
                        member_ids.append(member.get('id'))
                
                endpoint = response.get('@odata.nextLink', '').replace(self.base_url + '/', '')
                params = None
            
            logger.info(f"Found {len(member_ids)} user member IDs, now fetching details in batches...")
            
            # STEP 2: Fetch full details for users using $batch endpoint (20 users per batch)
            batch_size = 20
            for i in range(0, len(member_ids), batch_size):
                batch_ids = member_ids[i:i + batch_size]
                
                # Create batch request
                requests_batch = []
                for idx, user_id in enumerate(batch_ids):
                    requests_batch.append({
                        "id": str(idx),
                        "method": "GET",
                        "url": f"/users/{user_id}?$select=id,displayName,mail,userPrincipalName,givenName,surname"
                    })
                
                try:
                    # Make batch request
                    batch_response = self._make_request('POST', '$batch', None)
                    # Note: batch request needs special handling
                    import requests as http_requests
                    token = self.get_access_token()
                    headers = {
                        'Authorization': f'Bearer {token}',
                        'Content-Type': 'application/json'
                    }
                    
                    response = http_requests.post(
                        f"{self.base_url}/$batch",
                        headers=headers,
                        json={"requests": requests_batch},
                        timeout=30
                    )
                    
                    if response.status_code == 200:
                        batch_data = response.json()
                        for resp in batch_data.get('responses', []):
                            if resp.get('status') == 200:
                                user_data = resp.get('body')
                                if user_data:
                                    all_members.append(user_data)
                    
                    logger.info(f"Processed batch {i//batch_size + 1}/{(len(member_ids) + batch_size - 1)//batch_size}")
                    
                except Exception as batch_error:
                    logger.warning(f"Batch request failed, falling back to individual requests: {str(batch_error)}")
                    # Fallback to individual requests for this batch
                    for user_id in batch_ids:
                        try:
                            user_endpoint = f"users/{user_id}"
                            user_params = {
                                '$select': 'id,displayName,mail,userPrincipalName,givenName,surname'
                            }
                            user_data = self._make_request('GET', user_endpoint, user_params)
                            all_members.append(user_data)
                        except Exception as e:
                            logger.warning(f"Could not fetch details for user {user_id}: {str(e)}")
                            continue
            
            logger.info(f"Successfully retrieved details for {len(all_members)} users")
            return all_members
            
        except Exception as e:
            logger.error(f"Error fetching Azure AD group members: {str(e)}")
            raise AzureADAPIError(f"Failed to fetch group members: {str(e)}")
    
    def get_group_members_OLD(self, group_id: str) -> List[Dict]:
        """
        OLD METHOD - Kept for reference
        Get all members of an Azure AD group
        
        Args:
            group_id: Azure AD Group ID
            
        Returns:
            List[Dict]: List of user objects with id, displayName, mail, userPrincipalName
        """
        try:
            all_members = []
            # Use standard members endpoint (microsoft.graph.user requires different permissions)
            endpoint = f"groups/{group_id}/members"
            params = {
                '$select': 'id,displayName,mail,userPrincipalName,givenName,surname',
                '$top': 999
            }
            
            logger.info(f"Fetching members from group: {group_id} using endpoint: {endpoint}")
            
            while endpoint:
                try:
                    response = self._make_request('GET', endpoint, params)
                    members = response.get('value', [])
                    
                    logger.info(f"API Response received: {len(members)} members in this page for group: {group_id}")
                    logger.info(f"Response keys: {list(response.keys())}")
                    
                    # DEBUG: Log first member to see what fields are returned
                    if members and len(all_members) == 0:
                        logger.info(f"Sample member data (first user): {members[0]}")
                        logger.info(f"Member keys: {list(members[0].keys())}")
                    elif not members:
                        logger.warning(f"No members returned from API for group: {group_id}")
                        logger.warning(f"Full response: {response}")
                except Exception as api_error:
                    logger.error(f"Error making API request for group members: {str(api_error)}")
                    logger.exception("Full traceback:")
                    raise
                
                # Filter only users (not nested groups or other objects)
                # Check @odata.type if present, otherwise check if object has user properties
                for member in members:
                    odata_type = member.get('@odata.type', '')
                    
                    # Log detailed info for debugging
                    logger.debug(f"Processing member: displayName={member.get('displayName')}, "
                               f"@odata.type={odata_type}, "
                               f"has_mail={bool(member.get('mail'))}, "
                               f"has_userPrincipalName={bool(member.get('userPrincipalName'))}")
                    
                    # Accept if explicitly marked as user, or if it has user properties (mail/userPrincipalName)
                    if (odata_type == '#microsoft.graph.user' or 
                        (not odata_type and (member.get('mail') or member.get('userPrincipalName')))):
                        all_members.append(member)
                    elif odata_type and odata_type != '#microsoft.graph.user':
                        logger.info(f"Skipping non-user object: {odata_type} - {member.get('displayName')}")
                    else:
                        logger.warning(f"Skipping member (no type and no email): {member.get('displayName')} - Available fields: {list(member.keys())}")
                
                # Handle pagination
                endpoint = response.get('@odata.nextLink', '').replace(self.base_url + '/', '')
                params = None  # Pagination link already contains parameters
            
            logger.info(f"Retrieved {len(all_members)} user members from Azure AD group: {group_id}")
            return all_members
            
        except Exception as e:
            logger.error(f"Error fetching Azure AD group members: {str(e)}")
            raise AzureADAPIError(f"Failed to fetch group members: {str(e)}")
    
    def get_groups_by_type(self) -> Dict[str, List[Dict]]:
        """
        Get all Azure AD groups organized by type
        
        Returns:
            Dict with keys: 'security', 'microsoft365', 'distribution', 'other'
        """
        try:
            all_groups = self.get_all_groups()
            
            categorized = {
                'security': [],
                'microsoft365': [],
                'distribution': [],
                'other': []
            }
            
            for group in all_groups:
                group_types = group.get('groupTypes', [])
                
                if 'Unified' in group_types:
                    categorized['microsoft365'].append(group)
                elif not group_types:
                    # Security groups typically have empty groupTypes
                    categorized['security'].append(group)
                elif 'DynamicMembership' in group_types:
                    categorized['security'].append(group)
                else:
                    categorized['other'].append(group)
            
            return categorized
            
        except Exception as e:
            logger.error(f"Error categorizing Azure AD groups: {str(e)}")
            raise AzureADAPIError(f"Failed to categorize groups: {str(e)}")

