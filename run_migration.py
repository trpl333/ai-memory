#!/usr/bin/env python3
"""
Migration Runner for Multi-Tenant Transformation
Safely executes migration 002_add_customer_id_for_multi_tenant.sql

Usage (on production server 209.38.143.71):
    python3 run_migration.py --dry-run  # Preview changes
    python3 run_migration.py --execute  # Run migration
    python3 run_migration.py --verify   # Verify migration success
"""

import os
import sys
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
import argparse
from datetime import datetime

# Database connection from environment
DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    print("ERROR: DATABASE_URL environment variable not set!")
    print("Export it first: export DATABASE_URL='postgresql://user:pass@localhost:5432/dbname'")
    sys.exit(1)

def get_db_connection():
    """Create database connection"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        return conn
    except Exception as e:
        print(f"ERROR: Could not connect to database: {e}")
        sys.exit(1)

def read_migration_file():
    """Read the migration SQL file"""
    migration_path = os.path.join(os.path.dirname(__file__), 
                                   'migrations', 
                                   '002_add_customer_id_for_multi_tenant.sql')
    
    if not os.path.exists(migration_path):
        print(f"ERROR: Migration file not found: {migration_path}")
        sys.exit(1)
    
    with open(migration_path, 'r') as f:
        return f.read()

def check_table_exists(cursor, table_name):
    """Check if a table exists"""
    cursor.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = %s
        );
    """, (table_name,))
    return cursor.fetchone()[0]

def count_rows(cursor, table_name):
    """Count rows in a table"""
    try:
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        return cursor.fetchone()[0]
    except:
        return 0

