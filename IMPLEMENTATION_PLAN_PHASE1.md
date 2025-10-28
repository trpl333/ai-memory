# NeuroSphere AI - Phase 1 Implementation Plan
## Security-First MVP: Multi-Tenant Foundation

**Status:** APPROVED - Ready to Execute  
**Timeline:** 4 Weeks  
**Date:** October 28, 2025  
**Version:** 2.0 - Includes ChatGPT-5 Security Recommendations

---

## 🎯 Phase 1 Objectives

Transform AI-Memory (Alice) from single-tenant to production-ready multi-tenant service with:
- ✅ Database tenant isolation via `customer_id`
- ✅ PostgreSQL Row-Level Security (RLS) for automatic enforcement
- ✅ JWT authentication between Chad ↔ Alice
- ✅ Automated multi-tenant isolation tests
- ✅ Zero hardcoded company references

**ChatGPT-5 Verdict:** "80% production-ready" → **100% production-ready after Phase 1**

---

## 📅 Week-by-Week Breakdown

### **Week 1: Database Migration + RLS Policies**
**Owner:** Alice (AI-Memory)  
**Goal:** Add tenant isolation to database with automatic security enforcement

#### **Tasks:**

**1.1 Database Schema Changes**
- [ ] Add `customer_id INTEGER NOT NULL` to all 5 tables:
  - `memories`
  - `call_summaries`
  - `caller_profiles`
  - `personality_metrics`
  - `personality_averages`
- [ ] Add foreign key constraints: `FOREIGN KEY (customer_id) REFERENCES customers(id)`
- [ ] Add composite indexes: `CREATE INDEX idx_memories_customer_user ON memories(customer_id, user_id)`
- [ ] Update unique constraints on `caller_profiles`: `UNIQUE(customer_id, user_id)`

**1.2 Data Migration**
- [ ] Assign all existing data to `customer_id = 1` (Peterson Insurance)
- [ ] Verify migration: `SELECT COUNT(*) FROM memories WHERE customer_id = 1`
- [ ] Verify zero NULL customer_ids across all tables

**1.3 PostgreSQL Row-Level Security (NEW - ChatGPT-5 Recommendation)**
```sql
-- Enable RLS on all tables
ALTER TABLE memories ENABLE ROW LEVEL SECURITY;
ALTER TABLE call_summaries ENABLE ROW LEVEL SECURITY;
ALTER TABLE caller_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE personality_metrics ENABLE ROW LEVEL SECURITY;
ALTER TABLE personality_averages ENABLE ROW LEVEL SECURITY;

-- Create tenant isolation policies
CREATE POLICY tenant_isolation_memories ON memories
  USING (customer_id = current_setting('app.current_tenant')::int);

CREATE POLICY tenant_isolation_summaries ON call_summaries
  USING (customer_id = current_setting('app.current_tenant')::int);

CREATE POLICY tenant_isolation_profiles ON caller_profiles
  USING (customer_id = current_setting('app.current_tenant')::int);

CREATE POLICY tenant_isolation_metrics ON personality_metrics
  USING (customer_id = current_setting('app.current_tenant')::int);

CREATE POLICY tenant_isolation_averages ON personality_averages
  USING (customer_id = current_setting('app.current_tenant')::int);
```

**1.4 RLS Middleware (Python)**
- [ ] Install PyJWT: `pip install pyjwt`
- [ ] Create middleware to set session variable:
```python
# app/middleware/tenant_context.py
def set_tenant_context(db_session, customer_id: int):
    """Set PostgreSQL session variable for RLS enforcement."""
    db_session.execute(f"SET app.current_tenant = '{customer_id}'")
```

**1.5 Testing RLS**
- [ ] Test: Query without setting session variable → returns empty
- [ ] Test: Set customer_id=1 → returns Peterson data only
- [ ] Test: Set customer_id=2 → returns Smith data only
- [ ] Test: Buggy query (missing customer_id filter) → RLS blocks it

