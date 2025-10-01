"""
Management command to migrate SCORM Cloud configuration from global to branch-specific
"""

from django.core.management.base import BaseCommand, CommandError
from account_settings.models import GlobalAdminSettings, SCORMIntegration
from branches.models import Branch
from django.contrib.auth import get_user_model
import logging

logger = logging.getLogger(__name__)
User = get_user_model()


class Command(BaseCommand):
    help = 'Migrate SCORM Cloud configuration from global settings to branch-specific integrations'

    def add_arguments(self, parser):
        parser.add_argument(
            '--branch-id',
            type=int,
            help='Branch ID to create SCORM integration for (if not provided, will use first branch)',
        )
        parser.add_argument(
            '--user-id',
            type=int,
            help='User ID to associate with SCORM integration (if not provided, will use first superuser)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes',
        )

    def handle(self, *args, **options):
        try:
            # Check for existing branch-specific SCORM integrations
            from account_settings.models import SCORMIntegration
            existing_integrations = SCORMIntegration.objects.filter(is_active=True)
            
            if existing_integrations.exists():
                self.stdout.write("✅ Branch-specific SCORM integrations already exist:")
                for integration in existing_integrations:
                    self.stdout.write(f"   - {integration.name} (Branch: {integration.branch.name if integration.branch else 'No branch'})")
                return
            
            self.stdout.write("🔧 Setting up branch-specific SCORM integration...")
            self.stdout.write("⚠️  Note: Global SCORM settings have been removed. You need to configure SCORM credentials per branch.")
            
            # Get target branch
            if options['branch_id']:
                try:
                    branch = Branch.objects.get(id=options['branch_id'])
                except Branch.DoesNotExist:
                    raise CommandError(f"Branch with ID {options['branch_id']} not found")
            else:
                branch = Branch.objects.first()
                if not branch:
                    raise CommandError("No branches found. Please create a branch first.")
            
            self.stdout.write(f"   Target Branch: {branch.name} (ID: {branch.id})")
            
            # Get target user
            if options['user_id']:
                try:
                    user = User.objects.get(id=options['user_id'])
                except User.DoesNotExist:
                    raise CommandError(f"User with ID {options['user_id']} not found")
            else:
                user = User.objects.filter(is_superuser=True).first()
                if not user:
                    user = User.objects.first()
                    if not user:
                        raise CommandError("No users found. Please create a user first.")
            
            self.stdout.write(f"   Target User: {user.username} (ID: {user.id})")
            
            if options['dry_run']:
                self.stdout.write(self.style.WARNING("🔍 DRY RUN - No changes will be made"))
                return
            
            # Enable SCORM integration for the branch
            branch.scorm_integration_enabled = True
            branch.save()
            self.stdout.write(f"✅ Enabled SCORM integration for branch {branch.name}")
            
            self.stdout.write(self.style.SUCCESS("🎉 Branch SCORM integration setup completed!"))
            self.stdout.write("")
            self.stdout.write("Next steps:")
            self.stdout.write("1. Configure SCORM credentials in Account Settings → Integrations → SCORM Cloud")
            self.stdout.write("2. Test SCORM launch after configuring credentials")
            self.stdout.write("3. Verify branch SCORM settings in admin panel")
            
        except Exception as e:
            raise CommandError(f"Setup failed: {str(e)}")
