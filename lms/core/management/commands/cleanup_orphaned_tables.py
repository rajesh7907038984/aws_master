from django.core.management.base import BaseCommand
from django.db import connection
import json
import os


class Command(BaseCommand):
    help = 'Clean up orphaned database tables that have no corresponding Django models'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting',
        )
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Confirm deletion of orphaned tables',
        )

    def handle(self, *args, **options):
        self.stdout.write('🧹 Starting orphaned table cleanup...')
        
        # List of orphaned tables from the database analysis
        orphaned_tables = [
            "discussions_discussion_likes",
            "lms_notifications_bulknotification_target_courses",
            "courses_topic_restricted_learners",
            "lms_notifications_bulknotification_target_groups",
            "courses_comment_likes",
            "lms_notifications_bulknotification_custom_recipients",
            "account_settings_menucontrolsettings_visible_to_custom_roles",
            "courses_course_prerequisites",
            "users_customuser_user_permissions",
            "courses_discussion_likes",
            "reports_report_shared_with",
            "users_customuser_groups",
            "lms_messages_message_recipients",
            "lms_notifications_bulknotification_target_branches",
            "discussions_comment_likes"
        ]

        cursor = connection.cursor()
        
        # Verify tables are empty before deletion
        tables_to_drop = []
        
        for table_name in orphaned_tables:
            try:
                # Check if table exists
                cursor.execute("""
                    SELECT COUNT(*) FROM information_schema.tables 
                    WHERE table_schema='public' AND table_name=%s
                """, [table_name])
                
                table_exists = cursor.fetchone()[0] > 0
                
                if table_exists:
                    # Check if table is empty
                    cursor.execute(f'SELECT COUNT(*) FROM "{table_name}"')
                    row_count = cursor.fetchone()[0]
                    
                    if row_count == 0:
                        tables_to_drop.append(table_name)
                        self.stdout.write(f' {table_name}: Empty table, safe to drop')
                    else:
                        self.stdout.write(
                            self.style.WARNING(f' {table_name}: Contains {row_count} rows, skipping')
                        )
                else:
                    self.stdout.write(f'ℹ️ {table_name}: Table does not exist, skipping')
                    
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f' Error checking {table_name}: {e}')
                )

        if not tables_to_drop:
            self.stdout.write(self.style.SUCCESS(' No orphaned tables to clean up!'))
            return

        self.stdout.write(f'\n📋 Found {len(tables_to_drop)} empty orphaned tables to drop:')
        for table in tables_to_drop:
            self.stdout.write(f'  - {table}')

        if options['dry_run']:
            self.stdout.write(
                self.style.WARNING('\n🔍 DRY RUN: No changes made. Use --confirm to actually drop tables.')
            )
            return

        if not options['confirm']:
            self.stdout.write(
                self.style.WARNING('\n Use --confirm flag to proceed with deletion')
            )
            return

        # Drop the tables
        dropped_count = 0
        for table_name in tables_to_drop:
            try:
                cursor.execute(f'DROP TABLE "{table_name}" CASCADE')
                self.stdout.write(f'🗑️ Dropped table: {table_name}')
                dropped_count += 1
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f' Failed to drop {table_name}: {e}')
                )

        self.stdout.write(
            self.style.SUCCESS(f'\n Successfully dropped {dropped_count} orphaned tables!')
        )
        
        if dropped_count > 0:
            self.stdout.write(
                self.style.SUCCESS('💡 Database cleanup completed successfully.')
            )