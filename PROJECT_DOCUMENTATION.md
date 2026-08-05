# PROJECT DOCUMENTATION & TECHNICAL SPECIFICATION

**Project Title:** BenchZero – Constraint-Based Multi-Objective Workforce Staffing Allocation Engine  
**Repository:** Tirupathi-Jayadeep/BenchZero  
**Tech Stack:** Python 3.13, Django 5.0, Django REST Framework, Google OR-Tools CP-SAT, SciPy, HTML5, Vanilla CSS3, JS ES6, Chart.js  

---

## 1. Problem Statement
In IT consulting, software enterprises, and professional service agencies, managing workforce allocation ("the bench") is a high-stakes operational challenge. When developers finish projects, they enter "bench status"—representing unbillable payroll costs. Conversely, when new project slots open up, assigning under-qualified or over-committed developers leads to project delays, degraded software quality, and SLA violations.

The core challenge stems from:
- **High Combinatorial Complexity:** Finding optimal assignments for $N$ developers with varying skills, proficiency levels (1–5), weekly capacity limits, and approved leaves across $M$ open project slots with start/end dates, required skills, priority weightings (1–5), and hourly budget constraints.
- **Multi-Objective Trade-offs:** Balancing competing business goals such as maximizing technical skill fit, fulfilling critical (P1/P5) project slots first, minimizing bench cost/unutilized time, and optimizing hourly billing rates.
- **Fractional Allocation & Temporal Overlaps:** Developers often split weekly hours (e.g., 20h/wk on Project A and 20h/wk on Project B) while taking partial approved leaves across overlapping timeline ranges.

---

## 2. Existing System
Traditional workforce management relies on spreadsheet tools (MS Excel, Google Sheets) or conventional commercial scheduling software (Float, Resource Guru, Runn). These systems suffer from fundamental architectural limitations:

1. **Suboptimal Local "First-Come" Greedy Assignment:**
   - Conventional systems assign the first available developer to the first requested project slot (First-Come, First-Served).
   - *Failure Mode:* A high-proficiency senior developer gets greedily locked into a low-priority slot, leaving a downstream critical (P5) project trapped with an under-skilled or unavailable resource.
2. **Binary Availability Assumption:**
   - Legacy tools treat developer availability as a binary status ("Free" or "Busy"), ignoring fractional weekly hours (e.g., 10h available out of 40h max) and overlapping partial leave dates.
3. **Lack of Global Optimization & Multi-Constraint Enforcement:**
   - Manual resource managers struggle to calculate cross-project trade-offs, leading to accidental double-booking, over-allocation past 40h/wk, or skill proficiency mismatches.
4. **Race Conditions & Bypassed Approvals:**
   - Project managers overwrite database bookings directly, causing inconsistent booking states without audit trails or eligibility validation.

---

## 3. Proposed System (BenchZero)
**BenchZero** fundamentally reframes workforce bench management from a manual lookup exercise into a **Global Constraint Satisfaction Problem (CSP)** and **Integer Linear Programming (ILP) Optimization Problem** powered by **Google OR-Tools CP-SAT Solver**.

### Key Innovations:
* **Global Combinatorial Optimization:** Rather than making local sequential decisions, BenchZero evaluates the entire combinatorial decision space $(N \times M)$ simultaneously to guarantee globally optimal allocation.
* **Multi-Objective Objective Formulation:** Supports selectable solver objectives: `balanced`, `maximize_fit`, `maximize_priority`, `minimize_bench`, and `minimize_cost`.
* **Decoupled Human-in-the-Loop Pipeline:** Algorithmic solver runs produce candidate proposals (`AllocationProposal`), which Project Managers review, audit, accept, or reject before committed database locks (`Allocation`) are written.
* **Algorithmic Benchmark Engine:** Built-in side-by-side comparison engine executing **Google OR-Tools CP-SAT**, **SciPy Bipartite Hungarian Matcher**, and **Naive Greedy Matcher** on identical dataset snapshots.
* **Integrations & Governance:** Includes role-based access control (RBAC), approval workflows for developer leaves, automated audit logging, CSV bulk upload/parsing, and iCalendar (.ics) calendar synchronization.

