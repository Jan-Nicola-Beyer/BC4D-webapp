/* ─────────────────────────────────────────────────────────────────────────
   BC4D Intel — app.js  (full rewrite — all bugs fixed)
   ───────────────────────────────────────────────────────────────────────── */

/* ── 0. HELPERS ─────────────────────────────────────────────────────────── */
const $ = (sel, ctx = document) => ctx.querySelector(sel);
const $$ = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];

/* ── 1. WEBGL / 2D PARTICLE ENGINE ──────────────────────────────────────── */
(function initParticles() {
    const canvas = $('#particle-canvas');
    if (!canvas) return;
    const setSize = () => { canvas.width = window.innerWidth; canvas.height = window.innerHeight; };
    setSize();
    window.addEventListener('resize', setSize);

    const gl = canvas.getContext('webgl', { alpha: true, premultipliedAlpha: false });

    // ─ 2D fallback ─
    if (!gl) {
        const ctx = canvas.getContext('2d');
        const N = 180;
        const P = Array.from({ length: N }, () => ({
            x: Math.random() * canvas.width,  y: Math.random() * canvas.height,
            vx: (Math.random() - .5) * .4,    vy: (Math.random() - .5) * .4,
            r: Math.random() * 2 + .5,        a: Math.random() * .7 + .2,
        }));
        const mouse = { x: -9999, y: -9999 };
        window.addEventListener('mousemove', e => { mouse.x = e.clientX; mouse.y = e.clientY; });
        (function draw() {
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            P.forEach(p => {
                const dx = p.x - mouse.x, dy = p.y - mouse.y, d = Math.hypot(dx, dy);
                if (d < 100) { p.vx += dx / d * .05; p.vy += dy / d * .05; }
                p.vx *= .98; p.vy *= .98;
                p.x = (p.x + p.vx + canvas.width)  % canvas.width;
                p.y = (p.y + p.vy + canvas.height) % canvas.height;
                ctx.beginPath(); ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
                ctx.fillStyle = `rgba(61,168,244,${p.a * .6})`; ctx.fill();
            });
            requestAnimationFrame(draw);
        })();
        return;
    }

    // ─ WebGL shaders ─
    const vs = `
        attribute vec2 a_pos; attribute float a_sz, a_al, a_hu;
        varying float v_al, v_hu; uniform vec2 u_res;
        void main() {
            vec2 c = (a_pos / u_res) * 2.0 - 1.0;
            gl_Position = vec4(c * vec2(1,-1), 0, 1);
            gl_PointSize = a_sz; v_al = a_al; v_hu = a_hu;
        }`;
    const fs = `
        precision mediump float; varying float v_al, v_hu;
        void main() {
            vec2 d = gl_PointCoord - .5;
            float dist = dot(d,d); if (dist > .25) discard;
            float a = v_al * (1.0 - dist * 4.0);
            vec3 c = mix(vec3(.24,.66,.96), vec3(.48,.88,.83), v_hu);
            gl_FragColor = vec4(c, a * .75);
        }`;

    const mkShader = (t, src) => {
        const s = gl.createShader(t);
        gl.shaderSource(s, src); gl.compileShader(s); return s;
    };
    const prog = gl.createProgram();
    gl.attachShader(prog, mkShader(gl.VERTEX_SHADER, vs));
    gl.attachShader(prog, mkShader(gl.FRAGMENT_SHADER, fs));
    gl.linkProgram(prog); gl.useProgram(prog);

    const uRes = gl.getUniformLocation(prog, 'u_res');
    const aPos = gl.getAttribLocation(prog, 'a_pos');
    const aSz  = gl.getAttribLocation(prog, 'a_sz');
    const aAl  = gl.getAttribLocation(prog, 'a_al');
    const aHu  = gl.getAttribLocation(prog, 'a_hu');

    const N = 260;
    const pos = new Float32Array(N*2), vel = new Float32Array(N*2);
    const sz = new Float32Array(N), al = new Float32Array(N);
    const hu = new Float32Array(N), life = new Float32Array(N), maxL = new Float32Array(N);

    const spawn = (i, init) => {
        pos[i*2]   = Math.random() * canvas.width;
        pos[i*2+1] = init ? Math.random() * canvas.height : 0;
        vel[i*2]   = (Math.random() - .5) * .35;
        vel[i*2+1] = (Math.random() - .5) * .35;
        sz[i]  = Math.random() * 3.5 + 1;
        hu[i]  = Math.random();
        maxL[i] = 200 + Math.random() * 400;
        life[i] = init ? Math.random() * maxL[i] : 0;
        al[i]  = 0;
    };
    for (let i = 0; i < N; i++) spawn(i, true);

    const bufs = [gl.createBuffer(), gl.createBuffer(), gl.createBuffer(), gl.createBuffer()];
    const mouse = { x: -9999, y: -9999 };
    window.addEventListener('mousemove', e => { mouse.x = e.clientX; mouse.y = e.clientY; });

    gl.enable(gl.BLEND); gl.blendFunc(gl.SRC_ALPHA, gl.ONE); gl.clearColor(0,0,0,0);

    const upload = (buf, attr, data, n) => {
        gl.bindBuffer(gl.ARRAY_BUFFER, buf);
        gl.bufferData(gl.ARRAY_BUFFER, data, gl.DYNAMIC_DRAW);
        gl.enableVertexAttribArray(attr);
        gl.vertexAttribPointer(attr, n, gl.FLOAT, false, 0, 0);
    };

    (function frame() {
        canvas.width = window.innerWidth; canvas.height = window.innerHeight;
        gl.viewport(0, 0, canvas.width, canvas.height);
        gl.uniform2f(uRes, canvas.width, canvas.height);
        gl.clear(gl.COLOR_BUFFER_BIT);

        for (let i = 0; i < N; i++) {
            life[i]++;
            const t = life[i] / maxL[i];
            al[i] = t < .2 ? t / .2 * .85 : t > .8 ? (1-t) / .2 * .85 : .85;
            const dx = pos[i*2] - mouse.x, dy = pos[i*2+1] - mouse.y;
            const d = Math.hypot(dx, dy);
            if (d < 120) { vel[i*2] += dx/d * .4; vel[i*2+1] += dy/d * .4; }
            vel[i*2] *= .985; vel[i*2+1] *= .985;
            pos[i*2] += vel[i*2]; pos[i*2+1] += vel[i*2+1];
            if (life[i] > maxL[i] || pos[i*2] < -20 || pos[i*2] > canvas.width+20 ||
                pos[i*2+1] < -20 || pos[i*2+1] > canvas.height+20) spawn(i, false);
        }
        upload(bufs[0], aPos, pos, 2);
        upload(bufs[1], aSz,  sz,  1);
        upload(bufs[2], aAl,  al,  1);
        upload(bufs[3], aHu,  hu,  1);
        gl.drawArrays(gl.POINTS, 0, N);
        requestAnimationFrame(frame);
    })();
})();

/* ── 2. PER-PAGE REVEAL ENGINE ──────────────────────────────────────────── */
const PAGE_CFG = {
    import:    { cls: 'reveal',           stagger: 60  },
    dashboard: { cls: 'reveal',           stagger: 50  },
    analysis:  { cls: 'reveal-scale',     stagger: 70  },
    clusters:  { cls: 'reveal-flip',      stagger: 65  },
    insights:  { cls: 'reveal-scale',     stagger: 55  },
    responses: { cls: 'reveal-from-left', stagger: 50  },
    report:    { cls: 'reveal',           stagger: 60, rightPanel: '.report-editor-panel' },
    settings:  { cls: 'reveal-scale',     stagger: 80  },
};
const REVEAL_QUERY = '.glass-card, h1, .header-section > p, .line-draw, .stat-card, .tab-switcher, .settings-card, .styled-select, .filter-pills';

