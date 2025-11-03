from django import template
from datetime import datetime, timedelta
from typing import Any, Optional, Union, Dict

register = template.Library()

@register.filter
def add_days(value: Union[datetime, str, None], days: Union[int, str, None]) -> str:
    """Add a given number of days to a date string."""
    if not value or not days:
        return "-"
    
    try:
        # If value is already a datetime
        if isinstance(value, datetime):
            date_obj = value
        else:
            # Try to parse the string to a datetime
            date_obj = datetime.strptime(value, "%b %d, %Y")
        
        # Add the days
        new_date = date_obj + timedelta(days=int(days))
        
        # Format back to the same format
        return new_date.strftime("%b %d, %Y")
    except (ValueError, TypeError):
        return "-"

@register.filter
def get_item(dictionary: Optional[Dict[Any, Any]], key: Any) -> Any:
    """Get an item from a dictionary using key."""
    if not dictionary:
        return None
    return dictionary.get(key)

@register.simple_tag
def get_topic_for_assignment(assignment_id: Union[int, str]) -> Optional[Any]:
    """Get the topic associated with an assignment by assignment ID."""
    from courses.models import Topic
    try:
        topic = Topic.objects.filter(assignment_id=assignment_id).first()
        return topic
    except Topic.DoesNotExist:
        return None

@register.simple_tag
def get_topic_for_quiz(quiz_id):
    """Get the topic associated with a quiz by quiz ID."""
    from courses.models import Topic
    try:
        topic = Topic.objects.filter(quiz_id=quiz_id).first()
        return topic
    except Topic.DoesNotExist:
        return None

@register.simple_tag
def get_topic_for_discussion(discussion_id):
    """Get the topic associated with a discussion by discussion ID."""
    from courses.models import Topic
    try:
        topic = Topic.objects.filter(discussion_id=discussion_id).first()
        return topic
    except Topic.DoesNotExist:
        return None

@register.simple_tag
def get_topics_for_rubric(rubric):
    """Get all topics associated with a rubric through assignments."""
    try:
        from courses.models import Topic
        topics = []
        # Get all assignments associated with this rubric
        for assignment in rubric.rubric_assignments.all():
            # Find topics that reference this assignment
            assignment_topics = Topic.objects.filter(assignment=assignment)
            topics.extend(assignment_topics)
        return topics
    except Exception:
        return []

@register.simple_tag
def get_rubrics_for_course(course):
    """Get all rubrics associated with a course (both direct and through assignments)."""
    try:
        from lms_rubrics.models import Rubric
        rubrics = set()
        
        # Get directly linked rubrics
        direct_rubrics = course.rubrics.all()
        rubrics.update(direct_rubrics)
        
        # Get rubrics from course assignments
        # Check assignments linked through direct course field
        for assignment in course.assignments.all():
            if assignment.rubric:
                rubrics.add(assignment.rubric)
        
        # Check assignments linked through many-to-many relationship
        for assignment in course.course_assignments.all():
            if assignment.rubric:
                rubrics.add(assignment.rubric)
        
        return list(rubrics)
    except Exception:
        return []

@register.simple_tag
def get_outcomes_for_course(course):
    """Get all outcomes associated with a course (both direct and through assignment rubrics)."""
    try:
        from lms_outcomes.models import Outcome, RubricCriterionOutcome
        outcomes = set()
        
        # Get directly linked outcomes
        direct_outcomes = course.outcomes.all()
        outcomes.update(direct_outcomes)
        
        # Get outcomes from assignment rubrics
        course_rubrics = get_rubrics_for_course(course)
        for rubric in course_rubrics:
            # Get all criteria for this rubric
            for criterion in rubric.criteria.all():
                # Get outcomes connected to this criterion
                criterion_outcomes = RubricCriterionOutcome.objects.filter(
                    criterion=criterion
                ).select_related('outcome')
                for connection in criterion_outcomes:
                    outcomes.add(connection.outcome)
        
        return list(outcomes)
    except Exception:
        return []

# Note: get_topic_progress filter is defined in course_filters.py to avoid duplication 