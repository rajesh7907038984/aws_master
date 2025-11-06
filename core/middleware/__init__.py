"""
Core Middleware Package
Contains custom middleware for the LMS application
"""

from .domain_fix_middleware import DomainFixMiddleware

__all__ = ['DomainFixMiddleware']

