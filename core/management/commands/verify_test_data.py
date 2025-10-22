from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from business.models import Business, BusinessUserAssignment
from branches.models import Branch, AdminBranchAssignment
from users.models import CustomUser

User = get_user_model()

class Command(BaseCommand):
    help = 'Verify that all test data has been created correctly'

    def handle(self, *args, **options):
        self.stdout.write('🔍 Verifying test data...\n')
        
        # Verify Global Admin
        self.verify_global_admin()
        
        # Verify Super Admins
        self.verify_super_admins()
        
        # Verify Branch Admins
        self.verify_branch_admins()
        
        # Verify Instructors
        self.verify_instructors()
        
        # Verify Learners
        self.verify_learners()
        
        # Verify Business and Branches
        self.verify_business_structure()
        
        self.stdout.write('\n✅ Test data verification complete!')

    def verify_global_admin(self):
        """Verify Global Admin user"""
        self.stdout.write('👑 Verifying Global Admin...')
        
        try:
            user = CustomUser.objects.get(username='globaladmin_test')
            if user.role == 'globaladmin' and user.is_active:
                self.stdout.write(
                    self.style.SUCCESS(f'   ✓ Global Admin: {user.username} ({user.email})')
                )
            else:
                self.stdout.write(
                    self.style.ERROR(f'   ✗ Global Admin role/status incorrect: {user.username}')
                )
        except CustomUser.DoesNotExist:
            self.stdout.write(
                self.style.ERROR('   ✗ Global Admin not found: globaladmin_test')
            )

    def verify_super_admins(self):
        """Verify Super Admin users"""
        self.stdout.write('⚡ Verifying Super Admins...')
        
        super_admins = [
            'superadmin1_test',
            'superadmin2_test'
        ]
        
        for username in super_admins:
            try:
                user = CustomUser.objects.get(username=username)
                if user.role == 'superadmin' and user.is_active:
                    # Check business assignment
                    business_assignment = BusinessUserAssignment.objects.filter(
                        user=user,
                        is_active=True
                    ).first()
                    
                    if business_assignment:
                        self.stdout.write(
                            self.style.SUCCESS(f'   ✓ Super Admin: {user.username} → {business_assignment.business.name}')
                        )
                    else:
                        self.stdout.write(
                            self.style.ERROR(f'   ✗ Super Admin not assigned to business: {user.username}')
                        )
                else:
                    self.stdout.write(
                        self.style.ERROR(f'   ✗ Super Admin role/status incorrect: {user.username}')
                    )
            except CustomUser.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f'   ✗ Super Admin not found: {username}')
                )

    def verify_branch_admins(self):
        """Verify Branch Admin users"""
        self.stdout.write('👨‍💼 Verifying Branch Admins...')
        
        admin_data = [
            {
                'username': 'admin1_test',
                'primary_branch': 'Central London',
                'additional_branches': ['North London', 'South London', 'East London']
            },
            {
                'username': 'admin2_test',
                'primary_branch': 'Manchester Central',
                'additional_branches': ['Manchester North', 'Birmingham Central', 'Birmingham South']
            },
            {
                'username': 'admin3_test',
                'primary_branch': 'Leeds Main',
                'additional_branches': ['Leeds West', 'Liverpool Central', 'Liverpool North']
            },
            {
                'username': 'admin4_test',
                'primary_branch': 'Bristol Central',
                'additional_branches': ['Cardiff Main', 'Newcastle Central', 'Edinburgh Main']
            }
        ]
        
        for admin_info in admin_data:
            try:
                user = CustomUser.objects.get(username=admin_info['username'])
                if user.role == 'admin' and user.is_active:
                    # Check primary branch
                    if user.branch and user.branch.name == admin_info['primary_branch']:
                        self.stdout.write(
                            self.style.SUCCESS(f'   ✓ Branch Admin: {user.username} → {user.branch.name}')
                        )
                        
                        # Check additional branch assignments
                        additional_assignments = AdminBranchAssignment.objects.filter(
                            user=user,
                            is_active=True
                        ).count()
                        
                        expected_additional = len(admin_info['additional_branches'])
                        if additional_assignments == expected_additional:
                            self.stdout.write(
                                self.style.SUCCESS(f'     ✓ Additional branches: {additional_assignments}/{expected_additional}')
                            )
                        else:
                            self.stdout.write(
                                self.style.ERROR(f'     ✗ Additional branches: {additional_assignments}/{expected_additional}')
                            )
                    else:
                        self.stdout.write(
                            self.style.ERROR(f'   ✗ Branch Admin primary branch incorrect: {user.username}')
                        )
                else:
                    self.stdout.write(
                        self.style.ERROR(f'   ✗ Branch Admin role/status incorrect: {user.username}')
                    )
            except CustomUser.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f'   ✗ Branch Admin not found: {admin_info["username"]}')
                )

    def verify_instructors(self):
        """Verify Instructor users"""
        self.stdout.write('👨‍🏫 Verifying Instructors...')
        
        # Check instructors for each branch
        branch_data = [
            {'branch': 'Central London', 'expected': 2, 'prefix': 'branch1'},
            {'branch': 'North London', 'expected': 2, 'prefix': 'branch2'},
            {'branch': 'South London', 'expected': 2, 'prefix': 'branch3'},
            {'branch': 'East London', 'expected': 2, 'prefix': 'branch4'},
            {'branch': 'Manchester Central', 'expected': 2, 'prefix': 'branch5'},
            {'branch': 'Manchester North', 'expected': 2, 'prefix': 'branch6'},
            {'branch': 'Birmingham Central', 'expected': 2, 'prefix': 'branch7'},
            {'branch': 'Birmingham South', 'expected': 2, 'prefix': 'branch8'},
            {'branch': 'Leeds Main', 'expected': 2, 'prefix': 'branch9'},
            {'branch': 'Leeds West', 'expected': 2, 'prefix': 'branch10'},
            {'branch': 'Liverpool Central', 'expected': 2, 'prefix': 'branch11'},
            {'branch': 'Liverpool North', 'expected': 2, 'prefix': 'branch12'},
            {'branch': 'Bristol Central', 'expected': 2, 'prefix': 'branch13'},
            {'branch': 'Cardiff Main', 'expected': 2, 'prefix': 'branch14'},
            {'branch': 'Newcastle Central', 'expected': 2, 'prefix': 'branch15'},
            {'branch': 'Edinburgh Main', 'expected': 2, 'prefix': 'branch16'},
        ]
        
        total_instructors = 0
        for data in branch_data:
            try:
                branch = Branch.objects.get(name=data['branch'])
                instructors = CustomUser.objects.filter(
                    role='instructor',
                    is_active=True,
                    branch=branch,
                    username__endswith='_test'
                ).count()
                
                total_instructors += instructors
                
                if instructors == data['expected']:
                    self.stdout.write(
                        self.style.SUCCESS(f'   ✓ {data["branch"]}: {instructors}/{data["expected"]} instructors')
                    )
                else:
                    self.stdout.write(
                        self.style.ERROR(f'   ✗ {data["branch"]}: {instructors}/{data["expected"]} instructors')
                    )
            except Branch.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f'   ✗ Branch not found: {data["branch"]}')
                )
        
        self.stdout.write(f'   Total Instructors: {total_instructors}/32')

    def verify_learners(self):
        """Verify Learner users"""
        self.stdout.write('👨‍🎓 Verifying Learners...')
        
        # Check learners for each branch
        branch_data = [
            {'branch': 'Central London', 'expected': 3, 'prefix': 'branch1'},
            {'branch': 'North London', 'expected': 3, 'prefix': 'branch2'},
            {'branch': 'South London', 'expected': 3, 'prefix': 'branch3'},
            {'branch': 'East London', 'expected': 3, 'prefix': 'branch4'},
            {'branch': 'Manchester Central', 'expected': 3, 'prefix': 'branch5'},
            {'branch': 'Manchester North', 'expected': 3, 'prefix': 'branch6'},
            {'branch': 'Birmingham Central', 'expected': 3, 'prefix': 'branch7'},
            {'branch': 'Birmingham South', 'expected': 3, 'prefix': 'branch8'},
            {'branch': 'Leeds Main', 'expected': 3, 'prefix': 'branch9'},
            {'branch': 'Leeds West', 'expected': 3, 'prefix': 'branch10'},
            {'branch': 'Liverpool Central', 'expected': 3, 'prefix': 'branch11'},
            {'branch': 'Liverpool North', 'expected': 3, 'prefix': 'branch12'},
            {'branch': 'Bristol Central', 'expected': 3, 'prefix': 'branch13'},
            {'branch': 'Cardiff Main', 'expected': 3, 'prefix': 'branch14'},
            {'branch': 'Newcastle Central', 'expected': 3, 'prefix': 'branch15'},
            {'branch': 'Edinburgh Main', 'expected': 3, 'prefix': 'branch16'},
        ]
        
        total_learners = 0
        for data in branch_data:
            try:
                branch = Branch.objects.get(name=data['branch'])
                learners = CustomUser.objects.filter(
                    role='learner',
                    is_active=True,
                    branch=branch,
                    username__endswith='_test'
                ).count()
                
                total_learners += learners
                
                if learners == data['expected']:
                    self.stdout.write(
                        self.style.SUCCESS(f'   ✓ {data["branch"]}: {learners}/{data["expected"]} learners')
                    )
                else:
                    self.stdout.write(
                        self.style.ERROR(f'   ✗ {data["branch"]}: {learners}/{data["expected"]} learners')
                    )
            except Branch.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f'   ✗ Branch not found: {data["branch"]}')
                )
        
        self.stdout.write(f'   Total Learners: {total_learners}/48')

    def verify_business_structure(self):
        """Verify business and branch structure"""
        self.stdout.write('🏢 Verifying Business Structure...')
        
        # Check test business
        try:
            business = Business.objects.get(name='Test Business Company')
            self.stdout.write(
                self.style.SUCCESS(f'   ✓ Test Business: {business.name}')
            )
            
            # Check branches
            branches = Branch.objects.filter(
                business=business,
                is_active=True
            ).count()
            
            if branches == 16:
                self.stdout.write(
                    self.style.SUCCESS(f'   ✓ Test Branches: {branches}/16')
                )
            else:
                self.stdout.write(
                    self.style.ERROR(f'   ✗ Test Branches: {branches}/16')
                )
                
        except Business.DoesNotExist:
            self.stdout.write(
                self.style.ERROR('   ✗ Test Business not found: Test Business Company')
            )