---

## 4. System Architecture

### 4.1 Data Pipeline & Layered Architecture

```
+-----------------------------------------------------------------------------------+
|                                 USER INTERFACE                                    |
|   Glassmorphic Dark SPA (HTML5, Vanilla CSS3, JS ES6, Chart.js, FontAwesome)     |
+-----------------------------------------+-----------------------------------------+
                                          | REST API (JSON)
+-----------------------------------------v-----------------------------------------+
|                              DJANGO REST FRAMEWORK (DRF)                          |
|   - Authentication & RBAC Permissions (IsAdminUser, IsProjectManager, IsDeveloper)|
|   - Serializers & ViewSets (Developers, Projects, Slots, Allocations, Leaves)     |
+--------------------+--------------------+--------------------+--------------------+
                     |                    |                    |
+--------------------v-----+    +---------v----------+    +----v--------------------+
|  ELIGIBILITY FILTER      |    | LEAVE WORKFLOW     |    | CALENDAR SYNC ENGINE    |
| - Hard Skill Matches     |    | - Leave Requests   |    | - iCalendar (.ics) Export|
| - Date Overlap Checks    |    | - PM Approval Flow |    | - Syncing Schedules     |
| - Capacity Availability  |    +--------------------+    +-------------------------+
+--------------------+-----+
                     |
+--------------------v--------------------------------------------------------------+
|                           ALGORITHMIC OPTIMIZATION LAYER                          |
|  +-----------------------------------------------------------------------------+  |
|  |                 Google OR-Tools CP-SAT Solver (Primary Winner)              |  |
|  |   - Decision Variables: X(d,s) in {0, 1}                                    |  |
|  |   - Constraints: Weekly Hours, Slot Headcount, Leaves, Confirmed Allocs     |  |
|  |   - Objective: Maximize Total Multi-Objective Suitability Score S(d,s)       |  |
|  +-----------------------------------------------------------------------------+  |
|  |             SciPy Bipartite Matcher (scipy.optimize.linear_sum_assignment)  |  |
|  |             Naive Greedy Matcher (Baseline Comparison Benchmark)           |  |
|  +-----------------------------------------------------------------------------+  |
+--------------------+--------------------------------------------------------------+
                     | Candidate Proposals (status='proposed')
+--------------------v--------------------------------------------------------------+
|                         HUMAN-IN-THE-LOOP REVIEW HUB                              |
|   - Project Manager Approval / Rejection UI                                       |
|   - Select-for-Update Row Locking (Atomic Database Transactions)                 |
+--------------------+--------------------------------------------------------------+
                     | Confirmed Allocations
+--------------------v--------------------------------------------------------------+
|                           PERSISTENCE & AUDIT LAYER                               |
|   - SQLite (Dev) / PostgreSQL (Prod Docker Profile)                               |
|   - AllocationAuditLog (Created, Accepted Proposal, Cancelled, Reverted)           |
+-----------------------------------------------------------------------------------+
```

---

## 5. Tech Stack

| Category | Component / Technology | Purpose |
| :--- | :--- | :--- |
| **Backend Language & Runtime** | Python 3.13 | High-performance backend execution & scientific computing |
| **Web Framework** | Django 5.0, Django REST Framework (DRF) | ORM data management, REST API endpoints, RBAC permissions |
| **Optimization Engines** | Google OR-Tools CP-SAT (`ortools.sat.python.cp_model`) | Integer Programming & Constraint Satisfaction Solver |
| | SciPy (`scipy.optimize.linear_sum_assignment`) | Bipartite Matching / Hungarian Algorithm Benchmark |
| **Frontend UI** | HTML5, Vanilla CSS3, JavaScript ES6 | Single-Page Application (SPA) with Glassmorphic dark aesthetic |
| **Visualization & Styling** | Chart.js 4.4, FontAwesome 6.4, Google Fonts (Inter, Outfit) | Analytics charts, metrics, icon system, modern typography |
| **Database & ORM** | SQLite (Dev) / PostgreSQL (Production Docker) | Relational storage with row-level transactional locking |
| **Containerization & CI** | Docker, Docker Compose | Multi-container setup (Web App + PostgreSQL DB) |
| **Test Suite** | Pytest, Pytest-Django (47 passing automated tests) | Unit tests, API endpoint tests, permission & solver verification |

