/* ═══ AstroDash — Main Application JavaScript ═══ */

// ─── Channel Integration Helpers (LRGBSHO order) ───
const CH_COLORS = {
    l: '#d4d4d4', r: '#e53e3e', g: '#38a169', b: '#3b82f6',
    sii: '#ffa8a8', ha: '#a9e4b5', oiii: '#a5d8ff'
};
const CH_LABELS = { l:'L', r:'R', g:'G', b:'B', sii:'SII', ha:'Hα', oiii:'OIII' };
const CH_ORDER = ['l','r','g','b','sii','ha','oiii'];
function channelCell(minutes, color) {
    if (!minutes) return '<td style="color:var(--text-secondary)">—</td>';
    const hrs = (minutes / 60).toFixed(1);
    return `<td><span style="display:inline-block;background:${color}22;color:${color};padding:0.1rem 0.35rem;border-radius:4px;font-size:0.8rem;font-weight:600">${hrs}h</span></td>`;
}
function channelBadge(label, hours, color) {
    if (!hours) return '';
    return `<span style="display:inline-block;background:${color}22;color:${color};padding:0.1rem 0.4rem;border-radius:4px;margin:0.1rem;font-size:0.78rem;font-weight:600">${label} ${hours}h</span>`;
}
function moonPhaseIcon(pct) {
    if (pct == null || pct === '') return '';
    const p = parseFloat(pct);
    // Map illumination % to 1/8th moon phases (Unicode symbols)
    // These assume northern hemisphere waxing cycle for icon selection
    if (p <= 3) return '🌑';
    if (p <= 17) return '🌒';
    if (p <= 33) return '🌓';
    if (p <= 67) return '🌔';
    if (p <= 83) return '🌕';
    if (p <= 92) return '🌖';
    if (p <= 97) return '🌗';
    return '🌕';
}
function sessionChannelStack(s) {
    const chData = CH_ORDER.map(ch => ({
        key: ch, label: CH_LABELS[ch], color: CH_COLORS[ch],
        min: s['integration_' + ch + '_min'] || 0,
    }));
    const active = chData.filter(c => c.min > 0);
    if (!active.length) {
        // Show all dashes if no channel data
        return '<div style="font-size:0.78rem;color:var(--text-secondary);line-height:1.5">' +
            chData.map(c => `<span style="color:${c.color};font-weight:600">${c.label}</span> —`).join('<br>') + '</div>';
    }
    return '<div style="line-height:1.5">' + chData.map(c => {
        const hrs = c.min > 0 ? (c.min / 60).toFixed(1) + 'h' : '—';
        const style = c.min > 0
            ? `display:inline-block;background:${c.color}22;color:${c.color};padding:0.05rem 0.3rem;border-radius:4px;font-size:0.78rem;font-weight:600`
            : `font-size:0.78rem;color:var(--text-secondary)`;
        return `<div><span style="color:${c.color};font-weight:600;font-size:0.75rem;display:inline-block;width:2rem">${c.label}</span><span style="${style}">${hrs}</span></div>`;
    }).join('') + '</div>';
}
function escAttr(s) { return (s||'').replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/'/g,'&#39;').replace(/</g,'&lt;'); }
function colorizeBandpass(text) {
    if (!text) return '';
    // Colorize channel keywords with SHO Hubble Palette colors
    return text
        .replace(/\bSII\b/gi, `<span style="color:${CH_COLORS.sii};font-weight:600">SII</span>`)
        .replace(/\bS-?II\b/gi, `<span style="color:${CH_COLORS.sii};font-weight:600">SII</span>`)
        .replace(/\bSulfur\b/gi, `<span style="color:${CH_COLORS.sii};font-weight:600">Sulfur</span>`)
        .replace(/\bH[aα]\b/g, `<span style="color:${CH_COLORS.ha};font-weight:600">Hα</span>`)
        .replace(/\bHα\b/g, `<span style="color:${CH_COLORS.ha};font-weight:600">Hα</span>`)
        .replace(/\bH-?alpha\b/gi, `<span style="color:${CH_COLORS.ha};font-weight:600">Hα</span>`)
        .replace(/\bHydrogen\b/gi, `<span style="color:${CH_COLORS.ha};font-weight:600">Hydrogen</span>`)
        .replace(/\bOIII\b/gi, `<span style="color:${CH_COLORS.oiii};font-weight:600">OIII</span>`)
        .replace(/\bO-?III\b/gi, `<span style="color:${CH_COLORS.oiii};font-weight:600">OIII</span>`)
        .replace(/\bOxygen\b/gi, `<span style="color:${CH_COLORS.oiii};font-weight:600">Oxygen</span>`)
        .replace(/\bH[bβ]\b/g, `<span style="color:${CH_COLORS.oiii};font-weight:600">Hβ</span>`)
        .replace(/\bHβ\b/g, `<span style="color:${CH_COLORS.oiii};font-weight:600">Hβ</span>`);
}

// ─── Tab Navigation ───
function showTab(name) {
    document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.nav-btn').forEach(el => el.classList.remove('active'));
    const tab = document.getElementById('tab-' + name);
    if (tab) tab.classList.add('active');
    const btn = document.querySelector(`[data-tab="${name}"]`);
    if (btn) btn.classList.add('active');
    if (name === 'targets') loadTargets();
    if (name === 'projects') loadProjects();
    if (name === 'sessions') loadSessions();
    if (name === 'equipment') loadMyEquipment();
    if (name === 'settings') loadSettings();
}

// ─── Theme Toggle ───
function toggleTheme() {
    const html = document.documentElement;
    const next = html.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    html.setAttribute('data-theme', next);
    localStorage.setItem('theme', next);
    document.querySelector('.theme-toggle').textContent = next === 'dark' ? '☀️' : '🌙';
}
(function() {
    const saved = localStorage.getItem('theme') || 'light';
    document.documentElement.setAttribute('data-theme', saved);
    const btn = document.querySelector('.theme-toggle');
    if (btn) btn.textContent = saved === 'dark' ? '☀️' : '🌙';
})();

// ─── Dashboard ───
async function loadDashboard() {
    const apiKeyPrompt = 'Add your <a href="#" onclick="showTab(\'settings\'); return false;" style="color:var(--accent);text-decoration:underline">Astrospheric API key in Settings</a> to see detailed forecast data.';
    try {
        const resp = await fetch('/api/forecast');
        const data = await resp.json();
        if (data.error && !data.twilight) {
            // Hard error — no location etc.
            document.getElementById('verdict-text').textContent = 'No Data';
            document.getElementById('verdict-label').textContent = data.error;
        } else if (data.no_api_key) {
            // No API key — still render twilight/imaging window/moon
            renderPartialForecast(data, apiKeyPrompt);
        } else if (data.error) {
            // Has API key but no cache yet — render what we can
            renderPartialForecast(data, data.error);
        } else {
            renderForecast(data);
        }
    } catch (e) {
        console.error('Forecast load error:', e);
        document.getElementById('verdict-text').textContent = 'Error';
        document.getElementById('verdict-label').textContent = 'Failed to load forecast. Check settings.';
    }
    try {
        const resp = await fetch('/api/tonight/targets');
        const data = await resp.json();
        if (data.targets) renderTopTargets(data.targets.slice(0, 8), data.moon);
    } catch (e) {
        document.getElementById('top-targets').textContent = 'Unable to load targets. Check location in settings.';
    }
    try {
        const resp = await fetch('/api/forecast/tomorrow');
        const data = await resp.json();
        if (data.error && !data.imaging_window_start && data.error !== 'no_api_key') {
            // Hard error
        } else if (data.no_api_key) {
            document.getElementById('tomorrow-section').style.display = '';
            document.getElementById('tomorrow-verdict-text').textContent = '—';
            document.getElementById('tomorrow-score').textContent = '';
            document.getElementById('tomorrow-window').textContent = `${formatHour(data.imaging_window_start)} → ${formatHour(data.imaging_window_end)}`;
            document.getElementById('tomorrow-hours').textContent = `(${data.num_hours || '?'} hours)`;
            document.getElementById('tomorrow-worst').textContent = '';
            document.getElementById('tomorrow-body').innerHTML = `<tr><td colspan="8" style="text-align:center;padding:1.5rem;color:var(--text-secondary)">${apiKeyPrompt}</td></tr>`;
        } else if (data.hours && data.hours.length > 0) {
            renderTomorrowForecast(data);
        } else if (data.error) {
            document.getElementById('tomorrow-section').style.display = '';
            document.getElementById('tomorrow-verdict-text').textContent = 'N/A';
            document.getElementById('tomorrow-score').textContent = data.error;
            if (data.imaging_window_start != null) {
                document.getElementById('tomorrow-window').textContent = `${formatHour(data.imaging_window_start)} → ${formatHour(data.imaging_window_end)}`;
            }
        }
    } catch (e) {
        console.error('Tomorrow forecast error:', e);
    }
}

function renderPartialForecast(data, tableMessage) {
    // Render twilight and imaging window (always available)
    const tw = data.twilight || {};
    if (tw.sunset) {
        document.getElementById('twilight-details').style.display = 'block';
        document.getElementById('tw-sunset').textContent = tw.sunset || '—';
        document.getElementById('tw-civil-dusk').textContent = tw.civil_dusk || '—';
        document.getElementById('tw-nautical-dusk').textContent = tw.nautical_dusk || '—';
        document.getElementById('tw-astro-dusk').textContent = tw.astronomical_dusk || '—';
    }
    
    document.getElementById('imaging-window').textContent = `${formatHour(data.imaging_window_start)} → ${formatHour(data.imaging_window_end)}`;
    const numHrs = data.num_hours || ((data.imaging_window_end + 24 - data.imaging_window_start) % 24);
    document.getElementById('imaging-hours').textContent = `${numHrs} hours of imaging time tonight`;
    
    // Moon info — show imaging window range
    const moon = data.moon || {};
    document.getElementById('moon-illumination').textContent = `${Math.round(moon.illumination || 0)}% illuminated`;
    document.getElementById('moon-altitude').textContent = formatMoonWindow(moon);
    
    // Verdict area — show no forecast available
    document.getElementById('verdict-text').textContent = '—';
    document.getElementById('verdict-label').textContent = data.no_api_key ? '' : (data.error || '');
    document.getElementById('worst-issue').textContent = '';
    
    // Hourly table — show message
    document.getElementById('hourly-body').innerHTML = `<tr><td colspan="8" style="text-align:center;padding:1.5rem;color:var(--text-secondary)">${tableMessage}</td></tr>`;
}

function renderForecast(data) {
    const card = document.getElementById('verdict-card');
    card.className = 'card hero-card ' + data.verdict.toLowerCase().replace('-', '');
    const icons = { 'GO': '🟢', 'MAYBE': '🟡', 'NO-GO': '🔴' };
    document.getElementById('verdict-icon').textContent = icons[data.verdict] || '⏳';
    document.getElementById('verdict-text').textContent = data.verdict;
    const labels = { 'GO': 'Great night for imaging!', 'MAYBE': 'Marginal — check conditions', 'NO-GO': 'Poor conditions tonight' };
    document.getElementById('verdict-label').textContent = labels[data.verdict] || '';
    const sc = document.getElementById('score-circle');
    sc.className = 'score-circle ' + data.verdict.toLowerCase().replace('-', '');
    document.getElementById('score-value').textContent = data.score;

    const bb = document.getElementById('broadband-verdict');
    bb.querySelector('.sub-verdict-value').textContent = data.broadband_verdict;
    bb.querySelector('.sub-verdict-value').className = 'sub-verdict-value score-badge ' + data.broadband_verdict.toLowerCase().replace('-', '');
    const nb = document.getElementById('narrowband-verdict');
    nb.querySelector('.sub-verdict-value').textContent = data.narrowband_verdict;
    nb.querySelector('.sub-verdict-value').className = 'sub-verdict-value score-badge ' + data.narrowband_verdict.toLowerCase().replace('-', '');

    document.getElementById('filter-rec').textContent = data.filter_recommendation;
    document.getElementById('filter-detail').textContent = data.filter_detail;

    const moon = data.moon || {};
    document.getElementById('moon-illumination').textContent = `${Math.round(moon.illumination || 0)}% illuminated`;
    document.getElementById('moon-altitude').textContent = formatMoonWindow(moon);

    document.getElementById('imaging-window').textContent = `${formatHour(data.imaging_window_start)} → ${formatHour(data.imaging_window_end)}`;
    document.getElementById('imaging-hours').textContent = `${data.num_hours} hours of imaging time tonight`;
    document.getElementById('worst-issue').textContent = data.worst_issue;

    // Populate twilight details
    const tw = data.twilight || {};
    if (tw.sunset) {
        document.getElementById('twilight-details').style.display = 'block';
        document.getElementById('tw-sunset').textContent = tw.sunset || '—';
        document.getElementById('tw-civil-dusk').textContent = tw.civil_dusk || '—';
        document.getElementById('tw-nautical-dusk').textContent = tw.nautical_dusk || '—';
        document.getElementById('tw-astro-dusk').textContent = tw.astronomical_dusk || '—';
    }

    const tbody = document.getElementById('hourly-body');
    tbody.innerHTML = '';
    (data.hours || []).forEach(h => {
        const cls = h.score >= 70 ? 'go' : (h.score >= 45 ? 'maybe' : 'nogo');
        tbody.innerHTML += `<tr>
            <td>${h.time}</td>
            <td><span class="score-badge ${cls}">${h.score}</span></td>
            <td>${h.cloud_pct}%</td>
            <td>${h.transparency}</td>
            <td>${h.seeing}</td>
            <td>${h.wind_mph} mph</td>
            <td>${h.temp_f}°F</td>
            <td>${h.dew_depression_f}°F</td>
        </tr>`;
    });

    if (data.fetched_at) {
        const d = new Date(data.fetched_at + 'Z');
        document.getElementById('last-updated').textContent = `Last updated: ${d.toLocaleString()} · Credits: ${data.credits_used || '?'}/100`;
    }
}

function renderTomorrowForecast(data) {
    const section = document.getElementById('tomorrow-section');
    section.style.display = '';

    const icons = { 'GO': '🟢', 'MAYBE': '🟡', 'NO-GO': '🔴' };
    document.getElementById('tomorrow-verdict-icon').textContent = icons[data.verdict] || '⏳';
    document.getElementById('tomorrow-verdict-text').textContent = data.verdict;
    document.getElementById('tomorrow-score').textContent = data.score + '/100';
    document.getElementById('tomorrow-window').textContent = `${formatHour(data.imaging_window_start)} → ${formatHour(data.imaging_window_end)}`;
    document.getElementById('tomorrow-hours').textContent = `(${data.num_hours} hours)`;
    document.getElementById('tomorrow-worst').textContent = data.worst_issue;

    const tbody = document.getElementById('tomorrow-body');
    tbody.innerHTML = '';
    (data.hours || []).forEach(h => {
        const cls = h.score >= 70 ? 'go' : (h.score >= 45 ? 'maybe' : 'nogo');
        tbody.innerHTML += `<tr>
            <td>${h.time}</td>
            <td><span class="score-badge ${cls}">${h.score}</span></td>
            <td>${h.cloud_pct}%</td>
            <td>${h.transparency}</td>
            <td>${h.seeing}</td>
            <td>${h.wind_mph} mph</td>
            <td>${h.temp_f}°F</td>
            <td>${h.dew_depression_f}°F</td>
        </tr>`;
    });
}

function renderTopTargets(targets, moon) {
    const el = document.getElementById('top-targets');
    if (!targets.length) { el.textContent = 'No visible targets tonight.'; return; }
    let html = '<div class="target-cards">';
    targets.forEach(t => {
        const cls = t.score >= 70 ? 'go' : (t.score >= 45 ? 'maybe' : 'nogo');
        const filterTag = t.narrowband_target ? (moon && moon.illumination > 40 ? '🟢 NB OK' : 'NB') : (moon && moon.illumination > 40 ? '🔴 BB' : '🟢 BB');
        const astrobinQuery = encodeURIComponent(t.catalog_id || t.name);
        const astrobinUrl = `https://www.astrobin.com/search/?q=${astrobinQuery}`;
        const astrobinLink = `<a href="${astrobinUrl}" target="_blank" rel="noopener" title="Search on Astrobin" style="text-decoration:none;font-size:0.85rem;opacity:0.7;vertical-align:middle">🔭</a>`;
        const nameLink = `<a href="#" onclick="viewTargetFromDashboard('${(t.name||'').replace(/'/g,"\\'")}'); return false;" style="text-decoration:none;color:inherit">${t.name}</a>`;
        
        let projectLine = '';
        if (t.has_active_project) {
            const pct = t.project_hours_goal > 0 ? Math.min(100, (t.project_hours_accumulated / t.project_hours_goal) * 100) : 0;
            projectLine = `<div class="target-card-meta">
                <a href="#" onclick="viewProjectFromDashboard(${t.project_id}, '${(t.name||'').replace(/'/g,"\\'")}'); return false;" style="text-decoration:none;color:inherit" title="View project">
                    📂 <div class="progress-bar" style="display:inline-block;width:60px;vertical-align:middle"><div class="progress-fill" style="width:${pct}%"></div></div>
                    <span style="font-size:0.78rem;margin-left:0.2rem">${t.project_hours_accumulated.toFixed(1)}/${t.project_hours_goal}h</span>
                </a>
            </div>`;
        } else {
            projectLine = `<div class="target-card-meta">
                <button class="btn-sm" onclick="quickCreateProject(${t.id}, '${(t.name||'').replace(/'/g,"\\'")}'); this.disabled=true; this.textContent='Creating…'" style="font-size:0.72rem;padding:0.15rem 0.4rem">+ Start Project</button>
            </div>`;
        }
        
        html += `<div class="target-card">
            <div class="target-card-header">
                <span class="target-card-name">${nameLink} ${astrobinLink}</span>
                <span class="score-badge ${cls}" title="Target score (0–100) based on altitude, visibility hours, moon separation, and filter compatibility">${t.score}</span>
            </div>
            <span class="target-card-catalog">${t.catalog_id || ''} · ${t.constellation} · ${t.target_type}</span>
            <div class="target-card-stats">
                <span title="Maximum altitude above the horizon tonight">↑ ${t.max_altitude}°</span>
                <span title="Hours the target is above 20° altitude (usable imaging time)">⏱ ${t.hours_above_20}h</span>
                <span title="Angular separation from the moon — greater distance means less moon glare">🌙 ${t.moon_separation}°</span>
                <span title="${t.narrowband_target ? 'Narrowband target — good for emission nebulae filters' : 'Broadband target — requires dark skies and low moon'}">${filterTag}</span>
            </div>
            ${projectLine}
        </div>`;
    });
    html += '</div>';
    el.innerHTML = html;
}

function viewTargetFromDashboard(targetName) {
    showTab('targets');
    setTimeout(() => {
        const searchEl = document.getElementById('target-search');
        if (searchEl) { searchEl.value = targetName; renderTargets(); }
    }, 100);
}

function viewProjectFromDashboard(projectId, targetName) {
    showTab('projects');
    setTimeout(() => {
        const searchEl = document.getElementById('project-search');
        if (searchEl) { searchEl.value = targetName; renderProjects(); }
    }, 100);
}

async function quickCreateProject(targetId, targetName) {
    // Sun safety warning
    if (targetName === 'The Sun') {
        if (!confirm('⚠️ SOLAR IMAGING SAFETY WARNING ⚠️\n\nNever point a telescope at the Sun without a proper, dedicated solar filter securely attached.\n\nUnfiltered sunlight WILL cause instant, permanent eye damage and can destroy your camera sensor.\n\nOnly use dedicated white-light or Hα solar filters designed for your telescope.\n\nDo you have proper solar equipment and wish to continue?')) {
            return;
        }
    }
    const projName = prompt(`Project name for ${targetName}:`, targetName + ' — Broadband');
    if (projName === null) return;  // cancelled
    try {
        const resp = await fetch('/api/projects', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ target_id: targetId, name: projName || targetName, goal_hours: 0, status: 'not_started' })
        });
        const result = await resp.json();
        // Reload projects data, switch to projects tab, then open edit modal
        const projResp = await fetch('/api/projects');
        projectsData = await projResp.json();
        showTab('projects');
        setTimeout(() => {
            renderProjects();
            if (result.id) editProject(result.id);
        }, 100);
    } catch (e) {
        alert('Failed to create project: ' + e.message);
    }
}

