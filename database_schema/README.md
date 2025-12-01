# Database Schema Documentation

This directory contains the database schema for version control and documentation purposes.

## Overview

The LMS database schema is tracked in Git to help future developers understand the database structure and detect changes over time.

## Files

- **`baseline_schema.json`** - The main database schema (tracked in git)
  - Contains complete database structure including tables, columns, indexes, and constraints
  - Updated whenever migrations are applied
  - Used as reference for schema comparisons

- **`production_schema.json`** - Production environment schema (tracked in git)
  - Optional: Can be used to compare production vs development schemas

- **`schema_*.json`** - Temporary timestamped snapshots (not tracked in git)
  - Created for debugging or comparison purposes
  - Automatically ignored by git

## Current Schema Stats

- **Tables:** 215
- **Indexes:** 1,015
- **Constraints:** 2,871
- **Database Engine:** PostgreSQL
- **Last Updated:** {{ Check git commit history }}

## Usage

### View Current Schema

To dump the current database schema:

```bash
python3 manage.py dump_schema --baseline --output database_schema/baseline_schema.json
```

### Compare Current Database with Baseline

To check if your local database matches the baseline:

```bash
# Basic comparison
python3 manage.py compare_schema --baseline database_schema/baseline_schema.json

# Strict mode (exits with error if differences found)
python3 manage.py compare_schema --baseline database_schema/baseline_schema.json --strict

# Ignore specific differences
python3 manage.py compare_schema --baseline database_schema/baseline_schema.json --ignore-indexes
```

### Create a Snapshot

To create a timestamped snapshot (not tracked in git):

```bash
python3 manage.py dump_schema --output database_schema/schema_$(date +%Y%m%d_%H%M%S).json
```

Or use the convenience script:

```bash
bash scripts/schema_management.sh snapshot
```

## Workflow for Database Changes

### When Adding New Migrations

1. **Create your migration:**
   ```bash
   python3 manage.py makemigrations
   ```

2. **Review the migration file** to ensure it's correct

3. **Apply the migration:**
   ```bash
   python3 manage.py migrate
   ```

4. **Update the baseline schema:**
   ```bash
   python3 manage.py dump_schema --baseline --output database_schema/baseline_schema.json
   ```

5. **Commit both the migration and schema:**
   ```bash
   git add */migrations/*.py database_schema/baseline_schema.json
   git commit -m "Add migration: [describe the change]"
   git push
   ```

### When Pulling Changes from Git

1. **Pull the latest changes:**
   ```bash
   git pull
   ```

2. **Compare your local database with the updated baseline:**
   ```bash
   python3 manage.py compare_schema --baseline database_schema/baseline_schema.json
   ```

3. **If differences are found, apply migrations:**
   ```bash
   python3 manage.py migrate
   ```

4. **Verify your database now matches:**
   ```bash
   python3 manage.py compare_schema --baseline database_schema/baseline_schema.json
   ```

## Schema Management Scripts

The project includes a convenient shell script for schema management:

```bash
# Create baseline schema
bash scripts/schema_management.sh dump-baseline

# Dump current schema with timestamp
bash scripts/schema_management.sh dump-current

# Compare with baseline
bash scripts/schema_management.sh compare

# Validate schema (strict mode)
bash scripts/schema_management.sh validate

# Create snapshot
bash scripts/schema_management.sh snapshot

# Setup git hooks
bash scripts/schema_management.sh setup-git
```

## Advanced Options

### Include Django System Tables

By default, Django system tables (like `django_migrations`, `auth_*`) are excluded. To include them:

```bash
python3 manage.py dump_schema --baseline --include-django-tables
```

### Export as SQL

To export schema as SQL DDL instead of JSON:

```bash
python3 manage.py dump_schema --format sql --output database_schema/schema.sql
```

### Include Sample Data

To include sample data (first 10 rows per table):

```bash
python3 manage.py dump_schema --baseline --include-data
```

## Troubleshooting

### Schema Differences Found

If you see schema differences when comparing:

1. **Check if you have unapplied migrations:**
   ```bash
   python3 manage.py showmigrations --list | grep "\[ \]"
   ```

2. **Apply missing migrations:**
   ```bash
   python3 manage.py migrate
   ```

3. **Check if someone forgot to update the baseline:**
   - Review recent commits
   - Contact the team member who made the database changes

### Baseline Schema Out of Date

If the baseline is outdated:

1. **Pull latest changes:**
   ```bash
   git pull
   ```

2. **Apply all migrations:**
   ```bash
   python3 manage.py migrate
   ```

3. **Regenerate baseline:**
   ```bash
   python3 manage.py dump_schema --baseline
   ```

4. **Commit the updated baseline:**
   ```bash
   git add database_schema/baseline_schema.json
   git commit -m "Update baseline schema after migrations"
   git push
   ```

## Benefits for Future Users

1. **Documentation:** Understand database structure without accessing the database
2. **Change Detection:** Identify schema drift between environments
3. **Code Review:** Review database changes alongside code changes in PRs
4. **Onboarding:** New developers can see the full database structure
5. **Migration Safety:** Verify migrations produce expected schema changes
6. **Environment Comparison:** Compare development, staging, and production schemas

## Related Documentation

- Django Migrations: [Django Documentation](https://docs.djangoproject.com/en/stable/topics/migrations/)
- Migration Best Practices: `core/utils/migration_best_practices.py`
- Migration Safety Checker: `core/management/commands/analyze_migration_health.py`

## Questions?

If you have questions about the database schema or need help with migrations, please:
- Check the migration files in `*/migrations/` directories
- Review the model definitions in `*/models.py` files
- Contact the development team

