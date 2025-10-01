import random
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.contrib.auth import get_user_model
from assignments.models import Assignment, AssignmentSubmission, AssignmentInteractionLog, AssignmentSessionLog

User = get_user_model()

class Command(BaseCommand):
    help = 'Populate historical interaction data for existing assignments to demonstrate comprehensive tracking'

    def add_arguments(self, parser):
        parser.add_argument(
            '--assignment-id',
            type=int,
            help='Specific assignment ID to populate data for',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be created without actually creating it',
        )

    def handle(self, *args, **options):
        assignment_id = options.get('assignment_id')
        dry_run = options.get('dry_run', False)
        
        if assignment_id:
            try:
                assignments = [Assignment.objects.get(id=assignment_id)]
                self.stdout.write(f"Populating data for assignment ID {assignment_id}")
            except Assignment.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f'Assignment with ID {assignment_id} does not exist')
                )
                return
        else:
            assignments = Assignment.objects.all()[:5]  # Limit to first 5 assignments
            self.stdout.write(f"Populating data for {len(assignments)} assignments")

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN MODE - No data will be created"))

        total_interactions = 0
        total_sessions = 0

        for assignment in assignments:
            self.stdout.write(f"\nProcessing assignment: {assignment.title}")
            
            # Get all submissions for this assignment
            submissions = AssignmentSubmission.objects.filter(assignment=assignment)
            
            if not submissions.exists():
                self.stdout.write(f"  No submissions found for {assignment.title}")
                continue

            for submission in submissions:
                user = submission.user
                self.stdout.write(f"  Processing user: {user.get_full_name()}")
                
                # Create a realistic timeline of interactions
                submission_date = submission.submitted_at
                if not submission_date:
                    submission_date = timezone.now() - timedelta(days=random.randint(1, 30))
                
                # Create interactions leading up to submission
                interactions_data = self._generate_interaction_timeline(
                    assignment, user, submission, submission_date
                )
                
                if not dry_run:
                    # Create session logs
                    sessions_created = self._create_session_logs(
                        assignment, user, submission_date, interactions_data['sessions']
                    )
                    total_sessions += sessions_created
                    
                    # Create interaction logs
                    interactions_created = self._create_interaction_logs(
                        assignment, user, submission, interactions_data['interactions']
                    )
                    total_interactions += interactions_created
                else:
                    total_sessions += len(interactions_data['sessions'])
                    total_interactions += len(interactions_data['interactions'])
                    
                    self.stdout.write(f"    Would create {len(interactions_data['sessions'])} sessions")
                    self.stdout.write(f"    Would create {len(interactions_data['interactions'])} interactions")

        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f"\nDRY RUN COMPLETE:\n"
                    f"Would create {total_sessions} session logs\n"
                    f"Would create {total_interactions} interaction logs"
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"\nCOMPLETE:\n"
                    f"Created {total_sessions} session logs\n"
                    f"Created {total_interactions} interaction logs"
                )
            )

    def _generate_interaction_timeline(self, assignment, user, submission, submission_date):
        """Generate a realistic timeline of interactions for a user"""
        interactions = []
        sessions = []
        
        # Generate interactions over multiple days leading to submission
        days_before_submission = random.randint(1, 14)  # 1-14 days before submission
        
        for day_offset in range(days_before_submission, 0, -1):
            if random.random() < 0.7:  # 70% chance of activity on any given day
                day_date = submission_date - timedelta(days=day_offset)
                
                # Create 1-3 sessions per active day
                num_sessions = random.randint(1, 3)
                
                for session_num in range(num_sessions):
                    session_start = day_date.replace(
                        hour=random.randint(8, 20),
                        minute=random.randint(0, 59),
                        second=random.randint(0, 59)
                    )
                    
                    # Session duration: 5 minutes to 2 hours
                    session_duration = random.randint(300, 7200)  # 5 min to 2 hours in seconds
                    session_end = session_start + timedelta(seconds=session_duration)
                    
                    session_data = {
                        'start_time': session_start,
                        'end_time': session_end,
                        'duration_seconds': session_duration,
                        'page_views': random.randint(3, 15),
                        'interactions_count': random.randint(5, 25)
                    }
                    sessions.append(session_data)
                    
                    # Generate interactions within this session
                    session_interactions = self._generate_session_interactions(
                        assignment, user, submission, session_start, session_end
                    )
                    interactions.extend(session_interactions)
        
        # Add final submission interaction
        interactions.append({
            'interaction_type': 'submission_submit',
            'created_at': submission_date,
            'submission': submission,
            'interaction_data': {
                'submission_type': 'final_submission',
                'file_submitted': bool(submission.submission_file),
                'text_submitted': bool(submission.submission_text)
            }
        })
        
        return {
            'sessions': sessions,
            'interactions': interactions
        }

    def _generate_session_interactions(self, assignment, user, submission, start_time, end_time):
        """Generate realistic interactions within a session"""
        interactions = []
        session_duration = (end_time - start_time).total_seconds()
        
        # Always start with viewing the assignment
        interactions.append({
            'interaction_type': 'view',
            'created_at': start_time,
            'interaction_data': {
                'page_url': f'/assignments/{assignment.id}/',
                'session_start': True
            }
        })
        
        # Generate random interactions throughout the session
        interaction_types = [
            ('view', 0.3),  # 30% chance
            ('start_submission', 0.15),  # 15% chance
            ('draft_save', 0.2),  # 20% chance
            ('file_download', 0.1),  # 10% chance if attachments exist
            ('rubric_viewed', 0.1),  # 10% chance if rubric exists
        ]
        
        # Generate 3-10 interactions per session
        num_interactions = random.randint(3, 10)
        
        for i in range(num_interactions):
            # Distribute interactions throughout the session
            time_offset = (session_duration / num_interactions) * i
            interaction_time = start_time + timedelta(seconds=time_offset + random.randint(0, int(session_duration / num_interactions)))
            
            # Choose interaction type based on probabilities
            rand_val = random.random()
            cumulative_prob = 0
            
            for interaction_type, prob in interaction_types:
                cumulative_prob += prob
                if rand_val <= cumulative_prob:
                    # Skip certain interactions if conditions not met
                    if interaction_type == 'file_download' and not assignment.attachments.exists():
                        continue
                    if interaction_type == 'rubric_viewed' and not assignment.rubric:
                        continue
                    
                    interaction_data = self._get_interaction_data(interaction_type, assignment)
                    
                    interactions.append({
                        'interaction_type': interaction_type,
                        'created_at': interaction_time,
                        'interaction_data': interaction_data
                    })
                    break
        
        return interactions

    def _get_interaction_data(self, interaction_type, assignment):
        """Get appropriate interaction data based on type"""
        data = {}
        
        if interaction_type == 'view':
            data.update({
                'page_url': f'/assignments/{assignment.id}/',
                'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
        elif interaction_type == 'file_download':
            if assignment.attachments.exists():
                attachment = assignment.attachments.first()
                data.update({
                    'file_name': attachment.file_name,
                    'file_type': 'assignment_attachment'
                })
        elif interaction_type == 'draft_save':
            data.update({
                'draft_content_length': random.randint(50, 500),
                'auto_save': random.choice([True, False])
            })
        elif interaction_type == 'rubric_viewed':
            if assignment.rubric:
                data.update({
                    'rubric_title': assignment.rubric.title,
                    'criteria_count': assignment.rubric.criteria.count()
                })
        
        return data

    def _create_session_logs(self, assignment, user, submission_date, sessions_data):
        """Create AssignmentSessionLog records"""
        created_count = 0
        
        for session_data in sessions_data:
            session_key = f"session_{user.id}_{int(session_data['start_time'].timestamp())}"
            
            session_log = AssignmentSessionLog.objects.create(
                assignment=assignment,
                user=user,
                session_key=session_key,
                start_time=session_data['start_time'],
                end_time=session_data['end_time'],
                total_duration_seconds=session_data['duration_seconds'],
                page_views=session_data['page_views'],
                interactions_count=session_data['interactions_count'],
                ip_address='192.168.1.100',  # Simulated IP
                user_agent='Mozilla/5.0 (simulated)',
                is_active=False  # Historical sessions are not active
            )
            created_count += 1
        
        return created_count

    def _create_interaction_logs(self, assignment, user, submission, interactions_data):
        """Create AssignmentInteractionLog records"""
        created_count = 0
        
        for interaction_data in interactions_data:
            # Skip if interaction already exists (avoid duplicates)
            existing = AssignmentInteractionLog.objects.filter(
                assignment=assignment,
                user=user,
                interaction_type=interaction_data['interaction_type'],
                created_at=interaction_data['created_at']
            ).exists()
            
            if not existing:
                log = AssignmentInteractionLog.objects.create(
                    assignment=assignment,
                    user=user,
                    interaction_type=interaction_data['interaction_type'],
                    submission=interaction_data.get('submission'),
                    interaction_data=interaction_data.get('interaction_data', {}),
                    ip_address='192.168.1.100',  # Simulated IP
                    user_agent='Mozilla/5.0 (simulated)',
                    session_key=f"session_{user.id}_{int(interaction_data['created_at'].timestamp())}",
                    created_at=interaction_data['created_at']
                )
                created_count += 1
        
        return created_count 