"""
Django management command to ensure all courses have proper group structure.
This can be run manually or as a scheduled task to maintain course group integrity.
"""

import logging
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from django.apps import apps

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Manually create groups for courses. This functionality is NOT automatic and must be run by an administrator when needed.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--course',
            type=int,
            help='Course ID to fix (if not specified, will check all courses)'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force recreation of groups even if they already exist'
        )

    def handle(self, *args, **options):
        """Execute the command"""
        course_id = options.get('course')
        force = options.get('force', False)
        
        # Display a warning about the change in behavior
        self.stdout.write(self.style.WARNING(
            "NOTE: Automatic group creation during course creation has been removed. "
            "This command must now be run manually to create groups for courses."
        ))
        
        # Get models via apps to avoid circular imports
        Course = apps.get_model('courses', 'Course')
        CourseEnrollment = apps.get_model('courses', 'CourseEnrollment')
        BranchGroup = apps.get_model('groups', 'BranchGroup')
        GroupMembership = apps.get_model('groups', 'GroupMembership')
        GroupMemberRole = apps.get_model('groups', 'GroupMemberRole')
        CourseGroup = apps.get_model('groups', 'CourseGroup')
        CourseGroupAccess = apps.get_model('groups', 'CourseGroupAccess')
        CustomUser = apps.get_model('users', 'CustomUser')
        Branch = apps.get_model('branches', 'Branch')
        
        # Get default branch for courses without branch
        default_branch = Branch.objects.first()
        if not default_branch:
            self.stdout.write(self.style.ERROR("No branch exists - please create at least one branch first"))
            return
            
        # Get default creator (superuser) for groups
        default_creator = CustomUser.objects.filter(is_superuser=True).first()
        if not default_creator:
            self.stdout.write(self.style.WARNING("No superuser found - some group functions may be limited"))
        
        # Process a single course if specified, otherwise all courses
        if course_id:
            try:
                courses = [Course.objects.get(id=course_id)]
                self.stdout.write(f"Processing single course (ID: {course_id})")
            except Course.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"Course with ID {course_id} not found"))
                return
        else:
            courses = Course.objects.all()
            self.stdout.write(f"Processing all {courses.count()} courses")
        
        fixed_count = 0
        skipped_count = 0
        
        # Process each course
        for course in courses:
            try:
                with transaction.atomic():
                    # Check if course has a branch assigned
                    if not course.branch:
                        self.stdout.write(f"Course '{course.title}' has no branch, assigning to: {default_branch.name}")
                        course.branch = default_branch
                        course.save(update_fields=['branch'])
                    
                    # Check if course already has groups
                    has_course_group = CourseGroup.objects.filter(course=course).exists()
                    course_access_count = CourseGroupAccess.objects.filter(course=course).count()
                    
                    if has_course_group and course_access_count >= 2 and not force:
                        self.stdout.write(f"Course '{course.title}' already has groups set up. Skipping (use --force to override)")
                        skipped_count += 1
                        continue
                    
                    # Set creator for the groups
                    creator = course.instructor or default_creator
                    
                    # Delete existing groups if force is enabled or if groups are incomplete
                    if force or (has_course_group and course_access_count < 2):
                        self.stdout.write(f"Removing existing groups for course '{course.title}'")
                        
                        # Get existing groups
                        course_groups = CourseGroup.objects.filter(course=course).select_related('group')
                        existing_course_group_ids = [cg.group.id for cg in course_groups]
                        
                        course_access = CourseGroupAccess.objects.filter(course=course).select_related('group')
                        existing_user_group_ids = []
                        for ca in course_access:
                            if ca.group.group_type == 'user' and ca.group.id not in existing_course_group_ids:
                                existing_user_group_ids.append(ca.group.id)
                        
                        # First delete memberships to avoid foreign key constraint errors
                        if existing_course_group_ids or existing_user_group_ids:
                            all_group_ids = existing_course_group_ids + existing_user_group_ids
                            GroupMembership.objects.filter(group_id__in=all_group_ids).delete()
                        
                        # Delete existing group associations and access controls
                        CourseGroup.objects.filter(course=course).delete()
                        CourseGroupAccess.objects.filter(course=course).delete()
                        
                        # Delete roles
                        if existing_course_group_ids:
                            GroupMemberRole.objects.filter(group_id__in=existing_course_group_ids).delete()
                        
                        # Delete the groups themselves
                        if existing_course_group_ids:
                            BranchGroup.objects.filter(id__in=existing_course_group_ids).delete()
                        
                        if existing_user_group_ids:
                            BranchGroup.objects.filter(id__in=existing_user_group_ids).delete()
                    
                    # Create groups
                    # 1. User group
                    user_group_name = f"{course.title} Group"
                    user_group, user_group_created = BranchGroup.objects.get_or_create(
                        name=user_group_name,
                        branch=course.branch,
                        defaults={
                            "description": f"User group for {course.title}",
                            "created_by": creator,
                            "group_type": 'user'
                        }
                    )
                    if user_group_created:
                        self.stdout.write(f"Created user group: {user_group_name}")
                    else:
                        self.stdout.write(f"Using existing user group: {user_group_name}")
                    
                    # 2. Course group
                    course_group_name = f"{course.title} Course Group"
                    course_group, course_group_created = BranchGroup.objects.get_or_create(
                        name=course_group_name,
                        branch=course.branch,
                        defaults={
                            "description": f"Course group for {course.title}",
                            "created_by": creator,
                            "group_type": 'course'
                        }
                    )
                    if course_group_created:
                        self.stdout.write(f"Created course group: {course_group_name}")
                    else:
                        self.stdout.write(f"Using existing course group: {course_group_name}")
                    
                    # 3. Create roles
                    instructor_role, instructor_role_created = GroupMemberRole.objects.get_or_create(
                        name="Instructor Role",
                        group=course_group,
                        defaults={
                            "description": "Role for instructors with full editing and management permissions",
                            "can_view": True,
                            "can_edit": True,
                            "can_manage_members": True,
                            "can_manage_content": True,
                            "can_create_topics": True,
                            "auto_enroll": True
                        }
                    )
                    if instructor_role_created:
                        self.stdout.write("Created instructor role")
                    else:
                        # Update existing instructor roles to ensure they have the new permission
                        if not hasattr(instructor_role, 'can_create_topics') or not instructor_role.can_create_topics:
                            instructor_role.can_create_topics = True
                            instructor_role.save()
                            self.stdout.write("Updated existing instructor role with topic creation permission")
                        self.stdout.write("Using existing instructor role")
                    
                    admin_role, admin_role_created = GroupMemberRole.objects.get_or_create(
                        name="Admin Role",
                        group=course_group,
                        defaults={
                            "description": "Role for administrators with full management permissions",
                            "can_view": True,
                            "can_edit": True,
                            "can_manage_members": True,
                            "can_manage_content": True,
                            "auto_enroll": True
                        }
                    )
                    if admin_role_created:
                        self.stdout.write("Created admin role")
                    else:
                        self.stdout.write("Using existing admin role")
                    
                    learner_role, learner_role_created = GroupMemberRole.objects.get_or_create(
                        name="Learner Role",
                        group=course_group,
                        defaults={
                            "description": "Role for learners with view-only permissions",
                            "can_view": True,
                            "can_edit": False,
                            "can_manage_members": False,
                            "can_manage_content": False,
                            "auto_enroll": True
                        }
                    )
                    if learner_role_created:
                        self.stdout.write("Created learner role")
                    else:
                        self.stdout.write("Using existing learner role")
                    
                    # 4. Create course-to-group association
                    course_group_assoc, cg_created = CourseGroup.objects.get_or_create(
                        course=course,
                        group=course_group,
                        defaults={
                            "created_by": creator
                        }
                    )
                    if cg_created:
                        self.stdout.write("Created course-to-group association")
                    else:
                        self.stdout.write("Using existing course-to-group association")
                    
                    # 5. Set up access controls
                    access_control, ac_created = CourseGroupAccess.objects.get_or_create(
                        course=course,
                        group=course_group,
                        defaults={
                            "can_modify": True,
                            "assigned_role": instructor_role,
                            "assigned_at": timezone.now(),
                            "assigned_by": creator
                        }
                    )
                    if ac_created:
                        self.stdout.write("Created course group access control")
                    else:
                        self.stdout.write("Using existing course group access control")
                    
                    user_group_access, uga_created = CourseGroupAccess.objects.get_or_create(
                        course=course,
                        group=user_group,
                        defaults={
                            "can_modify": False,
                            "assigned_role": learner_role,
                            "assigned_at": timezone.now(),
                            "assigned_by": creator
                        }
                    )
                    if uga_created:
                        self.stdout.write("Created user group access control")
                    else:
                        self.stdout.write("Using existing user group access control")
                    
                    # 6. Add course instructor if exists
                    if course.instructor:
                        instructor = course.instructor
                        # Make sure instructor has the same branch as the group
                        if instructor.branch != course.branch:
                            self.stdout.write(f"Updating instructor {instructor.username} branch")
                            instructor.branch = course.branch
                            instructor.save(update_fields=['branch'])
                        
                        # Add to course group with instructor role
                        instructor_membership, created = GroupMembership.objects.get_or_create(
                            group=course_group,
                            user=instructor,
                            defaults={
                                'custom_role': instructor_role,
                                'is_active': True,
                                'joined_at': timezone.now(),
                                'invited_by': creator or instructor
                            }
                        )
                        if created:
                            self.stdout.write(f"Added instructor {instructor.username} to course group")
                        else:
                            self.stdout.write(f"Instructor {instructor.username} already in course group")
                        
                        # Add to user group
                        user_membership, created = GroupMembership.objects.get_or_create(
                            group=user_group,
                            user=instructor,
                            defaults={
                                'is_active': True,
                                'joined_at': timezone.now(),
                                'invited_by': creator or instructor
                            }
                        )
                        if created:
                            self.stdout.write(f"Added instructor {instructor.username} to user group")
                        else:
                            self.stdout.write(f"Instructor {instructor.username} already in user group")
                    
                    # 7. Add enrolled users
                    enrollments = CourseEnrollment.objects.filter(course=course).select_related('user')
                    self.stdout.write(f"Found {enrollments.count()} enrolled users to process")
                    
                    for enrollment in enrollments:
                        user = enrollment.user
                        
                        # Skip if the user is the instructor (already handled)
                        if course.instructor and user.id == course.instructor.id:
                            continue
                            
                        # Make sure user has the same branch as the group
                        if user.branch != course.branch:
                            self.stdout.write(f"Updating user {user.username} branch")
                            user.branch = course.branch
                            user.save(update_fields=['branch'])
                            
                        # Add to course group with appropriate role
                        # Determine role based on user type
                        if user.is_superuser or (isinstance(user.role, str) and user.role == 'admin'):
                            role = admin_role
                        else:
                            role = learner_role
                            
                        # Add to course group
                        course_membership, created = GroupMembership.objects.get_or_create(
                            group=course_group,
                            user=user,
                            defaults={
                                'custom_role': role,
                                'is_active': True,
                                'joined_at': timezone.now(),
                                'invited_by': creator
                            }
                        )
                        if created:
                            self.stdout.write(f"Added user {user.username} to course group with role: {role.name}")
                        else:
                            self.stdout.write(f"User {user.username} already in course group")
                            
                        # Add to user group
                        user_membership, created = GroupMembership.objects.get_or_create(
                            group=user_group,
                            user=user,
                            defaults={
                                'is_active': True,
                                'joined_at': timezone.now(),
                                'invited_by': creator
                            }
                        )
                        if created:
                            self.stdout.write(f"Added user {user.username} to user group")
                        else:
                            self.stdout.write(f"User {user.username} already in user group")
                    
                    fixed_count += 1
                    self.stdout.write(f"Fixed group structure for course '{course.title}' - Created groups and added {enrollments.count()} users")
                    
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error fixing course '{course.title}': {e}"))
                if options.get('traceback', False):
                    import traceback
                    traceback.print_exc()
        
        # Final summary
        self.stdout.write(f"Command completed - Fixed: {fixed_count}, Skipped: {skipped_count}, Total: {courses.count()}")
        return fixed_count 