# Bug Fix: Topic Creation 500 Error

## Issue
- **URL**: https://staging.nexsy.io/courses/53/topic/create/
- **Error**: 500 - Server error
- **Affected Roles**: Superadmin, Instructor (all roles)
- **Date Fixed**: November 3, 2025

## Root Cause
The `get_user_filtered_content()` function in `/home/ec2-user/lms/courses/views.py` had a Django ORM queryset combination error:

```
AssertionError: Cannot combine a unique query with a non-unique query.
```

The error occurred at line 7638 when trying to combine assignment querysets:
- The initial assignments querysets had `.distinct()` applied
- The course-specific queryset being combined did not have `.distinct()`
- Django cannot combine querysets with different uniqueness constraints

## Solution
Added `.distinct()` to the course-specific assignment queryset to ensure consistency:

**File**: `/home/ec2-user/lms/courses/views.py`  
**Line**: 7638

### Before:
```python
assignments = assignments | Assignment.objects.filter(courses=course)
```

### After:
```python
assignments = assignments | Assignment.objects.filter(courses=course).distinct()
```

## Testing
Tested successfully with:
- ✓ Superadmin role - HTTP 200 (previously 500)
- ✓ Instructor role - HTTP 200 (previously 500)
- ✓ TopicForm initialization successful
- ✓ Filtered content retrieval successful

## Deployment
- **Method**: Graceful reload using `kill -HUP` to gunicorn master process
- **Status**: Live on staging.nexsy.io
- **Downtime**: None

## Technical Details
- The issue was in the `get_user_filtered_content()` helper function
- This function is called by `topic_create()` view to filter quizzes, assignments, conferences, and discussions based on user roles
- The bug affected all user roles attempting to access topic creation pages
- The fix ensures all querysets maintain consistent uniqueness constraints before combination

## Files Modified
1. `/home/ec2-user/lms/courses/views.py` (line 7638)

## Verification
To verify the fix is working, both superadmin and instructor users can now successfully access:
- Course topic creation pages without 500 errors
- All content filtering works correctly
- Form initialization completes successfully

