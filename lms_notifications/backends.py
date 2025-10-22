import json
import requests
from django.core.mail.backends.base import BaseEmailBackend
from django.core.mail.message import EmailMessage
from django.conf import settings
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)

class OutlookOAuth2Backend(BaseEmailBackend):
    """
    Modern OAuth2 email backend for Microsoft 365/Outlook
    Replaces basic SMTP authentication which is being deprecated
    """
    
    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently, **kwargs)
        self.access_token = None
        self.token_expires = None
        self.connection = None
        
    def open(self):
        """
        Ensure a connection to the email service. 
        Required by Django's email backend interface.
        """
        try:
            # Test token acquisition to verify connection
            access_token = self.get_access_token()
            self.connection = access_token is not None
            return self.connection
        except Exception as e:
            logger.error(f"Failed to open OAuth2 connection: {str(e)}")
            # Always return False on failure, never raise
            # This prevents server crashes when OAuth2 is misconfigured
            return False
    
    def close(self):
        """
        Close the connection to the email service.
        """
        self.connection = None
        self.access_token = None
        self.token_expires = None
        
    def get_access_token(self):
        """Get OAuth2 access token for Microsoft Graph API"""
        try:
            # Check if token is still valid
            if (self.access_token and self.token_expires and 
                timezone.now() < self.token_expires):
                return self.access_token
                
            # Validate OAuth2 credentials are configured
            if not all([settings.OUTLOOK_TENANT_ID, settings.OUTLOOK_CLIENT_ID, settings.OUTLOOK_CLIENT_SECRET]):
                logger.error(" OAuth2 credentials are incomplete. Required: OUTLOOK_TENANT_ID, OUTLOOK_CLIENT_ID, OUTLOOK_CLIENT_SECRET")
                return None
                
            # Get new token
            token_url = f"https://login.microsoftonline.com/{settings.OUTLOOK_TENANT_ID}/oauth2/v2.0/token"
            
            data = {
                'grant_type': 'client_credentials',
                'client_id': settings.OUTLOOK_CLIENT_ID,
                'client_secret': settings.OUTLOOK_CLIENT_SECRET,
                'scope': 'https://graph.microsoft.com/.default'
            }
            
            response = requests.post(token_url, data=data)
            response.raise_for_status()
            
            token_data = response.json()
            self.access_token = token_data['access_token']
            
            # Set expiration (subtract 5 minutes for safety)
            expires_in = token_data.get('expires_in', 3600) - 300
            self.token_expires = timezone.now() + timezone.timedelta(seconds=expires_in)
            
            logger.info(" Successfully obtained OAuth2 access token")
            return self.access_token
            
        except requests.exceptions.HTTPError as e:
            # HTTP errors (400, 401, 403, etc.)
            status_code = e.response.status_code if hasattr(e, 'response') else 'unknown'
            error_msg = e.response.text if hasattr(e, 'response') else str(e)
            logger.error(f" OAuth2 HTTP Error {status_code}: {error_msg}")
            
            if status_code == 400:
                logger.error("🔑 Bad Request - OAuth2 credentials may be invalid, expired, or incorrectly configured")
            elif status_code == 401:
                logger.error("🔑 Unauthorized - OAuth2 credentials are invalid or expired")
            elif status_code == 403:
                logger.error("🔑 Forbidden - OAuth2 app may not have required permissions (Mail.Send)")
                
            return None
            
        except Exception as e:
            logger.error(f" Failed to get OAuth2 token: {str(e)}")
            # Always return None on failure, never raise
            # This prevents server crashes when OAuth2 credentials are invalid
            return None
    
    def send_messages(self, email_messages):
        """Send email messages using Microsoft Graph API"""
        if not email_messages:
            return 0
        
        # Ensure connection is open
        if not self.connection:
            if not self.open():
                logger.error(" Failed to establish OAuth2 connection - OAuth2 credentials may be invalid or expired")
                # Don't raise exception, just return 0 to indicate failure
                # The calling code can handle this gracefully
                return 0
            
        access_token = self.get_access_token()
        if not access_token:
            logger.error(" Failed to get OAuth2 access token - check OUTLOOK_CLIENT_ID, OUTLOOK_CLIENT_SECRET, and OUTLOOK_TENANT_ID")
            return 0
            
        sent_count = 0
        
        for message in email_messages:
            try:
                if self.send_single_message(message, access_token):
                    sent_count += 1
                else:
                    logger.error(f" Failed to send email to {', '.join(message.to)} - send_single_message returned False")
            except Exception as e:
                logger.error(f" Exception while sending email to {', '.join(message.to)}: {str(e)}")
                if not self.fail_silently:
                    # Don't raise - log and continue to prevent crashes
                    logger.error(" Email send failed but not raising exception to prevent server crashes")
                    
        return sent_count
    
    def send_single_message(self, message, access_token):
        """Send a single email message via Microsoft Graph API"""
        try:
            # Determine content type and body
            # Check for HTML alternatives first (EmailMultiAlternatives)
            html_content = None
            if hasattr(message, 'alternatives') and message.alternatives:
                for alternative_content, content_type in message.alternatives:
                    if content_type == 'text/html':
                        html_content = alternative_content
                        break
            
            # Use HTML content if available, otherwise use plain text
            if html_content:
                body_content = html_content
                content_type = "HTML"
                logger.debug(f"Using HTML alternative content (length: {len(html_content)})")
            elif message.content_subtype == 'html':
                body_content = message.body
                content_type = "HTML"
                logger.debug(f"Using HTML main body content (length: {len(message.body)})")
            else:
                body_content = message.body
                content_type = "Text"
                logger.debug(f"Using plain text content (length: {len(message.body)})")
            
            # Prepare email data for Graph API
            email_data = {
                "message": {
                    "subject": message.subject,
                    "body": {
                        "contentType": content_type,
                        "content": body_content
                    },
                    "toRecipients": [
                        {"emailAddress": {"address": to_email}} 
                        for to_email in message.to
                    ],
                    "ccRecipients": [
                        {"emailAddress": {"address": cc_email}} 
                        for cc_email in message.cc
                    ] if message.cc else [],
                    "bccRecipients": [
                        {"emailAddress": {"address": bcc_email}} 
                        for bcc_email in message.bcc
                    ] if message.bcc else [],
                    "from": {
                        "emailAddress": {
                            "address": message.from_email or settings.OUTLOOK_FROM_EMAIL
                        }
                    }
                },
                "saveToSentItems": True
            }
            
            # Handle attachments if any
            if hasattr(message, 'attachments') and message.attachments:
                email_data["message"]["attachments"] = []
                for attachment in message.attachments:
                    if hasattr(attachment, 'get_content'):
                        content = attachment.get_content()
                        email_data["message"]["attachments"].append({
                            "@odata.type": "#microsoft.graph.fileAttachment",
                            "name": attachment.get_filename(),
                            "contentBytes": content.decode('utf-8') if isinstance(content, bytes) else content
                        })
            
            # Try different Graph API endpoints
            endpoints_to_try = [
                f"https://graph.microsoft.com/v1.0/me/sendMail",  # Try 'me' endpoint first
                f"https://graph.microsoft.com/v1.0/users/{settings.OUTLOOK_FROM_EMAIL}/sendMail",  # Original endpoint
            ]
            
            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json'
            }
            
            for endpoint in endpoints_to_try:
                try:
                    response = requests.post(endpoint, headers=headers, json=email_data)
                    
                    if response.status_code == 202:  # Accepted
                        logger.info(f"Email sent successfully to {', '.join(message.to)} via {endpoint}")
                        return True
                    elif response.status_code == 404:
                        # Try next endpoint
                        continue
                    else:
                        logger.warning(f"Failed endpoint {endpoint}. Status: {response.status_code}, Response: {response.text}")
                        continue
                        
                except Exception as e:
                    logger.warning(f"Error with endpoint {endpoint}: {str(e)}")
                    continue
            
            # If all endpoints failed
            logger.error(f"Failed to send email through all available endpoints")
            return False
                
        except Exception as e:
            logger.error(f"Error sending email: {str(e)}")
            if not self.fail_silently:
                raise
            return False 