import csv
import io
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from lms_outcomes.models import Outcome, RubricCriterionOutcome
from lms_rubrics.models import Rubric, RubricCriterion
from users.models import CustomUser


class Command(BaseCommand):
    help = 'Import rubric-outcome mappings from CSV file'

    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            type=str,
            required=True,
            help='Path to CSV file containing rubric-outcome mappings'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be imported without making actual changes'
        )
        parser.add_argument(
            '--clear-existing',
            action='store_true',
            help='Clear all existing rubric-outcome connections before importing'
        )

    def handle(self, *args, **options):
        file_path = options['file']
        dry_run = options.get('dry_run', False)
        clear_existing = options.get('clear_existing', False)

        try:
            with open(file_path, 'r', encoding='utf-8') as csvfile:
                self.process_csv_file(csvfile, dry_run, clear_existing)
        except FileNotFoundError:
            raise CommandError(f'File not found: {file_path}')
        except Exception as e:
            raise CommandError(f'Error processing file: {str(e)}')

    def process_csv_file(self, csvfile, dry_run, clear_existing):
        """Process the CSV file and create rubric-outcome connections"""
        
        # Expected CSV format:
        # rubric_title,criterion_description,outcome_title,weight
        # "Assignment Rubric","Critical Thinking","Analyze Complex Problems",1.0
        
        csv_reader = csv.DictReader(csvfile)
        connections_created = 0
        errors = []
        
        # Validate CSV headers
        required_headers = ['rubric_title', 'criterion_description', 'outcome_title', 'weight']
        if not all(header in csv_reader.fieldnames for header in required_headers):
            raise CommandError(f'CSV must contain headers: {", ".join(required_headers)}')
        
        # Clear existing connections if requested
        if clear_existing:
            if dry_run:
                existing_count = RubricCriterionOutcome.objects.count()
                self.stdout.write(f'Would clear {existing_count} existing connections')
            else:
                existing_count = RubricCriterionOutcome.objects.count()
                RubricCriterionOutcome.objects.all().delete()
                self.stdout.write(self.style.WARNING(f'Cleared {existing_count} existing connections'))
        
        # Process each row
        with transaction.atomic():
            for row_num, row in enumerate(csv_reader, start=2):  # Start at 2 for header
                try:
                    rubric_title = row['rubric_title'].strip()
                    criterion_description = row['criterion_description'].strip()
                    outcome_title = row['outcome_title'].strip()
                    weight = float(row['weight'].strip())
                    
                    # Validate weight
                    if weight < 0 or weight > 1:
                        errors.append(f'Row {row_num}: Weight must be between 0.0 and 1.0, got {weight}')
                        continue
                    
                    # Find rubric
                    try:
                        rubric = Rubric.objects.get(title=rubric_title)
                    except Rubric.DoesNotExist:
                        errors.append(f'Row {row_num}: Rubric not found: {rubric_title}')
                        continue
                    except Rubric.MultipleObjectsReturned:
                        errors.append(f'Row {row_num}: Multiple rubrics found with title: {rubric_title}')
                        continue
                    
                    # Find criterion
                    try:
                        criterion = RubricCriterion.objects.get(
                            rubric=rubric,
                            description__icontains=criterion_description
                        )
                    except RubricCriterion.DoesNotExist:
                        errors.append(f'Row {row_num}: Criterion not found: {criterion_description} in rubric {rubric_title}')
                        continue
                    except RubricCriterion.MultipleObjectsReturned:
                        # If multiple found, try exact match
                        try:
                            criterion = RubricCriterion.objects.get(
                                rubric=rubric,
                                description=criterion_description
                            )
                        except (RubricCriterion.DoesNotExist, RubricCriterion.MultipleObjectsReturned):
                            errors.append(f'Row {row_num}: Multiple or no exact match for criterion: {criterion_description}')
                            continue
                    
                    # Find outcome
                    try:
                        outcome = Outcome.objects.get(title=outcome_title)
                    except Outcome.DoesNotExist:
                        errors.append(f'Row {row_num}: Outcome not found: {outcome_title}')
                        continue
                    except Outcome.MultipleObjectsReturned:
                        errors.append(f'Row {row_num}: Multiple outcomes found with title: {outcome_title}')
                        continue
                    
                    # Create or update connection
                    if dry_run:
                        self.stdout.write(f'Would create: {criterion} -> {outcome.title} (weight: {weight})')
                        connections_created += 1
                    else:
                        connection, created = RubricCriterionOutcome.objects.get_or_create(
                            criterion=criterion,
                            outcome=outcome,
                            defaults={'weight': weight}
                        )
                        
                        if created:
                            self.stdout.write(f'Created: {criterion} -> {outcome.title} (weight: {weight})')
                            connections_created += 1
                        else:
                            # Update weight if connection already exists
                            if connection.weight != weight:
                                connection.weight = weight
                                connection.save()
                                self.stdout.write(f'Updated weight: {criterion} -> {outcome.title} (weight: {weight})')
                            else:
                                self.stdout.write(f'Already exists: {criterion} -> {outcome.title} (weight: {weight})')
                
                except ValueError as e:
                    errors.append(f'Row {row_num}: Invalid weight value: {row.get("weight", "N/A")}')
                except Exception as e:
                    errors.append(f'Row {row_num}: Unexpected error: {str(e)}')
        
        # Report results
        self.stdout.write('\n' + '='*50)
        if dry_run:
            self.stdout.write(self.style.SUCCESS(f'DRY RUN: Would create {connections_created} connections'))
        else:
            self.stdout.write(self.style.SUCCESS(f'Successfully processed {connections_created} connections'))
        
        if errors:
            self.stdout.write(self.style.ERROR(f'\nErrors encountered:'))
            for error in errors:
                self.stdout.write(self.style.ERROR(f'  - {error}'))
        
        # Provide sample CSV format
        self.stdout.write(f'\nExpected CSV format:')
        self.stdout.write('rubric_title,criterion_description,outcome_title,weight')
        self.stdout.write('"Assignment Rubric","Critical Thinking","Analyze Complex Problems",1.0')
        self.stdout.write('"Quiz Rubric","Problem Solving","Solve Mathematical Problems",0.8')


    def create_sample_csv(self):
        """Create a sample CSV file for reference"""
        sample_content = '''rubric_title,criterion_description,outcome_title,weight
"Assignment Rubric","Critical Thinking","Analyze Complex Problems",1.0
"Assignment Rubric","Written Communication","Communicate Effectively",0.9
"Quiz Rubric","Problem Solving","Solve Mathematical Problems",0.8
"Discussion Rubric","Collaboration","Work Effectively in Teams",1.0
"Project Rubric","Technical Skills","Apply Technical Knowledge",0.9
'''
        with open('sample_rubric_outcome_mappings.csv', 'w') as f:
            f.write(sample_content)
        
        self.stdout.write(self.style.SUCCESS('Created sample_rubric_outcome_mappings.csv'))