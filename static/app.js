/**
 * ClearTrace — Enterprise Frontend Application & PWA Controller v2.0
 * Connects the 9 platform modules to the live FastAPI engine with interactive visualizations.
 */

const STATE = {
  activeModule: 'command-center',
  dataset: null,
  qualityScore: null,
  findings: [],
  proposals: [],
  timeline: [],
  auditEvents: [],
  passport: null,
  mathFindings: [],
  mathTolerance: 0.01,
  customRules: [],
  comparisonSummary: null,
  ragStatus: null,
  ragHistory: [],
  observatoryFilter: 'ALL',
  workspaceSearch: '',
};

// ── PWA Service Worker & Install Lifecycle ───────────────────────────────────

let deferredInstallPrompt = null;

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    // Attempt registration at root scope /sw.js
    navigator.serviceWorker.register('/sw.js', { scope: '/' })
      .then((reg) => {
        console.log('ClearTrace PWA Service Worker registered at root:', reg.scope);
        reg.addEventListener('updatefound', () => {
          const newWorker = reg.installing;
          if (newWorker) {
            newWorker.addEventListener('statechange', () => {
              if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
                showToast('ClearTrace update ready. Reloading...', 'info');
                setTimeout(() => window.location.reload(), 1200);
              }
            });
          }
        });
      })
      .catch((err) => {
        // Fallback to /static/sw.js
        navigator.serviceWorker.register('/static/sw.js')
          .then((reg) => console.log('ClearTrace PWA Service Worker active (fallback):', reg.scope))
          .catch((e) => console.warn('PWA registration error:', e));
      });
  });

  // Check for PWA updates whenever app comes to foreground on mobile / iOS
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible' && 'serviceWorker' in navigator) {
      navigator.serviceWorker.getRegistration().then((reg) => {
        if (reg) reg.update().catch(() => {});
      });
    }
  });
}

window.addEventListener('beforeinstallprompt', (e) => {
  e.preventDefault();
  deferredInstallPrompt = e;
  console.log('ClearTrace PWA installation prompt ready.');
  const installCard = document.getElementById('pwa-install-banner');
  if (installCard) installCard.style.display = 'block';
});

window.addEventListener('appinstalled', () => {
  console.log('ClearTrace PWA was successfully installed.');
  deferredInstallPrompt = null;
  showToast('ClearTrace PWA installed successfully!', 'success');
  const installCard = document.getElementById('pwa-install-banner');
  if (installCard) installCard.style.display = 'none';
});

// ── Online / Offline / Authentication Monitor ────────────────────────────────

function triggerConnectivityBanner(type, message, showActionBtn = false, actionText = 'Re-authenticate') {
  const banner = document.getElementById('connectivity-banner');
  const bannerText = document.getElementById('connectivity-text');
  const actionBtn = document.getElementById('connectivity-action-btn');
  if (!banner || !bannerText) return;

  banner.className = 'connectivity-banner ' + type;
  bannerText.textContent = message;
  if (actionBtn) {
    actionBtn.style.display = showActionBtn ? 'inline-block' : 'none';
    actionBtn.textContent = actionText;
  }
  banner.style.display = 'flex';

  if (type === 'online') {
    setTimeout(() => {
      banner.style.display = 'none';
      banner.className = 'connectivity-banner';
    }, 2800);
  }
}

function triggerAuthExpiredBanner(message) {
  triggerConnectivityBanner(
    'auth-expired',
    '🔐 ' + (message || 'ClearTrace sign-in required.'),
    true,
    'Sign In'
  );
}

function handleConnectivityAction() {
  showClearTraceLogin();
}

function showClearTraceLogin() {
  const existing = document.getElementById('ct-login-dialog');
  if (existing) {
    existing.showModal();
    existing.querySelector('input').focus();
    return;
  }

  const dialog = document.createElement('dialog');
  dialog.id = 'ct-login-dialog';
  dialog.style.cssText =
    'width:calc(100% - 40px);max-width:420px;box-sizing:border-box;' +
    'padding:30px;border-radius:20px;border:1px solid #384765;' +
    'background:#101a30;color:#f1f5ff;box-shadow:0 25px 90px #000a;' +
    'font:15px system-ui,sans-serif';

  dialog.innerHTML = `
    <h2 style="font-size:25px;margin:0 0 12px">
      Welcome to ClearTrace
    </h2>
    <p style="color:#b8c7de;line-height:1.5">
    Sign in with an email code to save your own workspace, or explore and repair a sample as a judge.
    </p>
    <form id="ct-login-form">
      <label for="ct-login-email" style="display:block;margin:12px 0 6px;color:#b8c7de">Email address</label>
      <input id="ct-login-email"
        type="email" required autocomplete="email" maxlength="254"
        aria-label="Email address"
        placeholder="you@example.com"
        style="width:100%;box-sizing:border-box;padding:14px;
        background:#080e1e;color:white;border:1px solid #506589;
        border-radius:10px;font-size:16px">
      <div id="ct-code-wrap" hidden>
        <label for="ct-login-code" style="display:block;margin:12px 0 6px;color:#b8c7de">6-digit code</label>
        <input id="ct-login-code" type="text" inputmode="numeric" pattern="[0-9]{6}"
          maxlength="6" autocomplete="one-time-code" aria-label="Email verification code"
          placeholder="Enter the code from your email"
          style="width:100%;box-sizing:border-box;padding:14px;
          background:#080e1e;color:white;border:1px solid #506589;
          border-radius:10px;font-size:16px;letter-spacing:.2em">
      </div>
      <button id="ct-change-email" type="button" hidden
        style="margin-top:8px;border:0;background:transparent;color:#a9c6ff;font-size:13px">
        Use a different email
      </button>
      <button id="ct-login-button" type="submit"
        style="margin-top:16px;width:100%;padding:14px;
        border:0;border-radius:10px;background:#467dec;
        color:white;font-size:16px;font-weight:700">
        Email me a sign-in code
      </button>
      <p id="ct-login-error" role="alert"
        style="color:#ffaaaa;min-height:20px"></p>
    </form>
    <button id="ct-google-login" type="button" hidden
      style="margin-top:8px;width:100%;padding:13px;border:1px solid #506589;border-radius:10px;
      background:#fff;color:#202938;font-size:15px;font-weight:700">
      Continue with Google
    </button>
    <div style="border-top:1px solid #384765;margin-top:12px;padding-top:16px">
      <button id="ct-public-demo" type="button"
        style="width:100%;padding:13px;border:1px solid #506589;border-radius:10px;
        background:transparent;color:#dce8ff;font-size:15px;font-weight:650">
        Explore sample workspace · no sign-in
      </button>
      <p style="color:#8fa2bf;font-size:12px;line-height:1.5;margin:9px 0 0">
        Explore and repair sample data in a temporary workspace. Personal file uploads need email sign-in.
      </p>
    </div>
  `;

  document.body.appendChild(dialog);
  dialog.addEventListener('cancel', event => event.preventDefault());
  dialog.showModal();

  const form = dialog.querySelector('#ct-login-form');
  const emailInput = dialog.querySelector('#ct-login-email');
  const codeInput = dialog.querySelector('#ct-login-code');
  const codeWrap = dialog.querySelector('#ct-code-wrap');
  const changeEmailButton = dialog.querySelector('#ct-change-email');
  const button = dialog.querySelector('#ct-login-button');
  const demoButton = dialog.querySelector('#ct-public-demo');
  const googleButton = dialog.querySelector('#ct-google-login');
  const error = dialog.querySelector('#ct-login-error');
  let codeRequested = false;

  emailInput.focus();

  fetch('/api/auth/status', { credentials: 'same-origin', cache: 'no-store' })
    .then(response => response.json())
    .then(status => { googleButton.hidden = !status.google_sign_in_enabled; })
    .catch(() => {});
  googleButton.addEventListener('click', () => { window.location.assign('/api/auth/google/start'); });

  changeEmailButton.addEventListener('click', () => {
    codeRequested = false;
    codeWrap.hidden = true;
    codeInput.required = false;
    codeInput.value = '';
    changeEmailButton.hidden = true;
    button.textContent = 'Email me a sign-in code';
    error.textContent = '';
    emailInput.focus();
  });

  demoButton.addEventListener('click', async () => {
    demoButton.disabled = true;
    error.style.color = '#ffaaaa';
    error.textContent = '';
    try {
      const response = await fetch('/api/auth/public-demo', {
        method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
        body: '{}'
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok || result.success !== true) throw new Error(result.detail || 'Could not open the sample workspace.');
      window.location.reload();
    } catch (err) {
      error.textContent = err.message || 'Could not open the sample workspace.';
      demoButton.disabled = false;
    }
  });

  form.addEventListener('submit', async event => {
    event.preventDefault();
    const email = emailInput.value.trim().toLowerCase();
    if (!email) return;

    button.disabled = true;
    error.textContent = '';

    try {
      const response = await fetch(codeRequested ? '/api/auth/verify' : '/api/auth/request-code', {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          'Content-Type': 'application/json',
          'X-Requested-With': 'XMLHttpRequest'
        },
        body: JSON.stringify(codeRequested ? { email, code: codeInput.value.trim() } : { email })
      });

      const result = await response.json().catch(() => ({}));

      if (!response.ok || result.success !== true) {
        throw new Error(result.detail || 'Sign-in could not be completed.');
      }

      if (!codeRequested) {
        codeRequested = true;
        codeWrap.hidden = false;
        codeInput.required = true;
        changeEmailButton.hidden = false;
        button.textContent = 'Verify code and sign in';
        error.style.color = '#a9e5c1';
        error.textContent = 'If the address can receive sign-in mail, a code is on its way.';
        codeInput.focus();
        return;
      }

      codeInput.value = '';

      const check = await fetch('/api/auth/status', {
        credentials: 'same-origin',
        cache: 'no-store'
      });

      const status = await check.json();

      if (!check.ok || !status.is_authenticated) {
        throw new Error('Secure login cookie was not accepted.');
      }

      window.location.reload();

    } catch (err) {
      error.style.color = '#ffaaaa';
      error.textContent = err.message || 'Sign-in failed.';
      if (codeRequested) {
        codeInput.value = '';
        codeInput.focus();
      } else {
        emailInput.focus();
      }
    } finally {
      button.disabled = false;
    }
  });
}

function updateConnectivityStatus() {
  if (navigator.onLine) {
    triggerConnectivityBanner('online', '✓ Reconnected to ClearTrace Engine');
    refreshAll().catch(() => {});
  } else {
    triggerConnectivityBanner('warning', '⚡ Offline Mode · App shell active. Engine connection required for data operations.');
  }
}

window.addEventListener('online', updateConnectivityStatus);
window.addEventListener('offline', updateConnectivityStatus);

// ── Mobile Navigation Drawer Controls ───────────────────────────────────────

function toggleMobileSheet(forceOpen) {
  const sheet = document.getElementById('mobile-sheet');
  const overlay = document.getElementById('mobile-sheet-overlay');
  if (!sheet || !overlay) return;

  const isOpen = forceOpen !== undefined ? forceOpen : !sheet.classList.contains('active');
  sheet.classList.toggle('active', isOpen);
  overlay.classList.toggle('active', isOpen);
  document.body.style.overflow = isOpen ? 'hidden' : '';
}

function switchModuleAndClose(moduleId) {
  switchModule(moduleId);
  toggleMobileSheet(false);
}

// ── Navigation Controller ────────────────────────────────────────────────────

function switchModule(moduleId) {
  STATE.activeModule = moduleId;

  // Update desktop sidebar
  document.querySelectorAll('.nav-link').forEach((link) => {
    link.classList.toggle('active', link.dataset.module === moduleId);
  });

  // Update mobile tab bar
  document.querySelectorAll('.mobile-tab').forEach((tab) => {
    tab.classList.toggle('active', tab.dataset.module === moduleId);
  });

  // Update viewport sections
  document.querySelectorAll('.view-section').forEach((sec) => {
    sec.classList.toggle('active', sec.id === `view-${moduleId}`);
  });

  // Scroll to top of content
  window.scrollTo({ top: 0, behavior: 'smooth' });

  // Render active module
  if (moduleId === 'command-center') renderCommandCenter();
  if (moduleId === 'workspace') renderWorkspace();
  if (moduleId === 'math-intelligence') renderMathIntelligence();
  if (moduleId === 'observatory') renderObservatory();
  if (moduleId === 'repair-studio') renderRepairStudio();
  if (moduleId === 'rag-assistant') renderRagAssistant();
  if (moduleId === 'explainability') renderExplainability();
  if (moduleId === 'passport') renderPassport();
  if (moduleId === 'audit-ledger') renderAuditLedger();
  if (moduleId === 'trust-vault') renderTrustVault();
  if (moduleId === 'settings') renderSettings();
}

// ── Hardened API Client with Pre-Parsing Protocol & Auth Detection ───────────

