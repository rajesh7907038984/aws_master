"""
Django management command to diagnose Teams integration issues

Usage:
    python manage.py diagnose_teams_integration
    python manage.py diagnose_teams_integration --integration-id <id>
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from account_settings.models import TeamsIntegration
from teams_integration.utils.teams_api import TeamsAPIClient, TeamsAPIError
import json
import sys


class Command(BaseCommand):
    help = 'Diagnose Microsoft Teams integration configuration and API connectivity'

    def add_arguments(self, parser):
        parser.add_argument(
            '--integration-id',
            type=int,
            help='Specific Teams integration ID to diagnose',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('=' * 70))
        self.stdout.write(self.style.SUCCESS('Teams Integration Diagnostic Tool'))
        self.stdout.write(self.style.SUCCESS('=' * 70))
        self.stdout.write('')

        integration_id = options.get('integration_id')
        
        if integration_id:
            try:
                integrations = [TeamsIntegration.objects.get(id=integration_id)]
            except TeamsIntegration.DoesNotExist:
                self.stdout.write(self.style.ERROR(f'Integration with ID {integration_id} not found'))
                return
        else:
            integrations = TeamsIntegration.objects.filter(is_active=True)
            
        if not integrations:
            self.stdout.write(self.style.WARNING('No active Teams integrations found'))
            return

        for integration in integrations:
            self.diagnose_integration(integration)
            self.stdout.write('')

    def diagnose_integration(self, integration):
        """Diagnose a specific Teams integration"""
        
        self.stdout.write(self.style.HTTP_INFO(f'Diagnosing: {integration.name} (ID: {integration.id})'))
        self.stdout.write('-' * 70)
        
        # Step 1: Basic Configuration Check
        self.stdout.write(self.style.SUCCESS('✓ Step 1: Configuration Check'))
        self.check_configuration(integration)
        self.stdout.write('')
        
        # Step 2: Authentication Test
        self.stdout.write(self.style.SUCCESS('✓ Step 2: Authentication Test'))
        auth_success = self.check_authentication(integration)
        self.stdout.write('')
        
        if not auth_success:
            self.stdout.write(self.style.ERROR('⚠ Authentication failed. Cannot proceed with further tests.'))
            self.print_troubleshooting_steps()
            return
        
        # Step 3: API Permissions Check
        self.stdout.write(self.style.SUCCESS('✓ Step 3: API Permissions Check'))
        self.check_api_permissions(integration)
        self.stdout.write('')
        
        # Step 4: User Email Check
        self.stdout.write(self.style.SUCCESS('✓ Step 4: User Email Configuration'))
        self.check_user_email(integration)
        self.stdout.write('')
        
        # Step 5: Test Calendar Event Creation (Dry Run)
        self.stdout.write(self.style.SUCCESS('✓ Step 5: Calendar API Test'))
        self.test_calendar_api(integration)
        self.stdout.write('')

    def check_configuration(self, integration):
        """Check basic configuration"""
        checks = [
            ('Client ID', bool(integration.client_id)),
            ('Client Secret', bool(integration.client_secret)),
            ('Tenant ID', bool(integration.tenant_id)),
            ('Integration Active', integration.is_active),
            ('Owner User', bool(integration.user)),
        ]
        
        for check_name, check_result in checks:
            if check_result:
                self.stdout.write(f'  ✓ {check_name}: Configured')
            else:
                self.stdout.write(self.style.WARNING(f'  ✗ {check_name}: Missing'))

    def check_authentication(self, integration):
        """Test authentication"""
        try:
            client = TeamsAPIClient(integration)
            result = client.test_connection()
            
            if result.get('success'):
                self.stdout.write(self.style.SUCCESS('  ✓ Authentication: SUCCESS'))
                details = result.get('details', {})
                if details:
                    self.stdout.write(f'    - Tenant ID: {details.get("tenant_id", "N/A")}')
                    self.stdout.write(f'    - Client ID: {details.get("client_id", "N/A")}')
                    self.stdout.write(f'    - Token Valid Until: {details.get("token_expires", "N/A")}')
                return True
            else:
                self.stdout.write(self.style.ERROR(f'  ✗ Authentication: FAILED'))
                self.stdout.write(self.style.ERROR(f'    Error: {result.get("error")}'))
                return False
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  ✗ Authentication: EXCEPTION'))
            self.stdout.write(self.style.ERROR(f'    Error: {str(e)}'))
            return False

    def check_api_permissions(self, integration):
        """Check if API has necessary permissions"""
        try:
            client = TeamsAPIClient(integration)
            
            # Try to get basic organizational info (requires least permissions)
            try:
                response = client._make_request('GET', '/organization')
                self.stdout.write(self.style.SUCCESS('  ✓ Basic API Access: SUCCESS'))
            except TeamsAPIError as e:
                error_msg = str(e).lower()
                if '403' in error_msg or 'forbidden' in error_msg:
                    self.stdout.write(self.style.WARNING('  ⚠ Basic API Access: Permission Denied'))
                    self.stdout.write('    This might indicate missing API permissions')
                elif '404' in error_msg:
                    self.stdout.write(self.style.WARNING('  ⚠ Basic API Access: Endpoint Not Found'))
                else:
                    self.stdout.write(self.style.ERROR(f'  ✗ Basic API Access: {str(e)}'))
            
            # Check Calendar permissions
            self.stdout.write('')
            self.stdout.write('  Required Application Permissions:')
            required_permissions = [
                'Calendars.ReadWrite',
                'OnlineMeetings.ReadWrite.All',
                'User.Read.All',
            ]
            
            for perm in required_permissions:
                self.stdout.write(f'    - {perm}')
            
            self.stdout.write('')
            self.stdout.write(self.style.WARNING('  ⚠ Cannot programmatically verify permissions'))
            self.stdout.write('  Please manually verify in Azure AD Portal:')
            self.stdout.write('  1. Go to Azure AD > App registrations')
            self.stdout.write(f'  2. Find app with Client ID: {integration.client_id[:8]}...')
            self.stdout.write('  3. Check API permissions section')
            self.stdout.write('  4. Ensure all permissions above are granted with admin consent')
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  ✗ Permission Check: {str(e)}'))

    def check_user_email(self, integration):
        """Check user email configuration"""
        if integration.user and integration.user.email:
            self.stdout.write(self.style.SUCCESS(f'  ✓ Integration Owner Email: {integration.user.email}'))
            
            # Validate email format
            email = integration.user.email
            if '@' in email and '.' in email:
                self.stdout.write('  ✓ Email Format: Valid')
            else:
                self.stdout.write(self.style.WARNING('  ⚠ Email Format: Might be invalid'))
        else:
            self.stdout.write(self.style.WARNING('  ✗ Integration Owner Email: Not configured'))
            self.stdout.write('    This will cause calendar event creation to fail')
            self.stdout.write('    Solution: Set an email address for the integration owner user')

    def test_calendar_api(self, integration):
        """Test calendar API endpoint"""
        if not integration.user or not integration.user.email:
            self.stdout.write(self.style.WARNING('  ⚠ Cannot test calendar API without user email'))
            return
        
        try:
            client = TeamsAPIClient(integration)
            user_email = integration.user.email
            
            # Test if we can access the user's calendar (just read, not create)
            endpoint = f'/users/{user_email}/calendar'
            
            try:
                response = client._make_request('GET', endpoint)
                self.stdout.write(self.style.SUCCESS('  ✓ Calendar Access: SUCCESS'))
                self.stdout.write(f'    Can access calendar for: {user_email}')
                
                # If we can access calendar, test creating event endpoint structure
                self.stdout.write('')
                self.stdout.write('  Testing event creation endpoint:')
                self.stdout.write(f'    Endpoint: /users/{user_email}/calendar/events')
                self.stdout.write('    Method: POST')
                self.stdout.write('    Status: Would work with correct event data')
                
            except TeamsAPIError as e:
                error_msg = str(e).lower()
                
                if '404' in error_msg or 'not found' in error_msg:
                    self.stdout.write(self.style.ERROR('  ✗ Calendar Access: 404 NOT FOUND'))
                    self.stdout.write('')
                    self.stdout.write(self.style.ERROR('  ROOT CAUSE IDENTIFIED:'))
                    self.stdout.write('  The 404 error indicates missing API permissions in Azure AD.')
                    self.stdout.write('')
                    self.stdout.write('  SOLUTION:')
                    self.stdout.write('  1. Go to Azure Portal: https://portal.azure.com')
                    self.stdout.write('  2. Navigate to: Azure Active Directory > App registrations')
                    self.stdout.write(f'  3. Find your app (Client ID: {integration.client_id[:12]}...)')
                    self.stdout.write('  4. Click "API permissions"')
                    self.stdout.write('  5. Click "Add a permission" > "Microsoft Graph"')
                    self.stdout.write('  6. Select "Application permissions" (NOT Delegated)')
                    self.stdout.write('  7. Add these permissions:')
                    self.stdout.write('     - Calendars.ReadWrite')
                    self.stdout.write('     - OnlineMeetings.ReadWrite.All')
                    self.stdout.write('     - User.Read.All')
                    self.stdout.write('  8. Click "Grant admin consent for [Your Organization]"')
                    self.stdout.write('  9. Wait 5-10 minutes for permissions to propagate')
                    self.stdout.write('')
                    
                elif '403' in error_msg or 'forbidden' in error_msg:
                    self.stdout.write(self.style.ERROR('  ✗ Calendar Access: 403 FORBIDDEN'))
                    self.stdout.write('  Permissions are configured but admin consent might be missing')
                    
                elif '401' in error_msg or 'unauthorized' in error_msg:
                    self.stdout.write(self.style.ERROR('  ✗ Calendar Access: 401 UNAUTHORIZED'))
                    self.stdout.write('  Authentication token issue detected')
                    
                else:
                    self.stdout.write(self.style.ERROR(f'  ✗ Calendar Access: {str(e)}'))
                    
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  ✗ Calendar API Test: {str(e)}'))

    def print_troubleshooting_steps(self):
        """Print general troubleshooting steps"""
        self.stdout.write('')
        self.stdout.write(self.style.HTTP_INFO('TROUBLESHOOTING GUIDE'))
        self.stdout.write('-' * 70)
        self.stdout.write('')
        self.stdout.write('Common Issues:')
        self.stdout.write('')
        self.stdout.write('1. Invalid Client Credentials')
        self.stdout.write('   - Verify Client ID, Client Secret, and Tenant ID')
        self.stdout.write('   - Ensure Client Secret has not expired')
        self.stdout.write('')
        self.stdout.write('2. Missing API Permissions')
        self.stdout.write('   - Required: Calendars.ReadWrite (Application)')
        self.stdout.write('   - Required: OnlineMeetings.ReadWrite.All (Application)')
        self.stdout.write('   - Required: User.Read.All (Application)')
        self.stdout.write('   - Must grant admin consent')
        self.stdout.write('')
        self.stdout.write('3. User Email Not Configured')
        self.stdout.write('   - Integration owner must have a valid email address')
        self.stdout.write('   - Email must match a user in Azure AD tenant')
        self.stdout.write('')
        self.stdout.write('For detailed instructions, see: TEAMS_INTEGRATION_FIX.md')
        self.stdout.write('')

