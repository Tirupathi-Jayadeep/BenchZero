function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

function extractArray(data) {
    if (!data) return [];
    if (Array.isArray(data)) return data;
    if (Array.isArray(data.results)) return data.results;
    return [];
}

document.addEventListener('DOMContentLoaded', () => {
    window.app = new BenchZeroApp();
});

class BenchZeroApp {
    constructor() {
        this.activeTab = 'dashboard';
        this.solverData = null;
        this.proposals = [];
        this.allocations = [];
        this.developers = [];
        this.projects = [];
        this.isNewSolverRun = false;
        this.authState = { is_authenticated: false, username: '', is_staff: false, require_auth_for_writes: false };

        this.benchmarkChart = null;
        this.dashBenchmarkChart = null;
        this.workforceStatusChartInstance = null;
        this.projectStatusChartInstance = null;
        this.benchTrendChartInstance = null;

        this.init();
    }

    async init() {
        this.initTheme();
        this.bindTabNavigation();
        this.bindEvents();
        await this.fetchAuthStatus();
        await this.loadAllData();
    }

    getChartThemeColors() {
        const isLight = document.body.classList.contains('theme-light');
        return {
            textColor: isLight ? '#334155' : '#8b949e',
            gridColor: isLight ? 'rgba(0, 0, 0, 0.08)' : 'rgba(255, 255, 255, 0.05)',
            isLight
        };
    }

    initTheme() {
        const savedTheme = localStorage.getItem('benchzero-theme') || 'dark';
        if (savedTheme === 'light') {
            document.body.classList.add('theme-light');
            const icon = document.getElementById('theme-icon');
            if (icon) icon.className = 'fa-solid fa-moon';
        }
    }

    toggleTheme() {
        document.body.classList.toggle('theme-light');
        const isLight = document.body.classList.contains('theme-light');
        localStorage.setItem('benchzero-theme', isLight ? 'light' : 'dark');
        const icon = document.getElementById('theme-icon');
        if (icon) {
            icon.className = isLight ? 'fa-solid fa-moon' : 'fa-solid fa-sun';
        }
        // Re-render active charts and views to adapt theme colors
        if (this.solverData) {
            this.renderBenchmarkMetrics(this.solverData);
            if (this.solverData.benchmarks) {
                const b = this.solverData.benchmarks;
                this.renderBenchmarkChart(b.cpsat, b.greedy, b.scipy);
            }
        }
        if (this.benchTrendData) {
            this.renderDashboardBenchTrend(this.benchTrendData);
        }
        this.renderWorkforceAndProjectStatus();
        this.renderRoleWorkforceDashboard();
    }


    async fetchAuthStatus() {
        const { ok, data } = await this.safeFetchJson('/api/auth/status/');
        if (ok && data) {
            this.authState = data;
            this.renderAuthStatus();
        }
    }

    renderAuthStatus() {
        const container = document.getElementById('auth-status-container');
        if (!container) return;

        if (this.authState.is_authenticated) {
            container.innerHTML = `
                <span class="badge badge-emerald" style="display: flex; align-items: center; gap: 6px; font-size: 11px; padding: 6px 10px;">
                    <i class="fa-solid fa-user-check"></i> ${escapeHtml(this.authState.username)} ${this.authState.is_staff ? '(Staff)' : ''}
                </span>
                <button type="button" class="btn btn-sm btn-outline" onclick="app.logoutUser()" title="Log out">
                    <i class="fa-solid fa-right-from-bracket"></i> Logout
                </button>
            `;
        } else if (this.authState.require_auth_for_writes) {
            container.innerHTML = `
                <span class="badge badge-warning" style="display: flex; align-items: center; gap: 6px; font-size: 11px; padding: 6px 10px;">
                    <i class="fa-solid fa-lock"></i> Staff Auth Required
                </span>
                <button type="button" class="btn btn-sm btn-primary" onclick="app.showLoginModal()">
                    <i class="fa-solid fa-right-to-bracket"></i> Staff Login
                </button>
            `;
        } else {
            container.innerHTML = `
                <span class="badge badge-count" style="display: flex; align-items: center; gap: 6px; font-size: 11px; padding: 6px 10px; background: rgba(255,255,255,0.06); color: var(--text-muted);">
                    <i class="fa-solid fa-unlock"></i> Local Demo Mode
                </span>
                <button type="button" class="btn btn-sm btn-outline" onclick="app.showLoginModal()">
                    Staff Login
                </button>
            `;
        }
    }

