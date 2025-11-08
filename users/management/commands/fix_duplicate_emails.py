from django.core.management.base import BaseCommand
from django.db.models import Count
from users.models import CustomUser
from django.db import transaction


class Command(BaseCommand):
    help = 'Fix duplicate email addresses by appending a counter to duplicates'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be changed without making changes'
        )
        parser.add_argument(
            '--auto-fix',
            action='store_true',
            help='Automatically fix duplicates by appending counters to emails'
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        auto_fix = options['auto_fix']
        
        self.stdout.write(self.style.SUCCESS('🔍 Checking for duplicate email addresses...\n'))
        
        # Find all emails that appear more than once (case-insensitive)
        from django.db import connection
        
        with connection.cursor() as cursor:
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
        
        # Process each duplicate email
        users_to_fix = []
        
        for email_lower, count in duplicate_emails:
            users = CustomUser.objects.filter(
                email__iexact=email_lower
            ).order_by('date_joined')  # Keep the oldest account with original email
            
            self.stdout.write(self.style.ERROR(
                f'\n📧 Email: {email_lower} ({count} occurrences)'
            ))
            
            # Keep first user with original email, modify others
            for idx, user in enumerate(users):
                if idx == 0:
                    self.stdout.write(f'   ✓ User {user.id} ({user.username}) - KEEPING original email')
                else:
                    new_email = f"{user.username}+duplicate{idx}@{email_lower.split('@')[1]}"
                    self.stdout.write(f'   → User {user.id} ({user.username}) - will change to: {new_email}')
                    users_to_fix.append((user, new_email))
        
        if not auto_fix:
            self.stdout.write(self.style.WARNING(
                f'\n⚠️  Found {len(users_to_fix)} user(s) that need email changes.'
            ))
            self.stdout.write(self.style.WARNING(
                '   Run with --auto-fix to automatically fix these duplicates.'
            ))
            self.stdout.write(self.style.WARNING(
                '   Run with --dry-run --auto-fix to see what would be changed.'
            ))
            return
        
        if dry_run:
            self.stdout.write(self.style.WARNING(
                f'\n🔍 DRY RUN: Would fix {len(users_to_fix)} duplicate email(s)'
            ))
            return
        
        # Apply fixes
        self.stdout.write(self.style.SUCCESS(
            f'\n🔧 Fixing {len(users_to_fix)} duplicate email(s)...'
        ))
        
        with transaction.atomic():
            for user, new_email in users_to_fix:
                old_email = user.email
                user.email = new_email
                user.save()
                self.stdout.write(f'   ✓ Updated user {user.id}: {old_email} → {new_email}')
        
        self.stdout.write(self.style.SUCCESS(
            f'\n✅ Successfully fixed {len(users_to_fix)} duplicate email(s)!'
        ))
        self.stdout.write(self.style.WARNING(
            '\n⚠️  IMPORTANT: Notify affected users of their new email addresses!'
        ))

