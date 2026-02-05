// --- SocketIO connection ---
const socket = io();

socket.on('connect', () => console.log('SocketIO connected'));
socket.on('disconnect', () => console.log('SocketIO disconnected'));

// --- DOM refs ---
const videoFeed = document.getElementById('videoFeed');
const videoOverlay = document.getElementById('videoOverlay');
const connectionStatus = document.getElementById('connectionStatus');
const riskBadge = document.getElementById('riskBadge');
const babyPosition = document.getElementById('babyPosition');
const babyInCrib = document.getElementById('babyInCrib');
const babyFace = document.getElementById('babyFace');
const babyDesc = document.getElementById('babyDesc');
const motionStatus = document.getElementById('motionStatus');
const motionMagnitude = document.getElementById('motionMagnitude');
const motionDesc = document.getElementById('motionDesc');
const audioCrying = document.getElementById('audioCrying');
const audioBreathing = document.getElementById('audioBreathing');
const audioRms = document.getElementById('audioRms');
const audioDesc = document.getElementById('audioDesc');
const audioLevelFill = document.getElementById('audioLevelFill');

// --- Video feed ---
setTimeout(() => {
    if (videoFeed.naturalWidth > 0) videoOverlay.classList.remove('visible');
}, 2000);
videoFeed.onload = () => videoOverlay.classList.remove('visible');
videoFeed.onerror = () => {
    videoOverlay.classList.add('visible');
    videoOverlay.innerHTML = '<span>Camera disconnected</span>';
    connectionStatus.classList.add('disconnected');
};

// --- Audio playback via WebSocket ---
let audioCtx = null;
let audioEnabled = false;
let nextPlayTime = 0;
const AUDIO_SR = 16000;

document.getElementById('audioToggleBtn').addEventListener('click', () => {
    const icon = document.getElementById('audioIcon');
    const btn = document.getElementById('audioToggleBtn');
    if (audioEnabled) {
        audioEnabled = false;
        if (audioCtx) { audioCtx.close(); audioCtx = null; }
        icon.innerHTML = '&#128266;';
        btn.classList.remove('active');
    } else {
        audioCtx = new AudioContext({ sampleRate: AUDIO_SR });
        audioEnabled = true;
        nextPlayTime = audioCtx.currentTime;
        icon.innerHTML = '&#128264;';
        btn.classList.add('active');
    }
});

socket.on('audio_data', (data) => {
    if (!audioEnabled || !audioCtx) return;
    try {
        const view = new DataView(data);
        const length = data.byteLength / 2;
        const float32 = new Float32Array(length);
        for (let i = 0; i < length; i++) {
            float32[i] = view.getInt16(i * 2, true) / 32768.0;
        }
        const buffer = audioCtx.createBuffer(1, length, AUDIO_SR);
        buffer.copyToChannel(float32, 0);
        const source = audioCtx.createBufferSource();
        source.buffer = buffer;
        source.connect(audioCtx.destination);
        const now = audioCtx.currentTime;
        if (nextPlayTime < now) nextPlayTime = now + 0.05;
        source.start(nextPlayTime);
        nextPlayTime += buffer.duration;
    } catch (e) {}
});

// --- Controls ---
document.getElementById('cameraSelect').addEventListener('change', async (e) => {
    const cameraId = parseInt(e.target.value);
    try {
        const resp = await fetch('/api/switch_camera', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ camera_id: cameraId }),
        });
        const data = await resp.json();
        if (data.success) videoFeed.src = '/video_feed?' + Date.now();
    } catch (err) { console.error('Camera switch failed:', err); }
});

document.getElementById('micSelect').addEventListener('change', async (e) => {
    const micId = parseInt(e.target.value);
    try {
        await fetch('/api/switch_microphone', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ microphone_id: micId }),
        });
    } catch (err) { console.error('Mic switch failed:', err); }
});

document.getElementById('testAlertBtn').addEventListener('click', async () => {
    const btn = document.getElementById('testAlertBtn');
    btn.disabled = true; btn.textContent = 'Sending...';
    try { await fetch('/api/test_alert', { method: 'POST' }); } catch (err) {}
    btn.disabled = false; btn.textContent = 'Test Alert';
});

document.getElementById('forceReportBtn').addEventListener('click', async () => {
    const btn = document.getElementById('forceReportBtn');
    btn.disabled = true; btn.textContent = 'Sending...';
    try { await fetch('/api/force_report', { method: 'POST' }); } catch (err) {}
    btn.disabled = false; btn.textContent = 'Status Report';
});