**Estimated Time:** 2 days (schema) + 0.5 day (RLS) + 1 day (testing) = 3.5 days

---

### **Week 2: JWT Authentication + API Updates**
**Owners:** Chad + Alice (Coordinated)  
**Goal:** Secure service-to-service communication with cryptographic verification

#### **Tasks:**

**2.1 JWT Secret Key Setup (Both)**
- [ ] Generate shared secret: `openssl rand -hex 32`
- [ ] Add to environment: `JWT_SECRET_KEY=<secret>` (both Chad & Alice)
- [ ] Document key rotation procedure

**2.2 Chad: JWT Token Generation**
- [ ] Install PyJWT: `pip install pyjwt`
- [ ] Create token generation function:
```python
# chad/utils/jwt_auth.py
import jwt
import os
from datetime import datetime, timedelta

def generate_alice_token(customer_id: int, scope: str = "read:memories write:memories"):
    """Generate JWT for Alice API calls."""
    payload = {
        "customer_id": customer_id,
        "scope": scope,
        "exp": datetime.utcnow() + timedelta(hours=1),
        "iat": datetime.utcnow()
    }
    return jwt.encode(payload, os.environ["JWT_SECRET_KEY"], algorithm="HS256")
```
- [ ] Update all Alice API calls to include Authorization header:
```python
# BEFORE
response = requests.get(f"{ai_memory_url}/v2/context/enriched",
    params={"user_id": phone})

# AFTER
token = generate_alice_token(customer_id)
response = requests.get(f"{ai_memory_url}/v2/context/enriched",
    headers={"Authorization": f"Bearer {token}"},
    params={"user_id": phone})
```

**2.3 Alice: JWT Validation Middleware**
- [ ] Create JWT validation middleware:
```python
# app/middleware/auth.py
from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
import os

security = HTTPBearer()

def validate_jwt(credentials: HTTPAuthorizationCredentials = Security(security)):
    """Validate JWT and extract customer_id."""
    try:
        token = credentials.credentials
        payload = jwt.decode(
            token,
            os.environ["JWT_SECRET_KEY"],
            algorithms=["HS256"]
        )
        return payload["customer_id"]
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
```
- [ ] Apply to all endpoints:
```python
@app.post("/v2/context/enriched")
def enriched_context(
    request: ContextRequest,
    customer_id: int = Depends(validate_jwt)
):
    # Set RLS session variable
    set_tenant_context(db.session, customer_id)
    # Now all queries automatically filtered by customer_id
    ...
```

**2.4 Update All Alice Endpoints**
- [ ] `/v1/memories/*` - Add JWT validation
- [ ] `/v2/context/enriched` - Add JWT validation
- [ ] `/v2/process-call` - Add JWT validation
- [ ] `/v2/summaries/*` - Add JWT validation
- [ ] `/v2/profile/*` - Add JWT validation
- [ ] Backward compatibility shims: `/memory/store`, `/memory/retrieve`

**2.5 Remove Hardcoded References**
- [ ] Chad: Remove "Peterson Insurance" from system prompts
- [ ] Chad: Remove hardcoded phone numbers from config
- [ ] Alice: Verify no company-specific logic in code

**Estimated Time:** Chad: 2 days | Alice: 3 days = 5 days total (parallel work)

---

### **Week 3: Multi-Tenant Testing**
**Owners:** Chad + Alice (Integrated Testing)  
**Goal:** Prove tenant isolation with automated tests

#### **Tasks:**

**3.1 Create Test Tenant #2**
- [ ] Chad: Create "Smith Insurance Agency" in customers table:
```sql
INSERT INTO customers (id, business_name, agent_name, greeting, voice_id)
VALUES (2, 'Smith Insurance Agency', 'Alex', 'Hi, this is Alex from Smith Insurance...', 'test_voice');
```
- [ ] Alice: Verify customer_id=2 is recognized