function formatHour(h) {
    if (h == null) return '?';
    if (h === 0) return '12 AM';
    if (h < 12) return h + ' AM';
    if (h === 12) return '12 PM';
    return (h - 12) + ' PM';
}

function formatMoonWindow(moon) {
    // Show moon altitude range during the imaging window
    if (moon.window_up === false) {
        return 'Below horizon all night';
    }
    if (moon.window_alt_min != null && moon.window_alt_max != null) {
        const min = Math.round(moon.window_alt_min);
        const max = Math.round(moon.window_alt_max);
        let text = '';
        if (min <= 0 && max <= 0) {
            return 'Below horizon all night';
        } else if (min <= 0) {
            // Moon rises or sets during window
            text = `Up to ${max}°`;
            if (moon.window_rises_at) text += `, rises ~${moon.window_rises_at}`;
            if (moon.window_sets_at) text += `, sets ~${moon.window_sets_at}`;
        } else {
            text = `${min}° to ${max}°`;
        }
        const hrs = moon.window_hours_up;
        const total = moon.window_total_hours;
        if (hrs != null && total != null && hrs < total) {
            text += ` (${hrs}/${total}h above)`;
        }
        return text;
    }
    // Fallback to current altitude
    return moon.altitude > 0 ? `${Math.round(moon.altitude)}° above horizon` : 'Below horizon';
}

async function refreshForecast() {
    document.getElementById('verdict-text').textContent = 'Refreshing...';
    await fetch('/api/forecast/refresh', { method: 'POST' });
    setTimeout(loadDashboard, 4000);
}

// ─── Targets ───
let targetsData = [];
let targetsSortCol = null;
let targetsSortAsc = true;

async function loadTargets() {
    const season = document.getElementById('target-season-filter')?.value || '';
    const type = document.getElementById('target-type-filter')?.value || '';
    let url = '/api/targets?';
    if (season) url += `season=${season}&`;
    if (type) url += `target_type=${encodeURIComponent(type)}&`;
    const resp = await fetch(url);
    targetsData = await resp.json();
    renderTargets();
}

// Equipment filter state
let _equipFilterActive = false;
let _equipFilterData = null;  // { telescopes: [...], cameras: [...], filters: [...] }

async function toggleEquipmentFilter() {
    const btn = document.getElementById('btn-equip-filter');
    const scopePicker = document.getElementById('equip-telescope-picker');
    const camPicker = document.getElementById('equip-camera-picker');
    
    if (_equipFilterActive) {
        _equipFilterActive = false;
        btn.style.background = '';
        btn.style.color = '';
        scopePicker.style.display = 'none';
        camPicker.style.display = 'none';
        renderTargets();
        return;
    }
    
    // Load equipment if not cached
    if (!_equipFilterData) {
        const resp = await fetch('/api/my-equipment-options');
        _equipFilterData = await resp.json();
    }
    
    const scopes = _equipFilterData.telescopes || [];
    if (scopes.length === 0) {
        alert('No telescopes found in My Equipment. Add a telescope first.');
        return;
    }
    
    // Telescope picker
    if (scopes.length > 1) {
        scopePicker.innerHTML = scopes.map((s, i) =>
            `<option value="${i}">${s.manufacturer} ${s.name} (${s.focal_length_mm || '?'}mm)</option>`
        ).join('');
        scopePicker.style.display = '';
    } else {
        scopePicker.style.display = 'none';
    }
    
    // Camera picker
    const cams = _equipFilterData.cameras || [];
    if (cams.length > 1) {
        camPicker.innerHTML = cams.map((c, i) =>
            `<option value="${i}">${c.manufacturer} ${c.name}</option>`
        ).join('');
        camPicker.style.display = '';
    } else {
        camPicker.style.display = 'none';
    }
    
    _equipFilterActive = true;
    btn.style.background = 'var(--accent)';
    btn.style.color = '#fff';
    renderTargets();
}

function applyEquipmentFilter() {
    renderTargets();
}

