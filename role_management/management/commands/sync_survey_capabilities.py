"""
Management command to sync survey capabilities to existing roles
"""
from django.core.management.base import BaseCommand
from role_management.models import Role, RoleCapability
from django.db import transaction


class Command(BaseCommand):
    help = 'Syncs survey capabilities to existing roles based on default definitions'

    def handle(self, *args, **options):
        """Sync survey-related capabilities to existing roles"""
        
        # Define survey capabilities for each role
        survey_capabilities = {
            'globaladmin': ['view_surveys', 'manage_surveys', 'view_survey_responses'],
            'superadmin': ['view_surveys', 'manage_surveys', 'view_survey_responses'],
            'admin': ['view_surveys', 'manage_surveys', 'view_survey_responses'],
            'instructor': ['view_surveys', 'manage_surveys'],
        }

        created_count = 0
        updated_count = 0
        
        with transaction.atomic():
            for role_name, capabilities in survey_capabilities.items():
                try:
                    # Get all roles with this name (there should be only one for system roles)
                    roles = Role.objects.filter(name=role_name)
                    
                    if not roles.exists():
                        self.stdout.write(
                            self.style.WARNING(f'No role found with name "{role_name}", skipping...')
                        )
                        continue
                    
                    for role in roles:
                        for capability in capabilities:
                            # Create or get the capability
                            role_capability, created = RoleCapability.objects.get_or_create(
                                role=role,
                                capability=capability,
                                defaults={
                                    'description': f'Survey management capability: {capability}',
                                    'is_active': True
                                }
                            )
                            
                            if created:
                                created_count += 1
                                self.stdout.write(
                                    self.style.SUCCESS(
                                        f'✓ Created capability "{capability}" for role "{role_name}" (ID: {role.id})'
                                    )
                                )
                            else:
                                # Ensure it's active
                                if not role_capability.is_active:
                                    role_capability.is_active = True
                                    role_capability.save()
                                    updated_count += 1
                                    self.stdout.write(
                                        self.style.WARNING(
                                            f'✓ Activated capability "{capability}" for role "{role_name}" (ID: {role.id})'
                                        )
                                    )
                                else:
                                    self.stdout.write(
                                        f'  Capability "{capability}" already exists for role "{role_name}" (ID: {role.id})'
                                    )
                
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(
                            f'✗ Error processing role "{role_name}": {str(e)}'
                        )
                    )

        self.stdout.write('')
        self.stdout.write(
            self.style.SUCCESS(
                f'════════════════════════════════════════════'
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                f'Summary: Created {created_count} new capabilities, '
                f'activated {updated_count} existing capabilities'
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                f'════════════════════════════════════════════'
            )
        )
        
        # Clear capability caches
        from django.core.cache import cache
        cache_keys = []
        for role in Role.objects.all():
            cache_keys.append(f"role_capabilities_{role.pk}")
        
        if cache_keys:
            try:
                cache.delete_many(cache_keys)
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Cleared {len(cache_keys)} capability caches'
                    )
                )
            except Exception as e:
                self.stdout.write(
                    self.style.WARNING(
                        f'Note: Could not clear caches (this is okay): {str(e)}'
                    )
                )
