from django.db import models
from django.conf import settings
from django.core.validators import FileExtensionValidator
from courses.models import Course


class IndividualLearningPlan(models.Model):
    """Main ILP model linking to a user"""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='individual_learning_plan'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_ilps'
    )
    
    def __str__(self):
        return f"ILP for {self.user.get_full_name() or self.user.username}"


class SENDAccommodation(models.Model):
    """SEND (Special Educational Needs and Disabilities) Accommodations"""
    ACCOMMODATION_TYPES = [
        ('visual', 'Visual Impairments'),
        ('hearing', 'Hearing Impairments'),
        ('mobility', 'Mobility/Physical'),
        ('cognitive', 'Cognitive/Learning'),
        ('mental_health', 'Mental Health'),
        ('other', 'Other'),
    ]
    
    ilp = models.ForeignKey(IndividualLearningPlan, on_delete=models.CASCADE, related_name='send_accommodations')
    accommodation_type = models.CharField(max_length=20, choices=ACCOMMODATION_TYPES)
    accommodation_type_other = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Other accommodation type if 'Other' is selected"
    )
    description = models.TextField(help_text="Description of the accommodation needed")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_accommodations'
    )
    
    def __str__(self):
        return f"{self.get_accommodation_type_display()} - {self.ilp.user.username}"


class StrengthWeakness(models.Model):
    """User strengths and weaknesses identified using AI"""
    TYPE_CHOICES = [
        ('strength', 'Strength'),
        ('weakness', 'Weakness'),
    ]
    
    SOURCE_CHOICES = [
        ('ai_analysis', 'AI Analysis'),
        ('teacher_input', 'Teacher Input'),
        ('self_assessment', 'Self Assessment'),
    ]
    
    ilp = models.ForeignKey(IndividualLearningPlan, on_delete=models.CASCADE, related_name='strengths_weaknesses')
    type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    description = models.TextField()
    source = models.CharField(max_length=15, choices=SOURCE_CHOICES, default='teacher_input')
    confidence_score = models.DecimalField(
        max_digits=3, 
        decimal_places=2, 
        null=True, 
        blank=True,
        help_text="AI confidence score (0.00-1.00)"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_strengths_weaknesses'
    )
    
    def __str__(self):
        return f"{self.get_type_display()}: {self.description[:50]}..."


class LearningPreference(models.Model):
    """Learning preferences and styles"""
    PREFERENCE_TYPES = [
        ('visual', 'Visual Learning'),
        ('auditory', 'Auditory Learning'),
        ('kinesthetic', 'Kinesthetic Learning'),
        ('reading_writing', 'Reading/Writing'),
        ('group', 'Group Learning'),
        ('individual', 'Individual Learning'),
        ('practical', 'Practical/Hands-on'),
        ('theoretical', 'Theoretical'),
    ]
    
    ilp = models.ForeignKey(IndividualLearningPlan, on_delete=models.CASCADE, related_name='learning_preferences')
    preference_type = models.CharField(max_length=20, choices=PREFERENCE_TYPES)
    preference_level = models.IntegerField(
        help_text="Preference level 1-5 (5 being highest preference)",
        choices=[(i, i) for i in range(1, 6)]
    )
    notes = models.TextField(blank=True, null=True)
    identified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='identified_preferences'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.get_preference_type_display()} (Level {self.preference_level})"


class StatementOfPurpose(models.Model):
    """Statement of Purpose - can be file upload or form responses"""
    ilp = models.OneToOneField(
        IndividualLearningPlan,
        on_delete=models.CASCADE,
        related_name='statement_of_purpose'
    )
    
    # File upload option
    sop_file = models.FileField(
        upload_to='ilp/sop_files/',
        validators=[FileExtensionValidator(allowed_extensions=['pdf', 'doc', 'docx'])],
        null=True,
        blank=True,
        help_text="Upload Statement of Purpose (PDF/Word, <5MB)"
    )
    
    # Form responses option
    reason_for_course = models.TextField(
        blank=True,
        null=True,
        help_text="Why are you pursuing this course?"
    )
    career_objectives = models.TextField(
        blank=True,
        null=True,
        help_text="What are your career objectives?"
    )
    relevant_experience = models.TextField(
        blank=True,
        null=True,
        help_text="Describe any relevant past work or experience"
    )
    additional_info = models.TextField(
        blank=True,
        null=True,
        help_text="Any additional information you'd like to share"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='updated_sops'
    )
    
    def has_content(self):
        """Check if SOP has any content"""
        return bool(
            self.sop_file or 
            self.reason_for_course or 
            self.career_objectives or 
            self.relevant_experience or 
            self.additional_info
        )
    
    def __str__(self):
        return f"SOP for {self.ilp.user.username}"


class CareerGoal(models.Model):
    """Career goals and aspirations"""
    ilp = models.OneToOneField(
        IndividualLearningPlan,
        on_delete=models.CASCADE,
        related_name='career_goal'
    )
    short_term_goal = models.TextField(
        help_text="Short-term career goal (1-2 years)"
    )
    long_term_goal = models.TextField(
        help_text="Long-term career goal (5+ years)"
    )
    target_industry = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Target industry or sector"
    )
    required_skills = models.TextField(
        blank=True,
        null=True,
        help_text="Skills needed to achieve these goals"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='updated_career_goals'
    )
    
    def __str__(self):
        return f"Career Goal for {self.ilp.user.username}"


class LearningGoal(models.Model):
    """Learning goals for courses - both short-term and long-term"""
    GOAL_TYPE_CHOICES = [
        ('short_term', 'Short Term Goal'),
        ('long_term', 'Long Term Goal'),
        ('custom', 'Custom Target'),
    ]
    
    STATUS_CHOICES = [
        ('not_started', 'Not Started'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('on_hold', 'On Hold'),
    ]
    
    ilp = models.ForeignKey(IndividualLearningPlan, on_delete=models.CASCADE, related_name='learning_goals')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='learning_goals', null=True, blank=True)
    goal_type = models.CharField(max_length=15, choices=GOAL_TYPE_CHOICES)
    custom_target_name = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Custom name for the target when goal_type is 'custom'"
    )
    title = models.CharField(max_length=200)
    description = models.TextField()
    target_completion_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='not_started')
    
    # AI and Teacher inputs
    teacher_input = models.TextField(
        blank=True,
        null=True,
        help_text="Teacher/Instructor input on this goal"
    )
    ai_input = models.TextField(
        blank=True,
        null=True,
        help_text="AI-generated suggestions for this goal"
    )
    
    # Learner and Instructor interaction
    learner_comment = models.TextField(
        blank=True,
        null=True,
        help_text="Learner's comments on this goal"
    )
    instructor_reply = models.TextField(
        blank=True,
        null=True,
        help_text="Instructor's reply to learner comments"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_learning_goals'
    )
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.get_goal_type_display()}: {self.title}"