function getEquipmentFilterParams() {
    if (!_equipFilterActive || !_equipFilterData) return null;
    const scopes = _equipFilterData.telescopes || [];
    const cams = _equipFilterData.cameras || [];
    const filters = _equipFilterData.filters || [];
    
    const scopePicker = document.getElementById('equip-telescope-picker');
    const camPicker = document.getElementById('equip-camera-picker');
    const scopeIdx = scopes.length > 1 ? parseInt(scopePicker.value) || 0 : 0;
    const camIdx = cams.length > 1 ? parseInt(camPicker.value) || 0 : 0;
    const scope = scopes[scopeIdx];
    if (!scope) return null;
    
    const fl = scope.focal_length_mm || 0;
    
    // Compute FOV if we have both telescope FL and camera sensor dimensions
    let fov_short_arcmin = null;
    let fov_long_arcmin = null;
    const cam = cams[camIdx];
    if (cam && fl && cam.sensor_width_mm && cam.sensor_height_mm) {
        // FOV (degrees) = 2 * atan(sensor_dimension_mm / (2 * focal_length_mm)) * (180/pi)
        const fovW = 2 * Math.atan(cam.sensor_width_mm / (2 * fl)) * (180 / Math.PI) * 60; // arcmin
        const fovH = 2 * Math.atan(cam.sensor_height_mm / (2 * fl)) * (180 / Math.PI) * 60;
        fov_short_arcmin = Math.min(fovW, fovH);
        fov_long_arcmin = Math.max(fovW, fovH);
    }
    
    const hasNarrowband = filters.some(f =>
        (f.filter_type || '').toLowerCase().includes('narrowband') ||
        (f.bandpass || '').toLowerCase().includes('ha') ||
        (f.bandpass || '').toLowerCase().includes('oiii') ||
        (f.bandpass || '').toLowerCase().includes('sii') ||
        (f.name || '').toLowerCase().includes('l-extreme') ||
        (f.name || '').toLowerCase().includes('l-enhance') ||
        (f.name || '').toLowerCase().includes('l-synergy')
    );
    const hasBroadband = filters.some(f =>
        (f.filter_type || '').toLowerCase().includes('broadband') ||
        (f.filter_type || '').toLowerCase().includes('light pollution') ||
        (f.bandpass || '').toLowerCase().includes('lrgb') ||
        (f.name || '').toLowerCase().includes('l-pro') ||
        (f.name || '').toLowerCase().includes('l-quad')
    ) || filters.length === 0;  // no filters = assume broadband capable
    
    return { focal_length: fl, fov_short_arcmin, fov_long_arcmin, hasNarrowband, hasBroadband };
}

function renderTargets() {
    const searchTerm = (document.getElementById('target-search')?.value || '').toLowerCase();
    let filtered = targetsData;
    if (searchTerm) {
        filtered = filtered.filter(t => 
            (t.name||'').toLowerCase().includes(searchTerm) ||
            (t.catalog_id||'').toLowerCase().includes(searchTerm) ||
            (t.alt_catalog_ids||'').toLowerCase().includes(searchTerm) ||
            (t.target_type||'').toLowerCase().includes(searchTerm) ||
            (t.constellation||'').toLowerCase().includes(searchTerm)
        );
    }
    // Equipment filter
    const eqParams = getEquipmentFilterParams();
    if (eqParams) {
        filtered = filtered.filter(t => {
            const isSolarSystem = ['Planet','Moon','Sun'].includes(t.target_type);
            // Filter type check — NB/BB compatibility (skip for solar system)
            if (!isSolarSystem) {
                if (t.narrowband_target && !t.broadband_target && !eqParams.hasNarrowband) return false;
                if (t.broadband_target && !t.narrowband_target && !eqParams.hasBroadband) return false;
            }
            // FOV size check — applies to everything including solar system
            if (eqParams.fov_short_arcmin && eqParams.fov_long_arcmin && t.size_arcmin) {
                const targetSize = t.size_arcmin;
                const minSize = eqParams.fov_short_arcmin * 0.05;  // at least 5% of short axis
                const maxSize = eqParams.fov_long_arcmin * 0.95;   // no more than 95% of long axis
                if (targetSize < minSize || targetSize > maxSize) return false;
            }
            return true;
        });
    }
    if (targetsSortCol) {
        filtered.sort((a, b) => {
            let va = a[targetsSortCol] ?? '', vb = b[targetsSortCol] ?? '';
            if (typeof va === 'number' && typeof vb === 'number') return targetsSortAsc ? va - vb : vb - va;
            if (typeof va === 'boolean') { va = va ? 1 : 0; vb = vb ? 1 : 0; return targetsSortAsc ? va - vb : vb - va; }
            return targetsSortAsc ? String(va).localeCompare(String(vb)) : String(vb).localeCompare(String(va));
        });
    }
    const arrow = (col) => targetsSortCol === col ? (targetsSortAsc ? ' ▲' : ' ▼') : '';
    const thead = document.querySelector('#targets-table thead tr');
    thead.innerHTML = `
        <th class="sortable" onclick="sortTargets('name')">Name${arrow('name')}</th>
        <th class="sortable" onclick="sortTargets('catalog_id')" title="Catalog designation (e.g. M42, NGC 7000, IC 1396)">Catalog${arrow('catalog_id')}</th>
        <th class="sortable" onclick="sortTargets('target_type')" title="DSO classification — nebula, galaxy, cluster, etc.">Type${arrow('target_type')}</th>
        <th class="sortable" onclick="sortTargets('constellation')" title="The constellation where this object is located">Constellation${arrow('constellation')}</th>
        <th class="sortable" onclick="sortTargets('season')" title="Best viewing season — when the target is highest in the sky during imaging hours">Season${arrow('season')}</th>
        <th class="sortable" onclick="sortTargets('size_arcmin')" title="Apparent size in arcminutes — larger values fill more of the field of view">Size${arrow('size_arcmin')}</th>
        <th class="sortable" onclick="sortTargets('difficulty')" title="Imaging difficulty — Beginner (bright, large) to Expert (faint, small, or requires long integration)">Difficulty${arrow('difficulty')}</th>
        <th class="sortable" onclick="sortTargets('narrowband_target')" title="Suitable for narrowband filters (Hα, OIII, SII) — typically emission nebulae and supernova remnants">NB${arrow('narrowband_target')}</th>
        <th class="sortable" onclick="sortTargets('broadband_target')" title="Suitable for broadband/RGB imaging — galaxies, reflection nebulae, star clusters">BB${arrow('broadband_target')}</th>
        <th title="Filters from your equipment recommended for this target based on its emission characteristics">Recommended Filters</th>
        <th></th>`;
    
    const tbody = document.getElementById('targets-body');
    const rows = [];
    filtered.forEach(t => {
        const astrobinQuery = encodeURIComponent(t.catalog_id || t.name);
        const astrobinUrl = `https://www.astrobin.com/search/?q=${astrobinQuery}`;
        const recFilters = (t.recommended_filters || [])
            .map(f => `<span style="display:inline-block;background:var(--bg-secondary);padding:0.15rem 0.4rem;border-radius:4px;margin:0.1rem;font-size:0.78rem" title="${f.reason}">${f.name}</span>`)
            .join('') || '<span style="color:var(--text-secondary);font-size:0.78rem">No filters selected</span>';
        rows.push(`<tr>
            <td><strong>${t.name}</strong> <a href="${astrobinUrl}" target="_blank" rel="noopener" title="Search on Astrobin" style="text-decoration:none;font-size:0.85rem;opacity:0.7;vertical-align:middle">🔭</a></td>
            <td title="Catalog ID">${t.catalog_id || ''}</td>
            <td>${t.target_type}</td>
            <td>${t.constellation || ''}</td>
            <td>${t.season || ''}</td>
            <td title="${t.size_arcmin ? t.size_arcmin + ' arcminutes apparent size' : ''}">${t.size_arcmin ? t.size_arcmin + "'" : ''}</td>
            <td>${t.difficulty || ''}</td>
            <td title="${t.narrowband_target ? 'Good narrowband target — responds well to Hα, OIII, SII filters' : 'Not a primary narrowband target'}">${t.narrowband_target ? '✅' : ''}</td>
            <td title="${t.broadband_target ? 'Good broadband/RGB target — best under dark skies with low moon' : 'Not a primary broadband target'}">${t.broadband_target ? '✅' : ''}</td>
            <td>${recFilters}</td>
            <td><button class="btn-sm" onclick="startProject(${t.id}, '${t.name.replace(/'/g, "\\'")}')">+ Project</button></td>
        </tr>`);
    });
    tbody.innerHTML = rows.join('');
}

function sortTargets(col) {
    if (targetsSortCol === col) targetsSortAsc = !targetsSortAsc;
    else { targetsSortCol = col; targetsSortAsc = true; }
    renderTargets();
}

// ─── Projects ───
let projectsData = [];
let projectsSortCol = null;
let projectsSortAsc = true;
const _projExpanded = {};  // track expand/collapse per project id

async function loadProjects() {
    const resp = await fetch('/api/projects');
    projectsData = await resp.json();
    renderProjects();
}

function renderProjects() {
    const el = document.getElementById('projects-list');
    if (!projectsData.length) { el.innerHTML = '<p>No projects yet. Start one from the Targets tab!</p>'; return; }
    
    const searchTerm = (document.getElementById('project-search')?.value || '').toLowerCase();
    let filtered = projectsData;
    if (searchTerm) {
        filtered = filtered.filter(p =>
            (p.target_name||'').toLowerCase().includes(searchTerm) ||
            (p.name||'').toLowerCase().includes(searchTerm) ||
            (p.target_catalog_id||'').toLowerCase().includes(searchTerm) ||
            (p.status||'').toLowerCase().includes(searchTerm) ||
            (p.filter_used||'').toLowerCase().includes(searchTerm)
        );
    }
    
    if (projectsSortCol) {
        filtered.sort((a, b) => {
            let va = a[projectsSortCol] ?? '', vb = b[projectsSortCol] ?? '';
            if (typeof va === 'number' && typeof vb === 'number') return projectsSortAsc ? va - vb : vb - va;
            return projectsSortAsc ? String(va).localeCompare(String(vb)) : String(vb).localeCompare(String(va));
        });
    }

    const arrow = (col) => projectsSortCol === col ? (projectsSortAsc ? ' ▲' : ' ▼') : '';
    let html = `<div class="table-scroll"><table><thead><tr>
        <th class="sortable" onclick="sortProjects('name')">Project${arrow('name')}</th>
        <th class="sortable" onclick="sortProjects('target_name')">Target${arrow('target_name')}</th>
        <th class="sortable" onclick="sortProjects('status')">Status${arrow('status')}</th>
        <th class="sortable" onclick="sortProjects('accumulated_hours')">Overall Progress${arrow('accumulated_hours')}</th>
        <th class="sortable" onclick="sortProjects('started_at')">Started${arrow('started_at')}</th>
        <th>Actions</th>
    </tr></thead><tbody>`;
    
    filtered.forEach(p => {
        const pct = p.goal_hours > 0 ? Math.min(100, (p.accumulated_hours / p.goal_hours) * 100) : 0;
        const started = p.started_at ? p.started_at.split('T')[0] : '';
        const projName = p.name || p.target_name || 'Project #' + p.id;
        const targetLabel = p.target_catalog_id ? `${p.target_name} (${p.target_catalog_id})` : (p.target_name || '');
        const astrobinQuery = encodeURIComponent(p.target_catalog_id || p.target_name || projName);
        const astrobinUrl = `https://www.astrobin.com/search/?q=${astrobinQuery}`;
        const statusClass = p.status === 'complete' ? 'go' : (p.status === 'not_started' ? 'nogo' : 'maybe');
        const statusLabel = p.status === 'not_started' ? 'Not Started' : p.status;
        const notesPreview = p.notes ? `<div style="font-size:0.75rem;color:var(--text-secondary);margin-top:0.15rem;max-width:250px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${(p.notes||'').replace(/"/g,'&quot;')}">${p.notes}</div>` : '';
        
        // Channel data (LRGBSHO order)
        const channels = CH_ORDER.map(ch => ({
            key: ch, label: CH_LABELS[ch], color: CH_COLORS[ch],
            accum: p['integration_' + ch + '_hrs'] || 0,
            goal: p['goal_' + ch + '_hours'] || 0,
        }));
        const activeChannels = channels.filter(c => c.goal > 0 || c.accum > 0);
        const expanded = _projExpanded[p.id] !== false;  // default expanded
        const chevron = activeChannels.length > 0
            ? `<button class="btn-sm" onclick="_projExpanded[${p.id}]=${expanded?'false':'true'};renderProjects()" style="font-size:0.7rem;padding:0.1rem 0.35rem;margin-left:0.3rem;vertical-align:middle">${expanded ? '▾' : '▸'}</button>`
            : '';
        
        // Build channel detail lines
        let chDetail = '';
        if (expanded && activeChannels.length > 0) {
            chDetail = '<div style="margin-top:0.35rem;padding-left:0.25rem">';
            activeChannels.forEach(c => {
                const chPct = c.goal > 0 ? Math.min(100, (c.accum / c.goal) * 100) : (c.accum > 0 ? 100 : 0);
                const met = c.goal > 0 && c.accum >= c.goal;
                const remaining = c.goal > 0 ? Math.max(0, c.goal - c.accum) : 0;
                const icon = met ? '<span style="color:var(--go)">✅</span>' : '<span style="display:inline-block;width:1.1em"></span>';
                const remainStr = c.goal > 0 ? (met ? '' : `<span style="font-size:0.72rem;color:var(--text-secondary);margin-left:0.3rem">${remaining.toFixed(1)}h left</span>`) : '';
                chDetail += `<div style="display:flex;align-items:center;gap:0.3rem;margin:0.2rem 0">
                    ${icon}<span style="font-size:0.75rem;font-weight:600;color:${c.color};width:2.2rem">${c.label}</span>
                    <div class="progress-bar" style="display:inline-block;width:80px;vertical-align:middle"><div class="progress-fill" style="width:${chPct}%;background:${c.color}"></div></div>
                    <span style="font-size:0.75rem;color:var(--text-secondary)">${c.accum.toFixed(1)}${c.goal > 0 ? '/' + c.goal + 'h' : 'h'}</span>${remainStr}
                </div>`;
            });
            chDetail += '</div>';
        }
        
        html += `<tr>
            <td>
                <a href="#" onclick="viewProjectSessions(${p.id}, '${projName.replace(/'/g,"\\'")}'); return false;" style="font-weight:600">${projName}</a>
                ${notesPreview}
            </td>
            <td>
                ${targetLabel}
                <a href="${astrobinUrl}" target="_blank" rel="noopener" title="Search on Astrobin" style="text-decoration:none;font-size:0.85rem;opacity:0.7;vertical-align:middle">🔭</a>
            </td>
            <td><span class="score-badge ${statusClass}">${statusLabel}</span></td>
            <td>
                <div style="display:flex;align-items:center">
                    <div class="progress-bar" style="display:inline-block;width:100px;vertical-align:middle"><div class="progress-fill" style="width:${pct}%"></div></div>
                    <span style="font-size:0.8rem;margin-left:0.3rem">${p.accumulated_hours.toFixed(1)}/${p.goal_hours}h</span>${chevron}
                </div>${chDetail}
            </td>
            <td>${started}</td>
            <td style="white-space:nowrap">
                <button class="btn-sm" onclick="editProject(${p.id})">✏️</button>
                <button class="btn-sm" onclick="showProjectSessionModal(${p.id}, '${(p.target_name||'').replace(/'/g,"\\'")}')">+ Session</button>
                <button class="btn-sm" style="color:var(--danger,#e55)" onclick="deleteProject(${p.id}, '${(p.target_name||'').replace(/'/g,"\\'")}')">🗑</button>
            </td>
        </tr>`;
    });
    html += '</tbody></table></div>';
    el.innerHTML = html;
}