async function api(endpoint, options = {}) {
  // Ensure same-origin credentials are sent on all requests so Cloudflare Access
  // CF_Authorization and server ct_session_id cookies are never lost.
  const headers = {
    'Accept': 'application/json',
    // CSRF sentinel: required by server on all state-mutating POST endpoints.
    // Browsers never send this header automatically on cross-origin requests.
    'X-Requested-With': 'XMLHttpRequest',
    ...(options.headers || {}),
  };
  if (options.body && !(options.body instanceof FormData) && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json';
  }

  // 30-second timeout: prevents indefinite hangs on Cloudflare Access login challenges
  // or unresponsive tunnel endpoints.
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 30000);

  const fetchOptions = {
    credentials: 'same-origin',
    ...options,
    headers,
    signal: controller.signal,
  };

  let res;
  try {
    res = await fetch(endpoint, fetchOptions);
    clearTimeout(timeoutId);
  } catch (netErr) {
    clearTimeout(timeoutId);
    // AbortError means timeout fired
    if (netErr.name === 'AbortError') {
      triggerConnectivityBanner('warning', '⏱️ Request timed out. ClearTrace engine not responding within 30s.');
      const timeoutErr = new Error('Request timed out after 30 seconds.');
      timeoutErr.name = 'TimeoutError';
      showToast('Request timed out. Check server status.', 'error');
      throw timeoutErr;
    }
    // True network failure (offline, DNS loss, or cross-origin redirect blockage)
    if (!navigator.onLine) {
      triggerConnectivityBanner('warning', '⚡ Offline Mode · Internet connection lost. App shell active.');
    } else {
      triggerConnectivityBanner('warning', '⚠️ Network interrupted. Unable to reach ClearTrace engine.');
    }
    const err = new Error('Network failure: Unable to communicate with ClearTrace engine.');
    err.name = 'NetworkError';
    showToast('Network error: Engine connection failed.', 'error');
    throw err;
  }

  // 1. Inspect Redirects: Cloudflare Access login challenge or SSO redirect
  const isCloudflareRedirect = res.redirected && (
    res.url.includes('/cdn-cgi/access/') ||
    res.url.includes('cloudflareaccess.com') ||
    res.url.includes('/login') ||
    !res.url.includes('/api/')
  );

  // 2. Inspect Content-Type before parsing JSON
  const contentType = (res.headers.get('content-type') || '').toLowerCase();
  const isHtml = contentType.includes('text/html');
  const isJson = contentType.includes('application/json');

  // 3. Detect Cloudflare Access Authentication / Session Expiration
  if (res.status === 401 || isCloudflareRedirect || (isHtml && (res.status === 200 || !res.ok))) {
    const authMessage = 'ClearTrace sign-in required. Use an email code or open the sample evaluation.';
    triggerAuthExpiredBanner(authMessage);
    const authErr = new Error(authMessage);
    authErr.name = 'AuthenticationError';
    authErr.status = res.status;
    showClearTraceLogin();
    throw authErr;
  }

  // 4. Handle HTTP Error Statuses (4xx, 5xx)
  if (!res.ok) {
    let errorDetail = res.statusText || 'API request failed';
    if (isJson) {
      try {
        const errJson = await res.json();
        errorDetail = errJson.detail || errJson.message || errJson.error || errorDetail;
      } catch (_) {}
    } else if (isHtml) {
      errorDetail = `Server returned HTML error (${res.status})`;
    }

    // Distinguish 503 engine unavailability from 500 server crashes
    if (res.status === 503) {
      triggerConnectivityBanner('warning', '⚠️ Engine Unavailable · ' + errorDetail);
    } else if (res.status >= 500) {
      triggerConnectivityBanner('error', `Server error (${res.status}): Engine encountered an error.`);
    }

    const httpErr = new Error(errorDetail);
    httpErr.status = res.status;
    httpErr.name = res.status >= 500 ? 'ServerError' : 'ClientError';
    showToast(errorDetail, 'error');
    throw httpErr;
  }

  // 5. Successful response: Validate JSON content-type
  if (!isJson) {
    const formatErr = new Error(`Protocol violation: Expected application/json from ${endpoint}, but received '${contentType}'`);
    formatErr.name = 'ProtocolError';
    showToast('Unexpected data format received from server.', 'error');
    throw formatErr;
  }

  return await res.json();
}

function syncFetch(url) {
  try {
    const xhr = new XMLHttpRequest();
    xhr.open('GET', url, false);
    xhr.setRequestHeader('Accept', 'application/json');
    xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
    xhr.send(null);
    if (xhr.status >= 200 && xhr.status < 300) {
      return JSON.parse(xhr.responseText);
    }
  } catch (e) {
    console.error('syncFetch failed for ' + url, e);
  }
  return null;
}

async function refreshAll() {
  if (window.location.search.includes('sync=1')) {
    STATE.dataset = syncFetch('/api/dataset/summary');
    STATE.qualityScore = syncFetch('/api/quality/score');
    STATE.findings = syncFetch('/api/quality/findings') || [];
    STATE.proposals = syncFetch('/api/repair/proposals') || [];
    STATE.timeline = syncFetch('/api/timemachine/timeline') || [];
    STATE.auditEvents = syncFetch('/api/audit/events') || [];
    STATE.passport = syncFetch('/api/passport');
    STATE.mathFindings = syncFetch('/api/math/findings?tolerance=' + STATE.mathTolerance) || [];
    STATE.customRules = syncFetch('/api/math/rules') || [];
    STATE.ragStatus = syncFetch('/api/rag/status');
    updateHeader();
    switchModule(STATE.activeModule);
    return;
  }
  try {
    const [summary, score, findings, proposals, timeline, audit, passport, mathFindings, customRules, ragStatus] = await Promise.all([
      api('/api/dataset/summary'),
      api('/api/quality/score'),
      api('/api/quality/findings'),
      api('/api/repair/proposals'),
      api('/api/timemachine/timeline'),
      api('/api/audit/events'),
      api('/api/passport'),
      api('/api/math/findings?tolerance=' + STATE.mathTolerance).catch(() => []),
      api('/api/math/rules').catch(() => []),
      api('/api/rag/status').catch(() => null),
    ]);

    STATE.dataset = summary;
    STATE.qualityScore = score;
    STATE.findings = findings;
    STATE.proposals = proposals;
    STATE.timeline = timeline;
    STATE.auditEvents = audit;
    STATE.passport = passport;
    STATE.mathFindings = mathFindings || [];
    STATE.customRules = customRules || [];
    STATE.ragStatus = ragStatus;

    updateHeader();
    switchModule(STATE.activeModule);
  } catch (err) {
    console.error('Refresh error:', err);
  }
}

function updateHeader() {
  if (!STATE.dataset) return;
  document.getElementById('header-filename').textContent = STATE.dataset.filename;
  document.getElementById('header-rev').textContent = `Revision ${STATE.dataset.revision}`;
  const formatTag = STATE.dataset.format ? ` [${STATE.dataset.format.toUpperCase()}]` : '';
  document.getElementById('header-meta').textContent = `${STATE.dataset.rows.toLocaleString()} rows · ${STATE.dataset.columns.length} columns${formatTag}`;

  // Badge counts (Desktop sidebar)
  document.getElementById('badge-repair-count').textContent = STATE.proposals.length;
  document.getElementById('badge-observatory-count').textContent = STATE.findings.length;
  const mathBadge = document.getElementById('badge-math-count');
  if (mathBadge) mathBadge.textContent = STATE.mathFindings.length;

  // Badge counts (Mobile bottom tabs)
  const mathTab = document.getElementById('badge-math-tab');
  if (mathTab) {
    mathTab.textContent = STATE.mathFindings.length;
    mathTab.style.display = STATE.mathFindings.length > 0 ? 'inline-block' : 'none';
  }
  const repairTab = document.getElementById('badge-repair-tab');
  if (repairTab) {
    repairTab.textContent = STATE.proposals.length;
    repairTab.style.display = STATE.proposals.length > 0 ? 'inline-block' : 'none';
  }

  // Badge counts (Mobile drawer sheet)
  const mathMobile = document.getElementById('badge-math-count-mobile');
  if (mathMobile) mathMobile.textContent = STATE.mathFindings.length;
  const obsMobile = document.getElementById('badge-observatory-count-mobile');
  if (obsMobile) obsMobile.textContent = STATE.findings.length;
  const repairMobile = document.getElementById('badge-repair-count-mobile');
  if (repairMobile) repairMobile.textContent = STATE.proposals.length;
}

// ── View Renderers ───────────────────────────────────────────────────────────

