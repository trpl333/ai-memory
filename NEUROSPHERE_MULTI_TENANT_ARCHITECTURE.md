# NeuroSphere AI - Multi-Tenant SaaS Architecture Plan
**Status:** DESIGN PHASE - No Code Written Yet  
**Purpose:** ChatGPT-5 Review & Alignment Document  
**Date:** October 28, 2025  
**Version:** 1.0 - Initial Architecture Design

---

## 🎯 Executive Summary

**Product:** NeuroSphere AI - White-label AI phone system for ANY industry  
**Business Model:** SaaS platform that companies can buy and customize  
**Test Client:** Peterson Insurance Company (The Insurance Doctors) - customer_id = 1  
**Goal:** Build once, sell many times (Smith Agency, Jones Real Estate, etc.)

**Critical Requirement:** ZERO hardcoded company data. All company-specific information configured via admin panel or database.

---

## 🏗️ System Components & Server Locations

### **Production Environment**
**Server:** DigitalOcean Droplet - 209.38.143.71  
**Operating System:** Ubuntu Linux

| Service | Port | Location on Server | Purpose | Status |
|---------|------|-------------------|---------|--------|
| **ChatStack (Flask)** | 5000 | `/opt/ChatStack/` | Admin UI, Twilio webhooks | ✅ Multi-tenant ready |
| **ChatStack (FastAPI)** | 8001 | `/opt/ChatStack/app/` | Phone call orchestrator | ✅ Multi-tenant ready |
| **AI-Memory (Alice)** | 8100 | `/opt/ai-memory/` | Memory storage service | ❌ Needs refactoring |
| **NeuroSphere Send Text** | 3000 | `/root/neurosphere_send_text/` | SMS notifications | ⚠️ Status unknown |
| **PostgreSQL** | 5432 | System service | All databases | ⚠️ Needs tenant isolation |
| **Nginx** | 80/443 | System service | Reverse proxy, SSL | ✅ Working |

**⚠️ CRITICAL:** These services share ONE server but must maintain data isolation per customer (tenant).

---

## 🔑 Multi-Tenant Architecture Decisions

### **Decision 1: Deployment Model**
**Choice:** Start with **SaaS Multi-Tenant**, plan for **Hybrid** later

**Phase 1 (MVP - Now to Q2 2026):**
- All customers share 209.38.143.71
- Data isolated by `customer_id` column in database
- Cheaper to operate, faster to onboard new customers
- Target: First 5-10 customers

**Phase 2 (Growth - Q3 2026+):**
- Small customers: Shared SaaS (current model)
- Enterprise customers: Dedicated server instances
- Same codebase, different deployments

**Technical Implementation:**
- Database: PostgreSQL with `customer_id` in ALL tables
- Row-level security to prevent cross-tenant queries
- Each service checks `customer_id` on every API call

---

### **Decision 2: Admin Panel Architecture**
**Choice:** Two-tier admin system

**Tier 1: Platform Admin** (NeuroSphere team - you/John)
- URL: `/platform/admin` (to be built)
- Access: Master login
- Functions:
  - Create new customer accounts
  - Assign industry templates
  - View all customers' system health
  - Manage billing/subscriptions
  - Provision Twilio numbers