function sortProjects(col) {
    if (projectsSortCol === col) projectsSortAsc = !projectsSortAsc;
    else { projectsSortCol = col; projectsSortAsc = true; }
    renderProjects();
}

async function deleteProject(id, name) {
    if (!confirm(`Delete project "${name}" and all its sessions?`)) return;
    await fetch('/api/projects/' + id, { method: 'DELETE' });
    loadProjects();
}

function editProject(id) {
    const p = projectsData.find(x => x.id === id);
    if (!p) return;
    const projName = p.target_name || p.name || 'Project #' + p.id;
    const statusOpts = ['not_started', 'active', 'complete'].map(s => {
        const label = s === 'not_started' ? 'Not Started' : s.charAt(0).toUpperCase() + s.slice(1);
        return `<option value="${s}" ${p.status === s ? 'selected' : ''}>${label}</option>`;
    }).join('');
    const goals = CH_ORDER.map(ch => {
        const key = 'goal_' + ch + '_hours';
        return { ch, label: CH_LABELS[ch], color: CH_COLORS[ch], val: p[key] || 0 };
    });
    const totalGoal = goals.reduce((s, g) => s + g.val, 0);
    
    const goalInputs = goals.map(g =>
        `<div class="form-group" style="flex:1;min-width:60px"><label style="color:${g.color};font-weight:600">${g.label}</label><input type="number" id="ep-g${g.ch}" step="any" min="0" value="${g.val}" oninput="updateGoalTotal()" style="-moz-appearance:textfield" /></div>`
    ).join('');
    
    const targetDisplay = (p.target_catalog_id ? p.target_name + ' (' + p.target_catalog_id + ')' : p.target_name) || 'Unknown Target';
    openModal(`Edit Project — ${projName}`, `
        <div class="form-group"><label>Target</label><input type="text" value="${targetDisplay}" disabled style="background:var(--bg-secondary);color:var(--text-secondary);cursor:not-allowed" /></div>
        <div class="form-group"><label>Project Name</label><input type="text" id="ep-name" value="${(p.name||'').replace(/"/g,'&quot;')}" placeholder="${p.target_name || ''}" /></div>
        <div class="form-group"><label>Status</label><select id="ep-status">${statusOpts}</select></div>
        <p style="font-size:0.8rem;color:var(--text-secondary);margin:0.75rem 0 0.25rem">Channel Goal Hours <span style="font-size:0.75rem">(LRGBSHO)</span>:</p>
        <div style="display:flex;flex-wrap:wrap;gap:0.3rem">${goalInputs}</div>
        <div style="font-size:0.85rem;color:var(--text);margin:0.25rem 0 0.75rem;padding:0.4rem 0.6rem;background:var(--bg-secondary);border-radius:6px">
            Total Goal: <strong id="ep-goal-total">${totalGoal.toFixed(1)}</strong>h
        </div>
        <div class="form-group"><label>Notes</label><textarea id="ep-notes" rows="2">${p.notes || ''}</textarea></div>
        <button class="btn-primary" onclick="saveProjectEdit(${p.id})" style="width:100%;margin-top:0.5rem">Save Changes</button>
    `);
}

function updateGoalTotal() {
    const total = CH_ORDER.reduce((s, ch) => s + (parseFloat(document.getElementById('ep-g' + ch)?.value) || 0), 0);
    const el = document.getElementById('ep-goal-total');
    if (el) el.textContent = total.toFixed(1);
}

async function saveProjectEdit(id) {
    const goals = {};
    let total = 0;
    CH_ORDER.forEach(ch => {
        const v = parseFloat(document.getElementById('ep-g' + ch)?.value) || 0;
        goals['goal_' + ch + '_hours'] = v;
        total += v;
    });
    await fetch('/api/projects/' + id, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            name: document.getElementById('ep-name').value || null,
            status: document.getElementById('ep-status').value,
            goal_hours: total,
            ...goals,
            notes: document.getElementById('ep-notes').value
        })
    });
    closeModal();
    loadProjects();
}

async function showProjectSessionModal(projectId, targetName) {
    const eqResp = await fetch('/api/my-equipment-options');
    const eq = await eqResp.json();
    const settingsResp = await fetch('/api/settings');
    const settings = await settingsResp.json();
    
    const cameraOpts = '<option value="">— Select —</option>' + eq.cameras.map(c => `<option value="${escAttr(c.name)}" data-color="${c.color_type||''}">${c.manufacturer} ${c.name}</option>`).join('');
    const teleOpts = '<option value="">— Select —</option>' + eq.telescopes.map(t => `<option value="${escAttr(t.name)}">${t.manufacturer} ${t.name}</option>`).join('');
    const mountOpts = '<option value="">— Select —</option>' + eq.mounts.map(m => `<option value="${escAttr(m.name)}">${m.manufacturer} ${m.name}</option>`).join('');
    const filterOpts = '<option value="">— Select —</option>' + eq.filters.map(f => `<option value="${escAttr(f.name)}">${f.manufacturer} ${f.name}</option>`).join('');
    const bortleVal = settings.bortle_zone || 5;
    const bortleOpts = [1,2,3,4,5,6,7,8,9].map(b => `<option value="${b}" ${b===bortleVal?'selected':''}>${b}</option>`).join('');

    openModal(`Log Session — ${targetName}`, `
        <input type="hidden" id="psess-project-id" value="${projectId}" />
        <input type="hidden" id="psess-target-name" value="${targetName}" />
        <div class="form-group"><label>Date</label><input type="date" id="psess-date" value="${new Date().toISOString().split('T')[0]}" onchange="autoFillMoon('psess')" /></div>
        <h4 style="margin:0.75rem 0 0.25rem;font-size:0.85rem;color:var(--text-secondary)">Equipment</h4>
        <div class="form-row">
            <div class="form-group"><label>Camera</label><select id="psess-camera">${cameraOpts}</select></div>
            <div class="form-group"><label>Telescope</label><select id="psess-telescope">${teleOpts}</select></div>
        </div>
        <div class="form-row">
            <div class="form-group"><label>Mount</label><select id="psess-mount">${mountOpts}</select></div>
            <div class="form-group"><label>Filter</label><select id="psess-filter">${filterOpts}</select></div>
        </div>
        <h4 style="margin:0.75rem 0 0.25rem;font-size:0.85rem;color:var(--text-secondary)">Imaging Details</h4>
        <div class="form-row">
            <div class="form-group"><label># Subs</label><input type="text" inputmode="numeric" pattern="[0-9]*" id="psess-subs" oninput="this.value=this.value.replace(/[^0-9]/g,'')" /></div>
            <div class="form-group"><label>Sub Length (s)</label><input type="text" inputmode="numeric" pattern="[0-9]*" id="psess-sublen" value="300" oninput="this.value=this.value.replace(/[^0-9]/g,'')" /></div>
        </div>
        <div class="form-row">
            <div class="form-group"><label>Gain</label><input type="text" inputmode="numeric" pattern="[0-9]*" id="psess-gain" value="100" oninput="this.value=this.value.replace(/[^0-9]/g,'')" /></div>
            <div class="form-group"><label>Bortle</label><select id="psess-bortle">${bortleOpts}</select></div>
        </div>
        <div class="form-row">
            <div class="form-group"><label>Moon Illumination %</label>
                <div style="display:flex;align-items:center;gap:0.4rem">
                    <input type="text" inputmode="numeric" pattern="[0-9]*" id="psess-moon" oninput="this.value=this.value.replace(/[^0-9]/g,'')" style="flex:1" />
                    <span id="psess-moon-phase" style="font-size:0.75rem;color:var(--text-secondary);white-space:nowrap"></span>
                </div>
            </div>
        </div>
        <div class="form-group"><label>Rating (1-5)</label>
            <input type="range" id="psess-rating" min="1" max="5" value="3" oninput="this.nextElementSibling.textContent='★'.repeat(this.value)+'☆'.repeat(5-this.value)" />
            <span>★★★☆☆</span></div>
        <div class="form-group"><label>Notes</label><textarea id="psess-notes" rows="2"></textarea></div>
        <button class="btn-primary" onclick="saveProjectSession()" style="width:100%;margin-top:0.5rem">Save Session</button>
    `);
    autoFillMoon('psess');
}

async function saveProjectSession() {
    const projectId = parseInt(document.getElementById('psess-project-id').value);
    const subs = parseInt(document.getElementById('psess-subs').value) || 0;
    const subLen = parseInt(document.getElementById('psess-sublen').value) || 300;
    const moonVal = document.getElementById('psess-moon').value;
    await fetch('/api/sessions', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            project_id: projectId,
            session_date: document.getElementById('psess-date').value,
            target_name: document.getElementById('psess-target-name').value,
            camera_used: document.getElementById('psess-camera').value || null,
            telescope_used: document.getElementById('psess-telescope').value || null,
            mount_used: document.getElementById('psess-mount').value || null,
            filter_used: document.getElementById('psess-filter').value || null,
            bortle: parseInt(document.getElementById('psess-bortle').value) || null,
            moon_illumination_pct: moonVal !== '' ? parseInt(moonVal) : null,
            num_subs: subs, sub_length_s: subLen, total_integration_min: (subs * subLen) / 60,
            gain: parseInt(document.getElementById('psess-gain').value) || null,
            rating: parseInt(document.getElementById('psess-rating').value),
            notes: document.getElementById('psess-notes').value,
        })
    });
    closeModal();
    loadProjects();
}

async function startProject(targetId, targetName) {
    const resp = await fetch('/api/projects', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target_id: targetId, goal_hours: 0 })
    });
    const result = await resp.json();
    // Switch to Projects tab, reload, then open edit modal for the new project
    showTab('projects');
    await loadProjects();
    if (result.id) editProject(result.id);
}

function showProjectModal() { alert('Use the Targets tab to start a new project from a target.'); }

// ─── Sessions ───
let sessionsData = [];
let sessionsSortCol = 'session_date';
let sessionsSortAsc = false;
let sessionsProjectFilter = null;  // {id, name} when filtering by project

