"""
Django management command to check if a specific user exists in Azure AD

Usage:
    python manage.py check_azure_user --email <email>
    python manage.py check_azure_user --email <email> --integration-id <id>
"""

from django.core.management.base import BaseCommand
from account_settings.models import TeamsIntegration
from teams_integration.utils.teams_api import TeamsAPIClient, TeamsAPIError


class Command(BaseCommand):
    help = 'Check if a specific user exists in Azure AD and has a mailbox'

    def add_arguments(self, parser):
        parser.add_argument(
            '--email',
            type=str,
            required=True,
            help='Email address to check',
        )
        parser.add_argument(
            '--integration-id',
            type=int,
            help='Teams integration ID to use (defaults to first active integration)',
        )

    def handle(self, *args, **options):
        email = options['email']
        integration_id = options.get('integration_id')

        # Get integration
        if integration_id:
            try:
                integration = TeamsIntegration.objects.get(id=integration_id)
            except TeamsIntegration.DoesNotExist:
                self.stdout.write(self.style.ERROR(f'Integration with ID {integration_id} not found'))
                return
        else:
            integration = TeamsIntegration.objects.filter(is_active=True).first()
            if not integration:
                self.stdout.write(self.style.ERROR('No active Teams integration found'))
                return

        self.stdout.write(f'Using integration: {integration.name}')
        self.stdout.write('=' * 80)
        self.stdout.write(f'\nChecking if user exists: {email}\n')

        try:
            client = TeamsAPIClient(integration)
            
            # Step 1: Check if user exists
            try:
                self.stdout.write('Step 1: Checking user existence...')
                user_response = client._make_request('GET', f'/users/{email}')
                
                if user_response and 'id' in user_response:
                    self.stdout.write(self.style.SUCCESS('  ✓ User EXISTS in Azure AD'))
                    self.stdout.write(f'    Display Name: {user_response.get("displayName")}')
                    self.stdout.write(f'    User Principal Name: {user_response.get("userPrincipalName")}')
                    self.stdout.write(f'    Mail: {user_response.get("mail") or "N/A"}')
                    self.stdout.write(f'    Account Enabled: {user_response.get("accountEnabled", "Unknown")}')
                    
                    # Step 2: Check if user has a calendar/mailbox
                    self.stdout.write('\nStep 2: Checking calendar/mailbox...')
                    try:
                        calendar_response = client._make_request('GET', f'/users/{email}/calendar')
                        self.stdout.write(self.style.SUCCESS('  ✓ User HAS a calendar/mailbox'))
                        self.stdout.write(f'    Calendar Name: {calendar_response.get("name", "Default")}')
                        
                        # Step 3: Check calendar permissions
                        self.stdout.write('\nStep 3: Checking calendar permissions...')
                        try:
                            # Try to get calendar events (just to test permissions)
                            events_response = client._make_request(
                                'GET', 
                                f'/users/{email}/calendar/events',
                                params={'$top': 1}
                            )
                            self.stdout.write(self.style.SUCCESS('  ✓ Can ACCESS calendar events'))
                            
                            self.stdout.write('\n' + '=' * 80)
                            self.stdout.write(self.style.SUCCESS('\n✓ ALL CHECKS PASSED!'))
                            self.stdout.write(f'\nThe email "{email}" can be used for Teams integration.')
                            self.stdout.write(f'\nTo update your integration, run:')
                            self.stdout.write(f'  python3 manage.py update_integration_owner_email \\')
                            self.stdout.write(f'    --integration-id {integration.id} \\')
                            self.stdout.write(f'    --email {email}')
                            
                        except TeamsAPIError as e:
                            if '403' in str(e) or 'forbidden' in str(e).lower():
                                self.stdout.write(self.style.ERROR('  ✗ Cannot access calendar events'))
                                self.stdout.write('\n  Reason: Missing Calendars.ReadWrite permission')
                                self.stdout.write('  Solution: Grant Calendars.ReadWrite application permission in Azure AD')
                            else:
                                raise
                    
                    except TeamsAPIError as e:
                        if '404' in str(e):
                            self.stdout.write(self.style.ERROR('  ✗ User has NO calendar/mailbox'))
                            self.stdout.write('\n  Reason: User does not have an Exchange Online license')
                            self.stdout.write('  Solution: Assign an Exchange Online license to this user in Azure AD')
                            self.stdout.write('    1. Go to Azure AD > Users > Select user')
                            self.stdout.write('    2. Click "Licenses"')
                            self.stdout.write('    3. Assign Microsoft 365 or Office 365 license')
                            self.stdout.write('    4. Wait 10-15 minutes for mailbox provisioning')
                        else:
                            raise
                    
            except TeamsAPIError as e:
                if '404' in str(e) or 'not found' in str(e).lower():
                    self.stdout.write(self.style.ERROR(f'  ✗ User NOT FOUND in Azure AD'))
                    self.stdout.write(f'\nThe user "{email}" does not exist in your Azure AD tenant.')
                    self.stdout.write('\nOptions:')
                    self.stdout.write('  1. Create this user in Azure AD:')
                    self.stdout.write('     - Go to https://portal.azure.com')
                    self.stdout.write('     - Azure AD > Users > New user')
                    self.stdout.write(f'     - Set User Principal Name to: {email}')
                    self.stdout.write('     - Assign Exchange Online license')
                    self.stdout.write('\n  2. Use a different email that exists in Azure AD:')
                    self.stdout.write('     - Check available users in Azure AD portal')
                    self.stdout.write('     - Use: python3 manage.py check_azure_user --email <existing-email>')
                else:
                    raise

        except TeamsAPIError as e:
            self.stdout.write(self.style.ERROR(f'\nError: {str(e)}'))
            
            if '403' in str(e) or 'forbidden' in str(e).lower():
                self.stdout.write('\nThis suggests missing API permissions.')
                self.stdout.write('Ensure your Azure AD app has these Application permissions:')
                self.stdout.write('  - User.Read.All')
                self.stdout.write('  - Calendars.ReadWrite')
                self.stdout.write('  - OnlineMeetings.ReadWrite.All')
                self.stdout.write('\nAnd that admin consent has been granted.')
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'\nUnexpected error: {str(e)}'))

