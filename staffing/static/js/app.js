document.addEventListener('DOMContentLoaded', () => {
    window.app = new BenchZeroApp();
});

class BenchZeroApp {
    constructor() {
        this.activeTab = 'dashboard';
        this.solverData = null;
        this.proposals = [];
        this.developers = [];
        this.projects = [];

        this.benchmarkChart = null;
        this.dashBenchmarkChart = null;

        this.init();
    }

    async init() {
        this.bindTabNavigation();
        this.bindEvents();
        await this.loadAllData();
    }

    bindTabNavigation() {
        document.querySelectorAll('.nav-item').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const targetTab = btn.getAttribute('data-tab');
                this.switchTab(targetTab);
            });
        });
    }

    switchTab(tabId) {
        this.activeTab = tabId;
        
        document.querySelectorAll('.nav-item').forEach(b => b.classList.remove('active'));
        const activeNav = document.querySelector(`.nav-item[data-tab="${tabId}"]`);
        if (activeNav) activeNav.classList.add('active');

        document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
        const targetPane = document.getElementById(`tab-${tabId}`);
        if (targetPane) targetPane.classList.add('active');

        const titleMap = {
            'dashboard': 'Executive Overview',
            'workbench': 'Optimization Engine Workbench',
            'proposals': 'Proposals & Decision Hub',
            'matrix': 'Resource & Slot Capacity Matrix',
            'management': 'Resource Data Management'
        };
        document.getElementById('page-title').textContent = titleMap[tabId] || 'BenchZero';
    }

    bindEvents() {
        // Quick run button
        document.getElementById('btn-quick-run')?.addEventListener('click', () => {
            this.switchTab('workbench');
            this.executeSolver();
        });

        // Config form run
        document.getElementById('solver-config-form')?.addEventListener('click', (e) => {
            if (e.target.id === 'btn-run-solver-wb' || e.target.closest('#btn-run-solver-wb')) {
                e.preventDefault();
                this.executeSolver();
            }
        });

        // Time slider text update
        document.getElementById('input-time-limit')?.addEventListener('input', (e) => {
            document.getElementById('time-limit-val').textContent = e.target.value;
        });

        // Bulk accept proposals
        document.getElementById('btn-bulk-accept')?.addEventListener('click', () => {
            this.bulkAcceptProposals();
        });

        // Form add developer
        document.getElementById('form-add-developer')?.addEventListener('submit', (e) => {
            e.preventDefault();
            this.addDeveloper();
        });

        // Form add slot
        document.getElementById('form-add-slot')?.addEventListener('submit', (e) => {
            e.preventDefault();
            this.addSlot();
        });
    }

    async loadAllData() {
        try {
            await Promise.all([
                this.fetchSolverRuns(),
                this.fetchProposals(),
                this.fetchConfirmedAllocations(),
                this.fetchDevelopers(),
                this.fetchProjects()
            ]);
            this.updateBadgeCount();
        } catch (err) {
            console.error('Error loading BenchZero data:', err);
        }
    }

    async fetchSolverRuns() {
        const res = await fetch('/api/solver-runs/');
        const data = await res.json();
        const runs = data.results || data;
        if (runs && runs.length > 0) {
            this.solverData = runs[0]; // latest run
            this.renderDashboardMetrics(this.solverData);
            this.renderWorkbenchComparison(this.solverData);
        }
    }

    async fetchProposals() {
        const res = await fetch('/api/proposals/');
        const data = await res.json();
        this.proposals = data.results || data;
        this.renderProposals(this.proposals);
    }

    async fetchConfirmedAllocations() {
        const res = await fetch('/api/allocations/');
        const data = await res.json();
        this.renderConfirmedAllocations(data.results || data);
    }

    async fetchDevelopers() {
        const res = await fetch('/api/developers/');
        const data = await res.json();
        this.developers = data.results || data;
        this.renderDeveloperMatrix(this.developers);
    }

    async fetchProjects() {
        const res = await fetch('/api/projects/');
        const data = await res.json();
        this.projects = data.results || data;
        this.renderSlotMatrix(this.projects);
        this.populateSlotProjectDropdown(this.projects);
    }

    async executeSolver() {
        const btn = document.getElementById('btn-run-solver-wb');
        const originalText = btn ? btn.innerHTML : '';
        if (btn) {
            btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Running CP-SAT Engine...';
            btn.disabled = true;
        }

        const objective = document.getElementById('input-objective')?.value || 'balanced';
        const timeLimit = parseFloat(document.getElementById('input-time-limit')?.value || 10.0);
        const runComparison = document.getElementById('check-comparison')?.checked ?? true;

        try {
            const res = await fetch('/api/solver-runs/run/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    objective: objective,
                    time_limit: timeLimit,
                    run_comparison: runComparison
                })
            });

            const data = await res.json();
            this.solverData = data;

            this.renderDashboardMetrics(data);
            this.renderWorkbenchComparison(data);
            await this.fetchProposals();

            if (btn) {
                btn.innerHTML = '<i class="fa-solid fa-check"></i> Solver Optimization Complete!';
                setTimeout(() => {
                    btn.innerHTML = originalText;
                    btn.disabled = false;
                }, 2000);
            }
        } catch (err) {
            console.error('Solver execution failed:', err);
            if (btn) {
                btn.innerHTML = originalText;
                btn.disabled = false;
            }
            alert('Failed to execute CP-SAT solver run.');
        }
    }

    renderDashboardMetrics(runData) {
        if (!runData) return;
        const metrics = runData.summary_metrics || {};

        document.getElementById('stat-total-devs').textContent = (metrics.assigned_developers || 0) + (metrics.bench_developers || 0);
        document.getElementById('stat-bench-devs').textContent = metrics.bench_developers || 0;
        document.getElementById('stat-staffed-slots').textContent = metrics.staffed_assignments || 0;
        document.getElementById('stat-high-prio').textContent = `${metrics.high_priority_fulfillment_pct || 0}%`;

        const comp = metrics.comparison || {};
        const cpsat = comp.cpsat || {};
        const greedy = comp.greedy || {};
        const scipy = comp.scipy || {};

        const gainPct = comp.gain_vs_greedy_pct !== undefined ? comp.gain_vs_greedy_pct : 0;
        document.getElementById('dash-gain-badge').textContent = `CP-SAT +${gainPct}% Score vs Greedy`;

        document.getElementById('dash-cpsat-score').textContent = (cpsat.total_score || runData.total_score || 0).toFixed(1);
        document.getElementById('dash-cpsat-assigned').textContent = cpsat.assignments ? cpsat.assignments.length : (runData.summary_metrics ? runData.summary_metrics.staffed_assignments : 0);
        document.getElementById('dash-cpsat-bench').textContent = metrics.bench_developers || 0;
        document.getElementById('dash-cpsat-runtime').textContent = `${(cpsat.runtime_seconds || runData.runtime_seconds || 0).toFixed(3)}s`;

        document.getElementById('dash-greedy-score').textContent = (greedy.total_score || 0).toFixed(1);
        document.getElementById('dash-greedy-assigned').textContent = greedy.assignments ? greedy.assignments.length : 0;
        document.getElementById('dash-greedy-bench').textContent = greedy.total_score ? Math.max(0, 15 - greedy.assignments.length) : 0;
        document.getElementById('dash-greedy-runtime').textContent = `${(greedy.runtime_seconds || 0).toFixed(3)}s`;

        document.getElementById('dash-scipy-score').textContent = (scipy.total_score || 0).toFixed(1);
        document.getElementById('dash-scipy-assigned').textContent = scipy.assignments ? scipy.assignments.length : 0;
        document.getElementById('dash-scipy-bench').textContent = scipy.total_score ? Math.max(0, 15 - scipy.assignments.length) : 0;
        document.getElementById('dash-scipy-runtime').textContent = `${(scipy.runtime_seconds || 0).toFixed(3)}s`;

        this.renderDashBenchmarkChart(cpsat, greedy, scipy);
    }

    renderWorkbenchComparison(runData) {
        if (!runData || !runData.summary_metrics) return;
        const comp = runData.summary_metrics.comparison || {};

        const cpsat = comp.cpsat || {};
        const greedy = comp.greedy || {};
        const scipy = comp.scipy || {};

        document.getElementById('badge-solver-diff').textContent = `CP-SAT +${comp.gain_vs_greedy_pct || 0}% Score vs Greedy`;
        this.renderBenchmarkChart(cpsat, greedy, scipy);
    }

    renderDashBenchmarkChart(cpsat, greedy, scipy) {
        const ctx = document.getElementById('dashBenchmarkChart');
        if (!ctx) return;

        if (this.dashBenchmarkChart) {
            this.dashBenchmarkChart.destroy();
        }

        this.dashBenchmarkChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: ['Total Score', 'Staffed Slots'],
                datasets: [
                    {
                        label: 'Google OR-Tools CP-SAT (Optimal)',
                        data: [cpsat.total_score || 0, cpsat.assignments ? cpsat.assignments.length : 0],
                        backgroundColor: '#3b82f6'
                    },
                    {
                        label: 'Naive Greedy Matcher',
                        data: [greedy.total_score || 0, greedy.assignments ? greedy.assignments.length : 0],
                        backgroundColor: '#6b7280'
                    },
                    {
                        label: 'SciPy Bipartite Matcher',
                        data: [scipy.total_score || 0, scipy.assignments ? scipy.assignments.length : 0],
                        backgroundColor: '#8b5cf6'
                    }
                ]
            },
            options: {
                responsive: true,
                plugins: {
                    legend: { labels: { color: '#9ca3af' } }
                },
                scales: {
                    x: { ticks: { color: '#9ca3af' }, grid: { color: 'rgba(255,255,255,0.05)' } },
                    y: { ticks: { color: '#9ca3af' }, grid: { color: 'rgba(255,255,255,0.05)' } }
                }
            }
        });
    }

    renderBenchmarkChart(cpsat, greedy, scipy) {
        const ctx = document.getElementById('benchmarkChart');
        if (!ctx) return;

        if (this.benchmarkChart) {
            this.benchmarkChart.destroy();
        }

        this.benchmarkChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: ['Total Score', 'Staffed Slots'],
                datasets: [
                    {
                        label: 'Google OR-Tools CP-SAT (Optimal)',
                        data: [cpsat.total_score || 0, cpsat.assignments ? cpsat.assignments.length : 0],
                        backgroundColor: '#3b82f6'
                    },
                    {
                        label: 'Naive Greedy Matcher',
                        data: [greedy.total_score || 0, greedy.assignments ? greedy.assignments.length : 0],
                        backgroundColor: '#6b7280'
                    },
                    {
                        label: 'SciPy Bipartite Matcher',
                        data: [scipy.total_score || 0, scipy.assignments ? scipy.assignments.length : 0],
                        backgroundColor: '#8b5cf6'
                    }
                ]
            },
            options: {
                responsive: true,
                plugins: {
                    legend: { labels: { color: '#9ca3af' } }
                },
                scales: {
                    x: { ticks: { color: '#9ca3af' }, grid: { color: 'rgba(255,255,255,0.05)' } },
                    y: { ticks: { color: '#9ca3af' }, grid: { color: 'rgba(255,255,255,0.05)' } }
                }
            }
        });
    }

    renderProposals(proposals) {
        const container = document.getElementById('proposals-container');
        if (!container) return;

        const proposedList = proposals.filter(p => p.status === 'proposed');
        if (proposedList.length === 0) {
            container.innerHTML = `<div class="card" style="grid-column: 1 / -1; padding: 30px; text-align: center; color: var(--text-muted);">
                <i class="fa-solid fa-circle-check" style="font-size: 32px; color: var(--emerald); margin-bottom: 12px;"></i>
                <p>All algorithm proposals have been reviewed and accepted!</p>
            </div>`;
            return;
        }

        container.innerHTML = proposedList.map(p => `
            <div class="proposal-card">
                <div class="proposal-header">
                    <div class="proposal-title">
                        <h4>${p.developer_name}</h4>
                        <span class="subtitle">${p.developer_title}</span>
                    </div>
                    <span class="proposal-score">${p.fit_score.toFixed(1)}</span>
                </div>
                <div class="proposal-body">
                    <div class="proposal-slot">
                        <i class="fa-solid fa-briefcase"></i> <strong>${p.project_name}</strong> - ${p.role_title}
                    </div>
                    <span class="badge badge-solver">CP-SAT Proposed</span>
                </div>
                <div class="proposal-actions">
                    <button class="btn btn-sm btn-success btn-block" onclick="app.acceptProposal(${p.id})">
                        <i class="fa-solid fa-check"></i> Accept
                    </button>
                    <button class="btn btn-sm btn-outline btn-block" onclick="app.rejectProposal(${p.id})">
                        <i class="fa-solid fa-xmark"></i> Reject
                    </button>
                </div>
            </div>
        `).join('');
    }

    renderConfirmedAllocations(allocations) {
        const tbody = document.getElementById('confirmed-allocations-body');
        if (!tbody) return;

        if (allocations.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; color: var(--text-muted);">No confirmed allocations yet. Accept proposals above to commit staffing.</td></tr>';
            return;
        }

        tbody.innerHTML = allocations.map(a => `
            <tr>
                <td><strong>${a.developer_name}</strong></td>
                <td>${a.project_name}</td>
                <td>${a.role_title}</td>
                <td>${a.start_date} to ${a.end_date}</td>
                <td>${a.allocated_hours}h / week</td>
                <td><span class="badge badge-success">${a.status.toUpperCase()}</span></td>
            </tr>
        `).join('');
    }

    renderDeveloperMatrix(developers) {
        const tbody = document.getElementById('matrix-developers-body');
        if (!tbody) return;

        tbody.innerHTML = developers.map(d => {
            const skillsHtml = (d.developer_skills || []).map(s => 
                `<span class="badge badge-solver" style="margin-right: 4px; margin-bottom: 4px;">${s.skill_name} (Lvl ${s.proficiency_level})</span>`
            ).join('');

            return `
                <tr>
                    <td><strong>${d.name}</strong></td>
                    <td>${d.title}</td>
                    <td>$${floatVal(d.hourly_cost)}/hr</td>
                    <td>${skillsHtml || '<span style="color:var(--text-muted)">No skills recorded</span>'}</td>
                    <td><span class="badge badge-emerald">ACTIVE</span></td>
                </tr>
            `;
        }).join('');
    }

    renderSlotMatrix(projects) {
        const tbody = document.getElementById('matrix-slots-body');
        if (!tbody) return;

        let rowsHtml = '';
        projects.forEach(p => {
            (p.slots || []).forEach(slot => {
                const reqsHtml = (slot.skill_requirements || []).map(r => 
                    `<span class="badge badge-solver">${r.skill_name} >= Lvl ${r.min_proficiency}</span>`
                ).join(' ');

                rowsHtml += `
                    <tr>
                        <td><strong>${p.name}</strong></td>
                        <td>${slot.role_title}</td>
                        <td><span class="badge badge-count">P${slot.priority}</span></td>
                        <td>${reqsHtml || 'Any'}</td>
                        <td>${slot.headcount_needed} Engineer(s)</td>
                    </tr>
                `;
            });
        });

        tbody.innerHTML = rowsHtml || '<tr><td colspan="5" style="text-align: center;">No project slots configured.</td></tr>';
    }

    populateSlotProjectDropdown(projects) {
        const select = document.getElementById('slot-project-id');
        if (!select) return;
        select.innerHTML = projects.map(p => `<option value="${p.id}">${p.name} (${p.client})</option>`).join('');
    }

    async acceptProposal(id) {
        try {
            const res = await fetch(`/api/proposals/${id}/accept/`, { method: 'POST' });
            const data = await res.json();
            if (res.status === 409) {
                alert(`Conflict Warning: ${data.error || 'Developer is already committed to an overlapping allocation.'}`);
            }
            await this.loadAllData();
        } catch (err) {
            console.error('Failed to accept proposal:', err);
        }
    }

    async rejectProposal(id) {
        try {
            await fetch(`/api/proposals/${id}/reject/`, { method: 'POST' });
            await this.loadAllData();
        } catch (err) {
            console.error('Failed to reject proposal:', err);
        }
    }

    async bulkAcceptProposals() {
        const proposedIds = this.proposals.filter(p => p.status === 'proposed').map(p => p.id);
        if (proposedIds.length === 0) return;

        try {
            const res = await fetch('/api/proposals/bulk-accept/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ proposal_ids: proposedIds })
            });
            const data = await res.json();
            if (data.conflicts_count > 0) {
                alert(`Bulk Approval Result: Accepted ${data.accepted_count} proposals. ${data.conflicts_count} conflicting proposals were auto-rejected.`);
            }
            await this.loadAllData();
        } catch (err) {
            console.error('Bulk accept failed:', err);
        }
    }

    async addDeveloper() {
        const name = document.getElementById('dev-name').value;
        const email = document.getElementById('dev-email').value;
        const title = document.getElementById('dev-title').value;
        const cost = parseFloat(document.getElementById('dev-cost').value);

        try {
            await fetch('/api/developers/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name, email, title, hourly_cost: cost, max_weekly_hours: 40 })
            });
            document.getElementById('form-add-developer').reset();
            await this.loadAllData();
            alert('Developer added successfully!');
        } catch (err) {
            console.error('Failed to add developer:', err);
        }
    }

    async addSlot() {
        const projectId = parseInt(document.getElementById('slot-project-id').value);
        const roleTitle = document.getElementById('slot-role').value;
        const priority = parseInt(document.getElementById('slot-priority').value);
        const headcount = parseInt(document.getElementById('slot-headcount').value);

        const today = new Date().toISOString().split('T')[0];
        const nextMonth = new Date(Date.now() + 60*24*60*60*1000).toISOString().split('T')[0];

        try {
            await fetch('/api/slots/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    project: projectId,
                    role_title: roleTitle,
                    start_date: today,
                    end_date: nextMonth,
                    priority: priority,
                    headcount_needed: headcount,
                    weekly_hours_required: 40
                })
            });
            document.getElementById('form-add-slot').reset();
            await this.loadAllData();
            alert('Project slot added successfully!');
        } catch (err) {
            console.error('Failed to add project slot:', err);
        }
    }

    updateBadgeCount() {
        const pendingCount = this.proposals.filter(p => p.status === 'proposed').length;
        const badge = document.getElementById('pending-proposals-badge');
        if (badge) badge.textContent = pendingCount;
    }
}

function floatVal(val) {
    return parseFloat(val || 0).toFixed(2);
}