class LearningProgress(models.Model):
    """Progress tracking and comments"""
    learning_goal = models.ForeignKey(LearningGoal, on_delete=models.CASCADE, related_name='progress_entries')
    progress_percentage = models.IntegerField(
        default=0,
        help_text="Progress percentage (0-100)"
    )
    learner_comment = models.TextField(
        blank=True,
        null=True,
        help_text="Learner's comment on progress"
    )
    teacher_comment = models.TextField(
        blank=True,
        null=True,
        help_text="Teacher/Instructor comment"
    )
    evidence_file = models.FileField(
        upload_to='ilp/progress_evidence/',
        validators=[FileExtensionValidator(allowed_extensions=['pdf', 'doc', 'docx', 'jpg', 'jpeg', 'png'])],
        null=True,
        blank=True,
        help_text="Upload evidence of progress"
    )
    review_requested = models.BooleanField(
        default=False,
        help_text="Whether learner has requested a review"
    )
    review_completed = models.BooleanField(
        default=False,
        help_text="Whether teacher has completed the review"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_progress_entries'
    )
    
    def __str__(self):
        return f"Progress for {self.learning_goal.title} - {self.progress_percentage}%"


class EducatorNote(models.Model):
    """Notes and observations from educators"""
    ilp = models.ForeignKey(IndividualLearningPlan, on_delete=models.CASCADE, related_name='educator_notes')
    note = models.TextField()
    is_private = models.BooleanField(
        default=False,
        help_text="Private notes only visible to staff"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_educator_notes'
    )
    
    def __str__(self):
        return f"Note for {self.ilp.user.username} by {self.created_by.username if self.created_by else 'Unknown'}"


class LearningNeeds(models.Model):
    """Learning needs assessment with employability skills tracking"""
    ilp = models.OneToOneField(
        IndividualLearningPlan,
        on_delete=models.CASCADE,
        related_name='learning_needs'
    )
    
    # Employability Skills Checkboxes
    job_search_skills = models.BooleanField(default=False)
    effective_cvs = models.BooleanField(default=False)
    improving_it_skills = models.BooleanField(default=False)
    interview_skills = models.BooleanField(default=False)
    team_skills = models.BooleanField(default=False)
    jcp_universal_jobmatch = models.BooleanField(default=False)
    job_application_skills = models.BooleanField(default=False)
    communication_skills = models.BooleanField(default=False)
    other_skills = models.BooleanField(default=False)
    other_skills_details = models.TextField(blank=True, null=True)
    
    # Additional Learning Assessment
    prior_learning_experience = models.TextField(blank=True, null=True)
    learning_challenges = models.TextField(blank=True, null=True)
    support_needed = models.TextField(blank=True, null=True)
    preferred_learning_environment = models.TextField(blank=True, null=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_learning_needs'
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='updated_learning_needs'
    )
    
    def __str__(self):
        return f"Learning Needs for {self.ilp.user.username}"
    
    @property
    def selected_skills_count(self):
        """Count of selected employability skills"""
        skills = [
            self.job_search_skills, self.effective_cvs, self.improving_it_skills,
            self.interview_skills, self.team_skills, self.jcp_universal_jobmatch,
            self.job_application_skills, self.communication_skills, self.other_skills
        ]
        return sum(skills)


class InductionChecklist(models.Model):
    """Comprehensive induction checklist for learners with Yes/No questionnaire"""
    ilp = models.OneToOneField(
        IndividualLearningPlan,
        on_delete=models.CASCADE,
        related_name='induction_checklist'
    )
    
    # Programme Content, Delivery and Assessment Arrangements
    programme_content_delivery_assessment = models.CharField(
        max_length=3,
        choices=[('yes', 'Yes'), ('no', 'No'), ('', 'Not Set')],
        default='',
        blank=True,
        help_text="Programme Content, Delivery and Assessment Arrangements discussed"
    )
    
    # Equality and Diversity
    equality_diversity = models.CharField(
        max_length=3,
        choices=[('yes', 'Yes'), ('no', 'No'), ('', 'Not Set')],
        default='',
        blank=True,
        help_text="Equality and Diversity discussed"
    )
    
    # Disciplinary and Grievance Procedures
    disciplinary_grievance_procedures = models.CharField(
        max_length=3,
        choices=[('yes', 'Yes'), ('no', 'No'), ('', 'Not Set')],
        default='',
        blank=True,
        help_text="Disciplinary and Grievance Procedures discussed"
    )
    
    # ESF and Co-financing
    esf_cofinancing = models.CharField(
        max_length=3,
        choices=[('yes', 'Yes'), ('no', 'No'), ('', 'Not Set')],
        default='',
        blank=True,
        help_text="ESF and Co-financing discussed"
    )
    
    # Information, advice and guidance
    information_advice_guidance = models.CharField(
        max_length=3,
        choices=[('yes', 'Yes'), ('no', 'No'), ('', 'Not Set')],
        default='',
        blank=True,
        help_text="Information, advice and guidance discussed"
    )
    
    # Health and Safety, the Safe Learner Principles
    health_safety_safe_learner = models.CharField(
        max_length=3,
        choices=[('yes', 'Yes'), ('no', 'No'), ('', 'Not Set')],
        default='',
        blank=True,
        help_text="Health and Safety, the Safe Learner Principles discussed"
    )
    
    # Safeguarding & Prevent Duty
    safeguarding_prevent_duty = models.CharField(
        max_length=3,
        choices=[('yes', 'Yes'), ('no', 'No'), ('', 'Not Set')],
        default='',
        blank=True,
        help_text="Safeguarding & Prevent Duty discussed"
    )
    
    # Terms and Conditions of Learning/Probation Period
    terms_conditions_learning = models.CharField(
        max_length=3,
        choices=[('yes', 'Yes'), ('no', 'No'), ('', 'Not Set')],
        default='',
        blank=True,
        help_text="Terms and Conditions of Learning/Probation Period discussed"
    )
    
    # Additional fields for tracking
    completed_by_learner = models.BooleanField(
        default=False,
        help_text="Whether the learner has completed reviewing all documents"
    )
    
    learner_completion_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Date when learner marked all items as complete"
    )
    
    assessor_notes = models.TextField(
        blank=True,
        null=True,
        help_text="Additional notes from the assessor about the induction process"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_induction_checklists'
    )
    
    def __str__(self):
        return f"Induction Checklist for {self.ilp.user.get_full_name() or self.ilp.user.username}"
    
    @property
    def completion_percentage(self):
        """Calculate completion percentage based on Yes responses"""
        fields = [
            self.programme_content_delivery_assessment,
            self.equality_diversity,
            self.disciplinary_grievance_procedures,
            self.esf_cofinancing,
            self.information_advice_guidance,
            self.health_safety_safe_learner,
            self.safeguarding_prevent_duty,
            self.terms_conditions_learning,
        ]
        total_items = len(fields)
        completed_items = sum(1 for field in fields if field == 'yes')
        return round((completed_items / total_items) * 100) if total_items > 0 else 0
    
    @property
    def all_items_completed(self):
        """Check if all items are marked as Yes"""
        return self.completion_percentage == 100