function viewProjectSessions(projectId, projectName) {
    sessionsProjectFilter = { id: projectId, name: projectName };
    showTab('sessions');
}

function clearSessionProjectFilter() {
    sessionsProjectFilter = null;
    document.getElementById('session-search').value = '';
    renderSessions();
}

async function loadSessions() {
    const resp = await fetch('/api/sessions');
    sessionsData = await resp.json();
    renderSessions();
}

function renderSessions() {
    const searchTerm = (document.getElementById('session-search')?.value || '').toLowerCase();
    let filtered = sessionsData;
    
    // Project filter
    const banner = document.getElementById('session-project-filter');
    if (sessionsProjectFilter) {
        filtered = filtered.filter(s => s.project_id === sessionsProjectFilter.id);
        document.getElementById('session-project-name').textContent = sessionsProjectFilter.name;
        banner.style.display = 'block';
    } else {
        banner.style.display = 'none';
    }
    
    // Text search
    if (searchTerm) {
        filtered = filtered.filter(s =>
            (s.target_name||'').toLowerCase().includes(searchTerm) ||
            (s.project_name||'').toLowerCase().includes(searchTerm) ||
            (s.filter_used||'').toLowerCase().includes(searchTerm) ||
            (s.session_date||'').includes(searchTerm) ||
            (s.notes||'').toLowerCase().includes(searchTerm)
        );
    }
    
    if (sessionsSortCol) {
        filtered.sort((a, b) => {
            let va = a[sessionsSortCol] ?? '', vb = b[sessionsSortCol] ?? '';
            if (typeof va === 'number' && typeof vb === 'number') return sessionsSortAsc ? va - vb : vb - va;
            return sessionsSortAsc ? String(va).localeCompare(String(vb)) : String(vb).localeCompare(String(va));
        });
    }
    const arrow = (col) => sessionsSortCol === col ? (sessionsSortAsc ? ' ▲' : ' ▼') : '';
    const thead = document.querySelector('#sessions-table thead tr');
    thead.innerHTML = `
        <th class="sortable" onclick="sortSessions('session_date')">Date${arrow('session_date')}</th>
        <th class="sortable" onclick="sortSessions('project_name')">Project${arrow('project_name')}</th>
        <th class="sortable" onclick="sortSessions('target_name')">Target${arrow('target_name')}</th>
        <th class="sortable" onclick="sortSessions('filter_used')">Filter${arrow('filter_used')}</th>
        <th class="sortable" onclick="sortSessions('num_subs')">Subs${arrow('num_subs')}</th>
        <th class="sortable" onclick="sortSessions('total_integration_min')">Total${arrow('total_integration_min')}</th>
        <th>Channels</th>
        <th class="sortable" onclick="sortSessions('moon_illumination_pct')">Moon${arrow('moon_illumination_pct')}</th>
        <th class="sortable" onclick="sortSessions('rating')">Rating${arrow('rating')}</th>
        <th>Notes</th>
        <th>Actions</th>`;
    
    const tbody = document.getElementById('sessions-body');
    tbody.innerHTML = '';
    if (!filtered.length) {
        const msg = sessionsProjectFilter ? 'No sessions for this project yet.' : (searchTerm ? 'No matching sessions.' : 'No sessions logged yet.');
        tbody.innerHTML = `<tr><td colspan="11">${msg}</td></tr>`; return;
    }
    filtered.forEach(s => {
        const stars = s.rating ? '★'.repeat(s.rating) + '☆'.repeat(5 - s.rating) : '';
        const intTime = s.total_integration_min ? (s.total_integration_min / 60).toFixed(1) + 'h' : '';
        const projLabel = s.project_name
            ? s.project_name
            : '<span style="color:var(--text-secondary);font-style:italic">No Project</span>';
        const targetLabel = s.project_target_name
            ? (s.project_target_catalog_id ? s.project_target_name + ' (' + s.project_target_catalog_id + ')' : s.project_target_name)
            : (s.target_name || '<span style="color:var(--text-secondary)">—</span>');
        const moonPct = s.moon_illumination_pct;
        const moonDisplay = moonPct != null ? `${moonPhaseIcon(moonPct)} ${Math.round(moonPct)}%` : '<span style="color:var(--text-secondary)">—</span>';
        tbody.innerHTML += `<tr>
            <td>${s.session_date}</td>
            <td>${projLabel}</td>
            <td>${targetLabel}</td>
            <td>${s.filter_used || ''}</td>
            <td>${s.num_subs || ''}</td>
            <td>${intTime}</td>
            <td>${sessionChannelStack(s)}</td>
            <td>${moonDisplay}</td>
            <td>${stars}</td>
            <td>${s.notes || ''}</td>
            <td style="white-space:nowrap">
                <button class="btn-sm" onclick="editSession(${s.id})">✏️</button>
                <button class="btn-sm" style="color:var(--danger,#e55)" onclick="deleteSession(${s.id})">🗑</button>
            </td>
        </tr>`;
    });
}

function sortSessions(col) {
    if (sessionsSortCol === col) sessionsSortAsc = !sessionsSortAsc;
    else { sessionsSortCol = col; sessionsSortAsc = true; }
    renderSessions();
}

async function deleteSession(id) {
    if (!confirm('Delete this session? Integration time will be subtracted from any linked project.')) return;
    await fetch('/api/sessions/' + id, { method: 'DELETE' });
    loadSessions();
}

async function editSession(id) {
    const s = sessionsData.find(x => x.id === id);
    if (!s) return;
    
    const eqResp = await fetch('/api/my-equipment-options');
    const eq = await eqResp.json();
    const projResp = await fetch('/api/projects');
    const projects = await projResp.json();
    
    const mkOpts = (list, field, current) => {
        let opts = '<option value="">— Select —</option>';
        list.forEach(item => {
            const sel = (current === item.name) ? 'selected' : '';
            opts += `<option value="${escAttr(item.name)}" ${sel}>${item.manufacturer} ${item.name}</option>`;
        });
        if (current && !list.find(i => i.name === current))
            opts += `<option value="${escAttr(current)}" selected>${current}</option>`;
        return opts;
    };
    
    // Project dropdown
    let projOpts = '<option value="">— No Project —</option>';
    projects.forEach(p => {
        const label = (p.name || p.target_name || 'Project #' + p.id) + ' (' + (p.target_catalog_id || p.target_name || '') + ')';
        const sel = s.project_id === p.id ? 'selected' : '';
        projOpts += `<option value="${p.id}" ${sel}>${label}</option>`;
    });
    
    const bortleVal = s.bortle || 5;
    const bortleOpts = [1,2,3,4,5,6,7,8,9].map(b => `<option value="${b}" ${b===bortleVal?'selected':''}>${b}</option>`).join('');
    const rating = s.rating || 3;
    const moonVal = s.moon_illumination_pct != null ? s.moon_illumination_pct : '';
    
    openModal('Edit Session', `
        <input type="hidden" id="edit-sess-id" value="${id}" />
        <div class="form-group"><label>Project</label><select id="edit-sess-project">${projOpts}</select></div>
        <div class="form-group"><label>Date</label><input type="date" id="edit-sess-date" value="${s.session_date || ''}" onchange="autoFillMoon('edit-sess')" /></div>
        <h4 style="margin:0.75rem 0 0.25rem;font-size:0.85rem;color:var(--text-secondary)">Equipment</h4>
        <div class="form-row">
            <div class="form-group"><label>Camera</label><select id="edit-sess-camera">${mkOpts(eq.cameras, 'name', s.camera_used)}</select></div>
            <div class="form-group"><label>Telescope</label><select id="edit-sess-telescope">${mkOpts(eq.telescopes, 'name', s.telescope_used)}</select></div>
        </div>
        <div class="form-row">
            <div class="form-group"><label>Mount</label><select id="edit-sess-mount">${mkOpts(eq.mounts, 'name', s.mount_used)}</select></div>
            <div class="form-group"><label>Filter</label><select id="edit-sess-filter">${mkOpts(eq.filters, 'name', s.filter_used)}</select></div>
        </div>
        <h4 style="margin:0.75rem 0 0.25rem;font-size:0.85rem;color:var(--text-secondary)">Imaging Details</h4>
        <div class="form-row">
            <div class="form-group"><label># Subs</label><input type="text" inputmode="numeric" pattern="[0-9]*" id="edit-sess-subs" value="${s.num_subs||''}" oninput="this.value=this.value.replace(/[^0-9]/g,'')" /></div>
            <div class="form-group"><label>Sub Length (s)</label><input type="text" inputmode="numeric" pattern="[0-9]*" id="edit-sess-sublen" value="${s.sub_length_s||300}" oninput="this.value=this.value.replace(/[^0-9]/g,'')" /></div>
        </div>
        <div class="form-row">
            <div class="form-group"><label>Gain</label><input type="text" inputmode="numeric" pattern="[0-9]*" id="edit-sess-gain" value="${s.gain||''}" oninput="this.value=this.value.replace(/[^0-9]/g,'')" /></div>
            <div class="form-group"><label>Bortle</label><select id="edit-sess-bortle">${bortleOpts}</select></div>
        </div>
        <div class="form-row">
            <div class="form-group"><label>Moon Illumination %</label>
                <div style="display:flex;align-items:center;gap:0.4rem">
                    <input type="text" inputmode="numeric" pattern="[0-9]*" id="edit-sess-moon" value="${moonVal}" oninput="this.value=this.value.replace(/[^0-9]/g,'')" style="flex:1" />
                    <span id="edit-sess-moon-phase" style="font-size:0.75rem;color:var(--text-secondary);white-space:nowrap"></span>
                </div>
            </div>
        </div>
        <div class="form-group"><label>Rating (1-5)</label>
            <input type="range" id="edit-sess-rating" min="1" max="5" value="${rating}" oninput="this.nextElementSibling.textContent='★'.repeat(this.value)+'☆'.repeat(5-this.value)" />
            <span>${'★'.repeat(rating)}${'☆'.repeat(5-rating)}</span></div>
        <div class="form-group"><label>Notes</label><textarea id="edit-sess-notes" rows="2">${s.notes||''}</textarea></div>
        <button class="btn-primary" onclick="saveEditSession()" style="width:100%;margin-top:0.5rem">Save Changes</button>
    `);
    // Auto-fill phase name for existing moon value
    if (s.session_date) autoFillMoon('edit-sess');
}

async function saveEditSession() {
    const id = parseInt(document.getElementById('edit-sess-id').value);
    const subs = parseInt(document.getElementById('edit-sess-subs').value) || 0;
    const subLen = parseInt(document.getElementById('edit-sess-sublen').value) || 300;
    const projectId = document.getElementById('edit-sess-project').value;
    const moonVal = document.getElementById('edit-sess-moon').value;
    await fetch('/api/sessions/' + id, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            project_id: projectId ? parseInt(projectId) : null,
            session_date: document.getElementById('edit-sess-date').value,
            camera_used: document.getElementById('edit-sess-camera').value || null,
            telescope_used: document.getElementById('edit-sess-telescope').value || null,
            mount_used: document.getElementById('edit-sess-mount').value || null,
            filter_used: document.getElementById('edit-sess-filter').value || null,
            bortle: parseInt(document.getElementById('edit-sess-bortle').value) || null,
            moon_illumination_pct: moonVal !== '' ? parseInt(moonVal) : null,
            num_subs: subs, sub_length_s: subLen, total_integration_min: (subs * subLen) / 60,
            gain: parseInt(document.getElementById('edit-sess-gain').value) || null,
            rating: parseInt(document.getElementById('edit-sess-rating').value),
            notes: document.getElementById('edit-sess-notes').value,
        })
    });
    closeModal();
    loadSessions();
    loadProjects();
}

async function autoFillMoon(prefix) {
    const dateEl = document.getElementById(prefix + '-date');
    const moonEl = document.getElementById(prefix + '-moon');
    const phaseEl = document.getElementById(prefix + '-moon-phase');
    if (!dateEl || !moonEl || !dateEl.value) return;
    try {
        const resp = await fetch('/api/moon-illumination?date_str=' + encodeURIComponent(dateEl.value));
        if (resp.ok) {
            const data = await resp.json();
            moonEl.value = data.illumination;
            if (phaseEl) phaseEl.textContent = data.phase_name || '';
        }
    } catch (e) { /* silently fail — user can still type manually */ }
}

// Standalone session creation removed — sessions must be created via Projects.

// ─── Equipment ───
const _equipOpen = {};  // track which sections are expanded

