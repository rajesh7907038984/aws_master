"""
Django management command to list users in Azure AD

Usage:
    python manage.py list_azure_ad_users
    python manage.py list_azure_ad_users --integration-id <id>
"""

from django.core.management.base import BaseCommand
from account_settings.models import TeamsIntegration
from teams_integration.utils.teams_api import TeamsAPIClient, TeamsAPIError


class Command(BaseCommand):
    help = 'List users from Azure AD to find valid email addresses for Teams integration'

    def add_arguments(self, parser):
        parser.add_argument(
            '--integration-id',
            type=int,
            help='Teams integration ID to use (defaults to first active integration)',
        )
        parser.add_argument(
            '--search',
            type=str,
            help='Search for users by name or email',
        )

    def handle(self, *args, **options):
        integration_id = options.get('integration_id')
        search_term = options.get('search')

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

        try:
            client = TeamsAPIClient(integration)
            
            # Build query parameters
            params = {
                '$top': 100
            }
            
            # Only add $select if we're not using $filter (some Azure AD configs don't allow both)
            if search_term:
                # Search filter
                params['$filter'] = f"startswith(displayName,'{search_term}') or startswith(userPrincipalName,'{search_term}')"
            else:
                params['$select'] = 'id,displayName,userPrincipalName,mail,accountEnabled'

            self.stdout.write('\nFetching users from Azure AD...\n')
            
            # Get users
            try:
                response = client._make_request('GET', '/users', params=params)
            except TeamsAPIError as e:
                # If the first attempt fails, try without $select
                if '400' in str(e):
                    self.stdout.write(self.style.WARNING('Retrying without $select parameter...\n'))
                    params = {'$top': 100}
                    response = client._make_request('GET', '/users', params=params)
                else:
                    raise
            
            users = response.get('value', [])
            
            if not users:
                self.stdout.write(self.style.WARNING('No users found'))
                return

            self.stdout.write(self.style.SUCCESS(f'Found {len(users)} users:\n'))
            
            # Display users in a table format
            self.stdout.write(f'{"Display Name":<30} {"Email / UPN":<50} {"Status":<10}')
            self.stdout.write('-' * 90)
            
            for user in users:
                display_name = user.get('displayName', 'N/A')[:29]
                email = user.get('mail') or user.get('userPrincipalName', 'N/A')
                email = email[:49]
                enabled = '✓ Active' if user.get('accountEnabled') else '✗ Disabled'
                
                self.stdout.write(f'{display_name:<30} {email:<50} {enabled:<10}')

            self.stdout.write('\n' + '=' * 80)
            self.stdout.write('\nTo use one of these emails for your Teams integration:')
            self.stdout.write('1. Copy the email address (or User Principal Name)')
            self.stdout.write('2. Run: python manage.py update_integration_owner_email \\')
            self.stdout.write(f'         --integration-id {integration.id} \\')
            self.stdout.write('         --email <copied-email> \\')
            self.stdout.write('         --verify')

        except TeamsAPIError as e:
            self.stdout.write(self.style.ERROR(f'\nError listing users: {str(e)}'))
            
            if '403' in str(e) or 'forbidden' in str(e).lower():
                self.stdout.write('\nThe error suggests insufficient permissions.')
                self.stdout.write('Please ensure the Azure AD app has the "User.Read.All" permission')
                self.stdout.write('and that admin consent has been granted.')
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'\nUnexpected error: {str(e)}'))

