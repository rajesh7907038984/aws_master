from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from business.models import BusinessUserAssignment, Business
from core.utils.business_filtering import get_superadmin_business_filter

User = get_user_model()

class Command(BaseCommand):
    help = 'Check business assignments for a specific user'

    def add_arguments(self, parser):
        parser.add_argument('username', type=str, help='Username to check')

    def handle(self, *args, **options):
        username = options['username']
        
        try:
            user = User.objects.get(username=username)
            self.stdout.write(f"\n=== Business Assignments for user: {username} ===")
            self.stdout.write(f"User role: {user.role}")
            self.stdout.write(f"User ID: {user.id}")
            
            # Check raw business assignments
            assignments = BusinessUserAssignment.objects.filter(user=user)
            self.stdout.write(f"\nTotal business assignments: {assignments.count()}")
            
            for assignment in assignments:
                status = "ACTIVE" if assignment.is_active else "INACTIVE"
                self.stdout.write(f"  - {assignment.business.name} (ID: {assignment.business.id}) - {status}")
            
            # Check active assignments only
            active_assignments = assignments.filter(is_active=True)
            self.stdout.write(f"\nActive business assignments: {active_assignments.count()}")
            
            # Use the utility function
            accessible_business_ids = get_superadmin_business_filter(user)
            self.stdout.write(f"Business IDs from utility function: {accessible_business_ids}")
            
            # Show businesses user should see
            if accessible_business_ids:
                businesses = Business.objects.filter(id__in=accessible_business_ids)
                self.stdout.write(f"\nBusinesses user should have access to:")
                for business in businesses:
                    self.stdout.write(f"  - {business.name} (ID: {business.id})")
            else:
                self.stdout.write("\nNo accessible businesses found!")
                
        except User.DoesNotExist:
            self.stdout.write(f"User '{username}' not found!")
