from django.core.management.base import BaseCommand
from django.db.models import Count
from users.models import CustomUser
from collections import defaultdict


class Command(BaseCommand):
    help = 'Find all users with duplicate email addresses'

    def add_arguments(self, parser):
        parser.add_argument(
            '--export-csv',
            type=str,
            help='Export results to CSV file (provide filename)'
        )
        parser.add_argument(
            '--show-details',
            action='store_true',
            help='Show detailed information for each duplicate email'
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('🔍 Checking database for duplicate email addresses...\n'))
        
        # Find all emails that appear more than once
        # Using raw SQL for better performance with large datasets
        from django.db import connection
        
        with connection.cursor() as cursor:
            # Query to find duplicate emails (case-insensitive)
            cursor.execute("""
                SELECT LOWER(email) as email_lower, COUNT(*) as count
                FROM users_customuser
                WHERE email IS NOT NULL AND email != ''
                GROUP BY LOWER(email)
                HAVING COUNT(*) > 1
                ORDER BY count DESC, email_lower
            """)
            
            duplicate_emails = cursor.fetchall()
        
        if not duplicate_emails:
            self.stdout.write(self.style.SUCCESS('✅ No duplicate email addresses found!'))
            return
        
        total_duplicates = sum(count for _, count in duplicate_emails)
        unique_duplicate_emails = len(duplicate_emails)
        
        self.stdout.write(self.style.WARNING(
            f'\n⚠️  Found {unique_duplicate_emails} email address(es) with duplicates'
        ))
        self.stdout.write(self.style.WARNING(
            f'   Total users with duplicate emails: {total_duplicates}\n'
        ))
        
        # Collect all duplicate user details
        all_duplicate_users = []
        
        for email_lower, count in duplicate_emails:
            # Get all users with this email (case-insensitive)
            users = CustomUser.objects.filter(
                email__iexact=email_lower
            ).order_by('id')
            
            self.stdout.write(self.style.ERROR(
                f'\n📧 Email: {email_lower} ({count} occurrences)'
            ))
            
            if options['show_details']:
                for idx, user in enumerate(users, 1):
                    self.stdout.write(f'   User {idx}:')
                    self.stdout.write(f'      - ID: {user.id}')
                    self.stdout.write(f'      - Username: {user.username}')
                    self.stdout.write(f'      - Email: {user.email}')
                    self.stdout.write(f'      - Full Name: {user.get_full_name() or "N/A"}')
                    self.stdout.write(f'      - Role: {user.role}')
                    self.stdout.write(f'      - Branch: {user.branch.name if user.branch else "N/A"}')
                    self.stdout.write(f'      - Is Active: {user.is_active}')
                    self.stdout.write(f'      - Date Joined: {user.date_joined}')
                    self.stdout.write(f'      - Last Login: {user.last_login or "Never"}')
                    self.stdout.write('')
            else:
                # Show summary
                user_ids = [str(user.id) for user in users]
                usernames = [user.username for user in users]
                self.stdout.write(f'   User IDs: {", ".join(user_ids)}')
                self.stdout.write(f'   Usernames: {", ".join(usernames)}')
            
            # Store for CSV export
            for user in users:
                all_duplicate_users.append({
                    'email': user.email,
                    'email_lower': email_lower,
                    'user_id': user.id,
                    'username': user.username,
                    'full_name': user.get_full_name() or '',
                    'role': user.role,
                    'branch': user.branch.name if user.branch else '',
                    'is_active': user.is_active,
                    'date_joined': user.date_joined,
                    'last_login': user.last_login or '',
                    'duplicate_count': count
                })
        
        # Export to CSV if requested
        if options.get('export_csv'):
            import csv
            import os
            from django.utils import timezone
            
            filename = options['export_csv']
            if not filename.endswith('.csv'):
                filename += '.csv'
            
            filepath = os.path.join(os.getcwd(), filename)
            
            with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = [
                    'email', 'email_lower', 'user_id', 'username', 'full_name',
                    'role', 'branch', 'is_active', 'date_joined', 'last_login', 'duplicate_count'
                ]
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                
                writer.writeheader()
                for user_data in all_duplicate_users:
                    # Convert datetime objects to strings
                    user_data['date_joined'] = user_data['date_joined'].isoformat() if user_data['date_joined'] else ''
                    user_data['last_login'] = user_data['last_login'].isoformat() if user_data['last_login'] else ''
                    writer.writerow(user_data)
            
            self.stdout.write(self.style.SUCCESS(
                f'\n✅ Exported duplicate email data to: {filepath}'
            ))
        
        # Summary
        self.stdout.write(self.style.WARNING(
            f'\n📊 Summary:'
        ))
        self.stdout.write(f'   - Unique duplicate emails: {unique_duplicate_emails}')
        self.stdout.write(f'   - Total users affected: {total_duplicates}')
        self.stdout.write(f'   - Use --show-details to see full user information')
        self.stdout.write(f'   - Use --export-csv <filename> to export to CSV')

