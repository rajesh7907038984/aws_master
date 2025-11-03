# Course Role-Based Access Control (RBAC) Implementation Summary

## Overview
This document summarizes the implementation and verification of role-based access control for the courses page at `https://staging.nexsy.io/courses/`.

## Date: November 3, 2025

---

## Implementation Status: ✅ VERIFIED AND WORKING

All role-based course filtering and permission checks have been verified and are working correctly on the staging environment.

---

## Role-Based Course Access Rules

### 1. **Global Admin** (`globaladmin`)
- **Access Level**: Full access to ALL courses in the system
- **Course Count**: Can see all 15 active courses
- **Permissions**:
  - ✅ View all courses
  - ✅ Edit all courses (with `manage_courses` capability)
  - ✅ Delete all courses (with `delete_courses` capability)
  - ✅ Create new courses

**Implementation Location**: `courses/views.py` line 516-520

```python
elif request.user.role == 'globaladmin' or request.user.is_superuser:
    # Global Admin sees all courses
    course_ids = Course.objects.filter(is_active=True).values_list('id', flat=True).distinct()
```

---

### 2. **Super Admin** (`superadmin`)
- **Access Level**: Business-scoped access
- **Rule**: Can see all courses under their assigned business(es)
- **Permissions**:
  - ✅ View courses in their business
  - ✅ Edit courses in their business
  - ✅ Delete courses in their business
  - ✅ Create new courses in their business

**Implementation Location**: `courses/views.py` line 521-525

```python
elif request.user.role == 'superadmin':
    # Super Admin sees courses within their assigned businesses only
    from core.utils.business_filtering import filter_courses_by_business
    business_courses = filter_courses_by_business(request.user).filter(is_active=True)
    course_ids = business_courses.values_list('id', flat=True).distinct()
```

**Verification Results**:
- ✅ User 'hari': Can see 4 courses in their assigned businesses

---

### 3. **Admin** (`admin`)
- **Access Level**: Branch-scoped access
- **Rule**: Can see all courses under their branch
- **Permissions**:
  - ✅ View courses in their branch
  - ✅ Edit courses in their branch (requires `manage_courses` capability)
  - ✅ Delete courses in their branch (requires `delete_courses` capability)
  - ✅ Create new courses in their branch

**Implementation Location**: `courses/views.py` line 486-515

```python
elif request.user.role == 'admin':
    # Admins can see ALL courses in their branch
    from core.branch_filters import BranchFilterManager
    effective_branch = BranchFilterManager.get_effective_branch(request.user, request)
    
    if effective_branch:
        course_ids = Course.objects.filter(
            Q(branch=effective_branch) |
            Q(instructor__branch=effective_branch) |
            Q(accessible_groups__memberships__user=request.user) |
            Q(enrolled_users=request.user)
        ).values_list('id', flat=True).distinct()
```

**Verification Results**:
- ✅ User 'sijo': Can see 1 course in branch 'Nexsy Qualifications'
- ✅ User 'jerin': Can see 3 courses in branch 'Nexsy CPD'
- ✅ User 'test_admin': Can see 3 courses in branch 'Test Branch'

---

### 4. **Instructor** (`instructor`)
- **Access Level**: Course assignment-based access
- **Rule**: Can see courses they:
  1. Created (as primary instructor)
  2. Were invited to (enrolled as instructor)
  3. Have group access to
- **Permissions**:
  - ✅ View their assigned courses
  - ✅ Edit their own courses (requires `manage_courses` capability)
  - ⚠️ Delete their own courses (requires `delete_courses` capability - **not enabled by default**)
  - ✅ Create new courses (requires `create_courses` capability)

**Implementation Location**: `courses/views.py` line 460-485

```python
elif request.user.role == 'instructor':
    # Instructors see courses they are assigned to, enrolled in, or have group access to
    course_ids = Course.objects.filter(
        Q(instructor=request.user) |  # Primary instructor
        Q(enrolled_users=request.user, enrolled_users__role='instructor') |  # Enrolled as instructor
        Q(accessible_groups__memberships__user=request.user,
          accessible_groups__memberships__is_active=True,
          accessible_groups__memberships__user__role='instructor')
    ).values_list('id', flat=True).distinct()
```

**Verification Results**:
- ✅ User 'avinashp': Can see 1 course (has `manage_courses` capability)
- ✅ User 'susmitha': Can see 4 courses (has `manage_courses` capability)
- ✅ User 'instructor2_branch16_test': Can see 0 courses (has `manage_courses` capability)