function revealPage(pageEl, isInit) {
    const pageId = pageEl.id.replace('page-', '');
    const cfg = PAGE_CFG[pageId] || PAGE_CFG.dashboard;
    const els = $$( REVEAL_QUERY, pageEl );
    const line = $('.line-draw', pageEl);

    if (isInit) {
        els.forEach(el => { el.classList.remove('will-reveal'); el.classList.add(cfg.cls, 'visible'); });
        if (line) line.classList.add('visible');
        return;
    }

    // Snap to hidden
    els.forEach(el => {
        el.classList.remove('reveal','reveal-scale','reveal-flip','reveal-from-left','reveal-from-right','visible','will-reveal');
        el.classList.add(cfg.cls, 'will-reveal');
    });
    if (line) { line.classList.remove('visible'); line.classList.add('will-reveal'); }

    if (cfg.rightPanel) {
        const rp = $(cfg.rightPanel, pageEl);
        if (rp) {
            rp.classList.add('reveal-from-right','will-reveal');
            setTimeout(() => rp.classList.add('visible'), 220);
        }
    }

    pageEl.offsetHeight; // force reflow

    if (line) setTimeout(() => line.classList.add('visible'), 80);
    els.forEach((el, i) => {
        setTimeout(() => {
            el.classList.remove('will-reveal');
            el.classList.add('visible');
        }, Math.min(i * cfg.stagger, 450) + 100);
    });
}

/* ── 3. API ─────────────────────────────────────────────────────────────── */
async function api(url, opts = {}) {
    const res = await fetch(url, { headers: { 'Content-Type': 'application/json' }, ...opts });
    if (!res.ok) {
        let detail = res.statusText;
        try { detail = (await res.json()).detail || detail; } catch(_) {}
        throw new Error(detail);
    }
    return res.json();
}

/* ── 4. NAVIGATION ──────────────────────────────────────────────────────── */
let _currentPage = 'import';

function navigateTo(targetPage) {
    if (targetPage === _currentPage) return;
    _currentPage = targetPage;

    $$('.page').forEach(p => p.classList.remove('active'));
    $$('.nav-links a').forEach(a => a.classList.toggle('active', a.dataset.page === targetPage));

    const page = $(`#page-${targetPage}`);
    if (!page) return;
    page.classList.add('active');

    const main = $('#main-scroll');
    if (main) main.scrollTop = 0;

    setTimeout(() => revealPage(page, false), 20);

    // Data hooks
    const hooks = {
        dashboard: loadDashboardData,
        settings:  loadSettings,
        analysis:  loadAiEstimate,
        clusters:  loadClusters,
        responses: loadResponses,
        report:    loadReport,
        insights:  () => setTimeout(loadInsights, 100),
    };
    hooks[targetPage]?.();
}

/* ── 5. INIT ────────────────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
    // Nav links — attach ONCE via delegation
    const navEl = $('.nav-links');
    if (navEl) navEl.addEventListener('click', e => {
        const a = e.target.closest('a[data-page]');
        if (a) { e.preventDefault(); navigateTo(a.dataset.page); }
    });

    // Dashboard tabs
    const dashTabs = $('#dash-tabs');
    if (dashTabs) dashTabs.addEventListener('click', e => {
        const btn = e.target.closest('.tab-btn');
        if (!btn) return;
        $$('#dash-tabs .tab-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        $$('.dash-tab-content').forEach(t => t.classList.remove('active'));
        $(`#dash-tab-${btn.dataset.tab}`)?.classList.add('active');
        if (btn.dataset.tab === 'pre')     populatePreTab();
        if (btn.dataset.tab === 'post')    populatePostTab();
        if (btn.dataset.tab === 'matched') populateMatchedTab();
    });

    // File upload
    setupDropZone('drop-pre',  'file-pre',  'pre');
    setupDropZone('drop-post', 'file-post', 'post');
    $('#btn-process')?.addEventListener('click', runMatching);

    // Demo load
    $('#btn-load-demo')?.addEventListener('click', loadDemoData);

    // AI Engine
    $('#btn-run-ai')?.addEventListener('click', runAiAnalysis);
    $('#btn-import-results')?.addEventListener('click', importJsonResults);

    // Clusters / Responses selects
    $('#clusters-question-select')?.addEventListener('change', e => renderClusters(e.target.value));
    $('#responses-question-select')?.addEventListener('change', e => renderResponses(e.target.value));

    // Confidence filter pills
    const pillContainer = $('#conf-filter');
    if (pillContainer) pillContainer.addEventListener('click', e => {
        const p = e.target.closest('.pill');
        if (!p) return;
        $$('#conf-filter .pill').forEach(x => x.classList.remove('active'));
        p.classList.add('active');
        const q = $('#responses-question-select')?.value;
        if (q) renderResponses(q);
    });

    // Report
    buildReportSectionList();
    $('#btn-gen-section')?.addEventListener('click', generateCurrentSection);
    $('#btn-gen-all-sections')?.addEventListener('click', generateAllSections);
    $('#btn-gen-report')?.addEventListener('click', exportReport);

    // Export chart
    $('#export-chart-btn')?.addEventListener('click', () => {
        const cvs = $('#matchChart');
        if (cvs) { const a = document.createElement('a'); a.download='chart.png'; a.href=cvs.toDataURL(); a.click(); }
    });

    // Settings
    $('#btn-save-settings')?.addEventListener('click', saveSettings);
    $('#btn-save-staffel')?.addEventListener('click',  saveStaffelName);
    $('#btn-clear-session')?.addEventListener('click', clearSession);

    // Lucide icons
    lucide.createIcons();

    // Initial reveal
    const initPage = $('.page.active');
    if (initPage) revealPage(initPage, true);

    // Load state from server
    loadAppState();
});

/* ── 6. STATE ────────────────────────────────────────────────────────────── */
let _appData = {};

async function loadAppState() {
    try {
        _appData = await api('/api/state');
        updateCounterTargets(_appData);
        if (_appData.has_match_result) {
            showMatchResultCard(_appData);
            if (_currentPage === 'dashboard') { loadDashboardData(); }
        }
        if (_appData.has_results) {
            showAiCompletion(_appData);
            await refreshQuestionDropdowns();
        }
    } catch(e) { console.warn('State load:', e.message); }
}

/* ── 7. IMPORT ──────────────────────────────────────────────────────────── */
const _files = { pre: null, post: null };

function setupDropZone(dropId, inputId, type) {
    const zone  = $(`#${dropId}`);
    const input = $(`#${inputId}`);
    if (!zone || !input) return;

    zone.addEventListener('click', () => input.click());
    input.addEventListener('change', () => { if (input.files[0]) handleFile(type, input.files[0]); });
    zone.addEventListener('dragover',  e => { e.preventDefault(); zone.style.borderColor = 'var(--particle-blue)'; });
    zone.addEventListener('dragleave', () => { zone.style.borderColor = ''; });
    zone.addEventListener('drop', e => {
        e.preventDefault(); zone.style.borderColor = '';
        if (e.dataTransfer.files[0]) handleFile(type, e.dataTransfer.files[0]);
    });
}

function handleFile(type, file) {
    _files[type] = file;
    $(`#${type}-label`).textContent = file.name;
    const zone = $(`#drop-${type}`);
    zone?.classList.add('loaded');
    if (_files.pre && _files.post) {
        const btn = $('#btn-process');
        if (btn) btn.disabled = false;
    }
}