function renderCommandCenter() {
  const container = document.getElementById('view-command-center');
  if (!STATE.dataset || !STATE.qualityScore) return;

  const m = STATE.dataset.metrics;
  const s = STATE.qualityScore;

  // SVG Radial Circle metrics: radius=40, circum=251.3
  const circum = 251.3;
  const strokeOffset = Math.max(0, circum * (1 - s.overall_score / 100));

  // Severity counts
  const highCount = STATE.findings.filter(f => f.risk === 'High').reduce((sum, f) => sum + f.affected_count, 0);
  const medCount = STATE.findings.filter(f => f.risk === 'Medium' || f.risk === 'Review').reduce((sum, f) => sum + f.affected_count, 0);
  const lowCount = STATE.findings.filter(f => f.risk === 'Low').reduce((sum, f) => sum + f.affected_count, 0);
  const totalIssueVol = Math.max(1, highCount + medCount + lowCount);

  container.innerHTML = `
    <!-- Guided Hackathon Evaluation Walkthrough Banner (INV-002) -->
    <div class="guided-demo-banner">
      <div class="guided-demo-header">
        <div class="guided-demo-title">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--ct-teal-600)" stroke-width="2.2"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg>
          <span>Guided Evaluation Tour — Autonomous Quality, Math Invariants & Provenance</span>
        </div>
        <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
          <button class="btn btn-secondary btn-sm" onclick="openComparisonModal()" style="font-size:0.74rem;padding:4px 10px;">⚖️ Compare Revisions</button>
          <button class="btn btn-primary btn-sm" onclick="openExecutiveReportModal()" style="font-size:0.74rem;padding:4px 10px;">📄 Executive Report</button>
        </div>
      </div>
      <div class="guided-demo-steps">
        <div class="demo-step-pill ${STATE.dataset ? 'completed' : 'active'}" onclick="switchModule('workspace')">
          <span>1. Ingest Dataset (${STATE.dataset ? escapeHtml(STATE.dataset.filename) : 'Pending'})</span>
          <span style="font-size:0.68rem;color:var(--ct-teal-600);">✓</span>
        </div>
        <div class="demo-step-pill ${STATE.mathFindings.some(f => f.invoice_id === 'INV-002') ? 'active' : (STATE.mathFindings.length > 0 ? 'active' : 'completed')}" onclick="switchModule('math-intelligence')">
          <span>2. Math Mismatch (INV-002: +25.00)</span>
          <span style="font-size:0.68rem;">${STATE.mathFindings.some(f => f.invoice_id === 'INV-002') ? '⚠ 495 vs 520' : '✓'}</span>
        </div>
        <div class="demo-step-pill ${STATE.proposals.length > 0 ? 'active' : 'completed'}" onclick="switchModule('repair-studio')">
          <span>3. Review Candidate Fixes</span>
          <span style="font-size:0.68rem;">(${STATE.proposals.length} pending)</span>
        </div>
        <div class="demo-step-pill ${STATE.dataset.revision > 1 ? 'completed' : ''}" onclick="switchModule('repair-studio')">
          <span>4. Approve & Advance Rev</span>
          <span style="font-size:0.68rem;">Rev ${STATE.dataset.revision}</span>
        </div>
        <div class="demo-step-pill ${STATE.auditEvents.length > 0 ? 'completed' : ''}" onclick="switchModule('audit-ledger')">
          <span>5. Provenance Ledger & Undo</span>
          <span style="font-size:0.68rem;">(${STATE.auditEvents.length} events)</span>
        </div>
        <div class="demo-step-pill ${STATE.passport ? 'completed' : ''}" onclick="switchModule('passport')">
          <span>6. Cryptographic Passport</span>
          <span style="font-size:0.68rem;">SHA-256</span>
        </div>
      </div>
    </div>

    <!-- Quality Score Hero with Animated SVG Radial Gauge -->
    <div class="score-hero">
      <div class="score-radial-wrap">
        <svg class="score-radial-svg" viewBox="0 0 100 100">
          <circle class="score-radial-bg" cx="50" cy="50" r="40"/>
          <circle class="score-radial-progress" cx="50" cy="50" r="40"
                  stroke-dasharray="251.3"
                  stroke-dashoffset="${strokeOffset}"/>
        </svg>
        <div class="score-radial-text">
          <div class="score-num">${s.overall_score.toFixed(1)}</div>
          <div class="score-grade">GRADE ${s.grade}</div>
        </div>
      </div>
      <div class="score-info">
        <h3>Transparent Data Hygiene Score</h3>
        <p>${s.summary}</p>
        <div class="dimension-bars">
          ${s.components.map(c => `
            <div class="dim-box">
              <div class="dim-title">
                <span>${c.name}</span>
                <span>${c.raw_score}%</span>
              </div>
              <div class="dim-progress">
                <div class="dim-bar" style="width:${c.raw_score}%;"></div>
              </div>
            </div>
          `).join('')}
        </div>
      </div>
    </div>

    <!-- 4 KPI Metrics Grid -->
    <div class="grid-4">
      <div class="kpi-card">
        <div class="kpi-top">
          <div class="kpi-label">Completeness</div>
          <span style="color:var(--ct-teal-600);font-size:0.8rem;font-weight:700;">✓</span>
        </div>
        <div class="kpi-value" style="color:var(--ct-teal-600);">${m.completeness_pct.toFixed(1)}%</div>
        <div class="kpi-desc">Filled, non-null values across all ${m.total_cells.toLocaleString()} cells.</div>
      </div>

      <div class="kpi-card">
        <div class="kpi-top">
          <div class="kpi-label">Missing Values</div>
          <span style="color:${m.missing_cells > 0 ? 'var(--ct-gold-500)' : 'var(--ct-navy-400)'};font-size:0.8rem;font-weight:700;">⚠</span>
        </div>
        <div class="kpi-value" style="color:${m.missing_cells > 0 ? 'var(--ct-gold-500)' : 'var(--ct-navy-900)'};">${m.missing_cells.toLocaleString()}</div>
        <div class="kpi-desc">Blank or whitespace-only cells flagged for review.</div>
      </div>

      <div class="kpi-card">
        <div class="kpi-top">
          <div class="kpi-label">Duplicate Rows</div>
          <span style="color:${m.duplicate_rows > 0 ? 'var(--ct-risk-high-txt)' : 'var(--ct-navy-400)'};font-size:0.8rem;font-weight:700;">✕</span>
        </div>
        <div class="kpi-value" style="color:${m.duplicate_rows > 0 ? 'var(--ct-risk-high-txt)' : 'var(--ct-navy-900)'};">${m.duplicate_rows.toLocaleString()}</div>
        <div class="kpi-desc">Identical records across all columns. Removable via Repair Studio.</div>
      </div>

      <div class="kpi-card">
        <div class="kpi-top">
          <div class="kpi-label">Format Checks</div>
          <span style="color:${m.format_violations > 0 ? 'var(--ct-risk-med-txt)' : 'var(--ct-navy-400)'};font-size:0.8rem;font-weight:700;">!</span>
        </div>
        <div class="kpi-value" style="color:${m.format_violations > 0 ? 'var(--ct-risk-med-txt)' : 'var(--ct-navy-900)'};">${m.format_violations.toLocaleString()}</div>
        <div class="kpi-desc">Outer whitespace, category case variants, and invalid dates or numbers.</div>
      </div>
    </div>

    <!-- Severity Distribution Meter -->
    <div class="card" style="padding:16px 20px;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
        <span style="font-size:0.75rem;font-weight:700;text-transform:uppercase;letter-spacing:0.06em;color:var(--ct-navy-500);">Issue Severity Distribution</span>
        <span style="font-size:0.72rem;color:var(--ct-navy-500);">${STATE.findings.length} Finding Groups (${m.review_count} affected records)</span>
      </div>
      <div style="height:10px;background:var(--ct-navy-100);border-radius:999px;display:flex;overflow:hidden;gap:2px;">
        <div style="width:${(highCount/totalIssueVol)*100}%;background:var(--ct-risk-high-border);transition:width 0.4s;" title="High Risk: ${highCount}"></div>
        <div style="width:${(medCount/totalIssueVol)*100}%;background:var(--ct-gold-400);transition:width 0.4s;" title="Medium Risk: ${medCount}"></div>
        <div style="width:${(lowCount/totalIssueVol)*100}%;background:var(--ct-teal-400);transition:width 0.4s;" title="Low Risk: ${lowCount}"></div>
      </div>
      <div style="display:flex;gap:18px;margin-top:8px;font-size:0.72rem;">
        <span style="display:flex;align-items:center;gap:6px;"><span style="width:8px;height:8px;border-radius:50%;background:var(--ct-risk-high-txt);"></span> High: ${highCount}</span>
        <span style="display:flex;align-items:center;gap:6px;"><span style="width:8px;height:8px;border-radius:50%;background:var(--ct-gold-500);"></span> Medium: ${medCount}</span>
        <span style="display:flex;align-items:center;gap:6px;"><span style="width:8px;height:8px;border-radius:50%;background:var(--ct-teal-600);"></span> Low: ${lowCount}</span>
      </div>
    </div>

    <!-- Trust Note -->
    <div class="trust-banner">
      <b>Human-in-the-Loop Philosophy:</b> ClearTrace surfaces data anomalies for human review.
      An unusual value or candidate outlier is an invitation to inspect, not proof of an error.
      No data values are invented or silently destroyed without explicit consent.
    </div>

    <!-- Quick Actions Split -->
    <div class="grid-2">
      <div class="card">
        <div class="card-header">
          <div>
            <div class="card-title">Pending Actionable Repairs (${STATE.proposals.length})</div>
            <div class="card-subtitle">Ranked by volume and risk impact</div>
          </div>
          <button class="btn btn-primary btn-sm" onclick="switchModule('repair-studio')">Open Studio →</button>
        </div>
        ${STATE.proposals.length === 0 ? '<p style="color:var(--ct-navy-500);font-size:0.85rem;">No repairs pending approval.</p>' : `
          <div class="table-responsive">
            <table class="data-table">
              <thead><tr><th>Action</th><th>Column</th><th>Affected</th><th>Risk</th></tr></thead>
              <tbody>
                ${STATE.proposals.slice(0, 4).map(p => `
                  <tr>
                    <td><b>${p.kind}</b></td>
                    <td><code>${p.column}</code></td>
                    <td>${p.affected_records}</td>
                    <td><span class="badge" style="background:${p.risk==='High'?'var(--ct-risk-high-bg)':'var(--ct-risk-low-bg)'};color:${p.risk==='High'?'var(--ct-risk-high-txt)':'var(--ct-risk-low-txt)'};padding:2px 8px;border-radius:999px;font-size:0.7rem;font-weight:700;">${p.risk}</span></td>
                  </tr>
                `).join('')}
              </tbody>
            </table>
          </div>
        `}
      </div>

      <div class="card">
        <div class="card-header">
          <div>
            <div class="card-title">Recent Audit Operations</div>
            <div class="card-subtitle">Tamper-evident event log</div>
          </div>
          <button class="btn btn-secondary btn-sm" onclick="switchModule('audit-ledger')">Full Ledger →</button>
        </div>
        <div class="table-responsive">
          <table class="data-table">
            <thead><tr><th>Time UTC</th><th>Decision</th><th>Rule</th><th>Details</th></tr></thead>
            <tbody>
              ${STATE.auditEvents.slice(-4).reverse().map(e => `
                <tr>
                  <td style="font-size:0.75rem;font-family:var(--ct-font-mono);">${e.timestamp_utc.split(' ')[1]}</td>
                  <td><span style="font-weight:700;font-size:0.75rem;color:var(--ct-teal-600);">${e.decision.toUpperCase()}</span></td>
                  <td><code>${e.rule_id}</code></td>
                  <td style="font-size:0.78rem;">${e.reason}</td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  `;
}

function renderWorkspace() {
  const container = document.getElementById('view-workspace');
  if (!STATE.dataset) return;

  const filteredPreview = STATE.dataset.preview.filter(row => {
    if (!STATE.workspaceSearch) return true;
    const query = STATE.workspaceSearch.toLowerCase();
    return Object.values(row).some(val => String(val).toLowerCase().includes(query));
  });

  const warningsHtml = (STATE.dataset.warnings && STATE.dataset.warnings.length > 0)
    ? `<div style="background:var(--ct-gold-100);border-left:4px solid var(--ct-gold-500);padding:10px 14px;border-radius:6px;margin-bottom:18px;font-size:0.8rem;color:var(--ct-gold-700);">
        <b>Format Ingestion Notices:</b><br>${STATE.dataset.warnings.map(w => `• ${escapeHtml(w)}`).join('<br>')}
      </div>`
    : '';

  container.innerHTML = `
    <div class="card">
      <div class="card-header">
        <div>
          <div class="card-title">Multi-Format Data Import & Workspace</div>
          <div class="card-subtitle">Local memory parsing · CSV, Excel (.xlsx), and PDF (.pdf) · 10 MB strict cap · Zero cloud egress</div>
        </div>
        <div style="display:flex;gap:6px;flex-wrap:wrap;">
          <button class="btn btn-secondary btn-sm" onclick="loadDemoDataset()">Standard CSV Demo</button>
          <button class="btn btn-secondary btn-sm" onclick="loadMathDemo('csv')">Math Errors (CSV)</button>
          <button class="btn btn-secondary btn-sm" onclick="loadMathDemo('xlsx')">Math Errors (Excel .xlsx)</button>
          <button class="btn btn-secondary btn-sm" onclick="loadMathDemo('pdf')">Math Errors (PDF .pdf)</button>
        </div>
      </div>

      ${warningsHtml}

      <!-- Upload Drop Zone -->
      <div id="drop-zone" style="border:2px dashed var(--ct-navy-200);border-radius:12px;padding:30px;text-align:center;background:var(--ct-surface-alt);cursor:pointer;margin-bottom:20px;transition:border-color 0.2s;">
        <input type="file" id="file-input" accept=".csv, .xlsx, .xlsm, .pdf" style="display:none;" onchange="handleFileSelect(event)">
        <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="var(--ct-teal-500)" stroke-width="1.8" style="margin-bottom:8px;"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
        <div style="font-weight:700;font-size:1.05rem;color:var(--ct-navy-950);">Drop CSV, Excel (.xlsx), or PDF (.pdf) file here, or click to browse</div>
        <p style="font-size:0.8rem;color:var(--ct-navy-500);margin-top:4px;">Extracts table records with sheet/cell/page provenance. Never executes spreadsheet macros. Max 10 MB.</p>
      </div>

      <!-- Search & Preview Controls -->
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;flex-wrap:wrap;gap:8px;">
        <div style="font-weight:700;font-size:0.92rem;color:var(--ct-navy-950);">
          Dataset Preview: <span style="color:var(--ct-teal-600);font-family:var(--ct-font-mono);">${STATE.dataset.filename}</span> [${(STATE.dataset.format || 'csv').toUpperCase()}] (${filteredPreview.length} of ${STATE.dataset.rows.toLocaleString()} rows)
        </div>
        <input type="text" placeholder="Filter rows in preview..." value="${STATE.workspaceSearch}"
               oninput="STATE.workspaceSearch = this.value; renderWorkspace();"
               style="padding:6px 12px;border:1px solid var(--ct-navy-200);border-radius:6px;font-size:0.8rem;width:240px;background:var(--ct-surface-card);color:var(--ct-navy-900);">
      </div>

      <!-- Dataset Preview Table -->
      <div class="table-responsive" style="max-height:440px;overflow-y:auto;">
        <table class="data-table">
          <thead>
            <tr>
              <th style="width:40px;">#</th>
              ${STATE.dataset.columns.map(c => `<th>${c}</th>`).join('')}
            </tr>
          </thead>
          <tbody>
            ${filteredPreview.map((row, idx) => `
              <tr>
                <td style="font-size:0.7rem;color:var(--ct-navy-400);font-family:var(--ct-font-mono);">${idx + 1}</td>
                ${STATE.dataset.columns.map(c => `<td>${row[c] !== null && row[c] !== undefined ? escapeHtml(String(row[c])) : '<i style="color:var(--ct-navy-400);font-size:0.75rem;">null</i>'}</td>`).join('')}
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    </div>
  `;

  const dropZone = document.getElementById('drop-zone');
  dropZone.addEventListener('click', () => document.getElementById('file-input').click());
  dropZone.addEventListener('dragover', (e) => { e.preventDefault(); dropZone.style.borderColor = 'var(--ct-teal-500)'; });
  dropZone.addEventListener('dragleave', () => { dropZone.style.borderColor = 'var(--ct-navy-200)'; });
  dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    if (e.dataTransfer.files.length > 0) uploadFile(e.dataTransfer.files[0]);
  });
}

