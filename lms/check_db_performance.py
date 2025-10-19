#!/usr/bin/env python
"""
Check database for performance issues, missing indexes, and constraints
"""

import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings.production')
django.setup()

from django.db import connection

def check_missing_indexes():
    """Check for tables without proper indexes"""
    print("🔍 Checking for Missing Indexes")
    print("=" * 70)
    
    with connection.cursor() as cursor:
        # Find tables with no indexes (except primary keys)
        cursor.execute("""
            SELECT 
                t.tablename,
                COUNT(i.indexname) as index_count
            FROM pg_tables t
            LEFT JOIN pg_indexes i ON t.tablename = i.tablename
            WHERE t.schemaname = 'public'
            AND t.tablename NOT LIKE 'django_%'
            AND t.tablename NOT LIKE 'auth_%'
            GROUP BY t.tablename
            HAVING COUNT(i.indexname) <= 1
            ORDER BY t.tablename;
        """)
        
        tables_with_few_indexes = cursor.fetchall()
        
        if tables_with_few_indexes:
            print(f"⚠️  Found {len(tables_with_few_indexes)} tables with minimal indexes:")
            for table, count in tables_with_few_indexes:
                print(f"  - {table}: {count} index(es)")
        else:
            print("✅ All tables have adequate indexes")
        
        return tables_with_few_indexes

def check_unused_indexes():
    """Check for indexes that are never used"""
    print("\n🔍 Checking for Unused Indexes")
    print("=" * 70)
    
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT
                schemaname,
                relname as tablename,
                indexrelname as indexname,
                idx_scan,
                pg_size_pretty(pg_relation_size(indexrelid)) as index_size
            FROM pg_stat_user_indexes
            WHERE idx_scan = 0
            AND indexrelname NOT LIKE '%pkey'
            AND schemaname = 'public'
            ORDER BY pg_relation_size(indexrelid) DESC
            LIMIT 20;
        """)
        
        unused_indexes = cursor.fetchall()
        
        if unused_indexes:
            print(f"⚠️  Found {len(unused_indexes)} unused indexes:")
            for schema, table, index, scans, size in unused_indexes:
                print(f"  - {index} on {table} ({size}) - {scans} scans")
        else:
            print("✅ All indexes are being used")
        
        return unused_indexes

def check_duplicate_indexes():
    """Check for duplicate or redundant indexes"""
    print("\n🔍 Checking for Duplicate Indexes")
    print("=" * 70)
    
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT
                idx1.indexname as index1,
                idx2.indexname as index2,
                idx1.tablename
            FROM pg_indexes idx1
            JOIN pg_indexes idx2 ON 
                idx1.tablename = idx2.tablename
                AND idx1.indexdef = idx2.indexdef
                AND idx1.indexname < idx2.indexname
            WHERE idx1.schemaname = 'public'
            ORDER BY idx1.tablename;
        """)
        
        duplicates = cursor.fetchall()
        
        if duplicates:
            print(f"⚠️  Found {len(duplicates)} duplicate indexes:")
            for idx1, idx2, table in duplicates:
                print(f"  - {idx1} and {idx2} on {table}")
        else:
            print("✅ No duplicate indexes found")
        
        return duplicates

def check_table_bloat():
    """Check for table bloat (dead tuples)"""
    print("\n🔍 Checking for Table Bloat")
    print("=" * 70)
    
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT
                schemaname,
                relname as tablename,
                n_live_tup,
                n_dead_tup,
                CASE 
                    WHEN n_live_tup > 0 
                    THEN ROUND((n_dead_tup::numeric / n_live_tup::numeric) * 100, 2)
                    ELSE 0 
                END as dead_ratio,
                pg_size_pretty(pg_total_relation_size(schemaname||'.'||relname)) as total_size
            FROM pg_stat_user_tables
            WHERE n_dead_tup > 1000
            AND schemaname = 'public'
            ORDER BY n_dead_tup DESC
            LIMIT 20;
        """)
        
        bloated_tables = cursor.fetchall()
        
        if bloated_tables:
            print(f"⚠️  Found {len(bloated_tables)} tables with significant dead tuples:")
            for schema, table, live, dead, ratio, size in bloated_tables:
                print(f"  - {table}: {dead} dead tuples ({ratio}% of live) - Size: {size}")
            print("\n💡 Recommendation: Run VACUUM ANALYZE on these tables")
        else:
            print("✅ No significant table bloat detected")
        
        return bloated_tables

def check_missing_foreign_key_indexes():
    """Check for foreign key columns without indexes"""
    print("\n🔍 Checking for Foreign Keys Without Indexes")
    print("=" * 70)
    
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT
                c.conrelid::regclass AS table_name,
                string_agg(a.attname, ', ') AS column_name,
                c.confrelid::regclass AS referenced_table
            FROM pg_constraint c
            JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)
            WHERE c.contype = 'f'
            AND NOT EXISTS (
                SELECT 1
                FROM pg_index i
                WHERE i.indrelid = c.conrelid
                AND a.attnum = ANY(i.indkey)
            )
            GROUP BY c.conrelid, c.confrelid
            ORDER BY table_name;
        """)
        
        missing_fk_indexes = cursor.fetchall()
        
        if missing_fk_indexes:
            print(f"⚠️  Found {len(missing_fk_indexes)} foreign keys without indexes:")
            for table, column, ref_table in missing_fk_indexes:
                print(f"  - {table}.{column} -> {ref_table}")
            print("\n💡 Recommendation: Add indexes on these foreign key columns")
        else:
            print("✅ All foreign keys have proper indexes")
        
        return missing_fk_indexes