async function runMatching() {
    const btn = $('#btn-process'), loader = $('#process-loader'), status = $('#process-status');
    if (!_files.pre || !_files.post) { if(status){status.textContent='Select both files first.';} return; }
    btn.disabled = true; loader.classList.add('visible'); status.textContent = 'Processing…';

    const fd = new FormData();
    fd.append('pre_file',  _files.pre);
    fd.append('post_file', _files.post);

    try {
        const res  = await fetch('/api/upload', { method: 'POST', body: fd });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Upload failed');
        _appData = { ..._appData, ...data };
        status.textContent = '';
        showMatchResultCard(data);
        updateCounterTargets(data);
        animateCounters();
    } catch(e) {
        status.style.color = '#fca5a5'; status.textContent = `Error: ${e.message}`;
        btn.disabled = false;
    } finally { loader.classList.remove('visible'); }
}

async function loadDemoData() {
    const btn = $('#btn-load-demo'), status = $('#process-status');
    if (btn) { btn.disabled = true; btn.textContent = 'Loading…'; }
    if (status) { status.style.color = 'var(--particle-blue)'; status.textContent = 'Loading demo data…'; }
    try {
        const data = await api('/api/demo/load', { method: 'POST' });
        _appData = { ..._appData, ...data, has_match_result: true, has_results: true,
                     n_matched: data.matched_pairs, match_rate_pct: 85.5, n_unmatched_pre: 174, n_unmatched_post: 22 };
        if (status) { status.style.color = '#6ee7b7'; status.textContent = 'Demo loaded ✓ — go to Dashboard to see all charts'; }
        showMatchResultCard(_appData);
        updateCounterTargets(_appData);
        animateCounters();
        await refreshQuestionDropdowns();
        showAiCompletion({ n_questions: data.n_questions, n_categories: 9, n_responses: data.n_responses,
                          n_high_confidence: Math.round(data.n_responses * 0.6), pct_high: 60 });
        // Pre-populate all dashboard tab data in background
        Promise.all([
            api('/api/dashboard/pre'),
            api('/api/dashboard/post'),
            api('/api/dashboard/matched'),
        ]).then(([pre, post, matched]) => {
            window._dashPre     = pre;
            window._dashPost    = post;
            window._dashMatched = matched;
        }).catch(e => console.warn('Pre-fetch dashboard:', e.message));
        setTimeout(() => { if(status) status.textContent=''; }, 5000);
    } catch(e) {
        if (status) { status.style.color = '#fca5a5'; status.textContent = `Error: ${e.message}`; }
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = 'Load Demo Data'; }
    }
}

function showMatchResultCard(data) {
    const card = $('#match-result-card'), inner = $('#match-result-inner');
    if (!card || !inner) return;
    const rate = data.match_rate_pct || data.match_rate_post || 0;
    const cls  = rate >= 70 ? 'match-rate-good' : rate >= 50 ? 'match-rate-ok' : 'match-rate-poor';
    const txt  = rate >= 70 ? '✅ Good match rate' : rate >= 50 ? '⚠️ Acceptable' : '⚠️ Low match rate';

    inner.innerHTML = `
        <div style="display:flex;align-items:center;gap:1rem;flex-wrap:wrap;margin-bottom:1rem;">
            <h3 style="font-weight:600;font-size:1.1rem;">Data ready</h3>
            <span class="match-rate-badge ${cls}">${txt} (${rate}%)</span>
        </div>
        <div class="match-result-grid">
            <div class="match-result-stat"><div class="val">${data.n_pre||0}</div><div class="lbl">Pre-Survey</div></div>
            <div class="match-result-stat"><div class="val">${data.n_post||0}</div><div class="lbl">Post-Survey</div></div>
            <div class="match-result-stat"><div class="val">${data.n_matched||data.matched_pairs||0}</div><div class="lbl">Matched Pairs</div></div>
        </div>
        <div style="display:flex;gap:1rem;margin-top:1.25rem;flex-wrap:wrap;">
            <button class="btn-primary" onclick="navigateTo('dashboard')">Continue to Dashboard →</button>
            <button class="btn-secondary" onclick="navigateTo('analysis')">Go to AI Analysis →</button>
        </div>`;
    card.style.display = 'block';
    lucide.createIcons();
}

/* ── 8. DASHBOARD ───────────────────────────────────────────────────────── */
let _chartInstance = null;
// Store distribution charts for export
window._tabCharts = {};

function updateCounterTargets(data) {
    const map = { 'stat-pre': data.n_pre, 'stat-post': data.n_post, 'stat-matched': data.n_matched || data.matched_pairs };
    Object.entries(map).forEach(([id, val]) => {
        const el = $(`#${id}`);
        if (el && val !== undefined) el.dataset.target = val;
    });
}

function animateCounters() {
    $$('.counter[data-target]').forEach(el => {
        const target = parseInt(el.dataset.target || 0);
        const from   = parseInt(el.textContent) || 0;
        const dur = 1200, start = performance.now();
        (function tick(now) {
            const t = Math.min((now - start) / dur, 1);
            el.textContent = Math.round(from + (target - from) * (1 - Math.pow(1 - t, 3)));
            if (t < 1) requestAnimationFrame(tick);
        })(performance.now());
    });
}

async function loadDashboardData() {
    try {
        const data = await api('/api/dashboard');
        Object.assign(_appData, data);
        updateCounterTargets(data);
        animateCounters();
        drawMatchChart(data);
    } catch(e) { console.warn('Dashboard:', e.message); }
}

function drawMatchChart(data) {
    const ctx = $('#matchChart');
    if (!ctx) return;
    if (_chartInstance) { _chartInstance.destroy(); _chartInstance = null; }

    const n_pre     = data.n_pre || 0;
    const n_post    = data.n_post || 0;
    const n_match   = data.n_matched || 0;
    const n_u_pre   = data.n_unmatched_pre || Math.max(n_pre - n_match, 0);
    const n_u_post  = data.n_unmatched_post || Math.max(n_post - n_match, 0);

    _chartInstance = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: ['Pre-Survey\nTotal', 'Post-Survey\nTotal', 'Matched\nPairs', 'Unmatched\nPre', 'Unmatched\nPost'],
            datasets: [{
                label: 'Respondents',
                data: [n_pre, n_post, n_match, n_u_pre, n_u_post],
                backgroundColor: [
                    'rgba(61,168,244,0.55)', 'rgba(123,224,212,0.55)',
                    'rgba(200,23,93,0.65)', 'rgba(217,119,6,0.45)', 'rgba(220,38,38,0.35)',
                ],
                borderColor: ['#3da8f4', '#7be0d4', '#C8175D', '#d97706', '#dc2626'],
                borderWidth: 1.5,
                borderRadius: 8,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: { duration: 1200, easing: 'easeOutQuart', delay: ctx => ctx.dataIndex * 150 },
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: 'rgba(5,11,23,0.94)',
                    borderColor: 'rgba(46,91,255,0.3)', borderWidth: 1,
                    titleColor: '#f0f6ff', bodyColor: 'rgba(180,200,230,0.7)', padding: 12,
                },
            },
            scales: {
                x: { grid: { color: 'rgba(46,91,255,0.07)' }, ticks: { color: 'rgba(180,200,230,0.65)', font: { family: "'Space Grotesk'" } } },
                y: { grid: { color: 'rgba(46,91,255,0.07)' }, ticks: { color: 'rgba(180,200,230,0.65)', font: { family: "'Space Grotesk'" } } },
            },
        },
    });
    window._matchChart = _chartInstance;
}

// Helper: replace entire content inside a tab's glass-card
function _replaceTabCard(tabId, html) {
    const content = $(`#${tabId}-tab-content`);
    if (content) {
        content.innerHTML = html;
        const ph = $(`#${tabId}-tab-placeholder`);
        if (ph) ph.style.display = 'none';
    }
}

