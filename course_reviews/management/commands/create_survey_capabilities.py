"""
Management command to create capabilities for course review surveys
"""
from django.core.management.base import BaseCommand
from role_management.models import Role, RoleCapability


class Command(BaseCommand):
    help = 'Creates capabilities for course review survey management'

    def handle(self, *args, **options):
        """Create survey-related capabilities"""
        # Define capabilities
        capabilities = [
            {
                'capability': 'manage_surveys',
                'description': 'Can create, edit, and delete course review surveys',
                'roles': ['admin', 'instructor']
            },
            {
                'capability': 'view_surveys',
                'description': 'Can view course review surveys',
                'roles': ['admin', 'instructor']
            },
        ]

        created_count = 0

        for cap_data in capabilities:
            # Assign to roles
            for role_name in cap_data['roles']:
                try:
                    # Get the role object
                    role = Role.objects.filter(name=role_name).first()
                    if not role:
                        self.stdout.write(
                            self.style.WARNING(f'Role "{role_name}" not found, skipping...')
                        )
                        continue
                    
                    # Create or get the capability
                    role_capability, created = RoleCapability.objects.get_or_create(
                        role=role,
                        capability=cap_data['capability'],
                        defaults={
                            'description': cap_data['description'],
                            'is_active': True
                        }
                    )
                    
                    if created:
                        created_count += 1
                        self.stdout.write(
                            self.style.SUCCESS(
                                f'Created capability "{cap_data["capability"]}" for role "{role_name}"'
                            )
                        )
                    else:
                        # Update description if it changed
                        if role_capability.description != cap_data['description']:
                            role_capability.description = cap_data['description']
                            role_capability.save()
                            self.stdout.write(
                                self.style.WARNING(
                                    f'Updated capability "{cap_data["capability"]}" for role "{role_name}"'
                                )
                            )
                        else:
                            self.stdout.write(
                                self.style.WARNING(
                                    f'Capability "{cap_data["capability"]}" already exists for role "{role_name}"'
                                )
                            )
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(
                            f'Error creating capability "{cap_data["capability"]}" for role "{role_name}": {str(e)}'
                        )
                    )

        self.stdout.write(
            self.style.SUCCESS(
                f'\nSummary: Created {created_count} new capability assignments'
            )
        )
