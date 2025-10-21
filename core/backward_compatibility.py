
# Backward compatibility imports
# These can be removed after all views are migrated

from core.permissions import (
    check_course_permission,
    check_course_edit_permission,
    check_topic_edit_permission,
    check_quiz_edit_permission,
    check_course_catalog_permission,
    check_course_content_permission,
    has_course_delete_permission,
    has_course_edit_permission
)

# Legacy mixins for backward compatibility
from core.mixins.enhanced_view_mixins import (
    CourseViewMixin,
    RobustAtomicViewMixin,
    BaseErrorHandlingMixin,
    GradingViewMixin
)