async function populatePreTab() {
    try {
        const data = await api('/api/dashboard/pre');
        if (!data?.items?.length) { return; }
        _replaceTabCard('pre', buildLikertSection(data.items, `Pre-Survey – ${data.n} respondents (baseline)`, 'pre'));
        buildDistributionChart('pre-dist-chart', data.items, 'pre');
        if (data.demographics?.length) {
            const el = $('#pre-tab-demographics');
            if (el) {
                el.innerHTML = buildDemographicsSection(data.demographics, 'pre');
                setTimeout(() => drawDemographicCharts(data.demographics, 'pre'), 100);
            }
        }
    } catch(e) { console.warn('Pre tab:', e.message); }
}

async function populatePostTab() {
    try {
        const data = await api('/api/dashboard/post');
        if (!data?.items?.length) { return; }
        _replaceTabCard('post', buildLikertSection(data.items, `Post-Survey – ${data.n} respondents (outcome)`, 'post'));
        buildDistributionChart('post-dist-chart', data.items, 'post');
        if (data.demographics?.length) {
            const el = $('#post-tab-demographics');
            if (el) {
                el.innerHTML = buildDemographicsSection(data.demographics, 'post');
                setTimeout(() => drawDemographicCharts(data.demographics, 'post'), 100);
            }
        }
    } catch(e) { console.warn('Post tab:', e.message); }
}

async function populateMatchedTab() {
    try {
        const data = await api('/api/dashboard/matched');
        if (!data?.comparisons?.length) {
            console.warn('Matched tab: no comparisons returned', data);
            return;
        }
        _replaceTabCard('matched', buildMatchedSection(data.comparisons));
        buildWaterfallChart('matched-waterfall-chart', data.comparisons);
    } catch(e) { console.warn('Matched tab:', e.message); }
}

function buildLikertSection(items, title, key) {
    const chartId = `${key}-dist-chart`;
    const rows = items.map(item => {
        const s = item.stats, pct = s.pct_agree || 0, pct_d = s.pct_disagree || 0;
        return `<tr>
            <td style="max-width:260px; font-size:0.85rem; padding:0.5rem 0.75rem;">${item.label}</td>
            <td style="color:var(--text-muted);font-size:0.85rem;padding:0.5rem 0.75rem;">${s.n}</td>
            <td style="color:var(--particle-blue);font-weight:600;font-size:0.85rem;padding:0.5rem 0.75rem;">${s.mean}</td>
            <td style="color:var(--text-muted);font-size:0.85rem;padding:0.5rem 0.75rem;">${s.sd}</td>
            <td style="padding:0.5rem 0.75rem; min-width:160px;">
                <div class="bar-track"><div class="bar-fill" style="width:${pct}%"></div></div>
                <span style="font-size:0.7rem;color:var(--text-muted);">${pct}% agree · ${pct_d}% disagree</span>
            </td>
        </tr>`;
    }).join('');

    return `
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:1rem;flex-wrap:wrap;gap:0.5rem;">
            <h3 style="font-weight:600;">${title}</h3>
            <div style="display:flex; gap:0.5rem;">
                <button class="btn-primary" style="padding:0.45rem 1.1rem;font-size:0.8rem;" onclick="exportTabChart('${chartId}','${key}')">
                    <span>⬇</span> Export Chart
                </button>
                <button class="btn-secondary" style="padding:0.45rem 1.1rem;font-size:0.8rem;" onclick="window.location.href='/api/export/data/${key}'">
                    <span>⬇</span> Export Data
                </button>
            </div>
        </div>
        <div style="height:300px; position:relative; margin-bottom:1.5rem;">
            <canvas id="${chartId}"></canvas>
        </div>
        <div class="chart-full" style="overflow-x:auto;">
            <table class="likert-table">
                <thead><tr><th>Item</th><th>N</th><th>M</th><th>SD</th><th>Agreement</th></tr></thead>
                <tbody>${rows}</tbody>
            </table>
        </div>`;
}

function buildDistributionChart(canvasId, items, key) {
    // Render after DOM update
    setTimeout(() => {
        const ctx = $(`#${canvasId}`);
        if (!ctx) return;
        if (window._tabCharts[key]) { window._tabCharts[key].destroy(); }
        const labels = items.map(it => it.label.substring(0, 35) + (it.label.length > 35 ? '…' : ''));
        const means  = items.map(it => it.stats.mean || 0);
        const sds    = items.map(it => it.stats.sd || 0);

        window._tabCharts[key] = new Chart(ctx, {
            type: 'bar',
            data: {
                labels,
                datasets: [{
                    label: 'Mean',
                    data: means,
                    backgroundColor: 'rgba(61,168,244,0.55)',
                    borderColor: '#3da8f4',
                    borderWidth: 1.5,
                    borderRadius: 6,
                    yAxisID: 'y',
                }, {
                    label: 'SD',
                    data: sds,
                    backgroundColor: 'rgba(200,23,93,0.35)',
                    borderColor: '#C8175D',
                    borderWidth: 1.5,
                    borderRadius: 4,
                    yAxisID: 'y',
                }],
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                indexAxis: 'y',
                animation: { duration: 1000, easing: 'easeOutQuart', delay: ctx => ctx.dataIndex * 40 },
                plugins: {
                    legend: { labels: { color: 'rgba(180,200,230,0.7)', font: { family: "'Space Grotesk'" } } },
                    tooltip: { backgroundColor: 'rgba(5,11,23,0.94)', titleColor: '#f0f6ff', bodyColor: 'rgba(180,200,230,0.7)', padding: 10 },
                },
                scales: {
                    x: { min: 0, max: 5, grid: { color: 'rgba(46,91,255,0.07)' }, ticks: { color: 'rgba(180,200,230,0.6)' } },
                    y: { grid: { color: 'rgba(46,91,255,0.07)' }, ticks: { color: 'rgba(180,200,230,0.6)', font: { size: 10 } } },
                },
            },
        });
    }, 60);
}

function buildMatchedSection(comparisons) {
    const rows = comparisons.map(c => {
        const comp = c.comparison;
        const ch = comp.mean_change;
        const color = ch > 0.1 ? '#6ee7b7' : ch < -0.1 ? '#fca5a5' : 'var(--text-muted)';
        const arrow = ch > 0.1 ? '▲' : ch < -0.1 ? '▼' : '→';
        return `<tr>
            <td style="font-size:0.85rem;max-width:240px;padding:0.5rem 0.75rem;">${c.label}</td>
            <td style="color:var(--text-muted);font-size:0.85rem;padding:0.5rem 0.75rem;">${comp.pre_mean ?? '—'}</td>
            <td style="color:var(--text-muted);font-size:0.85rem;padding:0.5rem 0.75rem;">${comp.post_mean ?? '—'}</td>
            <td style="color:${color};font-weight:600;font-size:0.85rem;padding:0.5rem 0.75rem;">${arrow} ${ch > 0 ? '+' : ''}${ch ?? '—'}</td>
            <td style="color:${color};font-size:0.85rem;padding:0.5rem 0.75rem;">${comp.effect_label || '—'} ${comp.significant ? '*' : ''}</td>
            <td style="color:var(--text-muted);font-size:0.8rem;padding:0.5rem 0.75rem;">${comp.p_value?.toFixed(3) ?? '—'}</td>
        </tr>`;
    }).join('');

    return `
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:1rem;flex-wrap:wrap;gap:0.5rem;">
            <div>
                <h3 style="font-weight:600;">Matched Panel Analysis</h3>
                <p style="color:var(--text-muted);font-size:0.85rem;margin-top:0.3rem;">Wilcoxon signed-rank test with Bonferroni correction. * p &lt; 0.05</p>
            </div>
            <div style="display:flex; gap:0.5rem;">
                <button class="btn-primary" style="padding:0.45rem 1.1rem;font-size:0.8rem;" onclick="exportTabChart('matched-waterfall-chart','matched')">
                    <span>⬇</span> Export Chart
                </button>
                <button class="btn-secondary" style="padding:0.45rem 1.1rem;font-size:0.8rem;" onclick="window.location.href='/api/export/data/matched'">
                    <span>⬇</span> Export Data
                </button>
            </div>
        </div>
        <div style="height:280px; position:relative; margin-bottom:1.5rem;">
            <canvas id="matched-waterfall-chart"></canvas>
        </div>
        <div class="chart-full" style="overflow-x:auto;">
            <table class="likert-table">
                <thead><tr><th>Item</th><th>Pre M</th><th>Post M</th><th>Δ</th><th>Effect</th><th>p</th></tr></thead>
                <tbody>${rows}</tbody>
            </table>
        </div>`;
}