function renderObservatory() {
  const container = document.getElementById('view-observatory');
  if (!STATE.findings) return;

  const filter = STATE.observatoryFilter;
  const filteredFindings = STATE.findings.filter(f => {
    if (filter === 'HIGH') return f.risk === 'High';
    if (filter === 'MEDIUM') return f.risk === 'Medium' || f.risk === 'Review';
    if (filter === 'LOW') return f.risk === 'Low';
    return true;
  });

  container.innerHTML = `
    <div class="card">
      <div class="card-header">
        <div>
          <div class="card-title">Data Observatory</div>
          <div class="card-subtitle">Deterministic inspection across missing cells, duplicates, whitespace, category variations, dates, and outliers.</div>
        </div>
        <div style="display:flex;gap:6px;">
          <button class="btn btn-sm ${filter==='ALL'?'btn-primary':'btn-secondary'}" onclick="STATE.observatoryFilter='ALL';renderObservatory();">All (${STATE.findings.length})</button>
          <button class="btn btn-sm ${filter==='HIGH'?'btn-primary':'btn-secondary'}" onclick="STATE.observatoryFilter='HIGH';renderObservatory();">High</button>
          <button class="btn btn-sm ${filter==='MEDIUM'?'btn-primary':'btn-secondary'}" onclick="STATE.observatoryFilter='MEDIUM';renderObservatory();">Medium</button>
          <button class="btn btn-sm ${filter==='LOW'?'btn-primary':'btn-secondary'}" onclick="STATE.observatoryFilter='LOW';renderObservatory();">Low</button>
        </div>
      </div>

      ${filteredFindings.length === 0 ? '<p style="color:var(--ct-teal-600);font-weight:600;padding:24px 0;">No findings matching current filter.</p>' : `
        <div class="table-responsive">
          <table class="data-table">
            <thead>
              <tr>
                <th>Category</th>
                <th>Column</th>
                <th>Affected</th>
                <th>Risk</th>
                <th>Sample Locations</th>
                <th>Explanation & Recommendation</th>
                <th>Action Status</th>
              </tr>
            </thead>
            <tbody>
              ${filteredFindings.map(f => `
                <tr>
                  <td><b>${f.kind}</b></td>
                  <td><code>${f.column}</code></td>
                  <td><b>${f.affected_count}</b></td>
                  <td><span class="badge" style="background:${f.risk==='High'?'var(--ct-risk-high-bg)':'var(--ct-risk-med-bg)'};color:${f.risk==='High'?'var(--ct-risk-high-txt)':'var(--ct-risk-med-txt)'};padding:2px 8px;border-radius:999px;font-size:0.72rem;font-weight:700;">${f.risk}</span></td>
                  <td style="font-family:var(--ct-font-mono);font-size:0.76rem;">${f.example}</td>
                  <td style="font-size:0.78rem;">
                    <div>${f.explanation}</div>
                    <div style="color:var(--ct-teal-600);font-size:0.74rem;margin-top:3px;">💡 ${f.recommendation}</div>
                  </td>
                  <td>
                    ${f.action ? '<span style="color:var(--ct-teal-600);font-weight:700;font-size:0.75rem;">Actionable</span>' : '<span style="color:var(--ct-navy-500);font-size:0.75rem;">Review Only</span>'}
                  </td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      `}
    </div>
  `;
}

function renderRepairStudio() {
  const container = document.getElementById('view-repair-studio');
  if (!STATE.proposals) return;

  container.innerHTML = `
    <div class="card">
      <div class="card-header">
        <div>
          <div class="card-title">Repair Studio & Impact Simulator</div>
          <div class="card-subtitle">
            Autonomous repairs ranked by Smart Prioritization. Review side-by-side cell diffs before explicit approval.
          </div>
        </div>
        ${STATE.proposals.length > 0 ? `
          <button class="btn btn-primary" onclick="batchApproveAll()">✓ Approve All Safe Proposals (${STATE.proposals.length})</button>
        ` : ''}
      </div>

      ${STATE.proposals.length === 0 ? `
        <div style="padding:48px 24px;text-align:center;color:var(--ct-teal-600);">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-bottom:12px;"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
          <div style="font-weight:700;font-size:1.15rem;color:var(--ct-navy-950);">All actionable repairs have been applied</div>
          <p style="font-size:0.84rem;color:var(--ct-navy-500);margin-top:4px;">Dataset is now at Revision ${STATE.dataset.revision}. Remaining items are domain review items.</p>
        </div>
      ` : `
        <div>
          ${STATE.proposals.map(p => `
            <div style="border:1px solid var(--ct-navy-100);border-radius:12px;padding:22px;margin-bottom:18px;background:var(--ct-surface-card);box-shadow:var(--ct-shadow-xs);">
              <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
                <div>
                  <span style="font-weight:700;font-size:1.05rem;color:var(--ct-navy-950);">${p.kind} · Column '${p.column}'</span>
                  <span style="margin-left:8px;font-size:0.75rem;background:var(--ct-navy-100);padding:2px 8px;border-radius:4px;color:var(--ct-navy-700);font-weight:600;">Priority Score: ${p.priority_score}</span>
                </div>
                <span class="badge" style="background:${p.risk==='High'?'var(--ct-risk-high-bg)':'var(--ct-risk-low-bg)'};color:${p.risk==='High'?'var(--ct-risk-high-txt)':'var(--ct-risk-low-txt)'};padding:2px 8px;border-radius:999px;font-size:0.72rem;font-weight:700;">${p.risk} Risk</span>
              </div>

              <!-- Pre-Mutation Impact Simulation -->
              <div style="background:var(--ct-surface-alt);border-left:3px solid var(--ct-teal-500);border-radius:4px;padding:10px 14px;margin:10px 0;font-size:0.8rem;">
                <b>Impact Simulation:</b> ${p.impact_simulation.resolved_issue} · Data Loss Risk: <b>${p.impact_simulation.data_loss_risk}</b>.
                <div style="color:var(--ct-navy-500);margin-top:2px;">Side-effects: ${p.impact_simulation.side_effects}</div>
              </div>

              <!-- Side-by-Side Diff Table -->
              <div class="diff-box">
                <div style="font-weight:700;margin-bottom:8px;font-size:0.78rem;color:var(--ct-navy-700);">Value Transformation Previews (Sample):</div>
                ${p.diff_sample.map(d => `
                  <div class="diff-row">
                    <span class="diff-row-num">Row ${d.row}:</span>
                    <span class="diff-del">${escapeHtml(d.before)}</span>
                    <span style="color:var(--ct-teal-600);font-weight:bold;">→</span>
                    <span class="diff-add">${escapeHtml(d.after)}</span>
                  </div>
                `).join('')}
              </div>

              <!-- Approval Actions -->
              <div style="display:flex;gap:10px;margin-top:14px;">
                <button class="btn btn-success" onclick="applySingleRepair('${p.finding_id}')">✓ Approve & Apply</button>
                <button class="btn btn-danger" onclick="rejectRepair('${p.finding_id}')">✕ Reject</button>
              </div>
            </div>
          `).join('')}
        </div>
      `}
    </div>
  `;
}

function renderExplainability() {
  const container = document.getElementById('view-explainability');
  container.innerHTML = `
    <div class="card" style="margin-bottom:20px;">
      <div class="card-header">
        <div>
          <div class="card-title">Data Quality & Invariant Explainability Center</div>
          <div class="card-subtitle">Mathematically grounded explanations, failure risk analyses, and repair protocols for every detection rule.</div>
        </div>
      </div>

      <div class="grid-2">
        <!-- Rule 1: Decimal Invariants -->
        <div class="explain-card">
          <div style="display:flex;justify-content:space-between;align-items:center;">
            <span class="explain-badge-deterministic">Deterministic Invariant</span>
            <span class="badge" style="background:var(--ct-risk-high-bg);color:var(--ct-risk-high-txt);font-weight:700;font-size:0.68rem;padding:2px 8px;border-radius:999px;">High Severity</span>
          </div>
          <h4 style="color:var(--ct-navy-950);font-size:0.95rem;">1. Arbitrary-Precision Decimal Invariants</h4>
          <div style="font-family:var(--ct-font-mono);font-size:0.8rem;background:var(--ct-surface-alt);padding:8px 10px;border-radius:6px;border:1px solid var(--ct-navy-100);color:var(--ct-navy-900);">
            Expected Total = ROUND(Qty &times; Price &minus; Discount + Tax, 2)
          </div>
          <p style="font-size:0.8rem;color:var(--ct-navy-600);line-height:1.5;">
            Standard IEEE-754 binary floating-point representation causes silent rounding anomalies in financial systems (e.g. <code>0.1 + 0.2 &ne; 0.3</code>). ClearTrace parses numbers with Python <code>Decimal</code> and enforces <code>ROUND_HALF_UP</code> with configurable tolerance (&plusmn;${STATE.mathTolerance}).
          </p>
          <div class="explain-risk-callout">
            <b>Downstream Risk:</b> Financial reconciliation discrepancies, silent penny drift, tax audit penalties, and statutory reporting rejection.
          </div>
        </div>

        <!-- Rule 2: Category Variants -->
        <div class="explain-card">
          <div style="display:flex;justify-content:space-between;align-items:center;">
            <span class="explain-badge-deterministic">Deterministic Invariant</span>
            <span class="badge" style="background:var(--ct-risk-med-bg);color:var(--ct-risk-med-txt);font-weight:700;font-size:0.68rem;padding:2px 8px;border-radius:999px;">Medium Severity</span>
          </div>
          <h4 style="color:var(--ct-navy-950);font-size:0.95rem;">2. Category Frequency Tie-Breaking & Mode Clustering</h4>
          <div style="font-family:var(--ct-font-mono);font-size:0.8rem;background:var(--ct-surface-alt);padding:8px 10px;border-radius:6px;border:1px solid var(--ct-navy-100);color:var(--ct-navy-900);">
            Canonical = argmax<sub>x &isin; Cluster</sub>(Frequency(x)), ties broken lexicographically
          </div>
          <p style="font-size:0.8rem;color:var(--ct-navy-600);line-height:1.5;">
            Clusters text values using whitespace trimming and Unicode case-folding (<code>val.casefold()</code>). Rather than choosing an arbitrary spelling, ClearTrace selects the highest observed frequency variant in the dataset, preserving real business naming conventions.
          </p>
          <div class="explain-risk-callout">
            <b>Downstream Risk:</b> Fractured grouping in BI dashboards, duplicate dimension keys in warehouses, and inaccurate categorical aggregations.
          </div>
        </div>

        <!-- Rule 3: Calendar Verification -->
        <div class="explain-card">
          <div style="display:flex;justify-content:space-between;align-items:center;">
            <span class="explain-badge-deterministic">Deterministic Invariant</span>
            <span class="badge" style="background:var(--ct-risk-high-bg);color:var(--ct-risk-high-txt);font-weight:700;font-size:0.68rem;padding:2px 8px;border-radius:999px;">High Severity</span>
          </div>
          <h4 style="color:var(--ct-navy-950);font-size:0.95rem;">3. Strict Proleptic Gregorian Calendar Verification</h4>
          <div style="font-family:var(--ct-font-mono);font-size:0.8rem;background:var(--ct-surface-alt);padding:8px 10px;border-radius:6px;border:1px solid var(--ct-navy-100);color:var(--ct-navy-900);">
            Validate ISO 8601 YYYY-MM-DD &amp; reject invalid days (e.g. Feb 30)
          </div>
          <p style="font-size:0.8rem;color:var(--ct-navy-600);line-height:1.5;">
            Rejects impossible calendar dates that permissive parsers silently advance (e.g., February 30th rolling over into March 2nd). Disambiguates DD/MM vs MM/DD transpositions across timestamps to preserve historical transaction sequence.
          </p>
          <div class="explain-risk-callout">
            <b>Downstream Risk:</b> Database insertion errors, broken time-series indexes, corrupted cohort analyses, and erroneous payment due date calculations.
          </div>
        </div>

        <!-- Rule 4: IQR Statistical Outliers -->
        <div class="explain-card">
          <div style="display:flex;justify-content:space-between;align-items:center;">
            <span class="explain-badge-heuristic">Statistical Heuristic</span>
            <span class="badge" style="background:var(--ct-gold-100);color:var(--ct-gold-800);font-weight:700;font-size:0.68rem;padding:2px 8px;border-radius:999px;">Review / Warning</span>
          </div>
          <h4 style="color:var(--ct-navy-950);font-size:0.95rem;">4. Interquartile Range (IQR) Non-Destructive Outlier Flagging</h4>
          <div style="font-family:var(--ct-font-mono);font-size:0.8rem;background:var(--ct-surface-alt);padding:8px 10px;border-radius:6px;border:1px solid var(--ct-navy-100);color:var(--ct-navy-900);">
            IQR = Q3 &minus; Q1 &middot; Bounds = [Q1 &minus; 1.5 &times; IQR, Q3 + 1.5 &times; IQR]
          </div>
          <p style="font-size:0.8rem;color:var(--ct-navy-600);line-height:1.5;">
            Detects numerical observations lying outside the standard 1.5&times;IQR statistical spread. In strict adherence to our Human-in-the-Loop policy, candidate outliers are NEVER automatically deleted or imputed without explicit operator confirmation.
          </p>
          <div class="explain-risk-callout">
            <b>Downstream Risk:</b> Skewed statistical metrics and ML regression biases if anomalous, or loss of critical high-value sales signals if deleted blindly.
          </div>
        </div>

        <!-- Rule 5: Formula Injection Defense -->
        <div class="explain-card">
          <div style="display:flex;justify-content:space-between;align-items:center;">
            <span class="explain-badge-deterministic">Security Invariant</span>
            <span class="badge" style="background:var(--ct-risk-high-bg);color:var(--ct-risk-high-txt);font-weight:700;font-size:0.68rem;padding:2px 8px;border-radius:999px;">Critical Security</span>
          </div>
          <h4 style="color:var(--ct-navy-950);font-size:0.95rem;">5. Spreadsheet Dynamic Data Exchange (CSV/DDE) Sanitization</h4>
          <div style="font-family:var(--ct-font-mono);font-size:0.8rem;background:var(--ct-surface-alt);padding:8px 10px;border-radius:6px;border:1px solid var(--ct-navy-100);color:var(--ct-navy-900);">
            Prefix with &apos; if cell starts with [=, +, -, @, |, %]
          </div>
          <p style="font-size:0.8rem;color:var(--ct-navy-600);line-height:1.5;">
            Conforms to OWASP ASVS CSV Injection guidelines. Escapes executable formula tokens when generating CSV exports so that spreadsheet software (Excel, LibreOffice, Google Sheets) renders the cell as text rather than executing arbitrary macros or exfiltrating data.
          </p>
          <div class="explain-risk-callout">
            <b>Downstream Risk:</b> Remote code execution on analyst workstations, malicious DDE payload triggers, and credential exfiltration.
          </div>
        </div>

        <!-- Rule 6: Sum & Subtotal Invariants -->
        <div class="explain-card">
          <div style="display:flex;justify-content:space-between;align-items:center;">
            <span class="explain-badge-deterministic">Deterministic Invariant</span>
            <span class="badge" style="background:var(--ct-risk-high-bg);color:var(--ct-risk-high-txt);font-weight:700;font-size:0.68rem;padding:2px 8px;border-radius:999px;">High Severity</span>
          </div>
          <h4 style="color:var(--ct-navy-950);font-size:0.95rem;">6. Line Item Sum & Subtotal Reconciliation</h4>
          <div style="font-family:var(--ct-font-mono);font-size:0.8rem;background:var(--ct-surface-alt);padding:8px 10px;border-radius:6px;border:1px solid var(--ct-navy-100);color:var(--ct-navy-900);">
            Recorded Total = &sum; Line Items &plusmn; &epsilon;
          </div>
          <p style="font-size:0.8rem;color:var(--ct-navy-600);line-height:1.5;">
            Cross-verifies header totals against individual line items or quantity &times; unit price derivations. Flags missing line items, dropped transaction records, unapplied promotional discounts, or tax rate desynchronization across invoice batches.
          </p>
          <div class="explain-risk-callout">
            <b>Downstream Risk:</b> Inaccurate accounts payable ledger balances, vendor overpayment, and broken ERP integration feeds.
          </div>
        </div>
      </div>
    </div>
  `;
}

function renderPassport() {
  const container = document.getElementById('view-passport');
  if (!STATE.passport) return;
  const p = STATE.passport;

  container.innerHTML = `
    <div class="card">
      <div class="card-header">
        <div>
          <div class="card-title">Data Passport — Cryptographic Hygiene Certificate</div>
          <div class="card-subtitle">Verifiable proof linking raw input SHA-256 with cleaned working dataset and audit history.</div>
        </div>
        <div style="display:flex;gap:8px;">
          <a class="btn btn-primary" href="/api/export/passport" download>📥 Download Passport JSON</a>
        </div>
      </div>

      <!-- Passport Certificate Box -->
      <div class="passport-certificate">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;">
          <div>
            <div style="font-size:0.75rem;letter-spacing:0.12em;text-transform:uppercase;color:var(--ct-teal-600);font-weight:800;">ClearTrace Data Passport</div>
            <div style="font-size:1.5rem;font-weight:800;color:var(--ct-navy-950);margin:4px 0;">${p.passport_id}</div>
            <div style="font-size:0.8rem;color:var(--ct-navy-500);">Issued UTC: ${p.issued_at_utc} | Target File: <b>${p.filename}</b></div>
          </div>
          <div style="text-align:right;display:flex;align-items:center;gap:16px;">
            <div class="passport-seal">🛡️</div>
            <div>
              <div style="font-size:2.2rem;font-weight:800;color:var(--ct-teal-600);line-height:1;">${p.quality_score}</div>
              <div style="font-size:0.75rem;font-weight:700;color:var(--ct-navy-600);">Grade ${p.grade} Certified</div>
            </div>
          </div>
        </div>

        <hr style="border:0;border-top:1px solid var(--ct-navy-100);margin:20px 0;">

        <!-- SHA-256 Fingerprint Digests -->
        <div class="grid-2" style="margin-bottom:14px;">
          <div style="background:var(--ct-surface-card);padding:12px;border-radius:8px;border:1px solid var(--ct-navy-100);">
            <div style="font-size:0.7rem;text-transform:uppercase;font-weight:700;color:var(--ct-navy-500);margin-bottom:4px;">Original Raw CSV SHA-256 Digest:</div>
            <code style="font-size:0.76rem;word-break:break-all;color:var(--ct-navy-800);">${p.original_sha256}</code>
          </div>
          <div style="background:var(--ct-surface-card);padding:12px;border-radius:8px;border:1px solid var(--ct-navy-100);">
            <div style="font-size:0.7rem;text-transform:uppercase;font-weight:700;color:var(--ct-navy-500);margin-bottom:4px;">Cleaned Working CSV SHA-256 Digest:</div>
            <code style="font-size:0.76rem;word-break:break-all;color:var(--ct-navy-800);">${p.cleaned_sha256}</code>
          </div>
        </div>

        <!-- Metric badges -->
        <div style="display:flex;gap:20px;font-size:0.82rem;margin-top:12px;flex-wrap:wrap;color:var(--ct-navy-700);">
          <span>Rows: <b>${p.total_rows.toLocaleString()}</b></span>
          <span>Columns: <b>${p.total_columns}</b></span>
          <span>Completeness: <b>${p.completeness_pct}%</b></span>
          <span>Approved Repairs: <b>${p.repairs_applied_count}</b></span>
          <span>Unresolved Warnings: <b>${p.unresolved_warnings_count}</b></span>
        </div>

        <div style="margin-top:20px;font-size:0.74rem;color:var(--ct-navy-500);display:flex;justify-content:space-between;align-items:center;">
          <span>Integrity Signature: <code>${p.integrity_signature}</code></span>
          <span style="color:var(--ct-teal-600);font-weight:600;">✓ Cryptographically Signed & Tamper-Evident</span>
        </div>
      </div>
    </div>
  `;
}

function renderAuditLedger() {
  const container = document.getElementById('view-audit-ledger');
  if (!STATE.auditEvents || !STATE.timeline) return;

  container.innerHTML = `
    <div class="card">
      <div class="card-header">
        <div>
          <div class="card-title">Audit Ledger & Dataset Time Machine</div>
          <div class="card-subtitle">Point-in-time snapshots, revision comparisons, and complete audit trail.</div>
        </div>
        <div style="display:flex;gap:8px;">
          <button class="btn btn-secondary" onclick="undoLastAction()">↩ Undo Last Action</button>
          <button class="btn btn-danger" onclick="resetToBaseline()">↺ Reset to Raw Baseline</button>
        </div>
      </div>

      <!-- Time Machine Horizontal Carousel -->
      <div class="card-title" style="font-size:0.95rem;margin-bottom:8px;">Dataset Time Machine Snapshots</div>
      <div style="display:flex;gap:12px;overflow-x:auto;padding-bottom:12px;margin-bottom:20px;">
        ${STATE.timeline.map(s => `
          <div style="border:1px solid var(--ct-navy-100);border-radius:10px;padding:14px 16px;background:var(--ct-surface-alt);min-width:190px;flex-shrink:0;">
            <div style="display:flex;justify-content:space-between;align-items:center;">
              <span style="font-weight:800;font-size:0.86rem;color:var(--ct-teal-600);">Rev ${s.revision}</span>
              <span style="font-size:0.68rem;color:var(--ct-navy-400);font-family:var(--ct-font-mono);">${s.hash}</span>
            </div>
            <div style="font-size:0.75rem;margin:5px 0;color:var(--ct-navy-950);font-weight:700;">${s.action}</div>
            <div style="font-size:0.72rem;color:var(--ct-navy-500);line-height:1.4;">${s.description}</div>
            <div style="margin-top:10px;">
              <button class="btn btn-secondary btn-sm" style="width:100%;" onclick="restoreSnapshot(${s.revision})">Jump to Rev ${s.revision}</button>
            </div>
          </div>
        `).join('')}
      </div>

      <!-- Full Audit Events Table -->
      <div class="card-title" style="font-size:0.95rem;margin-bottom:8px;">Complete Append-Only Ledger</div>
      <div class="table-responsive">
        <table class="data-table">
          <thead>
            <tr>
              <th>Event ID</th>
              <th>Timestamp UTC</th>
              <th>Revision</th>
              <th>Actor</th>
              <th>Decision</th>
              <th>Rule ID</th>
              <th>Items Changed</th>
              <th>Audit Reason / Target</th>
            </tr>
          </thead>
          <tbody>
            ${STATE.auditEvents.slice().reverse().map(e => `
              <tr>
                <td><code>${e.event_id}</code></td>
                <td style="font-size:0.75rem;font-family:var(--ct-font-mono);">${e.timestamp_utc}</td>
                <td><span class="rev-tag">${e.rev_before} → ${e.rev_after}</span></td>
                <td>${e.actor}</td>
                <td><span style="font-weight:700;font-size:0.75rem;color:${e.decision==='approved'?'var(--ct-teal-600)':(e.decision==='undone'?'var(--ct-gold-500)':'var(--ct-navy-700)')};">${e.decision.toUpperCase()}</span></td>
                <td><code>${e.rule_id}</code></td>
                <td><b>${e.items_changed}</b></td>
                <td style="font-size:0.78rem;">${e.reason}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    </div>
  `;
}

function renderTrustVault() {
  const container = document.getElementById('view-trust-vault');
  container.innerHTML = `
    <div class="card">
      <div class="card-header">
        <div>
          <div class="card-title">Trust Vault & Security Posture</div>
          <div class="card-subtitle">Verified alignment with OWASP ASVS 5.0.0 recommendations.</div>
        </div>
      </div>

      <div class="grid-2">
        <div style="border:1px solid var(--ct-navy-100);border-radius:10px;padding:20px;background:var(--ct-surface-alt);">
          <div style="font-weight:700;color:var(--ct-navy-950);margin-bottom:8px;font-size:0.95rem;">🛡️ Data Sovereignty & Isolation</div>
          <ul style="font-size:0.82rem;color:var(--ct-navy-700);line-height:1.65;padding-left:18px;">
            <li><b>Zero Cloud Egress:</b> CSV datasets are held exclusively in-memory for active sessions.</li>
            <li><b>Session-Local Lifetime:</b> Revisions, snapshots, and audit records exist only during browser execution.</li>
            <li><b>Bounded Memory Consumption:</b> 10 MB strict file cap prevents denial-of-service memory exhaustion.</li>
          </ul>
        </div>

        <div style="border:1px solid var(--ct-navy-100);border-radius:10px;padding:20px;background:var(--ct-surface-alt);">
          <div style="font-weight:700;color:var(--ct-navy-950);margin-bottom:8px;font-size:0.95rem;">🔒 Export & Injection Safeguards</div>
          <ul style="font-size:0.82rem;color:var(--ct-navy-700);line-height:1.65;padding-left:18px;">
            <li><b>Formula Sanitization:</b> Cells starting with <code>=</code>, <code>@</code>, <code>+</code>, <code>-</code> escaped with prepended <code>'</code>.</li>
            <li><b>Tamper-Evident SHA-256:</b> Every dataset modification recalculates a cryptographic digest.</li>
            <li><b>Stale Revision Guards:</b> Concurrency protection prevents duplicate or out-of-order repairs (HTTP 409).</li>
          </ul>
        </div>
      </div>
    </div>
  `;
}

function renderSettings() {
  const container = document.getElementById('view-settings');
  const isDark = document.documentElement.getAttribute('data-theme') === 'dark';

  container.innerHTML = `
    <div class="card">
      <div class="card-header">
        <div>
          <div class="card-title">Settings & Preferences</div>
          <div class="card-subtitle">Configure theme, validation sensitivity, and export rules.</div>
        </div>
      </div>

      <div style="max-width:560px;margin-top:10px;">
        <div id="ct-account-security" style="padding:14px 0;border-bottom:1px solid var(--ct-navy-100);">
          <div style="font-weight:700;font-size:0.9rem;">Account security</div>
          <div id="ct-account-summary" style="font-size:0.8rem;color:var(--ct-navy-500);margin-top:6px;">Checking your verified account…</div>
          <form id="ct-role-form" hidden style="display:grid;grid-template-columns:1fr auto auto;gap:8px;margin-top:12px;">
            <input id="ct-role-email" type="email" maxlength="254" required placeholder="Existing account email" aria-label="Existing account email" style="min-width:0;padding:9px 10px;border:1px solid var(--ct-navy-200);border-radius:7px;background:var(--ct-surface);color:var(--ct-navy-900);">
            <select id="ct-role-value" aria-label="Organization role" style="padding:9px 10px;border:1px solid var(--ct-navy-200);border-radius:7px;background:var(--ct-surface);color:var(--ct-navy-900);"><option value="viewer">Viewer</option><option value="analyst">Analyst</option><option value="admin">Admin</option><option value="remove">Remove access</option></select>
            <button class="btn btn-secondary btn-sm" type="submit">Assign</button>
          </form>
          <div id="ct-role-result" role="status" style="font-size:0.78rem;margin-top:6px;"></div>
          <div style="font-size:0.73rem;color:var(--ct-navy-500);margin-top:8px;line-height:1.5;">Assigning a role adds that signed-in account to the owner’s shared organization workspace. Members can access its datasets according to their role. “Remove access” restores that account’s private workspace.</div>
        </div>

        <div style="display:flex;justify-content:space-between;align-items:center;padding:14px 0;border-bottom:1px solid var(--ct-navy-100);">
          <div>
            <div style="font-weight:600;font-size:0.9rem;">Interface Theme</div>
            <div style="font-size:0.75rem;color:var(--ct-navy-500);">Toggle between light canvas and dark palette.</div>
          </div>
          <button class="btn btn-secondary btn-sm" onclick="toggleTheme()">${isDark ? '☀️ Switch to Light' : '🌙 Switch to Dark'}</button>
        </div>

        <div style="display:flex;justify-content:space-between;align-items:center;padding:14px 0;border-bottom:1px solid var(--ct-navy-100);">
          <div>
            <div style="font-weight:600;font-size:0.9rem;">Outlier Sensitivity Threshold</div>
            <div style="font-size:0.75rem;color:var(--ct-navy-500);">IQR Multiplier for candidate outlier detection.</div>
          </div>
          <code>1.5 × IQR</code>
        </div>

        <div style="display:flex;justify-content:space-between;align-items:center;padding:14px 0;border-bottom:1px solid var(--ct-navy-100);">
          <div>
            <div style="font-weight:600;font-size:0.9rem;">Formula Sanitization on Export</div>
            <div style="font-size:0.75rem;color:var(--ct-navy-500);">Prevent CSV injection vulnerabilities.</div>
          </div>
          <span style="color:var(--ct-teal-600);font-weight:700;">Always Active</span>
        </div>

        <div style="display:flex;justify-content:space-between;align-items:center;padding:14px 0;border-bottom:1px solid var(--ct-navy-100);">
          <div>
            <div style="font-weight:600;font-size:0.9rem;">Progressive Web App (PWA)</div>
            <div style="font-size:0.75rem;color:var(--ct-navy-500);">Install ClearTrace to home screen on Android or iPhone.</div>
          </div>
          <button class="btn btn-primary btn-sm" onclick="triggerPwaInstall()">
            📱 Install App
          </button>
        </div>

        <div style="margin-top:16px;padding:16px;background:var(--ct-surface-alt);border:1px solid var(--ct-navy-100);border-radius:10px;">
          <div style="font-weight:700;font-size:0.85rem;color:var(--ct-navy-950);margin-bottom:8px;">📱 Mobile PWA Architecture</div>
          <div style="font-size:0.75rem;color:var(--ct-navy-600);line-height:1.6;">
            <div>• <b>Application Shell:</b> Precached offline via Service Worker (<code>cleartrace-shell-v2.1.0</code>).</div>
            <div>• <b>Data Sovereignty:</b> Strict <code>Network-Only</code> for all <code>/api/</code> endpoints. Customer records are never stored in browser caches.</div>
            <div>• <b>Online Engine Operations:</b> Ingestion, math invariants, RAG searches, and repairs execute securely with the connected backend.</div>
          </div>
        </div>
      </div>
    </div>
  `;

  fetch('/api/auth/status', { credentials: 'same-origin', cache: 'no-store' })
    .then(response => response.json())
    .then(status => {
      const summary = document.getElementById('ct-account-summary');
      if (!summary) return;
      summary.textContent = status.is_authenticated
        ? `${status.email || 'Verified account'} · ${status.role || 'member'} role · Owner alerts ${status.owner_alerts_enabled ? 'on' : 'not configured'}${status.google_sign_in_enabled ? ' · Google sign-in on' : ''}`
        : (status.is_public_demo ? 'Temporary sample workspace · no personal account signed in' : 'No signed-in account');
      if (status.role === 'owner' || status.role === 'admin') {
        const form = document.getElementById('ct-role-form');
        if (status.role === 'admin') form.querySelector('option[value="admin"]').remove();
        form.hidden = false;
        form.style.display = 'grid';
        form.addEventListener('submit', async event => {
          event.preventDefault();
          const result = document.getElementById('ct-role-result');
          result.textContent = 'Saving…';
          try {
            const response = await api('/api/auth/role', { method: 'POST', body: JSON.stringify({
              email: document.getElementById('ct-role-email').value.trim(),
              role: document.getElementById('ct-role-value').value
            }) });
            result.textContent = response.success ? 'Role updated.' : (response.detail || 'Could not update role.');
          } catch (error) { result.textContent = error.message || 'Could not update role.'; }
        });
      }
    }).catch(() => {
      const summary = document.getElementById('ct-account-summary');
      if (summary) summary.textContent = 'Account security status is temporarily unavailable.';
    });
}

function triggerPwaInstall() {
  if (deferredInstallPrompt) {
    deferredInstallPrompt.prompt();
    deferredInstallPrompt.userChoice.then((choice) => {
      if (choice.outcome === 'accepted') {
        showToast('ClearTrace installation accepted.', 'success');
      }
      deferredInstallPrompt = null;
    });
  } else {
    const isStandalone = window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone;
    if (isStandalone) {
      showToast('ClearTrace is already running in standalone PWA mode.', 'info');
    } else {
      showToast('To install: on Chrome tap menu (⋮) > Install App. On iOS Safari tap Share (⬆) > Add to Home Screen.', 'info');
    }
  }
}

function renderMathIntelligence() {
  const container = document.getElementById('view-math-intelligence');
  if (!STATE.dataset) return;

  const mf = STATE.mathFindings;
  const mismatches = mf.filter(f => f.rule_id === 'MATH_MISMATCH');
  const invalids = mf.filter(f => f.rule_id === 'INVALID_NUMBER');
  const negatives = mf.filter(f => f.rule_id === 'NEGATIVE_NOT_ALLOWED');
  const missing = mf.filter(f => f.rule_id === 'MISSING_TOTAL');
  const discounts = mf.filter(f => f.rule_id === 'DISCOUNT_EXCEEDS_SUBTOTAL');

  container.innerHTML = `
    <!-- Header with Tolerance Controls -->
    <div class="card" style="margin-bottom:20px;">
      <div class="card-header" style="flex-wrap:wrap;gap:12px;">
        <div>
          <div class="card-title">Mathematical Error Intelligence</div>
          <div class="card-subtitle">Deterministic Decimal Arithmetic Validation · No LLM Hallucinations in Numerical Calculations</div>
        </div>
        <div style="display:flex;align-items:center;gap:10px;">
          <label style="font-size:0.8rem;font-weight:600;color:var(--ct-navy-700);">Tolerance:</label>
          <input type="number" step="0.001" min="0" value="${STATE.mathTolerance}" id="math-tolerance-input"
                 style="width:75px;padding:5px 8px;border:1px solid var(--ct-navy-200);border-radius:6px;font-size:0.8rem;background:var(--ct-surface-card);color:var(--ct-navy-900);">
          <button class="btn btn-secondary btn-sm" onclick="updateMathTolerance()">Recalculate</button>
        </div>
      </div>

      <!-- Formula Policy Card -->
      <div style="background:var(--ct-surface-alt);border:1px solid var(--ct-navy-100);border-radius:8px;padding:14px 18px;margin-top:10px;">
        <div style="font-size:0.75rem;font-weight:700;text-transform:uppercase;letter-spacing:0.06em;color:var(--ct-teal-600);margin-bottom:4px;">Grounded Verification Formula</div>
        <div style="font-family:var(--ct-font-mono);font-size:0.95rem;font-weight:700;color:var(--ct-navy-950);">
          Expected Total = Quantity × Unit Price − Discount + Tax
        </div>
        <p style="font-size:0.78rem;color:var(--ct-navy-500);margin-top:4px;line-height:1.4;">
          Evaluated using Python <code>Decimal</code> with <code>ROUND_HALF_UP</code> rounding and tolerance ±${STATE.mathTolerance}.
          Discrepancies exceeding tolerance are flagged with exact source row/cell/page references.
        </p>
      </div>
    </div>

    <!-- Math KPI Grid -->
    <div class="grid-4" style="margin-bottom:20px;">
      <div class="kpi-card">
        <div class="kpi-top"><div class="kpi-label">Math Mismatches</div><span style="color:${mismatches.length>0?'var(--ct-risk-high-txt)':'var(--ct-navy-400)'};font-weight:700;">!</span></div>
        <div class="kpi-value" style="color:${mismatches.length>0?'var(--ct-risk-high-txt)':'var(--ct-navy-900)'};">${mismatches.length}</div>
        <div class="kpi-desc">Calculated total diverges from reported amount (e.g. INV-002 +25.00).</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-top"><div class="kpi-label">Missing Totals</div><span style="color:${missing.length>0?'var(--ct-gold-600)':'var(--ct-navy-400)'};font-weight:700;">?</span></div>
        <div class="kpi-value" style="color:${missing.length>0?'var(--ct-gold-600)':'var(--ct-navy-900)'};">${missing.length}</div>
        <div class="kpi-desc">Empty recorded total with verifiable calculated amount (e.g. INV-006).</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-top"><div class="kpi-label">Negative Quantities</div><span style="color:${negatives.length>0?'var(--ct-risk-high-txt)':'var(--ct-navy-400)'};font-weight:700;">-</span></div>
        <div class="kpi-value" style="color:${negatives.length>0?'var(--ct-risk-high-txt)':'var(--ct-navy-900)'};">${negatives.length}</div>
        <div class="kpi-desc">Negative units violate invoice policy rules (e.g. INV-005).</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-top"><div class="kpi-label">Invalid Numeric Input</div><span style="color:${invalids.length>0?'var(--ct-risk-high-txt)':'var(--ct-navy-400)'};font-weight:700;">#</span></div>
        <div class="kpi-value" style="color:${invalids.length>0?'var(--ct-risk-high-txt)':'var(--ct-navy-900)'};">${invalids.length}</div>
        <div class="kpi-desc">Non-numeric tokens in numerical price/quantity fields (e.g. INV-007).</div>
      </div>
    </div>

    <!-- Custom Mathematical & Business Rule Builder (Feature A) -->
    <div class="card" style="margin-bottom:20px;">
      <div class="card-header" style="flex-wrap:wrap;gap:10px;">
        <div>
          <div class="card-title">Custom Mathematical & Business Rule Builder</div>
          <div class="card-subtitle">Define, simulate, and enforce domain-specific formula invariants and numeric bounds</div>
        </div>
        <span class="badge" style="background:var(--ct-teal-100);color:var(--ct-teal-800);padding:3px 10px;border-radius:999px;font-size:0.72rem;font-weight:700;">
          ${(STATE.customRules || []).length} Active Custom Rules
        </span>
      </div>

      <!-- Quick Presets -->
      <div style="font-size:0.75rem;font-weight:700;color:var(--ct-navy-500);text-transform:uppercase;letter-spacing:0.05em;margin-bottom:6px;">Quick Presets:</div>
      <div class="rule-preset-container">
        <button class="rule-preset-chip" onclick="selectRulePreset('profit')">📈 Margin: profit = rev - cogs</button>
        <button class="rule-preset-chip" onclick="selectRulePreset('discount')">🏷️ Discount Cap: discount &le; subtotal * 0.30</button>
        <button class="rule-preset-chip" onclick="selectRulePreset('quantity')">📦 Non-Negative: quantity &ge; 0</button>
        <button class="rule-preset-chip" onclick="selectRulePreset('tax')">🏛️ Tax Invariant: tax = subtotal * 0.10</button>
      </div>

      <!-- Rule Form -->
      <div style="background:var(--ct-surface-alt);border:1px solid var(--ct-navy-100);border-radius:8px;padding:16px;">
        <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(180px, 1fr));gap:12px;margin-bottom:12px;">
          <div>
            <label style="font-size:0.74rem;font-weight:700;color:var(--ct-navy-700);display:block;margin-bottom:4px;">Rule Identifier</label>
            <input type="text" id="custom-rule-id" placeholder="e.g. profit_margin_rule" style="width:100%;padding:6px 10px;border:1px solid var(--ct-navy-200);border-radius:6px;font-size:0.8rem;background:var(--ct-surface-card);color:var(--ct-navy-900);">
          </div>
          <div>
            <label style="font-size:0.74rem;font-weight:700;color:var(--ct-navy-700);display:block;margin-bottom:4px;">Rule Type</label>
            <select id="custom-rule-type" style="width:100%;padding:6px 10px;border:1px solid var(--ct-navy-200);border-radius:6px;font-size:0.8rem;background:var(--ct-surface-card);color:var(--ct-navy-900);">
              <option value="formula">Formula (target = expr)</option>
              <option value="constraint">Constraint (e.g. col &ge; min)</option>
              <option value="sum">Sum Invariant</option>
              <option value="percentage">Percentage Check</option>
            </select>
          </div>
          <div>
            <label style="font-size:0.74rem;font-weight:700;color:var(--ct-navy-700);display:block;margin-bottom:4px;">Target Column</label>
            <input type="text" id="custom-rule-target" placeholder="e.g. profit, discount" style="width:100%;padding:6px 10px;border:1px solid var(--ct-navy-200);border-radius:6px;font-size:0.8rem;background:var(--ct-surface-card);color:var(--ct-navy-900);">
          </div>
          <div>
            <label style="font-size:0.74rem;font-weight:700;color:var(--ct-navy-700);display:block;margin-bottom:4px;">Mathematical Expression</label>
            <input type="text" id="custom-rule-expr" placeholder="e.g. rev - cogs" style="width:100%;padding:6px 10px;border:1px solid var(--ct-navy-200);border-radius:6px;font-size:0.8rem;background:var(--ct-surface-card);color:var(--ct-navy-900);">
          </div>
          <div>
            <label style="font-size:0.74rem;font-weight:700;color:var(--ct-navy-700);display:block;margin-bottom:4px;">Tolerance (&plusmn;)</label>
            <input type="number" id="custom-rule-tol" step="0.001" value="0.01" style="width:100%;padding:6px 10px;border:1px solid var(--ct-navy-200);border-radius:6px;font-size:0.8rem;background:var(--ct-surface-card);color:var(--ct-navy-900);">
          </div>
        </div>
        <div style="display:flex;justify-content:flex-end;gap:10px;">
          <button class="btn btn-primary btn-sm" onclick="submitCustomRule()">➕ Add & Enforce Rule</button>
        </div>
      </div>

      <!-- Active Rules List -->
      ${(STATE.customRules && STATE.customRules.length > 0) ? `
        <div style="margin-top:14px;">
          <div style="font-size:0.78rem;font-weight:700;color:var(--ct-navy-800);margin-bottom:6px;">Active Enforced Rules:</div>
          <div style="border:1px solid var(--ct-navy-100);border-radius:6px;overflow:hidden;">
            ${STATE.customRules.map(r => `
              <div class="rule-list-item">
                <div style="display:flex;align-items:center;gap:10px;">
                  <span class="badge" style="background:var(--ct-teal-100);color:var(--ct-teal-800);font-size:0.7rem;font-weight:700;padding:2px 8px;border-radius:999px;">${r.rule_type}</span>
                  <b style="font-size:0.85rem;color:var(--ct-navy-950);">${escapeHtml(r.rule_id)}</b>
                  <code style="font-size:0.78rem;color:var(--ct-navy-700);">${escapeHtml(r.target_column || '')} = ${escapeHtml(r.expression || '')}</code>
                  <span style="font-size:0.72rem;color:var(--ct-navy-500);">(tol: &plusmn;${r.tolerance})</span>
                </div>
                <button class="btn btn-secondary btn-sm" onclick="deleteCustomRule('${escapeHtml(r.rule_id)}')" style="color:var(--ct-risk-high-txt);padding:3px 10px;font-size:0.72rem;">Delete Rule</button>
              </div>
            `).join('')}
          </div>
        </div>
      ` : ''}
    </div>

    <!-- Mathematical Discrepancy Findings -->
    <div class="card">
      <div class="card-header">
        <div>
          <div class="card-title">Mathematical Discrepancy Ledger (${mf.length} Findings)</div>
          <div class="card-subtitle">Every calculation traceable to original source row, sheet, or page</div>
        </div>
      </div>

      ${mf.length === 0 ? '<p style="color:var(--ct-navy-500);padding:14px 0;">No mathematical or constraint errors detected in current dataset revision.</p>' : `
        <div class="table-responsive">
          <table class="data-table">
            <thead>
              <tr>
                <th>Invoice / ID</th>
                <th>Source Provenance</th>
                <th>Rule Class</th>
                <th>Observed</th>
                <th>Expected</th>
                <th>Deviation</th>
                <th>Calculation Steps</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              ${mf.map(f => {
                return `
                  <tr>
                    <td><b>${escapeHtml(f.invoice_id)}</b></td>
                    <td><code style="font-size:0.75rem;">${escapeHtml(f.source_ref)}</code></td>
                    <td><span class="badge" style="background:${f.severity==='High'?'var(--ct-risk-high-bg)':'var(--ct-risk-low-bg)'};color:${f.severity==='High'?'var(--ct-risk-high-txt)':'var(--ct-risk-low-txt)'};padding:2px 8px;border-radius:999px;font-size:0.7rem;font-weight:700;">${f.rule_id}</span></td>
                    <td style="color:${f.observed ? 'var(--ct-risk-high-txt)' : 'var(--ct-navy-400)'};font-family:var(--ct-font-mono);">${f.observed || '<i>null</i>'}</td>
                    <td style="color:var(--ct-teal-700);font-weight:700;font-family:var(--ct-font-mono);">${f.expected || '—'}</td>
                    <td style="color:${f.deviation ? 'var(--ct-risk-high-txt)' : 'var(--ct-navy-400)'};font-weight:700;font-family:var(--ct-font-mono);">${f.deviation ? (parseFloat(f.deviation) > 0 ? '+' + f.deviation : f.deviation) : '—'}</td>
                    <td style="font-size:0.78rem;font-family:var(--ct-font-mono);max-width:280px;">${escapeHtml(f.calculation_steps || f.message)}</td>
                    <td>
                      ${f.proposed_value ? `
                        <button class="btn btn-primary btn-sm" onclick="applyMathRepairDirectly('${f.invoice_id}', '${f.field}', '${f.row_idx}', '${f.proposed_value}')">
                          Approve ${f.proposed_value}
                        </button>
                      ` : '<span style="color:var(--ct-navy-400);font-size:0.75rem;">Manual Review</span>'}
                    </td>
                  </tr>
                `;
              }).join('')}
            </tbody>
          </table>
        </div>
      `}
    </div>
  `;
}

function renderRagAssistant() {
  const container = document.getElementById('view-rag-assistant');
  if (!STATE.dataset) return;

  const status = STATE.ragStatus || { status: 'loading', llm_available: false, indexed_passages: 0 };
  const isLlmOnline = status.llm_available;

  container.innerHTML = `
    <!-- Top Knowledge Status Banner -->
    <div class="card" style="margin-bottom:20px;">
      <div class="card-header" style="flex-wrap:wrap;gap:12px;">
        <div>
          <div class="card-title">AI Knowledge Assistant (Grounded RAG)</div>
          <div class="card-subtitle">Session-Isolated BM25 Lexical Retrieval & Grounded Natural Language Explanations</div>
        </div>
        <div style="display:flex;align-items:center;gap:8px;">
          <div class="pulse-dot" style="background:${isLlmOnline ? 'var(--ct-teal-500)' : 'var(--ct-gold-500)'};"></div>
          <span style="font-size:0.75rem;font-weight:700;color:var(--ct-navy-700);">
            ${isLlmOnline ? `LLM Active (${status.llm_model})` : 'Evidence Direct Mode (Ollama Offline)'}
          </span>
        </div>
      </div>

      <div style="background:var(--ct-surface-alt);border:1px solid var(--ct-navy-100);border-radius:8px;padding:12px 16px;margin-top:10px;font-size:0.8rem;color:var(--ct-navy-600);line-height:1.45;">
        <b>Auditable Retrieval Guarantee:</b> ClearTrace indexes current session rows, dataset schema, business rules, and mathematical findings with exact sheet/cell/row/page provenance.
        All answers strictly cite verified source IDs. <i>Calculations are never delegated to the LLM.</i>
      </div>
    </div>

    <!-- Search / Question Box -->
    <div class="card" style="margin-bottom:20px;">
      <div style="font-size:0.85rem;font-weight:700;color:var(--ct-navy-900);margin-bottom:8px;">Ask a Question about this Dataset</div>
      <div style="display:flex;gap:10px;margin-bottom:12px;">
        <input type="text" id="rag-input" placeholder="e.g. Which invoice total is incorrect? Why was INV-002 flagged?"
               style="flex:1;padding:10px 14px;border:1px solid var(--ct-navy-200);border-radius:8px;font-size:0.9rem;background:var(--ct-surface-card);color:var(--ct-navy-900);"
               onkeydown="if(event.key==='Enter') submitRagQuestion();">
        <button class="btn btn-primary" onclick="submitRagQuestion()" id="rag-submit-btn">Ask Assistant</button>
        <button class="btn btn-secondary" onclick="searchRagKeyword()">Search Chunks</button>
      </div>

      <!-- Quick Chips -->
      <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;">
        <span style="font-size:0.72rem;color:var(--ct-navy-500);font-weight:600;">Prompt Examples:</span>
        <button class="btn btn-secondary btn-sm" style="font-size:0.75rem;" onclick="setRagPrompt('Which invoice total is incorrect?')">Incorrect Invoices?</button>
        <button class="btn btn-secondary btn-sm" style="font-size:0.75rem;" onclick="setRagPrompt('Why was INV-002 flagged? Show calculation.')">Why INV-002?</button>
        <button class="btn btn-secondary btn-sm" style="font-size:0.75rem;" onclick="setRagPrompt('How is the invoice expected total calculated?')">Calculation Policy</button>
        <button class="btn btn-secondary btn-sm" style="font-size:0.75rem;" onclick="setRagPrompt('What is the difference for INV-002?')">INV-002 Discrepancy</button>
      </div>
    </div>

    <!-- Q&A Results & History -->
    <div id="rag-results-container">
      ${STATE.ragHistory.length === 0 ? `
        <div class="card" style="text-align:center;padding:40px 20px;color:var(--ct-navy-500);">
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" style="margin-bottom:10px;color:var(--ct-teal-500);"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
          <div style="font-weight:700;font-size:1rem;color:var(--ct-navy-800);">Ask a question or select a prompt above</div>
          <p style="font-size:0.82rem;margin-top:4px;">Retrieval searches indexed session records and returns grounded answers with authentic source citations.</p>
        </div>
      ` : STATE.ragHistory.map((item) => `
        <div class="card" style="margin-bottom:16px;">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:12px;">
            <div style="font-weight:700;font-size:0.95rem;color:var(--ct-navy-950);">Q: ${escapeHtml(item.question)}</div>
            <span style="font-size:0.7rem;font-family:var(--ct-font-mono);background:var(--ct-surface-alt);padding:3px 8px;border-radius:6px;color:var(--ct-navy-600);">${escapeHtml(item.provider)}</span>
          </div>
          <div style="font-size:0.88rem;color:var(--ct-navy-800);line-height:1.6;white-space:pre-wrap;background:var(--ct-surface-alt);padding:14px;border-radius:8px;border-left:3px solid var(--ct-teal-500);">${item.answer}</div>

          <!-- Citation References -->
          ${item.references && item.references.length > 0 ? `
            <div style="margin-top:12px;display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
              <span style="font-size:0.75rem;font-weight:700;color:var(--ct-navy-500);">CITED SOURCES:</span>
              ${item.references.map(r => `<span style="font-family:var(--ct-font-mono);font-size:0.72rem;background:var(--ct-teal-100);color:var(--ct-teal-700);padding:3px 8px;border-radius:4px;font-weight:600;">[Source: ${escapeHtml(r)}]</span>`).join('')}
            </div>
          ` : ''}

          <!-- Retrieved Evidence Collapsible -->
          ${item.evidence && item.evidence.length > 0 ? `
            <details style="margin-top:14px;">
              <summary style="font-size:0.75rem;font-weight:700;color:var(--ct-navy-600);cursor:pointer;">
                View ${item.evidence.length} Retrieved Evidence Chunks (BM25 Match)
              </summary>
              <div style="display:flex;flex-direction:column;gap:8px;margin-top:10px;">
                ${item.evidence.map(ev => `
                  <div style="background:var(--ct-surface-card);border:1px solid var(--ct-navy-100);border-radius:6px;padding:10px 14px;font-size:0.78rem;">
                    <div style="display:flex;justify-content:space-between;color:var(--ct-navy-500);margin-bottom:4px;font-size:0.72rem;">
                      <b>${escapeHtml(ev.title)}</b>
                      <span>BM25 Score: ${ev.score}</span>
                    </div>
                    <code style="font-size:0.72rem;color:var(--ct-teal-700);">${escapeHtml(ev.ref)}</code>
                    <p style="margin-top:4px;color:var(--ct-navy-700);">${escapeHtml(ev.text)}</p>
                  </div>
                `).join('')}
              </div>
            </details>
          ` : ''}
        </div>
      `).join('')}
    </div>
  `;
}

// ── Interactive Actions ──────────────────────────────────────────────────────

async function loadDemoDataset() {
  try {
    await api('/api/dataset/demo', { method: 'POST' });
    showToast('Loaded synthetic demonstration dataset.', 'success');
    await refreshAll();
  } catch (e) { /* Handled */ }
}

async function loadMathDemo(format) {
  try {
    showToast(`Loading invoice math demo in ${format.toUpperCase()}...`, 'info');
    const res = await api('/api/dataset/math-demo', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ format: format }),
    });
    showToast(`Loaded ${res.filename} (${res.math_issues_count} math findings).`, 'success');
    await refreshAll();
    switchModule('math-intelligence');
  } catch (e) { /* Handled */ }
}

