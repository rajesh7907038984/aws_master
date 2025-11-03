from django.db import models
from django.conf import settings

class Discussion(models.Model):
    VISIBILITY_CHOICES = (
        ('public', 'Public'),
        ('private', 'Private'),
    )
    
    CONTENT_TYPE_CHOICES = (
        ('text', 'Text'),
        ('audio', 'Audio'),
        ('video', 'Video'),
        ('web_content', 'Web Content'),
        ('document', 'Document'),
    )
    
    ASSESSMENT_TYPE_CHOICES = (
        ('quiz', 'Quiz'),
        ('assignment', 'Assignment'),
        ('ilt_conference', 'ILT/Conference'),
        ('discussion', 'Discussion'),
    )
    
    STATUS_CHOICES = (
        ('published', 'Published'),
        ('draft', 'Draft'),
    )
    
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    content = models.TextField()
    instructions = models.TextField(blank=True, help_text="Instructions for participants joining the discussion")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='discussions')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    visibility = models.CharField(max_length=10, choices=VISIBILITY_CHOICES, default='public')
    likes = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='liked_discussions', blank=True)
    
    # Rubric relationship
    rubric = models.ForeignKey(
        'lms_rubrics.Rubric',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='discussions',
        help_text="Optional rubric to evaluate this discussion"
    )
    
    # New fields
    content_type = models.CharField(max_length=20, choices=CONTENT_TYPE_CHOICES, default='text')
    assessment_type = models.CharField(max_length=20, choices=ASSESSMENT_TYPE_CHOICES, default='discussion')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='published')
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    initial_post = models.TextField(blank=True)
    
    # Course relationship
    course = models.ForeignKey(
        'courses.Course',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='discussions',
        help_text="The course this discussion belongs to (if any)"
    )
    
    def get_course_info(self):
        """
        Get course information for this discussion.
        Returns course title and whether it's from direct relationship or topic-based.
        """
        # Check direct course relationship first
        if self.course:
            return {
                'title': self.course.title,
                'course': self.course,
                'source': 'direct'
            }
        
        # Check topic-based courses (discussion -> topic -> course)
        try:
            from courses.models import CourseTopic
        except ImportError:
            CourseTopic = None
        
        topic_courses = CourseTopic.objects.filter(
            topic__discussion=self
        ).select_related('course').distinct()
        
        if topic_courses.exists():
            # Return the first course found through topics
            course_topic = topic_courses.first()
            return {
                'title': course_topic.course.title,
                'course': course_topic.course,
                'source': 'topic'
            }
        
        # No course found
        return None

    def is_available_for_user(self, user):
        """Check if discussion is available for the user to access"""
        if self.status != 'published':
            return False
        
        # For admin and superadmin roles, allow access based on role permissions
        if user.role in ['admin', 'superadmin', 'globaladmin'] or user.is_superuser:
            return True
            
        # For instructor role, check various access conditions
        if user.role == 'instructor':
            # 1. Check if instructor created the discussion
            if self.created_by == user:
                return True
                
            # 2. Check if instructor is assigned to the course
            if self.course and self.course.instructor == user:
                return True
                
            # 3. Check if instructor is enrolled in related courses as instructor
            from courses.models import CourseEnrollment
            if self.course and CourseEnrollment.objects.filter(user=user, user__role='instructor', course=self.course).exists():
                return True
                
            # 4. Check topic-based course enrollments
            from courses.models import Course
            if Course.objects.filter(
                coursetopic__topic__discussion=self,
                courseenrollment__user=user
            ).exists():
                return True
            
            # 5. Branch-based access for instructors from same branch (educational reference)  
            if user.branch and self.status == 'published':
                # Check if discussion creator is from same branch
                if self.created_by and self.created_by.branch == user.branch:
                    return True
                    
                # Check if discussion's course is from same branch
                if self.course and self.course.branch == user.branch:
                    return True
            
            # If no access granted, return False
            return False
        
        # For learner role, apply strict filtering
        if user.role == 'learner':
            # Check if this discussion is linked to any published topics
            # Learners can only access discussions that are linked to active/published topics
            if not self.topics.filter(status='active').exists():
                return False  # No published topics linked to this discussion
            
            # Check if user is enrolled in any courses linked to this discussion
            # Discussion can be linked to courses through direct or topic relationships
            from courses.models import Course, CourseEnrollment
            
            # Get all courses that the user is enrolled in as a learner
            enrolled_course_ids = CourseEnrollment.objects.filter(user=user, user__role='learner').values_list('course_id', flat=True)
            
            # Check if discussion is linked to any enrolled courses through any relationship
            linked_to_enrolled_course = (
                # Direct course relationship
                (self.course and self.course.id in enrolled_course_ids) or
                # Topic-based course relationship
                Course.objects.filter(
                    id__in=enrolled_course_ids,
                    coursetopic__topic__discussion=self
                ).exists()
            )
            
            return linked_to_enrolled_course
        
        return False

    def __str__(self):
        if self.course:
            return f"{self.title} - {self.course.title}"
        return self.title
    
    class Meta:
        ordering = ['-updated_at']

class Comment(models.Model):
    discussion = models.ForeignKey(Discussion, on_delete=models.CASCADE, related_name='comments')
    content = models.TextField()
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='discussion_comments')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.CASCADE, related_name='replies')
    likes = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='liked_comments', blank=True)
    
    def __str__(self):
        return f"Comment by {self.created_by.username} on {self.discussion.title}"
    
    class Meta:
        ordering = ['created_at']

class DiscussionAttachment(models.Model):
    """Attachments for standalone discussions - Fixed Bug #5: Renamed from Attachment for clarity"""
    ATTACHMENT_TYPES = (
        ('document', 'Document'),
        ('image', 'Image'),
        ('video', 'Video'),
        ('audio', 'Audio'),
    )
    
    discussion = models.ForeignKey(Discussion, on_delete=models.CASCADE, related_name='attachments', null=True, blank=True)
    comment = models.ForeignKey(Comment, on_delete=models.CASCADE, related_name='attachments', null=True, blank=True)
    file = models.FileField(upload_to='discussions/attachments/%Y/%m/%d/')
    file_type = models.CharField(max_length=10, choices=ATTACHMENT_TYPES)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'discussions_attachment'  # Keep same table name for backward compatibility
        verbose_name = 'Discussion Attachment'
        verbose_name_plural = 'Discussion Attachments'
        constraints = [
            # Fixed Bug #4: Ensure attachment belongs to exactly one parent (discussion OR comment, not both)
            models.CheckConstraint(
                check=(
                    models.Q(discussion__isnull=False, comment__isnull=True) |
                    models.Q(discussion__isnull=True, comment__isnull=False)
                ),
                name='discussions_attachment_exclusive_parent'
            )
        ]
        indexes = [
            models.Index(fields=['discussion']),
            models.Index(fields=['comment']),
            models.Index(fields=['uploaded_by', '-uploaded_at']),
        ]
    
    def clean(self):
        """Validate that attachment belongs to either discussion or comment, not both"""
        from django.core.exceptions import ValidationError
        super().clean()
        
        if self.discussion and self.comment:
            raise ValidationError('Attachment cannot belong to both a discussion and a comment')
        
        if not self.discussion and not self.comment:
            raise ValidationError('Attachment must belong to either a discussion or a comment')
    
    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
    
    def __str__(self):
        if self.discussion:
            return f"Attachment for discussion: {self.discussion.title}"
        elif self.comment:
            return f"Attachment for comment"
        return "Orphaned attachment"
