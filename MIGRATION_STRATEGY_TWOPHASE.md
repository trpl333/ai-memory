# Two-Phase Migration Strategy
## Safe Multi-Tenant Deployment Without Downtime

**Problem Solved:** Original migration would break production by requiring `customer_id NOT NULL` before code is updated.  
**Solution:** Split migration into two phases with backward compatibility.

---

## 📋 Phase A: Database Schema (Safe - Non-Breaking)

**When:** Week 1 - Immediately  
**Risk:** LOW - Fully backward compatible  
**Downtime:** None

### What Phase A Does:
1. Adds `customer_id INTEGER DEFAULT 1` to all tables
2. Migrates existing data to customer_id=1 (Peterson)
3. Enables RLS + **FORCE RLS** (prevents owner bypass)
4. Creates RLS policies for tenant isolation
5. Adds composite indexes

### Why Safe:
- **DEFAULT 1** allows existing code to keep writing without errors
- Old API endpoints continue working (writes get customer_id=1 automatically)
- RLS policies created but don't break anything (permissive with default)
- No production impact

### Execute Phase A:
```bash
# On production server 209.38.143.71
cd /opt/ai-memory

# Run Phase A migration
python3 run_migration.py --execute-phase-a

# Verify
python3 run_migration.py --verify-phase-a
```

---

## 📋 Phase B: Remove DEFAULT + Enforce NOT NULL

**When:** Week 2 - AFTER API code deployed with JWT  
**Risk:** MEDIUM - Breaks old code  
**Downtime:** None (if code deployed first)

### What Phase B Does:
1. Removes `DEFAULT 1` from all customer_id columns
2. Sets `customer_id NOT NULL` (enforces data integrity)
3. Requires all writes to explicitly provide customer_id

### Prerequisites (MUST complete before Phase B):
- ✅ Week 2 JWT authentication deployed
- ✅ All API endpoints updated to extract customer_id from JWT
- ✅ Tested with Peterson Insurance (customer_id=1)
- ✅ No errors in production logs for 24 hours

### Execute Phase B:
```bash
# ONLY after Week 2 code deployed!
cd /opt/ai-memory

# Run Phase B migration
python3 run_migration.py --execute-phase-b

# Verify
python3 run_migration.py --verify-phase-b
```

---

## 🔄 Timeline

```
Week 1                     Week 2                     Week 3
├─────────────────────────┼─────────────────────────┼───────────
│ Phase A Migration       │ Deploy JWT Code         │ Testing
│ (Safe + RLS)            │ (24hr monitoring)       │
│                         │ Phase B Migration        │
│                         │ (Remove DEFAULT)         │
└─────────────────────────┴─────────────────────────┴───────────

Phase A: Database ready with DEFAULT 1 (backward compatible)
  ↓
Week 2: Deploy JWT-enabled API code
  ↓ (wait 24 hours, monitor logs)
Phase B: Remove DEFAULT, enforce NOT NULL
  ↓
Week 3: Full multi-tenant testing
```

---

## 🔐 Security Enhancements (Architect Fixes)

### Fix #1: Force RLS for Owner Role
```sql
-- BEFORE (VULNERABLE):
ALTER TABLE memories ENABLE ROW LEVEL SECURITY;

-- AFTER (SECURE):
ALTER TABLE memories ENABLE ROW LEVEL SECURITY;
ALTER TABLE memories FORCE ROW LEVEL SECURITY;  -- ← Prevents owner bypass
```

**Impact:** Without `FORCE`, database owner role bypasses RLS policies entirely!

### Fix #2: Backward Compatible DEFAULT
```sql
-- BEFORE (BREAKS PRODUCTION):
ALTER TABLE memories ADD COLUMN customer_id INTEGER;
-- Old code writes fail: "customer_id cannot be null"

-- AFTER (SAFE):
ALTER TABLE memories ADD COLUMN customer_id INTEGER DEFAULT 1;
-- Old code writes succeed: customer_id automatically = 1
```

**Impact:** Production continues working during migration window.