async function updateMathTolerance() {
  const input = document.getElementById('math-tolerance-input');
  if (!input) return;
  const val = parseFloat(input.value) || 0.01;
  STATE.mathTolerance = val;
  try {
    const res = await api('/api/math/validate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tolerance: val }),
    });
    STATE.mathFindings = res.findings;
    showToast(`Recalculated with tolerance ±${val} (${res.total_math_issues} issues).`, 'success');
    renderMathIntelligence();
    updateHeader();
  } catch (e) { /* Handled */ }
}

async function applyMathRepairDirectly(invId, col, rowIdx, proposedVal) {
  const findingId = `finding-math-${invId}-${col}`;
  try {
    const res = await api('/api/repair/apply', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        finding_id: findingId,
        expected_revision: STATE.dataset.revision,
      }),
    });
    showToast(`Approved repair for ${invId}: updated ${col} to ${proposedVal}.`, 'success');
    await refreshAll();
    switchModule('math-intelligence');
  } catch (e) { /* Handled */ }
}

function setRagPrompt(promptText) {
  const inp = document.getElementById('rag-input');
  if (inp) {
    inp.value = promptText;
    submitRagQuestion();
  }
}

async function submitRagQuestion() {
  const inp = document.getElementById('rag-input');
  if (!inp || !inp.value.trim()) return;
  const question = inp.value.trim();
  const btn = document.getElementById('rag-submit-btn');
  if (btn) btn.disabled = true;

  try {
    const res = await api('/api/rag/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: question }),
    });
    STATE.ragHistory.unshift({
      question: question,
      answer: res.answer,
      references: res.references,
      provider: res.provider,
      evidence: res.evidence_matches,
    });
    inp.value = '';
    renderRagAssistant();
  } catch (e) {
    /* Handled */
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function searchRagKeyword() {
  const inp = document.getElementById('rag-input');
  if (!inp || !inp.value.trim()) return;
  const q = inp.value.trim();
  try {
    const res = await api('/api/rag/search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: q, limit: 5 }),
    });
    const summary = res.results.map(r => `• [${r.title}] (${r.ref}): ${r.text}`).join('\n\n');
    STATE.ragHistory.unshift({
      question: `BM25 Search: "${q}"`,
      answer: summary || 'No matches found.',
      references: res.results.map(r => r.ref),
      provider: 'bm25-retrieval-only',
      evidence: res.results,
    });
    renderRagAssistant();
  } catch (e) { /* Handled */ }
}

