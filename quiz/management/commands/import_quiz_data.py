"""
Management command to import quiz and question data from JSON
Usage: python manage.py import_quiz_data --file path/to/data.json
"""

import json
import logging
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.contrib.auth import get_user_model
from django.utils import timezone
from quiz.models import Quiz, Question

User = get_user_model()
logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Import quiz and question data from JSON file'

    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            type=str,
            required=True,
            help='Path to JSON file containing quiz and question data'
        )
        parser.add_argument(
            '--creator-email',
            type=str,
            default='admin@example.com',
            help='Email of the user who will be set as creator (default: admin@example.com)'
        )
        parser.add_argument(
            '--update',
            action='store_true',
            help='Update existing quizzes if they already exist (match by title)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be imported without actually importing'
        )

    def handle(self, *args, **options):
        file_path = options['file']
        creator_email = options['creator_email']
        update_existing = options['update']
        dry_run = options['dry_run']

        # Get or create the creator user
        try:
            creator = User.objects.filter(email=creator_email).first()
            if not creator:
                # Try to get superuser
                creator = User.objects.filter(is_superuser=True).first()
                if not creator:
                    raise CommandError(
                        f"User with email '{creator_email}' not found and no superuser exists. "
                        "Please provide a valid --creator-email or create a superuser first."
                    )
                self.stdout.write(
                    self.style.WARNING(
                        f"User '{creator_email}' not found, using superuser: {creator.email}"
                    )
                )
        except Exception as e:
            raise CommandError(f"Error finding creator user: {str(e)}")

        # Load JSON data
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                # The file appears to contain two JSON arrays
                # Try to parse it as two separate arrays
                import re
                # Split by ']' followed by whitespace and '['
                parts = re.split(r'\]\s*\n\s*\[', content)
                
                if len(parts) == 2:
                    # Add back the brackets
                    quizzes_json = parts[0] + ']'
                    questions_json = '[' + parts[1]
                    
                    # Remove leading '[' from first part if exists
                    if quizzes_json.strip().startswith('[['):
                        quizzes_json = quizzes_json.strip()[1:]
                    
                    # Remove trailing ']' from second part if exists
                    if questions_json.strip().endswith(']]'):
                        questions_json = questions_json.strip()[:-1]
                    
                    quizzes_data = json.loads(quizzes_json)
                    questions_data = json.loads(questions_json)
                else:
                    # Try to load as single object with arrays
                    data = json.loads(content)
                    if isinstance(data, dict):
                        quizzes_data = data.get('quizzes', [])
                        questions_data = data.get('questions', [])
                    else:
                        raise ValueError("Unexpected JSON structure")
                        
        except FileNotFoundError:
            raise CommandError(f"File not found: {file_path}")
        except json.JSONDecodeError as e:
            raise CommandError(f"Invalid JSON file: {e}")
        except Exception as e:
            raise CommandError(f"Error reading file: {e}")

        # Statistics
        stats = {
            'quizzes_created': 0,
            'quizzes_updated': 0,
            'quizzes_skipped': 0,
            'questions_created': 0,
            'questions_updated': 0,
            'questions_skipped': 0,
            'errors': []
        }

        self.stdout.write(
            self.style.SUCCESS(
                f"\nFound {len(quizzes_data)} quizzes and {len(questions_data)} questions to import"
            )
        )

        if dry_run:
            self.stdout.write(self.style.WARNING("\n=== DRY RUN MODE - No changes will be made ===\n"))

        # Create a mapping of old quiz IDs to new Quiz objects
        quiz_id_mapping = {}

        # Import quizzes
        self.stdout.write(self.style.SUCCESS("\n=== Importing Quizzes ===\n"))
        
        for quiz_data in quizzes_data:
            try:
                old_quiz_id = quiz_data.get('id')
                title = quiz_data.get('title', '').strip()
                
                if not title:
                    stats['errors'].append(f"Quiz with id {old_quiz_id} has no title, skipping")
                    stats['quizzes_skipped'] += 1
                    continue

                # Check if quiz already exists
                existing_quiz = Quiz.objects.filter(title=title).first()
                
                if existing_quiz and not update_existing:
                    self.stdout.write(
                        self.style.WARNING(f"Quiz '{title}' already exists, skipping")
                    )
                    stats['quizzes_skipped'] += 1
                    quiz_id_mapping[old_quiz_id] = existing_quiz
                    continue

                if dry_run:
                    if existing_quiz:
                        self.stdout.write(f"Would update quiz: {title}")
                    else:
                        self.stdout.write(f"Would create quiz: {title}")
                    continue

                # Prepare quiz data
                quiz_fields = {
                    'title': title,
                    'description': quiz_data.get('description', ''),
                    'instructions': quiz_data.get('instructions', ''),
                    'time_limit': quiz_data.get('time_limit', 0),
                    'attempts_allowed': quiz_data.get('attempts_allowed', 1),
                    'is_active': quiz_data.get('is_active', True),
                }

                with transaction.atomic():
                    if existing_quiz:
                        # Update existing quiz
                        for field, value in quiz_fields.items():
                            setattr(existing_quiz, field, value)
                        existing_quiz.save()
                        quiz = existing_quiz
                        stats['quizzes_updated'] += 1
                        self.stdout.write(
                            self.style.SUCCESS(f"✓ Updated quiz: {title}")
                        )
                    else:
                        # Create new quiz
                        quiz = Quiz.objects.create(
                            creator=creator,
                            **quiz_fields
                        )
                        stats['quizzes_created'] += 1
                        self.stdout.write(
                            self.style.SUCCESS(f"✓ Created quiz: {title}")
                        )
                    
                    quiz_id_mapping[old_quiz_id] = quiz

            except Exception as e:
                error_msg = f"Error importing quiz '{quiz_data.get('title', 'Unknown')}': {str(e)}"
                stats['errors'].append(error_msg)
                self.stdout.write(self.style.ERROR(f"✗ {error_msg}"))
                continue

        # Build quiz ID mapping for existing quizzes (if importing questions separately)
        if not quiz_id_mapping:
            # If we didn't just import quizzes, build mapping from existing quizzes
            for quiz_data in quizzes_data:
                old_quiz_id = quiz_data.get('id')
                title = quiz_data.get('title', '').strip()
                if title:
                    existing_quiz = Quiz.objects.filter(title=title).first()
                    if existing_quiz:
                        quiz_id_mapping[old_quiz_id] = existing_quiz

        # Import questions
        self.stdout.write(self.style.SUCCESS("\n=== Importing Questions ===\n"))
        
        for question_data in questions_data:
            try:
                quiz_id = question_data.get('quiz_id')
                question_text = question_data.get('question_text', '').strip()
                
                if not quiz_id or quiz_id not in quiz_id_mapping:
                    stats['errors'].append(
                        f"Question '{question_text[:50]}...' references non-existent quiz_id {quiz_id}, skipping"
                    )
                    stats['questions_skipped'] += 1
                    continue

                if not question_text:
                    stats['errors'].append(f"Question with quiz_id {quiz_id} has no text, skipping")
                    stats['questions_skipped'] += 1
                    continue

                quiz = quiz_id_mapping[quiz_id]
                
                # Check if question already exists (by text and quiz)
                existing_question = Question.objects.filter(
                    quiz=quiz,
                    question_text=question_text
                ).first()
                
                if existing_question and not update_existing:
                    self.stdout.write(
                        self.style.WARNING(
                            f"Question '{question_text[:50]}...' already exists in quiz '{quiz.title}', skipping"
                        )
                    )
                    stats['questions_skipped'] += 1
                    continue

                if dry_run:
                    if existing_question:
                        self.stdout.write(
                            f"Would update question in '{quiz.title}': {question_text[:50]}..."
                        )
                    else:
                        self.stdout.write(
                            f"Would create question in '{quiz.title}': {question_text[:50]}..."
                        )
                    continue

                # Prepare question data
                question_fields = {
                    'question_text': question_text,
                    'question_type': question_data.get('question_type', 'multiple_choice'),
                    'points': question_data.get('points', 1),
                    'order': question_data.get('order', 0),
                }

                with transaction.atomic():
                    if existing_question:
                        # Update existing question
                        for field, value in question_fields.items():
                            setattr(existing_question, field, value)
                        existing_question.save()
                        stats['questions_updated'] += 1
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"✓ Updated question in '{quiz.title}': {question_text[:50]}..."
                            )
                        )
                    else:
                        # Create new question
                        question = Question.objects.create(
                            quiz=quiz,
                            **question_fields
                        )
                        stats['questions_created'] += 1
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"✓ Created question in '{quiz.title}': {question_text[:50]}..."
                            )
                        )

            except Exception as e:
                error_msg = f"Error importing question '{question_data.get('question_text', 'Unknown')[:50]}...': {str(e)}"
                stats['errors'].append(error_msg)
                self.stdout.write(self.style.ERROR(f"✗ {error_msg}"))
                continue

        # Print summary
        self.stdout.write(self.style.SUCCESS("\n" + "="*60))
        self.stdout.write(self.style.SUCCESS("IMPORT SUMMARY"))
        self.stdout.write(self.style.SUCCESS("="*60))
        
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - No changes were made\n"))
        
        self.stdout.write(f"Quizzes created:     {stats['quizzes_created']}")
        self.stdout.write(f"Quizzes updated:     {stats['quizzes_updated']}")
        self.stdout.write(f"Quizzes skipped:     {stats['quizzes_skipped']}")
        self.stdout.write(f"Questions created:   {stats['questions_created']}")
        self.stdout.write(f"Questions updated:   {stats['questions_updated']}")
        self.stdout.write(f"Questions skipped:   {stats['questions_skipped']}")
        self.stdout.write(f"Errors:              {len(stats['errors'])}")
        
        if stats['errors']:
            self.stdout.write(self.style.ERROR("\nErrors encountered:"))
            for error in stats['errors'][:10]:  # Show first 10 errors
                self.stdout.write(self.style.ERROR(f"  - {error}"))
            if len(stats['errors']) > 10:
                self.stdout.write(
                    self.style.ERROR(f"  ... and {len(stats['errors']) - 10} more errors")
                )
        
        # Important warnings
        self.stdout.write(self.style.WARNING("\n" + "="*60))
        self.stdout.write(self.style.WARNING("IMPORTANT NOTES"))
        self.stdout.write(self.style.WARNING("="*60))
        self.stdout.write(
            self.style.WARNING(
                "\n⚠ The imported questions DO NOT have answer options/choices!"
            )
        )
        self.stdout.write(
            self.style.WARNING(
                "⚠ You must add answers manually through the Django admin or provide"
            )
        )
        self.stdout.write(
            self.style.WARNING(
                "⚠ additional JSON data containing answer options for each question."
            )
        )
        self.stdout.write(
            self.style.WARNING(
                "\n⚠ To add answers, go to: Django Admin > Quiz > Questions > Select a question"
            )
        )
        self.stdout.write(
            self.style.WARNING(
                "⚠ Or use the quiz management interface in the LMS.\n"
            )
        )
        
        self.stdout.write(self.style.SUCCESS("="*60 + "\n"))

