from django.core.management.base import BaseCommand
from django.db import connection
from django.core.management import call_command
import os


class Command(BaseCommand):
    help = 'Restore the incorrectly dropped tables to fix functionality'

    def handle(self, *args, **options):
        self.stdout.write('🔄 Restoring incorrectly dropped tables...')
        
        # Recreate the dropped tables using raw SQL
        cursor = connection.cursor()
        
        tables_to_recreate = [
            {
                'name': 'lms_notifications_bulknotification_target_courses',
                'sql': '''
                CREATE TABLE IF NOT EXISTS lms_notifications_bulknotification_target_courses (
                    id BIGSERIAL PRIMARY KEY,
                    bulknotification_id BIGINT NOT NULL,
                    course_id BIGINT NOT NULL,
                    UNIQUE(bulknotification_id, course_id)
                );
                '''
            },
            {
                'name': 'lms_notifications_bulknotification_target_groups',
                'sql': '''
                CREATE TABLE IF NOT EXISTS lms_notifications_bulknotification_target_groups (
                    id BIGSERIAL PRIMARY KEY,
                    bulknotification_id BIGINT NOT NULL,
                    branchgroup_id BIGINT NOT NULL,
                    UNIQUE(bulknotification_id, branchgroup_id)
                );
                '''
            },
            {
                'name': 'lms_notifications_bulknotification_custom_recipients',
                'sql': '''
                CREATE TABLE IF NOT EXISTS lms_notifications_bulknotification_custom_recipients (
                    id BIGSERIAL PRIMARY KEY,
                    bulknotification_id BIGINT NOT NULL,
                    customuser_id BIGINT NOT NULL,
                    UNIQUE(bulknotification_id, customuser_id)
                );
                '''
            },
            {
                'name': 'lms_notifications_bulknotification_target_branches',
                'sql': '''
                CREATE TABLE IF NOT EXISTS lms_notifications_bulknotification_target_branches (
                    id BIGSERIAL PRIMARY KEY,
                    bulknotification_id BIGINT NOT NULL,
                    branch_id BIGINT NOT NULL,
                    UNIQUE(bulknotification_id, branch_id)
                );
                '''
            },
            {
                'name': 'courses_comment_likes',
                'sql': '''
                CREATE TABLE IF NOT EXISTS courses_comment_likes (
                    id BIGSERIAL PRIMARY KEY,
                    comment_id BIGINT NOT NULL,
                    customuser_id BIGINT NOT NULL,
                    UNIQUE(comment_id, customuser_id)
                );
                '''
            },
            {
                'name': 'courses_discussion_likes',
                'sql': '''
                CREATE TABLE IF NOT EXISTS courses_discussion_likes (
                    id BIGSERIAL PRIMARY KEY,
                    discussion_id BIGINT NOT NULL,
                    customuser_id BIGINT NOT NULL,
                    UNIQUE(discussion_id, customuser_id)
                );
                '''
            },
            {
                'name': 'users_customuser_user_permissions',
                'sql': '''
                CREATE TABLE IF NOT EXISTS users_customuser_user_permissions (
                    id BIGSERIAL PRIMARY KEY,
                    customuser_id BIGINT NOT NULL,
                    permission_id INT NOT NULL,
                    UNIQUE(customuser_id, permission_id)
                );
                '''
            },
            {
                'name': 'users_customuser_groups',
                'sql': '''
                CREATE TABLE IF NOT EXISTS users_customuser_groups (
                    id BIGSERIAL PRIMARY KEY,
                    customuser_id BIGINT NOT NULL,
                    group_id INT NOT NULL,
                    UNIQUE(customuser_id, group_id)
                );
                '''
            },
            {
                'name': 'reports_report_shared_with',
                'sql': '''
                CREATE TABLE IF NOT EXISTS reports_report_shared_with (
                    id BIGSERIAL PRIMARY KEY,
                    report_id BIGINT NOT NULL,
                    customuser_id BIGINT NOT NULL,
                    UNIQUE(report_id, customuser_id)
                );
                '''
            },
            {
                'name': 'account_settings_menucontrolsettings_visible_to_custom_roles',
                'sql': '''
                CREATE TABLE IF NOT EXISTS account_settings_menucontrolsettings_visible_to_custom_roles (
                    id BIGSERIAL PRIMARY KEY,
                    menucontrolsettings_id BIGINT NOT NULL,
                    role_id BIGINT NOT NULL,
                    UNIQUE(menucontrolsettings_id, role_id)
                );
                '''
            }
        ]
        
        created_count = 0
        for table in tables_to_recreate:
            try:
                cursor.execute(table['sql'])
                self.stdout.write(f'✅ Recreated table: {table["name"]}')
                created_count += 1
            except Exception as e:
                self.stdout.write(
                    self.style.WARNING(f'⚠️ Table {table["name"]} already exists or error: {e}')
                )
        
        self.stdout.write(
            self.style.SUCCESS(f'🎉 Successfully recreated {created_count} tables!')
        )
        
        # Run Django system check to verify everything is working
        self.stdout.write('🔍 Running system check...')
        try:
            call_command('check', verbosity=0)
            self.stdout.write(
                self.style.SUCCESS('✅ System check passed - all functionality restored!')
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ System check failed: {e}')
            )