---

## 6. Approach / Proposed Methodology

### Step 1: Pre-Solver Eligibility & Candidate Matrix Construction
Before launching the mathematical solver, BenchZero runs a strict **Hard Constraint Eligibility Filter**:
1. **Mandatory Skill Check:** A developer $d$ is eligible for slot $s$ iff for every mandatory skill requirement $r \in R_s$, the developer possesses $d.level \ge r.min\_proficiency$.
2. **Leave Overlap Check:** If developer $d$ has an approved leave spanning date range $[start_{leave}, end_{leave}]$ that overlaps with slot $s$'s active date range $[start_{slot}, end_{slot}]$, developer $d$ is disqualified for that slot.
3. **Confirmed Allocation Capacity Filter:** Calculate developer's remaining uncommitted weekly hours across the slot's timeline.

### Step 2: Multi-Objective Suitability Score Computation $S(d, s)$
For each eligible $(d, s)$ candidate pair, compute a normalized suitability score incorporating skill levels, project priority, dynamic hourly cost penalty, and objective target flags.

### Step 3: CP-SAT Constraint Programming Model Formulation
Formulate binary decision variables $X_{d,s} \in \{0, 1\}$, add linear inequality constraints for weekly hours and headcount limits, and set the integer objective function to maximize:
$$\sum_{(d,s)} X_{d,s} \cdot S(d, s)$$

### Step 4: Solvers Execution & Benchmark Comparison
Execute CP-SAT alongside Hungarian SciPy and Greedy baseline solvers. Return metrics including Total Quality Score, Unassigned Bench Count, High-Priority Slot Coverage %, and Execution Time (ms).

### Step 5: Decoupled Proposal Review & Transactional Persistence
Solver outputs generate `AllocationProposal` records. When a Project Manager approves a proposal, Django executes an atomic database transaction with `select_for_update()` row locking on `Developer` and `ProjectSlot` to prevent race conditions before creating confirmed `Allocation` and `AllocationAuditLog` entries.

---

## 7. Modules Implemented

1. **Authentication & RBAC Permission Module (`staffing/permissions.py`):**
   - Custom DRF permissions: `IsAdminUser`, `IsProjectManager`, `IsDeveloper`, and `IsSelfOrManager`.
2. **Developer & Skill Profile Management (`staffing/models.py`, `staffing/views.py`):**
   - Full CRUD for developers, skills, developer-skill proficiencies (1–5), max weekly hours, and hourly billing rates.
3. **Project & Slot Demand Module (`staffing/models.py`):**
   - Manages projects (priority 1–5, client, status) and project slots (role title, required skills, start/end dates, headcount needed, weekly hours required).
4. **Algorithmic Solver Core (`staffing/solver/`):**
   - `cpsat_solver.py`: Google OR-Tools CP-SAT solver implementation.
   - `scipy_solver.py`: SciPy Hungarian bipartite matching solver implementation.
   - `greedy_solver.py`: Baseline local greedy matching implementation.
   - `fit_score.py`: Dynamic multi-objective suitability scoring model.
   - `eligibility.py`: Hard eligibility and date overlap checking utility.
   - `runner.py`: Orchestrator running side-by-side solver comparisons.
5. **Leave Approval Workflow Module (`staffing/models.py`, `staffing/views.py`):**
   - Manages developer leave requests with start/end dates, approval states (`is_approved`), and automated calendar capacity deductions.
6. **Audit & Cancellation Module (`staffing/models.py`):**
   - Tracks `AllocationAuditLog` entries (`created`, `accepted_proposal`, `cancelled`, `reverted`) with performed user and timestamps.
7. **Calendar Synchronization Integration (`staffing/integrations/calendar_sync.py`):**
   - Generates standard iCalendar `.ics` file streams for developer allocations and approved leaves.
8. **Bulk Data Upload & Parser Module (`tests/test_upload.py`, `staffing/views.py`):**
   - Parses incoming CSV files for batch importing developers, skills, and project requirements.