async function loadMyEquipment() {
    const resp = await fetch('/api/my-equipment');
    const owned = await resp.json();
    const el = document.getElementById('my-equipment-list');

    const categories = [
        { key: 'mounts', label: 'Mounts' },
        { key: 'telescopes', label: 'Telescopes' },
        { key: 'cameras', label: 'Cameras' },
        { key: 'filters', label: 'Filters' },
        { key: 'accessories', label: 'Accessories' },
    ];

    let html = '';
    
    // Column definitions per category
    const EQUIP_COLS = {
        mounts: [
            {label:'Type', fn: i => i.mount_type || ''},
            {label:'Payload', fn: i => i.max_payload_kg ? i.max_payload_kg+'kg' : ''},
            {label:'Weight', fn: i => i.weight_kg ? i.weight_kg+'kg' : ''},
            {label:'PE', fn: i => i.periodic_error_arcsec ? i.periodic_error_arcsec+'"' : '', title:'Periodic error (arcsec)'},
            {label:'GoTo', fn: i => i.goto ? '✓' : ''},
        ],
        telescopes: [
            {label:'Type', fn: i => i.telescope_type || ''},
            {label:'Aperture', fn: i => i.aperture_mm ? i.aperture_mm+'mm' : ''},
            {label:'FL', fn: i => i.focal_length_mm ? i.focal_length_mm+'mm' : '', title:'Focal length'},
            {label:'f/', fn: i => i.focal_ratio ? 'f/'+i.focal_ratio : '', title:'Focal ratio'},
            {label:'Weight', fn: i => i.weight_kg ? i.weight_kg+'kg' : ''},
        ],
        cameras: [
            {label:'Type', fn: i => (i.color_type||'').replace('Color (OSC)','OSC').replace('Mono','Mono')},
            {label:'Sensor', fn: i => i.sensor_model || ''},
            {label:'Pixel', fn: i => i.pixel_size_um ? i.pixel_size_um+'µm' : '', title:'Pixel size'},
            {label:'Resolution', fn: i => (i.resolution_x && i.resolution_y) ? i.resolution_x+'×'+i.resolution_y : ''},
            {label:'Sensor Size', fn: i => (i.sensor_width_mm && i.sensor_height_mm) ? i.sensor_width_mm+'×'+i.sensor_height_mm+'mm' : ''},
            {label:'Cooled', fn: i => i.cooling ? (i.cooling_delta_c ? 'Δ'+i.cooling_delta_c+'°C' : '✓') : ''},
            {label:'Bit', fn: i => i.adc_bit ? i.adc_bit+'b' : '', title:'ADC bit depth'},
        ],
        filters: [
            {label:'Type', fn: i => i.filter_type || ''},
            {label:'Bandpass', fn: i => i.bandpass ? colorizeBandpass(i.bandpass) : '', raw:true},
            {label:'Size', fn: i => i.filter_size || ''},
            {label:'Moon OK', fn: i => i.moonlight_resistant ? '✓' : '', title:'Moonlight resistant'},
        ],
        accessories: [
            {label:'Type', fn: i => i.accessory_type || ''},
            {label:'BF', fn: i => i.back_focus_mm ? i.back_focus_mm+'mm' : '', title:'Back focus contribution'},
            {label:'Mag', fn: i => i.magnification ? i.magnification+'×' : '', title:'Magnification factor'},
            {label:'Weight', fn: i => i.weight_g ? i.weight_g+'g' : ''},
        ],
    };
    
    for (const cat of categories) {
        try {
            const catResp = await fetch('/api/equipment/' + cat.key);
            const catalog = await catResp.json();
            const ownedIds = owned.filter(o => o.category === cat.key).map(o => o.catalog_id);
            const open = _equipOpen[cat.key] || false;
            const cols = EQUIP_COLS[cat.key] || [];

            const grouped = {};
            catalog.forEach(item => {
                if (!grouped[item.manufacturer]) grouped[item.manufacturer] = [];
                grouped[item.manufacturer].push(item);
            });
            
            const totalCols = cols.length + 1; // +1 for name w/ checkbox

            html += `<div class="card" style="margin-bottom:0.75rem">
                <h3 style="cursor:pointer" onclick="toggleEquipSection('${cat.key}')">
                    ${cat.label} <span id="eqcnt-${cat.key}" style="font-size:0.8rem;color:var(--text-secondary)">(${ownedIds.length} selected) ▾</span>
                </h3>
                <div id="eqsec-${cat.key}" class="equip-checklist" style="display:${open?'block':'none'};max-height:400px;overflow-y:auto;overflow-x:auto;margin-top:0.5rem">
                <table style="width:100%;border-collapse:collapse;font-size:0.82rem">
                <thead><tr style="position:sticky;top:0;background:var(--bg-primary);z-index:1">
                    <th style="text-align:left;padding:0.25rem 0.4rem;border-bottom:1px solid var(--border);white-space:nowrap">Name</th>
                    ${cols.map(c => `<th style="text-align:left;padding:0.25rem 0.4rem;border-bottom:1px solid var(--border);white-space:nowrap;color:var(--text-secondary);font-weight:500"${c.title ? ' title="'+c.title+'"' : ''}>${c.label}</th>`).join('')}
                </tr></thead><tbody>`;

            for (const [mfr, items] of Object.entries(grouped).sort()) {
                html += `<tr><td colspan="${totalCols}" style="padding:0.4rem 0.4rem 0.15rem;font-size:0.75rem;font-weight:600;color:var(--text-secondary);border-top:1px solid var(--border)">${mfr}</td></tr>`;
                items.forEach(item => {
                    const checked = ownedIds.includes(item.id) ? 'checked' : '';
                    const rowBg = checked ? 'background:color-mix(in srgb, var(--accent) 8%, transparent);' : '';
                    html += `<tr style="${rowBg}">
                        <td style="padding:0.25rem 0.4rem;white-space:nowrap">
                            <label style="display:flex;align-items:center;gap:0.35rem;cursor:pointer;margin:0">
                                <input type="checkbox" ${checked} onchange="toggleEquipItem('${cat.key}', ${item.id}, this.checked)" />
                                <span>${item.name}</span>
                            </label>
                        </td>`;
                    cols.forEach(c => {
                        const val = c.fn(item);
                        html += `<td style="padding:0.25rem 0.4rem;white-space:nowrap;color:var(--text-secondary);font-size:0.78rem"${c.title ? ' title="'+c.title+'"' : ''}>${val}</td>`;
                    });
                    html += `</tr>`;
                });
            }
            html += `</tbody></table></div></div>`;
        } catch (e) {
            console.error('Failed to load', cat.key, e);
        }
    }
    el.innerHTML = html;
}

function toggleEquipSection(key) {
    const sec = document.getElementById('eqsec-' + key);
    if (!sec) return;
    const show = sec.style.display === 'none';
    sec.style.display = show ? 'block' : 'none';
    _equipOpen[key] = show;
}

async function toggleEquipItem(category, catalogId, add) {
    if (add) {
        await fetch('/api/my-equipment', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ category: category, catalog_id: catalogId, is_primary: false })
        });
    } else {
        const resp = await fetch('/api/my-equipment');
        const items = await resp.json();
        const match = items.find(i => i.category === category && i.catalog_id === catalogId);
        if (match) await fetch('/api/my-equipment/' + match.id, { method: 'DELETE' });
    }
    // Update the count text
    const resp2 = await fetch('/api/my-equipment');
    const all = await resp2.json();
    const cnt = all.filter(o => o.category === category).length;
    const cntEl = document.getElementById('eqcnt-' + category);
    if (cntEl) cntEl.textContent = `(${cnt} selected) ▾`;
    // Invalidate cached equipment filter data so next toggle picks up changes
    _equipFilterData = null;
}

async function removeEquipment(id) {
    if (!confirm('Remove this equipment?')) return;
    await fetch('/api/my-equipment/' + id, { method: 'DELETE' });
    loadMyEquipment();
}

function exportEquipment(format) {
    const cat = document.getElementById('equip-export-cat').value;
    window.open(`/api/equipment/${cat}/export/${format}`, '_blank');
}

async function importEquipment(input) {
    const file = input.files[0];
    if (!file) return;
    const cat = document.getElementById('equip-export-cat').value;
    const format = file.name.endsWith('.csv') ? 'csv' : 'json';
    const formData = new FormData();
    formData.append('file', file);
    const resp = await fetch(`/api/equipment/${cat}/import/${format}`, { method: 'POST', body: formData });
    const result = await resp.json();
    alert(`Imported ${result.imported} items.`);
    input.value = '';
}