async function handleFileSelect(event) {
  const file = event.target.files[0];
  if (file) uploadFile(file);
}

async function uploadFile(file) {
  const formData = new FormData();
  formData.append('file', file);
  try {
    showToast(`Uploading and analyzing ${file.name}...`, 'info');
    await api('/api/dataset/upload', { method: 'POST', body: formData });
    showToast(`Successfully analyzed ${file.name}`, 'success');
    await refreshAll();
    switchModule('command-center');
  } catch (err) {
    // Errors and auth redirects handled inside api()
  }
}

async function applySingleRepair(findingId) {
  try {
    const res = await api('/api/repair/apply', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        finding_id: findingId,
        expected_revision: STATE.dataset.revision,
      }),
    });
    showToast(`Applied repair: ${res.detail}`, 'success');
    await refreshAll();
  } catch (e) { /* Handled */ }
}

async function batchApproveAll() {
  try {
    const findingIds = STATE.proposals.map(p => p.finding_id);
    const res = await api('/api/repair/batch-apply', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        finding_ids: findingIds,
        expected_revision: STATE.dataset.revision,
      }),
    });
    showToast(`Applied ${res.applied_events.length} repairs (${res.total_items_changed} items modified).`, 'success');
    await refreshAll();
  } catch (e) { /* Handled */ }
}

