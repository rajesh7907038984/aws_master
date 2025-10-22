import os
import json
import zipfile
import shutil
from datetime import datetime
from django.core.management.base import BaseCommand
from django.core import serializers
from django.conf import settings
from django.utils import timezone
from django.contrib.auth import get_user_model

from courses.models import Course, Topic, CourseEnrollment, TopicProgress
from assignments.models import Assignment, AssignmentSubmission, AssignmentAttachment
from quiz.models import Quiz, Question, QuizAttempt
from discussions.models import Discussion
from conferences.models import Conference
from account_settings.models import ExportJob

User = get_user_model()

class Command(BaseCommand):
    help = 'Export LMS data to JSON with optional file attachments'

    def add_arguments(self, parser):
        parser.add_argument('--type', type=str, required=True, 
                          choices=['users', 'courses', 'topics', 'assignments', 'quizzes', 'discussions', 'conferences', 'all'],
                          help='Type of data to export')
        parser.add_argument('--output', type=str, required=True, help='Output directory path')
        parser.add_argument('--include-files', action='store_true', help='Include related files in export')
        parser.add_argument('--job-id', type=int, help='Export job ID for tracking')

    def handle(self, *args, **options):
        export_type = options['type']
        output_path = options['output']
        include_files = options['include_files']
        job_id = options.get('job_id')
        
        job = None
        if job_id:
            try:
                job = ExportJob.objects.get(id=job_id)
                job.status = 'processing'
                job.save()
            except ExportJob.DoesNotExist:
                pass

        try:
            self.stdout.write(f'Starting export of {export_type} data...')
            
            # Create output directory if it doesn't exist
            os.makedirs(output_path, exist_ok=True)
            
            # Create export directory with timestamp
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            export_dir = os.path.join(output_path, f'{export_type}_export_{timestamp}')
            os.makedirs(export_dir, exist_ok=True)
            
            record_count = 0
            
            if export_type == 'users' or export_type == 'all':
                record_count += self.export_users(export_dir, include_files)
            
            if export_type == 'courses' or export_type == 'all':
                record_count += self.export_courses(export_dir, include_files)
                
            if export_type == 'topics' or export_type == 'all':
                record_count += self.export_topics(export_dir, include_files)
                
            if export_type == 'assignments' or export_type == 'all':
                record_count += self.export_assignments(export_dir, include_files)
                
            if export_type == 'quizzes' or export_type == 'all':
                record_count += self.export_quizzes(export_dir, include_files)
                
            if export_type == 'discussions' or export_type == 'all':
                record_count += self.export_discussions(export_dir, include_files)
                
            if export_type == 'conferences' or export_type == 'all':
                record_count += self.export_conferences(export_dir, include_files)
            
            # Create ZIP file
            zip_path = f'{export_dir}.zip'
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, dirs, files in os.walk(export_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, export_dir)
                        zipf.write(file_path, arcname)
            
            # Remove the uncompressed directory
            shutil.rmtree(export_dir)
            
            # Get file size
            file_size = os.path.getsize(zip_path)
            
            # Update job status
            if job:
                job.status = 'completed'
                job.file_path = zip_path
                job.file_size = file_size
                job.record_count = record_count
                job.completed_at = timezone.now()
                job.save()
            
            self.stdout.write(self.style.SUCCESS(f'Export completed: {zip_path}'))
            self.stdout.write(f'Records exported: {record_count}')
            self.stdout.write(f'File size: {file_size / 1024 / 1024:.2f} MB')
            
        except Exception as e:
            error_msg = str(e)
            self.stdout.write(self.style.ERROR(f'Export failed: {error_msg}'))
            
            if job:
                job.status = 'failed'
                job.error_message = error_msg
                job.save()

    def export_users(self, export_dir, include_files):
        """Export users data"""
        users = User.objects.all()
        users_data = []
        
        for user in users:
            user_dict = {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'role': user.role,
                'is_active': user.is_active,
                'date_joined': user.date_joined.isoformat() if user.date_joined else None,
                'branch_id': user.branch_id,
                'phone_number': user.phone_number,
                'language': user.language,
                'timezone': user.timezone,
                # Personal information
                'unique_learner_number': user.unique_learner_number,
                'family_name': user.family_name,
                'given_names': user.given_names,
                'date_of_birth': user.date_of_birth.isoformat() if user.date_of_birth else None,
                'sex': user.sex,
                'ethnicity': user.ethnicity,
                'current_postcode': user.current_postcode,
                'address_line1': user.address_line1,
                'address_line2': user.address_line2,
                'city': user.city,
                'county': user.county,
                'country': user.country,
                'contact_preference': user.contact_preference,
                # Education
                'study_area': user.study_area,
                'level_of_study': user.level_of_study,
                'grades': user.grades,
                'education_data': user.education_data,
                # Employment
                'job_role': user.job_role,
                'industry': user.industry,
                'duration': user.duration,
                'key_skills': user.key_skills,
                # Additional fields...
            }
            
            # Handle file fields
            if include_files:
                files_dir = os.path.join(export_dir, 'user_files', str(user.id))
                os.makedirs(files_dir, exist_ok=True)
                
                if user.cv_file:
                    try:
                        src_path = user.cv_file.path
                        if os.path.exists(src_path):
                            dst_path = os.path.join(files_dir, 'cv' + os.path.splitext(user.cv_file.name)[1])
                            shutil.copy2(src_path, dst_path)
                            user_dict['cv_file_path'] = f'user_files/{user.id}/cv{os.path.splitext(user.cv_file.name)[1]}'
                    except (ValueError, AttributeError):
                        pass
                
                if user.statement_of_purpose_file:
                    try:
                        src_path = user.statement_of_purpose_file.path
                        if os.path.exists(src_path):
                            dst_path = os.path.join(files_dir, 'sop' + os.path.splitext(user.statement_of_purpose_file.name)[1])
                            shutil.copy2(src_path, dst_path)
                            user_dict['statement_of_purpose_file_path'] = f'user_files/{user.id}/sop{os.path.splitext(user.statement_of_purpose_file.name)[1]}'
                    except (ValueError, AttributeError):
                        pass
            
            users_data.append(user_dict)
        
        # Write users data to JSON
        with open(os.path.join(export_dir, 'users.json'), 'w') as f:
            json.dump(users_data, f, indent=2, default=str)
        
        self.stdout.write(f'Exported {len(users_data)} users')
        return len(users_data)

    def export_courses(self, export_dir, include_files):
        """Export courses data"""
        courses = Course.objects.all()
        courses_data = []
        
        for course in courses:
            course_dict = {
                'id': course.id,
                'title': course.title,
                'short_description': course.short_description,
                'description': course.description,
                'course_code': course.course_code,
                'course_outcomes': course.course_outcomes,
                'course_rubrics': course.course_rubrics,
                'category_id': course.category_id,
                'is_active': course.is_active,
                'language': course.language,
                'visibility': course.visibility,
                'schedule_type': course.schedule_type,
                'require_enrollment': course.require_enrollment,
                'price': str(course.price),
                'branch_id': course.branch_id,
                'instructor_id': course.instructor_id,
                'created_at': course.created_at.isoformat() if course.created_at else None,
                'updated_at': course.updated_at.isoformat() if course.updated_at else None,
            }
            
            # Handle file fields
            if include_files:
                files_dir = os.path.join(export_dir, 'course_files', str(course.id))
                os.makedirs(files_dir, exist_ok=True)
                
                if course.course_image:
                    try:
                        try:
                            src_path = course.course_image.path
                            if os.path.exists(src_path):
                                dst_path = os.path.join(files_dir, 'image' + os.path.splitext(course.course_image.name)[1])
                                shutil.copy2(src_path, dst_path)
                                course_dict['course_image_path'] = f'course_files/{course.id}/image{os.path.splitext(course.course_image.name)[1]}'
                        except NotImplementedError:
                            # Cloud storage doesn't support absolute paths, skip file export
                            pass
                    except (ValueError, AttributeError):
                        pass
                
                if course.course_video:
                    try:
                        try:
                            src_path = course.course_video.path
                            if os.path.exists(src_path):
                                dst_path = os.path.join(files_dir, 'video' + os.path.splitext(course.course_video.name)[1])
                                shutil.copy2(src_path, dst_path)
                                course_dict['course_video_path'] = f'course_files/{course.id}/video{os.path.splitext(course.course_video.name)[1]}'
                        except NotImplementedError:
                            # Cloud storage doesn't support absolute paths, skip file export
                            pass
                    except (ValueError, AttributeError):
                        pass
            
            courses_data.append(course_dict)
        
        # Export enrollments
        enrollments = CourseEnrollment.objects.all()
        enrollments_data = []
        for enrollment in enrollments:
            enrollments_data.append({
                'id': enrollment.id,
                'course_id': enrollment.course_id,
                'user_id': enrollment.user_id,
                'enrolled_at': enrollment.enrolled_at.isoformat() if enrollment.enrolled_at else None,
                'completed': enrollment.completed,
                'completion_date': enrollment.completion_date.isoformat() if enrollment.completion_date else None,
            })
        
        # Write to JSON files
        with open(os.path.join(export_dir, 'courses.json'), 'w') as f:
            json.dump(courses_data, f, indent=2, default=str)
            
        with open(os.path.join(export_dir, 'course_enrollments.json'), 'w') as f:
            json.dump(enrollments_data, f, indent=2, default=str)
        
        self.stdout.write(f'Exported {len(courses_data)} courses and {len(enrollments_data)} enrollments')
        return len(courses_data) + len(enrollments_data)

    def export_topics(self, export_dir, include_files):
        """Export topics data"""
        topics = Topic.objects.all()
        topics_data = []
        
        for topic in topics:
            topic_dict = {
                'id': topic.id,
                'title': topic.title,
                'description': topic.description,
                'instructions': topic.instructions,
                'content_type': topic.content_type,
                'status': topic.status,
                'start_date': topic.start_date.isoformat() if topic.start_date else None,
                'end_date': topic.end_date.isoformat() if topic.end_date else None,
                'endless_access': topic.endless_access,
                'web_url': topic.web_url,
                'section_id': topic.section_id,
                'text_content': topic.text_content,
                'embed_code': topic.embed_code,
                'order': topic.order,
                'alignment': topic.alignment,
                'discussion_id': topic.discussion_id,
                'conference_id': topic.conference_id,
                'quiz_id': topic.quiz_id,
                'assignment_id': topic.assignment_id,
                'created_at': topic.created_at.isoformat() if topic.created_at else None,
                'updated_at': topic.updated_at.isoformat() if topic.updated_at else None,
            }
            
            # Handle content files
            if include_files and topic.content_file:
                try:
                    src_path = topic.content_file.path
                    if os.path.exists(src_path):
                        files_dir = os.path.join(export_dir, 'topic_files', str(topic.id))
                        os.makedirs(files_dir, exist_ok=True)
                        dst_path = os.path.join(files_dir, os.path.basename(topic.content_file.name))
                        shutil.copy2(src_path, dst_path)
                        topic_dict['content_file_path'] = f'topic_files/{topic.id}/{os.path.basename(topic.content_file.name)}'
                except (ValueError, AttributeError):
                    pass
            
            topics_data.append(topic_dict)
        
        # Export topic progress
        progress_data = []
        for progress in TopicProgress.objects.all():
            progress_data.append({
                'id': progress.id,
                'user_id': progress.user_id,
                'topic_id': progress.topic_id,
                'completed': progress.completed,
                'progress_data': progress.progress_data,
                'last_score': str(progress.last_score) if progress.last_score else None,
                'best_score': str(progress.best_score) if progress.best_score else None,
                'total_time_spent': progress.total_time_spent,
                'attempts': progress.attempts,
                'last_accessed': progress.last_accessed.isoformat() if progress.last_accessed else None,
                'completed_at': progress.completed_at.isoformat() if progress.completed_at else None,
            })
        
        # Write to JSON files
        with open(os.path.join(export_dir, 'topics.json'), 'w') as f:
            json.dump(topics_data, f, indent=2, default=str)
            
        with open(os.path.join(export_dir, 'topic_progress.json'), 'w') as f:
            json.dump(progress_data, f, indent=2, default=str)
        
        self.stdout.write(f'Exported {len(topics_data)} topics and {len(progress_data)} progress records')
        return len(topics_data) + len(progress_data)

    def export_assignments(self, export_dir, include_files):
        """Export assignments data"""
        assignments = Assignment.objects.all()
        assignments_data = []
        
        for assignment in assignments:
            assignment_dict = {
                'id': assignment.id,
                'title': assignment.title,
                'description': assignment.description,
                'instructions': getattr(assignment, 'instructions', ''),
                'points': str(assignment.points) if hasattr(assignment, 'points') else None,
                'due_date': assignment.due_date.isoformat() if hasattr(assignment, 'due_date') and assignment.due_date else None,
                'is_active': assignment.is_active,
                'course_id': assignment.course_id,
                'created_at': assignment.created_at.isoformat() if assignment.created_at else None,
                'updated_at': assignment.updated_at.isoformat() if assignment.updated_at else None,
            }
            assignments_data.append(assignment_dict)
        
        # Export submissions
        submissions_data = []
        for submission in AssignmentSubmission.objects.all():
            submission_dict = {
                'id': submission.id,
                'assignment_id': submission.assignment_id,
                'user_id': submission.user_id,
                'submission_text': submission.submission_text,
                'submitted_at': submission.submitted_at.isoformat() if submission.submitted_at else None,
                'status': submission.status,
                'grade': str(submission.grade) if submission.grade else None,
                'graded_by_id': submission.graded_by_id,
                'graded_at': submission.graded_at.isoformat() if submission.graded_at else None,
            }
            
            # Handle submission files
            if include_files and submission.submission_file:
                try:
                    src_path = submission.submission_file.path
                    if os.path.exists(src_path):
                        files_dir = os.path.join(export_dir, 'assignment_files', str(submission.id))
                        os.makedirs(files_dir, exist_ok=True)
                        dst_path = os.path.join(files_dir, os.path.basename(submission.submission_file.name))
                        shutil.copy2(src_path, dst_path)
                        submission_dict['submission_file_path'] = f'assignment_files/{submission.id}/{os.path.basename(submission.submission_file.name)}'
                except (ValueError, AttributeError):
                    pass
            
            submissions_data.append(submission_dict)
        
        # Write to JSON files
        with open(os.path.join(export_dir, 'assignments.json'), 'w') as f:
            json.dump(assignments_data, f, indent=2, default=str)
            
        with open(os.path.join(export_dir, 'assignment_submissions.json'), 'w') as f:
            json.dump(submissions_data, f, indent=2, default=str)
        
        self.stdout.write(f'Exported {len(assignments_data)} assignments and {len(submissions_data)} submissions')
        return len(assignments_data) + len(submissions_data)

    def export_quizzes(self, export_dir, include_files):
        """Export quizzes data"""
        quizzes = Quiz.objects.all()
        quizzes_data = []
        
        for quiz in quizzes:
            quiz_dict = {
                'id': quiz.id,
                'title': quiz.title,
                'description': quiz.description,
                'instructions': getattr(quiz, 'instructions', ''),
                'time_limit': quiz.time_limit if hasattr(quiz, 'time_limit') else None,
                'attempts_allowed': quiz.attempts_allowed if hasattr(quiz, 'attempts_allowed') else None,
                'is_active': quiz.is_active,
                'created_at': quiz.created_at.isoformat() if quiz.created_at else None,
                'updated_at': quiz.updated_at.isoformat() if quiz.updated_at else None,
            }
            quizzes_data.append(quiz_dict)
        
        # Export questions
        questions_data = []
        for question in Question.objects.all():
            question_dict = {
                'id': question.id,
                'quiz_id': question.quiz_id,
                'question_text': question.question_text,
                'question_type': question.question_type,
                'points': str(question.points) if hasattr(question, 'points') else None,
                'order': question.order if hasattr(question, 'order') else None,
                'created_at': question.created_at.isoformat() if question.created_at else None,
            }
            questions_data.append(question_dict)
        
        # Export quiz attempts
        attempts_data = []
        for attempt in QuizAttempt.objects.all():
            attempts_data.append({
                'id': attempt.id,
                'quiz_id': attempt.quiz_id,
                'user_id': attempt.user_id,
                'score': str(attempt.score) if attempt.score else None,
                'is_completed': attempt.is_completed,
                'start_time': attempt.start_time.isoformat() if attempt.start_time else None,
                'end_time': attempt.end_time.isoformat() if attempt.end_time else None,
                'ip_address': getattr(attempt, 'ip_address', None),
                'user_agent': getattr(attempt, 'user_agent', None),
                'last_activity': attempt.last_activity.isoformat() if hasattr(attempt, 'last_activity') and attempt.last_activity else None,
            })
        
        # Write to JSON files
        with open(os.path.join(export_dir, 'quizzes.json'), 'w') as f:
            json.dump(quizzes_data, f, indent=2, default=str)
            
        with open(os.path.join(export_dir, 'quiz_questions.json'), 'w') as f:
            json.dump(questions_data, f, indent=2, default=str)
            
        with open(os.path.join(export_dir, 'quiz_attempts.json'), 'w') as f:
            json.dump(attempts_data, f, indent=2, default=str)
        
        self.stdout.write(f'Exported {len(quizzes_data)} quizzes, {len(questions_data)} questions, and {len(attempts_data)} attempts')
        return len(quizzes_data) + len(questions_data) + len(attempts_data)

    def export_discussions(self, export_dir, include_files):
        """Export discussions data"""
        discussions = Discussion.objects.all()
        discussions_data = []
        
        for discussion in discussions:
            discussions_data.append({
                'id': discussion.id,
                'title': discussion.title,
                'description': getattr(discussion, 'description', ''),
                'is_published': getattr(discussion, 'is_published', True),
                'course_id': getattr(discussion, 'course_id', None),
                'created_at': discussion.created_at.isoformat() if discussion.created_at else None,
                'updated_at': discussion.updated_at.isoformat() if discussion.updated_at else None,
            })
        
        with open(os.path.join(export_dir, 'discussions.json'), 'w') as f:
            json.dump(discussions_data, f, indent=2, default=str)
        
        self.stdout.write(f'Exported {len(discussions_data)} discussions')
        return len(discussions_data)

    def export_conferences(self, export_dir, include_files):
        """Export conferences data"""
        conferences = Conference.objects.all()
        conferences_data = []
        
        for conference in conferences:
            conferences_data.append({
                'id': conference.id,
                'title': conference.title,
                'description': getattr(conference, 'description', ''),
                'scheduled_time': conference.scheduled_time.isoformat() if hasattr(conference, 'scheduled_time') and conference.scheduled_time else None,
                'duration': conference.duration if hasattr(conference, 'duration') else None,
                'is_published': getattr(conference, 'is_published', True),
                'course_id': getattr(conference, 'course_id', None),
                'created_at': conference.created_at.isoformat() if conference.created_at else None,
                'updated_at': conference.updated_at.isoformat() if conference.updated_at else None,
            })
        
        with open(os.path.join(export_dir, 'conferences.json'), 'w') as f:
            json.dump(conferences_data, f, indent=2, default=str)
        
        self.stdout.write(f'Exported {len(conferences_data)} conferences')
        return len(conferences_data) 