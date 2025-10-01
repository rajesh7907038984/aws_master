from django.core.management.base import BaseCommand
from django.db import transaction
from django.contrib.auth import get_user_model
from business.models import Business, BusinessUserAssignment, BusinessLimits
from branches.models import Branch
from users.models import CustomUser

User = get_user_model()

class Command(BaseCommand):
    help = 'Setup default business and branch assignments for proper LMS hierarchy'

    def add_arguments(self, parser):
        parser.add_argument(
            '--create-defaults',
            action='store_true',
            help='Create default business and branches if they don\'t exist',
        )
        parser.add_argument(
            '--assign-users',
            action='store_true',
            help='Assign existing users without business/branch to defaults',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('🔍 DRY RUN MODE - No changes will be made')
            )
        
        self.stdout.write('🏢 Setting up default business and branch assignments...\n')
        
        try:
            with transaction.atomic():
                if options['create_defaults']:
                    self.create_default_structures(dry_run)
                
                if options['assign_users']:
                    self.assign_users_to_defaults(dry_run)
                    
                self.display_summary()
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error setting up default assignments: {str(e)}')
            )
            raise

    def create_default_structures(self, dry_run):
        """Create default business and branches if they don't exist"""
        self.stdout.write('📋 Creating default business and branch structures...')
        
        # 1. Create or get default business
        default_business_name = "Default Business"
        default_business = Business.objects.filter(name=default_business_name).first()
        
        if not default_business:
            if dry_run:
                self.stdout.write(
                    self.style.WARNING(f'   Would create default business: "{default_business_name}"')
                )
            else:
                default_business = Business.objects.create(
                    name=default_business_name,
                    description="Default business for users without specific business assignment",
                    is_active=True,
                    address_line1="Not Specified",
                    city="Not Specified",
                    country="United Kingdom"
                )
                self.stdout.write(
                    self.style.SUCCESS(f'   ✅ Created default business: {default_business.name}')
                )
        else:
            self.stdout.write(f'   ✅ Default business already exists: {default_business.name}')
        
        # 2. Create or get default branch
        if not dry_run and default_business:
            default_branch = default_business.get_default_branch()
            if not default_branch:
                default_branch = default_business.create_default_branch()
                self.stdout.write(
                    self.style.SUCCESS(f'   ✅ Created default branch: {default_branch.name}')
                )
            else:
                self.stdout.write(f'   ✅ Default branch already exists: {default_branch.name}')
        elif dry_run:
            self.stdout.write(
                self.style.WARNING(f'   Would create default branch for business')
            )
        
        # 3. Create business limits if they don't exist
        if not dry_run and default_business:
            business_limits, created = BusinessLimits.objects.get_or_create(
                business=default_business,
                defaults={
                    'total_user_limit': 1000,  # Higher limit for default business
                    'branch_creation_limit': 50,
                }
            )
            if created:
                self.stdout.write(
                    self.style.SUCCESS(f'   ✅ Created business limits for {default_business.name}')
                )
            else:
                self.stdout.write(f'   ✅ Business limits already exist for {default_business.name}')
        elif dry_run:
            self.stdout.write(
                self.style.WARNING(f'   Would create business limits')
            )

    def assign_users_to_defaults(self, dry_run):
        """Assign users without business/branch to default structures"""
        self.stdout.write('👥 Assigning users to default business/branch...')
        
        # Get default structures
        default_business = Business.objects.filter(name="Default Business").first()
        if not default_business:
            self.stdout.write(
                self.style.ERROR('   ❌ Default business not found. Run with --create-defaults first.')
            )
            return
        
        default_branch = default_business.get_default_branch()
        if not default_branch:
            if not dry_run:
                default_branch = default_business.create_default_branch()
            else:
                self.stdout.write(
                    self.style.WARNING('   Would create default branch')
                )
                return
        
        # 1. Handle Super Admin users without business assignments
        unassigned_superadmins = CustomUser.objects.filter(
            role='superadmin',
            is_active=True,
            business_assignments__isnull=True
        )
        
        if unassigned_superadmins.exists():
            self.stdout.write(f'   📋 Found {unassigned_superadmins.count()} Super Admin users without business assignments')
            
            for superadmin in unassigned_superadmins:
                if dry_run:
                    self.stdout.write(
                        self.style.WARNING(f'     Would assign {superadmin.username} to {default_business.name}')
                    )
                else:
                    BusinessUserAssignment.objects.create(
                        business=default_business,
                        user=superadmin,
                        is_active=True
                    )
                    # The signal handler will automatically assign them to the default branch
                    self.stdout.write(
                        self.style.SUCCESS(f'     ✅ Assigned {superadmin.username} to {default_business.name}')
                    )
        
        # 2. Handle Admin/Instructor/Learner users without branch assignments
        unassigned_users = CustomUser.objects.filter(
            role__in=['admin', 'instructor', 'learner'],
            is_active=True,
            branch__isnull=True
        )
        
        if unassigned_users.exists():
            self.stdout.write(f'   📋 Found {unassigned_users.count()} users without branch assignments')
            
            for user in unassigned_users:
                if dry_run:
                    self.stdout.write(
                        self.style.WARNING(f'     Would assign {user.username} ({user.role}) to {default_branch.name}')
                    )
                else:
                    user.branch = default_branch
                    user.save()
                    self.stdout.write(
                        self.style.SUCCESS(f'     ✅ Assigned {user.username} ({user.role}) to {default_branch.name}')
                    )
        
        # 3. Ensure Global Admin users don't have branch assignments (they shouldn't)
        global_admins_with_branches = CustomUser.objects.filter(
            role='globaladmin',
            is_active=True,
            branch__isnull=False
        )
        
        if global_admins_with_branches.exists():
            self.stdout.write(f'   ⚠️  Found {global_admins_with_branches.count()} Global Admin users with branch assignments (cleaning up)')
            
            for global_admin in global_admins_with_branches:
                if dry_run:
                    self.stdout.write(
                        self.style.WARNING(f'     Would remove branch assignment from {global_admin.username}')
                    )
                else:
                    global_admin.branch = None
                    global_admin.save()
                    self.stdout.write(
                        self.style.SUCCESS(f'     ✅ Removed branch assignment from {global_admin.username}')
                    )

    def display_summary(self):
        """Display current system summary"""
        self.stdout.write('\n📊 Current System Summary:')
        
        # Business count
        business_count = Business.objects.filter(is_active=True).count()
        self.stdout.write(f'   Total Active Businesses: {business_count}')
        
        # Branch count
        branch_count = Branch.objects.filter(is_active=True).count()
        self.stdout.write(f'   Total Active Branches: {branch_count}')
        
        # User counts by role
        for role, role_name in CustomUser.ROLE_CHOICES:
            count = CustomUser.objects.filter(role=role, is_active=True).count()
            self.stdout.write(f'   {role_name} Users: {count}')
        
        # Users without proper assignments
        unassigned_superadmins = CustomUser.objects.filter(
            role='superadmin',
            is_active=True,
            business_assignments__isnull=True
        ).count()
        
        unassigned_users = CustomUser.objects.filter(
            role__in=['admin', 'instructor', 'learner'],
            is_active=True,
            branch__isnull=True
        ).count()
        
        if unassigned_superadmins > 0:
            self.stdout.write(
                self.style.WARNING(f'   ⚠️  Super Admins without business assignment: {unassigned_superadmins}')
            )
        
        if unassigned_users > 0:
            self.stdout.write(
                self.style.WARNING(f'   ⚠️  Users without branch assignment: {unassigned_users}')
            )
        
        if unassigned_superadmins == 0 and unassigned_users == 0:
            self.stdout.write(
                self.style.SUCCESS('   ✅ All users properly assigned to business/branch structures!')
            )