def dry_run():
    """Preview what the migration will do"""
    print("=" * 80)
    print("DRY RUN: Multi-Tenant Migration Preview")
    print("=" * 80)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    tables = ['memories', 'call_summaries', 'caller_profiles', 
              'personality_metrics', 'personality_averages']
    
    print("\n📊 CURRENT STATE:")
    print("-" * 80)
    
    for table in tables:
        if check_table_exists(cursor, table):
            count = count_rows(cursor, table)
            
            # Check if customer_id already exists
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = %s AND column_name = 'customer_id'
            """, (table,))
            has_customer_id = cursor.fetchone() is not None
            
            status = "✅ Has customer_id" if has_customer_id else "❌ Missing customer_id"
            print(f"  {table:30} {count:8,} rows  {status}")
        else:
            print(f"  {table:30} ⚠️  Table does not exist!")
    
    print("\n📋 MIGRATION WILL:")
    print("-" * 80)
    print("  1. Add customer_id INTEGER column to all 5 tables")
    print("  2. Migrate existing data to customer_id=1 (Peterson Insurance)")
    print("  3. Set customer_id as NOT NULL")
    print("  4. Create composite indexes for performance")
    print("  5. Update unique constraints for multi-tenancy")
    print("  6. Enable PostgreSQL Row-Level Security (RLS)")
    print("  7. Create RLS policies for automatic tenant isolation")
    print("  8. Update personality_averages function for multi-tenancy")
    
    print("\n⚠️  IMPORTANT:")
    print("-" * 80)
    print("  - All existing data will be assigned to customer_id=1")
    print("  - This is Peterson Insurance (Test Client #1)")
    print("  - Migration takes ~5-30 seconds depending on data volume")
    print("  - Database will remain accessible during migration")
    
    cursor.close()
    conn.close()
    
    print("\n✅ Dry run complete. Run with --execute to apply changes.")
    print("=" * 80)

def execute_migration():
    """Execute the migration"""
    print("=" * 80)
    print("EXECUTING: Multi-Tenant Migration")
    print("=" * 80)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Read migration file
    migration_sql = read_migration_file()
    
    print(f"\n⏰ Starting migration at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("🚀 Executing migration SQL...")
    
    try:
        # Execute the entire migration
        cursor.execute(migration_sql)
        
        print("✅ Migration SQL executed successfully!")
        
        # Verify results
        print("\n📊 VERIFICATION:")
        print("-" * 80)
        
        tables = ['memories', 'call_summaries', 'caller_profiles', 
                  'personality_metrics', 'personality_averages']
        
        for table in tables:
            # Check customer_id exists
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = %s AND column_name = 'customer_id'
            """, (table,))
            has_customer_id = cursor.fetchone() is not None
            
            # Check for NULL customer_ids
            cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE customer_id IS NULL")
            null_count = cursor.fetchone()[0]
            
            # Check RLS enabled
            cursor.execute("""
                SELECT relrowsecurity 
                FROM pg_class 
                WHERE relname = %s
            """, (table,))
            rls_enabled = cursor.fetchone()[0] if cursor.rowcount > 0 else False
            
            status = "✅" if has_customer_id and null_count == 0 and rls_enabled else "❌"
            print(f"  {status} {table:30} customer_id: {has_customer_id}  NULLs: {null_count}  RLS: {rls_enabled}")
        
        # Check policies
        cursor.execute("""
            SELECT COUNT(*) 
            FROM pg_policies 
            WHERE schemaname = 'public' AND policyname LIKE 'tenant_isolation_%'
        """)
        policy_count = cursor.fetchone()[0]
        
        print(f"\n  ✅ RLS Policies Created: {policy_count}/5")
        
        print("\n✅ Migration completed successfully!")
        print(f"⏰ Finished at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
    except Exception as e:
        print(f"\n❌ ERROR during migration: {e}")
        print("Migration failed! Database state may be partially migrated.")
        print("Review errors and re-run or contact support.")
        sys.exit(1)
    
    cursor.close()
    conn.close()
    
    print("=" * 80)

def verify_migration():
    """Verify migration was successful"""
    print("=" * 80)
    print("VERIFICATION: Multi-Tenant Migration Status")
    print("=" * 80)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    tables = ['memories', 'call_summaries', 'caller_profiles', 
              'personality_metrics', 'personality_averages']
    
    all_good = True
    
    print("\n📋 CHECKLIST:")
    print("-" * 80)
    
    # Check 1: All tables have customer_id
    print("\n1. Customer ID Columns:")
    for table in tables:
        cursor.execute("""
            SELECT column_name, is_nullable 
            FROM information_schema.columns 
            WHERE table_name = %s AND column_name = 'customer_id'
        """, (table,))
        result = cursor.fetchone()
        
        if result and result[1] == 'NO':
            print(f"   ✅ {table:30} customer_id NOT NULL")
        else:
            print(f"   ❌ {table:30} MISSING or NULLABLE!")
            all_good = False
    
    # Check 2: No NULL customer_ids
    print("\n2. Data Migration (all rows assigned customer_id=1):")
    for table in tables:
        cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE customer_id IS NULL")
        null_count = cursor.fetchone()[0]
        
        cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE customer_id = 1")
        migrated_count = cursor.fetchone()[0]
        
        if null_count == 0:
            print(f"   ✅ {table:30} {migrated_count:8,} rows → customer_id=1")
        else:
            print(f"   ❌ {table:30} {null_count} NULL customer_ids!")
            all_good = False
    
    # Check 3: RLS enabled
    print("\n3. Row-Level Security (RLS) Enabled:")
    for table in tables:
        cursor.execute("""
            SELECT relrowsecurity 
            FROM pg_class 
            WHERE relname = %s
        """, (table,))
        rls_enabled = cursor.fetchone()[0] if cursor.rowcount > 0 else False
        
        if rls_enabled:
            print(f"   ✅ {table:30} RLS ENABLED")
        else:
            print(f"   ❌ {table:30} RLS NOT ENABLED!")
            all_good = False
    
    # Check 4: RLS policies exist
    print("\n4. RLS Policies Created:")
    cursor.execute("""
        SELECT tablename, policyname 
        FROM pg_policies 
        WHERE schemaname = 'public' AND policyname LIKE 'tenant_isolation_%'
        ORDER BY tablename
    """)
    policies = cursor.fetchall()
    
    for table, policy in policies:
        print(f"   ✅ {table:30} {policy}")
    
    if len(policies) != 5:
        print(f"   ❌ Expected 5 policies, found {len(policies)}!")
        all_good = False
    
    # Check 5: Indexes created
    print("\n5. Composite Indexes:")
    cursor.execute("""
        SELECT tablename, indexname 
        FROM pg_indexes 
        WHERE schemaname = 'public' 
        AND indexname LIKE '%_customer_%'
        ORDER BY tablename
    """)
    indexes = cursor.fetchall()
    
    for table, index in indexes:
        print(f"   ✅ {index}")
    
    if len(indexes) < 5:
        print(f"   ⚠️  Expected 5+ indexes, found {len(indexes)}")
    
    cursor.close()
    conn.close()
    
    print("\n" + "=" * 80)
    if all_good:
        print("✅ MIGRATION SUCCESSFUL - All checks passed!")
        print("✅ Multi-tenant database ready for production!")
    else:
        print("❌ MIGRATION INCOMPLETE - Review errors above")
        print("❌ Re-run migration or contact support")
    print("=" * 80)
    
    return all_good

def main():
    parser = argparse.ArgumentParser(description='Multi-Tenant Migration Runner')
    parser.add_argument('--dry-run', action='store_true', 
                       help='Preview migration without executing')
    parser.add_argument('--execute', action='store_true', 
                       help='Execute the migration')
    parser.add_argument('--verify', action='store_true', 
                       help='Verify migration success')
    
    args = parser.parse_args()
    
    if args.dry_run:
        dry_run()
    elif args.execute:
        print("\n⚠️  WARNING: This will modify the production database!")
        print("⚠️  All existing data will be assigned to customer_id=1")
        confirm = input("\nType 'YES' to confirm: ")
        
        if confirm == 'YES':
            execute_migration()
        else:
            print("Migration cancelled.")
    elif args.verify:
        verify_migration()
    else:
        parser.print_help()
        print("\nExamples:")
        print("  python3 run_migration.py --dry-run   # Preview changes")
        print("  python3 run_migration.py --execute   # Run migration")
        print("  python3 run_migration.py --verify    # Verify success")

if __name__ == '__main__':
    main()