class InductionDocument(models.Model):
    """Documents uploaded by admin/teacher for induction checklist items"""
    DOCUMENT_CATEGORIES = [
        ('programme_content', 'Programme Content, Delivery and Assessment Arrangements'),
        ('equality_diversity', 'Equality and Diversity'),
        ('disciplinary_grievance', 'Disciplinary and Grievance Procedures'),
        ('esf_cofinancing', 'ESF and Co-financing'),
        ('information_advice', 'Information, advice and guidance'),
        ('health_safety', 'Health and Safety, the Safe Learner Principles'),
        ('safeguarding_prevent', 'Safeguarding & Prevent Duty'),
        ('terms_conditions', 'Terms and Conditions of Learning/Probation Period'),
        ('general', 'General Induction Information'),
    ]
    
    induction_checklist = models.ForeignKey(
        InductionChecklist,
        on_delete=models.CASCADE,
        related_name='documents'
    )
    
    title = models.CharField(
        max_length=200,
        help_text="Document title"
    )
    
    category = models.CharField(
        max_length=30,
        choices=DOCUMENT_CATEGORIES,
        help_text="Category of induction document"
    )
    
    document_file = models.FileField(
        upload_to='induction_documents/',
        validators=[FileExtensionValidator(allowed_extensions=['pdf', 'doc', 'docx', 'txt'])],
        help_text="Upload induction document (PDF, DOC, DOCX, TXT)"
    )
    
    description = models.TextField(
        blank=True,
        null=True,
        help_text="Optional description of the document"
    )
    
    is_mandatory = models.BooleanField(
        default=True,
        help_text="Whether this document is mandatory for the learner to read"
    )
    
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='uploaded_induction_documents'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.title} ({self.get_category_display()})"


class InductionDocumentReadReceipt(models.Model):
    """Track when learners read induction documents"""
    document = models.ForeignKey(
        InductionDocument,
        on_delete=models.CASCADE,
        related_name='read_receipts'
    )
    
    learner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='induction_read_receipts'
    )
    
    read_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['document', 'learner']
        ordering = ['-read_at']
    
    def __str__(self):
        return f"{self.learner.username} read {self.document.title} on {self.read_at}"


