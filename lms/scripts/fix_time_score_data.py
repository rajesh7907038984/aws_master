#!/usr/bin/env python
"""
Data Repair Script for Time and Score Accuracy Issues
Fixes inconsistencies in TopicProgress time and score data
"""

import os
import sys
import django
from decimal import Decimal, InvalidOperation

# Setup Django environment
sys.path.append('/home/ec2-user/lms')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings')
django.setup()

from courses.models import TopicProgress, CourseEnrollment
from django.db import transaction
from django.db.models import F
from django.contrib.auth import get_user_model
from core.utils.scoring import ScoreCalculationService
from core.utils.timezone_utils import TimezoneUtils
import logging

User = get_user_model()
logger = logging.getLogger(__name__)

class DataRepairService:
    """Service for repairing time and score data inconsistencies"""
    
    def __init__(self):
        self.fixed_records = 0
        self.errors = []
    
    def fix_time_data(self):
        """Fix time data inconsistencies"""
        print("🔧 Fixing time data inconsistencies...")
        
        # Fix negative time values
        negative_time_records = TopicProgress.objects.filter(total_time_spent__lt=0)
        if negative_time_records.exists():
            print("  Found {{negative_time_records.count()}} records with negative time")
            negative_time_records.update(total_time_spent=0)
            self.fixed_records += negative_time_records.count()
            print("  ✅ Fixed {{negative_time_records.count()}} negative time records")
        
        # Fix null time values for accessed records
        null_time_accessed = TopicProgress.objects.filter(
            total_time_spent=0,
            last_accessed__isnull=False
        ).exclude(last_accessed=F('first_accessed'))
        
        if null_time_accessed.exists():
            print("  Found {{null_time_accessed.count()}} accessed records with zero time")
            # Set minimum time for accessed records (1 minute)
            null_time_accessed.update(total_time_spent=60)
            self.fixed_records += null_time_accessed.count()
            print("  ✅ Set minimum time for {{null_time_accessed.count()}} accessed records")
    
    def fix_score_data(self):
        """Fix score data inconsistencies"""
        print("🔧 Fixing score data inconsistencies...")
        
        # Fix invalid scores
        invalid_scores = TopicProgress.objects.exclude(last_score__isnull=True).exclude(
            last_score__gte=0
        ).exclude(last_score__lte=100)
        
        if invalid_scores.exists():
            print("  Found {{invalid_scores.count()}} records with invalid scores")
            for record in invalid_scores:
                try:
                    normalized_score = ScoreCalculationService.normalize_score(record.last_score)
                    if normalized_score is not None:
                        record.last_score = normalized_score
                        record.save()
                        self.fixed_records += 1
                except Exception as e:
                    self.errors.append("Error fixing score for record {{record.id}}: {{e}}")
            print("  ✅ Fixed {{invalid_scores.count()}} invalid score records")
        
        # Fix null scores for completed records
        completed_null_scores = TopicProgress.objects.filter(
            completed=True,
            last_score__isnull=True
        )
        
        if completed_null_scores.exists():
            print("  Found {{completed_null_scores.count()}} completed records with null scores")
            # Set default score for completed records
            completed_null_scores.update(last_score=Decimal('0.00'))
            self.fixed_records += completed_null_scores.count()
            print("  ✅ Set default scores for {{completed_null_scores.count()}} completed records")
    
    def recalculate_course_scores(self):
        """Recalculate course scores based on topic progress"""
        print("🔧 Recalculating course scores...")
        
        # Get all users with course enrollments
        users_with_courses = User.objects.filter(
            courseenrollment__isnull=False
        ).distinct()
        
        for user in users_with_courses:
            enrollments = CourseEnrollment.objects.filter(user=user)
            
            for enrollment in enrollments:
                # Get topic progress for this course
                topic_progress = TopicProgress.objects.filter(
                    user=user,
                    topic__courses=enrollment.course,
                    completed=True,
                    last_score__isnull=False
                )
                
                if topic_progress.exists():
                    # Calculate average score
                    scores = []
                    for progress in topic_progress:
                        normalized_score = ScoreCalculationService.normalize_score(progress.last_score)
                        if normalized_score is not None:
                            scores.append(float(normalized_score))
                    
                    if scores:
                        avg_score = sum(scores) / len(scores)
                        enrollment.score = Decimal(str(round(avg_score, 2)))
                        enrollment.save()
                        self.fixed_records += 1
        
        print("  ✅ Recalculated scores for {{users_with_courses.count()}} users")
    
    def add_missing_progress_records(self):
        """Add missing TopicProgress records for enrolled courses"""
        print("🔧 Adding missing progress records...")
        
        # Get all course enrollments
        enrollments = CourseEnrollment.objects.select_related('user', 'course').all()
        
        missing_records = []
        for enrollment in enrollments:
            # Get topics for this course
            course_topics = enrollment.course.topics.all()
            
            for topic in course_topics:
                # Check if progress record exists
                if not TopicProgress.objects.filter(
                    user=enrollment.user,
                    topic=topic
                ).exists():
                    missing_records.append(
                        TopicProgress(
                            user=enrollment.user,
                            topic=topic,
                            completed=False,
                            total_time_spent=0,
                            attempts=0
                        )
                    )
        
        if missing_records:
            print("  Found {{len(missing_records)}} missing progress records")
            with transaction.atomic():
                TopicProgress.objects.bulk_create(missing_records, ignore_conflicts=True)
                self.fixed_records += len(missing_records)
                print("  ✅ Created {{len(missing_records)}} missing progress records")
    
    def validate_data_consistency(self):
        """Validate data consistency after fixes"""
        print("🔍 Validating data consistency...")
        
        # Check for remaining issues
        negative_time = TopicProgress.objects.filter(total_time_spent__lt=0).count()
        null_scores_completed = TopicProgress.objects.filter(
            completed=True, 
            last_score__isnull=True
        ).count()
        invalid_scores = TopicProgress.objects.exclude(
            last_score__isnull=True
        ).exclude(last_score__gte=0).exclude(last_score__lte=100).count()
        
        print("  Remaining negative time records: {{negative_time}}")
        print("  Remaining completed records with null scores: {{null_scores_completed}}")
        print("  Remaining invalid scores: {{invalid_scores}}")
        
        if negative_time == 0 and null_scores_completed == 0 and invalid_scores == 0:
            print("  ✅ All data consistency issues resolved!")
            return True
        else:
            print("  ⚠️ Some data consistency issues remain")
            return False
    
    def run_full_repair(self):
        """Run complete data repair process"""
        print("🚀 Starting comprehensive data repair...")
        print("=" * 50)
        
        try:
            with transaction.atomic():
                self.fix_time_data()
                self.fix_score_data()
                self.add_missing_progress_records()
                self.recalculate_course_scores()
                
                # Validate after fixes
                is_consistent = self.validate_data_consistency()
                
                print("=" * 50)
                print("📊 Repair Summary:")
                print("  Records fixed: {{self.fixed_records}}")
                print("  Errors encountered: {{len(self.errors)}}")
                
                if self.errors:
                    print("  Errors:")
                    for error in self.errors:
                        print("    - {{error}}")
                
                if is_consistent:
                    print("  ✅ Data repair completed successfully!")
                else:
                    print("  ⚠️ Some issues may require manual intervention")
                
                return True
                
        except Exception as e:
            print("❌ Data repair failed: {{e}}")
            self.errors.append(str(e))
            return False

def main():
    """Main function to run data repair"""
    repair_service = DataRepairService()
    success = repair_service.run_full_repair()
    
    if success:
        print("\n🎉 Data repair completed successfully!")
        sys.exit(0)
    else:
        print("\n💥 Data repair failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()
