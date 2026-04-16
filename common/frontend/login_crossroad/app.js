// ── CAS / WebSEAL junction path detection ────────────────────────────────────
// WebSEAL rewrites HTML src/href attributes to include the junction prefix
// (e.g. /common-static/app.js → /askpbai/common-static/app.js) and may set
// an IV_JCT cookie.  We detect the prefix by:
//   1. Checking our own <script> tag's resolved src  (most reliable)
//   2. Falling back to the IV_JCT cookie
// Then we monkey-patch window.fetch so every fetch('/api/…') is automatically
// rewritten to fetch('/askpbai/api/…').  When not behind WebSEAL, base = '' → no-op.
(function () {
    var base = '';

    // Method 1: detect from our own <script src> (WebSEAL always rewrites these)
    try {
        var scriptSrc = document.currentScript && document.currentScript.getAttribute('src');
        if (scriptSrc) {
            var marker = '/common-static/app.js';
            var idx = scriptSrc.indexOf(marker);
            if (idx > 0) base = scriptSrc.substring(0, idx);
        }
    } catch (_) {}

    // Method 2: IV_JCT cookie fallback
    if (!base) {
        var m = document.cookie.match(/(?:^|;\s*)IV_JCT=([^;]*)/);
        if (m) base = decodeURIComponent(m[1]).replace(/\/+$/, '');
    }

    window.__PBAI_BASE = base;
    console.log('[PBAI] base path detected:', JSON.stringify(base));

    if (base) {
        var _origFetch = window.fetch;
        window.fetch = function (input, init) {
            if (typeof input === 'string' && input.startsWith('/') && !input.startsWith(base + '/')) {
                input = base + input;
            }
            return _origFetch.call(this, input, init);
        };
    }
})();

/** Return an absolute path prefixed with the junction base (if any). */
function pbaiUrl(path) { return (window.__PBAI_BASE || '') + path; }

function postNavigate(path, target) {
    var form = document.createElement('form');
    form.method = 'POST';
    form.action = pbaiUrl(path);
    form.style.display = 'none';
    if (target) form.target = target;
    document.body.appendChild(form);
    form.submit();
}

/** True when the page is served through a CAS / WebSEAL junction. */
function isCasGateway() { return !!(window.__PBAI_BASE); }

/** Last auto-session error message (for diagnostics). */
var _casAutoError = '';

/**
 * When behind CAS, call the backend to create a session from the
 * headers that WebSEAL injects on every proxied request.  Returns true
 * if a session was successfully created, false otherwise.
 */
async function casAutoSession() {
    if (!isCasGateway()) return false;
    try {
        console.log('[PBAI] calling /api/cas-session...');
        var res = await fetch('/api/cas-session', { method: 'POST' });         // fetch is auto-prefixed
        if (!res.ok) {
            var body = {};
            try { body = await res.json(); } catch (_) {}
            _casAutoError = body.detail || ('HTTP ' + res.status);
            console.error('[PBAI] /api/cas-session failed:', res.status, _casAutoError);
            return false;
        }
        var data = await res.json();
        console.log('[PBAI] cas-session OK, user:', data.username, 'role:', data.role);
        saveSession(
            data.token, data.username, data.role,
            data.groups, data.access_to, data.is_auditor,
            data.cas_jwt || ''
        );
        return true;
    } catch (e) {
        _casAutoError = e.message || 'Network error';
        console.error('[PBAI] casAutoSession exception:', e);
        return false;
    }
}

// Modularisation threshold: split into api.js / state.js / ui.js when this file
// exceeds ~300 lines or starts managing multiple distinct screens/states.
function getToken()      { return localStorage.getItem('pb_token')     || ''; }
function getUsername()   { return localStorage.getItem('pb_username')  || ''; }
function getRole()       { return localStorage.getItem('pb_role')      || 'user'; }
function getGroups()     { return JSON.parse(localStorage.getItem('pb_groups')    || '[]'); }
function getAccessTo()   { return JSON.parse(localStorage.getItem('pb_access_to') || '[]'); }
function getIsAuditor()  { return localStorage.getItem('pb_is_auditor') === 'true'; }
function getCasJwt()     { return localStorage.getItem('pb_cas_jwt')   || ''; }

function saveSession(token, username, role, groups, accessTo, isAuditor, casJwt) {
    localStorage.setItem('pb_token',      token);
    localStorage.setItem('pb_username',   username);
    localStorage.setItem('pb_role',       role || 'user');
    localStorage.setItem('pb_groups',     JSON.stringify(groups || []));
    localStorage.setItem('pb_access_to',  JSON.stringify(accessTo || []));
    localStorage.setItem('pb_is_auditor', isAuditor ? 'true' : 'false');
    if (casJwt) localStorage.setItem('pb_cas_jwt', casJwt);
}

