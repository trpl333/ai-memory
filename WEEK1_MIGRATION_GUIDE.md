# Week 1: Multi-Tenant Database Migration Guide
**Phase 1 - Security-First MVP**  
**Target Server:** 209.38.143.71 (Production)  
**Service:** AI-Memory (Alice) - Port 8100  
**Database:** PostgreSQL - Port 5432

---

## 🎯 What This Migration Does

Transforms AI-Memory from single-tenant to multi-tenant SaaS:
- ✅ Adds `customer_id` to all 5 tables
- ✅ Migrates existing data to customer_id=1 (Peterson Insurance)
- ✅ Enables PostgreSQL Row-Level Security (RLS)
- ✅ Creates RLS policies for automatic tenant isolation
- ✅ Updates indexes and constraints for multi-tenancy

**Duration:** 5-30 seconds (depending on data volume)  
**Downtime:** None (database remains accessible)  
**Reversible:** Yes (backup recommended)

---

## 📋 Pre-Migration Checklist

### 1. **Backup Database** (CRITICAL)
```bash
# SSH to production server
ssh user@209.38.143.71

# Create backup
pg_dump -U postgres -d ai_memory > backup_pre_multi_tenant_$(date +%Y%m%d_%H%M%S).sql

# Verify backup created
ls -lh backup_*.sql
```

### 2. **Check Current State**
```bash
# Navigate to AI-Memory directory
cd /opt/ai-memory

# Run dry-run to preview changes
python3 run_migration.py --dry-run
```

**Expected Output:**
```
📊 CURRENT STATE:
  memories                       5,755 rows  ❌ Missing customer_id
  call_summaries                   123 rows  ❌ Missing customer_id
  caller_profiles                   45 rows  ❌ Missing customer_id
  personality_metrics               67 rows  ❌ Missing customer_id
  personality_averages              45 rows  ❌ Missing customer_id

📋 MIGRATION WILL:
  1. Add customer_id INTEGER column to all 5 tables
  2. Migrate existing data to customer_id=1 (Peterson Insurance)
  ...
```

### 3. **Verify Prerequisites**
```bash
# Check PostgreSQL is running
sudo systemctl status postgresql

# Check AI-Memory service is running
sudo systemctl status ai-memory  # or: ps aux | grep gunicorn

# Check DATABASE_URL is set
echo $DATABASE_URL
# Should output: postgresql://user:pass@localhost:5432/ai_memory
```

---

## 🚀 Migration Execution

### Step 1: Stop AI-Memory Service (Recommended)
```bash
# Stop the service to prevent write conflicts
sudo systemctl stop ai-memory

# Verify stopped
ps aux | grep gunicorn  # Should show no processes
```

### Step 2: Execute Migration
```bash
cd /opt/ai-memory

# Run migration
python3 run_migration.py --execute
```

**You will be prompted:**
```
⚠️  WARNING: This will modify the production database!
⚠️  All existing data will be assigned to customer_id=1

Type 'YES' to confirm:
```

**Type:** `YES` (must be uppercase)

**Expected Output:**
```
⏰ Starting migration at 2025-10-28 14:30:15
🚀 Executing migration SQL...
✅ Migration SQL executed successfully!

📊 VERIFICATION:
  ✅ memories                       customer_id: True  NULLs: 0  RLS: True
  ✅ call_summaries                 customer_id: True  NULLs: 0  RLS: True
  ✅ caller_profiles                customer_id: True  NULLs: 0  RLS: True
  ✅ personality_metrics            customer_id: True  NULLs: 0  RLS: True
  ✅ personality_averages           customer_id: True  NULLs: 0  RLS: True

  ✅ RLS Policies Created: 5/5

✅ Migration completed successfully!
```

### Step 3: Verify Migration
```bash
# Run verification
python3 run_migration.py --verify
```

**Expected Output:**
```
✅ MIGRATION SUCCESSFUL - All checks passed!
✅ Multi-tenant database ready for production!
```

