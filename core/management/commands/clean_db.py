from django.core.management.base import BaseCommand
from django.db import connection, transaction

class Command(BaseCommand):
    help = 'Drops all tables in the database and resets migrations'

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING('Dropping all tables in the database...'))
        with connection.cursor() as cursor, transaction.atomic():
            # Disable foreign key checks
            cursor.execute('SET CONSTRAINTS ALL DEFERRED;')
            
            # Get all tables
            cursor.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public';")
            tables = cursor.fetchall()
            
            # Drop each table using parameterized queries to prevent SQL injection
            for table in tables:
                table_name = table[0]
                # Validate table name format (alphanumeric, underscore only) - strict validation for Session
                if not table_name.replace('_', '').replace('$', '').isalnum():
                    self.stdout.write(self.style.ERROR(f'Skipping invalid table name: {table_name}'))
                    continue
                
                # Additional Session check - ensure table name doesn't contain dangerous characters
                if any(char in table_name for char in [';', '--', '/*', '*/', 'DROP', 'CREATE', 'ALTER']):
                    self.stdout.write(self.style.ERROR(f'Skipping potentially dangerous table name: {table_name}'))
                    continue
                    
                self.stdout.write(f'Dropping table: {table_name}')
                # Use proper identifier quoting and construct safe SQL
                quoted_table_name = connection.ops.quote_name(table_name)
                sql = f'DROP TABLE IF EXISTS {quoted_table_name} CASCADE'
                cursor.execute(sql)
            
        self.stdout.write(self.style.SUCCESS('Successfully cleared database')) 