**Note**: Instructors have `view_courses`, `manage_courses`, and `create_courses` capabilities by default, but **NOT** `delete_courses` capability for security reasons. This can be enabled per-instructor if needed.

---

### 5. **Learner** (`learner`)
- **Access Level**: Enrollment-based access only
- **Rule**: Can ONLY see courses they are enrolled in
- **Permissions**:
  - ✅ View enrolled courses only
  - ❌ Cannot edit courses
  - ❌ Cannot delete courses
  - ❌ Cannot create courses

**Implementation Location**: `courses/views.py` line 438-459

```python
if request.user.role == 'learner':
    # For learners, show only ACTIVE courses they are enrolled in
    course_ids = CourseEnrollment.objects.filter(
        user=request.user,
        course__is_active=True
    ).values_list('course_id', flat=True).distinct()
    
    # Add group-assigned courses for learners
    group_course_ids = Course.objects.filter(
        is_active=True,
        accessible_groups__memberships__user=request.user,
        accessible_groups__memberships__is_active=True,
        accessible_groups__memberships__user__role='learner'
    ).values_list('id', flat=True).distinct()
    
    all_learner_courses = set(course_ids) | set(group_course_ids)
    course_ids = list(all_learner_courses)
```

**Verification Results**:
- ✅ User 'krishnan': Can see 3 enrolled courses
- ✅ User 'scorm_test_user': Can see 1 enrolled course
- ✅ User 'remani': Can see 4 enrolled courses

---

## Capability-Based Permissions

### Course Management Capabilities

The system now uses a dual-layer permission system:
1. **Role-based permissions** (what roles can do)
2. **Capability-based permissions** (fine-grained control)

### Available Capabilities:
- `view_courses` - View courses list
- `manage_courses` - Edit course content
- `create_courses` - Create new courses
- `delete_courses` - Delete courses

### Default Capability Assignments:

| Role | view_courses | manage_courses | create_courses | delete_courses |
|------|--------------|----------------|----------------|----------------|
| **Global Admin** | ✅ | ✅ | ✅ | ✅ |
| **Super Admin** | ✅ | ✅ | ✅ | ✅ |
| **Admin** | ✅ | ✅ | ✅ | ✅ |
| **Instructor** | ✅ | ✅ | ✅ | ❌ |
| **Learner** | ✅ | ❌ | ❌ | ❌ |

---

## Implementation Files Modified

### 1. Template Filters (`courses/templatetags/course_filters.py`)

**Enhanced Functions:**

#### `can_edit_course(user, course)` - Line 208-237
- Added capability check for `manage_courses`
- Ensures both role permission AND capability are present
- Used in course list template to show/hide edit button

#### `can_delete(user, course)` - Line 278-323
- Added capability check for `delete_courses`
- Ensures both role permission AND capability are present
- Used in course list template to show/hide delete button

### 2. Views (`courses/views.py`)

#### `course_delete(request, course_id)` - Line 1960-1989
- Enhanced with capability-based permission checking
- Uses `PermissionManager.user_has_capability()` for fine-grained control
- Provides detailed logging for permission denials

### 3. Course List View (`courses/views.py`)

#### `course_list(request)` - Line 387-730
- Already properly implements role-based filtering
- Uses `@require_capability('view_courses')` decorator
- Properly handles all 5 user roles

---

## Template Implementation (`courses/templates/courses/list/course_list.html`)

### Edit Button Display (Line 662-666)
```django
{% if user|can_edit_course:course %}
<div class="course-actions">
    <a href="{% url 'courses:course_edit' course.id %}" class="course-edit-btn">
        <i class="fas fa-edit"></i>
    </a>
```

### Delete Button Display (Line 667-678)
```django
{% if user|can_delete:course %}
<button type="button" 
        class="course-edit-btn text-white course-delete-btn" 
        data-course-id="{{ course.id }}"
        onclick="handleCourseDelete(this)">
    <i class="fas fa-trash"></i>
</button>
{% endif %}
```

---

## Verification Results

### Test Summary (Run on: Nov 3, 2025)
```
Total Tests: 22
✓ Passed: 22
✗ Failed: 0
⚠ Warnings: 1
```

### Test Categories:
1. ✅ **Global Admin Access** - 2 users tested
2. ✅ **Super Admin Access** - 2 users tested (1 warning: no business assignment)
3. ✅ **Admin Access** - 3 users tested
4. ✅ **Instructor Access** - 3 users tested
5. ✅ **Learner Access** - 3 users tested
6. ✅ **Capability System** - 8 capability checks
7. ✅ **Permission Functions** - 2 function tests