function rejectRepair(findingId) {
  STATE.proposals = STATE.proposals.filter(p => p.finding_id !== findingId);
  showToast('Repair proposal rejected. Working copy unchanged.', 'info');
  renderRepairStudio();
}

async function undoLastAction() {
  try {
    const res = await api('/api/audit/undo', { method: 'POST' });
    showToast(`Undid action: ${res.undone_event}`, 'info');
    await refreshAll();
  } catch (e) { /* Handled */ }
}

async function resetToBaseline() {
  if (!confirm('Are you sure you want to revert all changes back to the raw uploaded baseline?')) return;
  try {
    await api('/api/audit/reset', { method: 'POST' });
    showToast('Dataset reset to raw upload baseline.', 'info');
    await refreshAll();
  } catch (e) { /* Handled */ }
}

async function restoreSnapshot(targetRev) {
  if (!confirm(`Restore dataset working copy to Revision ${targetRev}?`)) return;
  try {
    await api('/api/timemachine/restore', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ target_revision: targetRev }),
    });
    showToast(`Restored to Revision ${targetRev}`, 'success');
    await refreshAll();
  } catch (e) { /* Handled */ }
}

function toggleTheme() {
  const current = document.documentElement.getAttribute('data-theme');
  const next = current === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  const btn = document.getElementById('theme-btn');
  if (btn) btn.textContent = next === 'dark' ? '☀️ Light' : '🌙 Dark';
  if (STATE.activeModule === 'settings') renderSettings();
}

function showToast(msg, type = 'info') {
  const toast = document.createElement('div');
  toast.style.cssText = `
    position: fixed; bottom: 28px; right: 28px; z-index: 9999;
    background: ${type === 'error' ? 'var(--ct-risk-high-txt)' : (type === 'success' ? 'var(--ct-teal-600)' : 'var(--ct-navy-950)')};
    color: #FFFFFF; padding: 12px 20px; border-radius: 8px; font-size: 0.84rem; font-weight: 600;
    box-shadow: 0 4px 18px rgba(0,0,0,0.22); max-width: 380px; line-height: 1.45; animation: fadeIn 0.2s ease;
  `;
  toast.textContent = msg;
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 3200);
}

