"""
Django management command to set service account email for Teams integration

Usage:
    python manage.py set_service_account --integration-id <id> --email <email>
    python manage.py set_service_account --integration-id <id> --email <email> --verify
"""

from django.core.management.base import BaseCommand
from account_settings.models import TeamsIntegration
from teams_integration.utils.teams_api import TeamsAPIClient, TeamsAPIError


class Command(BaseCommand):
    help = 'Set service account email for Teams integration and optionally verify it exists in Azure AD'

    def add_arguments(self, parser):
        parser.add_argument(
            '--integration-id',
            type=int,
            help='Teams integration ID to update (if not provided, updates first active integration)',
        )
        parser.add_argument(
            '--email',
            type=str,
            help='Service account email address (must exist in Azure AD with Exchange Online license)',
        )
        parser.add_argument(
            '--verify',
            action='store_true',
            help='Verify the email exists in Azure AD and has a mailbox before setting',
        )
        parser.add_argument(
            '--list',
            action='store_true',
            help='List all integrations and their current service account emails',
        )

    def handle(self, *args, **options):
        # Handle list option
        if options.get('list'):
            self.list_integrations()
            return

        # Validate email is provided
        new_email = options.get('email')
        if not new_email:
            self.stdout.write(self.style.ERROR('--email is required (unless using --list)'))
            return

        integration_id = options.get('integration_id')
        verify = options.get('verify', False)

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

        self.stdout.write('=' * 80)
        self.stdout.write(f'Integration: {integration.name} (ID: {integration.id})')
        self.stdout.write(f'Current service account email: {integration.service_account_email or "Not set"}')
        self.stdout.write(f'New service account email: {new_email}')
        self.stdout.write('=' * 80)

        # Verify the email exists in Azure AD
        if verify:
            self.stdout.write('\n📋 Verifying email exists in Azure AD...')
            try:
                client = TeamsAPIClient(integration)
                
                # Step 1: Check if user exists
                try:
                    self.stdout.write('  Step 1: Checking user existence...')
                    user_response = client._make_request('GET', f'/users/{new_email}')
                    
                    if user_response and 'id' in user_response:
                        self.stdout.write(self.style.SUCCESS('    ✓ User EXISTS in Azure AD'))
                        self.stdout.write(f'      Display Name: {user_response.get("displayName")}')
                        self.stdout.write(f'      User Principal Name: {user_response.get("userPrincipalName")}')
                        self.stdout.write(f'      Mail: {user_response.get("mail") or "N/A"}')
                        self.stdout.write(f'      Account Enabled: {user_response.get("accountEnabled", "Unknown")}')
                        
                        # Step 2: Check if user has a calendar/mailbox
                        self.stdout.write('\n  Step 2: Checking calendar/mailbox...')
                        try:
                            calendar_response = client._make_request('GET', f'/users/{new_email}/calendar')
                            if calendar_response and 'id' in calendar_response:
                                self.stdout.write(self.style.SUCCESS('    ✓ User has a calendar/mailbox'))
                                self.stdout.write(f'      Calendar Name: {calendar_response.get("name", "Default")}')
                        except TeamsAPIError as e:
                            if '404' in str(e):
                                self.stdout.write(self.style.ERROR('    ✗ User exists but has NO MAILBOX'))
                                self.stdout.write(self.style.WARNING(
                                    '\n      ⚠️  This user cannot create calendar events.'
                                ))
                                self.stdout.write('      Solutions:')
                                self.stdout.write('        1. Assign an Exchange Online license to this user')
                                self.stdout.write('        2. Use a different user email that has a mailbox')
                                return
                            else:
                                raise
                    else:
                        self.stdout.write(self.style.ERROR('    ✗ User not found in Azure AD'))
                        return
                        
                except TeamsAPIError as e:
                    if '404' in str(e) or 'not found' in str(e).lower():
                        self.stdout.write(self.style.ERROR(f'    ✗ User {new_email} NOT FOUND in Azure AD'))
                        self.stdout.write('\n📝 Next steps:')
                        self.stdout.write('  1. Create the user in Azure AD:')
                        self.stdout.write('     - Go to https://portal.azure.com')
                        self.stdout.write('     - Azure AD > Users > New user')
                        self.stdout.write(f'     - Set User Principal Name to: {new_email}')
                        self.stdout.write('     - Assign Exchange Online license')
                        self.stdout.write('  2. Try again with --verify flag')
                        self.stdout.write(f'  3. Or use a different email that exists in Azure AD')
                        return
                    else:
                        self.stdout.write(self.style.ERROR(f'Error verifying email: {str(e)}'))
                        return

            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Unexpected error during verification: {str(e)}'))
                return

            self.stdout.write('\n' + '=' * 80)

        # Update the service account email
        self.stdout.write(f'\n💾 Setting service account email...')
        integration.service_account_email = new_email
        integration.save()
        
        self.stdout.write(self.style.SUCCESS(f'\n✅ Service account email set successfully!'))
        self.stdout.write('\n📋 Next steps:')
        self.stdout.write('  1. Try creating a time slot with Teams meeting')
        self.stdout.write('  2. The system will use this service account email for Teams meetings')
        self.stdout.write(f'  3. Monitor logs for any issues')
        
        if not verify:
            self.stdout.write('\n⚠️  Note: Email was NOT verified. To verify, run:')
            self.stdout.write(f'  python manage.py set_service_account --integration-id {integration.id} --email {new_email} --verify')

    def list_integrations(self):
        """List all integrations and their service account emails"""
        integrations = TeamsIntegration.objects.all()
        
        if not integrations:
            self.stdout.write(self.style.WARNING('No Teams integrations found'))
            return

        self.stdout.write('=' * 100)
        self.stdout.write(f'{"ID":<5} {"Name":<25} {"Owner":<20} {"Service Account":<30} {"Active"}')
        self.stdout.write('=' * 100)
        
        for integration in integrations:
            owner = integration.user.username if integration.user else "None"
            service_email = integration.service_account_email or "Not set"
            active = "✓" if integration.is_active else "✗"
            
            self.stdout.write(
                f'{integration.id:<5} {integration.name:<25} {owner:<20} '
                f'{service_email:<30} {active}'
            )
        
        self.stdout.write('=' * 100)

