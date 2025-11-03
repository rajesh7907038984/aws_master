"""
Management command to verify and diagnose time tracking issues
"""
from django.core.management.base import BaseCommand
from django.db.models import Sum, Count
from users.models import CustomUser
from courses.models import TopicProgress, CourseEnrollment, Topic, CourseTopic
from scorm.models import ScormEnrollment, ScormAttempt


class Command(BaseCommand):
    help = 'Verify time tracking data and identify issues'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user-email',
            type=str,
            help='Email of the user to check',
        )
        parser.add_argument(
            '--user-id',
            type=int,
            help='ID of the user to check',
        )

    def handle(self, *args, **options):
        user_email = options.get('user_email')
        user_id = options.get('user_id')
        
        if user_email:
            try:
                user = CustomUser.objects.get(email=user_email)
            except CustomUser.DoesNotExist:
                self.stdout.write(self.style.ERROR(f'❌ User with email {user_email} not found'))
                return
        elif user_id:
            try:
                user = CustomUser.objects.get(id=user_id)
            except CustomUser.DoesNotExist:
                self.stdout.write(self.style.ERROR(f'❌ User with ID {user_id} not found'))
                return
        else:
            self.stdout.write(self.style.ERROR('❌ Please provide --user-email or --user-id'))
            return
        
        self.stdout.write("=" * 80)
        self.stdout.write(self.style.SUCCESS(f"📊 TIME TRACKING VERIFICATION REPORT"))
        self.stdout.write("=" * 80)
        self.stdout.write(f"\n👤 User: {user.get_full_name()} ({user.email})")
        self.stdout.write(f"   Role: {user.role}")
        self.stdout.write(f"   ID: {user.id}\n")
        
        # Get enrollments
        enrollments = CourseEnrollment.objects.filter(user=user).select_related('course')
        
        if not enrollments.exists():
            self.stdout.write(self.style.WARNING("⚠️  No course enrollments found"))
            return
        
        self.stdout.write(f"📚 Course Enrollments: {enrollments.count()}\n")
        
        for enrollment in enrollments:
            self.stdout.write("=" * 80)
            self.stdout.write(f"📖 {enrollment.course.title}")
            self.stdout.write(f"   Progress: {enrollment.progress_percentage}% | Completed: {enrollment.completed}")
            
            # Check TopicProgress with course field
            tp_with_course = TopicProgress.objects.filter(
                user=user,
                course=enrollment.course
            )
            
            # Check TopicProgress without course field (legacy)
            tp_without_course = TopicProgress.objects.filter(
                user=user,
                topic__coursetopic__course=enrollment.course,
                course__isnull=True
            )
            
            self.stdout.write(f"\n   📊 TopicProgress Records:")
            self.stdout.write(f"      With course field: {tp_with_course.count()}")
            self.stdout.write(f"      Legacy (no course): {tp_without_course.count()}")
            
            # Calculate time from both
            time_with_course = tp_with_course.aggregate(
                total=Sum('total_time_spent')
            )['total'] or 0
            
            time_without_course = tp_without_course.aggregate(
                total=Sum('total_time_spent')
            )['total'] or 0
            
            total_time = time_with_course + time_without_course
            
            self.stdout.write(f"\n   ⏱️  Time Tracking:")
            self.stdout.write(f"      From records with course: {time_with_course}s ({time_with_course // 60}m)")
            self.stdout.write(f"      From legacy records: {time_without_course}s ({time_without_course // 60}m)")
            self.stdout.write(f"      TOTAL: {total_time}s ({total_time // 60}m, {total_time // 3600}h)")
            
            # Format as displayed in report
            hours = total_time // 3600
            minutes = (total_time % 3600) // 60
            seconds = total_time % 60
            self.stdout.write(f"      Formatted: {hours}h {minutes}m {seconds}s")
            
            # Check SCORM activities
            course_topics = CourseTopic.objects.filter(course=enrollment.course).select_related('topic')
            scorm_topics = [ct.topic for ct in course_topics if ct.topic.content_type == 'Scorm']
            
            if scorm_topics:
                self.stdout.write(f"\n   📦 SCORM Activities: {len(scorm_topics)}")
                
                for topic in scorm_topics:
                    scorm_enrollments = ScormEnrollment.objects.filter(user=user, topic=topic)
                    
                    if scorm_enrollments.exists():
                        for se in scorm_enrollments:
                            self.stdout.write(f"\n      Topic: {topic.title}")
                            self.stdout.write(f"         SCORM time: {se.total_time_seconds}s ({se.total_time_seconds // 60}m)")
                            self.stdout.write(f"         Attempts: {se.total_attempts}")
                            self.stdout.write(f"         Status: {se.enrollment_status}")
                            
                            # Check if synced to TopicProgress
                            tp = TopicProgress.objects.filter(user=user, topic=topic, course=enrollment.course).first()
                            if tp:
                                self.stdout.write(f"         TopicProgress time: {tp.total_time_spent}s")
                                if tp.total_time_spent < se.total_time_seconds:
                                    self.stdout.write(
                                        self.style.WARNING(
                                            f"         ⚠️  MISMATCH: TopicProgress has less time than SCORM!"
                                        )
                                    )
                            else:
                                self.stdout.write(
                                    self.style.WARNING(
                                        f"         ⚠️  No TopicProgress record found!"
                                    )
                                )
                    else:
                        self.stdout.write(f"\n      Topic: {topic.title}")
                        self.stdout.write(self.style.WARNING(f"         ⚠️  No SCORM enrollment found"))
            
            # Check video/audio activities
            video_topics = [ct.topic for ct in course_topics if ct.topic.content_type in ['Video', 'EmbedVideo', 'Audio']]
            
            if video_topics:
                self.stdout.write(f"\n   🎥 Video/Audio Activities: {len(video_topics)}")
                
                for topic in video_topics:
                    tp = TopicProgress.objects.filter(user=user, topic=topic, course=enrollment.course).first()
                    
                    if tp:
                        self.stdout.write(f"\n      Topic: {topic.title} ({topic.content_type})")
                        self.stdout.write(f"         Time: {tp.total_time_spent}s ({tp.total_time_spent // 60}m)")
                        self.stdout.write(f"         Progress: {tp.video_progress if hasattr(tp, 'video_progress') else 'N/A'}%")
                        self.stdout.write(f"         Completed: {tp.completed}")
                        
                        # Check progress_data for video tracking details
                        if tp.progress_data and isinstance(tp.progress_data, dict):
                            total_viewing_time = tp.progress_data.get('total_viewing_time', 0)
                            if total_viewing_time > 0:
                                self.stdout.write(f"         Total viewing time (from progress_data): {int(total_viewing_time)}s")
                                if tp.total_time_spent == 0 and total_viewing_time > 0:
                                    self.stdout.write(
                                        self.style.WARNING(
                                            f"         ⚠️  ISSUE: progress_data has time but total_time_spent is 0!"
                                        )
                                    )
                    else:
                        self.stdout.write(f"\n      Topic: {topic.title} ({topic.content_type})")
                        self.stdout.write(self.style.WARNING(f"         ⚠️  No TopicProgress record"))
            
            self.stdout.write("\n")
        
        # Final summary
        self.stdout.write("=" * 80)
        self.stdout.write(self.style.SUCCESS("✅ VERIFICATION COMPLETE"))
        
        # Check if there are any issues
        all_tp = TopicProgress.objects.filter(user=user)
        total_time_all = all_tp.aggregate(total=Sum('total_time_spent'))['total'] or 0
        
        self.stdout.write(f"\n📈 Overall Statistics:")
        self.stdout.write(f"   Total TopicProgress records: {all_tp.count()}")
        self.stdout.write(f"   Total time across all activities: {total_time_all}s ({total_time_all // 60}m, {total_time_all // 3600}h)")
        
        # Check for orphaned records
        orphaned = all_tp.filter(course__isnull=True)
        if orphaned.exists():
            self.stdout.write(
                self.style.WARNING(
                    f"\n   ⚠️  Found {orphaned.count()} orphaned TopicProgress records (no course field)"
                )
            )
            self.stdout.write("   Run: python manage.py migrate_topic_progress_course_field")
        
        self.stdout.write("=" * 80)

