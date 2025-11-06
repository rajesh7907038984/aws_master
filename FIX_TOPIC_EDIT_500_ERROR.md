# Fix for Topic Edit 500 Error

## Issue
URL: `https://vle.nexsy.io/courses/topic/438/section/107/edit/`
Error: 500 Internal Server Error

## Root Cause
The error occurred in the `get_user_filtered_content()` function in `/home/ec2-user/lms/courses/views.py` at line 7734.

### Error Details
```
AssertionError: Cannot combine a unique query with a non-unique query.
```

The issue was caused by trying to combine Django QuerySets using the `|` (OR) operator when one QuerySet had `.distinct()` applied and the other didn't. Django cannot combine querysets with different uniqueness states.

### Problematic Code
```python
# Lines with premature .distinct() calls that prevented combining
assignments = Assignment.objects.filter(courses__branch=user_branch).distinct().order_by('title')
# ...later...
assignments = assignments | Assignment.objects.filter(courses=course).distinct()
```

## Solution
Removed premature `.distinct()` calls from the assignments querysets before they are combined with the OR operator. The final `.distinct()` in the return statement (line 7740) ensures no duplicates in the final result.

### Changes Made
1. **Line 7665**: Removed `.distinct()` from admin role assignment query
2. **Line 7693**: Removed `.distinct()` from instructor role assignment query  
3. **Line 7715**: Removed `.distinct()` from learner role assignment query
4. **Line 7734**: Removed `.distinct()` from course-specific assignment query

### Fixed Code Pattern
```python
# Initial querysets WITHOUT .distinct()
assignments = Assignment.objects.filter(courses__branch=user_branch).order_by('title')

# Combine querysets using OR operator
if course:
    assignments = assignments | Assignment.objects.filter(courses=course)

# Apply .distinct() only at the end
return {
    'assignments': assignments.distinct(),
    ...
}
```

## Deployment
1. Fixed code in `/home/ec2-user/lms/courses/views.py`
2. Killed old gunicorn processes
3. Restarted `lms-production` service
4. Verified no new errors in logs

## Verification
- Service status: ✅ Active (running)
- Gunicorn workers: ✅ 10 processes running
- Linter errors: ✅ None
- Error logs: ✅ No new errors for topic/438

## Date Fixed
November 6, 2025 14:33 UTC