    getCsrfToken() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        if (meta && meta.content) return meta.content;
        const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
        return match ? decodeURIComponent(match[1]) : '';
    }

    showLoginModal(pendingAction = null, customMessage = null) {
        if (pendingAction) {
            this.pendingAction = pendingAction;
        }
        const modal = document.getElementById('login-modal');
        const errorEl = document.getElementById('login-modal-error');
        if (errorEl) errorEl.style.display = 'none';

        const subtitleEl = document.getElementById('login-modal-subtitle');
        if (subtitleEl) {
            subtitleEl.textContent = customMessage || 'Log in with staff credentials to unlock write actions (candidate assignments, proposals, solver runs).';
        }

        if (modal) modal.style.display = 'flex';
        const userInp = document.getElementById('login-username');
        if (userInp) userInp.focus();
    }

    hideLoginModal() {
        const modal = document.getElementById('login-modal');
        if (modal) modal.style.display = 'none';
        const errorEl = document.getElementById('login-modal-error');
        if (errorEl) errorEl.style.display = 'none';
    }

    async loginUser(username, password) {
        const submitBtn = document.getElementById('btn-login-submit');
        const errorEl = document.getElementById('login-modal-error');
        const errorText = document.getElementById('login-modal-error-text');

        if (errorEl) errorEl.style.display = 'none';
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Logging In...';
        }

        try {
            const { ok, data } = await this.safeFetchJson('/api/auth/login/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password })
            });

            if (ok) {
                this.hideLoginModal();
                this.showToast(`Logged in successfully as ${data?.user?.username || username}!`, 'success');
                await this.fetchAuthStatus();
                await this.loadAllData();

                // If user had clicked an action (e.g. Accept Proposal) before logging in, auto-execute it!
                if (this.pendingAction && typeof this.pendingAction.callback === 'function') {
                    const action = this.pendingAction;
                    this.pendingAction = null;
                    try {
                        await action.callback();
                    } catch (pendingErr) {
                        console.error('Error executing pending action after login:', pendingErr);
                    }
                }
            } else {
                const errMsg = data?.error || data?.detail || 'Invalid username or password.';
                if (errorEl && errorText) {
                    errorText.textContent = errMsg;
                    errorEl.style.display = 'block';
                }
                this.showToast(errMsg, 'warning');
            }
        } finally {
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.innerHTML = '<i class="fa-solid fa-right-to-bracket"></i> Log In';
            }
        }
    }

    async logoutUser() {
        await this.safeFetchJson('/api/auth/logout/', { method: 'POST' });
        this.showToast('Logged out.', 'info');
        await this.fetchAuthStatus();
        await this.loadAllData();
    }

    async safeFetchJson(url, options = {}) {
        try {
            const opts = { ...options };
            opts.headers = { ...(opts.headers || {}) };
            const method = (opts.method || 'GET').toUpperCase();

            // Auto-attach CSRF token for mutating requests
            if (method !== 'GET' && method !== 'HEAD') {
                const csrfToken = this.getCsrfToken();
                if (csrfToken && !opts.headers['X-CSRFToken']) {
                    opts.headers['X-CSRFToken'] = csrfToken;
                }
            }

            const res = await fetch(url, opts);
            let data = null;
            const contentType = res.headers.get('content-type') || '';
            if (contentType.includes('application/json')) {
                data = await res.json().catch(() => null);
            } else {
                const text = await res.text().catch(() => '');
                data = { error: text || res.statusText };
            }
            
            if (res.status === 403 || res.status === 401) {
                if (!url.includes('/api/auth/login')) {
                    this.showLoginModal();
                }
                const rawMsg = data && (data.detail || data.error);
                const msg = (rawMsg && !rawMsg.includes('Authentication credentials'))
                    ? rawMsg
                    : 'Staff login required for write operations. Please log in.';
                return { ok: false, status: res.status, data: { error: `Permission Denied: ${msg}` } };
            }

            return { ok: res.ok, status: res.status, data };
        } catch (err) {
            console.error(`Fetch error for ${url}:`, err);
            return { ok: false, status: 0, data: { error: 'Network connection failed.' } };
        }
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
            'roles-dashboard': 'Developer Roles Dashboard',
            'management': 'Resource Data Management'
        };
        const titleEl = document.getElementById('page-title');
        if (titleEl) titleEl.textContent = titleMap[tabId] || 'BenchZero';

        // Item 9: Dynamic browser tab title
        document.title = `BenchZero — ${titleMap[tabId] || 'Dispatch Board'}`;

        if (tabId === 'roles-dashboard') {
            this.renderRoleWorkforceDashboard();
        }
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

        // Form login
        document.getElementById('form-login')?.addEventListener('submit', (e) => {
            e.preventDefault();
            const u = document.getElementById('login-username').value;
            const p = document.getElementById('login-password').value;
            this.loginUser(u, p);
        });

        // Role search & filter listeners
        document.getElementById('role-search-input')?.addEventListener('input', () => {
            this.renderRoleWorkforceDashboard();
        });
        document.getElementById('role-status-filter')?.addEventListener('change', () => {
            this.renderRoleWorkforceDashboard();
        });
        document.getElementById('role-skill-filter')?.addEventListener('change', () => {
            this.renderRoleWorkforceDashboard();
        });

        // Close notifications dropdown on outside click
        document.addEventListener('click', (e) => {
            const btn = document.getElementById('notifications-bell-btn');
            const menu = document.getElementById('notifications-dropdown');
            if (menu && menu.style.display === 'flex' && !btn?.contains(e.target) && !menu.contains(e.target)) {
                menu.style.display = 'none';
            }
        });

        this.bindFileUploadEvents();
        this.bindRulesTabEvents();

        // Close project suggestions drawer
        document.getElementById('btn-close-drawer')?.addEventListener('click', () => {
            const drawer = document.getElementById('project-suggestions-drawer');
            if (drawer) drawer.style.display = 'none';
            // Remove active row highlight
            document.querySelectorAll('.project-row-clickable').forEach(r => r.classList.remove('active-project-row'));
        });
    }

    async loadAllData() {
        // allSettled, not all: one failed fetch/render (e.g. a CDN blip on
        // Chart.js, a flaky network) must not prevent the rest of the
        // dashboard -- which has already fetched its own data independently
        // -- from rendering.
        const results = await Promise.allSettled([
            this.fetchSolverRuns(),
            this.fetchProposals(),
            this.fetchConfirmedAllocations(),
            this.fetchDevelopers(),
            this.fetchProjects(),
            this.fetchBenchTrend()
        ]);
        results.forEach(r => {
            if (r.status === 'rejected') console.error('BenchZero data load error:', r.reason);
        });
        this.renderWorkforceAndProjectStatus();
        this.renderCandidateAssignments(this.proposals);
        this.renderRoleWorkforceDashboard();
        this.renderActivityLog();
        this.renderNotifications();
        this.updateBadgeCount();
    }

    async fetchBenchTrend() {
        try {
            const res = await fetch('/api/allocations/bench-trend/?days=30');
            const data = await res.json();
            this.benchTrend = data.trend || [];
            this.renderBenchTrendChart(this.benchTrend);
        } catch (err) {
            console.error('Error loading bench trend:', err);
        }
    }

    renderBenchTrendChart(trend) {
        const ctx = document.getElementById('benchTrendChart');
        if (!ctx || !trend || trend.length === 0) return;
        if (typeof Chart === 'undefined') {
            console.warn('Chart.js unavailable -- skipping benchTrendChart render.');
            return;
        }

        if (this.benchTrendChartInstance) this.benchTrendChartInstance.destroy();

        const labels = trend.map(t => {
            const d = new Date(t.date + 'T00:00:00');
            return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
        });

        const { textColor, gridColor } = this.getChartThemeColors();

        this.benchTrendChartInstance = new Chart(ctx, {
            type: 'line',
            data: {
                labels,
                datasets: [{
                    label: 'Bench %',
                    data: trend.map(t => t.bench_pct),
                    borderColor: '#f59e0b',
                    backgroundColor: 'rgba(245, 158, 11, 0.12)',
                    fill: true,
                    tension: 0.3,
                    pointRadius: 2,
                    pointHoverRadius: 5,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: true,
                        max: 100,
                        ticks: { color: textColor, callback: v => v + '%' },
                        grid: { color: gridColor }
                    },
                    x: {
                        ticks: { color: textColor, maxRotation: 0, autoSkip: true, maxTicksLimit: 8 },
                        grid: { display: false }
                    }
                },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: (ctx) => {
                                const row = trend[ctx.dataIndex];
                                return `${row.bench} on bench / ${row.total_developers} total (${row.bench_pct}%)`;
                            }
                        }
                    }
                }
            }
        });

    }

    renderActivityLog() {
        const container = document.getElementById('activity-log-feed');
        if (!container) return;

        const iconMap = {
            created: { icon: 'fa-plus', cls: 'activity-icon-primary' },
            accepted: { icon: 'fa-circle-check', cls: 'activity-icon-emerald' },
            cancelled: { icon: 'fa-ban', cls: 'activity-icon-rose' },
            reverted: { icon: 'fa-rotate-left', cls: 'activity-icon-amber' },
        };

        const entries = [];
        this.allocations.forEach(a => {
            (a.audit_logs || []).forEach(log => {
                entries.push({
                    ...log,
                    developer_name: a.developer_name,
                    project_name: a.project_name,
                    role_title: a.role_title,
                });
            });
        });

        entries.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
        const recent = entries.slice(0, 25);

        if (recent.length === 0) {
            container.innerHTML = '<p style="color: var(--text-muted); text-align: center; padding: 24px 0;">No activity recorded yet.</p>';
            return;
        }

        const actionText = {
            created: 'was allocated to',
            accepted: 'proposal accepted for',
            cancelled: 'allocation cancelled on',
            reverted: 'allocation reverted on',
        };

        container.innerHTML = recent.map(e => {
            const meta = iconMap[e.action] || { icon: 'fa-circle-info', cls: 'activity-icon-primary' };
            const who = escapeHtml(e.performed_by_name || 'System');
            const verb = actionText[e.action] || e.action;
            const when = this.formatRelativeTime(e.timestamp);
            const reasonText = e.reason ? ` — "${escapeHtml(e.reason)}"` : '';
            const devName = escapeHtml(e.developer_name);
            const projName = escapeHtml(e.project_name);
            const rTitle = escapeHtml(e.role_title);
            return `
                <div class="activity-item">
                    <div class="activity-icon ${meta.cls}"><i class="fa-solid ${meta.icon}"></i></div>
                    <div class="activity-text">
                        <strong>${devName}</strong> ${verb} <strong>${projName}</strong> (${rTitle})${reasonText}
                        <small>by ${who} · ${when}</small>
                    </div>
                </div>
            `;
        }).join('');
    }

    formatRelativeTime(isoString) {
        const then = new Date(isoString);
        const diffMs = Date.now() - then.getTime();
        const diffMin = Math.floor(diffMs / 60000);
        if (diffMin < 1) return 'just now';
        if (diffMin < 60) return `${diffMin} min ago`;
        const diffHr = Math.floor(diffMin / 60);
        if (diffHr < 24) return `${diffHr} hr${diffHr === 1 ? '' : 's'} ago`;
        const diffDay = Math.floor(diffHr / 24);
        if (diffDay < 30) return `${diffDay} day${diffDay === 1 ? '' : 's'} ago`;
        return then.toLocaleDateString();
    }

    async cancelAllocation(id) {
        const reason = prompt('Reason for cancelling this allocation (optional):', '');
        if (reason === null) return;

        const { ok, data } = await this.safeFetchJson(`/api/allocations/${id}/cancel/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ reason: reason || 'User initiated cancellation' })
        });

        if (!ok) {
            this.showToast(`Cancel Failed: ${data?.error || 'Failed to cancel allocation'}`, 'warning');
            return;
        }

        this.showToast('Allocation cancelled successfully.', 'info');
        await this.loadAllData();
    }

    async fetchSolverRuns() {
        const { ok, data } = await this.safeFetchJson('/api/solver-runs/');
        if (ok && data) {
            const runs = extractArray(data);
            if (runs.length > 0) {
                this.solverData = runs[0];
                this.renderDashboardMetrics(this.solverData);
                this.renderWorkbenchComparison(this.solverData);
            }
        }
    }

    async fetchProposals() {
        const { ok, data } = await this.safeFetchJson('/api/proposals/');
        if (ok && data) {
            this.proposals = extractArray(data);
            this.renderProposals(this.proposals);
            this.renderCandidateAssignments(this.proposals);
            this.renderProjectTeamRosters(this.allocations, this.proposals);
        }
    }

    async fetchConfirmedAllocations() {
        const { ok, data } = await this.safeFetchJson('/api/allocations/');
        if (ok && data) {
            this.allocations = extractArray(data);
            this.renderConfirmedAllocations(this.allocations);
            this.renderProjectTeamRosters(this.allocations, this.proposals);
        }
    }

    async fetchDevelopers() {
        const { ok, data } = await this.safeFetchJson('/api/developers/');
        if (ok && data) {
            this.developers = extractArray(data);
            this.renderDeveloperMatrix(this.developers);
        }
    }

    async fetchProjects() {
        const { ok, data } = await this.safeFetchJson('/api/projects/');
        if (ok && data) {
            this.projects = extractArray(data);
            this.renderSlotMatrix(this.projects);
            this.populateSlotProjectDropdown(this.projects);
        }
    }

    isDateInRange(date, start, end) {
        const d = new Date(date), s = new Date(start), e = new Date(end);
        return d >= s && d <= e;
    }

    computeWorkforceStatus() {
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        const statusList = [];
        let allocatedCount = 0, benchCount = 0, leaveCount = 0;

        this.developers.forEach(dev => {
            const activeLeave = (dev.leaves || []).find(
                l => l.is_approved && this.isDateInRange(today, l.start_date, l.end_date)
            );
            if (activeLeave) {
                leaveCount++;
                statusList.push({
                    id: dev.id,
                    name: dev.name, status: 'On Leave',
                    detail: `${activeLeave.reason} — until ${activeLeave.end_date}`,
                    badgeClass: 'status-badge-purple'
                });
                return;
            }

            const activeAlloc = this.allocations.find(
                a => a.developer === dev.id && a.status === 'confirmed' && new Date(a.end_date) >= today
            );
            if (activeAlloc) {
                allocatedCount++;
                const isUpcoming = new Date(activeAlloc.start_date) > today;
                statusList.push({
                    id: dev.id,
                    name: dev.name,
                    status: isUpcoming ? `Allocated (Starts ${activeAlloc.start_date})` : 'Allocated',
                    detail: `${activeAlloc.project_name} — ${activeAlloc.role_title} (until ${activeAlloc.end_date})`,
                    badgeClass: 'status-badge-emerald'
                });
            } else {
                benchCount++;
                const pastAllocs = this.allocations.filter(
                    a => a.developer === dev.id && a.status === 'confirmed' && new Date(a.end_date) < today
                );
                let sinceDate = dev.created_at ? new Date(dev.created_at) : today;
                pastAllocs.forEach(a => {
                    const endDate = new Date(a.end_date);
                    if (endDate > sinceDate) sinceDate = endDate;
                });
                const daysBench = Math.max(0, Math.floor((today - sinceDate) / (1000 * 60 * 60 * 24)));
                statusList.push({
                    id: dev.id,
                    name: dev.name, status: 'On Bench',
                    detail: `${daysBench} day${daysBench === 1 ? '' : 's'} on bench`,
                    badgeClass: 'status-badge-amber'
                });
            }
        });

        return { statusList, allocatedCount, benchCount, leaveCount };
    }

    computeProjectStatus() {
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        const rows = [];
        let fullCount = 0, partialCount = 0, unstaffedCount = 0;

        this.projects.forEach(proj => {
            let totalNeeded = 0, totalFilled = 0;
            (proj.slots || []).forEach(slot => {
                totalNeeded += slot.headcount_needed;
                const filled = this.allocations.filter(
                    a => a.project_slot === slot.id && a.status === 'confirmed' && new Date(a.end_date) >= today
                ).length;
                totalFilled += Math.min(filled, slot.headcount_needed);
            });

            let statusLabel, badgeClass;
            if (totalNeeded === 0) {
                statusLabel = 'No Open Slots';
                badgeClass = 'status-badge-purple';
            } else if (totalFilled >= totalNeeded) {
                statusLabel = 'Fully Staffed';
                badgeClass = 'status-badge-emerald';
                fullCount++;
            } else if (totalFilled > 0) {
                statusLabel = 'Partial';
                badgeClass = 'status-badge-amber';
                partialCount++;
            } else {
                statusLabel = 'Unstaffed';
                badgeClass = 'status-badge-rose';
                unstaffedCount++;
            }

            rows.push({
                id: proj.id,
                name: proj.name, client: proj.client, priority: proj.priority,
                filled: `${totalFilled}/${totalNeeded}`, status: statusLabel, badgeClass
            });
        });

        const order = { 'Unstaffed': 0, 'Partial': 1, 'Fully Staffed': 2, 'No Open Slots': 3 };
        rows.sort((a, b) => (order[a.status] - order[b.status]) || (b.priority - a.priority));

        return { rows, fullCount, partialCount, unstaffedCount };
    }

    renderDoughnutChart(canvasId, instanceKey, labels, data, colors) {
        const ctx = document.getElementById(canvasId);
        if (!ctx) return;
        if (typeof Chart === 'undefined') {
            console.warn(`Chart.js unavailable -- skipping ${canvasId} render.`);
            return;
        }
        if (this[instanceKey]) this[instanceKey].destroy();

        this[instanceKey] = new Chart(ctx, {
            type: 'doughnut',
            data: { labels, datasets: [{ data, backgroundColor: colors, borderWidth: 0 }] },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { position: 'bottom', labels: { color: '#9ca3af', boxWidth: 12, padding: 12, font: { size: 11 } } }
                }
            }
        });
    }

    renderWorkforceAndProjectStatus() {
        const wf = this.computeWorkforceStatus();
        const wfAllocatedEl = document.getElementById('wf-allocated-count');
        if (!wfAllocatedEl) return; // panel not on this page render yet

        wfAllocatedEl.textContent = wf.allocatedCount;
        document.getElementById('wf-bench-count').textContent = wf.benchCount;
        document.getElementById('wf-leave-count').textContent = wf.leaveCount;

        const wfBody = document.getElementById('workforce-status-body');
        if (wfBody) {
            wfBody.innerHTML = wf.statusList.map(s => `
                <tr>
                    <td>${escapeHtml(s.name)}</td>
                    <td><span class="status-badge ${s.badgeClass}">${escapeHtml(s.status)}</span></td>
                    <td>${escapeHtml(s.detail)}</td>
                </tr>
            `).join('') || '<tr><td colspan="3" style="text-align:center; color:var(--text-muted);">No developers yet.</td></tr>';
        }

        this.renderDoughnutChart(
            'workforceStatusChart', 'workforceStatusChartInstance',
            ['Allocated', 'On Bench', 'On Leave'],
            [wf.allocatedCount, wf.benchCount, wf.leaveCount],
            ['#10b981', '#f59e0b', '#8b5cf6']
        );

        const proj = this.computeProjectStatus();
        document.getElementById('proj-full-count').textContent = proj.fullCount;
        document.getElementById('proj-partial-count').textContent = proj.partialCount;
        document.getElementById('proj-unstaffed-count').textContent = proj.unstaffedCount;

        const projBody = document.getElementById('project-status-body');
        if (projBody) {
            projBody.innerHTML = proj.rows.map(r => `
                <tr class="project-row-clickable" data-project-name="${escapeHtml(r.name)}" title="Click to view suggested developers for ${escapeHtml(r.name)}">
                    <td>${escapeHtml(r.name)}</td>
                    <td>${escapeHtml(r.client)}</td>
                    <td>${r.filled}</td>
                    <td><span class="status-badge ${r.badgeClass}">${escapeHtml(r.status)}</span></td>
                </tr>
            `).join('') || '<tr><td colspan="4" style="text-align:center; color:var(--text-muted);">No projects yet.</td></tr>';

            // Bind click handlers on project rows
            projBody.querySelectorAll('.project-row-clickable').forEach(row => {
                row.addEventListener('click', () => {
                    const projectName = row.getAttribute('data-project-name');
                    this.showProjectSuggestions(projectName);
                    // Highlight clicked row
                    projBody.querySelectorAll('.project-row-clickable').forEach(r => r.classList.remove('active-project-row'));
                    row.classList.add('active-project-row');
                });
            });
        }

        this.renderDoughnutChart(
            'projectStatusChart', 'projectStatusChartInstance',
            ['Fully Staffed', 'Partial', 'Unstaffed'],
            [proj.fullCount, proj.partialCount, proj.unstaffedCount],
            ['#10b981', '#f59e0b', '#ef4444']
        );
    }

    showProjectSuggestions(projectName) {
        const drawer = document.getElementById('project-suggestions-drawer');
        const titleEl = document.getElementById('drawer-project-title');
        const bodyEl = document.getElementById('drawer-suggestions-body');
        if (!drawer || !titleEl || !bodyEl) return;

        titleEl.innerHTML = `<i class="fa-solid fa-user-tag"></i> Suggested for: ${escapeHtml(projectName)}`;

        // Filter proposals for this project
        const projectProposals = (this.proposals || []).filter(
            p => p.project_name === projectName && p.status === 'proposed'
        );

        if (projectProposals.length === 0) {
            bodyEl.innerHTML = `<div class="drawer-empty">
                <i class="fa-solid fa-user-slash"></i>
                <p>No suggested candidates for this project yet.</p>
                <span>Run the CP-SAT solver to generate suggestions.</span>
            </div>`;
        } else {
            bodyEl.innerHTML = projectProposals.map(p => `
                <div class="drawer-suggestion-card">
                    <div class="drawer-candidate-info">
                        <div class="candidate-avatar"><i class="fa-solid fa-user"></i></div>
                        <div>
                            <strong>${escapeHtml(p.developer_name)}</strong>
                            <span class="candidate-subtitle">${escapeHtml(p.developer_title || '')}</span>
                        </div>
                    </div>
                    <div class="drawer-candidate-meta">
                        <span class="candidate-role-chip">${escapeHtml(p.role_title)}</span>
                        <span class="badge badge-emerald">${p.fit_score.toFixed(1)} Fit</span>
                    </div>
                    <button class="btn btn-sm btn-success" onclick="app.acceptProposal(${p.id})">
                        <i class="fa-solid fa-check"></i> Accept
                    </button>
                </div>
            `).join('');
        }

        drawer.style.display = 'block';
        drawer.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
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
            const { ok, data } = await this.safeFetchJson('/api/solver-runs/run/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    objective: objective,
                    time_limit: timeLimit,
                    run_comparison: runComparison
                })
            });

            if (!ok) {
                this.showToast(`Solver Run Notice: ${data.error || 'Failed to run solver'}`, 'warning');
                if (btn) {
                    btn.innerHTML = originalText;
                    btn.disabled = false;
                }
                return;
            }

            this.solverData = data;
            this.isNewSolverRun = true;

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
            this.showToast('Failed to execute CP-SAT solver run.', 'warning');
        }
    }

    renderDashboardMetrics(runData) {
        if (!runData) return;
        const metrics = runData.summary_metrics || {};

        // Bug 1 Fix: Compute KPI cards from LIVE data, not stale solver snapshot
        const wf = this.computeWorkforceStatus();
        const proj = this.computeProjectStatus();
        const totalDevs = this.developers.length;
        const benchDevs = wf.benchCount;
        const confirmedAllocs = (this.allocations || []).filter(a => a.status === 'confirmed');
        const staffedSlots = confirmedAllocs.length;

        // High-priority fulfillment: count confirmed allocs for P4+ slots
        let highPrioTotal = 0, highPrioFilled = 0;
        (this.projects || []).forEach(p => {
            (p.slots || []).forEach(s => {
                if (s.priority >= 4) {
                    highPrioTotal += s.headcount_needed;
                    const filled = confirmedAllocs.filter(a => a.project_slot === s.id).length;
                    highPrioFilled += Math.min(filled, s.headcount_needed);
                }
            });
        });
        const highPrioPct = highPrioTotal > 0 ? Math.round((highPrioFilled / highPrioTotal) * 100) : 0;

        document.getElementById('stat-total-devs').textContent = totalDevs;
        document.getElementById('stat-bench-devs').textContent = benchDevs;
        document.getElementById('stat-staffed-slots').textContent = staffedSlots;
        document.getElementById('stat-high-prio').textContent = `${highPrioPct}%`;

        const comp = metrics.comparison || {};
        const cpsat = comp.cpsat || {};
        const greedy = comp.greedy || {};
        const scipy = comp.scipy || {};

        const gainPct = comp.gain_vs_greedy_pct !== undefined ? comp.gain_vs_greedy_pct : 0;
        document.getElementById('dash-gain-badge').textContent = `CP-SAT +${gainPct}% Score vs Greedy`;

        document.getElementById('dash-cpsat-score').textContent = (cpsat.total_score || runData.total_score || 0).toFixed(1);
        document.getElementById('dash-cpsat-assigned').textContent = cpsat.assignments ? cpsat.assignments.length : (metrics.staffed_assignments || 0);
        document.getElementById('dash-cpsat-bench').textContent = cpsat.assignments ? Math.max(0, totalDevs - cpsat.assignments.length) : benchDevs;
        document.getElementById('dash-cpsat-runtime').textContent = `${(cpsat.runtime_seconds || runData.runtime_seconds || 0).toFixed(3)}s`;

        document.getElementById('dash-greedy-score').textContent = (greedy.total_score || 0).toFixed(1);
        document.getElementById('dash-greedy-assigned').textContent = greedy.assignments ? greedy.assignments.length : 0;
        document.getElementById('dash-greedy-bench').textContent = greedy.assignments ? Math.max(0, totalDevs - greedy.assignments.length) : 0;
        document.getElementById('dash-greedy-runtime').textContent = `${(greedy.runtime_seconds || 0).toFixed(3)}s`;

        document.getElementById('dash-scipy-score').textContent = (scipy.total_score || 0).toFixed(1);
        document.getElementById('dash-scipy-assigned').textContent = scipy.assignments ? scipy.assignments.length : 0;
        document.getElementById('dash-scipy-bench').textContent = scipy.assignments ? Math.max(0, totalDevs - scipy.assignments.length) : 0;
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
        if (typeof Chart === 'undefined') return;

        if (this.dashBenchmarkChart) {
            this.dashBenchmarkChart.destroy();
        }

        // Bug 3 Fix: Separate score and slots into dual Y-axis chart
        const cpsatScore = cpsat.total_score || 0;
        const scipyScore = scipy.total_score || 0;
        const greedyScore = greedy.total_score || 0;
        const cpsatSlots = cpsat.assignments ? cpsat.assignments.length : 0;
        const scipySlots = scipy.assignments ? scipy.assignments.length : 0;
        const greedySlots = greedy.assignments ? greedy.assignments.length : 0;

        this.dashBenchmarkChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: ['CP-SAT', 'SciPy', 'Greedy'],
                datasets: [
                    {
                        label: 'Quality Score',
                        data: [cpsatScore, scipyScore, greedyScore],
                        backgroundColor: ['#58a6ff', '#bc8cff', '#8b949e'],
                        yAxisID: 'yScore',
                        order: 2
                    },
                    {
                        label: 'Staffed Slots',
                        data: [cpsatSlots, scipySlots, greedySlots],
                        backgroundColor: ['rgba(88,166,255,0.35)', 'rgba(188,140,255,0.35)', 'rgba(139,148,158,0.35)'],
                        borderColor: ['#58a6ff', '#bc8cff', '#8b949e'],
                        borderWidth: 2,
                        yAxisID: 'ySlots',
                        order: 1
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { labels: { color: '#8b949e', font: { size: 11 } } }
                },
                scales: {
                    x: { ticks: { color: '#8b949e' }, grid: { color: 'rgba(255,255,255,0.05)' } },
                    yScore: {
                        type: 'linear', position: 'left',
                        title: { display: true, text: 'Quality Score', color: '#8b949e', font: { size: 11 } },
                        ticks: { color: '#8b949e' },
                        grid: { color: 'rgba(255,255,255,0.05)' }
                    },
                    ySlots: {
                        type: 'linear', position: 'right',
                        title: { display: true, text: 'Staffed Slots', color: '#8b949e', font: { size: 11 } },
                        ticks: { color: '#8b949e', stepSize: 1 },
                        grid: { drawOnChartArea: false }
                    }
                }
            }
        });
    }

    renderBenchmarkChart(cpsat, greedy, scipy) {
        const ctx = document.getElementById('benchmarkChart');
        if (!ctx) return;
        if (typeof Chart === 'undefined') return;

        if (this.benchmarkChart) {
            this.benchmarkChart.destroy();
        }

        const cpsatScore = cpsat.total_score || 0;
        const scipyScore = scipy.total_score || 0;
        const greedyScore = greedy.total_score || 0;
        const cpsatSlots = cpsat.assignments ? cpsat.assignments.length : 0;
        const scipySlots = scipy.assignments ? scipy.assignments.length : 0;
        const greedySlots = greedy.assignments ? greedy.assignments.length : 0;

        const { textColor, gridColor } = this.getChartThemeColors();

        this.benchmarkChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: ['CP-SAT', 'SciPy', 'Greedy'],
                datasets: [
                    {
                        label: 'Quality Score',
                        data: [cpsatScore, scipyScore, greedyScore],
                        backgroundColor: ['#2563eb', '#7c3aed', '#64748b'],
                        yAxisID: 'yScore',
                        order: 2
                    },
                    {
                        label: 'Staffed Slots',
                        data: [cpsatSlots, scipySlots, greedySlots],
                        backgroundColor: ['rgba(37, 99, 235, 0.25)', 'rgba(124, 58, 237, 0.25)', 'rgba(100, 116, 139, 0.25)'],
                        borderColor: ['#2563eb', '#7c3aed', '#64748b'],
                        borderWidth: 2,
                        yAxisID: 'ySlots',
                        order: 1
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { labels: { color: textColor, font: { size: 11 } } }
                },
                scales: {
                    x: { ticks: { color: textColor }, grid: { color: gridColor } },
                    yScore: {
                        type: 'linear', position: 'left',
                        title: { display: true, text: 'Quality Score', color: textColor, font: { size: 11, weight: 'bold' } },
                        ticks: { color: textColor },
                        grid: { color: gridColor }
                    },
                    ySlots: {
                        type: 'linear', position: 'right',
                        title: { display: true, text: 'Staffed Slots', color: textColor, font: { size: 11, weight: 'bold' } },
                        ticks: { color: textColor, stepSize: 1 },
                        grid: { drawOnChartArea: false }
                    }
                }
            }
        });

    }

    /**
     * Compute a fit score for a developer against a slot's skill requirements.
     * Mirrors the solver's scoring logic:
     *   - Each matched skill contributes: (dev_proficiency / 5) * weight
     *   - Mandatory skills have weight 20, optional have weight 10
     *   - Missing mandatory skills score 0 for that skill
     *   - Final score is normalized to ~0-150 range for display consistency
     */
    computeDevSlotScore(dev, slot) {
        const reqs = slot.skill_requirements || [];
        if (reqs.length === 0) return { score: 50, matchedCount: 0, totalReqs: 0, missingMandatory: false };

        const devSkillMap = {};
        (dev.developer_skills || []).forEach(ds => {
            devSkillMap[ds.skill_name.toLowerCase()] = ds.proficiency_level;
        });

        let totalScore = 0;
        let maxPossible = 0;
        let matchedCount = 0;
        let missingMandatory = false;

        reqs.forEach(req => {
            const weight = req.is_mandatory ? 20 : 10;
            maxPossible += weight;
            const devProf = devSkillMap[req.skill_name.toLowerCase()];

            if (devProf !== undefined) {
                // Developer has this skill
                if (devProf >= (req.min_proficiency || 1)) {
                    totalScore += (devProf / 5) * weight;
                    matchedCount++;
                } else {
                    // Has skill but below minimum
                    totalScore += (devProf / 5) * weight * 0.5;
                    if (req.is_mandatory) missingMandatory = true;
                }
            } else {
                // Developer doesn't have this skill at all
                if (req.is_mandatory) missingMandatory = true;
            }
        });

        const normalized = maxPossible > 0 ? (totalScore / maxPossible) * 150 : 50;
        return { score: parseFloat(normalized.toFixed(1)), matchedCount, totalReqs: reqs.length, missingMandatory };
    }

    renderCandidateAssignments(proposals) {
        const container = document.getElementById('dash-candidate-assignments-grouped');
        if (!container) return;

        // Deduplicate projects by ID to ensure unique project cards
        const rawProjects = this.projects || [];
        const seenProjIds = new Set();
        const projects = [];
        rawProjects.forEach(p => {
            if (!seenProjIds.has(p.id)) {
                seenProjIds.add(p.id);
                projects.push(p);
            }
        });

        const developers = this.developers || [];
        const proposedList = proposals.filter(p => p.status === 'proposed');

        if (projects.length === 0 || developers.length === 0) {
            container.innerHTML = `<div style="text-align: center; color: var(--text-muted); padding: 30px 20px;">
                <i class="fa-solid fa-spinner fa-pulse" style="font-size: 24px; margin-bottom: 10px; display: block;"></i>
                Loading candidate data...
            </div>`;
            return;
        }

        // Build a lookup of solver proposals by slot id for quick access
        const proposalBySlot = {};
        proposedList.forEach(p => {
            if (!proposalBySlot[p.project_slot]) proposalBySlot[p.project_slot] = [];
            proposalBySlot[p.project_slot].push(p);
        });

        // Count confirmed allocations by slot id
        const confirmedBySlot = {};
        (this.allocations || []).filter(a => a.status === 'confirmed').forEach(a => {
            confirmedBySlot[a.project_slot] = (confirmedBySlot[a.project_slot] || 0) + 1;
        });

        // Already-allocated developer IDs (confirmed) — exclude from candidate lists
        const allocatedDevIds = new Set();
        (this.allocations || []).filter(a => a.status === 'confirmed').forEach(a => allocatedDevIds.add(a.developer));

        let html = '';
        let hasAnySlots = false;

        projects.forEach(proj => {
            const slots = proj.slots || [];
            if (slots.length === 0) return;

            let roleCardsHtml = '';

            slots.forEach(slot => {
                const confirmedCount = confirmedBySlot[slot.id] || 0;
                const isSlotFull = confirmedCount >= slot.headcount_needed;

                // Get solver's top picks for this slot
                const solverPicks = proposalBySlot[slot.id] || [];

                // Compute scores for ALL developers against this slot
                const allCandidates = [];
                developers.forEach(dev => {
                    if (allocatedDevIds.has(dev.id)) return; // skip already allocated

                    const result = this.computeDevSlotScore(dev, slot);
                    const solverProposal = solverPicks.find(p => p.developer === dev.id);

                    allCandidates.push({
                        devId: dev.id,
                        name: dev.name,
                        title: dev.title,
                        score: solverProposal ? solverProposal.fit_score : result.score,
                        matchedSkills: result.matchedCount,
                        totalReqs: result.totalReqs,
                        missingMandatory: result.missingMandatory,
                        isSolverPick: !!solverProposal,
                        proposalId: solverProposal ? solverProposal.id : null,
                    });
                });

                // Sort: solver picks first, then by score descending
                allCandidates.sort((a, b) => {
                    if (a.isSolverPick && !b.isSolverPick) return -1;
                    if (!a.isSolverPick && b.isSolverPick) return 1;
                    return b.score - a.score;
                });

                // Show top N eligible (non-solver) candidates: those who match at least 1 skill
                const eligibleOthers = allCandidates.filter(c => !c.isSolverPick && !c.missingMandatory && c.matchedSkills > 0);
                const displayCandidates = [
                    ...allCandidates.filter(c => c.isSolverPick),
                    ...eligibleOthers.slice(0, 5)
                ];

                // Bug 2 Fix: Always show role slots, even with 0 candidates
                hasAnySlots = true;

                const candidateRows = displayCandidates.map(c => {
                    const scoreClass = c.score >= 120 ? 'status-dot-green' : c.score >= 80 ? 'status-dot-amber' : 'status-dot-red';
                    const solverBadge = c.isSolverPick
                        ? `<span class="solver-pick-badge"><i class="fa-solid fa-crown"></i> Solver Pick</span>`
                        : `<span class="eligible-badge">Eligible</span>`;

                    let acceptBtn = '';
                    if (isSlotFull) {
                        acceptBtn = `<span class="status-dot-badge status-dot-green"><span class="status-dot-icon"></span>Staffed</span>`;
                    } else if (c.isSolverPick && c.proposalId) {
                        acceptBtn = `<button class="btn btn-sm btn-success" onclick="app.acceptProposal(${c.proposalId})"><i class="fa-solid fa-check"></i> Accept Proposal</button>`;
                    } else {
                        acceptBtn = `<button class="btn btn-sm btn-outline" onclick="app.assignDeveloperToSlot(${slot.id}, ${c.devId})"><i class="fa-solid fa-user-plus"></i> Assign Candidate</button>`;
                    }

                    const skillMatch = c.totalReqs > 0
                        ? `<span class="skill-match-chip mono-text">${c.matchedSkills}/${c.totalReqs} skills</span>`
                        : '';

                    const flipAnimClass = (c.isSolverPick && this.isNewSolverRun) ? 'split-flap-in' : '';

                    return `
                        <div class="assignment-candidate-card ${c.isSolverPick ? 'solver-pick-card' : ''} ${flipAnimClass}">
                            <div class="candidate-info">
                                <div class="candidate-avatar ${c.isSolverPick ? 'avatar-solver' : ''}">
                                    <i class="fa-solid fa-user"></i>
                                </div>
                                <div>
                                    <strong>${escapeHtml(c.name)}</strong>
                                    <span class="candidate-subtitle">${escapeHtml(c.title || '')}</span>
                                </div>
                            </div>
                            <div class="candidate-meta-row">
                                ${solverBadge}
                                ${skillMatch}
                                <span class="status-dot-badge ${scoreClass} arrival-score">SCORE: ${c.score.toFixed(1)}</span>
                            </div>
                            ${acceptBtn}
                        </div>
                    `;
                }).join('');

                const remainingCount = eligibleOthers.length > 5 ? eligibleOthers.length - 5 : 0;
                const moreText = remainingCount > 0 ? `<div class="more-candidates-hint">+ ${remainingCount} more eligible candidate${remainingCount > 1 ? 's' : ''}</div>` : '';

                const headcountChip = isSlotFull
                    ? `<span class="status-dot-badge status-dot-green"><span class="status-dot-icon"></span>Staffed (${confirmedCount}/${slot.headcount_needed})</span>`
                    : `<span class="role-headcount mono-text">${confirmedCount}/${slot.headcount_needed} filled (${slot.headcount_needed - confirmedCount} open)</span>`;

                roleCardsHtml += `
                    <div class="role-slot-group">
                        <div class="role-slot-header">
                            <i class="fa-solid fa-briefcase"></i>
                            <strong>${escapeHtml(slot.role_title)}</strong>
                            ${headcountChip}
                            <span class="role-priority-chip mono-text">P${slot.priority}</span>
                        </div>
                        <div class="role-candidates-list">
                            ${isSlotFull
                                ? `<div style="font-size: 12px; color: var(--green); padding: 4px 8px; font-weight: 500;"><i class="fa-solid fa-circle-check"></i> All ${slot.headcount_needed} developer position(s) fully allocated.</div>`
                                : (displayCandidates.length > 0
                                    ? candidateRows
                                    : `<div class="empty-slot-notice"><i class="fa-solid fa-user-slash"></i> No eligible candidates found. <button class="btn btn-sm btn-outline" onclick="app.switchTab('management')" style="margin-left:8px;">Add Developers →</button></div>`)}
                            ${!isSlotFull ? moreText : ''}
                        </div>
                    </div>
                `;
            });

            if (!roleCardsHtml) return;

            html += `
                <details class="assignment-project-group" open>
                    <summary class="assignment-project-summary">
                        <div class="assignment-project-info">
                            <i class="fa-solid fa-folder-open"></i>
                            <strong>${escapeHtml(proj.name)}</strong>
                            <span class="client-tag">${escapeHtml(proj.client)}</span>
                        </div>
                        <span class="badge badge-solver mono-text">${(proj.slots || []).length} ROLE${(proj.slots || []).length > 1 ? 'S' : ''}</span>
                    </summary>
                    <div class="assignment-candidates-list">
                        ${roleCardsHtml}
                    </div>
                </details>
            `;
        });

        if (!hasAnySlots) {
            container.innerHTML = `<div style="text-align: center; color: var(--text-muted); padding: 30px 20px;">
                <i class="fa-solid fa-circle-check" style="font-size: 28px; color: var(--green); margin-bottom: 10px; display: block;"></i>
                No open role slots require candidate assignment.
            </div>`;
            this.isNewSolverRun = false;
            return;
        }

        container.innerHTML = html;
        // Reset flag so routine background polling or tab switches don't re-trigger split-flap
        this.isNewSolverRun = false;
    }

    renderProjectTeamRosters(allocations, proposals) {
        const container = document.getElementById('project-teams-container');
        if (!container) return;

        // Combine confirmed allocations and active proposed items by project
        const projectMap = {};

        (allocations || []).forEach(a => {
            const pName = a.project_name || 'General Project';
            if (!projectMap[pName]) projectMap[pName] = [];
            projectMap[pName].push({
                developer_name: a.developer_name,
                role_title: a.role_title,
                hours: a.allocated_hours,
                status: 'CONFIRMED'
            });
        });

        (proposals || []).filter(p => p.status === 'proposed').forEach(p => {
            const pName = p.project_name || 'General Project';
            if (!projectMap[pName]) projectMap[pName] = [];
            projectMap[pName].push({
                developer_name: p.developer_name,
                role_title: p.role_title,
                hours: 40,
                status: 'PROPOSED'
            });
        });

        if (Object.keys(projectMap).length === 0) {
            container.innerHTML = '<div class="card" style="padding: 20px; text-align: center; color: var(--text-muted);">No active project teams allocated yet.</div>';
            return;
        }

        let html = '';
        for (const [projName, teamMembers] of Object.entries(projectMap)) {
            const membersHtml = teamMembers.map(m => `
                <div style="background-color: #0e1424; border: 1px solid var(--border-color); border-radius: 8px; padding: 12px; display: flex; align-items: center; justify-content: space-between;">
                    <div>
                        <strong style="display: block; font-size: 14px;">${m.developer_name}</strong>
                        <span style="font-size: 12px; color: var(--text-muted);">${m.role_title} (${m.hours}h/wk)</span>
                    </div>
                    <span class="badge ${m.status === 'CONFIRMED' ? 'badge-emerald' : 'badge-solver'}">${m.status}</span>
                </div>
            `).join('');

            html += `
                <div class="card margin-bottom-lg">
                    <div class="card-header">
                        <h3><i class="fa-solid fa-folder-open"></i> Project: ${projName}</h3>
                        <span class="badge badge-emerald">${teamMembers.length} Developers Staffed</span>
                    </div>
                    <div class="card-body">
                        <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 14px;">
                            ${membersHtml}
                        </div>
                    </div>
                </div>
            `;
        }

        container.innerHTML = html;
    }

    renderProposals(proposals) {
        const container = document.getElementById('proposals-container');
        if (!container) return;

        const proposedList = (proposals || []).filter(p => p.status === 'proposed');
        if (proposedList.length === 0) {
            container.innerHTML = `<div class="card" style="padding: 35px; text-align: center; color: var(--text-muted);">
                <i class="fa-solid fa-circle-check" style="font-size: 36px; color: var(--emerald); margin-bottom: 12px; display: block;"></i>
                <h4 style="font-size: 16px; font-weight: 700; color: var(--text-main); margin-bottom: 4px;">All Proposed Allocations Reviewed</h4>
                <p style="font-size: 13px;">All algorithm proposals have been reviewed and accepted!</p>
            </div>`;
            return;
        }

        // Group proposals by Project Title
        const projectMap = {};
        proposedList.forEach(p => {
            const pName = (p.project_name || 'General Project').trim();
            if (!projectMap[pName]) projectMap[pName] = [];
            projectMap[pName].push(p);
        });

        // Developer rate & details lookup map
        const devMap = {};
        (this.developers || []).forEach(d => {
            devMap[d.id] = d;
        });

        // Project metadata lookup map
        const projMetadataMap = {};
        (this.projects || []).forEach(p => {
            projMetadataMap[p.name] = p;
        });

        let html = '';
        // Iterate over projects
        for (const [projName, projProposals] of Object.entries(projectMap)) {
            // Order developer proposals within this project by fit score in descending order
            projProposals.sort((a, b) => (parseFloat(b.fit_score) || 0) - (parseFloat(a.fit_score) || 0));

            const projMeta = projMetadataMap[projName];
            const clientName = projMeta?.client || 'Enterprise Client';
            const priorityVal = projMeta?.priority || 3;
            const avgFitScore = (projProposals.reduce((sum, p) => sum + (parseFloat(p.fit_score) || 0), 0) / projProposals.length).toFixed(1);

            const cardsHtml = projProposals.map(p => {
                const dev = devMap[p.developer];
                const cost = dev ? parseFloat(dev.hourly_cost || 0).toFixed(2) : null;
                const devSkills = dev?.developer_skills || [];
                const skillsHtml = devSkills.length > 0
                    ? devSkills.slice(0, 3).map(s => `<span class="role-skill-chip">${escapeHtml(s.skill_name)} <small>Lvl ${s.proficiency_level}</small></span>`).join('')
                    : '';

                return `
                    <div class="proposal-card">
                        <div class="proposal-header">
                            <div class="proposal-title">
                                <h4 class="clickable-dev-name" onclick="app.showDeveloperModal(${p.developer})" title="Click to view developer profile">
                                    ${escapeHtml(p.developer_name)} <i class="fa-solid fa-arrow-up-right-from-square" style="font-size: 10px; color: var(--primary);"></i>
                                </h4>
                                <span class="subtitle"><i class="fa-solid fa-user-tag" style="color: var(--primary); font-size: 11px;"></i> ${escapeHtml(p.developer_title || 'Developer')}</span>
                            </div>
                            <div style="text-align: right;">
                                <span class="proposal-score" title="Multi-objective algorithmic fit score">
                                    <i class="fa-solid fa-bolt" style="font-size: 12px; color: var(--emerald);"></i> ${parseFloat(p.fit_score).toFixed(1)}
                                </span>
                                <div style="font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px;">Fit Score</div>
                            </div>
                        </div>

                        <div class="proposal-body">
                            <div class="proposal-slot">
                                <i class="fa-solid fa-briefcase" style="color: var(--primary);"></i> <strong>Role Needed:</strong> <span class="role-needed-chip">${escapeHtml(p.role_title)}</span>
                            </div>
                            ${skillsHtml ? `<div class="dev-skills-wrap" style="margin-top: 8px; margin-bottom: 8px;">${skillsHtml}</div>` : ''}
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 10px; font-size: 12px; color: var(--text-muted);">
                                <span><i class="fa-solid fa-dollar-sign" style="color: var(--emerald);"></i> ${cost ? `$${cost}/hr` : 'Standard Rate'}</span>
                                <span class="badge badge-solver"><i class="fa-solid fa-microchip"></i> CP-SAT Pick</span>
                            </div>
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
                `;
            }).join('');

            html += `
                <div class="card margin-bottom-lg proposal-project-group-card">
                    <div class="card-header flex-between flex-wrap gap-md">
                        <div class="flex-align-center gap-md">
                            <div class="project-avatar-icon">
                                <i class="fa-solid fa-folder-open" style="color: var(--primary);"></i>
                            </div>
                            <div>
                                <h3 style="font-family: var(--font-heading); font-size: 17px; margin-bottom: 2px;">
                                    ${escapeHtml(projName)}
                                </h3>
                                <div style="font-size: 12px; color: var(--text-muted); display: flex; gap: 10px; align-items: center; flex-wrap: wrap;">
                                    <span><i class="fa-solid fa-building"></i> ${escapeHtml(clientName)}</span>
                                    <span class="badge badge-count">P${priorityVal} Priority</span>
                                </div>
                            </div>
                        </div>
                        <div style="display: flex; gap: 8px; align-items: center; flex-wrap: wrap;">
                            <span class="badge badge-solver">${projProposals.length} Proposed Role${projProposals.length > 1 ? 's' : ''}</span>
                            <span class="status-chip status-chip-emerald"><i class="fa-solid fa-star"></i> Avg Fit: <strong>${avgFitScore}</strong></span>
                            <button class="btn btn-sm btn-success" onclick="app.bulkAcceptForProject('${escapeHtml(projName)}')">
                                <i class="fa-solid fa-check-double"></i> Accept Project
                            </button>
                        </div>
                    </div>
                    <div class="card-body">
                        <div class="proposals-list-grid">
                            ${cardsHtml}
                        </div>
                    </div>
                </div>
            `;
        }

        container.innerHTML = html;
    }

    async bulkAcceptForProject(projectName) {
        const projectProposalIds = (this.proposals || [])
            .filter(p => p.status === 'proposed' && p.project_name === projectName)
            .map(p => p.id);

        if (projectProposalIds.length === 0) {
            this.showToast(`No pending proposals found for ${projectName}.`, 'info');
            return;
        }

        const { ok, status, data } = await this.safeFetchJson('/api/proposals/bulk-accept/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ proposal_ids: projectProposalIds })
        });

        if (status === 401 || status === 403) {
            this.showLoginModal(
                { callback: () => this.bulkAcceptForProject(projectName), name: `Accept All for ${projectName}` },
                `Staff login required to accept proposals for ${projectName}. Please log in.`
            );
            return;
        }

        if (ok && data) {
            this.showToast(`Accepted ${data.accepted_count} proposal(s) for ${projectName}.`, 'success');
            await this.loadAllData();
        } else {
            this.showToast(data?.error || 'Bulk accept for project failed.', 'warning');
        }
    }


    renderConfirmedAllocations(allocations) {
        const tbody = document.getElementById('confirmed-allocations-body');
        if (!tbody) return;

        if (allocations.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: var(--text-muted);">No confirmed allocations yet. Accept proposals above to commit staffing.</td></tr>';
            return;
        }

        tbody.innerHTML = allocations.map(a => {
            const isConfirmed = a.status === 'confirmed';
            const actionCell = isConfirmed
                ? `<button class="btn-cancel-alloc" onclick="app.cancelAllocation(${a.id})"><i class="fa-solid fa-ban"></i> Cancel</button>`
                : `<span style="color: var(--text-dim); font-size: 12px;">—</span>`;
            const badgeClass = isConfirmed ? 'badge-success' : 'badge-count';
            return `
                <tr>
                    <td><strong>${escapeHtml(a.developer_name)}</strong></td>
                    <td>${escapeHtml(a.project_name)}</td>
                    <td>${escapeHtml(a.role_title)}</td>
                    <td>${escapeHtml(a.start_date)} to ${escapeHtml(a.end_date)}</td>
                    <td>${a.allocated_hours}h / week</td>
                    <td><span class="badge ${badgeClass}">${escapeHtml(a.status).toUpperCase()}</span></td>
                    <td>${actionCell}</td>
                </tr>
            `;
        }).join('');
    }

    renderDeveloperMatrix(developers) {
        const tbody = document.getElementById('matrix-developers-body');
        if (!tbody) return;

        tbody.innerHTML = developers.map(d => {
            const skillsHtml = (d.developer_skills || []).map(s => 
                `<span class="badge badge-solver" style="margin-right: 4px; margin-bottom: 4px;">${escapeHtml(s.skill_name)} (Lvl ${s.proficiency_level})</span>`
            ).join('');

            return `
                <tr>
                    <td><strong>${escapeHtml(d.name)}</strong></td>
                    <td>${escapeHtml(d.title)}</td>
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
        const { ok, status, data } = await this.safeFetchJson(`/api/proposals/${id}/accept/`, { method: 'POST' });
        if (status === 401 || status === 403) {
            this.showLoginModal(
                { callback: () => this.acceptProposal(id), name: `Accept Proposal #${id}` },
                'Staff login required to accept candidate proposals. Please log in.'
            );
            return;
        }
        if (status === 409) {
            this.showToast(`Conflict Warning: ${data?.error || 'Developer is already committed to an overlapping allocation.'}`, 'warning');
        } else if (ok) {
            this.showToast('Candidate assignment confirmed!', 'success');
        } else {
            this.showToast(data?.error || 'Failed to accept proposal.', 'warning');
        }
        await this.loadAllData();
    }

    showToast(message, type = 'info') {
        let container = document.getElementById('toast-container');
        if (!container) {
            container = document.createElement('div');
            container.id = 'toast-container';
            container.className = 'toast-container';
            document.body.appendChild(container);
        }

        // Limit to max 5 visible toasts — dismiss oldest
        const existing = container.querySelectorAll('.toast-item');
        if (existing.length >= 5) {
            existing[0].remove();
        }

        const toast = document.createElement('div');
        toast.className = `toast-item toast-${type}`;
        const icon = type === 'success' ? 'fa-circle-check' : type === 'warning' ? 'fa-triangle-exclamation' : 'fa-circle-info';
        toast.innerHTML = `<i class="fa-solid ${icon}"></i> <span>${escapeHtml(message)}</span> <button class="toast-dismiss" onclick="this.parentElement.remove()"><i class="fa-solid fa-xmark"></i></button>`;

        container.appendChild(toast);

        setTimeout(() => {
            toast.classList.add('toast-fade-out');
            setTimeout(() => toast.remove(), 300);
        }, 4500);
    }

    dismissUploadAlert() {
        const container = document.getElementById('upload-results-container');
        if (container) container.innerHTML = '';
    }

    downloadSampleFile(type) {
        let content = '';
        let filename = '';
        let mimeType = 'text/plain';

        if (type === 'developers' || type === 'developer') {
            filename = 'sample_developers.csv';
            mimeType = 'text/csv';
            content = `name,email,title,hourly_cost,max_weekly_hours,skills\n"Sarah Jenkins","sarah.jenkins@company.com","Senior Full Stack Architect",95,40,"Python:5, Django:5, React:4"\n"Michael Chang","michael.chang@company.com","Lead Data Engineer",85,40,"Python:5, PostgreSQL:4, Spark:3"`;
        } else if (type === 'projects' || type === 'project') {
            filename = 'sample_projects.csv';
            mimeType = 'text/csv';
            content = `name,client,priority,budget,description,role_title,start_date,end_date,headcount_needed,required_skills\n"NextGen Cloud Migration","Enterprise Corp",5,150000,"Migrate legacy stack to Kubernetes","Cloud DevOps Engineer","2026-09-01","2026-12-31",2,"Kubernetes:4, Docker:4, AWS:3"`;
        } else {
            filename = 'sample_data.json';
            mimeType = 'application/json';
            content = JSON.stringify({
                developers: [
                    { name: "Sarah Jenkins", email: "sarah.j@company.com", title: "Senior Architect", hourly_cost: 95, skills: [{ name: "Python", level: 5 }] }
                ]
            }, null, 2);
        }

        const blob = new Blob([content], { type: mimeType });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

    async assignDeveloperToSlot(slotId, devId, startDate, endDate, weeklyHours) {
        if (!startDate || !endDate) {
            (this.projects || []).forEach(p => {
                (p.slots || []).forEach(s => {
                    if (s.id == slotId) {
                        startDate = s.start_date;
                        endDate = s.end_date;
                        weeklyHours = s.weekly_hours_required || 40;
                    }
                });
            });
        }
        if (!startDate) startDate = new Date().toISOString().split('T')[0];
        if (!endDate) endDate = new Date(Date.now() + 60*24*60*60*1000).toISOString().split('T')[0];
        if (!weeklyHours) weeklyHours = 40;

        const { ok, status, data } = await this.safeFetchJson('/api/allocations/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                developer: devId,
                project_slot: slotId,
                start_date: startDate,
                end_date: endDate,
                allocated_hours: weeklyHours,
                status: 'confirmed'
            })
        });

        if (status === 401 || status === 403) {
            this.showLoginModal(
                { callback: () => this.assignDeveloperToSlot(slotId, devId, startDate, endDate, weeklyHours), name: 'Assign Developer' },
                'Staff login required to assign developers. Please log in.'
            );
            return;
        }

        if (!ok) {
            let errMsg = data?.error || 'Failed to create assignment.';
            if (typeof data === 'object' && !data?.error) {
                const messages = [];
                for (const [k, v] of Object.entries(data)) {
                    const valStr = Array.isArray(v) ? v.join(' ') : String(v);
                    messages.push(`${k}: ${valStr}`);
                }
                if (messages.length > 0) errMsg = messages.join(' | ');
            }
            this.showToast(`Assignment Warning: ${errMsg}`, 'warning');
        } else {
            this.showToast('Developer assigned to project slot successfully!', 'success');
            await this.loadAllData();
        }
    }

    async rejectProposal(id) {
        const { ok, status, data } = await this.safeFetchJson(`/api/proposals/${id}/reject/`, { method: 'POST' });
        if (status === 401 || status === 403) {
            this.showLoginModal(
                { callback: () => this.rejectProposal(id), name: `Reject Proposal #${id}` },
                'Staff login required to reject proposals. Please log in.'
            );
            return;
        }
        if (ok) {
            this.showToast('Proposal rejected.', 'info');
            await this.loadAllData();
        } else {
            this.showToast(data?.error || 'Failed to reject proposal.', 'warning');
        }
    }

    async bulkAcceptProposals() {
        const proposedIds = this.proposals.filter(p => p.status === 'proposed').map(p => p.id);
        if (proposedIds.length === 0) {
            this.showToast('No pending proposals to accept.', 'info');
            return;
        }

        const { ok, status, data } = await this.safeFetchJson('/api/proposals/bulk-accept/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ proposal_ids: proposedIds })
        });

        if (status === 401 || status === 403) {
            this.showLoginModal(
                { callback: () => this.bulkAcceptProposals(), name: 'Bulk Accept Proposals' },
                'Staff login required for bulk proposal approval. Please log in.'
            );
            return;
        }

        if (ok && data) {
            this.showToast(`Bulk Approval Result: Accepted ${data.accepted_count} proposals. ${data.conflicts_count || 0} conflicting proposals auto-rejected.`, 'success');
            await this.loadAllData();
        } else {
            this.showToast(data?.error || 'Bulk accept failed.', 'warning');
        }
    }

    async addDeveloper() {
        const name = document.getElementById('dev-name').value;
        const email = document.getElementById('dev-email').value;
        const title = document.getElementById('dev-title').value;
        const cost = parseFloat(document.getElementById('dev-cost').value);

        const { ok, status, data } = await this.safeFetchJson('/api/developers/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, email, title, hourly_cost: cost, max_weekly_hours: 40 })
        });

        if (status === 401 || status === 403) {
            this.showLoginModal(
                { callback: () => this.addDeveloper(), name: 'Add Developer' },
                'Staff login required to add developers. Please log in.'
            );
            return;
        }

        if (ok) {
            document.getElementById('form-add-developer').reset();
            this.showToast('Developer added successfully!', 'success');
            await this.loadAllData();
        } else {
            this.showToast(data?.error || 'Failed to add developer.', 'warning');
        }
    }

    async addSlot() {
        const projectId = parseInt(document.getElementById('slot-project-id').value);
        const roleTitle = document.getElementById('slot-role').value;
        const priority = parseInt(document.getElementById('slot-priority').value);
        const headcount = parseInt(document.getElementById('slot-headcount').value);

        const today = new Date().toISOString().split('T')[0];
        const nextMonth = new Date(Date.now() + 60*24*60*60*1000).toISOString().split('T')[0];

        const { ok, status, data } = await this.safeFetchJson('/api/slots/', {
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

        if (status === 401 || status === 403) {
            this.showLoginModal(
                { callback: () => this.addSlot(), name: 'Add Project Slot' },
                'Staff login required to add project slots. Please log in.'
            );
            return;
        }

        if (ok) {
            document.getElementById('form-add-slot').reset();
            this.showToast('Project slot added successfully!', 'success');
            await this.loadAllData();
        } else {
            this.showToast(data?.error || 'Failed to add project slot.', 'warning');
        }
    }


    updateBadgeCount() {
        const pendingCount = this.proposals.filter(p => p.status === 'proposed').length;
        const badge = document.getElementById('pending-proposals-badge');
        if (badge) badge.textContent = pendingCount;
    }

    bindRulesTabEvents() {
        const tabBtns = document.querySelectorAll('.rules-tab-btn');
        tabBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                const targetTab = btn.getAttribute('data-ruletab');
                tabBtns.forEach(b => b.classList.remove('active'));
                btn.classList.add('active');

                document.querySelectorAll('.rule-pane').forEach(pane => pane.style.display = 'none');
                const activePane = document.getElementById(`ruletab-${targetTab}`);
                if (activePane) activePane.style.display = 'block';
            });
        });
    }

    bindFileUploadEvents() {
        // Dropzone 1: Developers
        const devDropzone = document.getElementById('dev-dropzone');
        const devInput = document.getElementById('dev-file-input');
        const devBtn = document.getElementById('btn-upload-devs');
        const devDisplay = document.getElementById('dev-file-name-display');

        if (devDropzone && devInput) {
            devDropzone.addEventListener('click', () => devInput.click());
            devInput.addEventListener('change', (e) => {
                if (e.target.files.length > 0) {
                    this.selectedDevFile = e.target.files[0];
                    if (devDisplay) {
                        devDisplay.textContent = `Selected: ${this.selectedDevFile.name}`;
                        devDisplay.style.display = 'inline-block';
                    }
                    if (devBtn) devBtn.disabled = false;
                }
            });

            ['dragover', 'dragenter'].forEach(eventName => {
                devDropzone.addEventListener(eventName, (e) => {
                    e.preventDefault();
                    devDropzone.classList.add('dragover');
                });
            });

            ['dragleave', 'drop'].forEach(eventName => {
                devDropzone.addEventListener(eventName, (e) => {
                    e.preventDefault();
                    devDropzone.classList.remove('dragover');
                });
            });

            devDropzone.addEventListener('drop', (e) => {
                if (e.dataTransfer.files.length > 0) {
                    this.selectedDevFile = e.dataTransfer.files[0];
                    devInput.files = e.dataTransfer.files;
                    if (devDisplay) {
                        devDisplay.textContent = `Selected: ${this.selectedDevFile.name}`;
                        devDisplay.style.display = 'inline-block';
                    }
                    if (devBtn) devBtn.disabled = false;
                }
            });
        }

        // Dropzone 2: Projects
        const projDropzone = document.getElementById('proj-dropzone');
        const projInput = document.getElementById('proj-file-input');
        const projBtn = document.getElementById('btn-upload-projects');
        const projDisplay = document.getElementById('proj-file-name-display');

        if (projDropzone && projInput) {
            projDropzone.addEventListener('click', () => projInput.click());
            projInput.addEventListener('change', (e) => {
                if (e.target.files.length > 0) {
                    this.selectedProjFile = e.target.files[0];
                    if (projDisplay) {
                        projDisplay.textContent = `Selected: ${this.selectedProjFile.name}`;
                        projDisplay.style.display = 'inline-block';
                    }
                    if (projBtn) projBtn.disabled = false;
                }
            });

            ['dragover', 'dragenter'].forEach(eventName => {
                projDropzone.addEventListener(eventName, (e) => {
                    e.preventDefault();
                    projDropzone.classList.add('dragover');
                });
            });

            ['dragleave', 'drop'].forEach(eventName => {
                projDropzone.addEventListener(eventName, (e) => {
                    e.preventDefault();
                    projDropzone.classList.remove('dragover');
                });
            });

            projDropzone.addEventListener('drop', (e) => {
                if (e.dataTransfer.files.length > 0) {
                    this.selectedProjFile = e.dataTransfer.files[0];
                    projInput.files = e.dataTransfer.files;
                    if (projDisplay) {
                        projDisplay.textContent = `Selected: ${this.selectedProjFile.name}`;
                        projDisplay.style.display = 'inline-block';
                    }
                    if (projBtn) projBtn.disabled = false;
                }
            });
        }

        // Process buttons
        devBtn?.addEventListener('click', () => this.uploadDeveloperFile());
        projBtn?.addEventListener('click', () => this.uploadProjectFile());

        // Download samples
        document.getElementById('btn-download-dev-sample')?.addEventListener('click', () => {
            this.downloadSampleFile('employee');
        });
        document.getElementById('btn-download-proj-sample')?.addEventListener('click', () => {
            this.downloadSampleFile('project');
        });
    }

    async uploadDeveloperFile() {
        const file = this.selectedDevFile || document.getElementById('dev-file-input')?.files[0];
        if (!file) {
            alert('Please select or drop a valid Employee JSON or CSV file.');
            return;
        }

        const formData = new FormData();
        formData.append('file', file);

        const btn = document.getElementById('btn-upload-devs');
        if (btn) btn.disabled = true;

        try {
            const { ok, status, data } = await this.safeFetchJson('/api/developers/upload/', {
                method: 'POST',
                body: formData
            });

            if (status === 401 || status === 403) {
                this.showLoginModal(
                    { callback: () => this.uploadDeveloperFile(), name: 'Upload Developer File' },
                    'Staff login required to upload employee data. Please log in.'
                );
                return;
            }

            const result = data || {};
            this.renderUploadResults(result, 'Employee');

            if (result.success || result.imported_count > 0 || result.updated_count > 0) {
                await this.loadAllData();
            }
        } catch (err) {
            console.error('Error uploading employee file:', err);
            this.renderUploadResults({
                success: false,
                errors: [`Network or server error processing file: ${err.message}`]
            }, 'Employee');
        } finally {
            if (btn) btn.disabled = false;
        }
    }

    async uploadProjectFile() {
        const file = this.selectedProjFile || document.getElementById('proj-file-input')?.files[0];
        if (!file) {
            alert('Please select or drop a valid Project JSON or CSV file.');
            return;
        }

        const formData = new FormData();
        formData.append('file', file);

        const btn = document.getElementById('btn-upload-projects');
        if (btn) btn.disabled = true;

        try {
            const { ok, status, data } = await this.safeFetchJson('/api/projects/upload/', {
                method: 'POST',
                body: formData
            });

            if (status === 401 || status === 403) {
                this.showLoginModal(
                    { callback: () => this.uploadProjectFile(), name: 'Upload Project File' },
                    'Staff login required to upload project data. Please log in.'
                );
                return;
            }

            const result = data || {};
            this.renderUploadResults(result, 'Project');

            if (result.success || result.imported_projects_count > 0 || result.imported_slots_count > 0) {
                await this.loadAllData();
            }
        } catch (err) {
            console.error('Error uploading project file:', err);
            this.renderUploadResults({
                success: false,
                errors: [`Network or server error processing file: ${err.message}`]
            }, 'Project');
        } finally {
            if (btn) btn.disabled = false;
        }
    }

    dismissUploadAlert() {
        const container = document.getElementById('upload-results-box');
        if (container) container.style.display = 'none';
    }


    renderUploadResults(result, type) {
        const container = document.getElementById('upload-results-box');
        if (!container) return;

        container.style.display = 'block';
        container.className = 'results-alert-box ' + (result.success ? 'success' : 'danger');

        let html = '';
        if (result.success) {
            html += `
                <div class="upload-alert-header flex-between flex-wrap gap-md">
                    <div class="flex-align-center gap-md">
                        <div class="alert-icon-wrap icon-success"><i class="fa-solid fa-circle-check"></i></div>
                        <div>
                            <h4 class="alert-title">${type} Import Processed Successfully</h4>
                            <p class="alert-subtitle">File processed cleanly with no breaking format errors.</p>
                        </div>
                    </div>
                    <button class="btn btn-sm btn-outline btn-dismiss-alert" onclick="app.dismissUploadAlert()">
                        <i class="fa-solid fa-xmark"></i> Dismiss
                    </button>
                </div>
                <div class="upload-alert-body">
            `;

            if (type === 'Employee') {
                html += `<div class="upload-metrics-row">
                    <span class="metric-chip metric-emerald"><i class="fa-solid fa-user-plus"></i> <strong>${result.imported_count || 0}</strong> New Developers</span>
                    <span class="metric-chip metric-purple"><i class="fa-solid fa-user-pen"></i> <strong>${result.updated_count || 0}</strong> Updated Records</span>
                </div>`;
            } else {
                html += `<div class="upload-metrics-row">
                    <span class="metric-chip metric-emerald"><i class="fa-solid fa-folder-plus"></i> <strong>${result.imported_projects_count || 0}</strong> Projects</span>
                    <span class="metric-chip metric-purple"><i class="fa-solid fa-layer-group"></i> <strong>${result.imported_slots_count || 0}</strong> Role Slots</span>
                </div>`;
            }

            if (result.warnings && result.warnings.length > 0) {
                html += `
                    <details class="upload-warnings-details">
                        <summary class="upload-warnings-summary">
                            <i class="fa-solid fa-triangle-exclamation" style="color: var(--amber);"></i>
                            <span>${result.warnings.length} Warning(s) / Auto-Created References</span>
                        </summary>
                        <ul class="upload-warning-list">
                            ${result.warnings.map(w => `<li>${w}</li>`).join('')}
                        </ul>
                    </details>
                `;
            }
            html += `</div>`;
        } else {
            const rawErrors = result.errors || (result.error ? [result.error] : ['Unknown format validation failure']);
            const totalCount = rawErrors.length;

            // Group errors by reason type
            const categoryCounts = {};
            const parsedRows = [];

            rawErrors.forEach(errStr => {
                const match = errStr.match(/^Row\s+(\d+)(?:\s*\((.*?)\))?:\s*(.*)$/i);
                if (match) {
                    const rowNum = parseInt(match[1]);
                    const entityName = match[2] || '';
                    const reason = match[3].trim();

                    let category = 'Validation Error';
                    if (reason.toLowerCase().includes('missing developer name')) category = 'Missing Developer Name';
                    else if (reason.toLowerCase().includes('missing email')) category = 'Missing Email Address';
                    else if (reason.toLowerCase().includes('invalid email')) category = 'Invalid Email Format';
                    else if (reason.toLowerCase().includes('hourly cost')) category = 'Invalid Hourly Cost';
                    else if (reason.toLowerCase().includes('weekly hours')) category = 'Invalid Weekly Hours';
                    else category = reason;

                    categoryCounts[category] = (categoryCounts[category] || 0) + 1;
                    parsedRows.push({ rowNum, entityName, reason, category, raw: errStr });
                } else {
                    categoryCounts['File Format Error'] = (categoryCounts['File Format Error'] || 0) + 1;
                    parsedRows.push({ rowNum: null, entityName: '', reason: errStr, category: 'File Format Error', raw: errStr });
                }
            });

            const categoryChipsHtml = Object.entries(categoryCounts).map(([cat, count]) => `
                <span class="error-category-chip">
                    <i class="fa-solid fa-circle-exclamation"></i> ${cat}: <strong>${count}</strong>
                </span>
            `).join('');

            // Group contiguous identical error reasons across row ranges (e.g., Rows 1-36: Missing developer name)
            const groupedErrors = [];
            let currentGroup = null;

            parsedRows.forEach(item => {
                if (currentGroup && currentGroup.reason === item.reason && item.rowNum !== null && currentGroup.endRow + 1 === item.rowNum) {
                    currentGroup.endRow = item.rowNum;
                    currentGroup.count++;
                } else {
                    if (currentGroup) groupedErrors.push(currentGroup);
                    currentGroup = {
                        startRow: item.rowNum,
                        endRow: item.rowNum,
                        count: 1,
                        reason: item.reason,
                        category: item.category,
                        entityName: item.entityName
                    };
                }
            });
            if (currentGroup) groupedErrors.push(currentGroup);

            const errorRowsHtml = groupedErrors.map(g => {
                let rangeLabel = '';
                if (g.startRow === null) {
                    rangeLabel = `<span class="row-num-badge alert-tag">Format Alert</span>`;
                } else if (g.startRow === g.endRow) {
                    rangeLabel = `<span class="row-num-badge">Row ${g.startRow}</span>`;
                } else {
                    rangeLabel = `<span class="row-num-badge">Rows ${g.startRow}–${g.endRow}</span>`;
                }

                const countBadge = g.count > 1 ? `<span class="entity-name-tag">${g.count} rows</span>` : '';
                const entityTag = g.entityName ? `<span class="entity-name-tag">${g.entityName}</span>` : '';
                return `
                    <div class="error-list-item">
                        ${rangeLabel}
                        ${countBadge}
                        ${entityTag}
                        <span class="error-text-desc">${g.reason}</span>
                    </div>
                `;
            }).join('');

            html += `
                <div class="upload-alert-header flex-between flex-wrap gap-md">
                    <div class="flex-align-center gap-md">
                        <div class="alert-icon-wrap icon-danger"><i class="fa-solid fa-triangle-exclamation"></i></div>
                        <div>
                            <h4 class="alert-title">${type} Import Validation Failed</h4>
                            <p class="alert-subtitle">Found <strong>${totalCount}</strong> validation issue${totalCount > 1 ? 's' : ''} in the uploaded file.</p>
                        </div>
                    </div>
                    <div style="display: flex; gap: 8px; flex-wrap: wrap;">
                        <button class="btn btn-sm btn-outline" onclick="app.downloadSampleFile('${type.toLowerCase()}')">
                            <i class="fa-solid fa-download"></i> Sample Format
                        </button>
                        <button class="btn btn-sm btn-outline btn-dismiss-alert" onclick="app.dismissUploadAlert()">
                            <i class="fa-solid fa-xmark"></i> Dismiss
                        </button>
                    </div>
                </div>

                <div class="upload-alert-body">
                    <div class="error-category-bar">
                        ${categoryChipsHtml}
                    </div>

                    <details class="upload-errors-details" open>
                        <summary class="upload-errors-summary">
                            <i class="fa-solid fa-list-check"></i> View Detailed Validation Issues (${totalCount})
                            <span class="summary-toggle-hint">Click to collapse/expand</span>
                        </summary>
                        <div class="error-details-scroll">
                            ${errorRowsHtml}
                        </div>
                    </details>

                    <div class="error-help-footer">
                        <i class="fa-solid fa-lightbulb" style="color: var(--amber);"></i>
                        <span><strong>Tip:</strong> Ensure all mandatory columns (e.g., <code>name</code> and <code>email</code> for developers) are filled and header names match the expected format specs.</span>
                    </div>
                </div>
            `;
        }

        container.innerHTML = html;
        container.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    renderRoleWorkforceDashboard() {
        const container = document.getElementById('role-workforce-container');
        if (!container) return;

        const developers = this.developers || [];
        const allocations = this.allocations || [];
        const proposals = this.proposals || [];

        const searchVal = (document.getElementById('role-search-input')?.value || '').toLowerCase().trim();
        const statusFilter = document.getElementById('role-status-filter')?.value || 'all';
        const skillSelect = document.getElementById('role-skill-filter');
        const skillFilter = (skillSelect?.value || 'all').toLowerCase().trim();

        // Populate dynamic skills in skill dropdown if needed
        if (skillSelect) {
            const currentVal = skillSelect.value;
            const uniqueSkills = new Set();
            developers.forEach(d => {
                (d.developer_skills || []).forEach(ds => {
                    if (ds.skill_name) uniqueSkills.add(ds.skill_name);
                });
            });
            // Ensure core skills are present
            ['Python', 'Django', 'React', 'AWS', 'Kubernetes', 'Go', 'PyTorch', 'PostgreSQL', 'TypeScript', 'Node.js', 'Redis'].forEach(s => uniqueSkills.add(s));
            
            const sortedSkills = Array.from(uniqueSkills).sort();
            const optionsHtml = ['<option value="all">All Skills</option>']
                .concat(sortedSkills.map(s => `<option value="${s.toLowerCase()}" ${s.toLowerCase() === currentVal.toLowerCase() ? 'selected' : ''}>${s}</option>`))
                .join('');
            
            if (skillSelect.dataset.populated !== sortedSkills.join(',')) {
                skillSelect.innerHTML = optionsHtml;
                skillSelect.dataset.populated = sortedSkills.join(',');
                if (currentVal) skillSelect.value = currentVal;
            }
        }

        // Lookup of confirmed allocations by dev id
        const allocationByDev = {};
        allocations.filter(a => a.status === 'confirmed').forEach(a => {
            allocationByDev[a.developer] = a;
        });

        // Lookup of active proposals by dev id
        const proposalByDev = {};
        proposals.filter(p => p.status === 'proposed').forEach(p => {
            proposalByDev[p.developer] = p;
        });

        // First pass: Build devItem models for all developers
        const allDevItems = developers.map(dev => {
            const role = (dev.title || 'Senior Software Engineer').trim();
            const devAllocations = allocations.filter(a => a.developer === dev.id);
            const confirmedAlloc = devAllocations.find(a => a.status === 'confirmed');
            const activeProp = proposalByDev[dev.id];

            const pastAllocations = devAllocations
                .filter(a => a !== confirmedAlloc)
                .sort((a, b) => new Date(b.end_date || '1970-01-01') - new Date(a.end_date || '1970-01-01'));
            const lastAllocation = pastAllocations.length > 0 ? pastAllocations[0] : null;

            let devStatus = 'BENCH';
            let currentProject = null;
            let currentRoleSlot = null;
            let startDate = null;
            let endDate = null;
            let weeklyHours = 0;

            if (confirmedAlloc) {
                devStatus = 'WORKING';
                currentProject = confirmedAlloc.project_name;
                currentRoleSlot = confirmedAlloc.role_title;
                startDate = confirmedAlloc.start_date;
                endDate = confirmedAlloc.end_date;
                weeklyHours = confirmedAlloc.allocated_hours;
            } else if (activeProp) {
                devStatus = 'PROPOSED';
                currentProject = activeProp.project_name;
                currentRoleSlot = activeProp.role_title;
                startDate = activeProp.start_date || 'Upcoming';
                endDate = activeProp.end_date || 'TBD';
                weeklyHours = 40;
            } else {
                devStatus = 'BENCH';
            }

            const cost = parseFloat(dev.hourly_cost || 0);

            return {
                id: dev.id,
                name: dev.name,
                email: dev.email,
                title: role,
                cost: cost,
                maxHours: dev.max_weekly_hours,
                status: devStatus,
                project: currentProject,
                slotRole: currentRoleSlot,
                startDate: startDate,
                endDate: endDate,
                lastAllocation: lastAllocation,
                hours: weeklyHours,
                skills: (dev.developer_skills || []).map(ds => ({
                    name: ds.skill_name,
                    level: ds.proficiency_level
                }))
            };
        });

        // Filter developers based on user search & filter
        const filteredDevs = allDevItems.filter(d => {
            const matchesSearch = !searchVal || 
                d.name.toLowerCase().includes(searchVal) || 
                d.email.toLowerCase().includes(searchVal) || 
                d.title.toLowerCase().includes(searchVal) ||
                (d.project && d.project.toLowerCase().includes(searchVal)) ||
                (d.slotRole && d.slotRole.toLowerCase().includes(searchVal)) ||
                (d.lastAllocation && d.lastAllocation.project_name.toLowerCase().includes(searchVal)) ||
                d.skills.some(s => s.name.toLowerCase().includes(searchVal));

            const matchesStatus = statusFilter === 'all' ||
                (statusFilter === 'working' && (d.status === 'WORKING' || d.status === 'PROPOSED')) ||
                (statusFilter === 'bench' && d.status === 'BENCH');

            const matchesSkill = skillFilter === 'all' ||
                d.skills.some(s => s.name.toLowerCase().includes(skillFilter));

            return matchesSearch && matchesStatus && matchesSkill;
        });

        // Group filtered developers by role
        const filteredRoleMap = {};
        let filteredWorking = 0;
        let filteredBench = 0;
        let filteredCostSum = 0;

        filteredDevs.forEach(d => {
            const role = d.title;
            if (!filteredRoleMap[role]) {
                filteredRoleMap[role] = {
                    roleTitle: role,
                    developers: [],
                    workingCount: 0,
                    benchCount: 0,
                    totalCost: 0
                };
            }
            filteredRoleMap[role].developers.push(d);
            filteredRoleMap[role].totalCost += d.cost;
            filteredCostSum += d.cost;

            if (d.status === 'WORKING' || d.status === 'PROPOSED') {
                filteredWorking++;
                filteredRoleMap[role].workingCount++;
            } else {
                filteredBench++;
                filteredRoleMap[role].benchCount++;
            }
        });

        // Update KPI Stats Cards based on filtered dataset
        const isFiltered = searchVal !== '' || statusFilter !== 'all' || skillFilter !== 'all';
        const distinctRolesCount = Object.keys(filteredRoleMap).length;
        const avgHourlyCost = filteredDevs.length > 0 ? (filteredCostSum / filteredDevs.length).toFixed(2) : '0.00';

        const elTotalRoles = document.getElementById('role-stat-total-roles');
        const elWorkingDevs = document.getElementById('role-stat-working-devs');
        const elBenchDevs = document.getElementById('role-stat-bench-devs');
        const elAvgCost = document.getElementById('role-stat-avg-cost');
        const elGroupBadge = document.getElementById('role-groups-count-badge');

        if (elTotalRoles) elTotalRoles.textContent = distinctRolesCount;
        if (elWorkingDevs) elWorkingDevs.textContent = filteredWorking;
        if (elBenchDevs) elBenchDevs.textContent = filteredBench;
        if (elAvgCost) elAvgCost.textContent = `$${avgHourlyCost}/hr`;
        if (elGroupBadge) elGroupBadge.textContent = `${distinctRolesCount} Role Categories${isFiltered ? ' (Filtered)' : ''}`;

        // Render Chart with filteredRoleMap and statusFilter
        this.renderRoleDistributionChart(filteredRoleMap, statusFilter);

        if (filteredDevs.length === 0) {
            container.innerHTML = `<div class="card" style="padding: 30px; text-align: center; color: var(--text-muted);">
                <i class="fa-solid fa-filter-circle-xmark" style="font-size: 28px; margin-bottom: 10px; display: block; color: var(--amber);"></i>
                <strong>No developers match the active filters.</strong>
                <p style="font-size: 12px; margin-top: 6px;">Try adjusting your search query, status dropdown, or skill filter.</p>
            </div>`;
            return;
        }

        let html = '';
        Object.values(filteredRoleMap).forEach(group => {
            const avgRoleRate = (group.totalCost / group.developers.length).toFixed(2);

            const devCardsHtml = group.developers.map(d => {
                const isWorking = d.status === 'WORKING' || d.status === 'PROPOSED';
                const statusBadge = d.status === 'WORKING'
                    ? `<span class="badge badge-emerald"><i class="fa-solid fa-briefcase"></i> ALLOCATED</span>`
                    : d.status === 'PROPOSED'
                        ? `<span class="badge badge-solver"><i class="fa-solid fa-clock"></i> PROPOSED</span>`
                        : `<span class="badge badge-amber"><i class="fa-solid fa-couch"></i> ON BENCH</span>`;

                const projectInfo = isWorking
                    ? `
                        <div class="dev-project-tag working-tag">
                            <div class="flex-between margin-bottom-xs">
                                <span><i class="fa-solid fa-folder-open" style="color: var(--emerald);"></i> <strong>${escapeHtml(d.project)}</strong> (${escapeHtml(d.slotRole || 'Engineer')})</span>
                                <span style="font-size: 11px; font-weight: 600; color: var(--emerald);">${d.hours}h/wk</span>
                            </div>
                            <div class="dev-timeline-info" style="font-size: 11px; color: var(--text-muted); display: flex; align-items: center; gap: 6px; margin-top: 4px;">
                                <i class="fa-solid fa-calendar-days" style="color: var(--emerald);"></i>
                                <span>Current Timeline: <strong style="color: var(--text-main);">${d.startDate}</strong> to <strong style="color: var(--text-main);">${d.endDate}</strong></span>
                            </div>
                        </div>
                    `
                    : `
                        <div class="dev-project-tag bench-tag">
                            ${d.lastAllocation ? `
                                <div class="flex-between margin-bottom-xs">
                                    <span><i class="fa-solid fa-clock-rotate-left" style="color: var(--amber);"></i> <strong>Previously Worked On:</strong> ${escapeHtml(d.lastAllocation.project_name)}</span>
                                    <span style="font-size: 11px; color: var(--text-muted);">${escapeHtml(d.lastAllocation.role_title)}</span>
                                </div>
                                <div class="dev-timeline-info" style="font-size: 11px; color: var(--amber); display: flex; align-items: center; gap: 6px; margin-top: 4px;">
                                    <i class="fa-solid fa-calendar-check"></i>
                                    <span>Past Duration: <strong>${d.lastAllocation.start_date}</strong> to <strong>${d.lastAllocation.end_date}</strong></span>
                                </div>
                            ` : `
                                <div style="font-size: 12px; color: var(--amber);"><i class="fa-solid fa-circle-dot"></i> On Bench · No prior project history recorded</div>
                                <div style="font-size: 11px; color: var(--text-dim); margin-top: 2px;">Available for immediate assignment (${d.maxHours}h/wk capacity)</div>
                            `}
                        </div>
                    `;

                const skillsHtml = d.skills.length > 0
                    ? d.skills.map(s => `<span class="role-skill-chip">${escapeHtml(s.name)} <small>Lvl ${s.level}</small></span>`).join('')
                    : `<span style="font-size: 11px; color: var(--text-dim);">No skills listed</span>`;

                return `
                    <div class="dev-role-member-card ${isWorking ? 'working-dev-card' : 'bench-dev-card'}">
                        <div class="dev-member-top flex-between">
                            <div class="dev-member-info">
                                <div class="dev-avatar ${isWorking ? 'avatar-active' : 'avatar-bench'}">
                                    <i class="fa-solid fa-user"></i>
                                </div>
                                <div>
                                    <h4 class="dev-name clickable-dev-name" onclick="app.showDeveloperModal(${d.id})" title="Click to view full developer profile">${escapeHtml(d.name)} <i class="fa-solid fa-arrow-up-right-from-square" style="font-size: 10px; color: var(--primary);"></i></h4>
                                    <span class="dev-email"><i class="fa-solid fa-envelope"></i> ${escapeHtml(d.email)}</span>
                                </div>
                            </div>
                            <div style="text-align: right;">
                                ${statusBadge}
                                <div class="dev-rate-text">$${d.cost.toFixed(2)}/hr</div>
                            </div>
                        </div>

                        ${projectInfo}

                        <div class="dev-member-skills-row">
                            <span class="skills-label"><i class="fa-solid fa-code"></i> Skills:</span>
                            <div class="dev-skills-wrap">${skillsHtml}</div>
                        </div>
                    </div>
                `;
            }).join('');

            html += `
                <div class="card margin-bottom-lg role-group-card">
                    <div class="card-header flex-between flex-wrap gap-md">
                        <div class="role-group-title">
                            <i class="fa-solid fa-user-tag" style="color: var(--primary);"></i>
                            <h3>${escapeHtml(group.roleTitle)}</h3>
                            <span class="badge badge-solver">${group.developers.length} Developer${group.developers.length > 1 ? 's' : ''}</span>
                        </div>
                        <div class="role-group-summary-badges">
                            <span class="status-chip status-chip-emerald"><strong>${group.workingCount}</strong> Working</span>
                            <span class="status-chip status-chip-amber"><strong>${group.benchCount}</strong> On Bench</span>
                            <span class="status-chip status-chip-purple"><strong>$${avgRoleRate}</strong> Avg Rate</span>
                        </div>
                    </div>
                    <div class="card-body">
                        <div class="role-members-grid">
                            ${devCardsHtml}
                        </div>
                    </div>
                </div>
            `;
        });

        container.innerHTML = html;
    }

    renderRoleDistributionChart(roleMap, statusFilter = 'all') {
        const ctx = document.getElementById('roleDistributionChart');
        if (!ctx) return;
        if (typeof Chart === 'undefined') {
            console.warn('Chart.js unavailable -- skipping role distribution chart.');
            return;
        }

        if (this.roleDistributionChartInstance) {
            this.roleDistributionChartInstance.destroy();
            this.roleDistributionChartInstance = null;
        }

        const labels = Object.keys(roleMap);
        const { textColor, gridColor } = this.getChartThemeColors();

        if (labels.length === 0) {
            // Render an empty chart state
            this.roleDistributionChartInstance = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: ['No matching roles'],
                    datasets: [{
                        label: 'No Data',
                        data: [0],
                        backgroundColor: 'rgba(255,255,255,0.05)'
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        x: { ticks: { color: textColor }, grid: { display: false } },
                        y: { beginAtZero: true, max: 1, ticks: { color: textColor, stepSize: 1 }, grid: { color: gridColor } }
                    },
                    plugins: {
                        legend: { display: false }
                    }
                }
            });
            return;
        }

        const workingData = labels.map(r => roleMap[r].workingCount);
        const benchData = labels.map(r => roleMap[r].benchCount);

        const datasets = [];
        if (statusFilter === 'all' || statusFilter === 'working') {
            datasets.push({
                label: 'Working / Staffed',
                data: workingData,
                backgroundColor: '#10b981',
                borderRadius: 4
            });
        }
        if (statusFilter === 'all' || statusFilter === 'bench') {
            datasets.push({
                label: 'On Bench',
                data: benchData,
                backgroundColor: '#f59e0b',
                borderRadius: 4
            });
        }

        this.roleDistributionChartInstance = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: datasets
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: {
                        stacked: true,
                        ticks: {
                            color: textColor,
                            font: { size: 11 },
                            maxRotation: 45,
                            minRotation: 20
                        },
                        grid: { display: false }
                    },
                    y: {
                        stacked: true,
                        beginAtZero: true,
                        ticks: { color: textColor, stepSize: 1 },
                        grid: { color: gridColor }
                    }
                },
                plugins: {
                    legend: {
                        position: 'top',
                        labels: { color: textColor, boxWidth: 12, padding: 12 }
                    },
                    tooltip: {
                        mode: 'index',
                        intersect: false
                    }
                }
            }
        });

    }


    // ===== Item 10: Developer Profile Detail Modal =====
    showDeveloperModal(devId) {
        const dev = (this.developers || []).find(d => d.id === devId);
        if (!dev) return;

        const modal = document.getElementById('developer-detail-modal');
        const body = document.getElementById('developer-detail-modal-body');
        if (!modal || !body) return;

        const devSkills = dev.developer_skills || [];
        const devAllocs = (this.allocations || []).filter(a => a.developer === dev.id);
        const activeAlloc = devAllocs.find(a => a.status === 'confirmed' && new Date(a.end_date) >= new Date());
        const pastAllocs = devAllocs.filter(a => a !== activeAlloc).sort((a, b) => new Date(b.end_date) - new Date(a.end_date));
        const leaves = dev.leaves || [];

        const initials = dev.name.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase();

        const skillsBarsHtml = devSkills.length > 0
            ? devSkills.map(s => {
                const pct = (s.proficiency_level / 5) * 100;
                return `
                    <div class="skill-meter-item">
                        <div class="skill-meter-header">
                            <span>${escapeHtml(s.skill_name)}</span>
                            <span style="color: var(--primary);">Lvl ${s.proficiency_level} / 5</span>
                        </div>
                        <div class="skill-progress-bar">
                            <div class="skill-progress-fill" style="width: ${pct}%;"></div>
                        </div>
                    </div>
                `;
            }).join('')
            : '<p style="color: var(--text-muted); font-size: 13px;">No skill ratings recorded.</p>';

        const allocsHistoryHtml = devAllocs.length > 0
            ? devAllocs.map(a => {
                const isConfirmed = a.status === 'confirmed';
                return `
                    <div class="history-timeline-item">
                        <div style="font-size: 18px; color: ${isConfirmed ? 'var(--green)' : 'var(--text-muted)'};">
                            <i class="fa-solid ${isConfirmed ? 'fa-circle-check' : 'fa-clock-rotate-left'}"></i>
                        </div>
                        <div style="flex: 1;">
                            <div class="flex-between">
                                <strong>${escapeHtml(a.project_name)}</strong>
                                <span class="badge ${isConfirmed ? 'badge-emerald' : 'badge-count'}">${a.status.toUpperCase()}</span>
                            </div>
                            <div style="color: var(--text-muted); font-size: 12px; margin-top: 2px;">
                                <span>${escapeHtml(a.role_title)}</span> · <span>${a.allocated_hours}h/week</span>
                            </div>
                            <div style="color: var(--text-dim); font-size: 11px; margin-top: 2px;">
                                ${a.start_date} to ${a.end_date}
                            </div>
                        </div>
                    </div>
                `;
            }).join('')
            : '<p style="color: var(--text-muted); font-size: 13px;">No project allocations on record yet.</p>';

        const leavesHtml = leaves.length > 0
            ? leaves.map(l => `
                <div class="history-timeline-item">
                    <div style="color: var(--purple); font-size: 16px;"><i class="fa-solid fa-umbrella-beach"></i></div>
                    <div>
                        <strong>${escapeHtml(l.reason || 'Vacation')}</strong>
                        <div style="color: var(--text-muted); font-size: 12px;">${l.start_date} to ${l.end_date} (${l.is_approved ? 'Approved' : 'Pending'})</div>
                    </div>
                </div>
            `).join('')
            : '<p style="color: var(--text-muted); font-size: 13px;">No leave records scheduled.</p>';

        body.innerHTML = `
            <div class="dev-profile-header">
                <div class="dev-profile-avatar">${initials}</div>
                <div class="dev-profile-meta" style="flex: 1;">
                    <h3>${escapeHtml(dev.name)}</h3>
                    <div style="color: var(--text-muted); font-size: 13px; margin-bottom: 6px;">${escapeHtml(dev.title)} · <span class="mono-text">${escapeHtml(dev.email)}</span></div>
                    <div style="display: flex; gap: 8px; align-items: center; flex-wrap: wrap;">
                        <span class="badge ${activeAlloc ? 'badge-emerald' : 'badge-amber'}">${activeAlloc ? 'ALLOCATED' : 'ON BENCH'}</span>
                        <span class="badge badge-solver mono-text">$${floatVal(dev.hourly_cost)}/hr</span>
                        <span class="badge badge-count mono-text">${dev.max_weekly_hours}h/wk max</span>
                    </div>
                </div>
            </div>

            <div class="detail-section-title"><i class="fa-solid fa-code"></i> Technical Skills & Proficiency</div>
            <div class="dev-skills-grid">
                ${skillsBarsHtml}
            </div>

            <div class="detail-section-title"><i class="fa-solid fa-briefcase"></i> Project Allocation History (${devAllocs.length})</div>
            <div>
                ${allocsHistoryHtml}
            </div>

            <div class="detail-section-title"><i class="fa-solid fa-calendar-days"></i> Leave Schedule (${leaves.length})</div>
            <div>
                ${leavesHtml}
            </div>

            <div style="display: flex; justify-content: flex-end; gap: 10px; margin-top: 24px; padding-top: 16px; border-top: 1px solid var(--border-color);">
                <button type="button" class="btn btn-outline" onclick="app.hideDeveloperModal()">Close</button>
            </div>
        `;

        modal.style.display = 'flex';
    }

    hideDeveloperModal() {
        const modal = document.getElementById('developer-detail-modal');
        if (modal) modal.style.display = 'none';
    }

    // ===== Item 11: Project Detail Modal =====
    showProjectModal(projectId) {
        const proj = (this.projects || []).find(p => p.id === projectId);
        if (!proj) return;

        const modal = document.getElementById('project-detail-modal');
        const body = document.getElementById('project-detail-modal-body');
        if (!modal || !body) return;

        const slots = proj.slots || [];
        const confirmedAllocs = (this.allocations || []).filter(a => a.status === 'confirmed');

        let totalHeadcount = 0;
        let staffedHeadcount = 0;

        const slotsHtml = slots.map(slot => {
            totalHeadcount += slot.headcount_needed;
            const slotAllocs = confirmedAllocs.filter(a => a.project_slot === slot.id);
            staffedHeadcount += Math.min(slotAllocs.length, slot.headcount_needed);
            const isFilled = slotAllocs.length >= slot.headcount_needed;

            const reqsHtml = (slot.skill_requirements || []).map(r =>
                `<span class="badge badge-solver">${escapeHtml(r.skill_name)} >= Lvl ${r.min_proficiency} ${r.is_mandatory ? '(Req)' : ''}</span>`
            ).join(' ');

            const devsHtml = slotAllocs.map(a =>
                `<span class="badge badge-emerald"><i class="fa-solid fa-user-check"></i> ${escapeHtml(a.developer_name)}</span>`
            ).join(' ');

            return `
                <div class="history-timeline-item">
                    <div style="font-size: 18px; color: ${isFilled ? 'var(--green)' : 'var(--amber)'};">
                        <i class="fa-solid ${isFilled ? 'fa-circle-check' : 'fa-briefcase'}"></i>
                    </div>
                    <div style="flex: 1;">
                        <div class="flex-between">
                            <strong>${escapeHtml(slot.role_title)}</strong>
                            <span class="badge ${isFilled ? 'badge-emerald' : 'badge-amber'}">${slotAllocs.length}/${slot.headcount_needed} Staffed</span>
                        </div>
                        <div style="color: var(--text-muted); font-size: 12px; margin: 4px 0;">
                            <span>${slot.start_date} to ${slot.end_date}</span> · <span class="mono-text">P${slot.priority} Priority</span> · <span>${slot.weekly_hours_required || 40}h/wk</span>
                        </div>
                        <div style="margin-top: 6px; display: flex; gap: 4px; flex-wrap: wrap;">
                            ${reqsHtml || '<span style="font-size: 11px; color: var(--text-dim);">No specific skills required</span>'}
                        </div>
                        ${devsHtml ? `<div style="margin-top: 8px; display: flex; gap: 6px; flex-wrap: wrap;">${devsHtml}</div>` : ''}
                    </div>
                </div>
            `;
        }).join('') || '<p style="color: var(--text-muted);">No role demand slots configured for this project.</p>';

        body.innerHTML = `
            <div class="dev-profile-header">
                <div class="dev-profile-avatar" style="background: linear-gradient(135deg, #10b981, var(--primary));">
                    <i class="fa-solid fa-folder-open"></i>
                </div>
                <div class="dev-profile-meta" style="flex: 1;">
                    <h3>${escapeHtml(proj.name)}</h3>
                    <div style="color: var(--text-muted); font-size: 13px; margin-bottom: 6px;">Client: <strong>${escapeHtml(proj.client)}</strong> · Priority: <strong style="color: var(--amber);">P${proj.priority}</strong></div>
                    <div style="display: flex; gap: 8px; align-items: center; flex-wrap: wrap;">
                        <span class="badge ${staffedHeadcount >= totalHeadcount && totalHeadcount > 0 ? 'badge-emerald' : 'badge-amber'}">${staffedHeadcount}/${totalHeadcount} Staffed</span>
                        <span class="badge badge-solver mono-text">Budget: $${floatVal(proj.budget)}</span>
                        <span class="badge badge-count">${slots.length} Role Slot(s)</span>
                    </div>
                </div>
            </div>

            ${proj.description ? `<p style="font-size: 13px; color: var(--text-muted); margin-bottom: 16px;">${escapeHtml(proj.description)}</p>` : ''}

            <div class="detail-section-title"><i class="fa-solid fa-layer-group"></i> Project Demand Slots & Staffing</div>
            <div>
                ${slotsHtml}
            </div>

            <div style="display: flex; justify-content: flex-end; gap: 10px; margin-top: 24px; padding-top: 16px; border-top: 1px solid var(--border-color);">
                <button type="button" class="btn btn-outline" onclick="app.hideProjectModal()">Close</button>
            </div>
        `;

        modal.style.display = 'flex';
    }

    hideProjectModal() {
        const modal = document.getElementById('project-detail-modal');
        if (modal) modal.style.display = 'none';
    }

    // ===== Item 13: Solver History Modal =====
    async showSolverHistoryModal() {
        const modal = document.getElementById('solver-history-modal');
        const body = document.getElementById('solver-history-modal-body');
        if (!modal || !body) return;

        const { ok, data } = await this.safeFetchJson('/api/solver-runs/');
        const runs = ok ? extractArray(data) : [];

        if (runs.length === 0) {
            body.innerHTML = '<p style="text-align: center; color: var(--text-muted); padding: 30px;">No optimization engine runs recorded yet. Click "RUN CP-SAT SOLVER" to execute your first solve.</p>';
        } else {
            const rowsHtml = runs.map(run => {
                const metrics = run.summary_metrics || {};
                const comp = metrics.comparison || {};
                const gain = comp.gain_vs_greedy_pct !== undefined ? `+${comp.gain_vs_greedy_pct}%` : '—';
                const when = this.formatRelativeTime(run.timestamp);

                return `
                    <tr>
                        <td><strong>#${run.id}</strong></td>
                        <td>${escapeHtml(run.objective_used || 'balanced')}</td>
                        <td><span class="badge badge-emerald">${escapeHtml(run.status)}</span></td>
                        <td class="mono-cell"><strong>${run.total_score ? run.total_score.toFixed(1) : '0.0'}</strong></td>
                        <td class="mono-cell">${metrics.staffed_assignments || 0}</td>
                        <td class="mono-cell">${gain}</td>
                        <td class="mono-cell">${(run.runtime_seconds || 0).toFixed(3)}s</td>
                        <td style="color: var(--text-muted); font-size: 11px;">${when}</td>
                    </tr>
                `;
            }).join('');

            body.innerHTML = `
                <div class="table-responsive">
                    <table class="data-table">
                        <thead>
                            <tr>
                                <th>RUN</th>
                                <th>OBJECTIVE</th>
                                <th>STATUS</th>
                                <th>SCORE</th>
                                <th>STAFFED</th>
                                <th>GAIN</th>
                                <th>RUNTIME</th>
                                <th>DATE</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${rowsHtml}
                        </tbody>
                    </table>
                </div>
                <div style="display: flex; justify-content: flex-end; margin-top: 20px;">
                    <button type="button" class="btn btn-outline" onclick="app.hideSolverHistoryModal()">Close</button>
                </div>
            `;
        }

        modal.style.display = 'flex';
    }

    hideSolverHistoryModal() {
        const modal = document.getElementById('solver-history-modal');
        if (modal) modal.style.display = 'none';
    }

    // ===== Item 14: Notifications Dropdown =====
    toggleNotificationsDropdown() {
        const menu = document.getElementById('notifications-dropdown');
        if (!menu) return;
        const isVisible = menu.style.display === 'flex';
        menu.style.display = isVisible ? 'none' : 'flex';
    }

    renderNotifications() {
        const container = document.getElementById('notifications-list-container');
        const countBadge = document.getElementById('notif-count-badge');
        if (!container) return;

        const entries = [];
        this.allocations.forEach(a => {
            (a.audit_logs || []).forEach(log => {
                entries.push({
                    ...log,
                    developer_name: a.developer_name,
                    project_name: a.project_name,
                    role_title: a.role_title,
                });
            });
        });

        entries.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
        const recent = entries.slice(0, 8);

        if (countBadge) countBadge.textContent = `${recent.length} Events`;

        if (recent.length === 0) {
            container.innerHTML = '<p style="padding: 20px; color: var(--text-muted); text-align: center;">No recent events.</p>';
            return;
        }

        const iconMap = {
            created: { icon: 'fa-plus', color: 'var(--primary)' },
            accepted: { icon: 'fa-circle-check', color: 'var(--green)' },
            cancelled: { icon: 'fa-ban', color: 'var(--red)' },
            reverted: { icon: 'fa-rotate-left', color: 'var(--amber)' },
        };

        container.innerHTML = recent.map(e => {
            const meta = iconMap[e.action] || { icon: 'fa-circle-info', color: 'var(--primary)' };
            const when = this.formatRelativeTime(e.timestamp);
            return `
                <div class="notification-item">
                    <i class="fa-solid ${meta.icon}" style="color: ${meta.color};"></i>
                    <div>
                        <div><strong>${escapeHtml(e.developer_name)}</strong> ${escapeHtml(e.action)} on <strong>${escapeHtml(e.project_name)}</strong></div>
                        <small style="color: var(--text-muted); font-size: 11px;">${when} by ${escapeHtml(e.performed_by_name || 'System')}</small>
                    </div>
                </div>
            `;
        }).join('');
    }

    downloadSampleFile(type) {
        let content = '';
        let filename = '';

        if (type === 'employee') {
            filename = 'sample_employees.json';
            content = JSON.stringify([
                {
                    "name": "Jane Doe",
                    "email": "jane.doe@benchzero.io",
                    "title": "Staff AI Architect",
                    "hourly_cost": 145.00,
                    "max_weekly_hours": 40,
                    "skills": [
                        { "name": "Python", "proficiency_level": 5 },
                        { "name": "PyTorch", "proficiency_level": 5 },
                        { "name": "Docker", "proficiency_level": 4 }
                    ]
                },
                {
                    "name": "Robert Miller",
                    "email": "robert.m@benchzero.io",
                    "title": "Lead Go Engineer",
                    "hourly_cost": 125.00,
                    "max_weekly_hours": 40,
                    "skills": [
                        { "name": "Go", "proficiency_level": 5 },
                        { "name": "PostgreSQL", "proficiency_level": 4 },
                        { "name": "Kubernetes", "proficiency_level": 4 }
                    ]
                }
            ], null, 2);
        } else {
            filename = 'sample_projects.json';
            const today = new Date().toISOString().split('T')[0];
            const end = new Date(Date.now() + 90*24*60*60*1000).toISOString().split('T')[0];
            content = JSON.stringify([
                {
                    "name": "Nebula Quantum Platform",
                    "client": "Nebula Corp",
                    "priority": 5,
                    "budget": 300000.00,
                    "description": "High throughput distributed data analytics pipeline",
                    "slots": [
                        {
                            "role_title": "Lead Distributed Go Engineer",
                            "start_date": today,
                            "end_date": end,
                            "priority": 5,
                            "headcount_needed": 2,
                            "weekly_hours_required": 40,
                            "required_skills": [
                                { "name": "Go", "min_proficiency": 4, "is_mandatory": true },
                                { "name": "PostgreSQL", "min_proficiency": 3, "is_mandatory": false }
                            ]
                        }
                    ]
                }
            ], null, 2);
        }

        const blob = new Blob([content], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }
}

function floatVal(val) {
    return parseFloat(val || 0).toFixed(2);
}

