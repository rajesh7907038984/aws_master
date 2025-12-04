"""
Centralized Todo Service for Role-Based and User-Specific Todo Generation
"""
from django.utils import timezone
from django.db.models import Q, Count, Prefetch
from datetime import timedelta, datetime, time as dt_time
import logging

logger = logging.getLogger(__name__)

# Import models at module level to prevent scoping issues
try:
    from courses.models import CourseEnrollment
except ImportError:
    # Handle case where models aren't ready yet
    CourseEnrollment = None

class TodoService:
    """Service class for generating role-based and user-specific todo items"""
    
    def __init__(self, user):
        self.user = user
        self.now = timezone.now()
        self.today = self.now.date()
        self.tomorrow = self.today + timedelta(days=1)
        self.next_week = self.today + timedelta(days=7)
        self.next_month = self.today + timedelta(days=30)
        
    def get_todos(self, limit=10, offset=0):
        """Main method to get todos based on user role"""
        try:
            if self.user.role == 'learner':
                return self._get_learner_todos(limit, offset)
            elif self.user.role == 'instructor':
                return self._get_instructor_todos(limit, offset)
            elif self.user.role in ['admin', 'superadmin']:
                return self._get_admin_todos(limit, offset)
            elif self.user.role == 'globaladmin':
                return self._get_global_admin_todos(limit, offset)
            else:
                return []
        except Exception as e:
            logger.error(f"Error generating todos for user {self.user.id}: {str(e)}")
            return []
    
    def _get_learner_todos(self, limit=10, offset=0):
        """Generate todos for learners - comprehensive time-sensitive reminder list"""
        from assignments.models import Assignment, AssignmentSubmission
        from conferences.models import Conference, ConferenceTimeSlot
        from lms_messages.models import Message, MessageReadStatus
        from lms_notifications.models import Notification
        from courses.models import Topic
        from quiz.models import Quiz, QuizAttempt
        from discussions.models import Discussion
        from scorm.models import ScormPackage
        
        # Use module-level import, fallback to local import if needed
        if CourseEnrollment is None:
            from courses.models import CourseEnrollment as LocalCourseEnrollment
        else:
            LocalCourseEnrollment = CourseEnrollment
        
        todos = []
        
        # Get enrolled courses
        enrolled_courses = LocalCourseEnrollment.objects.filter(
            user=self.user
        ).select_related('course')
        enrolled_course_ids = list(enrolled_courses.values_list('course_id', flat=True))
        
        # 0. URGENT PRIORITY: Unread messages
        unread_messages = Message.objects.filter(
            recipients=self.user
        ).exclude(
            read_statuses__user=self.user,
            read_statuses__is_read=True
        ).select_related('sender').order_by('-created_at')[:10]
        
        for message in unread_messages:
            days_ago = (self.now.date() - message.created_at.date()).days
            if days_ago == 0:
                due_text, priority = "Received today", 'high'
            elif days_ago == 1:
                due_text, priority = "Received yesterday", 'high'
            else:
                due_text, priority = f"Received {days_ago} days ago", 'medium'
            
            sender_name = message.sender.get_full_name() if message.sender else "System"
            
            todos.append({
                'id': f'message_unread_{message.id}',
                'title': f'Message: {message.subject}',
                'description': f'From: {sender_name}',
                'due_date': due_text,
                'sort_date': message.created_at,
                'type': 'message',
                'priority': priority,
                'icon': 'envelope',
                'url': f'/messages/{message.id}/',
                'metadata': {
                    'message_id': message.id,
                    'sender_id': message.sender.id if message.sender else None,
                    'days_ago': days_ago,
                    'has_notification': True
                }
            })
        
        # 0b. URGENT PRIORITY: Graded assignments with feedback to review
        graded_submissions = AssignmentSubmission.objects.filter(
            user=self.user,
            status='graded',
            grade__isnull=False,
            graded_at__isnull=False
        ).exclude(
            Q(rubric_overall_feedback='') | Q(rubric_overall_feedback__isnull=True)
        ).select_related('assignment').prefetch_related('assignment__courses').order_by('-graded_at')[:10]
        
        for submission in graded_submissions:
            days_ago = (self.now.date() - submission.graded_at.date()).days
            if days_ago == 0:
                due_text, priority = "Graded today", 'high'
            elif days_ago <= 2:
                due_text, priority = f"Graded {days_ago} days ago", 'high'
            else:
                due_text, priority = f"Graded {days_ago} days ago", 'medium'
            
            # Calculate grade percentage
            grade_pct = (submission.grade / submission.assignment.points * 100) if submission.assignment.points else 0
            
            first_course = submission.assignment.courses.first()
            todos.append({
                'id': f'feedback_assignment_{submission.id}',
                'title': f'View Feedback: {submission.assignment.title}',
                'description': f'Assignment - Grade: {grade_pct:.0f}% - {first_course.title if first_course else "General"}',
                'due_date': due_text,
                'sort_date': submission.graded_at,
                'type': 'feedback',
                'priority': priority,
                'icon': 'comment-alt',
                'url': f'/assignments/{submission.assignment.id}/submission/{submission.id}/',
                'metadata': {
                    'submission_id': submission.id,
                    'assignment_id': submission.assignment.id,
                    'grade': submission.grade,
                    'grade_percentage': grade_pct,
                    'days_ago': days_ago,
                    'assessment_type': 'assignment',
                    'has_notification': True
                }
            })
        
        # 0c. URGENT PRIORITY: Quiz feedback received (graded quizzes with feedback)
        graded_quiz_attempts = QuizAttempt.objects.filter(
            user=self.user,
            is_completed=True,
            quiz__course__in=enrolled_course_ids
        ).select_related('quiz', 'quiz__course').order_by('-end_time')[:10]
        
        for attempt in graded_quiz_attempts:
            if attempt.quiz and attempt.end_time:
                days_ago = (self.now.date() - attempt.end_time.date()).days
                if days_ago == 0:
                    due_text, priority = "Completed today", 'high'
                elif days_ago <= 2:
                    due_text, priority = f"Completed {days_ago} days ago", 'high'
                else:
                    due_text, priority = f"Completed {days_ago} days ago", 'medium'
                
                todos.append({
                    'id': f'feedback_quiz_{attempt.id}',
                    'title': f'View Results: {attempt.quiz.title}',
                    'description': f'Quiz - Score: {attempt.score:.0f}% - {attempt.quiz.course.title if attempt.quiz.course else "General"}',
                    'due_date': due_text,
                    'sort_date': attempt.end_time,
                    'type': 'feedback',
                    'priority': priority,
                    'icon': 'comment-alt',
                    'url': f'/quiz/attempt/{attempt.id}/view/',
                    'metadata': {
                        'attempt_id': attempt.id,
                        'quiz_id': attempt.quiz.id,
                        'score': float(attempt.score),
                        'days_ago': days_ago,
                        'assessment_type': 'quiz',
                        'has_notification': True
                    }
                })
        
        if not enrolled_course_ids and not unread_messages and not graded_submissions:
            return []
        
        # 1. HIGH PRIORITY: Overdue assignments
        # Note: Assignment has ManyToMany relationship with Course through 'courses'
        overdue_assignments = Assignment.objects.filter(
            Q(courses__in=enrolled_course_ids),
            due_date__lt=self.now,
            is_active=True
        ).exclude(
            submissions__user=self.user,
            submissions__status__in=['submitted', 'graded']
        ).distinct()[:5]
        
        for assignment in overdue_assignments:
            days_overdue = (self.now.date() - assignment.due_date.date()).days
            first_course = assignment.courses.first()
            todos.append({
                'id': f'assignment_overdue_{assignment.id}',
                'title': f'OVERDUE: {assignment.title}',
                'description': f'{first_course.title if first_course else "General"} - {days_overdue} days overdue',
                'due_date': f'{days_overdue} days overdue',
                'sort_date': assignment.due_date - timedelta(days=1000),  # Highest priority
                'type': 'assignment',
                'priority': 'critical',
                'icon': 'exclamation-triangle',
                'url': f'/assignments/{assignment.id}/',
                'metadata': {
                    'assignment_id': assignment.id,
                    'course_id': first_course.id if first_course else None,
                    'points': getattr(assignment, 'points', None),
                    'assignment_points': getattr(assignment, 'points', None),  # For template compatibility
                    'days_overdue': days_overdue
                }
            })
        
        # 2. HIGH PRIORITY: Due today/tomorrow assignments
        # Note: Assignment has ManyToMany relationship with Course through 'courses'
        urgent_assignments = Assignment.objects.filter(
            Q(courses__in=enrolled_course_ids),
            due_date__gte=self.now,
            due_date__date__lte=self.tomorrow,
            is_active=True
        ).exclude(
            submissions__user=self.user,
            submissions__status__in=['submitted', 'graded']
        ).distinct().select_related('course').order_by('due_date')[:10]
        
        for assignment in urgent_assignments:
            due_text = self._format_due_date(assignment.due_date)
            priority = 'high' if assignment.due_date.date() <= self.tomorrow else 'medium'
            first_course = assignment.courses.first()
            
            todos.append({
                'id': f'assignment_urgent_{assignment.id}',
                'title': assignment.title,
                'description': f'{first_course.title if first_course else "General"}',
                'due_date': due_text,
                'sort_date': assignment.due_date,
                'type': 'assignment',
                'priority': priority,
                'icon': 'file-alt',
                'url': f'/assignments/{assignment.id}/',
                'metadata': {
                    'assignment_id': assignment.id,
                    'course_id': first_course.id if first_course else None,
                    'points': getattr(assignment, 'points', None),
                    'assignment_points': getattr(assignment, 'points', None)  # For template compatibility
                }
            })
        
        # 3. MEDIUM PRIORITY: Upcoming assignments (within month)
        # Note: Assignment has ManyToMany relationship with Course through 'courses'
        upcoming_assignments = Assignment.objects.filter(
            Q(courses__in=enrolled_course_ids),
            due_date__gt=self.tomorrow,
            due_date__date__lte=self.next_month,
            is_active=True
        ).exclude(
            submissions__user=self.user,
            submissions__status__in=['submitted', 'graded']
        ).distinct().select_related('course').order_by('due_date')[:20]
        
        for assignment in upcoming_assignments:
            due_text = self._format_due_date(assignment.due_date)
            first_course = assignment.courses.first()
            todos.append({
                'id': f'assignment_upcoming_{assignment.id}',
                'title': assignment.title,
                'description': f'Assignment - {first_course.title if first_course else "General"}',
                'due_date': due_text,
                'sort_date': assignment.due_date,
                'type': 'assignment',
                'priority': 'medium',
                'icon': 'file-alt',
                'url': f'/assignments/{assignment.id}/',
                'metadata': {
                    'assignment_id': assignment.id,
                    'course_id': first_course.id if first_course else None,
                    'points': getattr(assignment, 'points', None),
                    'assignment_points': getattr(assignment, 'points', None)  # For template compatibility
                }
            })
        
        # 3b. HIGH/MEDIUM PRIORITY: Quiz assessments (from Topics with Quiz content type)
        quiz_topics = Topic.objects.filter(
            section__course__in=enrolled_course_ids,
            content_type='Quiz',
            status='active',
            quiz__isnull=False,
            end_date__isnull=False,
            end_date__gte=self.today
        ).select_related('quiz', 'section__course').order_by('end_date')[:20]
        
        for topic in quiz_topics:
            # Check if user has completed the quiz
            completed_attempts = QuizAttempt.objects.filter(
                user=self.user,
                quiz=topic.quiz,
                is_completed=True
            ).exists()
            
            if not completed_attempts:
                # Create datetime from end_date (use end of day for sorting)
                quiz_due_datetime = datetime.combine(topic.end_date, dt_time(23, 59, 59))
                quiz_due_datetime = timezone.make_aware(quiz_due_datetime, timezone.get_current_timezone())
                
                due_text = self._format_due_date(quiz_due_datetime)
                if topic.end_date <= self.tomorrow:
                    priority = 'high'
                elif topic.end_date <= self.next_week:
                    priority = 'medium'
                else:
                    priority = 'low'
                
                todos.append({
                    'id': f'quiz_{topic.quiz.id}',
                    'title': topic.quiz.title if topic.quiz else topic.title,
                    'description': f'Quiz - {topic.section.course.title if topic.section and topic.section.course else "General"}',
                    'due_date': due_text,
                    'sort_date': quiz_due_datetime,
                    'type': 'quiz',
                    'priority': priority,
                    'icon': 'question-circle',
                    'url': f'/quiz/{topic.quiz.id}/' if topic.quiz else f'/courses/{topic.section.course.id}/view/' if topic.section and topic.section.course else '#',
                    'metadata': {
                        'quiz_id': topic.quiz.id if topic.quiz else None,
                        'topic_id': topic.id,
                        'course_id': topic.section.course.id if topic.section and topic.section.course else None
                    }
                })
        
        # 3c. HIGH/MEDIUM PRIORITY: Discussion assessments (from Topics with Discussion content type)
        discussion_topics = Topic.objects.filter(
            section__course__in=enrolled_course_ids,
            content_type='Discussion',
            status='active',
            discussion__isnull=False
        ).select_related('discussion', 'section__course').order_by('end_date')[:20]
        
        for topic in discussion_topics:
            # Use topic end_date or discussion end_date
            due_date = topic.end_date
            if not due_date and topic.discussion:
                due_date = topic.discussion.end_date
            
            if due_date and due_date >= self.today:
                # Create datetime from end_date (use end of day for sorting)
                discussion_due_datetime = datetime.combine(due_date, dt_time(23, 59, 59))
                discussion_due_datetime = timezone.make_aware(discussion_due_datetime, timezone.get_current_timezone())
                
                due_text = self._format_due_date(discussion_due_datetime)
                if due_date <= self.tomorrow:
                    priority = 'high'
                elif due_date <= self.next_week:
                    priority = 'medium'
                else:
                    priority = 'low'
                
                todos.append({
                    'id': f'discussion_{topic.discussion.id if topic.discussion else topic.id}',
                    'title': topic.discussion.title if topic.discussion else topic.title,
                    'description': f'Discussion - {topic.section.course.title if topic.section and topic.section.course else "General"}',
                    'due_date': due_text,
                    'sort_date': discussion_due_datetime,
                    'type': 'discussion',
                    'priority': priority,
                    'icon': 'comments',
                    'url': f'/discussions/{topic.discussion.id}/' if topic.discussion else f'/courses/{topic.section.course.id}/view/' if topic.section and topic.section.course else '#',
                    'metadata': {
                        'discussion_id': topic.discussion.id if topic.discussion else None,
                        'topic_id': topic.id,
                        'course_id': topic.section.course.id if topic.section and topic.section.course else None
                    }
                })
        
        # 3d. HIGH/MEDIUM PRIORITY: SCORM assessments (from Topics with SCORM content type)
        scorm_topics = Topic.objects.filter(
            section__course__in=enrolled_course_ids,
            content_type='SCORM',
            status='active',
            scorm__isnull=False,
            end_date__isnull=False,
            end_date__gte=self.today
        ).select_related('scorm', 'section__course').order_by('end_date')[:20]
        
        for topic in scorm_topics:
            # Create datetime from end_date (use end of day for sorting)
            scorm_due_datetime = datetime.combine(topic.end_date, dt_time(23, 59, 59))
            scorm_due_datetime = timezone.make_aware(scorm_due_datetime, timezone.get_current_timezone())
            
            due_text = self._format_due_date(scorm_due_datetime)
            if topic.end_date <= self.tomorrow:
                priority = 'high'
            elif topic.end_date <= self.next_week:
                priority = 'medium'
            else:
                priority = 'low'
            
            todos.append({
                'id': f'scorm_{topic.scorm.id if topic.scorm else topic.id}',
                'title': topic.scorm.title if topic.scorm else topic.title,
                'description': f'SCORM - {topic.section.course.title if topic.section and topic.section.course else "General"}',
                'due_date': due_text,
                'sort_date': scorm_due_datetime,
                'type': 'scorm',
                'priority': priority,
                'icon': 'graduation-cap',
                'url': f'/courses/{topic.section.course.id}/view/' if topic.section and topic.section.course else '#',
                'metadata': {
                    'scorm_id': topic.scorm.id if topic.scorm else None,
                    'topic_id': topic.id,
                    'course_id': topic.section.course.id if topic.section and topic.section.course else None
                }
            })
        
        # 4. HIGH/MEDIUM PRIORITY: ILT/Conference time slots - all available slots in chronological order
        # Get conferences with time slots enabled
        conferences_with_slots = Conference.objects.filter(
            course__in=enrolled_course_ids,
            use_time_slots=True,
            status='published'
        ).select_related('course').prefetch_related('time_slots')
        
        # Get all available time slots from conferences
        all_time_slots = ConferenceTimeSlot.objects.filter(
            conference__course__in=enrolled_course_ids,
            conference__status='published',
            is_available=True,
            date__gte=self.today
        ).select_related('conference', 'conference__course').order_by('date', 'start_time')[:20]
        
        for time_slot in all_time_slots:
            # Create datetime for sorting
            slot_datetime = datetime.combine(time_slot.date, time_slot.start_time)
            slot_datetime = timezone.make_aware(slot_datetime, timezone.get_current_timezone())
            
            due_text = self._format_due_date(slot_datetime)
            if time_slot.date <= self.tomorrow:
                priority = 'high'
            elif time_slot.date <= self.next_week:
                priority = 'medium'
            else:
                priority = 'low'
            
            time_str = f"{time_slot.start_time.strftime('%I:%M %p')} - {time_slot.end_time.strftime('%I:%M %p')}"
            
            todos.append({
                'id': f'conference_slot_{time_slot.id}',
                'title': f'ILT: {time_slot.conference.title}',
                'description': f'{time_slot.conference.course.title if time_slot.conference.course else "General"} - {time_str}',
                'due_date': due_text,
                'sort_date': slot_datetime,
                'type': 'conference',
                'priority': priority,
                'icon': 'video',
                'url': f'/conferences/{time_slot.conference.id}/',
                'metadata': {
                    'time_slot_id': time_slot.id,
                    'conference_id': time_slot.conference.id,
                    'course_id': time_slot.conference.course.id if time_slot.conference.course else None,
                    'meeting_time': time_str,
                    'date': time_slot.date,
                    'start_time': time_slot.start_time,
                    'end_time': time_slot.end_time
                }
            })
        
        # Also add regular conferences (without time slots) for backward compatibility
        regular_conferences = Conference.objects.filter(
            course__in=enrolled_course_ids,
            date__gte=self.today,
            date__lte=self.next_month,
            status='published',
            use_time_slots=False
        ).select_related('course').order_by('date')[:10]
        
        for conference in regular_conferences:
            # Create datetime for sorting
            conf_datetime = datetime.combine(conference.date, conference.start_time) if conference.start_time else conference.date
            if isinstance(conf_datetime, datetime) and not timezone.is_aware(conf_datetime):
                conf_datetime = timezone.make_aware(conf_datetime, timezone.get_current_timezone())
            
            due_text = self._format_due_date(conf_datetime)
            priority = 'high' if conference.date <= self.tomorrow else 'medium'
            
            time_str = conference.start_time.strftime("%I:%M %p") if conference.start_time else ""
            
            todos.append({
                'id': f'conference_{conference.id}',
                'title': f'ILT: {conference.title}',
                'description': f'{conference.course.title if conference.course else "General"} - {time_str}',
                'due_date': due_text,
                'sort_date': conf_datetime,
                'type': 'conference',
                'priority': priority,
                'icon': 'video',
                'url': f'/conferences/{conference.id}/',
                'metadata': {
                    'conference_id': conference.id,
                    'course_id': conference.course.id if conference.course else None,
                    'meeting_time': time_str
                }
            })
        
        # 5. LOW PRIORITY: In-progress courses (match sidebar logic - use progress > 0)
        incomplete_enrollments = enrolled_courses.filter(
            completed=False
        ).select_related('course')
        
        # Filter to only those with actual progress (match sidebar context processor logic)
        in_progress_list = []
        for enrollment in incomplete_enrollments:
            try:
                if enrollment.get_progress() > 0:
                    in_progress_list.append(enrollment)
            except Exception:
                continue
        
        # Sort by last_accessed (with null handling) and limit to 5
        in_progress_list = sorted(
            in_progress_list,
            key=lambda x: x.last_accessed or (self.now - timedelta(days=365)),
            reverse=True
        )[:5]
        
        for enrollment in in_progress_list:
            progress = enrollment.progress_percentage
            # Handle case where last_accessed might be None
            if enrollment.last_accessed:
                description = f'{progress}% complete - Last accessed {enrollment.last_accessed.strftime("%b %d")}'
            else:
                description = f'{progress}% complete'
            
            todos.append({
                'id': f'course_continue_{enrollment.course.id}',
                'title': f'Continue: {enrollment.course.title}',
                'description': description,
                'due_date': 'In Progress',
                'sort_date': self.now + timedelta(days=1),
                'type': 'course',
                'priority': 'low',
                'icon': 'book-open',
                'url': f'/courses/{enrollment.course.id}/view/',
                'metadata': {
                    'course_id': enrollment.course.id,
                    'progress': progress,
                    'enrollment_id': enrollment.id,
                    'course_name': enrollment.course.title
                }
            })
        
        # 6. LOW PRIORITY: Not started courses
        not_started_enrollments = enrolled_courses.filter(
            completed=False,
            last_accessed__isnull=True
        )[:3]
        
        for enrollment in not_started_enrollments:
            course_desc = (enrollment.course.short_description or 
                          enrollment.course.description or 
                          enrollment.course.title)[:60] + "..."
            
            todos.append({
                'id': f'course_start_{enrollment.course.id}',
                'title': f'Start: {enrollment.course.title}',
                'description': course_desc,
                'due_date': 'Not Started',
                'sort_date': self.now + timedelta(days=2),
                'type': 'course',
                'priority': 'low',
                'icon': 'play-circle',
                'url': f'/courses/{enrollment.course.id}/view/',
                'metadata': {
                    'course_id': enrollment.course.id,
                    'enrollment_id': enrollment.id,
                    'progress': 0
                }
            })
        
        # Sort todos chronologically by sort_date (time-sensitive order)
        # Priority order: critical > high > medium > low, then by date/time
        priority_order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
        todos.sort(key=lambda x: (
            priority_order.get(x['priority'], 4),
            x['sort_date'] if isinstance(x['sort_date'], (datetime, type(self.now))) else datetime.min.replace(tzinfo=timezone.get_current_timezone())
        ))
        
        # Apply pagination
        return todos[offset:offset + limit]
    
    def _get_instructor_todos(self, limit=10, offset=0):
        """Generate todos for instructors"""
        from courses.models import Course
        from assignments.models import AssignmentSubmission
        from users.models import CustomUser
        from lms_messages.models import Message, MessageReadStatus
        
        todos = []
        
        # 0. URGENT PRIORITY: Unread messages
        unread_messages = Message.objects.filter(
            recipients=self.user
        ).exclude(
            read_statuses__user=self.user,
            read_statuses__is_read=True
        ).select_related('sender').order_by('-created_at')[:10]
        
        for message in unread_messages:
            days_ago = (self.now.date() - message.created_at.date()).days
            if days_ago == 0:
                due_text, priority = "Received today", 'high'
            elif days_ago == 1:
                due_text, priority = "Received yesterday", 'high'
            else:
                due_text, priority = f"Received {days_ago} days ago", 'medium'
            
            sender_name = message.sender.get_full_name() if message.sender else "System"
            
            todos.append({
                'id': f'message_unread_{message.id}',
                'title': f'Message: {message.subject}',
                'description': f'From: {sender_name}',
                'due_date': due_text,
                'sort_date': message.created_at,
                'type': 'message',
                'priority': priority,
                'icon': 'envelope',
                'url': f'/messages/{message.id}/',
                'metadata': {
                    'message_id': message.id,
                    'sender_id': message.sender.id if message.sender else None,
                    'days_ago': days_ago,
                    'has_notification': True
                }
            })
        
        # Get instructor's courses
        if self.user.role == 'instructor' and self.user.branch:
            accessible_courses = Course.objects.filter(
                Q(instructor=self.user) | 
                Q(accessible_groups__memberships__user=self.user,
                  accessible_groups__memberships__is_active=True),
                branch=self.user.branch,
                is_active=True
            ).distinct()
        else:
            return []
        
        accessible_course_ids = list(accessible_courses.values_list('id', flat=True))
        
        # 1. HIGH PRIORITY: Submissions pending grading
        # Note: Assignment has ManyToMany relationship with Course through 'courses'
        pending_submissions = AssignmentSubmission.objects.filter(
            assignment__courses__id__in=accessible_course_ids,
            status='submitted'
        ).select_related('assignment', 'user').distinct().order_by('submitted_at')[:15]
        
        for submission in pending_submissions:
            days_since = (self.now.date() - submission.submitted_at.date()).days
            if days_since == 0:
                due_text, priority = "Submitted today", 'high'
            elif days_since == 1:
                due_text, priority = "Submitted yesterday", 'high'
            elif days_since <= 3:
                due_text, priority = f"Submitted {days_since} days ago", 'high'
            else:
                due_text, priority = f"Submitted {days_since} days ago", 'medium'
            
            todos.append({
                'id': f'submission_grade_{submission.id}',
                'title': f'Grade: {submission.assignment.title}',
                'description': f'{submission.user.get_full_name()} - {submission.assignment.course.title}',
                'due_date': due_text,
                'sort_date': submission.submitted_at,
                'type': 'grading',
                'priority': priority,
                'icon': 'check-circle',
                'url': f'/assignments/{submission.assignment.id}/submissions/',
                'metadata': {
                    'submission_id': submission.id,
                    'student_id': submission.user.id,
                    'assignment_id': submission.assignment.id,
                    'days_pending': days_since
                }
            })
        
        # 2. MEDIUM PRIORITY: Upcoming conferences to host
        from conferences.models import Conference
        upcoming_conferences = Conference.objects.filter(
            course__in=accessible_course_ids,
            date__gte=self.now,
            date__lte=self.next_week,
            status='published'
        ).select_related('course').order_by('date')[:5]
        
        for conference in upcoming_conferences:
            due_text = self._format_due_date(conference.date)
            priority = 'high' if conference.date.date() <= self.tomorrow else 'medium'
            
            todos.append({
                'id': f'conference_host_{conference.id}',
                'title': f'Host: {conference.title}',
                'description': f'{conference.course.title if conference.course else "General"} - {conference.date.strftime("%I:%M %p")}',
                'due_date': due_text,
                'sort_date': conference.date,
                'type': 'conference',
                'priority': priority,
                'icon': 'video',
                'url': f'/conferences/{conference.id}/edit/',
                'metadata': {
                    'conference_id': conference.id,
                    'course_id': conference.course.id if conference.course else None,
                    'meeting_time': conference.date.strftime("%I:%M %p")
                }
            })
        
        # 3. LOW PRIORITY: Course management tasks
        for course in accessible_courses[:5]:
            # Get enrollment count - ONLY count learner role users, exclude instructors/admins
            enrollment_count = course.courseenrollment_set.filter(user__role='learner').count()
            
            todos.append({
                'id': f'course_manage_{course.id}',
                'title': f'Manage: {course.title}',
                'description': f'{enrollment_count} students enrolled',
                'due_date': 'Ongoing',
                'sort_date': self.now + timedelta(days=5),
                'type': 'course_management',
                'priority': 'low',
                'icon': 'chalkboard-teacher',
                'url': f'/courses/{course.id}/edit/',
                'metadata': {
                    'course_id': course.id,
                    'enrollment_count': enrollment_count
                }
            })
        
        # Sort todos by priority and date
        priority_order = {'high': 1, 'medium': 2, 'low': 3}
        todos.sort(key=lambda x: (priority_order.get(x['priority'], 4), x['sort_date']))
        
        return todos[offset:offset + limit]
    
    def _get_admin_todos(self, limit=10, offset=0):
        """Generate todos for admins/superadmins"""
        from users.models import CustomUser
        from assignments.models import AssignmentSubmission
        from courses.models import Course
        
        todos = []
        
        # Determine admin scope
        if self.user.role == 'admin':
            scope_filter = {'branch': self.user.branch} if self.user.branch else {}
        else:  # superadmin
            from core.utils.business_filtering import get_superadmin_business_filter
            business_scope = get_superadmin_business_filter(self.user)
            if business_scope:
                scope_filter = {'branch__business__in': business_scope}
            else:
                scope_filter = {}
        
        # 1. HIGH PRIORITY: New user registrations
        pending_users = CustomUser.objects.filter(
            is_active=False,
            date_joined__gte=self.now - timedelta(days=30),
            **scope_filter
        ).order_by('-date_joined')[:10]
        
        for user in pending_users:
            days_since = (self.now.date() - user.date_joined.date()).days
            if days_since == 0:
                due_text, priority = "Registered today", 'high'
            elif days_since <= 3:
                due_text, priority = f"Registered {days_since} days ago", 'high'
            else:
                due_text, priority = f"Registered {days_since} days ago", 'medium'
            
            todos.append({
                'id': f'user_approval_{user.id}',
                'title': f'Approve: {user.get_full_name()}',
                'description': f'{user.email} - {user.role.title() if user.role else "User"}',
                'due_date': due_text,
                'sort_date': user.date_joined,
                'type': 'user_management',
                'priority': priority,
                'icon': 'user-check',
                'url': f'/users/{user.id}/edit/',
                'metadata': {
                    'user_id': user.id,
                    'user_role': user.role,
                    'days_pending': days_since
                }
            })
        
        # 2. MEDIUM PRIORITY: Course management
        if scope_filter:
            recent_courses = Course.objects.filter(
                created_at__gte=self.now - timedelta(days=7),
                **scope_filter
            ).order_by('-created_at')[:5]
        else:
            recent_courses = Course.objects.filter(
                created_at__gte=self.now - timedelta(days=7)
            ).order_by('-created_at')[:5]
        
        for course in recent_courses:
            days_since = (self.now.date() - course.created_at.date()).days
            # Get enrollment count - ONLY count learner role users, exclude instructors/admins  
            enrollment_count = course.courseenrollment_set.filter(user__role='learner').count()
            
            todos.append({
                'id': f'course_review_{course.id}',
                'title': f'Review: {course.title}',
                'description': f'Created {days_since} days ago - {enrollment_count} enrollments',
                'due_date': f'Created {days_since} days ago',
                'sort_date': course.created_at,
                'type': 'course_review',
                'priority': 'medium',
                'icon': 'eye',
                'url': f'/courses/{course.id}/view/',
                'metadata': {
                    'course_id': course.id,
                    'enrollment_count': enrollment_count,
                    'days_since_created': days_since
                }
            })
        
        # 3. LOW PRIORITY: System maintenance
        todos.append({
            'id': 'system_maintenance',
            'title': 'System Health Check',
            'description': 'Review system performance and maintenance tasks',
            'due_date': 'Weekly',
            'sort_date': self.now + timedelta(days=7),
            'type': 'maintenance',
            'priority': 'low',
            'icon': 'cogs',
            'url': '/users/admin/',
            'metadata': {}
        })
        
        # Sort and return
        priority_order = {'high': 1, 'medium': 2, 'low': 3}
        todos.sort(key=lambda x: (priority_order.get(x['priority'], 4), x['sort_date']))
        
        return todos[offset:offset + limit]
    
    def _get_global_admin_todos(self, limit=10, offset=0):
        """Generate todos for global admins"""
        from users.models import CustomUser
        from courses.models import Course
        from business.models import Business
        
        todos = []
        
        # 1. System-wide monitoring tasks
        todos.append({
            'id': 'global_system_overview',
            'title': 'Global System Overview',
            'description': 'Monitor platform-wide performance and usage',
            'due_date': 'Daily',
            'sort_date': self.now,
            'type': 'monitoring',
            'priority': 'high',
            'icon': 'globe',
            'url': '/dashboard/globaladmin/',
            'metadata': {}
        })
        
        # 2. New business registrations
        recent_businesses = Business.objects.filter(
            created_at__gte=self.now - timedelta(days=7)
        ).order_by('-created_at')[:5]
        
        for business in recent_businesses:
            days_since = (self.now.date() - business.created_at.date()).days
            todos.append({
                'id': f'business_review_{business.id}',
                'title': f'Review: {business.name}',
                'description': f'New business registered {days_since} days ago',
                'due_date': f'{days_since} days ago',
                'sort_date': business.created_at,
                'type': 'business_review',
                'priority': 'high' if days_since <= 2 else 'medium',
                'icon': 'building',
                'url': f'/business/{business.id}/',
                'metadata': {
                    'business_id': business.id,
                    'days_since_created': days_since
                }
            })
        
        # Sort and return
        priority_order = {'high': 1, 'medium': 2, 'low': 3}
        todos.sort(key=lambda x: (priority_order.get(x['priority'], 4), x['sort_date']))
        
        return todos[offset:offset + limit]
    
    def _format_due_date(self, due_date):
        """Format due date for display"""
        if isinstance(due_date, str):
            return due_date
            
        due_date_only = due_date.date() if hasattr(due_date, 'date') else due_date
        
        if due_date_only == self.today:
            return "Today"
        elif due_date_only == self.tomorrow:
            return "Tomorrow"
        elif due_date_only <= self.next_week:
            return due_date.strftime('%a %b %d')
        else:
            return due_date.strftime('%b %d')
    
    def get_todo_counts_by_type(self):
        """Get todo counts grouped by type"""
        todos = self.get_todos(limit=100)  # Get more for accurate counts
        
        counts = {}
        for todo in todos:
            todo_type = todo['type']
            priority = todo['priority']
            
            if todo_type not in counts:
                counts[todo_type] = {'total': 0, 'high': 0, 'medium': 0, 'low': 0, 'critical': 0}
            
            counts[todo_type]['total'] += 1
            counts[todo_type][priority] += 1
        
        return counts
    
    def get_todos_by_type(self, todo_type, limit=10, offset=0):
        """Get todos filtered by type"""
        all_todos = self.get_todos(limit=100)  # Get more for filtering
        filtered_todos = [todo for todo in all_todos if todo['type'] == todo_type]
        return filtered_todos[offset:offset + limit]
