
# Migration Safeguards
# ===================

# 1. Always check migration dependencies before creating new migrations
python manage.py showmigrations --plan

# 2. Validate migration graph before applying
python manage.py migrate --plan

# 3. Use fake migrations for missing dependencies
python manage.py migrate app_name migration_name --fake

# 4. Reset problematic apps if needed
python manage.py migrate app_name zero --fake
python manage.py migrate app_name

# 5. Check for circular dependencies
python manage.py makemigrations --dry-run
