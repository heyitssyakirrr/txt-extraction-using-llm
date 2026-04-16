// Access Control page logic
// Depends on /common-static/app.js for getToken, getUsername, getGroups, authHeaders, doLogout, escapeHtml, clearSession, showToast

function escapeJsString(value) {
    return String(value).replace(/\\/g, '\\\\').replace(/'/g, "\\'");
}

function loadingMarkup(message) {
    return '<div class="loading-state"><span class="spinner" aria-hidden="true"></span><span>'
        + escapeHtml(message || 'Loading...')
        + '</span></div>';
}

function setListLoading(containerId, message) {
    var container = document.getElementById(containerId);
    if (!container) return null;
    container.innerHTML = loadingMarkup(message);
    container.setAttribute('aria-busy', 'true');
    return container;
}

function setListError(container, message) {
    if (!container) return;
    container.innerHTML = '<div class="ac-error" role="alert" aria-live="polite">'
        + escapeHtml(message)
        + '</div>';
    container.setAttribute('aria-busy', 'false');
}

function setListIdle(container) {
    if (container) container.setAttribute('aria-busy', 'false');
}

(async function guard() {
    // When behind CAS, auto-create session from WebSEAL headers if needed
    if (isCasGateway() && (!getToken() || !getUsername())) { await casAutoSession(); }
    if (!getToken() || !getUsername()) { postNavigate('/'); return; }
    if (!getGroups().includes('master')) { postNavigate('/crossroad'); return; }
    document.getElementById('welcome-text').textContent = getUsername().toUpperCase();
    initAccessControl();
})();

async function acFetch(url, opts) {
    var options = opts || {};
    var headers = Object.assign({}, authHeaders(), options.headers || {});
    var res = await fetch(url, {
        method: options.method || 'GET',
        headers: headers,
        body: options.body || undefined,
    });
    if (res.status === 401) { clearSession(); postNavigate('/'); return null; }
    if (res.status === 404) return { _notAvailable: true };
    if (!res.ok) {
        var data = await res.json().catch(function() { return {}; });
        throw new Error(data.detail || 'HTTP ' + res.status);
    }
    return res.json();
}

async function initAccessControl() {
    await Promise.all([loadGroups(), loadMasterUsers()]);
}

async function loadGroups() {
    var container = setListLoading('groups-list', 'Loading...');
    try {
        var data = await acFetch('/admin/groups', { method: 'POST' });
        if (!container) return;
        if (!data || data._notAvailable) {
            container.innerHTML = '<div class="ac-empty">Not available in current access mode.</div>';
            document.getElementById('btn-reload').style.display = 'none';
            document.getElementById('btn-add-group').style.display = 'none';
            return;
        }
        var keys = Object.keys(data);
        if (keys.length === 0) {
            container.innerHTML = '<div class="ac-empty">No groups configured.</div>';
            return;
        }
        var rows = keys.map(function(cn) {
            var cfg = data[cn];
            var cnSafe = escapeJsString(cn);
            var helpersSafe = escapeJsString((cfg.helpers || []).join(', '));
            var accessToSafe = escapeJsString((cfg.access_to || []).join(', '));
            var isAdmin = cfg.is_admin ? 'true' : 'false';
            var isAuditor = cfg.is_auditor ? 'true' : 'false';
            return '<tr>' +
                '<td>' + escapeHtml(cn) + '</td>' +
                '<td>' + escapeHtml((cfg.helpers || []).join(', ')) + '</td>' +
                '<td>' + escapeHtml((cfg.access_to || []).join(', ')) + '</td>' +
                '<td>' + (cfg.is_admin ? 'Yes' : 'No') + '</td>' +
                '<td>' + (cfg.is_auditor ? 'Yes' : 'No') + '</td>' +
                '<td class="ac-td-action">' +
                '<button class="btn btn--primary btn--sm" style="margin-right:0.25rem" onclick="editGroup(\'' + cnSafe + '\',\'' + helpersSafe + '\',\'' + accessToSafe + '\',' + isAdmin + ',' + isAuditor + ')">Edit</button>' +
                '<button class="btn btn--danger btn--sm" onclick="deleteGroup(\'' + cnSafe + '\')">Delete</button>' +
                '</td>' +
                '</tr>';
        }).join('');
        container.innerHTML = '<table class="table ac-table">' +
            '<thead><tr><th>Group CN</th><th>Helpers</th><th>Access To</th><th>Admin</th><th>Auditor</th><th></th></tr></thead>' +
            '<tbody>' + rows + '</tbody>' +
            '</table>';
    } catch (e) {
        setListError(container, 'Failed to load: ' + e.message);
    } finally {
        setListIdle(container);
    }
}

async function addGroup() {
    var cn = (document.getElementById('new-group-cn')?.value || '').trim();
    var helpersRaw = document.getElementById('new-group-helpers')?.value || '';
    var helpers = helpersRaw.split(',').map(function(h) { return h.trim(); }).filter(Boolean);
    var accessToRaw = document.getElementById('new-group-access-to')?.value || '';
    var accessTo = accessToRaw.split(',').map(function(g) { return g.trim(); }).filter(Boolean);
    var isAdmin = document.getElementById('new-group-admin')?.checked || false;
    var isAuditor = document.getElementById('new-group-auditor')?.checked || false;
    if (!cn) { showToast('Group CN is required.', 'error'); return; }
    try {
        var result = await acFetch('/admin/groups', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ cn: cn, helpers: helpers, access_to: accessTo, is_admin: isAdmin, is_auditor: isAuditor }),
        });
        if (result && !result._notAvailable) {
            document.getElementById('new-group-cn').value = '';
            document.getElementById('new-group-helpers').value = '';
            document.getElementById('new-group-access-to').value = '';
            document.getElementById('new-group-admin').checked = false;
            document.getElementById('new-group-auditor').checked = false;
            showToast('Group \'' + cn + '\' added.', 'success');
            await loadGroups();
        }
    } catch (e) {
        showToast('Add failed: ' + e.message, 'error');
    }
}