### Step 4: Restart AI-Memory Service
```bash
# Start the service
sudo systemctl start ai-memory

# Check status
sudo systemctl status ai-memory

# Check logs for errors
sudo journalctl -u ai-memory -n 50 --no-pager
```

---

## 🧪 Testing Multi-Tenant Isolation

### Test 1: RLS Enforcement
```sql
-- SSH to server and open psql
psql -U postgres -d ai_memory

-- Set session to customer_id=1 (Peterson)
SET app.current_tenant = '1';

-- Query memories (should only see Peterson's data)
SELECT customer_id, COUNT(*) FROM memories GROUP BY customer_id;
-- Should show: customer_id=1, count=5755

-- Try to query without setting tenant (should fail)
RESET app.current_tenant;
SELECT COUNT(*) FROM memories;
-- Should return 0 rows (RLS blocks all access)
```

### Test 2: API Endpoint Testing
```bash
# Test memory storage endpoint (will need JWT in Week 2)
curl -X POST http://localhost:8100/memory/store \
  -H "Content-Type: application/json" \
  -d '{
    "customer_id": 1,
    "user_id": "+15551234567",
    "content": "Test memory for Peterson"
  }'

# Should succeed with customer_id=1
```

---

## 🐛 Troubleshooting

### Issue: "ERROR: column customer_id already exists"
**Cause:** Migration was partially run before  
**Fix:**
```bash
# Check which tables already have customer_id
psql -U postgres -d ai_memory -c "
  SELECT table_name 
  FROM information_schema.columns 
  WHERE column_name = 'customer_id' AND table_schema = 'public';
"

# Run verification to see what's missing
python3 run_migration.py --verify

# If needed, manually complete missing steps from migration SQL
```

### Issue: "ERROR: could not connect to database"
**Cause:** DATABASE_URL not set or PostgreSQL not running  
**Fix:**
```bash
# Check PostgreSQL status
sudo systemctl status postgresql

# Set DATABASE_URL (check .env file)
export DATABASE_URL="postgresql://username:password@localhost:5432/ai_memory"

# Or source .env
cd /opt/ai-memory
source .env
```

### Issue: Migration fails partway through
**Cause:** Syntax error or constraint violation  
**Fix:**
```bash
# Restore from backup
psql -U postgres -d ai_memory < backup_pre_multi_tenant_YYYYMMDD_HHMMSS.sql

# Review error message
# Fix issue in migration SQL
# Re-run migration
```

### Issue: RLS policies block all queries
**Cause:** Session variable not set  
**Fix:**
```python
# In Python code, always set session variable before queries:
db.session.execute("SET app.current_tenant = :tenant_id", {"tenant_id": customer_id})
```

---

## ✅ Success Criteria

**Migration is complete when:**

- [ ] All 5 tables have `customer_id` column (NOT NULL)
- [ ] All existing data assigned to customer_id=1 (Peterson)
- [ ] Zero NULL customer_ids in any table
- [ ] RLS enabled on all 5 tables
- [ ] 5 RLS policies created (tenant_isolation_*)
- [ ] Composite indexes created for performance
- [ ] AI-Memory service restarts without errors
- [ ] Test API calls work with customer_id=1
- [ ] Verification script passes all checks

---

## 📊 What Changed (Technical Details)

### Database Schema Changes

**Before:**
```sql
CREATE TABLE caller_profiles (
    id UUID PRIMARY KEY,
    user_id VARCHAR(255) UNIQUE NOT NULL,  -- ❌ Globally unique
    ...
);
```

**After:**
```sql
CREATE TABLE caller_profiles (
    id UUID PRIMARY KEY,
    customer_id INTEGER NOT NULL,          -- ✅ Tenant isolation
    user_id VARCHAR(255) NOT NULL,
    ...
    UNIQUE (customer_id, user_id)          -- ✅ Unique per tenant
);

ALTER TABLE caller_profiles ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_caller_profiles ON caller_profiles
  USING (customer_id = current_setting('app.current_tenant')::int);
```

### RLS Behavior