def check_long_running_queries():
    """Check for slow query patterns"""
    print("\n🔍 Checking Query Statistics")
    print("=" * 70)
    
    with connection.cursor() as cursor:
        try:
            # Check if pg_stat_statements extension is available
            cursor.execute("""
                SELECT EXISTS (
                    SELECT 1 FROM pg_extension WHERE extname = 'pg_stat_statements'
                );
            """)
            
            has_extension = cursor.fetchone()[0]
            
            if has_extension:
                cursor.execute("""
                    SELECT
                        LEFT(query, 100) as query_snippet,
                        calls,
                        ROUND(total_time::numeric, 2) as total_time_ms,
                        ROUND(mean_time::numeric, 2) as mean_time_ms,
                        ROUND((100 * total_time / SUM(total_time) OVER())::numeric, 2) AS percentage
                    FROM pg_stat_statements
                    WHERE query NOT LIKE '%pg_stat_statements%'
                    ORDER BY total_time DESC
                    LIMIT 10;
                """)
                
                slow_queries = cursor.fetchall()
                
                if slow_queries:
                    print("📊 Top 10 queries by total execution time:")
                    for query, calls, total, mean, pct in slow_queries:
                        print(f"  - {query}...")
                        print(f"    Calls: {calls}, Total: {total}ms, Mean: {mean}ms, {pct}%")
                else:
                    print("✅ No significant slow queries detected")
            else:
                print("ℹ️  pg_stat_statements extension not available")
                
        except Exception as e:
            print(f"ℹ️  Could not check query statistics: {e}")

def check_database_size():
    """Check database and table sizes"""
    print("\n🔍 Checking Database Size")
    print("=" * 70)
    
    with connection.cursor() as cursor:
        # Total database size
        cursor.execute("""
            SELECT pg_size_pretty(pg_database_size(current_database()));
        """)
        db_size = cursor.fetchone()[0]
        print(f"📊 Total database size: {db_size}")
        
        # Largest tables
        cursor.execute("""
            SELECT
                tablename,
                pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size,
                pg_total_relation_size(schemaname||'.'||tablename) as size_bytes
            FROM pg_tables
            WHERE schemaname = 'public'
            ORDER BY size_bytes DESC
            LIMIT 10;
        """)
        
        largest_tables = cursor.fetchall()
        print("\n📊 Top 10 largest tables:")
        for table, size, size_bytes in largest_tables:
            print(f"  - {table}: {size}")

def check_connection_limits():
    """Check database connection usage"""
    print("\n🔍 Checking Connection Usage")
    print("=" * 70)
    
    with connection.cursor() as cursor:
        # Current connections
        cursor.execute("""
            SELECT 
                COUNT(*) as current_connections,
                MAX(COALESCE(setting::int, 100)) as max_connections
            FROM pg_stat_activity
            CROSS JOIN pg_settings
            WHERE pg_settings.name = 'max_connections';
        """)
        
        current, max_conn = cursor.fetchone()
        usage_pct = (current / max_conn) * 100
        
        print(f"📊 Current connections: {current} / {max_conn} ({usage_pct:.1f}%)")
        
        if usage_pct > 80:
            print("⚠️  Connection usage is high!")
        elif usage_pct > 50:
            print("⚠️  Connection usage is moderate")
        else:
            print("✅ Connection usage is healthy")

def main():
    print("🔍 Database Performance Check")
    print("=" * 70)
    print()
    
    issues_found = []
    
    # Run all checks
    missing_indexes = check_missing_indexes()
    if missing_indexes:
        issues_found.append(f"{len(missing_indexes)} tables with minimal indexes")
    
    unused_indexes = check_unused_indexes()
    if unused_indexes:
        issues_found.append(f"{len(unused_indexes)} unused indexes")
    
    duplicates = check_duplicate_indexes()
    if duplicates:
        issues_found.append(f"{len(duplicates)} duplicate indexes")
    
    bloated = check_table_bloat()
    if bloated:
        issues_found.append(f"{len(bloated)} bloated tables")
    
    missing_fk_idx = check_missing_foreign_key_indexes()
    if missing_fk_idx:
        issues_found.append(f"{len(missing_fk_idx)} foreign keys without indexes")
    
    check_long_running_queries()
    check_database_size()
    check_connection_limits()
    
    print("\n" + "=" * 70)
    print("🎯 Performance Summary:")
    
    if issues_found:
        print(f"⚠️  Found {len(issues_found)} performance issues:")
        for issue in issues_found:
            print(f"  - {issue}")
        print("\n💡 Recommendations:")
        if missing_fk_idx:
            print("  1. Add indexes on foreign key columns")
        if bloated:
            print("  2. Run VACUUM ANALYZE on bloated tables")
        if unused_indexes:
            print("  3. Consider removing unused indexes")
        return False
    else:
        print("✅ Database performance looks good!")
        return True

if __name__ == '__main__':
    success = main()
    exit(0 if success else 1)