class HealthSafetyQuestionnaire(models.Model):
    """Health & Safety questionnaire responses for each learner"""
    ilp = models.OneToOneField(
        IndividualLearningPlan,
        on_delete=models.CASCADE,
        related_name='health_safety_questionnaire'
    )
    
    # Questions from the screenshot - all text fields for answers
    named_first_aider = models.TextField(
        blank=True,
        null=True,
        help_text="Who is the named first aider?"
    )
    
    named_first_aider_confirmed = models.CharField(
        max_length=3,
        choices=[('yes', 'Yes'), ('no', 'No'), ('', 'Not Set')],
        default='',
        blank=True,
        help_text="Confirmed understanding of first aider information"
    )
    
    fire_extinguishers_location = models.TextField(
        blank=True,
        null=True,
        help_text="Where are the fire extinguishers?"
    )
    
    fire_extinguishers_confirmed = models.CharField(
        max_length=3,
        choices=[('yes', 'Yes'), ('no', 'No'), ('', 'Not Set')],
        default='',
        blank=True,
        help_text="Confirmed awareness of fire extinguisher locations"
    )
    
    first_aid_box_location = models.TextField(
        blank=True,
        null=True,
        help_text="Where is the First Aid box kept?"
    )
    
    first_aid_box_confirmed = models.CharField(
        max_length=3,
        choices=[('yes', 'Yes'), ('no', 'No'), ('', 'Not Set')],
        default='',
        blank=True,
        help_text="Confirmed awareness of first aid box location"
    )
    
    fire_assembly_point = models.TextField(
        blank=True,
        null=True,
        help_text="Where is the Fire Assembly point?"
    )
    
    fire_assembly_confirmed = models.CharField(
        max_length=3,
        choices=[('yes', 'Yes'), ('no', 'No'), ('', 'Not Set')],
        default='',
        blank=True,
        help_text="Confirmed awareness of fire assembly point"
    )
    
    accident_book_location = models.TextField(
        blank=True,
        null=True,
        help_text="Where is the Accident Book kept?"
    )
    
    accident_book_confirmed = models.CharField(
        max_length=3,
        choices=[('yes', 'Yes'), ('no', 'No'), ('', 'Not Set')],
        default='',
        blank=True,
        help_text="Confirmed awareness of accident book location"
    )
    
    accident_reporting_person = models.TextField(
        blank=True,
        null=True,
        help_text="Who do you report accidents to?"
    )
    
    accident_reporting_confirmed = models.CharField(
        max_length=3,
        choices=[('yes', 'Yes'), ('no', 'No'), ('', 'Not Set')],
        default='',
        blank=True,
        help_text="Confirmed understanding of accident reporting procedure"
    )
    
    health_safety_policy_location = models.TextField(
        blank=True,
        null=True,
        help_text="Where is the Health & Safety Policy displayed?"
    )
    
    health_safety_policy_confirmed = models.CharField(
        max_length=3,
        choices=[('yes', 'Yes'), ('no', 'No'), ('', 'Not Set')],
        default='',
        blank=True,
        help_text="Confirmed awareness of health & safety policy location"
    )
    
    health_safety_issue_reporting = models.TextField(
        blank=True,
        null=True,
        help_text="Who do you report a health & safety issue to?"
    )
    
    health_safety_issue_confirmed = models.CharField(
        max_length=3,
        choices=[('yes', 'Yes'), ('no', 'No'), ('', 'Not Set')],
        default='',
        blank=True,
        help_text="Confirmed understanding of health & safety issue reporting"
    )
    
    nearest_fire_exits = models.TextField(
        blank=True,
        null=True,
        help_text="Where are your nearest fire exits?"
    )
    
    nearest_fire_exits_confirmed = models.CharField(
        max_length=3,
        choices=[('yes', 'Yes'), ('no', 'No'), ('', 'Not Set')],
        default='',
        blank=True,
        help_text="Confirmed awareness of nearest fire exits"
    )
    
    health_safety_manager = models.TextField(
        blank=True,
        null=True,
        help_text="Who is responsible for managing health & safety?"
    )
    
    health_safety_manager_confirmed = models.CharField(
        max_length=3,
        choices=[('yes', 'Yes'), ('no', 'No'), ('', 'Not Set')],
        default='',
        blank=True,
        help_text="Confirmed understanding of health & safety management"
    )
    
    common_accidents = models.TextField(
        blank=True,
        null=True,
        help_text="What are the most common accidents in this type of environment?"
    )
    
    common_accidents_confirmed = models.CharField(
        max_length=3,
        choices=[('yes', 'Yes'), ('no', 'No'), ('', 'Not Set')],
        default='',
        blank=True,
        help_text="Confirmed awareness of common accidents"
    )
    
    prohibited_substances = models.TextField(
        blank=True,
        null=True,
        help_text="What substances are prohibited at this centre?"
    )
    
    prohibited_substances_confirmed = models.CharField(
        max_length=3,
        choices=[('yes', 'Yes'), ('no', 'No'), ('', 'Not Set')],
        default='',
        blank=True,
        help_text="Confirmed understanding of prohibited substances"
    )
    
    # Completion tracking
    questionnaire_completed = models.BooleanField(
        default=False,
        help_text="Whether the learner has completed the questionnaire"
    )
    
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Date and time when questionnaire was completed"
    )
    
    # Acknowledgment
    learner_acknowledgment = models.BooleanField(
        default=False,
        help_text="Learner acknowledges understanding of health & safety arrangements"
    )
    
    acknowledgment_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Date when learner acknowledged understanding"
    )
    
    # Admin/Teacher notes
    assessor_notes = models.TextField(
        blank=True,
        null=True,
        help_text="Additional notes from the assessor"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_health_safety_questionnaires'
    )
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Health & Safety Questionnaire for {self.ilp.user.get_full_name() or self.ilp.user.username}"
    
    @property
    def completion_percentage(self):
        """Calculate completion percentage based on filled questions and confirmations"""
        total_items = 24  # 12 questions + 12 confirmations
        completed_items = 0
        
        question_fields = [
            'named_first_aider', 'fire_extinguishers_location', 'first_aid_box_location',
            'fire_assembly_point', 'accident_book_location', 'accident_reporting_person',
            'health_safety_policy_location', 'health_safety_issue_reporting', 'nearest_fire_exits',
            'health_safety_manager', 'common_accidents', 'prohibited_substances'
        ]
        
        confirmation_fields = [
            'named_first_aider_confirmed', 'fire_extinguishers_confirmed', 'first_aid_box_confirmed',
            'fire_assembly_confirmed', 'accident_book_confirmed', 'accident_reporting_confirmed',
            'health_safety_policy_confirmed', 'health_safety_issue_confirmed', 'nearest_fire_exits_confirmed',
            'health_safety_manager_confirmed', 'common_accidents_confirmed', 'prohibited_substances_confirmed'
        ]
        
        # Check question answers
        for field in question_fields:
            if getattr(self, field):
                completed_items += 1
        
        # Check confirmations (yes/no answers)
        for field in confirmation_fields:
            if getattr(self, field) in ['yes', 'no']:
                completed_items += 1
        
        return int((completed_items / total_items) * 100)
    
    @property
    def is_fully_completed(self):
        """Check if all questions are answered and acknowledged"""
        return self.completion_percentage == 100 and self.learner_acknowledgment


class HealthSafetyDocument(models.Model):
    """Documents related to Health & Safety"""
    health_safety_questionnaire = models.ForeignKey(
        HealthSafetyQuestionnaire,
        on_delete=models.CASCADE,
        related_name='documents'
    )
    
    title = models.CharField(
        max_length=200,
        help_text="Document title"
    )
    
    document_file = models.FileField(
        upload_to='health_safety_documents/',
        validators=[FileExtensionValidator(allowed_extensions=['pdf', 'doc', 'docx', 'txt'])],
        help_text="Upload health & safety document (PDF, DOC, DOCX, TXT)"
    )
    
    description = models.TextField(
        blank=True,
        null=True,
        help_text="Optional description of the document"
    )
    
    is_mandatory = models.BooleanField(
        default=True,
        help_text="Whether this document is mandatory for the learner to read"
    )
    
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='uploaded_health_safety_documents'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Health & Safety Document: {self.title}"


