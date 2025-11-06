# Gradebook Initial Assessment Bug Fix

## Issue Summary
Initial Assessment quiz scores were not displaying properly in the gradebook view at `/gradebook/course/{id}/`. Students who completed Initial Assessments would see "Not Taken" instead of their actual scores and classification results.

## Root Cause
The bug was in the `course_gradebook_detail` view in `/gradebook/views.py`. The function was using an incorrect Django ORM subquery pattern to fetch quiz attempts:

### Problematic Code (Lines 1236-1247):
```python
# Get the latest attempt time for each student-quiz pair
latest_attempts = QuizAttempt.objects.filter(
    quiz=OuterRef('quiz'),
    user=OuterRef('user'),
    is_completed=True
).order_by('-end_time')

quiz_attempts = QuizAttempt.objects.filter(
    user__in=all_students,
    quiz__in=quizzes,
    is_completed=True,
    end_time__in=Subquery(latest_attempts.values('end_time')[:1])
).select_related('quiz', 'user', 'quiz__rubric').order_by('-end_time')
```

### Why This Failed:
1. The `end_time__in=Subquery(latest_attempts.values('end_time')[:1])` pattern doesn't properly correlate with the outer query
2. The `OuterRef` usage in this context doesn't work as intended for filtering
3. This caused quiz attempts (especially for Initial Assessments) to not be retrieved correctly
4. As a result, the `pre_calculate_student_scores` function received an incomplete/empty set of quiz attempts

## The Fix
Simplified the query to fetch ALL completed quiz attempts, and let the `pre_calculate_student_scores` function handle deduplication (which it already does in lines 51-56).

### Fixed Code:
```python
# Get quiz attempts for this course (ordered by end time) with optimized queries
# Get all completed attempts - deduplication is handled by pre_calculate_student_scores
quiz_attempts = QuizAttempt.objects.filter(
    user__in=all_students,
    quiz__in=quizzes,
    is_completed=True
).select_related('quiz', 'user', 'quiz__rubric').order_by('-end_time')
```

### Why This Works:
1. Gets all completed quiz attempts (including Initial Assessments)
2. Orders by `-end_time` so most recent attempts come first
3. The `pre_calculate_student_scores` function already has logic to keep only the latest attempt per student-quiz pair (lines 51-56):
   ```python
   quiz_attempt_lookup = {}
   for attempt in quiz_attempts:
       key = (attempt.user_id, attempt.quiz_id)
       # Keep only the latest attempt for each student-quiz pair
       if key not in quiz_attempt_lookup or attempt.end_time > quiz_attempt_lookup[key].end_time:
           quiz_attempt_lookup[key] = attempt
   ```

## Files Modified
1. `/home/ec2-user/lms/gradebook/views.py`
   - Fixed `course_gradebook_detail` function (lines 1232-1238)
   - Fixed `export_gradebook_csv` function (lines 2687-2693)

## Additional Context
The same bug existed in two places:
1. **Course Gradebook Detail View** (line ~1236): Used for displaying the gradebook table
2. **CSV Export Function** (line ~2688): Used for exporting gradebook data

Both instances have been fixed using the same approach.

## Testing Recommendations
1. Navigate to `/gradebook/course/{course_id}/` for a course with Initial Assessments
2. Verify that students who have completed Initial Assessments show:
   - Their classification (e.g., "Below Level 1", "Level 1", "Level 2")
   - Their score percentage
   - A "VIEW DETAILS" button to see the full attempt
3. Test CSV export to ensure Initial Assessment scores are included
4. Verify that only the latest attempt is shown when students have multiple attempts

## Date
November 6, 2025

