"""
Django management command to update Teams integration owner email

Usage:
    python manage.py update_integration_owner_email --integration-id <id> --email <email>
"""

from django.core.management.base import BaseCommand
from account_settings.models import TeamsIntegration
from teams_integration.utils.teams_api import TeamsAPIClient, TeamsAPIError


class Command(BaseCommand):
    help = 'Update Teams integration owner email and verify it exists in Azure AD'

    def add_arguments(self, parser):
        parser.add_argument(
            '--integration-id',
            type=int,
            required=True,
            help='Teams integration ID to update',
        )
        parser.add_argument(
            '--email',
            type=str,
            required=True,
            help='New email address (must exist in Azure AD)',
        )
        parser.add_argument(
            '--verify',
            action='store_true',
            help='Verify the email exists in Azure AD before updating',
        )

    def handle(self, *args, **options):
        integration_id = options['integration_id']
        new_email = options['email']
        verify = options.get('verify', False)

        try:
            integration = TeamsIntegration.objects.get(id=integration_id)
        except TeamsIntegration.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'Integration with ID {integration_id} not found'))
            return

        self.stdout.write(f'Found integration: {integration.name}')
        
        if not integration.user:
            self.stdout.write(self.style.ERROR('Integration has no owner user assigned'))
            return

        old_email = integration.user.email
        self.stdout.write(f'Current email: {old_email}')
        self.stdout.write(f'New email: {new_email}')

        # Verify the email exists in Azure AD
        if verify:
            self.stdout.write('\nVerifying email exists in Azure AD...')
            try:
                client = TeamsAPIClient(integration)
                
                # Try to get the user from Azure AD
                endpoint = f'/users/{new_email}'
                response = client._make_request('GET', endpoint)
                
                if response and 'id' in response:
                    self.stdout.write(self.style.SUCCESS(f'✓ User found in Azure AD:'))
                    self.stdout.write(f'  Display Name: {response.get("displayName")}')
                    self.stdout.write(f'  User Principal Name: {response.get("userPrincipalName")}')
                    self.stdout.write(f'  Mail: {response.get("mail")}')
                    
                    # Check if they have a mailbox
                    try:
                        calendar_endpoint = f'/users/{new_email}/calendar'
                        calendar_response = client._make_request('GET', calendar_endpoint)
                        self.stdout.write(self.style.SUCCESS(f'✓ User has a calendar/mailbox'))
                    except TeamsAPIError as e:
                        if '404' in str(e):
                            self.stdout.write(self.style.ERROR(f'✗ User exists but has NO MAILBOX'))
                            self.stdout.write(self.style.WARNING(
                                '  This user cannot create calendar events. '
                                'Ensure they have an Exchange Online license.'
                            ))
                            return
                        else:
                            raise
                else:
                    self.stdout.write(self.style.ERROR(f'✗ User not found in Azure AD'))
                    return
                    
            except TeamsAPIError as e:
                if '404' in str(e) or 'not found' in str(e).lower():
                    self.stdout.write(self.style.ERROR(f'✗ User {new_email} NOT FOUND in Azure AD'))
                    self.stdout.write('\nPossible solutions:')
                    self.stdout.write('1. Create the user in Azure AD')
                    self.stdout.write('2. Use a different email that exists in Azure AD')
                    self.stdout.write('3. List all Azure AD users with: python manage.py list_azure_ad_users')
                    return
                else:
                    self.stdout.write(self.style.ERROR(f'Error verifying email: {str(e)}'))
                    return

        # Update the email
        self.stdout.write(f'\nUpdating email...')
        integration.user.email = new_email
        integration.user.save()
        
        self.stdout.write(self.style.SUCCESS(f'✓ Email updated successfully'))
        self.stdout.write(f'\nTo verify the change, run:')
        self.stdout.write(f'  python manage.py diagnose_teams_integration --integration-id {integration_id}')