// --- Status polling ---
async function updateStatus() {
    try {
        const resp = await fetch('/api/status');
        const data = await resp.json();

        const baby = data.baby || {};
        const risk = baby.risk_level || 'safe';
        riskBadge.textContent = risk.toUpperCase();
        riskBadge.className = 'risk-badge ' + risk;
        babyPosition.textContent = `Position: ${baby.position || '--'}`;
        babyInCrib.textContent = `In crib: ${baby.in_crib !== undefined ? (baby.in_crib ? 'Yes' : 'No') : '--'}`;
        babyFace.textContent = `Face covered: ${baby.face_covered !== undefined ? (baby.face_covered ? 'YES' : 'No') : '--'}`;
        babyDesc.textContent = baby.description || '--';

        const babyCard = document.getElementById('babyCard');
        babyCard.className = 'status-card' + (risk === 'danger' ? ' card-danger' : risk === 'warning' ? ' card-warning' : '');

        const motion = data.motion || {};
        motionStatus.textContent = `Motion: ${motion.has_motion ? 'Yes' : 'No'}`;
        motionMagnitude.textContent = `Magnitude: ${motion.motion_magnitude ?? '--'}`;
        motionDesc.textContent = motion.description || '--';

        const audio = data.audio || {};
        audioCrying.textContent = `Crying: ${audio.is_crying ? 'YES' : 'No'}`;
        const brate = audio.breathing_rate ? ` (~${audio.breathing_rate} bpm)` : '';
        audioBreathing.textContent = `Breathing: ${audio.breathing_detected ? 'Detected' + brate : 'Not detected'}`;
        audioRms.textContent = `Level: ${audio.rms_level ?? '--'} | Centroid: ${audio.spectral_centroid ?? '--'}Hz`;
        audioDesc.textContent = audio.description || '--';

        // Audio level meter
        const rmsNorm = Math.min((audio.rms_level || 0) / 0.3, 1.0);
        audioLevelFill.style.width = (rmsNorm * 100) + '%';
        audioLevelFill.style.background = audio.is_crying ? '#ef4444' : rmsNorm > 0.5 ? '#f59e0b' : '#22c55e';

        connectionStatus.classList.remove('disconnected');
    } catch (err) {
        connectionStatus.classList.add('disconnected');
    }
}

// --- Tabs ---
document.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('click', () => {
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
        tab.classList.add('active');
        document.getElementById('tab-' + tab.dataset.tab).classList.add('active');
    });
});

function fmtTime(ts) {
    if (!ts) return '';
    return new Date(ts).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function riskDot(level) {
    const colors = { danger: '#ef4444', warning: '#f59e0b', safe: '#22c55e' };
    return `<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${colors[level]||'#71717a'};margin-right:4px"></span>`;
}

async function updateDiscordLog() {
    try {
        const rows = await (await fetch('/api/history/discord?limit=30')).json();
        const el = document.getElementById('discordLog');
        if (!rows.length) { el.innerHTML = '<div class="log-empty">No Discord messages yet</div>'; return; }
        el.innerHTML = rows.map(r => `
            <div class="log-item ${r.success ? '' : 'log-error'}">
                <span class="log-time">${fmtTime(r.timestamp)}</span>
                <span class="log-channel">${r.channel}</span>
                ${riskDot(r.risk_level)}
                <span class="log-title">${r.title || ''}</span>
                <span class="log-desc">${(r.description || '').substring(0, 80)}</span>
                ${r.has_image ? '<span class="log-badge">IMG</span>' : ''}
                ${!r.success ? '<span class="log-badge log-badge-err">FAIL</span>' : ''}
            </div>`).join('');
    } catch (e) {}
}

async function updateVisionLog() {
    try {
        const rows = await (await fetch('/api/history/vision?limit=30')).json();
        const el = document.getElementById('visionLog');
        if (!rows.length) { el.innerHTML = '<div class="log-empty">No vision data yet</div>'; return; }
        el.innerHTML = rows.map(r => `
            <div class="log-item">
                <span class="log-time">${fmtTime(r.timestamp)}</span>
                ${riskDot(r.risk_level)}
                <span class="log-badge">${r.position}</span>
                <span class="log-desc">${r.description || ''}</span>
                ${r.face_covered ? '<span class="log-badge log-badge-err">FACE COVERED</span>' : ''}
                ${!r.in_crib ? '<span class="log-badge log-badge-err">OUT OF CRIB</span>' : ''}
            </div>`).join('');
    } catch (e) {}
}

async function updateEventsLog() {
    try {
        const rows = await (await fetch('/api/history/events?limit=30')).json();
        const el = document.getElementById('eventsLog');
        if (!rows.length) { el.innerHTML = '<div class="log-empty">No events yet</div>'; return; }
        el.innerHTML = rows.map(r => {
            let desc = '';
            try { desc = r.data ? JSON.stringify(JSON.parse(r.data)).substring(0, 80) : ''; } catch(e) {}
            return `<div class="log-item">
                <span class="log-time">${fmtTime(r.timestamp)}</span>
                <span class="log-badge">${r.event_type}</span>
                <span class="log-severity log-severity-${r.severity}">${r.severity}</span>
                <span class="log-desc">${desc}</span>
            </div>`;
        }).join('');
    } catch (e) {}
}

async function updateStats() {
    try {
        const s = await (await fetch('/api/stats')).json();
        document.getElementById('statVision').textContent = s.vision_logs || 0;
        document.getElementById('statMotion').textContent = s.motion_logs || 0;
        document.getElementById('statAudio').textContent = s.audio_logs || 0;
        document.getElementById('statDiscord').textContent = s.discord_messages || 0;
        document.getElementById('statAlerts').textContent = s.alerts_count || 0;
        document.getElementById('statCries').textContent = s.cry_count || 0;
    } catch (e) {}
}

function updateAllLogs() {
    updateDiscordLog();
    updateVisionLog();
    updateEventsLog();
    updateStats();
}

setInterval(updateStatus, 3000);
setInterval(updateAllLogs, 5000);
updateStatus();
updateAllLogs();