function buildWaterfallChart(canvasId, comparisons) {
    setTimeout(() => {
        const ctx = $(`#${canvasId}`);
        if (!ctx) return;
        if (window._tabCharts['matched']) { window._tabCharts['matched'].destroy(); }
        const labels  = comparisons.map(c => c.label.substring(0, 30) + '…');
        const changes  = comparisons.map(c => c.comparison.mean_change ?? 0);
        const bgColors = changes.map(v => v > 0 ? 'rgba(5,150,105,0.6)' : v < 0 ? 'rgba(220,38,38,0.5)' : 'rgba(100,100,100,0.4)');

        window._tabCharts['matched'] = new Chart(ctx, {
            type: 'bar',
            data: {
                labels,
                datasets: [{ label: 'Mean Change (Post − Pre)', data: changes, backgroundColor: bgColors, borderRadius: 6, borderWidth: 0 }],
            },
            options: {
                responsive: true, maintainAspectRatio: false, indexAxis: 'y',
                animation: { duration: 900, delay: ctx => ctx.dataIndex * 50 },
                plugins: {
                    legend: { display: false },
                    tooltip: { backgroundColor: 'rgba(5,11,23,0.94)', titleColor: '#f0f6ff', bodyColor: 'rgba(180,200,230,0.7)', padding: 10 },
                },
                scales: {
                    x: { grid: { color: 'rgba(46,91,255,0.07)' }, ticks: { color: 'rgba(180,200,230,0.6)' } },
                    y: { grid: {display:false}, ticks: { color: 'rgba(180,200,230,0.6)', font: { size: 9 } } },
                },
            },
        });
    }, 60);
}

// Export any tab chart by id
window.exportTabChart = function(chartId, label) {
    const cvs = $(`#${chartId}`);
    if (!cvs) { alert(`Chart "${chartId}" not found. Switch to that tab first.`); return; }
    const a = document.createElement('a');
    a.download = `bc4d_${label}_chart.png`;
    a.href = cvs.toDataURL('image/png', 1.0);
    a.click();
};

function buildDemographicsSection(demographics, key) {
    if (!demographics || !demographics.length) return '';
    return demographics.map((d, i) => {
        const chartId = `${key}-demo-${i}`;
        const s = d.stats;
        const total = s.n || 1;
        const rows = Object.entries(s.percentages).sort((a, b) => b[1] - a[1]).map(([cat, pct]) => {
            const count = s.categories[cat] || 0;
            return `<tr>
                <td style="max-width:260px; font-size:0.85rem; padding:0.5rem 0.75rem;">${cat}</td>
                <td style="color:var(--text-muted);font-size:0.85rem;padding:0.5rem 0.75rem;">${count}</td>
                <td style="padding:0.5rem 0.75rem; min-width:160px;">
                    <div class="bar-track"><div class="bar-fill" style="width:${pct}%"></div></div>
                    <span style="font-size:0.7rem;color:var(--text-muted);">${pct}%</span>
                </td>
            </tr>`;
        }).join('');

        return `
            <div style="margin-top:2rem;">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:1rem;flex-wrap:wrap;gap:0.5rem;">
                    <h3 style="font-weight:600;">Demographics: ${d.label}</h3>
                    <div style="display:flex; gap:0.5rem;">
                        <button class="btn-primary" style="padding:0.45rem 1.1rem;font-size:0.8rem;" onclick="exportTabChart('${chartId}','${key}_demo_${i}')">
                            <span>⬇</span> Export Chart
                        </button>
                        <button class="btn-secondary" style="padding:0.45rem 1.1rem;font-size:0.8rem;" onclick="window.location.href='/api/export/data/${key}'">
                            <span>⬇</span> Export Data
                        </button>
                    </div>
                </div>
                <div style="display:flex; flex-wrap:wrap; gap:2rem; align-items:center; margin-bottom:1.5rem;">
                    <div style="height:250px; width:100%; max-width:300px; position:relative;">
                        <canvas id="${chartId}"></canvas>
                    </div>
                    <div class="chart-full" style="flex:1; overflow-x:auto;">
                        <table class="likert-table">
                            <thead><tr><th>Category</th><th>N</th><th>Percentage</th></tr></thead>
                            <tbody>${rows}</tbody>
                        </table>
                    </div>
                </div>
            </div>`;
    }).join('');
}

function drawDemographicCharts(demographics, key) {
    const palette = ['#3da8f4','#7be0d4','#C8175D','#d97706','#6366f1','#ec4899','#14b8a6','#a855f7'];
    demographics.forEach((d, i) => {
        const chartId = `${key}-demo-${i}`;
        const ctx = $(`#${chartId}`);
        if (!ctx) return;
        
        const cats = Object.entries(d.stats.percentages).sort((a, b) => b[1] - a[1]);
        const labels = cats.map(c => c[0].substring(0, 25));
        const dataVals = cats.map(c => c[1]);

        if (window._tabCharts[`${key}_demo_${i}`]) { window._tabCharts[`${key}_demo_${i}`].destroy(); }
        window._tabCharts[`${key}_demo_${i}`] = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels,
                datasets: [{ data: dataVals, backgroundColor: palette, borderWidth: 2, borderColor: 'rgba(3,7,15,0.8)' }],
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: { backgroundColor:'rgba(5,11,23,0.94)', titleColor:'#f0f6ff', bodyColor:'rgba(180,200,230,0.7)', padding:10 },
                },
            },
        });
    });
}

/* ── 9. AI ENGINE ───────────────────────────────────────────────────────── */
async function loadAiEstimate() {
    try {
        const data = await api('/api/analysis/estimate');
        const el = $('#ai-estimate-text');
        if (el && data.text) el.innerHTML = data.text.replace(/\n/g, '<br>');
        if (data.has_results) showAiCompletion(data);
    } catch(e) {}
}

async function runAiAnalysis() {
    const btn = $('#btn-run-ai'), loader = $('#ai-loader'), status = $('#ai-status');
    const progressArea = $('#ai-progress-area'), bar = $('#ai-progress-bar');
    const detail = $('#ai-progress-detail'), pct = $('#ai-progress-pct');

    btn.disabled = true; loader.classList.add('visible');
    progressArea.style.display = 'block';
    status.style.color = 'var(--particle-blue)'; status.textContent = 'Connecting…';

    try {
        const res = await fetch('/api/analysis/run', { method: 'POST' });
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            const text = decoder.decode(value);
            text.split('\n').filter(l => l.startsWith('data:')).forEach(line => {
                try {
                    const ev = JSON.parse(line.slice(5));
                    if (ev.progress !== undefined) {
                        const p = Math.round(ev.progress * 100);
                        bar.style.width = p + '%'; pct.textContent = p + '%';
                    }
                    if (ev.detail) detail.textContent = ev.detail;
                    if (ev.done) {
                        refreshQuestionDropdowns();
                        showAiCompletion(ev);
                        status.style.color = '#6ee7b7'; status.textContent = 'Complete ✓';
                    }
                    if (ev.error) { status.style.color='#fca5a5'; status.textContent = ev.error; }
                } catch(_) {}
            });
        }
    } catch(e) {
        status.style.color = '#fca5a5'; status.textContent = `Error: ${e.message}`;
    } finally {
        btn.disabled = false; loader.classList.remove('visible');
    }
}

