from django.core.management.base import BaseCommand
from role_management.models import Role, RoleCapability

class Command(BaseCommand):
    help = 'Add delete_users capability to existing admin roles'

    def handle(self, *args, **kwargs):
        self.stdout.write('Adding delete_users capability to admin roles...')
        
        # Find all admin roles
        admin_roles = Role.objects.filter(name='admin')
        
        for role in admin_roles:
            # Check if role already has delete_users capability
            if not role.capabilities.filter(capability='delete_users').exists():
                # Add the capability
                RoleCapability.objects.create(
                    role=role,
                    capability='delete_users',
                    description='Capability to delete users within branch scope',
                    is_active=True
                )
                self.stdout.write(
                    self.style.SUCCESS(f'✓ Added delete_users capability to role: {role}')
                )
            else:
                self.stdout.write(
                    f'- Role "{role}" already has delete_users capability'
                )
        
        if not admin_roles.exists():
            self.stdout.write(
                self.style.WARNING('No admin roles found in the system')
            )
        
        self.stdout.write(
            self.style.SUCCESS('Successfully updated admin roles with delete_users capability')
        ) 