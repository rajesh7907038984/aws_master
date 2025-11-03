import os
import json
import zipfile
import shutil
from datetime import datetime
from django.core.management.base import BaseCommand
from django.core.exceptions import ValidationError
from django.conf import settings
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.db import transaction

from courses.models import Course, Topic, CourseEnrollment, TopicProgress
from assignments.models import Assignment, AssignmentSubmission
from quiz.models import Quiz, Question, QuizAttempt
from discussions.models import Discussion
from conferences.models import Conference
from account_settings.models import ImportJob
from branches.models import Branch

User = get_user_model()

class Command(BaseCommand):
    help = 'Import LMS data from exported JSON files'

    def add_arguments(self, parser):
        parser.add_argument('--type', type=str, required=True, 
                          choices=['users', 'courses', 'topics', 'assignments', 'quizzes', 'discussions', 'conferences', 'all'],
                          help='Type of data to import')
        parser.add_argument('--file', type=str, required=True, help='Path to import file (ZIP or directory)')
        parser.add_argument('--replace', action='store_true', help='Replace existing records')
        parser.add_argument('--job-id', type=int, help='Import job ID for tracking')

    def handle(self, *args, **options):
        import_type = options['type']
        file_path = options['file']
        replace_existing = options['replace']
        job_id = options.get('job_id')
        
        job = None
        if job_id:
            try:
                job = ImportJob.objects.get(id=job_id)
                job.status = 'processing'
                job.save()
            except ImportJob.DoesNotExist:
                pass

        try:
            self.stdout.write(f'Starting import of {import_type} data...')
            
            # Extract ZIP file if needed
            import_dir = self.prepare_import_directory(file_path)
            
            records_processed = 0
            records_created = 0
            records_updated = 0
            records_failed = 0
            validation_errors = []
            
            # Handle 'all' type by importing all data types in order
            if import_type == 'users' or import_type == 'all':
                stats = self.import_users(import_dir, replace_existing)
                records_processed += stats[0]
                records_created += stats[1]
                records_updated += stats[2]
                records_failed += stats[3]
                validation_errors.extend(stats[4])
            
            if import_type == 'courses' or import_type == 'all':
                stats = self.import_courses(import_dir, replace_existing)
                records_processed += stats[0]
                records_created += stats[1]
                records_updated += stats[2]
                records_failed += stats[3]
                validation_errors.extend(stats[4])
                
            if import_type == 'topics' or import_type == 'all':
                stats = self.import_topics(import_dir, replace_existing)
                records_processed += stats[0]
                records_created += stats[1]
                records_updated += stats[2]
                records_failed += stats[3]
                validation_errors.extend(stats[4])
                
            if import_type == 'assignments' or import_type == 'all':
                stats = self.import_assignments(import_dir, replace_existing)
                records_processed += stats[0]
                records_created += stats[1]
                records_updated += stats[2]
                records_failed += stats[3]
                validation_errors.extend(stats[4])
                
            if import_type == 'quizzes' or import_type == 'all':
                stats = self.import_quizzes(import_dir, replace_existing)
                records_processed += stats[0]
                records_created += stats[1]
                records_updated += stats[2]
                records_failed += stats[3]
                validation_errors.extend(stats[4])
                
            if import_type == 'discussions' or import_type == 'all':
                stats = self.import_discussions(import_dir, replace_existing)
                records_processed += stats[0]
                records_created += stats[1]
                records_updated += stats[2]
                records_failed += stats[3]
                validation_errors.extend(stats[4])
                
            if import_type == 'conferences' or import_type == 'all':
                stats = self.import_conferences(import_dir, replace_existing)
                records_processed += stats[0]
                records_created += stats[1]
                records_updated += stats[2]
                records_failed += stats[3]
                validation_errors.extend(stats[4])
            
            # Update job status
            if job:
                if records_failed > 0:
                    job.status = 'partial' if records_created > 0 or records_updated > 0 else 'failed'
                else:
                    job.status = 'completed'
                
                job.records_processed = records_processed
                job.records_created = records_created
                job.records_updated = records_updated
                job.records_failed = records_failed
                job.validation_errors = {'errors': validation_errors}
                job.completed_at = timezone.now()
                job.save()
            
            self.stdout.write(self.style.SUCCESS(f'Import completed'))
            self.stdout.write(f'Records processed: {records_processed}')
            self.stdout.write(f'Records created: {records_created}')
            self.stdout.write(f'Records updated: {records_updated}')
            self.stdout.write(f'Records failed: {records_failed}')
            
            if validation_errors:
                self.stdout.write(self.style.WARNING(f'Validation errors: {len(validation_errors)}'))
                for error in validation_errors[:5]:  # Show first 5 errors
                    self.stdout.write(f'  - {error}')
            
        except Exception as e:
            error_msg = str(e)
            self.stdout.write(self.style.ERROR(f'Import failed: {error_msg}'))
            
            if job:
                job.status = 'failed'
                job.error_message = error_msg
                job.save()

    def prepare_import_directory(self, file_path):
        """Prepare the import directory by extracting ZIP if needed"""
        import tempfile
        if file_path.endswith('.zip'):
            # Extract ZIP file to temp directory (use temp if S3, otherwise use MEDIA_ROOT)
            if settings.MEDIA_ROOT:
                extract_dir = os.path.join(settings.MEDIA_ROOT, 'temp_imports', datetime.now().strftime('%Y%m%d_%H%M%S'))
                os.makedirs(extract_dir, exist_ok=True)
            else:
                # Using S3 - create temp directory for extraction
                extract_dir = tempfile.mkdtemp(prefix='import_extract_')
            
            with zipfile.ZipFile(file_path, 'r') as zipf:
                zipf.extractall(extract_dir)
            
            return extract_dir
        else:
            return file_path

    def import_users(self, import_dir, replace_existing):
        """Import users data"""
        users_file = os.path.join(import_dir, 'users.json')
        if not os.path.exists(users_file):
            raise FileNotFoundError(f"Users data file not found: {users_file}")
        
        with open(users_file, 'r') as f:
            users_data = json.load(f)
        
        records_processed = 0
        records_created = 0
        records_updated = 0
        records_failed = 0
        validation_errors = []
        
        for user_data in users_data:
            records_processed += 1
            try:
                with transaction.atomic():
                    # Check if user exists
                    user_exists = User.objects.filter(username=user_data['username']).exists()
                    
                    if user_exists and not replace_existing:
                        # Skip existing user
                        continue
                    
                    # Validate required fields
                    if not user_data.get('username'):
                        raise ValidationError("Username is required")
                    
                    if not user_data.get('email'):
                        raise ValidationError("Email is required")
                    
                    # Handle branch relationship
                    branch = None
                    if user_data.get('branch_id'):
                        try:
                            branch = Branch.objects.get(id=user_data['branch_id'])
                        except Branch.DoesNotExist:
                            pass
                    
                    # Create or update user
                    user_defaults = {
                        'email': user_data['email'],
                        'first_name': user_data.get('first_name', ''),
                        'last_name': user_data.get('last_name', ''),
                        'role': user_data.get('role', 'learner'),
                        'is_active': user_data.get('is_active', True),
                        'branch': branch,
                        'phone_number': user_data.get('phone_number'),
                        'language': user_data.get('language', 'en'),
                        'timezone': user_data.get('timezone', 'UTC'),
                        # Personal information
                        'unique_learner_number': user_data.get('unique_learner_number'),
                        'family_name': user_data.get('family_name'),
                        'given_names': user_data.get('given_names'),
                        'sex': user_data.get('sex'),
                        'ethnicity': user_data.get('ethnicity'),
                        'current_postcode': user_data.get('current_postcode'),
                        'address_line1': user_data.get('address_line1'),
                        'address_line2': user_data.get('address_line2'),
                        'city': user_data.get('city'),
                        'county': user_data.get('county'),
                        'country': user_data.get('country'),
                        'contact_preference': user_data.get('contact_preference'),
                        # Education
                        'study_area': user_data.get('study_area'),
                        'level_of_study': user_data.get('level_of_study'),
                        'grades': user_data.get('grades'),
                        'education_data': user_data.get('education_data'),
                        # Employment
                        'job_role': user_data.get('job_role'),
                        'industry': user_data.get('industry'),
                        'duration': user_data.get('duration'),
                        'key_skills': user_data.get('key_skills'),
                    }
                    
                    # Parse date fields
                    if user_data.get('date_of_birth'):
                        try:
                            user_defaults['date_of_birth'] = datetime.fromisoformat(user_data['date_of_birth']).date()
                        except ValueError:
                            pass
                    
                    if user_data.get('date_joined'):
                        try:
                            user_defaults['date_joined'] = datetime.fromisoformat(user_data['date_joined'])
                        except ValueError:
                            pass
                    
                    user, created = User.objects.update_or_create(
                        username=user_data['username'],
                        defaults=user_defaults
                    )
                    
                    # Handle file imports
                    if user_data.get('cv_file_path'):
                        self._copy_user_file(import_dir, user_data['cv_file_path'], user, 'cv_file')
                    
                    if user_data.get('statement_of_purpose_file_path'):
                        self._copy_user_file(import_dir, user_data['statement_of_purpose_file_path'], user, 'statement_of_purpose_file')
                    
                    if created:
                        records_created += 1
                    else:
                        records_updated += 1
                        
            except Exception as e:
                records_failed += 1
                validation_errors.append(f"User {user_data.get('username', 'Unknown')}: {str(e)}")
                self.stdout.write(f"Failed to import user {user_data.get('username', 'Unknown')}: {str(e)}")
        
        return records_processed, records_created, records_updated, records_failed, validation_errors

    def import_courses(self, import_dir, replace_existing):
        """Import courses data"""
        courses_file = os.path.join(import_dir, 'courses.json')
        if not os.path.exists(courses_file):
            raise FileNotFoundError(f"Courses data file not found: {courses_file}")
        
        with open(courses_file, 'r') as f:
            courses_data = json.load(f)
        
        records_processed = 0
        records_created = 0
        records_updated = 0
        records_failed = 0
        validation_errors = []
        
        for course_data in courses_data:
            records_processed += 1
            try:
                with transaction.atomic():
                    # Validate required fields
                    if not course_data.get('title'):
                        raise ValidationError("Course title is required")
                    
                    # Handle foreign key relationships
                    branch = None
                    if course_data.get('branch_id'):
                        try:
                            branch = Branch.objects.get(id=course_data['branch_id'])
                        except Branch.DoesNotExist:
                            pass
                    
                    instructor = None
                    if course_data.get('instructor_id'):
                        try:
                            instructor = User.objects.get(id=course_data['instructor_id'])
                        except User.DoesNotExist:
                            pass
                    
                    course_defaults = {
                        'title': course_data['title'],
                        'short_description': course_data.get('short_description', ''),
                        'description': course_data.get('description', ''),
                        'course_code': course_data.get('course_code'),
                        'course_outcomes': course_data.get('course_outcomes', ''),
                        'course_rubrics': course_data.get('course_rubrics', ''),
                        'is_active': course_data.get('is_active', True),
                        'language': course_data.get('language', 'en'),
                        'visibility': course_data.get('visibility', 'public'),
                        'schedule_type': course_data.get('schedule_type', 'self_paced'),
                        'require_enrollment': course_data.get('require_enrollment', True),
                        'branch': branch,
                        'instructor': instructor,
                    }
                    
                    # Parse price
                    if course_data.get('price'):
                        try:
                            course_defaults['price'] = float(course_data['price'])
                        except (ValueError, TypeError):
                            course_defaults['price'] = 0.00
                    
                    # Parse date fields
                    if course_data.get('created_at'):
                        try:
                            course_defaults['created_at'] = datetime.fromisoformat(course_data['created_at'])
                        except ValueError:
                            pass
                    
                    if course_data.get('updated_at'):
                        try:
                            course_defaults['updated_at'] = datetime.fromisoformat(course_data['updated_at'])
                        except ValueError:
                            pass
                    
                    # Check if course exists (by title for now, could use course_code if available)
                    existing_course = Course.objects.filter(title=course_data['title']).first()
                    
                    if existing_course and not replace_existing:
                        continue
                    
                    if existing_course:
                        # Update existing course
                        for key, value in course_defaults.items():
                            setattr(existing_course, key, value)
                        existing_course.save()
                        course = existing_course
                        records_updated += 1
                    else:
                        # Create new course
                        course = Course.objects.create(**course_defaults)
                        records_created += 1
                    
                    # Handle file imports
                    if course_data.get('course_image_path'):
                        self._copy_course_file(import_dir, course_data['course_image_path'], course, 'course_image')
                    
                    if course_data.get('course_video_path'):
                        self._copy_course_file(import_dir, course_data['course_video_path'], course, 'course_video')
                        
            except Exception as e:
                records_failed += 1
                validation_errors.append(f"Course {course_data.get('title', 'Unknown')}: {str(e)}")
                self.stdout.write(f"Failed to import course {course_data.get('title', 'Unknown')}: {str(e)}")
        
        # Import enrollments if file exists
        enrollments_file = os.path.join(import_dir, 'course_enrollments.json')
        if os.path.exists(enrollments_file):
            enrollment_stats = self._import_enrollments(enrollments_file, replace_existing)
            records_processed += enrollment_stats[0]
            records_created += enrollment_stats[1]
            records_updated += enrollment_stats[2]
            records_failed += enrollment_stats[3]
            validation_errors.extend(enrollment_stats[4])
        
        return records_processed, records_created, records_updated, records_failed, validation_errors

    def import_topics(self, import_dir, replace_existing):
        """Import topics data"""
        topics_file = os.path.join(import_dir, 'topics.json')
        if not os.path.exists(topics_file):
            raise FileNotFoundError(f"Topics data file not found: {topics_file}")
        
        with open(topics_file, 'r') as f:
            topics_data = json.load(f)
        
        records_processed = 0
        records_created = 0
        records_updated = 0
        records_failed = 0
        validation_errors = []
        
        for topic_data in topics_data:
            records_processed += 1
            try:
                with transaction.atomic():
                    # Validate required fields
                    if not topic_data.get('title'):
                        raise ValidationError("Topic title is required")
                    
                    if not topic_data.get('content_type'):
                        raise ValidationError("Topic content type is required")
                    
                    topic_defaults = {
                        'title': topic_data['title'],
                        'description': topic_data.get('description', ''),
                        'instructions': topic_data.get('instructions', ''),
                        'content_type': topic_data['content_type'],
                        'status': topic_data.get('status', 'draft'),
                        'endless_access': topic_data.get('endless_access', False),
                        'web_url': topic_data.get('web_url'),
                        'text_content': topic_data.get('text_content'),
                        'embed_code': topic_data.get('embed_code'),
                        'order': topic_data.get('order', 0),
                        'alignment': topic_data.get('alignment', 'left'),
                    }
                    
                    # Parse date fields
                    if topic_data.get('start_date'):
                        try:
                            naive_date = datetime.fromisoformat(topic_data['start_date'])
                            if naive_date.tzinfo is None:
                                # Make timezone-aware
                                from django.utils import timezone
                                topic_defaults['start_date'] = timezone.make_aware(naive_date)
                            else:
                                topic_defaults['start_date'] = naive_date
                        except ValueError:
                            pass
                    
                    if topic_data.get('end_date'):
                        try:
                            naive_date = datetime.fromisoformat(topic_data['end_date'])
                            if naive_date.tzinfo is None:
                                # Make timezone-aware
                                from django.utils import timezone
                                topic_defaults['end_date'] = timezone.make_aware(naive_date)
                            else:
                                topic_defaults['end_date'] = naive_date
                        except ValueError:
                            pass
                    
                    # Check if topic exists
                    existing_topic = Topic.objects.filter(title=topic_data['title']).first()
                    
                    if existing_topic and not replace_existing:
                        continue
                    
                    if existing_topic:
                        # Update existing topic
                        for key, value in topic_defaults.items():
                            setattr(existing_topic, key, value)
                        existing_topic.save()
                        topic = existing_topic
                        records_updated += 1
                    else:
                        # Create new topic
                        topic = Topic.objects.create(**topic_defaults)
                        records_created += 1
                    
                    # Handle file imports
                    if topic_data.get('content_file_path'):
                        self._copy_topic_file(import_dir, topic_data['content_file_path'], topic)
                        
            except Exception as e:
                records_failed += 1
                validation_errors.append(f"Topic {topic_data.get('title', 'Unknown')}: {str(e)}")
                self.stdout.write(f"Failed to import topic {topic_data.get('title', 'Unknown')}: {str(e)}")
        
        return records_processed, records_created, records_updated, records_failed, validation_errors

    def import_assignments(self, import_dir, replace_existing):
        """Import assignments data"""
        assignments_file = os.path.join(import_dir, 'assignments.json')
        if not os.path.exists(assignments_file):
            raise FileNotFoundError(f"Assignments data file not found: {assignments_file}")
        
        with open(assignments_file, 'r') as f:
            assignments_data = json.load(f)
        
        records_processed = 0
        records_created = 0
        records_updated = 0
        records_failed = 0
        validation_errors = []
        
        for assignment_data in assignments_data:
            records_processed += 1
            try:
                with transaction.atomic():
                    # Validate required fields
                    if not assignment_data.get('title'):
                        raise ValidationError("Assignment title is required")
                    
                    # Handle foreign key relationships
                    course = None
                    if assignment_data.get('course_id'):
                        try:
                            course = Course.objects.get(id=assignment_data['course_id'])
                        except Course.DoesNotExist:
                            pass
                    
                    assignment_defaults = {
                        'title': assignment_data['title'],
                        'description': assignment_data.get('description', ''),
                        'instructions': assignment_data.get('instructions', ''),
                        'is_active': assignment_data.get('is_active', True),
                        'course': course,
                    }
                    
                    # Parse numeric fields
                    if assignment_data.get('points'):
                        try:
                            assignment_defaults['points'] = float(assignment_data['points'])
                        except (ValueError, TypeError):
                            pass
                    
                    # Parse date fields
                    if assignment_data.get('due_date'):
                        try:
                            naive_date = datetime.fromisoformat(assignment_data['due_date'])
                            if naive_date.tzinfo is None:
                                # Make timezone-aware
                                from django.utils import timezone
                                assignment_defaults['due_date'] = timezone.make_aware(naive_date)
                            else:
                                assignment_defaults['due_date'] = naive_date
                        except ValueError:
                            pass
                    
                    # Check if assignment exists
                    existing_assignment = Assignment.objects.filter(title=assignment_data['title']).first()
                    
                    if existing_assignment and not replace_existing:
                        continue
                    
                    if existing_assignment:
                        # Update existing assignment
                        for key, value in assignment_defaults.items():
                            if hasattr(existing_assignment, key):
                                setattr(existing_assignment, key, value)
                        existing_assignment.save()
                        records_updated += 1
                    else:
                        # Create new assignment with only fields that exist in the model
                        valid_fields = {}
                        for key, value in assignment_defaults.items():
                            if hasattr(Assignment, key):
                                valid_fields[key] = value
                        assignment = Assignment.objects.create(**valid_fields)
                        records_created += 1
                        
            except Exception as e:
                records_failed += 1
                validation_errors.append(f"Assignment {assignment_data.get('title', 'Unknown')}: {str(e)}")
                self.stdout.write(f"Failed to import assignment {assignment_data.get('title', 'Unknown')}: {str(e)}")
        
        return records_processed, records_created, records_updated, records_failed, validation_errors

    def import_quizzes(self, import_dir, replace_existing):
        """Import quizzes data"""
        quizzes_file = os.path.join(import_dir, 'quizzes.json')
        if not os.path.exists(quizzes_file):
            raise FileNotFoundError(f"Quizzes data file not found: {quizzes_file}")
        
        with open(quizzes_file, 'r') as f:
            quizzes_data = json.load(f)
        
        records_processed = 0
        records_created = 0
        records_updated = 0
        records_failed = 0
        validation_errors = []
        
        for quiz_data in quizzes_data:
            records_processed += 1
            try:
                with transaction.atomic():
                    # Validate required fields
                    if not quiz_data.get('title'):
                        raise ValidationError("Quiz title is required")
                    
                    quiz_defaults = {
                        'title': quiz_data['title'],
                        'description': quiz_data.get('description', ''),
                        'instructions': quiz_data.get('instructions', ''),
                        'is_active': quiz_data.get('is_active', True),
                    }
                    
                    # Add optional fields if they exist in the model
                    if hasattr(Quiz, 'time_limit') and quiz_data.get('time_limit'):
                        quiz_defaults['time_limit'] = quiz_data['time_limit']
                    
                    if hasattr(Quiz, 'attempts_allowed') and quiz_data.get('attempts_allowed'):
                        quiz_defaults['attempts_allowed'] = quiz_data['attempts_allowed']
                    
                    # Check if quiz exists
                    existing_quiz = Quiz.objects.filter(title=quiz_data['title']).first()
                    
                    if existing_quiz and not replace_existing:
                        continue
                    
                    if existing_quiz:
                        # Update existing quiz
                        for key, value in quiz_defaults.items():
                            if hasattr(existing_quiz, key):
                                setattr(existing_quiz, key, value)
                        existing_quiz.save()
                        records_updated += 1
                    else:
                        # Create new quiz with only valid fields
                        valid_fields = {}
                        for key, value in quiz_defaults.items():
                            if hasattr(Quiz, key):
                                valid_fields[key] = value
                        quiz = Quiz.objects.create(**valid_fields)
                        records_created += 1
                        
            except Exception as e:
                records_failed += 1
                validation_errors.append(f"Quiz {quiz_data.get('title', 'Unknown')}: {str(e)}")
                self.stdout.write(f"Failed to import quiz {quiz_data.get('title', 'Unknown')}: {str(e)}")
        
        return records_processed, records_created, records_updated, records_failed, validation_errors

    def import_discussions(self, import_dir, replace_existing):
        """Import discussions data"""
        discussions_file = os.path.join(import_dir, 'discussions.json')
        if not os.path.exists(discussions_file):
            raise FileNotFoundError(f"Discussions data file not found: {discussions_file}")
        
        with open(discussions_file, 'r') as f:
            discussions_data = json.load(f)
        
        records_processed = 0
        records_created = 0
        records_updated = 0
        records_failed = 0
        validation_errors = []
        
        for discussion_data in discussions_data:
            records_processed += 1
            try:
                with transaction.atomic():
                    # Validate required fields
                    if not discussion_data.get('title'):
                        raise ValidationError("Discussion title is required")
                    
                    discussion_defaults = {
                        'title': discussion_data['title'],
                        'description': discussion_data.get('description', ''),
                    }
                    
                    # Add optional fields if they exist in the model
                    if hasattr(Discussion, 'is_published'):
                        discussion_defaults['is_published'] = discussion_data.get('is_published', True)
                    
                    # Check if discussion exists
                    existing_discussion = Discussion.objects.filter(title=discussion_data['title']).first()
                    
                    if existing_discussion and not replace_existing:
                        continue
                    
                    if existing_discussion:
                        # Update existing discussion
                        for key, value in discussion_defaults.items():
                            if hasattr(existing_discussion, key):
                                setattr(existing_discussion, key, value)
                        existing_discussion.save()
                        records_updated += 1
                    else:
                        # Create new discussion with only valid fields
                        valid_fields = {}
                        for key, value in discussion_defaults.items():
                            if hasattr(Discussion, key):
                                valid_fields[key] = value
                        discussion = Discussion.objects.create(**valid_fields)
                        records_created += 1
                        
            except Exception as e:
                records_failed += 1
                validation_errors.append(f"Discussion {discussion_data.get('title', 'Unknown')}: {str(e)}")
                self.stdout.write(f"Failed to import discussion {discussion_data.get('title', 'Unknown')}: {str(e)}")
        
        return records_processed, records_created, records_updated, records_failed, validation_errors

    def import_conferences(self, import_dir, replace_existing):
        """Import conferences data"""
        conferences_file = os.path.join(import_dir, 'conferences.json')
        if not os.path.exists(conferences_file):
            raise FileNotFoundError(f"Conferences data file not found: {conferences_file}")
        
        with open(conferences_file, 'r') as f:
            conferences_data = json.load(f)
        
        records_processed = 0
        records_created = 0
        records_updated = 0
        records_failed = 0
        validation_errors = []
        
        for conference_data in conferences_data:
            records_processed += 1
            try:
                with transaction.atomic():
                    # Validate required fields
                    if not conference_data.get('title'):
                        raise ValidationError("Conference title is required")
                    
                    conference_defaults = {
                        'title': conference_data['title'],
                        'description': conference_data.get('description', ''),
                    }
                    
                    # Add optional fields if they exist in the model
                    if hasattr(Conference, 'is_published'):
                        conference_defaults['is_published'] = conference_data.get('is_published', True)
                    
                    if hasattr(Conference, 'duration') and conference_data.get('duration'):
                        conference_defaults['duration'] = conference_data['duration']
                    
                    # Parse date fields
                    if hasattr(Conference, 'scheduled_time') and conference_data.get('scheduled_time'):
                        try:
                            conference_defaults['scheduled_time'] = datetime.fromisoformat(conference_data['scheduled_time'])
                        except ValueError:
                            pass
                    
                    # Check if conference exists
                    existing_conference = Conference.objects.filter(title=conference_data['title']).first()
                    
                    if existing_conference and not replace_existing:
                        continue
                    
                    if existing_conference:
                        # Update existing conference
                        for key, value in conference_defaults.items():
                            if hasattr(existing_conference, key):
                                setattr(existing_conference, key, value)
                        existing_conference.save()
                        records_updated += 1
                    else:
                        # Create new conference with only valid fields
                        valid_fields = {}
                        for key, value in conference_defaults.items():
                            if hasattr(Conference, key):
                                valid_fields[key] = value
                        conference = Conference.objects.create(**valid_fields)
                        records_created += 1
                        
            except Exception as e:
                records_failed += 1
                validation_errors.append(f"Conference {conference_data.get('title', 'Unknown')}: {str(e)}")
                self.stdout.write(f"Failed to import conference {conference_data.get('title', 'Unknown')}: {str(e)}")
        
        return records_processed, records_created, records_updated, records_failed, validation_errors

    def _import_enrollments(self, enrollments_file, replace_existing):
        """Import course enrollments"""
        with open(enrollments_file, 'r') as f:
            enrollments_data = json.load(f)
        
        records_processed = 0
        records_created = 0
        records_updated = 0
        records_failed = 0
        validation_errors = []
        
        for enrollment_data in enrollments_data:
            records_processed += 1
            try:
                with transaction.atomic():
                    # Get course and user
                    try:
                        course = Course.objects.get(id=enrollment_data['course_id'])
                        user = User.objects.get(id=enrollment_data['user_id'])
                    except (Course.DoesNotExist, User.DoesNotExist):
                        raise ValidationError("Course or User not found")
                    
                    enrollment_defaults = {
                        'enrolled_at': datetime.fromisoformat(enrollment_data['enrolled_at']) if enrollment_data.get('enrolled_at') else timezone.now(),
                        'completed': enrollment_data.get('completed', False),
                    }
                    
                    if enrollment_data.get('completion_date'):
                        try:
                            enrollment_defaults['completion_date'] = datetime.fromisoformat(enrollment_data['completion_date'])
                        except ValueError:
                            pass
                    
                    enrollment, created = CourseEnrollment.objects.update_or_create(
                        course=course,
                        user=user,
                        defaults=enrollment_defaults
                    )
                    
                    if created:
                        records_created += 1
                    else:
                        records_updated += 1
                        
            except Exception as e:
                records_failed += 1
                validation_errors.append(f"Enrollment course_id={enrollment_data.get('course_id')}, user_id={enrollment_data.get('user_id')}: {str(e)}")
        
        return records_processed, records_created, records_updated, records_failed, validation_errors

    def _copy_user_file(self, import_dir, file_path, user, field_name):
        """Copy user file from import directory to proper location"""
        from django.core.files.storage import default_storage
        from django.core.files.base import ContentFile
        try:
            src_path = os.path.join(import_dir, file_path)
            if os.path.exists(src_path):
                filename = os.path.basename(file_path)
                # Determine destination path based on storage type
                if settings.MEDIA_ROOT:
                    # Local storage
                    dst_dir = os.path.join(settings.MEDIA_ROOT, 'user_files', field_name.replace('_file', ''), str(user.id))
                    os.makedirs(dst_dir, exist_ok=True)
                    dst_path = os.path.join(dst_dir, filename)
                    shutil.copy2(src_path, dst_path)
                    relative_path = os.path.relpath(dst_path, settings.MEDIA_ROOT)
                else:
                    # S3 storage
                    s3_key = f'user_files/{field_name.replace("_file", "")}/{user.id}/{filename}'
                    with open(src_path, 'rb') as f:
                        default_storage.save(s3_key, ContentFile(f.read()))
                    relative_path = s3_key
                
                # Update user field
                setattr(user, field_name, relative_path)
                user.save(update_fields=[field_name])
        except Exception as e:
            self.stdout.write(f"Failed to copy user file {file_path}: {str(e)}")

    def _copy_course_file(self, import_dir, file_path, course, field_name):
        """Copy course file from import directory to proper location"""
        from django.core.files.storage import default_storage
        from django.core.files.base import ContentFile
        try:
            src_path = os.path.join(import_dir, file_path)
            if os.path.exists(src_path):
                filename = os.path.basename(file_path)
                # Determine destination path based on storage type
                if settings.MEDIA_ROOT:
                    # Local storage
                    dst_dir = os.path.join(settings.MEDIA_ROOT, f'course_{course.id}')
                    os.makedirs(dst_dir, exist_ok=True)
                    dst_path = os.path.join(dst_dir, filename)
                    shutil.copy2(src_path, dst_path)
                    relative_path = os.path.relpath(dst_path, settings.MEDIA_ROOT)
                else:
                    # S3 storage
                    s3_key = f'course_{course.id}/{filename}'
                    with open(src_path, 'rb') as f:
                        default_storage.save(s3_key, ContentFile(f.read()))
                    relative_path = s3_key
                
                # Update course field
                setattr(course, field_name, relative_path)
                course.save(update_fields=[field_name])
        except Exception as e:
            self.stdout.write(f"Failed to copy course file {file_path}: {str(e)}")

    def _copy_topic_file(self, import_dir, file_path, topic):
        """Copy topic file from import directory to proper location"""
        from django.core.files.storage import default_storage
        from django.core.files.base import ContentFile
        try:
            src_path = os.path.join(import_dir, file_path)
            if os.path.exists(src_path):
                filename = os.path.basename(file_path)
                # Determine destination path based on storage type
                if settings.MEDIA_ROOT:
                    # Local storage
                    dst_dir = os.path.join(settings.MEDIA_ROOT, f'topic_uploads', str(topic.id))
                    os.makedirs(dst_dir, exist_ok=True)
                    dst_path = os.path.join(dst_dir, filename)
                    shutil.copy2(src_path, dst_path)
                    relative_path = os.path.relpath(dst_path, settings.MEDIA_ROOT)
                else:
                    # S3 storage
                    s3_key = f'topic_uploads/{topic.id}/{filename}'
                    with open(src_path, 'rb') as f:
                        default_storage.save(s3_key, ContentFile(f.read()))
                    relative_path = s3_key
                
                # Update topic field
                topic.content_file = relative_path
                topic.save(update_fields=['content_file'])
        except Exception as e:
            self.stdout.write(f"Failed to copy topic file {file_path}: {str(e)}") 