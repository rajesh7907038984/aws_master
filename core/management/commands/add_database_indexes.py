"""
Management command to add missing database indexes for performance optimization
"""

from django.core.management.base import BaseCommand
from django.db import connection
from django.apps import apps


class Command(BaseCommand):
    help = 'Add missing database indexes for performance optimization'

    def handle(self, *args, **options):
        self.stdout.write('Adding missing database indexes...')
        
        # Get all models
        models = apps.get_models()
        
        indexes_added = 0
        
        with connection.cursor() as cursor:
            for model in models:
                # Check each field in the model
                for field in model._meta.get_fields():
                    if hasattr(field, 'db_index') and field.db_index:
                        continue
                    
                    # Add index for ForeignKey fields
                    if hasattr(field, 'related_model') and field.related_model:
                        table_name = model._meta.db_table
                        field_name = field.name
                        index_name = f'idx_{table_name}_{field_name}'
                        
                        try:
                            # Check if index already exists
                            cursor.execute(f"""
                                SELECT COUNT(*) FROM pg_indexes 
                                WHERE tablename = '{table_name}' 
                                AND indexname = '{index_name}'
                            """)
                            
                            if cursor.fetchone()[0] == 0:
                                # Create index
                                cursor.execute(f"""
                                    CREATE INDEX CONCURRENTLY {index_name} 
                                    ON {table_name} ({field_name})
                                """)
                                self.stdout.write(f'Added index: {index_name}')
                                indexes_added += 1
                                
                        except Exception as e:
                            self.stdout.write(f'Error adding index {index_name}: {e}')
                    
                    # Add index for commonly queried fields
                    elif field.name in ['created_at', 'updated_at', 'is_active', 'status']:
                        table_name = model._meta.db_table
                        field_name = field.name
                        index_name = f'idx_{table_name}_{field_name}'
                        
                        try:
                            # Check if index already exists
                            cursor.execute(f"""
                                SELECT COUNT(*) FROM pg_indexes 
                                WHERE tablename = '{table_name}' 
                                AND indexname = '{index_name}'
                            """)
                            
                            if cursor.fetchone()[0] == 0:
                                # Create index
                                cursor.execute(f"""
                                    CREATE INDEX CONCURRENTLY {index_name} 
                                    ON {table_name} ({field_name})
                                """)
                                self.stdout.write(f'Added index: {index_name}')
                                indexes_added += 1
                                
                        except Exception as e:
                            self.stdout.write(f'Error adding index {index_name}: {e}')
        
        self.stdout.write(
            self.style.SUCCESS(f'Successfully added {indexes_added} database indexes')
        )
