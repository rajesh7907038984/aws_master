"""
Management command to populate default roles and their capabilities.
This should be run after migrations to ensure the role management system has all default roles.
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from role_management.models import Role, RoleCapability
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Populate default roles and their capabilities for the role management system'

    def add_arguments(self, parser):
        parser.add_argument(
            '--recreate',
            action='store_true',
            help='Delete existing roles and recreate them',
        )

    def handle(self, *args, **options):
        recreate = options.get('recreate', False)

        self.stdout.write(self.style.SUCCESS('Starting role population...'))

        # Define default roles
        default_roles = [
            {
                'name': 'globaladmin',
                'description': 'Global Administrator with system-wide access and control over all businesses, branches, and users.',
            },
            {
                'name': 'superadmin',
                'description': 'Super Administrator with business-level access and control over assigned businesses and branches.',
            },
            {
                'name': 'admin',
                'description': 'Branch Administrator with branch-level access and control over branch users and content.',
            },
            {
                'name': 'instructor',
                'description': 'Instructor with ability to create and manage courses, assignments, and grade students.',
            },
            {
                'name': 'learner',
                'description': 'Learner with access to view courses, submit assignments, and take quizzes.',
            },
        ]

        with transaction.atomic():
            if recreate:
                self.stdout.write(self.style.WARNING('Recreate mode: Deleting existing default roles...'))
                Role.objects.filter(name__in=[r['name'] for r in default_roles]).delete()

            for role_data in default_roles:
                role_name = role_data['name']
                
                # Check if role already exists
                role, created = Role.objects.get_or_create(
                    name=role_name,
                    defaults={
                        'description': role_data['description'],
                        'is_active': True,
                    }
                )

                if created:
                    self.stdout.write(self.style.SUCCESS(f'✓ Created role: {role_name}'))
                else:
                    self.stdout.write(self.style.WARNING(f'→ Role already exists: {role_name}'))
                    # Update description if it has changed
                    if role.description != role_data['description']:
                        role.description = role_data['description']
                        role.save()
                        self.stdout.write(self.style.SUCCESS(f'  Updated description for: {role_name}'))

                # Get default capabilities for this role
                default_capabilities = Role.objects.get_default_capabilities(role_name)
                
                # Get existing capabilities
                existing_capabilities = set(
                    role.capabilities.values_list('capability', flat=True)
                )

                # Add missing capabilities
                capabilities_added = 0
                for capability in default_capabilities:
                    if capability not in existing_capabilities:
                        RoleCapability.objects.create(
                            role=role,
                            capability=capability,
                            description=f'{capability.replace("_", " ").title()} capability',
                            is_active=True,
                        )
                        capabilities_added += 1

                if capabilities_added > 0:
                    self.stdout.write(
                        self.style.SUCCESS(f'  Added {capabilities_added} capabilities to {role_name}')
                    )
                else:
                    self.stdout.write(f'  All capabilities already exist for {role_name}')

                # Show total capabilities for this role
                total_capabilities = role.capabilities.count()
                self.stdout.write(f'  Total capabilities: {total_capabilities}')

        self.stdout.write(self.style.SUCCESS('\n✓ Role population completed successfully!'))
        
        # Show summary
        self.stdout.write('\n' + '='*60)
        self.stdout.write(self.style.SUCCESS('SUMMARY'))
        self.stdout.write('='*60)
        
        for role in Role.objects.filter(name__in=[r['name'] for r in default_roles]).order_by('id'):
            capability_count = role.capabilities.filter(is_active=True).count()
            user_count = role.user_roles.filter(is_active=True).count()
            self.stdout.write(
                f'{role.get_name_display():15} - {capability_count:2} capabilities, {user_count:3} users'
            )
        
        self.stdout.write('='*60)
