# -*- coding: utf-8 -*-
"""
Fix Slide Completion Scores
Corrects SCORM scores for slide-based courses that were incorrectly scored as quiz scores
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from scorm.models import ScormAttempt
from courses.models import TopicProgress
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Fix SCORM scores for slide-completion based courses'

    def add_arguments(self, parser):
        parser.add_argument(
            '--username',
            type=str,
            help='Specific username to fix (optional)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be changed without making changes',
        )

    def handle(self, *args, **options):
        username = options.get('username')
        dry_run = options.get('dry_run', False)
        
        User = get_user_model()
        
        if username:
            users = User.objects.filter(username=username)
        else:
            users = User.objects.all()
        
        fixed_count = 0
        
        for user in users:
            self.stdout.write(f'\n=== Processing user: {user.username} ===')
            
            # Get all SCORM attempts for this user
            attempts = ScormAttempt.objects.filter(user=user).order_by('-last_accessed')
            
            for attempt in attempts:
                if not attempt.suspend_data:
                    continue
                
                # Check if this is slide-completion based SCORM
                visited_count = attempt.suspend_data.count('Visited')
                
                if visited_count >= 3:
                    # This is slide completion - should be 100% score
                    current_score = attempt.score_raw
                    
                    if current_score != 100.0:
                        self.stdout.write(
                            f'  Attempt {attempt.id}: Found {visited_count} visited slides'
                        )
                        self.stdout.write(
                            f'    Current score: {current_score} -> Should be: 100.0'
                        )
                        self.stdout.write(
                            f'    Package: {attempt.scorm_package.title}'
                        )
                        
                        if not dry_run:
                            # Fix the attempt
                            attempt.score_raw = 100.0
                            attempt.lesson_status = 'passed'
                            attempt.success_status = 'passed'
                            attempt.completion_status = 'completed'
                            attempt.save()
                            
                            # Fix TopicProgress
                            topic_progress = TopicProgress.objects.filter(
                                user=user,
                                topic=attempt.scorm_package.topic
                            ).first()
                            
                            if topic_progress:
                                topic_progress.last_score = 100.0
                                if not topic_progress.best_score or 100.0 > topic_progress.best_score:
                                    topic_progress.best_score = 100.0
                                topic_progress.completed = True
                                topic_progress.completion_method = 'scorm'
                                topic_progress.save()
                                
                                # Update progress_data
                                if not topic_progress.progress_data:
                                    topic_progress.progress_data = {}
                                topic_progress.progress_data['score_raw'] = 100.0
                                topic_progress.progress_data['slide_completion_fixed'] = True
                                topic_progress.progress_data['visited_slides'] = visited_count
                                topic_progress.save()
                            
                            self.stdout.write(f'    ✅ Fixed attempt {attempt.id}')
                            fixed_count += 1
                        else:
                            self.stdout.write(f'    🔍 Would fix attempt {attempt.id} (dry run)')
                            fixed_count += 1
        
        if dry_run:
            self.stdout.write(f'\n🔍 DRY RUN: Would fix {fixed_count} attempts')
        else:
            self.stdout.write(f'\n✅ Fixed {fixed_count} slide-completion SCORM attempts')