**Tier 2: Tenant Admin** (Each customer's staff)
- URL: `/customer/{customer_id}/admin`
- Access: Customer-specific login (isolated)
- Functions:
  - Customize AI personality/greeting
  - View their call logs only
  - Manage their caller profiles
  - Configure voice settings
  - View their usage statistics

**Current Status:**
- Chad (ChatStack): Has `/admin.html` but NOT multi-tenant aware yet
- Alice (AI-Memory): No admin panel, only APIs

**Build Priority:** Tenant Admin FIRST (this is the product we sell)

---

### **Decision 3: API Key Management**
**Choice:** Hybrid approach

**For MVP (First 5 customers):**
- NeuroSphere provisions: Twilio sub-accounts, OpenAI API keys
- Customers pay us monthly (we bill them)
- Simpler onboarding, we control quality

**For Scale (10+ customers):**
- Enterprise option: BYOK (Bring Your Own Keys)
- Customers provide their own Twilio/OpenAI accounts
- Lower our operational costs
- Better for customers who want full control

**Data Model:**
```
customers table:
  - twilio_phone_number (we provision)
  - byok_twilio_sid (NULL for standard, filled for BYOK)
  - byok_twilio_token (encrypted)
  - byok_openai_key (encrypted)
```

---

### **Decision 4: Industry Templates**
**Choice:** Insurance + Real Estate for MVP

**Template 1: Insurance Agency**
- Fields: Name, Phone, Email, Address
- Policies: Auto 1, Auto 2, Home Policy, Life Insurance
- Family: Spouse Name, Children Names, Birthdays
- Quick Bio Format: "John Smith | Orange County | Client since 2020 | 2 Auto + 1 Home"
- Customer: Peterson Insurance (live test)

**Template 2: Real Estate Agency**
- Fields: Name, Phone, Email
- Status: Buyer or Seller
- Properties: Property 1, Property 2 (address, price)
- Financing: Pre-approved, Max Budget
- Quick Bio Format: "Jane Doe | Buyer | $500K budget | Pre-approved"
- Customer: TBD (need to find test client)

**Future Templates:** Mortgage, Medical/Dental, Law Offices (Phase 2)

---

### **Decision 5: Documentation Structure**
**Choice:** Split into 3 separate documents

**Doc 1: MULTI_PROJECT_ARCHITECTURE.md v2.0** (Technical)
- Audience: Developers
- Contents:
  - Service details (ports, endpoints, locations)
  - Database schemas with `customer_id`
  - API contracts between services
  - Authentication/authorization flows
  - Deployment procedures
  - Security model

**Doc 2: CUSTOMER_ONBOARDING_GUIDE.md** (Operational)
- Audience: NeuroSphere sales/support team
- Contents:
  - Step-by-step: How to onboard "Smith Agency"
  - Provisioning checklist (Twilio, database, config)
  - Testing verification steps
  - Go-live process
  - Troubleshooting common issues

**Doc 3: TENANT_ADMIN_GUIDE.md** (User-facing)
- Audience: Customers (their staff)
- Contents:
  - How to login to admin panel
  - How to customize AI personality
  - How to view call logs
  - How to manage team members
  - FAQ / common questions

---

## 🔄 Data Flow: Multi-Tenant Call Handling

### **Scenario:** Customer "Peterson Insurance" receives a call

```
1. INCOMING CALL
   Twilio → 209.38.143.71:5000 (Chad Flask)
   Caller: +15551234567
   To: +18001234567 (Peterson's business number)

2. CUSTOMER LOOKUP (Chad)
   Chad queries: SELECT id FROM customers WHERE twilio_phone_number = '+18001234567'
   Result: customer_id = 1 (Peterson Insurance)
   
3. CONTEXT RETRIEVAL (Chad → Alice)
   POST http://209.38.143.71:8100/v2/context/enriched
   {
     "customer_id": 1,              ← CRITICAL: Tenant isolation
     "user_id": "+15551234567"
   }
   
4. ALICE PROCESSES (Alice internal)
   Query: SELECT * FROM caller_profiles 
          WHERE customer_id = 1 AND user_id = '+15551234567'
   
   Returns: Quick Bio + Recent Summaries (ONLY Peterson's data)
   
5. AI RESPONSE (Chad)
   Chad builds system prompt with caller context
   OpenAI generates response
   ElevenLabs speaks to caller
   
6. CALL ENDS - SUMMARIZATION (Chad → Alice)
   POST http://209.38.143.71:8100/v2/process-call
   {
     "customer_id": 1,              ← CRITICAL: Stores with tenant_id
     "user_id": "+15551234567",
     "thread_id": "customer_1_user_15551234567",
     "conversation_history": [...]
   }
   
7. ALICE STORES (Alice internal)
   - Generate AI summary
   - Extract key topics/variables
   - Analyze personality
   - Store in: call_summaries (customer_id=1), caller_profiles (customer_id=1)
```

### **Critical Security Check:**
- If customer_id = 2 (Smith Agency) calls, they get ZERO access to customer_id = 1 data
- Every database query MUST filter by `customer_id`
- Missing `customer_id` = Error (fail closed, not open)

---

## 📊 Database Architecture - Alice (AI-Memory) Refactoring

### **Current State (BROKEN - No Tenant Isolation)**

```sql
-- CURRENT - INSECURE
CREATE TABLE memories (
    id UUID PRIMARY KEY,
    user_id TEXT NOT NULL,              -- ❌ No customer_id
    content TEXT,
    created_at TIMESTAMP
);

-- PROBLEM: All customers' memories mixed together!
-- Query for +15551234567 returns Peterson AND Smith data
```

### **Target State (SECURE - Multi-Tenant)**

```sql
-- TARGET - TENANT ISOLATED
CREATE TABLE memories (
    id UUID PRIMARY KEY,
    customer_id INTEGER NOT NULL,       -- ✅ Tenant isolation
    user_id TEXT NOT NULL,
    content TEXT,
    created_at TIMESTAMP,
    
    FOREIGN KEY (customer_id) REFERENCES customers(id),
    INDEX idx_customer_user (customer_id, user_id)
);

-- SECURE: Must provide BOTH customer_id AND user_id
-- Query: WHERE customer_id = 1 AND user_id = '+15551234567'
```

### **Tables Requiring Refactoring (Alice)**

| Table | Status | Changes Needed |
|-------|--------|----------------|
| `memories` | ❌ Broken | Add `customer_id INTEGER NOT NULL` |
| `call_summaries` | ❌ Broken | Add `customer_id INTEGER NOT NULL` |
| `caller_profiles` | ❌ Broken | Add `customer_id INTEGER NOT NULL`, UNIQUE(customer_id, user_id) |
| `personality_metrics` | ❌ Broken | Add `customer_id INTEGER NOT NULL` |
| `personality_averages` | ❌ Broken | Add `customer_id INTEGER NOT NULL` |

### **Migration Strategy**
**Approach:** Assign all existing data to `customer_id = 1` (Peterson Insurance)

**Reasoning:**
- All current data IS Peterson Insurance (our test client)
- Preserves 5,755+ existing memories
- No data loss

**SQL Migration:**
```sql
-- Step 1: Add columns (nullable first)
ALTER TABLE memories ADD COLUMN customer_id INTEGER;
ALTER TABLE call_summaries ADD COLUMN customer_id INTEGER;
ALTER TABLE caller_profiles ADD COLUMN customer_id INTEGER;
ALTER TABLE personality_metrics ADD COLUMN customer_id INTEGER;
ALTER TABLE personality_averages ADD COLUMN customer_id INTEGER;

-- Step 2: Populate with Peterson Insurance ID
UPDATE memories SET customer_id = 1 WHERE customer_id IS NULL;
UPDATE call_summaries SET customer_id = 1 WHERE customer_id IS NULL;
UPDATE caller_profiles SET customer_id = 1 WHERE customer_id IS NULL;
UPDATE personality_metrics SET customer_id = 1 WHERE customer_id IS NULL;
UPDATE personality_averages SET customer_id = 1 WHERE customer_id IS NULL;

-- Step 3: Make NOT NULL
ALTER TABLE memories ALTER COLUMN customer_id SET NOT NULL;
ALTER TABLE call_summaries ALTER COLUMN customer_id SET NOT NULL;
ALTER TABLE caller_profiles ALTER COLUMN customer_id SET NOT NULL;
ALTER TABLE personality_metrics ALTER COLUMN customer_id SET NOT NULL;
ALTER TABLE personality_averages ALTER COLUMN customer_id SET NOT NULL;

-- Step 4: Add indexes for performance
CREATE INDEX idx_memories_customer_user ON memories(customer_id, user_id);
CREATE INDEX idx_summaries_customer ON call_summaries(customer_id);
CREATE INDEX idx_profiles_customer ON caller_profiles(customer_id);
```

---

## 🔌 API Contract Changes - Alice Endpoints

### **Backward Compatibility Endpoints (Legacy - NEEDS FIX)**

**Current (INSECURE):**
```http
POST /memory/store
{
  "user_id": "+15551234567",
  "content": "John called about policy"
}
```

**Fixed (SECURE):**
```http
POST /memory/store
{
  "customer_id": 1,                    # ← REQUIRED
  "user_id": "+15551234567",
  "content": "John called about policy"
}

Response:
{
  "success": true,
  "id": "uuid",
  "error": null
}

Error if missing customer_id:
{
  "success": false,
  "error": "customer_id is required for multi-tenant security"
}
```

### **V1 API Endpoints (NEEDS FIX)**

All `/v1/memories/*` endpoints must require `customer_id`:

```http
GET /v1/memories/user/{user_id}?customer_id=1
POST /v1/memories {"customer_id": 1, ...}
DELETE /v1/memories/{id}?customer_id=1
```

### **V2 API Endpoints (NEEDS FIX)**

All `/v2/*` endpoints must require `customer_id`:

```http
POST /v2/context/enriched
{
  "customer_id": 1,
  "user_id": "+15551234567"
}

POST /v2/process-call
{
  "customer_id": 1,
  "user_id": "+15551234567",
  "thread_id": "customer_1_user_15551234567",
  "conversation_history": [...]
}

GET /v2/summaries/{user_id}?customer_id=1
GET /v2/profile/{user_id}?customer_id=1
GET /v2/personality/{user_id}?customer_id=1
```

---

## 🔐 Security Model

### **Authentication Flow**

```
1. Twilio receives call to +18001234567
2. Twilio webhooks to: https://209.38.143.71/call/incoming
3. Chad authenticates Twilio request (validates signature)
4. Chad looks up customer_id from phone number
5. Chad calls Alice with customer_id in request
6. Alice validates customer_id exists in database
7. Alice returns ONLY data for that customer_id
```

### **Authorization Checks**

**Every Alice API call:**
1. Require `customer_id` parameter
2. Validate `customer_id` exists in customers table
3. Filter ALL database queries by `customer_id`
4. Never return data from other customers

**Database Row-Level Security:**
```sql
-- Example query pattern (ALWAYS use this)
SELECT * FROM caller_profiles
WHERE customer_id = %s AND user_id = %s
LIMIT 1;

-- NEVER do this (security vulnerability)
SELECT * FROM caller_profiles
WHERE user_id = %s;  -- ❌ Returns data from ALL customers
```

---

## 📋 Chad's Current Multi-Tenant Status

### **✅ What Chad Already Has (Good News!)**

**Database:**
```python
# customer_models.py
class Customer(Base):
    id = Column(Integer, primary_key=True)        # customer_id
    business_name = Column(String)                # "Peterson Insurance"
    agent_name = Column(String)                   # "Samantha"
    greeting = Column(Text)                       # Custom greeting
    voice_id = Column(String)                     # ElevenLabs voice
    personality = Column(Text)                    # AI instructions
    twilio_phone_number = Column(String)          # Their business number
```

**Customer Lookup:**
```python
# Chad can identify customer by incoming Twilio number
customer = session.query(Customer).filter_by(
    twilio_phone_number=request.form['To']
).first()

customer_id = customer.id  # ← Chad knows which customer this is!
```

**Thread Namespacing:**
```python
# Chad creates isolated thread IDs
thread_id = f"customer_{customer_id}_user_{phone}"
# Example: "customer_1_user_9495565377"
```

### **❌ What Chad Needs to Fix**

**1. Send customer_id to Alice**
```python
# CURRENT - Missing customer_id
response = requests.get(
    f"{ai_memory_url}/v1/memories",
    params={"user_id": phone, "limit": 500}
)

# FIXED - Include customer_id
response = requests.get(
    f"{ai_memory_url}/v1/memories",
    params={
        "customer_id": customer_id,  # ← Add this
        "user_id": phone,
        "limit": 500
    }
)
```

**2. Remove Hardcoded References**
- System prompts: Remove "Peterson Family Insurance"
- Config files: No hardcoded phone numbers
- Test data: Use generic examples

**3. Admin Panel - Add Tenant Scoping**
- Current `/admin.html` shows global settings
- Need: `/customer/{customer_id}/admin` (scoped to one customer)

---

## 🎯 Implementation Roadmap

### **Phase 1: Documentation & Schema Design** (Week 1)
**Alice & Chad collaborate:**
- [ ] Update MULTI_PROJECT_ARCHITECTURE.md v2.0 (technical)
- [ ] Define database schema changes (all tables with customer_id)
- [ ] Document API contracts (what Chad sends to Alice)
- [ ] Create industry templates (Insurance + Real Estate)
- [ ] Send to ChatGPT-5 for architecture review

### **Phase 2: Alice Refactoring** (Week 2)
**Alice (AI-Memory) changes:**
- [ ] Run database migration SQL (add customer_id columns)
- [ ] Update all API endpoints to require customer_id
- [ ] Add customer_id validation on every query
- [ ] Update backward compatibility shims
- [ ] Create industry template storage system
- [ ] Write unit tests for tenant isolation

### **Phase 3: Chad Integration** (Week 3)
**Chad (ChatStack) changes:**
- [ ] Update all API calls to Alice to include customer_id
- [ ] Remove hardcoded company references
- [ ] Build tenant admin UI (/customer/{id}/admin)
- [ ] Test with customer_id = 1 (Peterson)
- [ ] Create customer_id = 2 (Test - "Smith Agency")

### **Phase 4: Testing & Validation** (Week 4)
**Both services:**
- [ ] Create Test Tenant #2 ("Smith Insurance Agency")
- [ ] Run parallel calls (Peterson + Smith simultaneously)
- [ ] Verify zero data leakage between tenants
- [ ] Load testing (simulate 5 customers calling at once)
- [ ] Write CUSTOMER_ONBOARDING_GUIDE.md
- [ ] Write TENANT_ADMIN_GUIDE.md

---

## ❓ Questions for ChatGPT-5 Review

We need ChatGPT-5 to review this architecture and answer:

### **1. Multi-Tenant Security**
- Is our `customer_id` filtering approach secure?
- Are there edge cases where data could leak between tenants?
- Should we add additional security layers (encryption, audit logs)?

### **2. Database Design**
- Is adding `customer_id` to existing tables the right approach?
- Should we use separate schemas per tenant instead? (e.g., `customer_1.memories`)
- What about performance with 100+ customers?

### **3. API Design**
- Should `customer_id` be in query params, request body, or HTTP headers?
- Should we use JWT tokens with embedded customer_id instead?
- How to handle API authentication between Chad and Alice?

### **4. Scalability**
- Current plan: All customers on one server (209.38.143.71)
- At what point do we need to split to multiple servers?
- Database connection pooling strategy for multi-tenant?

### **5. Industry Templates**
- Is our JSON-based template approach flexible enough?
- How do we handle template versioning (insurance_v1 → insurance_v2)?
- Should templates be in database or code?

### **6. Admin Panel Architecture**
- Is two-tier admin (Platform + Tenant) the right split?
- Should we build separate apps or one app with role-based access?
- How to handle super-admin access for debugging customer issues?

### **7. Deployment Strategy**
- Current: Manual deployment via SSH to 209.38.143.71
- Recommended: CI/CD pipeline, blue-green deployments?
- How to deploy updates without downtime for all customers?

### **8. Missing Pieces**
- What critical components are we missing?
- What could go wrong with this architecture?
- Industry best practices for SaaS multi-tenancy we should follow?

---

## 🔗 Service Communication Map

```
┌─────────────────────────────────────────────────────────────────┐
│  Production Server: 209.38.143.71 (DigitalOcean)                │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────┐
│  Twilio Cloud   │
└────────┬────────┘
         │ Webhook: /call/incoming
         ▼
┌─────────────────────────────────────────────────────────────────┐
│  Chad (ChatStack)                                                │
│  Location: /opt/ChatStack/                                       │
│                                                                  │
│  Port 5000: Flask (Admin UI, Twilio webhooks)                   │
│  Port 8001: FastAPI (Phone orchestrator)                        │
│                                                                  │
│  Database: PostgreSQL (customers table) ✅ Has customer_id      │
└────────┬─────────────────────────────────────────┬──────────────┘
         │                                          │
         │ HTTP: customer_id + user_id             │
         ▼                                          │
┌─────────────────────────────────────────┐        │
│  Alice (AI-Memory)                      │        │
│  Location: /opt/ai-memory/              │        │
│                                          │        │
│  Port 8100: FastAPI (Memory APIs)       │        │
│                                          │        │
│  Database: PostgreSQL ❌ NEEDS customer_id│       │
└─────────────────────────────────────────┘        │
                                                    │
                                                    ▼
                                           ┌─────────────────┐
                                           │  OpenAI API     │
                                           │  (LLM)          │
                                           └─────────────────┘
                                                    │
                                                    ▼
                                           ┌─────────────────┐
                                           │  ElevenLabs     │
                                           │  (TTS)          │
                                           └─────────────────┘

┌─────────────────────────────────────────┐
│  NeuroSphere Send Text                  │
│  Location: /root/neurosphere_send_text/ │
│  Port 3000: Flask (SMS service)         │
│  Status: ⚠️ Multi-tenant status unknown  │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│  LeadFlowTracker (CRM)                  │
│  Location: Separate Replit              │
│  Status: ⚠️ Multi-tenant status unknown  │
└─────────────────────────────────────────┘
```

---

## 📝 Technical Specifications

### **Customer ID Format**
- Type: `INTEGER`
- Auto-increment primary key
- Range: 1 to 2,147,483,647
- Example: Peterson Insurance = 1, Smith Agency = 2

### **Thread ID Format**
- Pattern: `customer_{customer_id}_user_{phone_number}`
- Example: `customer_1_user_15551234567`
- Created by: Chad
- Stored by: Alice (as-is, plus separate customer_id column)

### **User ID Format**
- Pattern: Phone number in E.164 format
- Example: `+15551234567`
- Used for: Caller identification within a customer's account

### **Environment Variables (All Services)**
```bash
# Platform-level (same for all customers)
DATABASE_URL=postgresql://...
OPENAI_API_KEY=sk-...
SESSION_SECRET=...

# Customer-level (stored in database, NOT env vars)
# business_name, agent_name, greeting, voice_id, personality
```

---

## ✅ Success Criteria

**We know multi-tenancy works when:**

1. ✅ Two customers can call simultaneously without interference
2. ✅ Customer 1 cannot see Customer 2's caller data
3. ✅ Each customer can customize their AI independently
4. ✅ No hardcoded company names in code
5. ✅ New customer onboarding takes <1 hour (not days)
6. ✅ Database queries always filter by customer_id
7. ✅ Admin panel shows different data per customer
8. ✅ Can deploy code updates without affecting all customers

---

## 🚫 What NOT to Do (Common Pitfalls)

1. ❌ **Don't mix customer data** - Every table needs customer_id
2. ❌ **Don't hardcode company names** - Use database/config
3. ❌ **Don't skip customer_id validation** - Fail closed, not open
4. ❌ **Don't share API keys across customers** - Each gets their own or BYOK
5. ❌ **Don't deploy without testing tenant isolation** - Security critical
6. ❌ **Don't forget to update MPA** - Documentation prevents confusion
7. ❌ **Don't assume location** - Always document which server/port

---

**END OF ARCHITECTURE DOCUMENT**

**Next Step:** Submit to ChatGPT-5 for review and recommendations.