async function importJsonResults() {
    const input = document.createElement('input');
    input.type = 'file'; input.accept = '.json'; input.click();
    input.onchange = async () => {
        const file = input.files[0]; if (!file) return;
        const fd = new FormData(); fd.append('file', file);
        try {
            const res = await fetch('/api/analysis/import', { method:'POST', body: fd });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail);
            await refreshQuestionDropdowns();
            showAiCompletion(data);
        } catch(e) {
            const s=$('#ai-status'); if(s){s.style.color='#fca5a5'; s.textContent=e.message;}
        }
    };
}

function showAiCompletion(data) {
    const card = $('#ai-completion-card'), stats = $('#ai-completion-stats');
    if (!card) return;
    card.style.display = 'block';
    if (stats) {
        stats.innerHTML = `
            <strong>${data.n_questions || 0}</strong> questions analyzed ·
            <strong>${data.n_categories || 0}</strong> categories ·
            <strong>${data.n_responses || 0}</strong> responses classified ·
            <strong>${data.n_high_confidence || 0}</strong> high-confidence (${data.pct_high || 0}%)
        `;
    }
    lucide.createIcons();
}

/* ── 10. CLUSTERS ───────────────────────────────────────────────────────── */
async function loadClusters() {
    try {
        const data = await api('/api/clusters');
        window._clustersData = data;
        const qs = Object.keys(data);
        const sel = $('#clusters-question-select');
        if (!sel) return;
        sel.innerHTML = '<option value="">— Select a question —</option>' +
            qs.map(q => `<option value="${encodeURIComponent(q)}">${q.replace(/^\[(Pre|Post)\] /,'').substring(0,70)}</option>`).join('');
        if (qs.length) { sel.value = encodeURIComponent(qs[0]); renderClusters(encodeURIComponent(qs[0])); }
    } catch(e) { console.warn('Clusters:', e.message); }
}

function renderClusters(encodedKey) {
    const qKey = decodeURIComponent(encodedKey);
    const content = $('#clusters-content');
    if (!content || !qKey || !window._clustersData) return;
    const data = window._clustersData[qKey];
    if (!data) return;

    const taxonomy = data.taxonomy || {};
    const classifications = data.classifications || [];

    let html = `<p style="color:var(--text-muted);font-size:0.85rem;margin-bottom:1rem;">${qKey}</p>`;
    const cats = taxonomy.categories || [];
    if (!cats.length) {
        html += '<div class="glass-card"><p style="color:var(--text-muted);">No taxonomy data.</p></div>';
    } else {
        cats.forEach(mc => {
            html += `<div class="cluster-main-category">${mc.main_category}</div>`;
            (mc.sub_categories || []).forEach((sub, si) => {
                const count = classifications.filter(c => (c.human_override || c.cluster_id) === sub.id).length;
                const color = ['#3da8f4','#7be0d4','#C8175D','#d97706','#6366f1','#ec4899'][si % 6];
                html += `<div class="cluster-sub-card">
                    <div class="cluster-badge" style="background:${color}22;color:${color};border:1px solid ${color}55;">${count}</div>
                    <div style="flex:1;">
                        <div style="display:flex; align-items:center;">
                            <input class="styled-input" style="font-size:0.95rem; font-weight:600; padding:0.1rem 0.3rem; border:none; background:transparent; width:100%; border-bottom:1px dashed var(--border-color);" value="${sub.title.replace(/"/g, '&quot;')}" onchange="renameCluster('${encodedKey}', '${sub.id}', this.value)" />
                        </div>
                        ${sub.include_rule ? `<p style="color:var(--text-muted);font-size:0.8rem;">${sub.include_rule.substring(0,120)}</p>` : ''}
                        ${(sub.examples||[]).slice(0,2).map(ex=>`<p style="color:var(--text-subtle);font-size:0.78rem;font-style:italic;margin-top:0.2rem;">"${ex.substring(0,100)}"</p>`).join('')}
                    </div>
                </div>`;
            });
        });
    }
    content.innerHTML = html;
    $$('#clusters-content .cluster-sub-card').forEach((card,i) => {
        card.classList.add('reveal-flip','will-reveal');
        setTimeout(() => { card.classList.remove('will-reveal'); card.classList.add('visible'); }, i*80+80);
    });
}

async function refreshQuestionDropdowns() {
    try {
        const data = await api('/api/clusters');
        window._clustersData = data;
        const qs = Object.keys(data);
        const opts = '<option value="">— Select a question —</option>' +
            qs.map(q => `<option value="${encodeURIComponent(q)}">${q.replace(/^\[(Pre|Post)\] /,'').substring(0,70)}</option>`).join('');
        [$('#clusters-question-select'), $('#responses-question-select')].forEach(sel => {
            if (sel) sel.innerHTML = opts;
        });
    } catch(e) {}
}

/* ── 11. RESPONSES ──────────────────────────────────────────────────────── */
async function loadResponses() {
    await refreshQuestionDropdowns();
    const sel = $('#responses-question-select');
    if (sel?.options.length > 1) { sel.selectedIndex = 1; renderResponses(sel.value); }
}

function renderResponses(encodedKey) {
    const qKey   = decodeURIComponent(encodedKey);
    const content = $('#responses-content'), countEl = $('#responses-count');
    if (!content || !qKey || !window._clustersData) return;
    const data = window._clustersData[qKey];
    if (!data) return;

    const confFilter = $('#conf-filter .pill.active')?.dataset.conf || 'all';
    const all = data.classifications || [];
    const filtered = confFilter === 'all' ? all : all.filter(c => c.confidence === confFilter);

    if (countEl) countEl.textContent = `${filtered.length}/${all.length} shown`;
    if (!filtered.length) {
        content.innerHTML = '<div class="glass-card"><p style="color:var(--text-muted);">No responses match filter.</p></div>';
        return;
    }

    const flatTax = data.flat_taxonomy || [];
    const mainCats = [...new Set(flatTax.map(c => c.main_category))];
    const subByMain = {};
    flatTax.forEach(c => {
        if (!subByMain[c.main_category]) subByMain[c.main_category] = [];
        subByMain[c.main_category].push(c);
    });

    content.innerHTML = filtered.map((item, i) => {
        const originalIndex = all.indexOf(item);
        const cid = item.human_override || item.cluster_id;
        const currentCat = flatTax.find(c => c.id === cid) || { main_category: item.main_category || '', title: item.cluster_title || '' };
        const cls = item.confidence === 'high' ? 'conf-high' : item.confidence === 'medium' ? 'conf-medium' : 'conf-low';
        
        const mainOptions = mainCats.map(mc => `<option value="${mc.replace(/"/g, '&quot;')}" ${mc === currentCat.main_category ? 'selected' : ''}>${mc}</option>`).join('');
        const subOptions = (subByMain[currentCat.main_category] || []).map(sc => `<option value="${sc.id}" ${sc.id === cid ? 'selected' : ''}>${sc.title}</option>`).join('');

        return `<div class="response-row reveal-from-left" style="transition-delay:${Math.min(i*25,200)}ms;">
            <span class="conf-badge ${cls}">${item.confidence}</span>
            <div style="flex:1;">
                <div class="response-text">${item.text}</div>
                <div style="display:flex; gap:0.5rem; margin-top:0.4rem; align-items:center;">
                    <select class="styled-select" style="font-size:0.8rem; padding:0.2rem 0.5rem; width:150px; background-color:var(--accent-color);" onchange="updateMainCat('${encodedKey}', ${originalIndex}, this.value, 'sub-${i}')">
                        ${mainOptions}
                    </select>
                    <span style="color:var(--text-muted);">&rsaquo;</span>
                    <select id="sub-${i}" class="styled-select" style="font-size:0.8rem; padding:0.2rem 0.5rem; width:180px; background-color:var(--dim-bg);" onchange="reassignResponse('${encodedKey}', ${originalIndex}, this.value)">
                        ${subOptions}
                    </select>
                    ${item.human_override ? '<span style="color:var(--warning-color);font-size:0.75rem;margin-left:0.5rem;">(Edited)</span>' : ''}
                </div>
            </div>
        </div>`;
    }).join('');

    $$('#responses-content .response-row').forEach((row, i) => {
        row.classList.add('will-reveal');
        setTimeout(() => { row.classList.remove('will-reveal'); row.classList.add('visible'); }, i*30+50);
    });
}