class HealthSafetyDocumentReadReceipt(models.Model):
    """Track when learners read health & safety documents"""
    document = models.ForeignKey(
        HealthSafetyDocument,
        on_delete=models.CASCADE,
        related_name='read_receipts'
    )
    
    learner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='health_safety_read_receipts'
    )
    
    read_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['document', 'learner']
        ordering = ['-read_at']
    
    def __str__(self):
        return f"{self.learner.username} read {self.document.title} on {self.read_at}"


class InternalCourseReview(models.Model):
    """Internal course review capturing comprehensive assessment data"""
    
    QUALIFICATION_CHOICES = [
        ('yes', 'Yes - Qualification Achieved'),
        ('no', 'No - Qualification Not Achieved'),
    ]
    
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('pending_review', 'Pending Review'),
        ('completed', 'Completed'),
        ('requires_update', 'Requires Update'),
    ]
    
    ilp = models.OneToOneField(
        IndividualLearningPlan,
        on_delete=models.CASCADE,
        related_name='course_review'
    )
    
    # Course Review Questions
    iag_session_review = models.TextField(
        verbose_name="Review of initial IAG session and learner's feelings",
        help_text="Review of initial IAG session and learner's feelings relating to the success of the identified actions",
        blank=True,
        null=True
    )
    
    action_completion_skills = models.TextField(
        verbose_name="Action completion and skill improvement",
        help_text="Did the learner complete the actions and have they improved their skills?",
        blank=True,
        null=True
    )
    
    careers_service_advice = models.TextField(
        verbose_name="National Careers Service advice",
        help_text="Advise learner of National Careers Service (Career Connect) and issue contact details (PA)",
        blank=True,
        null=True
    )
    
    progression_routes = models.TextField(
        verbose_name="Progression routes discussion",
        help_text="Discuss possible progression routes (provide details of external training required) (PA)",
        blank=True,
        null=True
    )
    
    career_objectives = models.TextField(
        verbose_name="Career objectives discussion",
        help_text="Discuss learner career objectives and how they may be achieved (PA)",
        blank=True,
        null=True
    )
    
    qualification_achieved = models.CharField(
        max_length=3,
        choices=QUALIFICATION_CHOICES,
        verbose_name="Qualification achievement",
        blank=True,
        null=True
    )
    
    qualification_details = models.TextField(
        verbose_name="Qualification achievement details",
        help_text="If qualification was not achieved, provide detailed reasons for non-achievement",
        blank=True,
        null=True
    )
    
    # Staff and Status Information
    review_completed_by = models.CharField(
        max_length=255,
        verbose_name="Completed by",
        blank=True,
        null=True
    )
    
    review_completion_date = models.DateField(
        verbose_name="Date completed",
        blank=True,
        null=True
    )
    
    review_status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='draft',
        verbose_name="Review status"
    )
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_course_reviews'
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='updated_course_reviews'
    )
    
    class Meta:
        verbose_name = "Internal Course Review"
        verbose_name_plural = "Internal Course Reviews"
    
    def __str__(self):
        return f"Course Review for {self.ilp.user.username}"
    
    @property
    def completion_percentage(self):
        """Calculate completion percentage based on filled fields"""
        total_fields = 6  # Main review questions
        completed_fields = 0
        
        if self.iag_session_review:
            completed_fields += 1
        if self.action_completion_skills:
            completed_fields += 1
        if self.careers_service_advice:
            completed_fields += 1
        if self.progression_routes:
            completed_fields += 1
        if self.career_objectives:
            completed_fields += 1
        if self.qualification_achieved:
            completed_fields += 1
            
        return round((completed_fields / total_fields) * 100)
    
    @property
    def is_complete(self):
        """Check if the review is considered complete"""
        return self.completion_percentage >= 80  # 80% threshold for completion


class InductionChecklistSection(models.Model):
    """Customizable sections for induction checklist"""
    induction_checklist = models.ForeignKey(
        InductionChecklist,
        on_delete=models.CASCADE,
        related_name='custom_sections'
    )
    
    title = models.CharField(
        max_length=200,
        help_text="Section title (e.g., 'Health & Safety', 'Programme Information')"
    )
    
    description = models.TextField(
        blank=True,
        null=True,
        help_text="Optional description of this section"
    )
    
    order = models.PositiveIntegerField(
        default=1,
        help_text="Display order of this section"
    )
    
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this section is active"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_induction_sections'
    )
    
    class Meta:
        ordering = ['order', 'title']
        unique_together = ['induction_checklist', 'title']
    
    def __str__(self):
        return f"{self.title} - {self.induction_checklist.ilp.user.get_full_name()}"
    
    @property
    def completion_percentage(self):
        """Calculate completion percentage for this section"""
        total_questions = self.questions.count()
        if total_questions == 0:
            return 100
        
        completed_questions = self.questions.filter(
            student_confirmed='yes',
            instructor_confirmed='yes'
        ).count()
        
        return round((completed_questions / total_questions) * 100)


class InductionChecklistQuestion(models.Model):
    """Individual questions within induction checklist sections"""
    section = models.ForeignKey(
        InductionChecklistSection,
        on_delete=models.CASCADE,
        related_name='questions'
    )
    
    question_text = models.TextField(
        help_text="The question to be answered"
    )
    
    answer_text = models.TextField(
        blank=True,
        null=True,
        help_text="Answer provided by student/instructor"
    )
    
    student_confirmed = models.CharField(
        max_length=3,
        choices=[('yes', 'Yes'), ('no', 'No'), ('', 'Not Set')],
        default='',
        blank=True,
        help_text="Student confirmation of understanding"
    )
    
    instructor_confirmed = models.CharField(
        max_length=3,
        choices=[('yes', 'Yes'), ('no', 'No'), ('', 'Not Set')],
        default='',
        blank=True,
        help_text="Instructor confirmation of completion"
    )
    
    student_comment = models.TextField(
        blank=True,
        null=True,
        help_text="Student's additional comments or questions"
    )
    
    instructor_reply = models.TextField(
        blank=True,
        null=True,
        help_text="Instructor's reply to student comments"
    )
    
    order = models.PositiveIntegerField(
        default=1,
        help_text="Display order within the section"
    )
    
    is_mandatory = models.BooleanField(
        default=True,
        help_text="Whether this question must be answered"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_induction_questions'
    )
    
    class Meta:
        ordering = ['order', 'id']
    
    def __str__(self):
        return f"Q{self.order}: {self.question_text[:50]}..."
    
    @property
    def is_completed(self):
        """Check if question is fully completed (only requires student confirmation now)"""
        return (
            bool(self.answer_text) and 
            self.student_confirmed == 'yes'
        )