function clearSession() {
    localStorage.removeItem('pb_token');
    localStorage.removeItem('pb_username');
    localStorage.removeItem('pb_role');
    localStorage.removeItem('pb_groups');
    localStorage.removeItem('pb_access_to');
    localStorage.removeItem('pb_is_auditor');
    localStorage.removeItem('pb_cas_jwt');
}

function authHeaders(extra) {
    const token = getToken();
    const headers = Object.assign({ 'Authorization': 'Bearer ' + token }, extra || {});
    const casJwt = getCasJwt();
    if (casJwt) headers['iv-jwt'] = casJwt;
    // WebSEAL strips Authorization; send token via X-PBAI-Token which passes through
    if (isCasGateway()) headers['X-PBAI-Token'] = token;
    return headers;
}

function ensureToastContainer() {
    var existing = document.querySelector('.toast-container');
    if (existing) return existing;
    var container = document.createElement('div');
    container.className = 'toast-container';
    container.setAttribute('aria-live', 'polite');
    container.setAttribute('aria-atomic', 'false');
    document.body.appendChild(container);
    return container;
}

function showToast(message, type, duration) {
    var tone = type || 'info';
    var timeout = duration || 4000;
    var container = ensureToastContainer();
    var toast = document.createElement('div');
    toast.className = 'toast toast--' + tone;
    toast.setAttribute('role', 'alert');
    toast.textContent = String(message || '');
    container.appendChild(toast);
    window.setTimeout(function() {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(8px)';
        window.setTimeout(function() {
            toast.remove();
        }, 200);
    }, timeout);
    return toast;
}

// Active auth mode — set by initLoginPage() after fetching /api/auth-mode.
let _authMode = 'legacy';

function loginOnEnter(e) {
    if (e.key === 'Enter') doLogin();
}

function _renderLegacyForm() {
    return `
        <label for="login-username">Staff ID</label>
        <input type="text" id="login-username" class="input" placeholder="Staff ID"
               autocomplete="username" onkeydown="loginOnEnter(event)">

        <label for="login-password">Password</label>
        <input type="password" id="login-password" class="input" placeholder="Password"
               autocomplete="current-password" onkeydown="loginOnEnter(event)">

        <div id="login-error" class="login-error" role="alert" aria-live="polite"></div>
        <button id="login-submit" class="btn btn--primary btn--block btn--lg" onclick="doLogin()">Sign In</button>
    `;
}

function _renderCasForm() {
    return `
        <label for="login-token">JWT Token</label>
        <textarea id="login-token" class="input" rows="4" placeholder="Paste your JWT token here"
                  onkeydown="loginOnEnter(event)" style="resize:vertical;font-family:monospace;font-size:0.8em;"></textarea>

        <div id="login-error" class="login-error" role="alert" aria-live="polite"></div>
        <button id="login-submit" class="btn btn--primary btn--block btn--lg" onclick="doLogin()">Sign In</button>
    `;
}

async function initLoginPage() {
    const formEl    = document.getElementById('login-form');
    const subtitleEl = document.getElementById('login-subtitle');
    if (!formEl) return;

    try {
        const res  = await fetch('/api/auth-mode', { method: 'POST' });
        const data = res.ok ? await res.json() : { mode: 'legacy' };
        _authMode  = data.mode || 'legacy';
    } catch (_) {
        _authMode = 'legacy';
    }

    if (_authMode === 'cas') {
        if (subtitleEl) subtitleEl.textContent = 'Sign in with your CAS token';
        formEl.innerHTML = _renderCasForm();
    } else {
        formEl.innerHTML = _renderLegacyForm();
    }
}

async function doLogin() {
    const errEl = document.getElementById('login-error');
    const btn   = document.getElementById('login-submit');

    if (errEl) { errEl.textContent = ''; errEl.classList.remove('visible'); }

    let body;
    if (_authMode === 'cas') {
        const token = (document.getElementById('login-token')?.value || '').trim();
        if (!token) {
            if (errEl) { errEl.textContent = 'Please paste your JWT token.'; errEl.classList.add('visible'); }
            return;
        }
        body = { token };
    } else {
        const username = (document.getElementById('login-username')?.value || '').trim();
        const password =  document.getElementById('login-password')?.value || '';
        if (!username || !password) {
            if (errEl) { errEl.textContent = 'Please enter your staff ID and password.'; errEl.classList.add('visible'); }
            return;
        }
        body = { username, password };
    }

    if (btn) { btn.disabled = true; btn.textContent = 'Signing in\u2026'; }

    try {
        const res  = await fetch('/login', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify(body),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Login failed');

        const rawCasJwt = _authMode === 'cas' ? (body.token || '') : '';
        saveSession(data.token, data.username, data.role, data.groups, data.access_to, data.is_auditor, rawCasJwt);

        if (document.getElementById('login-password')) document.getElementById('login-password').value = '';
        postNavigate('/crossroad');
    } catch (e) {
        if (errEl) { errEl.textContent = e.message; errEl.classList.add('visible'); }
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = 'Sign In'; }
    }
}