**Without RLS (DANGEROUS):**
```python
# Buggy code - forgets customer_id filter
profiles = db.query(CallerProfile).filter_by(user_id="+1555").all()
# Returns: Smith's data, Peterson's data, everyone's data! ❌
```

**With RLS (SAFE):**
```python
# Same buggy code, but RLS protects us
db.execute("SET app.current_tenant = '1'")
profiles = db.query(CallerProfile).filter_by(user_id="+1555").all()
# Returns: Only Peterson's data ✅
# PostgreSQL blocks cross-tenant access automatically
```

---

## 🔄 Rollback Procedure (If Needed)

### Option 1: Restore from Backup
```bash
# Drop current database
psql -U postgres -c "DROP DATABASE ai_memory;"

# Recreate database
psql -U postgres -c "CREATE DATABASE ai_memory;"

# Restore backup
psql -U postgres -d ai_memory < backup_pre_multi_tenant_YYYYMMDD_HHMMSS.sql

# Restart service
sudo systemctl restart ai-memory
```

### Option 2: Manual Rollback (Partial Migration)
```sql
-- Disable RLS
ALTER TABLE memories DISABLE ROW LEVEL SECURITY;
ALTER TABLE call_summaries DISABLE ROW LEVEL SECURITY;
ALTER TABLE caller_profiles DISABLE ROW LEVEL SECURITY;
ALTER TABLE personality_metrics DISABLE ROW LEVEL SECURITY;
ALTER TABLE personality_averages DISABLE ROW LEVEL SECURITY;

-- Drop policies
DROP POLICY IF EXISTS tenant_isolation_memories ON memories;
DROP POLICY IF EXISTS tenant_isolation_call_summaries ON call_summaries;
DROP POLICY IF EXISTS tenant_isolation_caller_profiles ON caller_profiles;
DROP POLICY IF EXISTS tenant_isolation_personality_metrics ON personality_metrics;
DROP POLICY IF EXISTS tenant_isolation_personality_averages ON personality_averages;

-- Note: Keep customer_id columns and data (they won't hurt)
```

---

## 📞 Next Steps After Migration

**Immediately after migration:**
1. ✅ Verify migration with `python3 run_migration.py --verify`
2. ✅ Test API endpoints work
3. ✅ Monitor logs for errors: `sudo journalctl -u ai-memory -f`
4. ✅ Test with Peterson Insurance calls (customer_id=1)

**Week 2 Work (after migration complete):**
1. Install PyJWT library
2. Implement JWT validation middleware
3. Update all API endpoints to extract customer_id from JWT
4. Coordinate with Chad on JWT secret key
5. Test end-to-end with JWT authentication

---

## 📝 Migration Execution Log Template

```
Migration Execution Log
Date: _____________________
Time Started: _____________________
Executed By: _____________________

Pre-Migration:
[ ] Database backup created: ____________________________
[ ] Dry-run completed successfully
[ ] Prerequisites verified

Migration:
[ ] AI-Memory service stopped
[ ] Migration executed: python3 run_migration.py --execute
[ ] Verification passed: python3 run_migration.py --verify
[ ] AI-Memory service restarted

Post-Migration Testing:
[ ] API endpoints respond correctly
[ ] Logs show no errors
[ ] Test call with Peterson Insurance successful

Issues Encountered: _____________________
_____________________
_____________________

Time Completed: _____________________
Status: [ ] SUCCESS  [ ] PARTIAL  [ ] FAILED
```

---

## 🆘 Support

**If migration fails or you encounter issues:**

1. **Don't Panic** - Database remains accessible
2. **Review Error Messages** - Check logs and migration output
3. **Restore from Backup** - If needed, restore the pre-migration backup
4. **Contact Support** - Share logs and error messages

**Files to share if requesting support:**
- Migration output (`run_migration.py --execute` output)
- Verification output (`run_migration.py --verify` output)
- AI-Memory logs (`sudo journalctl -u ai-memory -n 100`)
- PostgreSQL logs (`sudo tail -100 /var/log/postgresql/postgresql-*.log`)

---

**END OF MIGRATION GUIDE**

Ready to execute on production server 209.38.143.71! 🚀