// ─── Settings ───
async function loadSettings() {
    const resp = await fetch('/api/settings');
    const s = await resp.json();
    document.getElementById('settings-form').innerHTML = `
    <div style="display:flex;gap:1.5rem;flex-wrap:wrap;align-items:flex-start">
        <div class="card" style="max-width:600px;flex:1;min-width:320px">
            <h3>📍 Location</h3>
            <div class="form-group"><label>Location Name</label>
                <input type="text" id="s-location" value="${s.location_name || ''}" /></div>
            <div class="form-row">
                <div class="form-group"><label>Latitude</label>
                    <input type="number" id="s-lat" step="0.0001" value="${s.latitude || ''}" /></div>
                <div class="form-group"><label>Longitude</label>
                    <input type="number" id="s-lon" step="0.0001" value="${s.longitude || ''}" /></div>
            </div>
            <div class="form-row">
                <div class="form-group"><label>Bortle Zone</label>
                    <input type="number" id="s-bortle" min="1" max="9" value="${s.bortle_zone || 5}" /></div>
                <div class="form-group"><label>Timezone</label>
                    <select id="s-timezone">
                        <option value="America/New_York" ${s.timezone=='America/New_York'?'selected':''}>Eastern (ET)</option>
                        <option value="America/Chicago" ${s.timezone=='America/Chicago'?'selected':''}>Central (CT)</option>
                        <option value="America/Denver" ${s.timezone=='America/Denver'?'selected':''}>Mountain (MT)</option>
                        <option value="America/Phoenix" ${s.timezone=='America/Phoenix'?'selected':''}>Arizona (no DST)</option>
                        <option value="America/Los_Angeles" ${s.timezone=='America/Los_Angeles'?'selected':''}>Pacific (PT)</option>
                        <option value="America/Anchorage" ${s.timezone=='America/Anchorage'?'selected':''}>Alaska (AKT)</option>
                        <option value="Pacific/Honolulu" ${s.timezone=='Pacific/Honolulu'?'selected':''}>Hawaii (HST)</option>
                        <option value="America/Toronto" ${s.timezone=='America/Toronto'?'selected':''}>Eastern Canada</option>
                        <option value="America/Edmonton" ${s.timezone=='America/Edmonton'?'selected':''}>Mountain Canada</option>
                        <option value="America/Vancouver" ${s.timezone=='America/Vancouver'?'selected':''}>Pacific Canada</option>
                        <option value="Europe/London" ${s.timezone=='Europe/London'?'selected':''}>UK (GMT/BST)</option>
                        <option value="Europe/Paris" ${s.timezone=='Europe/Paris'?'selected':''}>Central Europe (CET)</option>
                        <option value="Europe/Berlin" ${s.timezone=='Europe/Berlin'?'selected':''}>Germany (CET)</option>
                        <option value="Australia/Sydney" ${s.timezone=='Australia/Sydney'?'selected':''}>Australia Eastern</option>
                        <option value="Asia/Tokyo" ${s.timezone=='Asia/Tokyo'?'selected':''}>Japan (JST)</option>
                    </select></div>
            </div>

            <hr style="margin:1.25rem 0;border-color:var(--border)">
            <h3>🔑 API</h3>
            <div class="form-group"><label>Astrospheric API Key</label>
                <input type="password" id="s-apikey" value="${s.astrospheric_api_key || ''}" /></div>

            <hr style="margin:1.25rem 0;border-color:var(--border)">
            <h3>🔭 Imaging</h3>
            <h4 style="margin:0.5rem 0 0.25rem;font-size:0.85rem;color:var(--text-secondary)">Horizon Limits (degrees)</h4>
            <div class="horizon-grid">
                <div class="horizon-direction"><label>N</label><input type="number" id="s-hn" value="${s.horizon_north||30}" /><span>°</span></div>
                <div class="horizon-direction"><label>E</label><input type="number" id="s-he" value="${s.horizon_east||15}" /><span>°</span></div>
                <div class="horizon-direction"><label>S</label><input type="number" id="s-hs" value="${s.horizon_south||15}" /><span>°</span></div>
                <div class="horizon-direction"><label>W</label><input type="number" id="s-hw" value="${s.horizon_west||15}" /><span>°</span></div>
            </div>
            <div class="form-group" style="margin-top:0.75rem"><label>Stop imaging at</label>
                <select id="s-endhr">
                    <option value="0" ${s.imaging_end_hour==0?'selected':''}>Midnight</option>
                    <option value="1" ${s.imaging_end_hour==1?'selected':''}>1:00 AM</option>
                    <option value="2" ${s.imaging_end_hour==2?'selected':''}>2:00 AM</option>
                    <option value="3" ${s.imaging_end_hour==3?'selected':''}>3:00 AM</option>
                    <option value="4" ${s.imaging_end_hour==4?'selected':''}>4:00 AM</option>
                </select></div>
            <h4 style="margin:0.75rem 0 0.25rem;font-size:0.85rem;color:var(--text-secondary)">Target Preferences</h4>
            <p style="font-size:0.8rem;color:var(--text-secondary);margin-bottom:0.5rem">Select your preferred target types for recommendations.</p>
            <div class="checkbox-grid" id="s-prefs-grid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:0.3rem">
                ${[
                    ['Emission Nebula', '🌫️ Emission Nebulae'],
                    ['Planetary Nebula', '🔵 Planetary Nebulae'],
                    ['Reflection Nebula', '💎 Reflection Nebulae'],
                    ['Supernova Remnant', '💥 Supernova Remnants'],
                    ['Spiral Galaxy', '🌀 Spiral Galaxies'],
                    ['Galaxy Group', '🌌 Galaxy Groups'],
                    ['Globular Cluster', '⭐ Globular Clusters'],
                    ['Open Cluster', '✨ Open Clusters'],
                    ['Dark Nebula', '🌑 Dark Nebulae'],
                    ['Planet', '🪐 Planets'],
                    ['Moon', '🌙 Moon'],
                    ['Sun', '☀️ Sun'],
                ].map(([val, lbl]) => {
                    const chk = (s.preferred_targets || []).includes(val) ? 'checked' : '';
                    return '<label class="checkbox-card" style="margin:0;padding:0.35rem 0.5rem;font-size:0.82rem"><input type="checkbox" value="' + val + '" ' + chk + ' /><span>' + lbl + '</span></label>';
                }).join('')}
            </div>
            <button class="btn-primary" onclick="saveSettings()" style="margin-top:1rem">Save Settings</button>
            <span id="settings-status" style="margin-left:1rem;color:var(--go)"></span>
            <hr style="margin:1.5rem 0;border-color:var(--border)">
            <h3>💾 Backup & Restore</h3>
            <p style="font-size:0.8rem;color:var(--text-secondary);margin-bottom:0.5rem">Download a full backup of your settings, equipment, projects, and sessions. Restore from a previous backup to replace all current data.</p>
            <div style="display:flex;gap:0.5rem;flex-wrap:wrap;margin-top:0.5rem">
                <a href="/api/backup" class="btn-primary" style="text-decoration:none;text-align:center">⬇ Download Backup</a>
                <button class="btn-sm" onclick="document.getElementById('restore-file-input').click()" style="white-space:nowrap">⬆ Restore from Backup</button>
                <input type="file" id="restore-file-input" accept=".json" style="display:none" onchange="restoreBackup(this)" />
            </div>
            <span id="restore-status" style="display:block;margin-top:0.5rem;font-size:0.85rem"></span>
            <hr style="margin:1.5rem 0;border-color:var(--border)">
            <h3>Actions</h3>
            <button class="btn-sm" onclick="rerunSetup()" style="margin-top:0.5rem">🔄 Re-run Setup Wizard</button>
            <a href="/api/debug/raw-forecast" target="_blank" class="btn-sm" style="display:inline-block;margin-top:0.5rem;margin-left:0.5rem;text-decoration:none">🔍 Debug Forecast Data</a>
        </div>
        <div class="card" style="max-width:440px;align-self:start">
            <h3>🔔 Notifications</h3>
            <p style="font-size:0.8rem;color:var(--text-secondary);margin-bottom:0.75rem">Get alerted when conditions are good for imaging.</p>
            <div class="form-group">
                <label class="toggle-label" style="display:flex;align-items:center;gap:0.5rem;cursor:pointer">
                    <input type="checkbox" id="s-notify-enabled" ${s.notify_enabled ? 'checked' : ''} onchange="document.getElementById('s-notify-options').style.display=this.checked?'':'none'" />
                    <span>Enable notifications</span>
                </label>
            </div>
            <div id="s-notify-options" style="${s.notify_enabled ? '' : 'display:none'}">
                <div class="form-group"><label>Method</label>
                    <select id="s-notify-method" onchange="updateNotifyMethodUI()">
                        <option value="ntfy" ${(s.notify_method||'ntfy')==='ntfy'?'selected':''}>ntfy</option>
                        <option value="discord" ${s.notify_method==='discord'?'selected':''}>Discord Webhook</option>
                        <option value="webhook" ${s.notify_method==='webhook'?'selected':''}>Generic Webhook</option>
                    </select>
                </div>
                <div id="s-ntfy-config" style="${(s.notify_method||'ntfy')==='ntfy'?'':'display:none'}">
                    <div class="form-group"><label>ntfy Server</label>
                        <input type="text" id="s-ntfy-server" value="${s.notify_ntfy_server || 'https://ntfy.sh'}" /></div>
                    <div class="form-group"><label>ntfy Topic</label>
                        <input type="text" id="s-ntfy-topic" value="${s.notify_ntfy_topic || ''}" placeholder="astrodash-alerts" /></div>
                </div>
                <div id="s-discord-config" style="${s.notify_method==='discord'?'':'display:none'}">
                    <div class="form-group"><label>Discord Webhook URL</label>
                        <input type="text" id="s-discord-url" value="${s.notify_discord_url || ''}" placeholder="https://discord.com/api/webhooks/..." /></div>
                </div>
                <div id="s-webhook-config" style="${s.notify_method==='webhook'?'':'display:none'}">
                    <div class="form-group"><label>Generic Webhook URL</label>
                        <input type="text" id="s-webhook-url" value="${s.notify_webhook_url || ''}" placeholder="https://..." /></div>
                    <p style="font-size:0.75rem;color:var(--text-secondary);margin:-0.25rem 0 0.5rem">All variables are sent as JSON fields alongside the rendered message.</p>
                </div>
                <div class="form-group"><label>Alert when score ≥</label>
                    <div style="display:flex;align-items:center;gap:0.5rem">
                        <input type="range" id="s-notify-threshold" min="30" max="90" value="${s.notify_go_threshold || 70}" step="5"
                               oninput="document.getElementById('s-threshold-val').textContent=this.value+'%'" style="flex:1" />
                        <span id="s-threshold-val" style="min-width:3rem;text-align:right;font-weight:600">${s.notify_go_threshold || 70}%</span>
                    </div>
                </div>
                <div class="form-group" style="margin-top:0.25rem">
                    <label style="display:flex;align-items:center;gap:0.5rem;cursor:pointer" title="Send a single heads-up notification when conditions are below the GO threshold so you know not to bother tonight">
                        <input type="checkbox" id="s-notify-nogo" ${s.notify_nogo ? 'checked' : ''} />
                        <span>Also notify on NO-GO nights</span>
                    </label>
                    <p style="font-size:0.7rem;color:var(--text-secondary);margin:0.15rem 0 0 1.6rem">Single alert when below threshold — saves you from checking</p>
                </div>
                <h4 style="margin:0.75rem 0 0.25rem;font-size:0.85rem;color:var(--text-secondary)">Schedule</h4>
                <div class="form-row">
                    <div class="form-group">
                        <label title="Hours before astronomical dusk (sky fully dark, sun 18° below horizon) to send the first alert for the current imaging window">Hours before dark</label>
                        <input type="text" inputmode="numeric" pattern="[0-9]*" id="s-notify-hours-before" value="${s.notify_hours_before_dark || 6}"
                               oninput="this.value=this.value.replace(/[^0-9]/g,'')" />
                        <p style="font-size:0.7rem;color:var(--text-secondary);margin:0.2rem 0 0">Before astronomical dusk</p>
                    </div>
                    <div class="form-group">
                        <label title="How often to re-send the alert (in whole hours). Set to 24 for once per imaging window.">Repeat every (hours)</label>
                        <input type="text" inputmode="numeric" pattern="[0-9]*" id="s-notify-interval" value="${s.notify_interval_hours || 24}"
                               oninput="this.value=this.value.replace(/[^0-9]/g,'')" />
                        <p style="font-size:0.7rem;color:var(--text-secondary);margin:0.2rem 0 0">24 = once per imaging window</p>
                    </div>
                    <div class="form-group">
                        <label title="Don't send notifications before this hour (local time). Leave empty for no restriction.">Quiet until</label>
                        <select id="s-notify-quiet">
                            <option value="">No restriction</option>
                            ${[10,11,12,13,14,15,16].map(h => {
                                const label = h > 12 ? (h-12)+':00 PM' : h+':00 '+(h===12?'PM':'AM');
                                return '<option value="'+h+'" '+(s.notify_quiet_start===h?'selected':'')+'>'+label+'</option>';
                            }).join('')}
                        </select>
                        <p style="font-size:0.7rem;color:var(--text-secondary);margin:0.2rem 0 0">Suppress early alerts</p>
                    </div>
                </div>
                <hr style="margin:0.75rem 0;border-color:var(--border)">
                <div class="form-group">
                    <label style="display:flex;justify-content:space-between;align-items:center">
                        Message Template
                        <button class="btn-sm" onclick="resetNotifyTemplate()" style="font-size:0.7rem;padding:0.15rem 0.4rem">Reset to Default</button>
                    </label>
                    <textarea id="s-notify-template" rows="6" style="font-family:monospace;font-size:0.82rem;line-height:1.4;white-space:pre-wrap">${(s.notify_template || _defaultNotifyTemplate).replace(/</g,'&lt;')}</textarea>
                </div>
                <div style="margin-bottom:0.75rem">
                    <p style="font-size:0.75rem;color:var(--text-secondary);margin-bottom:0.4rem">Click a variable to insert it at cursor position:</p>
                    <div id="s-var-chips" style="display:flex;flex-wrap:wrap;gap:0.25rem"></div>
                </div>
            </div>
            <div style="display:flex;gap:0.5rem;margin-top:0.75rem">
                <button class="btn-primary" onclick="saveNotifications()" style="flex:1">Save</button>
                <button class="btn-sm" onclick="testNotification()" style="white-space:nowrap">📤 Test</button>
                <button class="btn-sm" onclick="previewNotifyTemplate()" style="white-space:nowrap">👁 Preview</button>
            </div>
            <span id="notify-status" style="display:block;margin-top:0.5rem;font-size:0.85rem"></span>
            <div id="notify-preview" style="display:none;margin-top:0.5rem;padding:0.6rem;background:var(--bg-secondary);border-radius:6px;font-size:0.82rem;white-space:pre-wrap;line-height:1.4;border:1px solid var(--border)"></div>
        </div>
    </div>`;

    // Build variable chips after DOM is ready
    buildNotifyVarChips();
}

async function saveSettings() {
    const prefs = [];
    document.querySelectorAll('#s-prefs-grid input[type=checkbox]:checked').forEach(cb => prefs.push(cb.value));
    const resp = await fetch('/api/settings', {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            location_name: document.getElementById('s-location').value,
            latitude: parseFloat(document.getElementById('s-lat').value) || null,
            longitude: parseFloat(document.getElementById('s-lon').value) || null,
            bortle_zone: parseInt(document.getElementById('s-bortle').value) || 5,
            timezone: document.getElementById('s-timezone').value,
            astrospheric_api_key: document.getElementById('s-apikey').value || null,
            horizon_north: parseInt(document.getElementById('s-hn').value) || 30,
            horizon_east: parseInt(document.getElementById('s-he').value) || 15,
            horizon_south: parseInt(document.getElementById('s-hs').value) || 15,
            horizon_west: parseInt(document.getElementById('s-hw').value) || 15,
            imaging_end_hour: parseInt(document.getElementById('s-endhr').value),
            preferred_targets: prefs,
        })
    });
    const status = document.getElementById('settings-status');
    if (resp.ok) {
        status.textContent = '✓ Saved! Forecast will refresh shortly.';
        status.style.color = 'var(--go)';
        setTimeout(() => { status.textContent = ''; }, 3000);
    } else {
        status.textContent = '✗ Save failed';
        status.style.color = 'var(--nogo)';
    }
}

// ─── Notification Helpers ───
const _defaultNotifyTemplate = "🔭 {verdict} for imaging tonight! Score: {score}/100\nFilter: {filter_recommendation} | Moon: {moon_illumination}% ({moon_phase})\nWindow: {imaging_window} ({imaging_hours}h)\nBest hour: {best_hour} (score {best_hour_score})\nBroadband: {broadband_verdict} | Narrowband: {narrowband_verdict}\nWatch out: {worst_issue}";