class InductionChecklistDocument(models.Model):
    """Documents attached to induction checklist sections"""
    section = models.ForeignKey(
        InductionChecklistSection,
        on_delete=models.CASCADE,
        related_name='documents'
    )
    
    # Add relationship to specific question
    question = models.ForeignKey(
        InductionChecklistQuestion,
        on_delete=models.CASCADE,
        related_name='documents',
        null=True,
        blank=True,
        help_text="Specific question this document is attached to"
    )
    
    title = models.CharField(
        max_length=200,
        help_text="Document title"
    )
    
    document_file = models.FileField(
        upload_to='induction_section_documents/',
        validators=[FileExtensionValidator(allowed_extensions=['pdf', 'doc', 'docx', 'txt', 'jpg', 'jpeg', 'png'])],
        help_text="Upload document (PDF, DOC, DOCX, TXT, Images)"
    )
    
    description = models.TextField(
        blank=True,
        null=True,
        help_text="Optional description of the document"
    )
    
    is_mandatory = models.BooleanField(
        default=True,
        help_text="Whether this document is mandatory for learners to review"
    )
    
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='uploaded_induction_section_documents'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.title} - {self.section.title}"


# ========================================================================================
# Health & Safety Dynamic Sections and Questions (following Induction Checklist pattern)
# ========================================================================================

class HealthSafetySection(models.Model):
    """Customizable sections for health & safety questionnaire"""
    health_safety_questionnaire = models.ForeignKey(
        HealthSafetyQuestionnaire,
        on_delete=models.CASCADE,
        related_name='dynamic_sections'
    )
    
    title = models.CharField(
        max_length=200,
        help_text="Section title (e.g., 'Fire Safety', 'First Aid', 'Emergency Procedures')"
    )
    
    description = models.TextField(
        blank=True,
        null=True,
        help_text="Optional description of this section"
    )
    
    order = models.PositiveIntegerField(
        default=1,
        help_text="Display order of this section"
    )
    
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this section is active"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_health_safety_sections'
    )
    
    class Meta:
        ordering = ['order', 'title']
        unique_together = ['health_safety_questionnaire', 'title']
    
    def __str__(self):
        return f"{self.title} - {self.health_safety_questionnaire.ilp.user.get_full_name()}"
    
    @property
    def completion_percentage(self):
        """Calculate completion percentage for this section"""
        total_questions = self.questions.count()
        if total_questions == 0:
            return 100
        
        completed_questions = self.questions.filter(
            student_confirmed='yes',
            instructor_confirmed='yes'
        ).count()
        
        return round((completed_questions / total_questions) * 100)


class HealthSafetyQuestion(models.Model):
    """Individual questions within health & safety sections"""
    section = models.ForeignKey(
        HealthSafetySection,
        on_delete=models.CASCADE,
        related_name='questions'
    )
    
    question_text = models.TextField(
        help_text="The health & safety question to be answered"
    )
    
    answer_text = models.TextField(
        blank=True,
        null=True,
        help_text="Answer provided by student/instructor"
    )
    
    student_confirmed = models.CharField(
        max_length=3,
        choices=[('yes', 'Yes'), ('no', 'No'), ('', 'Not Set')],
        default='',
        blank=True,
        help_text="Student confirmation of understanding"
    )
    
    instructor_confirmed = models.CharField(
        max_length=3,
        choices=[('yes', 'Yes'), ('no', 'No'), ('', 'Not Set')],
        default='',
        blank=True,
        help_text="Instructor confirmation of completion"
    )
    
    student_comment = models.TextField(
        blank=True,
        null=True,
        help_text="Student's additional comments or questions"
    )
    
    instructor_reply = models.TextField(
        blank=True,
        null=True,
        help_text="Instructor's reply to student comments"
    )
    
    order = models.PositiveIntegerField(
        default=1,
        help_text="Display order within the section"
    )
    
    is_mandatory = models.BooleanField(
        default=True,
        help_text="Whether this question must be answered"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_health_safety_questions'
    )
    
    class Meta:
        ordering = ['order', 'id']
    
    def __str__(self):
        return f"Q{self.order}: {self.question_text[:50]}..."
    
    @property
    def is_completed(self):
        """Check if question is fully completed"""
        return (
            bool(self.answer_text) and 
            self.student_confirmed == 'yes' and 
            self.instructor_confirmed == 'yes'
        )


class HealthSafetySectionDocument(models.Model):
    """Documents attached to health & safety sections"""
    section = models.ForeignKey(
        HealthSafetySection,
        on_delete=models.CASCADE,
        related_name='documents'
    )
    
    title = models.CharField(
        max_length=200,
        help_text="Document title"
    )
    
    document_file = models.FileField(
        upload_to='health_safety_section_documents/',
        validators=[FileExtensionValidator(allowed_extensions=['pdf', 'doc', 'docx', 'txt', 'jpg', 'jpeg', 'png'])],
        help_text="Upload document (PDF, DOC, DOCX, TXT, Images)"
    )
    
    description = models.TextField(
        blank=True,
        null=True,
        help_text="Optional description of the document"
    )
    
    is_mandatory = models.BooleanField(
        default=True,
        help_text="Whether this document is mandatory for learners to review"
    )
    
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='uploaded_health_safety_section_documents'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.title} - {self.section.title}"


# ========================================================================================
# Learning Needs Dynamic Sections and Questions (following Induction Checklist pattern)
# ========================================================================================

