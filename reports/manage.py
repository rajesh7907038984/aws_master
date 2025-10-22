#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys


def main():
    """Run administrative tasks."""
    # Set default settings module but allow override from environment
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings')
    
    # Comment out this block to allow using DATABASE_URL in development
    # if os.environ.get('DJANGO_ENV') != 'production' and 'DATABASE_URL' in os.environ:
    #     del os.environ['DATABASE_URL']
    
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()