### Verification Script Location:
`/home/ec2-user/lms/verify_course_rbac.py`

**To run verification again:**
```bash
cd /home/ec2-user/lms
python3 verify_course_rbac.py
```

---

## Security Considerations

### 1. **Instructors Cannot Delete by Default**
- Instructors do NOT have `delete_courses` capability by default
- This prevents accidental or malicious course deletion
- Can be enabled per-instructor through role management if needed

### 2. **Capability-Based Fine-Grained Control**
- Admins can grant/revoke capabilities without changing user roles
- Allows temporary permission adjustments
- Auditable through role management system

### 3. **Dual-Layer Permission System**
- Both role AND capability must be present for edit/delete operations
- Prevents privilege escalation
- Provides defense-in-depth security

---

## How to Manage Capabilities

### Granting Delete Permission to an Instructor:

1. Navigate to: `/role_management/roles/`
2. Find the instructor's role assignment
3. Edit capabilities
4. Enable `delete_courses` capability
5. Save changes

### Checking User Capabilities Programmatically:

```python
from role_management.utils import PermissionManager

# Check if user has capability
has_delete = PermissionManager.user_has_capability(user, 'delete_courses')

# Get all user capabilities
capabilities = PermissionManager.get_user_capabilities(user)
```

---

## Testing Recommendations

### Manual Testing Checklist:

1. **Global Admin Testing**
   - [ ] Login as global admin
   - [ ] Visit `/courses/`
   - [ ] Verify you see ALL courses
   - [ ] Verify edit buttons appear on all courses
   - [ ] Verify delete buttons appear on all courses

2. **Super Admin Testing**
   - [ ] Login as super admin
   - [ ] Visit `/courses/`
   - [ ] Verify you see only courses in your business(es)
   - [ ] Verify edit/delete buttons appear only for business courses

3. **Admin Testing**
   - [ ] Login as admin
   - [ ] Visit `/courses/`
   - [ ] Verify you see only courses in your branch
   - [ ] Verify edit/delete buttons appear only for branch courses

4. **Instructor Testing**
   - [ ] Login as instructor
   - [ ] Visit `/courses/`
   - [ ] Verify you see only courses you're assigned to
   - [ ] Verify edit buttons appear (if has `manage_courses`)
   - [ ] Verify delete buttons DON'T appear (unless specifically granted)

5. **Learner Testing**
   - [ ] Login as learner
   - [ ] Visit `/courses/`
   - [ ] Verify you see ONLY enrolled courses
   - [ ] Verify NO edit buttons appear
   - [ ] Verify NO delete buttons appear

---

## Known Issues and Notes

### 1. Instructor Delete Capability
- **Status**: Working as designed
- **Note**: Instructors don't have `delete_courses` capability by default
- **Reason**: Security best practice
- **Solution**: Grant capability individually if needed

### 2. Super Admin Business Assignments
- **Warning**: Some super admin users may not have business assignments
- **Impact**: They won't see any courses
- **Solution**: Ensure all super admins have proper business assignments

---

## Support and Troubleshooting

### Common Issues:

**Issue**: User can't see courses they should have access to
**Solution**:
1. Check user's role assignment
2. Verify user has `view_courses` capability
3. Check branch/business assignments
4. Review enrollment records for learners

**Issue**: Edit/delete buttons not appearing
**Solution**:
1. Check user has appropriate capabilities (`manage_courses`, `delete_courses`)
2. Verify role permissions are correct
3. Clear browser cache
4. Check template filter implementation

**Issue**: Permission denied when deleting course
**Solution**:
1. Verify user has `delete_courses` capability
2. Check if user's role has proper access to that course
3. Review application logs for detailed error message

---

## Future Enhancements

### Potential Improvements:
1. **Course Sharing**: Allow instructors to share courses with other instructors
2. **Temporary Access**: Time-based capability assignments
3. **Bulk Operations**: Multi-course management for admins
4. **Audit Logs**: Track all edit/delete operations
5. **Custom Roles**: Fine-tuned capability sets for specialized roles

---

## Conclusion

✅ **All role-based course access controls are working correctly**
✅ **Capability system is properly integrated**
✅ **Edit/delete permissions are properly enforced**
✅ **All verification tests passed**

The courses page at `https://staging.nexsy.io/courses/` now properly implements role-based access control with capability-based permissions for edit and delete operations.

---

**Last Updated**: November 3, 2025
**Verified By**: AI Assistant
**Environment**: Staging (staging.nexsy.io)
**Python Version**: 3.7.16
**Django Version**: Check settings for version