class LearningNeedsSection(models.Model):
    """Customizable sections for learning needs assessment"""
    learning_needs = models.ForeignKey(
        LearningNeeds,
        on_delete=models.CASCADE,
        related_name='dynamic_sections'
    )
    
    title = models.CharField(
        max_length=200,
        help_text="Section title (e.g., 'Employability Skills', 'Learning Support', 'Assessment Needs')"
    )
    
    description = models.TextField(
        blank=True,
        null=True,
        help_text="Optional description of this section"
    )
    
    order = models.PositiveIntegerField(
        default=1,
        help_text="Display order of this section"
    )
    
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this section is active"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_learning_needs_sections'
    )
    
    class Meta:
        ordering = ['order', 'title']
        unique_together = ['learning_needs', 'title']
    
    def __str__(self):
        return f"{self.title} - {self.learning_needs.ilp.user.get_full_name()}"
    
    @property
    def completion_percentage(self):
        """Calculate completion percentage for this section"""
        total_questions = self.questions.count()
        if total_questions == 0:
            return 100
        
        completed_questions = self.questions.filter(
            student_confirmed='yes',
            instructor_confirmed='yes'
        ).count()
        
        return round((completed_questions / total_questions) * 100)


class LearningNeedsQuestion(models.Model):
    """Individual questions within learning needs sections"""
    section = models.ForeignKey(
        LearningNeedsSection,
        on_delete=models.CASCADE,
        related_name='questions'
    )
    
    question_text = models.TextField(
        help_text="The learning needs question to be answered"
    )
    
    answer_text = models.TextField(
        blank=True,
        null=True,
        help_text="Answer provided by student/instructor"
    )
    
    student_confirmed = models.CharField(
        max_length=3,
        choices=[('yes', 'Yes'), ('no', 'No'), ('', 'Not Set')],
        default='',
        blank=True,
        help_text="Student confirmation of understanding"
    )
    
    instructor_confirmed = models.CharField(
        max_length=3,
        choices=[('yes', 'Yes'), ('no', 'No'), ('', 'Not Set')],
        default='',
        blank=True,
        help_text="Instructor confirmation of completion"
    )
    
    student_comment = models.TextField(
        blank=True,
        null=True,
        help_text="Student's additional comments or questions"
    )
    
    instructor_reply = models.TextField(
        blank=True,
        null=True,
        help_text="Instructor's reply to student comments"
    )
    
    order = models.PositiveIntegerField(
        default=1,
        help_text="Display order within the section"
    )
    
    is_mandatory = models.BooleanField(
        default=True,
        help_text="Whether this question must be answered"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_learning_needs_questions'
    )
    
    class Meta:
        ordering = ['order', 'id']
    
    def __str__(self):
        return f"Q{self.order}: {self.question_text[:50]}..."
    
    @property
    def is_completed(self):
        """Check if question is fully completed"""
        return (
            bool(self.answer_text) and 
            self.student_confirmed == 'yes' and 
            self.instructor_confirmed == 'yes'
        )


class LearningNeedsSectionDocument(models.Model):
    """Documents attached to learning needs sections"""
    section = models.ForeignKey(
        LearningNeedsSection,
        on_delete=models.CASCADE,
        related_name='documents'
    )
    
    title = models.CharField(
        max_length=200,
        help_text="Document title"
    )
    
    document_file = models.FileField(
        upload_to='learning_needs_section_documents/',
        validators=[FileExtensionValidator(allowed_extensions=['pdf', 'doc', 'docx', 'txt', 'jpg', 'jpeg', 'png'])],
        help_text="Upload document (PDF, DOC, DOCX, TXT, Images)"
    )
    
    description = models.TextField(
        blank=True,
        null=True,
        help_text="Optional description of the document"
    )
    
    is_mandatory = models.BooleanField(
        default=True,
        help_text="Whether this document is mandatory for learners to review"
    )
    
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='uploaded_learning_needs_section_documents'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.title} - {self.section.title}"


# ========================================================================================
# Strengths & Weaknesses Dynamic Sections and Questions (following Induction Checklist pattern)
# ========================================================================================

class StrengthsWeaknessesSection(models.Model):
    """Customizable sections for strengths & weaknesses assessment"""
    ilp = models.ForeignKey(
        IndividualLearningPlan,
        on_delete=models.CASCADE,
        related_name='strengths_weaknesses_sections'
    )
    
    title = models.CharField(
        max_length=200,
        help_text="Section title (e.g., 'Academic Strengths', 'Communication Skills', 'Areas for Development')"
    )
    
    description = models.TextField(
        blank=True,
        null=True,
        help_text="Optional description of this section"
    )
    
    order = models.PositiveIntegerField(
        default=1,
        help_text="Display order of this section"
    )
    
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this section is active"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_strengths_weaknesses_sections'
    )
    
    class Meta:
        ordering = ['order', 'title']
        unique_together = ['ilp', 'title']
    
    def __str__(self):
        return f"{self.title} - {self.ilp.user.get_full_name()}"
    
    @property
    def completion_percentage(self):
        """Calculate completion percentage for this section"""
        total_questions = self.questions.count()
        if total_questions == 0:
            return 100
        
        completed_questions = self.questions.filter(
            student_confirmed='yes',
            instructor_confirmed='yes'
        ).count()
        
        return round((completed_questions / total_questions) * 100)


class StrengthsWeaknessesQuestion(models.Model):
    """Individual questions within strengths & weaknesses sections"""
    TYPE_CHOICES = [
        ('strength', 'Strength'),
        ('weakness', 'Area for Development'),
    ]
    
    section = models.ForeignKey(
        StrengthsWeaknessesSection,
        on_delete=models.CASCADE,
        related_name='questions'
    )
    
    item_type = models.CharField(
        max_length=10,
        choices=TYPE_CHOICES,
        help_text="Whether this is a strength or area for development"
    )
    
    description = models.TextField(
        help_text="Description of the strength or area for development"
    )
    
    student_confirmed = models.CharField(
        max_length=3,
        choices=[('yes', 'Yes'), ('no', 'No'), ('', 'Not Set')],
        default='',
        blank=True,
        help_text="Student confirmation of understanding"
    )
    
    instructor_confirmed = models.CharField(
        max_length=3,
        choices=[('yes', 'Yes'), ('no', 'No'), ('', 'Not Set')],
        default='',
        blank=True,
        help_text="Instructor confirmation of completion"
    )
    
    student_comment = models.TextField(
        blank=True,
        null=True,
        help_text="Student's additional comments or questions"
    )
    
    instructor_comment = models.TextField(
        blank=True,
        null=True,
        help_text="Instructor's response to student feedback"
    )
    
    order = models.PositiveIntegerField(
        default=1,
        help_text="Display order within the section"
    )
    
    is_mandatory = models.BooleanField(
        default=True,
        help_text="Whether this assessment must be confirmed"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_strengths_weaknesses_questions'
    )
    
    class Meta:
        ordering = ['order', 'id']
    
    def __str__(self):
        return f"{self.get_item_type_display()}: {self.description[:50]}..."
    
    @property
    def is_completed(self):
        """Check if assessment is fully completed"""
        return (
            bool(self.description) and 
            self.student_confirmed == 'yes' and 
            self.instructor_confirmed == 'yes'
        )