/* ── OVERRIDES & TAXONOMY MUTATIONS ─────────────────────────────────────── */
window.updateMainCat = function(encodedKey, originalIndex, newMainCat, subSelectId) {
    const qKey = decodeURIComponent(encodedKey);
    const data = window._clustersData[qKey];
    const subCats = data.flat_taxonomy.filter(c => c.main_category === newMainCat);
    const subSel = $(`#${subSelectId}`);
    subSel.innerHTML = subCats.map(sc => `<option value="${sc.id}">${sc.title}</option>`).join('');
    if (subCats.length > 0) { window.reassignResponse(encodedKey, originalIndex, subCats[0].id); }
};

window.reassignResponse = async function(encodedKey, originalIndex, newClusterId) {
    const qKey = decodeURIComponent(encodedKey);
    const data = window._clustersData[qKey];
    const cat = data.flat_taxonomy.find(c => c.id === newClusterId);
    if (!cat) return;
    try {
        await api('/api/responses/reassign', {
            method: 'POST',
            body: JSON.stringify({
                question: qKey, response_index: originalIndex,
                new_cluster_id: cat.id, new_cluster_title: cat.title, new_main_category: cat.main_category
            })
        });
        await refreshQuestionDropdowns();
        renderResponses(encodedKey);
    } catch(e) { console.warn(e); }
};

window.showAddCategoryModal = function() {
    const sel = $('#responses-question-select');
    if (!sel || !sel.value) return alert('Select a question first.');
    $('#add-category-modal').style.display = 'flex';
};

window.submitNewCategory = async function() {
    const sel = $('#responses-question-select');
    const main = $('#add-cat-main').value.trim();
    const sub = $('#add-cat-sub').value.trim();
    if (!sel.value || !main || !sub) return;
    try {
        await api('/api/responses/category/add', {
            method: 'POST',
            body: JSON.stringify({ question: decodeURIComponent(sel.value), main_category: main, sub_category: sub })
        });
        $('#add-category-modal').style.display = 'none';
        $('#add-cat-main').value = ''; $('#add-cat-sub').value = '';
        await refreshQuestionDropdowns();
        renderResponses(sel.value);
    } catch(e) { alert(e.message); }
};

window.renameCluster = async function(encodedKey, clusterId, newTitle) {
    if (!newTitle.trim()) return;
    const qKey = decodeURIComponent(encodedKey);
    try {
        await api('/api/clusters/rename', {
            method: 'POST',
            body: JSON.stringify({ question: qKey, cluster_id: clusterId, new_title: newTitle })
        });
        await refreshQuestionDropdowns();
        renderClusters(encodedKey);
    } catch(e) { console.warn(e); }
};

/* ── 12. INSIGHTS ───────────────────────────────────────────────────────── */
async function loadInsights() {
    const content = $('#insights-content');
    if (!window._clustersData || !content) return;
    const qs = Object.keys(window._clustersData);
    if (!qs.length) return;

    let html = '';
    const palette = ['#3da8f4','#7be0d4','#C8175D','#d97706','#6366f1','#ec4899','#14b8a6','#a855f7'];

    qs.slice(0, 6).forEach((q, qi) => {
        const data = window._clustersData[q];
        const classifications = data.classifications || [];
        const flatTax = data.flat_taxonomy || [];
        if (!classifications.length || !flatTax.length) return;

        const counts = {};
        classifications.forEach(c => {
            const cid = c.human_override || c.cluster_id;
            const cat = flatTax.find(f => f.id === cid);
            if (cat) counts[cat.title] = (counts[cat.title] || 0) + 1;
        });
        const sorted = Object.entries(counts).sort((a,b)=>b[1]-a[1]).slice(0, 8);
        const total = classifications.length;
        const shortQ = q.replace(/^\[(Pre|Post)\] /,'').substring(0, 55);
        const chartId = `insights-chart-${qi}`;

        html += `<div class="glass-card" style="margin-bottom:1.5rem;">
            <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:1rem;flex-wrap:wrap;gap:0.5rem;">
                <h3 style="font-weight:600;font-size:0.95rem;flex:1;">${shortQ}</h3>
                <div style="display:flex; gap:0.5rem; flex-shrink:0;">
                    <button class="btn-primary" style="padding:0.4rem 1rem;font-size:0.8rem;" onclick="exportTabChart('${chartId}','insights_${qi}')">⬇ Export Chart</button>
                    <button class="btn-secondary" style="padding:0.4rem 1rem;font-size:0.8rem;" onclick="window.location.href='/api/export/data/clusters?question=${encodeURIComponent(q)}'">⬇ Export Data</button>
                </div>
            </div>
            <div style="height:220px;position:relative;margin-bottom:1rem;">
                <canvas id="${chartId}"></canvas>
            </div>
            ${sorted.map(([cat, n], i) => {
                const pct = Math.round(n/total*100);
                const col = palette[i % palette.length];
                return `<div style="margin-bottom:0.65rem;">
                    <div style="display:flex;justify-content:space-between;margin-bottom:0.25rem;">
                        <span style="font-size:0.85rem;">${cat}</span>
                        <span style="font-size:0.78rem;color:var(--text-muted);">${n} (${pct}%)</span>
                    </div>
                    <div class="bar-track"><div class="bar-fill" style="width:${pct}%;background:linear-gradient(90deg,${col}99,${col});"></div></div>
                </div>`;
            }).join('')}
        </div>`;
    });

    content.innerHTML = html || '<div class="glass-card"><p style="color:var(--text-muted);">No analysis data available. Run AI Engine or load demo data.</p></div>';

    // Draw pie/doughnut charts
    qs.slice(0, 6).forEach((q, qi) => {
        const data = window._clustersData[q];
        const classifications = data.classifications || [];
        const flatTax = data.flat_taxonomy || [];
        if (!classifications.length || !flatTax.length) return;

        const counts = {};
        classifications.forEach(c => {
            const cid = c.human_override || c.cluster_id;
            const cat = flatTax.find(f => f.id === cid);
            if (cat) counts[cat.title] = (counts[cat.title] || 0) + 1;
        });
        const sorted = Object.entries(counts).sort((a,b)=>b[1]-a[1]).slice(0,8);
        const chartId = `insights-chart-${qi}`;

        setTimeout(() => {
            const ctx = $(`#${chartId}`); if (!ctx) return;
            new Chart(ctx, {
                type: 'doughnut',
                data: {
                    labels: sorted.map(([lbl]) => lbl.substring(0,25)),
                    datasets: [{ data: sorted.map(([,n])=>n), backgroundColor: palette, borderWidth: 2, borderColor: 'rgba(3,7,15,0.8)', hoverBorderColor: '#fff' }],
                },
                options: {
                    responsive: true, maintainAspectRatio: false,
                    plugins: {
                        legend: { position:'right', labels: { color:'rgba(180,200,230,0.8)', boxWidth:12, font:{family:"'Space Grotesk'",size:11} } },
                        tooltip: { backgroundColor:'rgba(5,11,23,0.94)', titleColor:'#f0f6ff', bodyColor:'rgba(180,200,230,0.7)', padding:10 },
                    },
                },
            });
        }, qi * 80 + 60);
    });
}