function escapeHtml(str) {
  return String(str || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// ── Custom Rule Builder Handlers (Feature A) ─────────────────────────────────

function selectRulePreset(presetKey) {
  const presets = {
    profit: { id: 'profit_margin_check', type: 'formula', col: 'profit', expr: 'rev - cogs' },
    discount: { id: 'discount_limit_check', type: 'constraint', col: 'discount', expr: 'discount <= subtotal * 0.30' },
    quantity: { id: 'non_negative_qty', type: 'constraint', col: 'quantity', expr: 'quantity >= 0' },
    tax: { id: 'sales_tax_check', type: 'formula', col: 'tax', expr: 'subtotal * 0.10' }
  };
  const p = presets[presetKey];
  if (!p) return;
  const idEl = document.getElementById('custom-rule-id');
  const typeEl = document.getElementById('custom-rule-type');
  const colEl = document.getElementById('custom-rule-target');
  const exprEl = document.getElementById('custom-rule-expr');
  if (idEl) idEl.value = p.id;
  if (typeEl) typeEl.value = p.type;
  if (colEl) colEl.value = p.col;
  if (exprEl) exprEl.value = p.expr;
}

async function submitCustomRule() {
  const ruleIdEl = document.getElementById('custom-rule-id');
  const ruleTypeEl = document.getElementById('custom-rule-type');
  const targetColEl = document.getElementById('custom-rule-target');
  const expressionEl = document.getElementById('custom-rule-expr');
  const tolEl = document.getElementById('custom-rule-tol');

  const ruleId = ruleIdEl ? ruleIdEl.value.trim() : '';
  const ruleType = ruleTypeEl ? ruleTypeEl.value : 'formula';
  const targetCol = targetColEl ? targetColEl.value.trim() : '';
  const expression = expressionEl ? expressionEl.value.trim() : '';
  const tol = tolEl ? parseFloat(tolEl.value) || 0.01 : 0.01;

  if (!ruleId || !targetCol || !expression) {
    showToast('Please provide Rule ID, Target Column, and Mathematical Expression.', 'error');
    return;
  }

  try {
    const res = await api('/api/math/rules', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        rule_id: ruleId,
        rule_type: ruleType,
        target_column: targetCol,
        expression: expression,
        tolerance: tol,
        description: `Custom ${ruleType} rule enforcing ${targetCol} = ${expression}`,
      }),
    });
    showToast(`Rule '${ruleId}' enforced! (${res.total_math_issues} discrepancy findings detected)`, 'success');
    await refreshAll();
  } catch (err) {
    showToast('Failed to add custom rule: ' + err.message, 'error');
  }
}

async function deleteCustomRule(ruleId) {
  try {
    await api('/api/math/rules/' + encodeURIComponent(ruleId), { method: 'DELETE' });
    showToast(`Custom rule '${ruleId}' removed.`, 'info');
    await refreshAll();
  } catch (err) {
    showToast('Failed to delete custom rule: ' + err.message, 'error');
  }
}

// ── Before / After Quality Comparison (Feature C) ───────────────────────────

async function openComparisonModal() {
  const modal = document.getElementById('comparison-modal');
  const body = document.getElementById('comparison-modal-body');
  if (!modal || !body) return;

  modal.classList.add('active');
  body.innerHTML = `
    <div style="text-align:center;padding:40px;color:var(--ct-navy-500);">
      <div class="pulse-dot" style="margin:0 auto 12px;"></div>
      Calculating quality delta between Revision 1 baseline and Revision ${STATE.dataset ? STATE.dataset.revision : 1}...
    </div>
  `;

  try {
    const data = await api('/api/comparison/summary');
    STATE.comparisonSummary = data;
    renderComparisonModalContent(data);
  } catch (err) {
    body.innerHTML = `<div style="color:var(--ct-risk-high-txt);padding:20px;text-align:center;">Failed to compute comparison: ${escapeHtml(err.message)}</div>`;
  }
}

function closeComparisonModal() {
  const modal = document.getElementById('comparison-modal');
  if (modal) modal.classList.remove('active');
}

function renderComparisonModalContent(c) {
  const body = document.getElementById('comparison-modal-body');
  if (!body) return;

  const deltaColor = c.score_delta > 0 ? 'var(--ct-teal-600)' : (c.score_delta < 0 ? 'var(--ct-risk-high-txt)' : 'var(--ct-navy-600)');
  const deltaSign = c.score_delta > 0 ? '+' : '';

  body.innerHTML = `
    <div class="comparison-container">
      <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;padding-bottom:12px;border-bottom:1px solid var(--ct-navy-100);">
        <div>
          <b style="font-size:1.05rem;color:var(--ct-navy-950);">${escapeHtml(c.filename)}</b>
          <div style="font-size:0.75rem;color:var(--ct-navy-500);margin-top:2px;">
            Comparing Ingestion Baseline (Rev ${c.revision_baseline}) vs Working Copy (Rev ${c.revision_current})
          </div>
        </div>
        <span class="badge" style="background:var(--ct-teal-50);color:var(--ct-teal-700);border:1px solid var(--ct-teal-300);padding:4px 12px;font-size:0.75rem;font-weight:700;">
          ${c.total_repairs_applied} Repairs Applied
        </span>
      </div>

      <!-- KPI Side-by-Side Comparison Grid -->
      <div class="comparison-kpi-grid">
        <div class="comparison-kpi-col">
          <div style="font-size:0.72rem;text-transform:uppercase;font-weight:700;color:var(--ct-navy-500);letter-spacing:0.06em;">Baseline (Revision ${c.revision_baseline})</div>
          <div style="font-size:2.2rem;font-weight:800;color:var(--ct-navy-800);margin:8px 0 4px;">${c.score_baseline.toFixed(1)}</div>
          <div style="font-size:0.8rem;font-weight:700;color:var(--ct-navy-600);">Grade: ${c.grade_baseline}</div>
          <div style="font-size:0.75rem;color:var(--ct-navy-500);margin-top:8px;">${c.initial_issues_count} Initial Issues Detected</div>
        </div>

        <div class="comparison-delta-badge">
          <div style="font-size:1.9rem;font-weight:900;color:${deltaColor};">${deltaSign}${c.score_delta.toFixed(1)}%</div>
          <div style="font-size:0.72rem;font-weight:700;color:var(--ct-navy-500);text-transform:uppercase;letter-spacing:0.05em;margin-top:2px;">Net Quality Delta</div>
          <div style="font-size:0.72rem;color:var(--ct-teal-600);margin-top:4px;">${c.resolved_issues_count} Issues Resolved</div>
        </div>

        <div class="comparison-kpi-col">
          <div style="font-size:0.72rem;text-transform:uppercase;font-weight:700;color:var(--ct-teal-700);letter-spacing:0.06em;">Working Copy (Revision ${c.revision_current})</div>
          <div style="font-size:2.2rem;font-weight:800;color:var(--ct-teal-600);margin:8px 0 4px;">${c.score_current.toFixed(1)}</div>
          <div style="font-size:0.8rem;font-weight:700;color:var(--ct-teal-700);">Grade: ${c.grade_current}</div>
          <div style="font-size:0.75rem;color:var(--ct-navy-500);margin-top:8px;">${c.remaining_issues_count} Remaining Issues</div>
        </div>
      </div>

      <!-- Dedicated Mathematical Integrity Dimension (INV-002) -->
      ${(c.initial_math_issues_count > 0 || c.current_math_issues_count > 0 || c.resolved_math_issues_count > 0) ? `
        <div style="background:var(--ct-surface-alt);border:1px solid var(--ct-teal-200);border-radius:8px;padding:12px 14px;margin-top:10px;">
          <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">
            <div>
              <b style="font-size:0.82rem;color:var(--ct-teal-800);">Mathematical Integrity Dimension:</b>
              <span style="font-size:0.75rem;color:var(--ct-navy-600);margin-left:6px;">
                ${c.math_score_baseline.toFixed(1)}% → <b>${c.math_score_current.toFixed(1)}%</b>
                <span style="color:${c.math_score_delta >= 0 ? 'var(--ct-teal-600)' : 'var(--ct-risk-high-txt)'};font-weight:700;">
                  (${c.math_score_delta >= 0 ? '+' : ''}${c.math_score_delta.toFixed(1)}%)
                </span>
              </span>
            </div>
            <div style="font-size:0.75rem;color:var(--ct-navy-600);">
              <b>${c.resolved_math_issues_count}</b> Math Discrepanc${c.resolved_math_issues_count === 1 ? 'y' : 'ies'} Resolved · <b>${c.current_math_issues_count}</b> Remaining
            </div>
          </div>
          ${c.composite_score_delta !== undefined ? `
            <div style="font-size:0.72rem;color:var(--ct-navy-500);margin-top:4px;">
              Composite Quality Score (70% Schema + 30% Math): <b>${c.composite_score_baseline.toFixed(1)}% → ${c.composite_score_current.toFixed(1)}% (${c.composite_score_delta >= 0 ? '+' : ''}${c.composite_score_delta.toFixed(1)}%)</b>
            </div>
          ` : ''}
        </div>
      ` : ''}

      <!-- Applied Repairs Breakdown -->
      <div style="margin-top:10px;">
        <div style="font-size:0.8rem;font-weight:700;color:var(--ct-navy-800);margin-bottom:8px;">Applied Repair Mutations by Rule Class:</div>
        ${c.repairs_breakdown && c.repairs_breakdown.length > 0 ? `
          <div style="display:flex;gap:8px;flex-wrap:wrap;">
            ${c.repairs_breakdown.map(r => `
              <div style="background:var(--ct-surface-card);border:1px solid var(--ct-navy-200);border-radius:6px;padding:6px 12px;font-size:0.75rem;display:flex;align-items:center;gap:6px;">
                <code style="font-weight:700;color:var(--ct-teal-700);">${escapeHtml(r.rule_id)}</code>
                <span style="background:var(--ct-teal-100);color:var(--ct-teal-800);padding:1px 6px;border-radius:999px;font-weight:700;font-size:0.7rem;">${r.count}</span>
              </div>
            `).join('')}
          </div>
        ` : `
          <p style="font-size:0.8rem;color:var(--ct-navy-500);font-style:italic;">No repair mutations applied yet. Review and approve candidate fixes in Repair Studio to advance revisions.</p>
        `}
      </div>

      <!-- Action Note -->
      <div style="background:var(--ct-surface-alt);border:1px solid var(--ct-navy-100);border-radius:8px;padding:12px 14px;font-size:0.78rem;color:var(--ct-navy-600);display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px;">
        <span>Zero silent alterations. Revert any action at any time via <b>Undo</b> or <b>Time Machine</b>.</span>
        ${c.revision_current > 1 ? `
          <button class="btn btn-secondary btn-sm" onclick="closeComparisonModal(); undoLastAction();">Undo Last Fix</button>
        ` : ''}
      </div>
    </div>
  `;
}

// ── Executive Quality Report Generator (Feature D) ──────────────────────────

let currentReportFormat = 'markdown';
let rawReportMarkdown = '';
let rawReportJson = null;

async function openExecutiveReportModal() {
  const modal = document.getElementById('report-modal');
  const body = document.getElementById('report-modal-body');
  if (!modal || !body) return;

  modal.classList.add('active');
  body.innerHTML = `
    <div style="text-align:center;padding:40px;color:var(--ct-navy-500);">
      <div class="pulse-dot" style="margin:0 auto 12px;"></div>
      Compiling cryptographic executive report with SHA-256 seal...
    </div>
  `;

  try {
    const jsonRes = await api('/api/export/report?format=json');
    rawReportMarkdown = jsonRes.report_markdown || '';
    rawReportJson = jsonRes;
    currentReportFormat = 'markdown';
    const btnFmt = document.getElementById('btn-report-format');
    if (btnFmt) btnFmt.textContent = 'Switch to JSON';
    renderReportModalBody();
  } catch (err) {
    body.innerHTML = `<div style="color:var(--ct-risk-high-txt);padding:20px;text-align:center;">Failed to generate executive report: ${escapeHtml(err.message)}</div>`;
  }
}

function closeExecutiveReportModal() {
  const modal = document.getElementById('report-modal');
  if (modal) modal.classList.remove('active');
}

function toggleReportFormat() {
  currentReportFormat = currentReportFormat === 'markdown' ? 'json' : 'markdown';
  const btnFmt = document.getElementById('btn-report-format');
  if (btnFmt) btnFmt.textContent = currentReportFormat === 'markdown' ? 'Switch to JSON' : 'Switch to Markdown';
  renderReportModalBody();
}

function renderReportModalBody() {
  const body = document.getElementById('report-modal-body');
  if (!body) return;

  if (currentReportFormat === 'markdown') {
    body.innerHTML = `
      <div style="margin-bottom:12px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;">
        <span style="font-size:0.76rem;color:var(--ct-navy-500);">Format: <b>Markdown (.md)</b> · Certified by ClearTrace Cryptographic Data Passport</span>
        <button class="btn btn-secondary btn-sm" onclick="navigator.clipboard.writeText(rawReportMarkdown); showToast('Report Markdown copied!', 'success');">📋 Copy Markdown</button>
      </div>
      <div class="report-viewer-content">${escapeHtml(rawReportMarkdown)}</div>
    `;
  } else {
    const jsonStr = JSON.stringify(rawReportJson, null, 2);
    body.innerHTML = `
      <div style="margin-bottom:12px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;">
        <span style="font-size:0.76rem;color:var(--ct-navy-500);">Format: <b>JSON (.json)</b> · Machine-readable compliance ledger</span>
        <button class="btn btn-secondary btn-sm" onclick="navigator.clipboard.writeText(JSON.stringify(rawReportJson, null, 2)); showToast('Report JSON copied!', 'success');">📋 Copy JSON</button>
      </div>
      <div class="report-viewer-content">${escapeHtml(jsonStr)}</div>
    `;
  }
}

// ── Initialize App & Accessibility Listeners ─────────────────────────────────

window.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    closeComparisonModal();
    closeExecutiveReportModal();
    toggleMobileSheet(false);
  }
});

window.addEventListener('DOMContentLoaded', () => {
  refreshAll();
});