**3.2 Automated Isolation Tests (Alice)**
- [ ] Create test suite: `tests/test_tenant_isolation.py`
```python
def test_memory_isolation():
    """Verify Peterson cannot see Smith's memories."""
    # Store memory for Peterson (customer_id=1)
    store_memory(customer_id=1, user_id="+1111", content="Peterson data")
    
    # Store memory for Smith (customer_id=2)
    store_memory(customer_id=2, user_id="+1111", content="Smith data")
    
    # Query Peterson's memories
    peterson_mems = get_memories(customer_id=1, user_id="+1111")
    assert "Smith data" not in str(peterson_mems)
    
    # Query Smith's memories
    smith_mems = get_memories(customer_id=2, user_id="+1111")
    assert "Peterson data" not in str(smith_mems)

def test_rls_enforcement():
    """Verify RLS blocks buggy queries."""
    # Set session to customer_id=1
    set_tenant_context(db.session, 1)
    
    # Buggy query (missing customer_id filter)
    result = db.query(CallerProfile).filter_by(user_id="+1111").first()
    
    # RLS should only return Peterson's data (if exists) or None
    if result:
        assert result.customer_id == 1

def test_caller_profile_isolation():
    """Verify caller profiles isolated by tenant."""
    # Same phone number, different tenants
    create_profile(customer_id=1, user_id="+1555", name="John Peterson")
    create_profile(customer_id=2, user_id="+1555", name="John Smith")
    
    # Peterson sees only their John
    p_profile = get_profile(customer_id=1, user_id="+1555")
    assert p_profile.name == "John Peterson"
    
    # Smith sees only their John
    s_profile = get_profile(customer_id=2, user_id="+1555")
    assert s_profile.name == "John Smith"
```

**3.3 End-to-End Integration Tests (Chad)**
- [ ] Simulate call to Peterson's number → verify uses customer_id=1
- [ ] Simulate call to Smith's number → verify uses customer_id=2
- [ ] Run parallel calls (Peterson + Smith simultaneously)
- [ ] Verify JWT tokens contain correct customer_id
- [ ] Verify context retrieval returns correct tenant data

**3.4 Load Testing**
- [ ] Simulate 10 tenants calling simultaneously
- [ ] Verify no cross-tenant data leakage
- [ ] Monitor database performance (connection pooling)
- [ ] Check JWT validation latency

**3.5 Security Penetration Testing**
- [ ] Try to spoof customer_id in request body → JWT should reject
- [ ] Try to access customer_id=2 data with customer_id=1 token → blocked
- [ ] Try SQL injection with customer_id parameter → sanitized
- [ ] Verify RLS cannot be bypassed

**Estimated Time:** 4 days (test writing + execution + bug fixes)

---

### **Week 4: Documentation & Hardening**
**Owners:** Chad + Alice (Collaborative)  
**Goal:** Production-ready documentation and final validation

#### **Tasks:**

**4.1 Update Technical Documentation**
- [ ] Update `MULTI_PROJECT_ARCHITECTURE.md` v2.0:
  - Document RLS policies
  - Document JWT flow (Chad → Alice)
  - Update API contracts with Authorization headers
  - Add security architecture section
- [ ] Update `CHATSTACK_MIGRATION_GUIDE.md`:
  - Include JWT token usage
  - Document customer_id in all V2 endpoints
- [ ] Update `replit.md`:
  - Add Phase 1 completion date
  - Document RLS + JWT security layers

**4.2 Create Operational Documentation**
- [ ] Create `CUSTOMER_ONBOARDING_GUIDE.md`:
  - Step 1: Create customer in database
  - Step 2: Assign Twilio number
  - Step 3: Configure industry template
  - Step 4: Test call flow
  - Step 5: Go-live checklist
- [ ] Create `SECURITY_RUNBOOK.md`:
  - JWT secret rotation procedure
  - RLS policy audit process
  - Tenant isolation verification steps
  - Incident response for data leakage

**4.3 Final Validation**
- [ ] Run full test suite (Peterson + Smith)
- [ ] Verify all API endpoints require JWT
- [ ] Verify all database queries filtered by customer_id
- [ ] Check for any remaining hardcoded references
- [ ] Verify RLS policies active on all tables
- [ ] Code review: Search for potential tenant leakage points