async function doLogout() {
    try {
        await fetch('/logout', { method: 'POST', headers: authHeaders() });
    } catch (_) {  }
    clearSession();
    postNavigate('/');
}

function escapeHtml(t) {
    return String(t)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;')
        .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function renderHelpers(helpers) {
    const grid = document.getElementById('helper-grid');
    if (!grid) return;

    if (!helpers || helpers.length === 0) {
        grid.innerHTML = '<div class="helper-empty">No helpers available for your account.</div>';
        return;
    }

    grid.innerHTML = helpers.map(h => {
        if (h.implemented) {
            return `<button class="helper-card" type="button" onclick="postNavigate('${escapeHtml(h.url)}')">
                        <div class="helper-card-name">${escapeHtml(h.name)}</div>
                        <div class="helper-card-desc">${escapeHtml(h.description)}</div>
                    </button>`;
        }
        return `<div class="helper-card helper-card--soon">
                    <div class="helper-card-name">${escapeHtml(h.name)}</div>
                    <div class="helper-card-desc">${escapeHtml(h.description)}</div>
                    <span class="coming-soon-badge">Coming Soon</span>
                </div>`;
    }).join('');
}

async function initCrossroad() {
    // When behind CAS, always refresh session from WebSEAL headers (detects user switches)
    if (isCasGateway()) {
        if (!(await casAutoSession())) {
            var grid = document.getElementById('helper-grid');
            if (grid) {
                grid.setAttribute('aria-busy', 'false');
                grid.innerHTML = '<div class="helper-empty" style="color:#c00">' +
                    'CAS auto-login failed: ' + escapeHtml(_casAutoError) +
                    '<br><br>Open browser DevTools \u2192 Console tab for details.' +
                    '<br>Run a POST request to ' + escapeHtml(pbaiUrl('/api/debug-headers')) + ' to inspect the WebSEAL headers.' +
                    '</div>';
            }
            return;
        }
    }
    const token    = getToken();
    const username = getUsername();

    if (!token || !username) {
        postNavigate('/');
        return;
    }

    const welcomeEl = document.getElementById('welcome-text');
    if (welcomeEl) welcomeEl.textContent = username.toUpperCase();

    try {
        const res = await fetch('/api/helpers', { method: 'POST', headers: authHeaders() });
        if (res.status === 401) { clearSession(); postNavigate('/'); return; }
        if (!res.ok) throw new Error('HTTP ' + res.status);
        renderHelpers(await res.json());
    } catch (e) {
        const grid = document.getElementById('helper-grid');
        if (grid) grid.innerHTML = '<div class="helper-empty">Failed to load helpers: ' + escapeHtml(e.message) + '</div>';
    } finally {
        const grid = document.getElementById('helper-grid');
        if (grid) grid.setAttribute('aria-busy', 'false');
    }

    if (getGroups().includes('master')) {
        const masterSection = document.getElementById('master-section');
        if (masterSection) masterSection.style.display = '';
    }

}

(async function init() {
    if (document.getElementById('helper-grid')) {
        initCrossroad();
    } else if (document.getElementById('login-form')) {
        // When behind CAS, auto-create a session and skip the login form entirely
        if (isCasGateway()) {
            if (await casAutoSession()) { postNavigate('/crossroad'); return; }
            var formEl = document.getElementById('login-form');
            if (formEl) {
                formEl.innerHTML = '<div style="color:#c00;padding:1rem;text-align:left;font-size:0.9em">' +
                    '<b>CAS auto-login failed</b><br>' + escapeHtml(_casAutoError) +
                    '<br><br>Open browser DevTools \u2192 Console tab for details.' +
                    '<br><br>Run a POST request to ' + escapeHtml(pbaiUrl('/api/debug-headers')) + ' to inspect the WebSEAL headers sent to the backend.' +
                    '</div>';
            }
            return;
        }
        const token    = getToken();
        const username = getUsername();
        if (token && username) {
            fetch('/api/helpers', { method: 'POST', headers: authHeaders() })
                .then(r => { if (r.ok) postNavigate('/crossroad'); })
                .catch(() => {});
        }
        initLoginPage();
    }
})();