9. **Interactive Dashboard Front-End (`staffing/static/js/app.js`, `styles.css`, `index.html`):**
   - Single-Page Glassmorphic UI featuring solver objective selectors, real-time KPI metrics, bench trend analytics, audit log feeds, and allocation review cards.

---

## 8. Mathematical Formulas Used

### 8.1 Base Skill Match Score
Let $R_s$ be the set of skill requirements for slot $s$. For requirement $r \in R_s$, let $L_{d, r}$ be developer $d$'s proficiency level ($1 \dots 5$) and $M_r$ be the minimum required proficiency.
$$\text{SkillScore}(d, r) = \begin{cases} 50.0 + 15.0 \times (L_{d, r} - M_r) & \text{if } L_{d, r} \ge M_r \\ 10.0 & \text{if } L_{d, r} < M_r \end{cases}$$

$$\text{BaseSkillScore}(d, s) = \frac{1}{|R_s|} \sum_{r \in R_s} \text{SkillScore}(d, r) \quad (\text{Default } 60.0 \text{ if } R_s = \emptyset)$$

---

### 8.2 Project Slot Priority Multiplier
For slot priority $P_s \in \{1, 2, 3, 4, 5\}$:
$$\text{PriorityMult}(s) = 1.0 + 0.25 \times (P_s - 1)$$

---

### 8.3 Dynamic Pool Cost Penalty Factor
Let $C_d$ be the hourly cost of developer $d$, and $C_{\min}, C_{\max}$ be the minimum and maximum hourly costs in the active developer pool:
$$\text{CostFactor}(d) = 0.5 + 1.0 \times \left( \frac{C_{\max} - C_d}{C_{\max} - C_{\min}} \right) \quad (\text{for } C_{\max} > C_{\min})$$
*(Cheapest developer receives maximum weight $1.5$; highest-cost developer receives $0.5$.)*

---

### 8.4 Multi-Objective Suitability Score $S(d, s)$
Depending on the selected solver objective strategy:

1. **`balanced` (Default):**
   $$S(d, s) = \text{BaseSkillScore}(d, s) \times \text{PriorityMult}(s)$$

2. **`maximize_fit`:**
   $$S(d, s) = \text{BaseSkillScore}(d, s) \times 1.5 \times \text{PriorityMult}(s)$$

3. **`maximize_priority`:**
   $$S(d, s) = \text{BaseSkillScore}(d, s) \times (P_s)^{1.6}$$

4. **`minimize_cost`:**
   $$S(d, s) = \text{BaseSkillScore}(d, s) \times \text{CostFactor}(d) \times \text{PriorityMult}(s)$$

5. **`minimize_bench`:**
   $$S(d, s) = (\text{BaseSkillScore}(d, s) + 40.0) \times \text{PriorityMult}(s)$$

---

### 8.5 Optimization Model Formulation (CP-SAT)

#### Decision Variables:
$$X_{d,s} \in \{0, 1\} \quad \forall d \in D, s \in S \text{ where } d \text{ is eligible for } s$$

#### Subject to Constraints:

1. **Linear Weekly Hours Capacity Constraint:**  
   For every developer $d \in D$ and for every active calendar date $t \in T$:
   $$\sum_{s \in S_{\text{active}}(t)} X_{d,s} \cdot H_s + \sum_{a \in A_{\text{confirmed}}(d, t)} H_a \le \text{MaxWeeklyHours}_d$$

2. **Slot Headcount Hard Constraint:**  
   For every project slot $s \in S$:
   $$\sum_{d \in D_{\text{eligible}}(s)} X_{d,s} \le \text{HeadcountNeeded}_s$$

3. **Leave Disqualification Constraint:**  
   If $\text{ApprovedLeave}(d, t) = \text{True}$ for any $t \in [start_s, end_s]$, then $X_{d,s} = 0$.

#### Objective Function:
$$\text{Maximize } Z = \sum_{d \in D} \sum_{s \in S} X_{d,s} \cdot \lfloor 100 \times S(d, s) \rfloor$$
