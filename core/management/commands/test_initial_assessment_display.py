from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from business.models import Business
from branches.models import Branch

User = get_user_model()

class Command(BaseCommand):
    help = 'Test initial assessment display for different user roles'

    def add_arguments(self, parser):
        parser.add_argument(
            '--username',
            type=str,
            help='Test specific username (optional)',
        )

    def handle(self, *args, **options):
        self.stdout.write('🧪 Testing initial assessment display...\n')
        
        if options['username']:
            self.test_specific_user(options['username'])
        else:
            self.test_all_roles()

    def test_specific_user(self, username):
        """Test a specific user's login and dashboard access"""
        try:
            user = User.objects.get(username=username)
            self.stdout.write(f'Testing user: {username} ({user.role})')
            
            if self.test_user_login(user):
                self.test_user_dashboard(user)
            else:
                self.stdout.write(
                    self.style.ERROR(f'   ✗ Login failed for {username}')
                )
        except User.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f'   ✗ User not found: {username}')
            )

    def test_all_roles(self):
        """Test all user roles"""
        test_users = [
            'globaladmin_test',
            'superadmin1_test',
            'admin1_test',
            'instructor1_branch1_test',
            'learner1_branch1_test'
        ]
        
        for username in test_users:
            try:
                user = User.objects.get(username=username)
                self.stdout.write(f'\n👤 Testing {username} ({user.role}):')
                
                if self.test_user_login(user):
                    self.test_user_dashboard(user)
                else:
                    self.stdout.write(
                        self.style.ERROR(f'   ✗ Login failed for {username}')
                    )
            except User.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f'   ✗ User not found: {username}')
                )

    def test_user_login(self, user):
        """Test user login functionality"""
        client = Client()
        
        # Test login page access
        login_url = reverse('login')
        response = client.get(login_url)
        
        if response.status_code == 200:
            self.stdout.write('   ✓ Login page accessible')
        else:
            self.stdout.write(
                self.style.ERROR(f'   ✗ Login page not accessible: {response.status_code}')
            )
            return False
        
        # Test login with credentials
        login_data = {
            'username': user.username,
            'password': 'test123'
        }
        
        response = client.post(login_url, login_data, follow=True)
        
        if response.status_code == 200 and user.is_authenticated:
            self.stdout.write('   ✓ Login successful')
            return True
        else:
            self.stdout.write(
                self.style.ERROR(f'   ✗ Login failed: {response.status_code}')
            )
            return False

    def test_user_dashboard(self, user):
        """Test user dashboard access"""
        client = Client()
        
        # Login the user
        login_data = {
            'username': user.username,
            'password': 'test123'
        }
        
        client.post(reverse('login'), login_data)
        
        # Test role-based dashboard redirect
        dashboard_urls = {
            'globaladmin': '/users/dashboard/globaladmin/',
            'superadmin': '/users/dashboard/superadmin/',
            'admin': '/users/dashboard/admin/',
            'instructor': '/users/dashboard/instructor/',
            'learner': '/users/dashboard/learner/'
        }
        
        expected_url = dashboard_urls.get(user.role)
        if expected_url:
            response = client.get(expected_url)
            
            if response.status_code == 200:
                self.stdout.write(f'   ✓ Dashboard accessible: {expected_url}')
                
                # Check for initial assessment content
                if self.check_initial_assessment_content(response, user):
                    self.stdout.write('   ✓ Initial assessment content found')
                else:
                    self.stdout.write(
                        self.style.WARNING('   ⚠ Initial assessment content not found')
                    )
            else:
                self.stdout.write(
                    self.style.ERROR(f'   ✗ Dashboard not accessible: {response.status_code}')
                )
        else:
            self.stdout.write(
                self.style.ERROR(f'   ✗ No dashboard URL defined for role: {user.role}')
            )

    def check_initial_assessment_content(self, response, user):
        """Check if initial assessment content is present in the response"""
        content = response.content.decode('utf-8').lower()
        
        # Look for common initial assessment indicators
        assessment_indicators = [
            'initial assessment',
            'assessment',
            'quiz',
            'test',
            'evaluation',
            'placement',
            'diagnostic'
        ]
        
        found_indicators = [indicator for indicator in assessment_indicators 
                           if indicator in content]
        
        if found_indicators:
            self.stdout.write(f'     Found indicators: {", ".join(found_indicators)}')
            return True
        
        return False

    def display_test_summary(self):
        """Display test summary"""
        self.stdout.write('\n📊 Test Summary:')
        
        # Count users by role
        for role, role_name in User.ROLE_CHOICES:
            count = User.objects.filter(
                role=role,
                is_active=True,
                username__endswith='_test'
            ).count()
            self.stdout.write(f'   {role_name}: {count} users')
        
        # Count businesses and branches
        business_count = Business.objects.filter(name='Test Business Company').count()
        branch_count = Branch.objects.filter(
            name__in=[
                'Central London', 'North London', 'South London', 'East London',
                'Manchester Central', 'Manchester North', 'Birmingham Central', 'Birmingham South',
                'Leeds Main', 'Leeds West', 'Liverpool Central', 'Liverpool North',
                'Bristol Central', 'Cardiff Main', 'Newcastle Central', 'Edinburgh Main'
            ]
        ).count()
        
        self.stdout.write(f'   Test Businesses: {business_count}')
        self.stdout.write(f'   Test Branches: {branch_count}')
        
        self.stdout.write('\n🔑 Quick Test Commands:')
        self.stdout.write('   python manage.py verify_test_data')
        self.stdout.write('   python manage.py test_initial_assessment_display --username globaladmin_test')
        self.stdout.write('   python manage.py test_initial_assessment_display --username learner1_branch1_test')
