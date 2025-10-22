from django.core.management.base import BaseCommand
from django.db import transaction
from django.contrib.auth import get_user_model
from django.utils import timezone
from business.models import Business, BusinessUserAssignment, BusinessLimits
from branches.models import Branch, BranchUserLimits, AdminBranchAssignment
from users.models import CustomUser
import logging

User = get_user_model()
logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Create comprehensive test data for LMS including all user roles, businesses, and branches'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clean',
            action='store_true',
            help='Clean existing test data before creating new data',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        clean = options['clean']
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('🔍 DRY RUN MODE - No changes will be made')
            )
        
        self.stdout.write('🏢 Creating comprehensive test data for LMS...\n')
        
        try:
            with transaction.atomic():
                if clean:
                    self.clean_test_data(dry_run)
                
                # Create test business
                test_business = self.create_test_business(dry_run)
                
                # Create test branches
                branches = self.create_test_branches(test_business, dry_run)
                
                # Create test users
                self.create_test_users(test_business, branches, dry_run)
                
                # Create business and branch limits
                self.create_limits(test_business, branches, dry_run)
                
                self.display_summary()
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error creating test data: {str(e)}')
            )
            logger.error(f'Error creating test data: {str(e)}', exc_info=True)
            raise

    def clean_test_data(self, dry_run):
        """Clean existing test data"""
        self.stdout.write('🧹 Cleaning existing test data...')
        
        # Clean test users
        test_users = CustomUser.objects.filter(
            username__endswith='_test',
            email__endswith='@testlms.com'
        )
        
        if test_users.exists():
            if dry_run:
                self.stdout.write(
                    self.style.WARNING(f'   Would delete {test_users.count()} test users')
                )
            else:
                test_users.delete()
                self.stdout.write(
                    self.style.SUCCESS(f'   Deleted {test_users.count()} test users')
                )
        
        # Clean test branches
        test_branches = Branch.objects.filter(
            name__in=[
                'Central London', 'North London', 'South London', 'East London',
                'Manchester Central', 'Manchester North', 'Birmingham Central', 'Birmingham South',
                'Leeds Main', 'Leeds West', 'Liverpool Central', 'Liverpool North',
                'Bristol Central', 'Cardiff Main', 'Newcastle Central', 'Edinburgh Main'
            ]
        )
        
        if test_branches.exists():
            if dry_run:
                self.stdout.write(
                    self.style.WARNING(f'   Would delete {test_branches.count()} test branches')
                )
            else:
                test_branches.delete()
                self.stdout.write(
                    self.style.SUCCESS(f'   Deleted {test_branches.count()} test branches')
                )
        
        # Clean test business
        test_business = Business.objects.filter(name='Test Business Company').first()
        if test_business:
            if dry_run:
                self.stdout.write(
                    self.style.WARNING(f'   Would delete test business: {test_business.name}')
                )
            else:
                test_business.delete()
                self.stdout.write(
                    self.style.SUCCESS(f'   Deleted test business: {test_business.name}')
                )

    def create_test_business(self, dry_run):
        """Create test business"""
        self.stdout.write('🏢 Creating test business...')
        
        business_name = 'Test Business Company'
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING(f'   Would create business: {business_name}')
            )
            return None
        
        business, created = Business.objects.get_or_create(
            name=business_name,
            defaults={
                'description': 'Test business for comprehensive LMS testing',
                'is_active': True,
                'address_line1': '123 Test Street',
                'city': 'London',
                'country': 'United Kingdom',
                'phone': '+44 20 1234 5678',
                'email': 'contact@testbusiness.com',
                'website': 'https://testbusiness.com'
            }
        )
        
        if created:
            self.stdout.write(
                self.style.SUCCESS(f'   Created business: {business.name}')
            )
        else:
            self.stdout.write(f'   Business already exists: {business.name}')
        
        return business

    def create_test_branches(self, business, dry_run):
        """Create test branches"""
        self.stdout.write('🏢 Creating test branches...')
        
        branch_data = [
            # London Area (Admin1's Branches)
            {'name': 'Central London', 'description': 'Central London branch'},
            {'name': 'North London', 'description': 'North London branch'},
            {'name': 'South London', 'description': 'South London branch'},
            {'name': 'East London', 'description': 'East London branch'},
            
            # Midlands (Admin2's Branches)
            {'name': 'Manchester Central', 'description': 'Manchester Central branch'},
            {'name': 'Manchester North', 'description': 'Manchester North branch'},
            {'name': 'Birmingham Central', 'description': 'Birmingham Central branch'},
            {'name': 'Birmingham South', 'description': 'Birmingham South branch'},
            
            # North (Admin3's Branches)
            {'name': 'Leeds Main', 'description': 'Leeds Main branch'},
            {'name': 'Leeds West', 'description': 'Leeds West branch'},
            {'name': 'Liverpool Central', 'description': 'Liverpool Central branch'},
            {'name': 'Liverpool North', 'description': 'Liverpool North branch'},
            
            # Wales/Scotland (Admin4's Branches)
            {'name': 'Bristol Central', 'description': 'Bristol Central branch'},
            {'name': 'Cardiff Main', 'description': 'Cardiff Main branch'},
            {'name': 'Newcastle Central', 'description': 'Newcastle Central branch'},
            {'name': 'Edinburgh Main', 'description': 'Edinburgh Main branch'},
        ]
        
        branches = []
        
        for branch_info in branch_data:
            if dry_run:
                self.stdout.write(
                    self.style.WARNING(f'   Would create branch: {branch_info["name"]}')
                )
                branches.append(None)
            else:
                branch, created = Branch.objects.get_or_create(
                    name=branch_info['name'],
                    business=business,
                    defaults={
                        'description': branch_info['description'],
                        'is_active': True
                    }
                )
                
                if created:
                    self.stdout.write(
                        self.style.SUCCESS(f'   Created branch: {branch.name}')
                    )
                else:
                    self.stdout.write(f'   Branch already exists: {branch.name}')
                
                branches.append(branch)
        
        return branches

    def create_test_users(self, business, branches, dry_run):
        """Create comprehensive test users"""
        self.stdout.write('👥 Creating test users...')
        
        # Create Global Admin
        self.create_global_admin(dry_run)
        
        # Create Super Admins
        self.create_super_admins(business, dry_run)
        
        # Create Branch Admins
        self.create_branch_admins(business, branches, dry_run)
        
        # Create Instructors
        self.create_instructors(branches, dry_run)
        
        # Create Learners
        self.create_learners(branches, dry_run)

    def create_global_admin(self, dry_run):
        """Create Global Admin user"""
        username = 'globaladmin_test'
        email = 'globaladmin@testlms.com'
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING(f'   Would create Global Admin: {username}')
            )
            return
        
        user, created = CustomUser.objects.get_or_create(
            username=username,
            defaults={
                'email': email,
                'first_name': 'Global',
                'last_name': 'Admin',
                'role': 'globaladmin',
                'is_active': True,
                'is_staff': True,
                'is_superuser': True
            }
        )
        
        if created:
            user.set_password('test123')
            user.save()
            self.stdout.write(
                self.style.SUCCESS(f'   Created Global Admin: {username}')
            )
        else:
            self.stdout.write(f'   Global Admin already exists: {username}')

    def create_super_admins(self, business, dry_run):
        """Create Super Admin users"""
        super_admins = [
            {
                'username': 'superadmin1_test',
                'email': 'superadmin1@testlms.com',
                'first_name': 'Super',
                'last_name': 'Admin One'
            },
            {
                'username': 'superadmin2_test',
                'email': 'superadmin2@testlms.com',
                'first_name': 'Super',
                'last_name': 'Admin Two'
            }
        ]
        
        for admin_data in super_admins:
            if dry_run:
                self.stdout.write(
                    self.style.WARNING(f'   Would create Super Admin: {admin_data["username"]}')
                )
                continue
            
            user, created = CustomUser.objects.get_or_create(
                username=admin_data['username'],
                defaults={
                    'email': admin_data['email'],
                    'first_name': admin_data['first_name'],
                    'last_name': admin_data['last_name'],
                    'role': 'superadmin',
                    'is_active': True,
                    'is_staff': True
                }
            )
            
            if created:
                user.set_password('test123')
                user.save()
                
                # Assign to business
                BusinessUserAssignment.objects.get_or_create(
                    business=business,
                    user=user,
                    defaults={'is_active': True}
                )
                
                self.stdout.write(
                    self.style.SUCCESS(f'   Created Super Admin: {admin_data["username"]}')
                )
            else:
                self.stdout.write(f'   Super Admin already exists: {admin_data["username"]}')

    def create_branch_admins(self, business, branches, dry_run):
        """Create Branch Admin users"""
        admin_assignments = [
            {
                'username': 'admin1_test',
                'email': 'admin1@testlms.com',
                'first_name': 'Admin',
                'last_name': 'One',
                'primary_branch': 'Central London',
                'additional_branches': ['North London', 'South London', 'East London']
            },
            {
                'username': 'admin2_test',
                'email': 'admin2@testlms.com',
                'first_name': 'Admin',
                'last_name': 'Two',
                'primary_branch': 'Manchester Central',
                'additional_branches': ['Manchester North', 'Birmingham Central', 'Birmingham South']
            },
            {
                'username': 'admin3_test',
                'email': 'admin3@testlms.com',
                'first_name': 'Admin',
                'last_name': 'Three',
                'primary_branch': 'Leeds Main',
                'additional_branches': ['Leeds West', 'Liverpool Central', 'Liverpool North']
            },
            {
                'username': 'admin4_test',
                'email': 'admin4@testlms.com',
                'first_name': 'Admin',
                'last_name': 'Four',
                'primary_branch': 'Bristol Central',
                'additional_branches': ['Cardiff Main', 'Newcastle Central', 'Edinburgh Main']
            }
        ]
        
        for admin_data in admin_assignments:
            if dry_run:
                self.stdout.write(
                    self.style.WARNING(f'   Would create Branch Admin: {admin_data["username"]}')
                )
                continue
            
            # Find primary branch
            primary_branch = None
            for branch in branches:
                if branch and branch.name == admin_data['primary_branch']:
                    primary_branch = branch
                    break
            
            if not primary_branch:
                self.stdout.write(
                    self.style.ERROR(f'   Primary branch not found: {admin_data["primary_branch"]}')
                )
                continue
            
            user, created = CustomUser.objects.get_or_create(
                username=admin_data['username'],
                defaults={
                    'email': admin_data['email'],
                    'first_name': admin_data['first_name'],
                    'last_name': admin_data['last_name'],
                    'role': 'admin',
                    'is_active': True,
                    'branch': primary_branch
                }
            )
            
            if created:
                user.set_password('test123')
                user.save()
                
                # Create additional branch assignments
                for additional_branch_name in admin_data['additional_branches']:
                    additional_branch = None
                    for branch in branches:
                        if branch and branch.name == additional_branch_name:
                            additional_branch = branch
                            break
                    
                    if additional_branch:
                        AdminBranchAssignment.objects.get_or_create(
                            user=user,
                            branch=additional_branch,
                            defaults={'is_active': True}
                        )
                
                self.stdout.write(
                    self.style.SUCCESS(f'   Created Branch Admin: {admin_data["username"]}')
                )
            else:
                self.stdout.write(f'   Branch Admin already exists: {admin_data["username"]}')

    def create_instructors(self, branches, dry_run):
        """Create Instructor users"""
        instructor_data = [
            # London Area (Admin1's Branches)
            {'branch': 'Central London', 'count': 2, 'prefix': 'branch1'},
            {'branch': 'North London', 'count': 2, 'prefix': 'branch2'},
            {'branch': 'South London', 'count': 2, 'prefix': 'branch3'},
            {'branch': 'East London', 'count': 2, 'prefix': 'branch4'},
            
            # Midlands (Admin2's Branches)
            {'branch': 'Manchester Central', 'count': 2, 'prefix': 'branch5'},
            {'branch': 'Manchester North', 'count': 2, 'prefix': 'branch6'},
            {'branch': 'Birmingham Central', 'count': 2, 'prefix': 'branch7'},
            {'branch': 'Birmingham South', 'count': 2, 'prefix': 'branch8'},
            
            # North (Admin3's Branches)
            {'branch': 'Leeds Main', 'count': 2, 'prefix': 'branch9'},
            {'branch': 'Leeds West', 'count': 2, 'prefix': 'branch10'},
            {'branch': 'Liverpool Central', 'count': 2, 'prefix': 'branch11'},
            {'branch': 'Liverpool North', 'count': 2, 'prefix': 'branch12'},
            
            # Wales/Scotland (Admin4's Branches)
            {'branch': 'Bristol Central', 'count': 2, 'prefix': 'branch13'},
            {'branch': 'Cardiff Main', 'count': 2, 'prefix': 'branch14'},
            {'branch': 'Newcastle Central', 'count': 2, 'prefix': 'branch15'},
            {'branch': 'Edinburgh Main', 'count': 2, 'prefix': 'branch16'},
        ]
        
        for data in instructor_data:
            # Find the branch
            target_branch = None
            for branch in branches:
                if branch and branch.name == data['branch']:
                    target_branch = branch
                    break
            
            if not target_branch:
                self.stdout.write(
                    self.style.ERROR(f'   Branch not found: {data["branch"]}')
                )
                continue
            
            for i in range(1, data['count'] + 1):
                username = f'instructor{i}_{data["prefix"]}_test'
                email = f'instructor{i}_{data["prefix"]}@testlms.com'
                
                if dry_run:
                    self.stdout.write(
                        self.style.WARNING(f'   Would create Instructor: {username}')
                    )
                    continue
                
                user, created = CustomUser.objects.get_or_create(
                    username=username,
                    defaults={
                        'email': email,
                        'first_name': f'Instructor{i}',
                        'last_name': f'{data["branch"]}',
                        'role': 'instructor',
                        'is_active': True,
                        'branch': target_branch
                    }
                )
                
                if created:
                    user.set_password('test123')
                    user.save()
                    self.stdout.write(
                        self.style.SUCCESS(f'   Created Instructor: {username}')
                    )
                else:
                    self.stdout.write(f'   Instructor already exists: {username}')

    def create_learners(self, branches, dry_run):
        """Create Learner users"""
        learner_data = [
            # London Area (Admin1's Branches)
            {'branch': 'Central London', 'count': 3, 'prefix': 'branch1'},
            {'branch': 'North London', 'count': 3, 'prefix': 'branch2'},
            {'branch': 'South London', 'count': 3, 'prefix': 'branch3'},
            {'branch': 'East London', 'count': 3, 'prefix': 'branch4'},
            
            # Midlands (Admin2's Branches)
            {'branch': 'Manchester Central', 'count': 3, 'prefix': 'branch5'},
            {'branch': 'Manchester North', 'count': 3, 'prefix': 'branch6'},
            {'branch': 'Birmingham Central', 'count': 3, 'prefix': 'branch7'},
            {'branch': 'Birmingham South', 'count': 3, 'prefix': 'branch8'},
            
            # North (Admin3's Branches)
            {'branch': 'Leeds Main', 'count': 3, 'prefix': 'branch9'},
            {'branch': 'Leeds West', 'count': 3, 'prefix': 'branch10'},
            {'branch': 'Liverpool Central', 'count': 3, 'prefix': 'branch11'},
            {'branch': 'Liverpool North', 'count': 3, 'prefix': 'branch12'},
            
            # Wales/Scotland (Admin4's Branches)
            {'branch': 'Bristol Central', 'count': 3, 'prefix': 'branch13'},
            {'branch': 'Cardiff Main', 'count': 3, 'prefix': 'branch14'},
            {'branch': 'Newcastle Central', 'count': 3, 'prefix': 'branch15'},
            {'branch': 'Edinburgh Main', 'count': 3, 'prefix': 'branch16'},
        ]
        
        for data in learner_data:
            # Find the branch
            target_branch = None
            for branch in branches:
                if branch and branch.name == data['branch']:
                    target_branch = branch
                    break
            
            if not target_branch:
                self.stdout.write(
                    self.style.ERROR(f'   Branch not found: {data["branch"]}')
                )
                continue
            
            for i in range(1, data['count'] + 1):
                username = f'learner{i}_{data["prefix"]}_test'
                email = f'learner{i}_{data["prefix"]}@testlms.com'
                
                if dry_run:
                    self.stdout.write(
                        self.style.WARNING(f'   Would create Learner: {username}')
                    )
                    continue
                
                user, created = CustomUser.objects.get_or_create(
                    username=username,
                    defaults={
                        'email': email,
                        'first_name': f'Learner{i}',
                        'last_name': f'{data["branch"]}',
                        'role': 'learner',
                        'is_active': True,
                        'branch': target_branch
                    }
                )
                
                if created:
                    user.set_password('test123')
                    user.save()
                    self.stdout.write(
                        self.style.SUCCESS(f'   Created Learner: {username}')
                    )
                else:
                    self.stdout.write(f'   Learner already exists: {username}')

    def create_limits(self, business, branches, dry_run):
        """Create business and branch limits"""
        self.stdout.write('📊 Creating business and branch limits...')
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('   Would create business and branch limits')
            )
            return
        
        # Create business limits
        business_limits, created = BusinessLimits.objects.get_or_create(
            business=business,
            defaults={
                'total_user_limit': 1000,
                'branch_creation_limit': 20
            }
        )
        
        if created:
            self.stdout.write(
                self.style.SUCCESS(f'   Created business limits for {business.name}')
            )
        else:
            self.stdout.write(f'   Business limits already exist for {business.name}')
        
        # Create branch limits for each branch
        for branch in branches:
            if not branch:
                continue
                
            branch_limits, created = BranchUserLimits.objects.get_or_create(
                branch=branch,
                defaults={
                    'user_limit': 100,
                    'admin_limit': 5,
                    'instructor_limit': 20,
                    'learner_limit': 500
                }
            )
            
            if created:
                self.stdout.write(
                    self.style.SUCCESS(f'   Created branch limits for {branch.name}')
                )
            else:
                self.stdout.write(f'   Branch limits already exist for {branch.name}')

    def display_summary(self):
        """Display summary of created test data"""
        self.stdout.write('\n📊 Test Data Summary:')
        
        # User counts by role
        for role, role_name in CustomUser.ROLE_CHOICES:
            count = CustomUser.objects.filter(
                role=role, 
                is_active=True,
                username__endswith='_test'
            ).count()
            self.stdout.write(f'   {role_name} Users: {count}')
        
        # Business count
        business_count = Business.objects.filter(
            name='Test Business Company'
        ).count()
        self.stdout.write(f'   Test Businesses: {business_count}')
        
        # Branch count
        branch_count = Branch.objects.filter(
            name__in=[
                'Central London', 'North London', 'South London', 'East London',
                'Manchester Central', 'Manchester North', 'Birmingham Central', 'Birmingham South',
                'Leeds Main', 'Leeds West', 'Liverpool Central', 'Liverpool North',
                'Bristol Central', 'Cardiff Main', 'Newcastle Central', 'Edinburgh Main'
            ]
        ).count()
        self.stdout.write(f'   Test Branches: {branch_count}')
        
        self.stdout.write('\n🔑 Quick Test Accounts:')
        self.stdout.write('   Global Admin: globaladmin_test / test123')
        self.stdout.write('   Super Admin: superadmin1_test / test123')
        self.stdout.write('   Branch Admin: admin1_test / test123')
        self.stdout.write('   Instructor: instructor1_branch1_test / test123')
        self.stdout.write('   Learner: learner1_branch1_test / test123')
        
        self.stdout.write('\n🌐 Login URL: http://localhost:8000/login/')
        self.stdout.write('📋 All test accounts use password: test123')