const _notifyVars = [
    {key: 'verdict', label: 'Verdict', example: 'GO / MAYBE / NO-GO'},
    {key: 'score', label: 'Score', example: '78'},
    {key: 'filter_recommendation', label: 'Filter Suggestion', example: 'L-Pro'},
    {key: 'moon_illumination', label: 'Moon Illumination %', example: '42'},
    {key: 'moon_phase', label: 'Moon Phase', example: 'Waxing Gibbous'},
    {key: 'imaging_hours', label: 'Imaging Hours', example: '6'},
    {key: 'imaging_window', label: 'Imaging Window', example: '8:30 PM → 2:00 AM'},
    {key: 'best_hour', label: 'Best Hour', example: '11:00 PM'},
    {key: 'best_hour_score', label: 'Best Hour Score', example: '92'},
    {key: 'worst_issue', label: 'Worst Issue', example: 'Clouds (35%)'},
    {key: 'broadband_verdict', label: 'Broadband Verdict', example: 'MAYBE'},
    {key: 'narrowband_verdict', label: 'Narrowband Verdict', example: 'GO'},
];

function buildNotifyVarChips() {
    const container = document.getElementById('s-var-chips');
    if (!container) return;
    container.innerHTML = '';
    _notifyVars.forEach(v => {
        const chip = document.createElement('button');
        chip.className = 'btn-sm';
        chip.style.cssText = 'font-size:0.72rem;padding:0.15rem 0.4rem;font-family:monospace;cursor:pointer';
        chip.textContent = '{' + v.key + '}';
        chip.title = v.label + ' — e.g. ' + v.example;
        chip.onclick = () => insertVarIntoTemplate(v.key);
        container.appendChild(chip);
    });
}

function insertVarIntoTemplate(varKey) {
    const ta = document.getElementById('s-notify-template');
    if (!ta) return;
    const start = ta.selectionStart;
    const end = ta.selectionEnd;
    const text = ta.value;
    const insert = '{' + varKey + '}';
    ta.value = text.substring(0, start) + insert + text.substring(end);
    ta.selectionStart = ta.selectionEnd = start + insert.length;
    ta.focus();
}

function resetNotifyTemplate() {
    const ta = document.getElementById('s-notify-template');
    if (ta) ta.value = _defaultNotifyTemplate;
}

function previewNotifyTemplate() {
    const ta = document.getElementById('s-notify-template');
    const preview = document.getElementById('notify-preview');
    if (!ta || !preview) return;
    // Render with sample data
    const sampleVars = {
        verdict: 'GO', score: '85', filter_recommendation: 'L-Pro',
        moon_illumination: '12', moon_phase: 'Waxing Crescent',
        imaging_hours: '6', imaging_window: '8:30 PM → 2:00 AM',
        best_hour: '11:00 PM', best_hour_score: '92',
        worst_issue: 'All clear', broadband_verdict: 'GO', narrowband_verdict: 'GO',
    };
    let rendered = ta.value || _defaultNotifyTemplate;
    for (const [k, v] of Object.entries(sampleVars)) {
        rendered = rendered.replaceAll('{' + k + '}', v);
    }
    preview.textContent = rendered;
    preview.style.display = preview.style.display === 'none' ? '' : 'none';
}

function updateNotifyMethodUI() {
    const method = document.getElementById('s-notify-method').value;
    document.getElementById('s-ntfy-config').style.display = method === 'ntfy' ? '' : 'none';
    document.getElementById('s-discord-config').style.display = method === 'discord' ? '' : 'none';
    document.getElementById('s-webhook-config').style.display = method === 'webhook' ? '' : 'none';
}

async function saveNotifications() {
    const resp = await fetch('/api/settings', {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            notify_enabled: document.getElementById('s-notify-enabled').checked,
            notify_method: document.getElementById('s-notify-method').value,
            notify_ntfy_server: document.getElementById('s-ntfy-server').value || null,
            notify_ntfy_topic: document.getElementById('s-ntfy-topic').value || null,
            notify_discord_url: document.getElementById('s-discord-url').value || null,
            notify_webhook_url: document.getElementById('s-webhook-url').value || null,
            notify_go_threshold: parseInt(document.getElementById('s-notify-threshold').value) || 70,
            notify_nogo: document.getElementById('s-notify-nogo').checked,
            notify_hours_before_dark: parseInt(document.getElementById('s-notify-hours-before').value) || 6,
            notify_interval_hours: parseInt(document.getElementById('s-notify-interval').value) || 24,
            notify_quiet_start: document.getElementById('s-notify-quiet').value ? parseInt(document.getElementById('s-notify-quiet').value) : null,
            notify_template: document.getElementById('s-notify-template').value || null,
        })
    });
    const status = document.getElementById('notify-status');
    if (resp.ok) {
        status.textContent = '✓ Notification settings saved.';
        status.style.color = 'var(--go)';
        setTimeout(() => { status.textContent = ''; }, 3000);
    } else {
        status.textContent = '✗ Save failed';
        status.style.color = 'var(--nogo)';
    }
}

async function testNotification() {
    const status = document.getElementById('notify-status');
    status.textContent = 'Sending test…';
    status.style.color = 'var(--text-secondary)';
    try {
        const resp = await fetch('/api/notifications/test', { method: 'POST' });
        const data = await resp.json();
        if (data.status === 'sent') {
            status.textContent = '✓ Test message sent! Check your device.';
            status.style.color = 'var(--go)';
        } else {
            status.textContent = '✗ ' + (data.error || 'Failed to send');
            status.style.color = 'var(--nogo)';
        }
    } catch (e) {
        status.textContent = '✗ Error: ' + e.message;
        status.style.color = 'var(--nogo)';
    }
    setTimeout(() => { status.textContent = ''; }, 5000);
}

async function restoreBackup(input) {
    const file = input.files[0];
    if (!file) return;
    const status = document.getElementById('restore-status');
    if (!confirm('⚠️ This will REPLACE all current data (settings, equipment, projects, and sessions) with the backup. This cannot be undone.\n\nContinue?')) {
        input.value = '';
        return;
    }
    status.textContent = 'Restoring…';
    status.style.color = 'var(--text-secondary)';
    try {
        const form = new FormData();
        form.append('file', file);
        const resp = await fetch('/api/restore', { method: 'POST', body: form });
        const data = await resp.json();
        if (resp.ok) {
            status.textContent = '✓ Restored! ' + (data.projects || 0) + ' projects, ' + (data.sessions || 0) + ' sessions. Reloading…';
            status.style.color = 'var(--go)';
            setTimeout(() => { window.location.reload(); }, 1500);
        } else {
            status.textContent = '✗ ' + (data.detail || 'Restore failed');
            status.style.color = 'var(--nogo)';
        }
    } catch (e) {
        status.textContent = '✗ Error: ' + e.message;
        status.style.color = 'var(--nogo)';
    }
    input.value = '';
}

async function rerunSetup() {
    if (!confirm('Re-run the setup wizard? Your existing data will be preserved.')) return;
    await fetch('/api/settings/reset-setup', { method: 'POST' });
    window.location.href = '/';
}

function showImportHelp() {
    openModal('Equipment Import Format', `
        <p>Import equipment in <strong>JSON</strong> or <strong>CSV</strong> format. Select the category in the dropdown before importing. Fields vary by category.</p>
        
        <h4 style="margin-top:1rem">Camera Fields</h4>
        <pre style="background:var(--bg);padding:0.75rem;border-radius:6px;font-size:0.75rem;overflow-x:auto">{
  "name": "ASI533MC Pro", "manufacturer": "ZWO",
  "sensor_model": "IMX533", "color_type": "Color (OSC)",
  "pixel_size_um": 3.76, "resolution_x": 3008, "resolution_y": 3008,
  "sensor_width_mm": 11.31, "sensor_height_mm": 11.31,
  "cooling": true, "cooling_delta_c": 35, "adc_bit": 14
}</pre>

        <h4 style="margin-top:0.75rem">Telescope Fields</h4>
        <pre style="background:var(--bg);padding:0.75rem;border-radius:6px;font-size:0.75rem;overflow-x:auto">{
  "name": "Zenithstar 81", "manufacturer": "William Optics",
  "telescope_type": "APO Refractor",
  "aperture_mm": 81, "focal_length_mm": 382, "focal_ratio": 4.7,
  "weight_kg": 2.3
}</pre>

        <h4 style="margin-top:0.75rem">Mount Fields</h4>
        <pre style="background:var(--bg);padding:0.75rem;border-radius:6px;font-size:0.75rem;overflow-x:auto">{
  "name": "EQ6-R Pro", "manufacturer": "Sky-Watcher",
  "mount_type": "GEM", "max_payload_kg": 20,
  "weight_kg": 17.3, "periodic_error_arcsec": 8, "goto": true
}</pre>

        <h4 style="margin-top:0.75rem">Filter Fields</h4>
        <pre style="background:var(--bg);padding:0.75rem;border-radius:6px;font-size:0.75rem;overflow-x:auto">{
  "name": "L-eXtreme", "manufacturer": "Optolong",
  "filter_type": "Dual-Band Narrowband",
  "bandpass": "Ha 7nm, OIII 7nm", "filter_size": "2\\"",
  "narrowband_friendly": true, "moonlight_resistant": true
}</pre>

        <h4 style="margin-top:0.75rem">Accessory Fields</h4>
        <pre style="background:var(--bg);padding:0.75rem;border-radius:6px;font-size:0.75rem;overflow-x:auto">{
  "name": "Flat6AIII", "manufacturer": "William Optics",
  "accessory_type": "Field Flattener",
  "back_focus_mm": 55, "magnification": 1.0
}</pre>

        <h4 style="margin-top:1rem">CSV Format</h4>
        <p style="font-size:0.85rem">Header row with field names, then data rows. Boolean values: True/False. Empty values left blank.</p>
        <pre style="background:var(--bg);padding:0.75rem;border-radius:6px;font-size:0.75rem;overflow-x:auto">name,manufacturer,telescope_type,aperture_mm,focal_length_mm,focal_ratio,weight_kg
Zenithstar 81,William Optics,APO Refractor,81,382,4.7,2.3</pre>

        <h4 style="margin-top:1rem">Download Templates</h4>
        <p style="font-size:0.85rem">Export an existing category to see the exact format with all available fields:</p>
        <div style="display:flex;gap:0.5rem;flex-wrap:wrap;margin-top:0.5rem">
            <a href="/api/equipment/cameras/export/json" class="btn-sm" style="text-decoration:none">📥 cameras.json</a>
            <a href="/api/equipment/telescopes/export/json" class="btn-sm" style="text-decoration:none">📥 telescopes.json</a>
            <a href="/api/equipment/mounts/export/json" class="btn-sm" style="text-decoration:none">📥 mounts.json</a>
            <a href="/api/equipment/filters/export/json" class="btn-sm" style="text-decoration:none">📥 filters.json</a>
            <a href="/api/equipment/accessories/export/json" class="btn-sm" style="text-decoration:none">📥 accessories.json</a>
        </div>
        <div style="display:flex;gap:0.5rem;flex-wrap:wrap;margin-top:0.35rem">
            <a href="/api/equipment/cameras/export/csv" class="btn-sm" style="text-decoration:none">📥 cameras.csv</a>
            <a href="/api/equipment/telescopes/export/csv" class="btn-sm" style="text-decoration:none">📥 telescopes.csv</a>
            <a href="/api/equipment/mounts/export/csv" class="btn-sm" style="text-decoration:none">📥 mounts.csv</a>
            <a href="/api/equipment/filters/export/csv" class="btn-sm" style="text-decoration:none">📥 filters.csv</a>
            <a href="/api/equipment/accessories/export/csv" class="btn-sm" style="text-decoration:none">📥 accessories.csv</a>
        </div>
    `);
}

// ─── Modal ───
function openModal(title, bodyHtml) {
    document.getElementById('modal-title').textContent = title;
    document.getElementById('modal-body').innerHTML = bodyHtml;
    document.getElementById('modal-overlay').classList.add('active');
    document.getElementById('modal').classList.add('active');
}
function closeModal() {
    document.getElementById('modal-overlay').classList.remove('active');
    document.getElementById('modal').classList.remove('active');
}

// ─── Init ───
document.addEventListener('DOMContentLoaded', () => {
    showTab('dashboard');
    loadDashboard();
    setInterval(loadDashboard, 300000);
});