### Fix #3: Request Lifecycle Integration
```python
# BEFORE (INCOMPLETE):
# Middleware existed but wasn't wired into requests

# AFTER (COMPLETE):
@app.get("/caller/profile/{user_id}")
def get_profile(
    user_id: str,
    db: Session = Depends(get_tenant_session)  # ← Auto-sets tenant context
):
    # Session variable already set
    # RLS automatically filters queries
    profile = db.query(CallerProfile).filter_by(user_id=user_id).first()
    return profile
```

**Impact:** Tenant context guaranteed set on every request, cleared after (no leakage).

---

## ✅ Phase A Verification Checklist

**Before Phase B, verify all of these:**

- [ ] Phase A migration completed successfully
- [ ] All 5 tables have `customer_id` column with DEFAULT 1
- [ ] RLS enabled AND **FORCED** on all 5 tables
- [ ] 5 RLS policies created (tenant_isolation_*)
- [ ] Existing data assigned to customer_id=1 (Peterson)
- [ ] Zero NULL customer_ids in any table
- [ ] Composite indexes created
- [ ] Production service restarted and running
- [ ] API endpoints respond normally (200 OK)
- [ ] Test call with Peterson works
- [ ] No errors in logs for 1 hour

---

## 🚨 Rollback Procedures

### Rollback Phase A (if problems during Week 1):
```sql
-- Remove customer_id columns
ALTER TABLE memories DROP COLUMN IF EXISTS customer_id;
ALTER TABLE call_summaries DROP COLUMN IF EXISTS customer_id;
ALTER TABLE caller_profiles DROP COLUMN IF EXISTS customer_id;
ALTER TABLE personality_metrics DROP COLUMN IF EXISTS customer_id;
ALTER TABLE personality_averages DROP COLUMN IF EXISTS customer_id;

-- Disable RLS
ALTER TABLE memories DISABLE ROW LEVEL SECURITY;
ALTER TABLE call_summaries DISABLE ROW LEVEL SECURITY;
ALTER TABLE caller_profiles DISABLE ROW LEVEL SECURITY;
ALTER TABLE personality_metrics DISABLE ROW LEVEL SECURITY;
ALTER TABLE personality_averages DISABLE ROW LEVEL SECURITY;
```

### Rollback Phase B (if problems during Week 2):
```sql
-- Re-add DEFAULT 1 (makes old code work again)
ALTER TABLE memories ALTER COLUMN customer_id SET DEFAULT 1;
ALTER TABLE call_summaries ALTER COLUMN customer_id SET DEFAULT 1;
ALTER TABLE caller_profiles ALTER COLUMN customer_id SET DEFAULT 1;
ALTER TABLE personality_metrics ALTER COLUMN customer_id SET DEFAULT 1;
ALTER TABLE personality_averages ALTER COLUMN customer_id SET DEFAULT 1;

-- Make nullable (removes NOT NULL constraint)
ALTER TABLE memories ALTER COLUMN customer_id DROP NOT NULL;
ALTER TABLE call_summaries ALTER COLUMN customer_id DROP NOT NULL;
ALTER TABLE caller_profiles ALTER COLUMN customer_id DROP NOT NULL;
ALTER TABLE personality_metrics ALTER COLUMN customer_id DROP NOT NULL;
ALTER TABLE personality_averages ALTER COLUMN customer_id DROP NOT NULL;
```

---

## 📊 Comparison: Original vs Two-Phase

| Aspect | Original (Broken) | Two-Phase (Fixed) |
|--------|-------------------|-------------------|
| **Safety** | Breaks production | Backward compatible |
| **RLS Security** | Owner bypass | Forced for all roles |
| **Deployment** | Must stop service | Zero downtime |
| **Rollback** | Complex | Simple (per phase) |
| **Testing Window** | None | 1 week between phases |
| **Risk** | HIGH | LOW → MEDIUM |

---

## 🎯 Success Criteria

**Phase A Complete When:**
- ✅ Migration executed without errors
- ✅ RLS policies enforced (including owner)
- ✅ Production traffic unaffected
- ✅ All writes default to customer_id=1

**Phase B Complete When:**
- ✅ DEFAULT removed, NOT NULL enforced
- ✅ All writes provide explicit customer_id from JWT
- ✅ No NULL customer_ids anywhere
- ✅ Cross-tenant isolation verified

---

**END OF MIGRATION STRATEGY**

Use this two-phase approach for safe, zero-downtime multi-tenant migration! 🚀