async function editGroup(cn, currentHelpers, currentAccessTo, currentIsAdmin, currentIsAuditor) {
    var newHelpers = window.prompt('Helpers (comma-separated):', currentHelpers);
    if (newHelpers === null) return;
    var helpers = newHelpers.split(',').map(function(h) { return h.trim(); }).filter(Boolean);
    var newAccessTo = window.prompt('Access To (comma-separated):', currentAccessTo);
    if (newAccessTo === null) return;
    var accessTo = newAccessTo.split(',').map(function(g) { return g.trim(); }).filter(Boolean);
    var isAdmin = window.confirm('Set as admin group? (OK = Yes, Cancel = No)\nCurrent: ' + (currentIsAdmin ? 'Yes' : 'No'));
    var isAuditor = window.confirm('Set as auditor group? (OK = Yes, Cancel = No)\nCurrent: ' + (currentIsAuditor ? 'Yes' : 'No'));
    try {
        var result = await acFetch('/admin/groups/' + encodeURIComponent(cn), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ helpers: helpers, access_to: accessTo, is_admin: isAdmin, is_auditor: isAuditor }),
        });
        if (result && !result._notAvailable) {
            showToast('Group \'' + cn + '\' updated.', 'success');
            await loadGroups();
        }
    } catch (e) {
        showToast('Update failed: ' + e.message, 'error');
    }
}

async function deleteGroup(cn) {
    if (!window.confirm('Delete group \'' + cn + '\'?')) return;
    try {
        var result = await acFetch('/admin/groups/' + encodeURIComponent(cn) + '/delete', { method: 'POST' });
        if (result && !result._notAvailable) {
            showToast('Group \'' + cn + '\' deleted.', 'success');
            await loadGroups();
        }
    } catch (e) {
        showToast('Delete failed: ' + e.message, 'error');
    }
}

async function loadMasterUsers() {
    var container = setListLoading('master-users-list', 'Loading...');
    try {
        var data = await acFetch('/admin/master-users', { method: 'POST' });
        if (!container) return;
        if (!data || data._notAvailable) {
            container.innerHTML = '<div class="ac-empty">Not available.</div>';
            return;
        }
        if (data.length === 0) {
            container.innerHTML = '<div class="ac-empty">No master user overrides.</div>';
            return;
        }
        var rows = data.map(function(username) {
            var raw = String(username || '');
            return '<tr>' +
                '<td>' + escapeHtml(raw) + '</td>' +
                '<td class="ac-td-action"><button class="btn btn--danger btn--sm" onclick="removeMasterUser(\'' + escapeJsString(raw) + '\')">Remove</button></td>' +
                '</tr>';
        }).join('');
        container.innerHTML = '<table class="table ac-table">' +
            '<thead><tr><th>Username</th><th></th></tr></thead>' +
            '<tbody>' + rows + '</tbody>' +
            '</table>';
    } catch (e) {
        setListError(container, 'Failed to load: ' + e.message);
    } finally {
        setListIdle(container);
    }
}

async function removeMasterUser(username) {
    try {
        var result = await acFetch('/admin/master-users/' + encodeURIComponent(username) + '/delete', { method: 'POST' });
        if (result && !result._notAvailable) {
            showToast('Removed master user ' + username + '.', 'success');
            await loadMasterUsers();
        }
    } catch (e) {
        showToast('Remove failed: ' + e.message, 'error');
    }
}

document.getElementById('btn-add-master')?.addEventListener('click', async function() {
    var input = document.getElementById('master-user-input');
    var username = (input.value || '').trim();
    if (!username) return;
    try {
        var result = await acFetch('/admin/master-users', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username: username }),
        });
        if (result && !result._notAvailable) {
            input.value = '';
            showToast('Added master user ' + username + '.', 'success');
            await loadMasterUsers();
        }
    } catch (e) {
        showToast('Add failed: ' + e.message, 'error');
    }
});

document.getElementById('master-user-input')?.addEventListener('keydown', function(e) {
    if (e.key === 'Enter') document.getElementById('btn-add-master')?.click();
});

document.getElementById('btn-add-group')?.addEventListener('click', addGroup);

document.getElementById('new-group-cn')?.addEventListener('keydown', function(e) {
    if (e.key === 'Enter') addGroup();
});

document.getElementById('btn-reload')?.addEventListener('click', async function() {
    var btn = document.getElementById('btn-reload');
    btn.disabled = true;
    btn.textContent = 'Reloading...';
    try {
        var data = await acFetch('/admin/groups/reload', { method: 'POST' });
        if (data && !data._notAvailable) {
            await loadGroups();
            showToast('Reloaded group access settings.', 'success');
        }
    } catch (e) {
        showToast('Reload failed: ' + e.message, 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = 'Reload';
    }
});