class StrengthsWeaknessesSectionDocument(models.Model):
    """Documents attached to strengths & weaknesses sections"""
    section = models.ForeignKey(
        StrengthsWeaknessesSection,
        on_delete=models.CASCADE,
        related_name='documents'
    )
    
    title = models.CharField(
        max_length=200,
        help_text="Document title"
    )
    
    document_file = models.FileField(
        upload_to='strengths_weaknesses_section_documents/',
        validators=[FileExtensionValidator(allowed_extensions=['pdf', 'doc', 'docx', 'txt', 'jpg', 'jpeg', 'png'])],
        help_text="Upload document (PDF, DOC, DOCX, TXT, Images)"
    )
    
    description = models.TextField(
        blank=True,
        null=True,
        help_text="Optional description of the document"
    )
    
    is_mandatory = models.BooleanField(
        default=True,
        help_text="Whether this document is mandatory for learners to review"
    )
    
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='uploaded_strengths_weaknesses_section_documents'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.title} - {self.section.title}"


class StrengthWeaknessFeedback(models.Model):
    """Feedback discussion thread for strength/weakness questions"""
    FEEDBACK_TYPE_CHOICES = [
        ('instructor_initial', 'Instructor Initial Feedback'),
        ('learner_response', 'Learner Response'),
        ('instructor_reply', 'Instructor Reply'),
        ('learner_follow_up', 'Learner Follow-up'),
    ]
    
    APPROVAL_STATUS_CHOICES = [
        ('pending', 'Pending Review'),
        ('approved', 'Approved'),
        ('not_approved', 'Not Approved'),
        ('needs_revision', 'Needs Revision'),
    ]
    
    question = models.ForeignKey(
        StrengthsWeaknessesQuestion,
        on_delete=models.CASCADE,
        related_name='feedback_discussions'
    )
    
    feedback_type = models.CharField(
        max_length=20,
        choices=FEEDBACK_TYPE_CHOICES,
        help_text="Type of feedback in the discussion thread"
    )
    
    content = models.TextField(
        help_text="Feedback content/message"
    )
    
    approval_status = models.CharField(
        max_length=15,
        choices=APPROVAL_STATUS_CHOICES,
        default='pending',
        help_text="Learner's approval status for instructor feedback"
    )
    
    approval_comment = models.TextField(
        blank=True,
        null=True,
        help_text="Additional comment with approval/disapproval"
    )
    
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='created_strength_weakness_feedback'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['created_at']
    
    def __str__(self):
        return f"{self.get_feedback_type_display()} - {self.question}"
    
    @property
    def is_instructor_feedback(self):
        """Check if this feedback is from an instructor"""
        return self.feedback_type in ['instructor_initial', 'instructor_reply']
    
    @property
    def is_learner_feedback(self):
        """Check if this feedback is from a learner"""
        return self.feedback_type in ['learner_response', 'learner_follow_up']


class SimpleStrengthsWeaknesses(models.Model):
    """Simplified strengths and weaknesses assessment with just two fields"""
    APPROVAL_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('not_approved', 'Not Approved'),
    ]
    
    ilp = models.OneToOneField(
        IndividualLearningPlan,
        on_delete=models.CASCADE,
        related_name='simple_strengths_weaknesses'
    )
    
    # Strengths field
    strengths_content = models.TextField(
        blank=True,
        null=True,
        help_text="Learner's strengths assessment"
    )
    strengths_created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_strengths_assessments'
    )
    strengths_updated_at = models.DateTimeField(auto_now=True)
    strengths_approval = models.CharField(
        max_length=15,
        choices=APPROVAL_CHOICES,
        default='pending',
        help_text="Learner's approval status for strengths assessment"
    )
    strengths_learner_comment = models.TextField(
        blank=True,
        null=True,
        help_text="Learner's comment on strengths assessment"
    )
    strengths_instructor_reply = models.TextField(
        blank=True,
        null=True,
        help_text="Instructor's reply to learner's strengths feedback"
    )
    
    # Development areas field
    development_content = models.TextField(
        blank=True,
        null=True,
        help_text="Areas for development assessment"
    )
    development_created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_development_assessments'
    )
    development_updated_at = models.DateTimeField(auto_now=True)
    development_approval = models.CharField(
        max_length=15,
        choices=APPROVAL_CHOICES,
        default='pending',
        help_text="Learner's approval status for development areas assessment"
    )
    development_learner_comment = models.TextField(
        blank=True,
        null=True,
        help_text="Learner's comment on development areas assessment"
    )
    development_instructor_reply = models.TextField(
        blank=True,
        null=True,
        help_text="Instructor's reply to learner's development feedback"
    )
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Simple Strengths & Weaknesses Assessment"
        verbose_name_plural = "Simple Strengths & Weaknesses Assessments"
    
    def __str__(self):
        return f"Strengths & Weaknesses Assessment for {self.ilp.user.username}"
    
    @property
    def completion_percentage(self):
        """Calculate completion percentage based on content and approvals"""
        total_fields = 4  # strengths_content, development_content, strengths_approval, development_approval
        completed_fields = 0
        
        if self.strengths_content:
            completed_fields += 1
            completed_fields += 1
        if self.strengths_approval and self.strengths_approval != 'pending':
            completed_fields += 1
            completed_fields += 1
        
        return int((completed_fields / total_fields) * 100)
    
    @property
    def has_pending_approvals(self):
        """Check if there are pending approvals from learner"""
        return (
            (self.strengths_content and self.strengths_approval == 'pending') or
            (self.development_content and self.development_approval == 'pending')
        )