**4.4 Prepare for Phase 2**
- [ ] Document monitoring requirements (Prometheus/Grafana)
- [ ] Document rate limiting strategy
- [ ] Document GDPR compliance needs
- [ ] Create Phase 2 implementation plan

**Estimated Time:** 3 days (documentation) + 2 days (validation) = 5 days

---

## 🔐 Security Checklist (ChatGPT-5 Requirements)

**Before declaring Phase 1 complete, verify:**

- [ ] ✅ Every table has `customer_id` column
- [ ] ✅ PostgreSQL RLS enabled on all tables
- [ ] ✅ RLS policies prevent cross-tenant queries
- [ ] ✅ JWT authentication active on all endpoints
- [ ] ✅ JWT tokens validated and customer_id extracted
- [ ] ✅ Session variable set for RLS enforcement
- [ ] ✅ Automated tests prove tenant isolation
- [ ] ✅ Load testing shows no performance degradation
- [ ] ✅ Penetration testing shows no security gaps
- [ ] ✅ Zero hardcoded company references
- [ ] ✅ Documentation updated and accurate

---

## 🔄 Alice ↔ Chad Coordination Points

### **Week 1: Minimal Coordination**
- Alice works independently on database
- Chad monitors progress, no code changes yet

### **Week 2: Heavy Coordination**
- **Sync Point 1 (Day 1):** Share JWT secret key
- **Sync Point 2 (Day 3):** Test first JWT call end-to-end
- **Sync Point 3 (Day 5):** Verify all endpoints migrated

### **Week 3: Integrated Testing**
- **Daily standups:** Review test results
- **Pair debugging:** Fix cross-tenant issues together
- **Load testing:** Run simultaneous simulations

### **Week 4: Documentation**
- **Joint reviews:** Both approve all documentation
- **Final validation:** Both sign off on security checklist

---

## 📊 Success Metrics

**We know Phase 1 is complete when:**

1. ✅ Two tenants (Peterson + Smith) can operate simultaneously
2. ✅ Automated tests prove zero data leakage
3. ✅ JWT authentication prevents tenant spoofing
4. ✅ RLS policies automatically enforce isolation
5. ✅ No hardcoded company names anywhere in code
6. ✅ New customer can be onboarded in <30 minutes
7. ✅ All ChatGPT-5 critical recommendations implemented
8. ✅ Documentation is complete and accurate

---

## 🚀 Phase 2 Preview (Weeks 5-6)

**Deferred from Phase 1 but planned for Phase 2:**

- Monitoring & Alerting (Prometheus/Grafana)
- Per-tenant rate limiting
- Usage metrics for billing
- GDPR export/delete endpoints
- Automated backup per tenant
- Containerization (Docker)
- Secondary server redundancy

---

## ⚠️ Risk Mitigation

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| RLS breaks existing queries | Medium | High | Test extensively in Week 1, rollback plan ready |
| JWT adds latency | Low | Medium | Benchmark in Week 2, optimize if >50ms overhead |
| Cross-tenant test fails | Medium | Critical | Fix immediately, block Phase 1 completion |
| Timeline slips | Low | Medium | Weekly checkpoints, adjust scope if needed |

---

## 📋 Daily Checklist Template

**Each day, both Chad & Alice should:**

- [ ] Update task completion status
- [ ] Document any blockers
- [ ] Communicate progress to user
- [ ] Test recent changes
- [ ] Commit code to version control

---

## ✅ Approval & Kickoff

**Approved by:**
- [ ] User (Product Owner)
- [ ] Chad (ChatStack)
- [ ] Alice (AI-Memory)
- [ ] ChatGPT-5 (Architecture Review) ✅

**Kickoff Date:** _____________

**Target Completion:** 4 weeks from kickoff

---

**END OF PHASE 1 IMPLEMENTATION PLAN**

Ready to execute on approval! 🚀