/* ── 13. REPORT ─────────────────────────────────────────────────────────── */
const REPORT_SECTIONS = [
    { key: 'executive_summary',    label: '1. Executive Summary' },
    { key: 'method_sample',        label: '2. Method & Sample' },
    { key: 'quantitative_results', label: '3. Quantitative Results' },
    { key: 'qualitative_findings', label: '4. Qualitative Findings' },
    { key: 'pre_post_comparison',  label: '5. Pre/Post Comparison' },
    { key: 'recommendations',      label: '6. Recommendations' },
    { key: 'appendix',             label: '7. Appendix' },
];
let _currentSection = null;
let _reportSections = {};

function buildReportSectionList() {
    const list = $('#report-section-list');
    if (!list) return;
    list.innerHTML = REPORT_SECTIONS.map(s => `
        <button class="report-section-btn" data-section="${s.key}" id="sec-btn-${s.key}">
            <span class="section-status" id="sec-status-${s.key}">⬜</span>
            ${s.label}
        </button>`).join('');

    list.addEventListener('click', e => {
        const btn = e.target.closest('.report-section-btn');
        if (!btn) return;
        $$('.report-section-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        _currentSection = btn.dataset.section;
        const lbl = REPORT_SECTIONS.find(s => s.key === _currentSection)?.label;
        $('#report-current-section-title').textContent = lbl || _currentSection;
        $('#btn-gen-section').disabled = false;
        const editor = $('#report-editor');
        if (editor) editor.value = _reportSections[_currentSection] || `Click 'Generate' to create this section with AI.\n\nOr type your own content here.`;
    });

    $('#report-editor')?.addEventListener('input', () => {
        if (_currentSection) {
            _reportSections[_currentSection] = $('#report-editor').value;
            const s = $(`#sec-status-${_currentSection}`);
            if (s) s.textContent = '✏️';
        }
    });
}

async function loadReport() {
    try {
        const data = await api('/api/report/sections');
        _reportSections = data;
        Object.entries(data).forEach(([key, text]) => {
            if (text) { const s = $(`#sec-status-${key}`); if(s) s.textContent = '✅'; }
        });
    } catch(e) {}
}

async function generateCurrentSection() {
    if (!_currentSection) return;
    const btn = $('#btn-gen-section'), statusEl = $('#report-gen-status'), editor = $('#report-editor');
    const sStatus = $(`#sec-status-${_currentSection}`);
    btn.disabled = true; btn.textContent = 'Generating…';
    if (statusEl) statusEl.textContent = 'Generating…';
    if (sStatus)  sStatus.textContent = '🔄';
    if (editor)   editor.value = '';

    try {
        const res = await fetch(`/api/report/generate/${_currentSection}`, { method:'POST' });
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let full = '';
        while (true) {
            const {done, value} = await reader.read();
            if (done) break;
            full += decoder.decode(value);
            if (editor) editor.value = full;
        }
        _reportSections[_currentSection] = full;
        if (sStatus) sStatus.textContent = '✅';
        if (statusEl) { statusEl.textContent = 'Generated ✓'; statusEl.style.color = '#6ee7b7'; }
    } catch(e) {
        if (statusEl) { statusEl.textContent = `Error: ${e.message}`; statusEl.style.color = '#fca5a5'; }
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<span>✦</span> Generate';
        lucide.createIcons();
    }
}

async function generateAllSections() {
    const btn = $('#btn-gen-all-sections');
    btn.disabled = true; btn.textContent = 'Working…';
    for (const s of REPORT_SECTIONS) {
        _currentSection = s.key;
        $$('.report-section-btn').forEach(b => b.classList.toggle('active', b.dataset.section === s.key));
        const titleEl = $('#report-current-section-title');
        if (titleEl) titleEl.textContent = s.label;
        await generateCurrentSection();
        await new Promise(r => setTimeout(r, 400));
    }
    btn.disabled = false; btn.textContent = 'Generate All';
}

async function exportReport() {
    try {
        const res = await fetch('/api/report/export', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({ sections: _reportSections }),
        });
        if (!res.ok) throw new Error((await res.json()).detail || 'Export failed');
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a'); a.href=url; a.download='BC4D_Evaluation_Report.docx'; a.click();
        URL.revokeObjectURL(url);
    } catch(e) {
        const s = $('#report-gen-status');
        if (s) { s.textContent = `Export error: ${e.message}`; s.style.color='#fca5a5'; }
    }
}

/* ── 14. SETTINGS ───────────────────────────────────────────────────────── */
async function loadSettings() {
    try {
        const data = await api('/api/settings');
        const keyEl     = $('#input-api-key');
        const staffelEl = $('#input-staffel-name');
        if (keyEl && data.api_key) keyEl.value = data.api_key;
        if (staffelEl && data.staffel_name) staffelEl.value = data.staffel_name;
        const info = $('#session-info');
        if (info) info.innerHTML = `
            Pre-survey: <strong>${data.n_pre || 0}</strong> respondents<br>
            Post-survey: <strong>${data.n_post || 0}</strong> respondents<br>
            Matched pairs: <strong>${data.matched_pairs || 0}</strong><br>
            Tagged questions: <strong>${data.tagged_questions || 0}</strong><br>
            Report sections: <strong>${data.report_sections || 0}</strong><br>
            Staffel: <strong>${data.staffel_name || '(not set)'}</strong>`;
    } catch(e) { console.warn('Settings:', e.message); }
}

async function saveSettings() {
    const key = $('#input-api-key')?.value.trim();
    const status = $('#settings-status');
    if (!key) { if(status){status.textContent='Enter an API key first.';status.style.color='#fca5a5';} return; }
    if (status) { status.textContent='Saving & testing…'; status.style.color='var(--particle-blue)'; }
    try {
        const data = await api('/api/settings', { method:'POST', body: JSON.stringify({ api_key: key }) });
        if (status) { status.textContent = data.message || 'Saved.'; status.style.color = '#6ee7b7'; }
    } catch(e) {
        if (status) { status.textContent = `Error: ${e.message}`; status.style.color = '#fca5a5'; }
    }
}

async function saveStaffelName() {
    const name = $('#input-staffel-name')?.value.trim();
    if (!name) return;
    try { await api('/api/settings', { method:'POST', body: JSON.stringify({ staffel_name: name }) }); }
    catch(e) {}
}

async function clearSession() {
    const s = $('#session-clear-status');
    try {
        await api('/api/session/clear', { method: 'POST' });
        _reportSections = {}; window._clustersData = {};
        if (s) { s.textContent = 'Session cleared.'; s.style.color = '#6ee7b7'; }
        setTimeout(loadSettings, 300);
    } catch(e) {
        if (s) { s.textContent = `Error: ${e.message}`; s.style.color = '#fca5a5'; }
    }
}
