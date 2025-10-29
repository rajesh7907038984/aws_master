# SCORM Gradebook Display Fix

## Issue
SCORM topics without scores (content-only SCORM) were displaying "0.0/100.0" in the gradebook instead of only showing their status (Completed, In Progress, Not Started).

## Solution
Modified the gradebook logic to distinguish between:
- **Quiz-based SCORM**: SCORM packages with meaningful scores (> 0) - displays score like "47.0/100.0"
- **Content-only SCORM**: SCORM packages without scores (score = 0 or None) - displays only status

## Files Modified

### 1. `/home/ec2-user/lms/gradebook/templatetags/gradebook_tags.py`

#### Changes in `get_activity_score` function (lines 358-386):
- Added check for meaningful score: `has_meaningful_score = (progress.last_score is not None and float(progress.last_score if progress.last_score is not None else 0) > 0)`
- Only returns score data if SCORM has a score > 0
- Returns `score: None` for content-only SCORM packages

#### Changes in `calculate_student_total` function (lines 547-582):
- Only counts SCORM in total points if it has a meaningful score (> 0)
- Content-only SCORM is excluded from both total earned and total possible points
- This ensures the gradebook percentage is accurate and doesn't include content-only activities

### 2. `/home/ec2-user/lms/gradebook/management/commands/clear_gradebook_cache.py`
- Created new management command to manually clear gradebook cache
- Usage: `python3 manage.py clear_gradebook_cache`

## Template Behavior

The existing template logic (`gradebook/templates/gradebook/course_detail.html` lines 1748-1781) already handles the display correctly:

```django
{% if score_data.score is not None %}
  {# Quiz-based SCORM - show score #}
  {{ score_data.score|floatformat:1 }}/{{ activity.max_score|floatformat:1 }}
{% elif score_data.completed %}
  {# Content-only SCORM - show completion status only #}
  Completed
{% else %}
  {# Not completed yet #}
  {% if score_data.can_resume %}
    In Progress
  {% else %}
    Not Attempted
  {% endif %}
{% endif %}
```

## Expected Results

### Before Fix:
- SCORM 1 (wef): 47.0/100.0 ✓ (correct)
- SCORM 2 (edc): 0.0/100.0 ✗ (incorrect - should show status only)
- SCORM 3 (dcv): 0.0/100.0 ✗ (incorrect - should show status only)
- Total: 47.0/300.0 pts (15.7%)

### After Fix:
- SCORM 1 (wef): 47.0/100.0 (quiz-based SCORM with score)
- SCORM 2 (edc): Completed / In Progress / Not Started (content-only SCORM)
- SCORM 3 (dcv): Completed / In Progress / Not Started (content-only SCORM)
- Total: 47.0/100.0 pts (47.0%) - only counts quiz-based SCORM

## Deployment Steps

For code changes in Python files (like templatetags) to take effect:

1. **Restart the Django application** (required for code changes):
   ```bash
   sudo rm -f /home/ec2-user/lmslogs/gunicorn.pid  # Remove stale PID file if exists
   sudo systemctl restart lms-production
   ```

2. **Clear the gradebook cache**:
   ```bash
   python3 manage.py clear_gradebook_cache
   ```

## Cache Management

The gradebook uses caching for performance. Changes will take effect:
1. **Immediately** after restarting service + clearing cache
2. **Automatically** when TopicProgress is updated (signal handler in `gradebook/signals.py`)
3. **After 5 minutes** when cache expires naturally (timeout=300 seconds)

## Testing

To verify the fix:
1. Restart the application: `sudo systemctl restart lms-production`
2. Clear cache: `python3 manage.py clear_gradebook_cache`
3. Navigate to: https://staging.nexsy.io/gradebook/course/34/
4. Verify that content-only SCORM topics show status instead of "0.0/100.0"
5. Verify that total points calculation excludes content-only SCORM

## Technical Details

The fix uses the following logic to determine SCORM type:
```python
has_meaningful_score = (
    progress.last_score is not None and 
    float(progress.last_score if progress.last_score is not None else 0) > 0
)
```

This ensures that:
- `last_score = None` → Content-only (no score)
- `last_score = 0` → Content-only (zero score)
- `last_score > 0` → Quiz-based (meaningful score)

## Date
October 29, 2025

