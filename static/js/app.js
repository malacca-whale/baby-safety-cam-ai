// Baby Safety Cam AI - Frontend JavaScript
// --- SocketIO connection ---
const socket = io();

socket.on('connect', () => {
    console.log('SocketIO connected');
    updateConnectionStatus(true);
});
socket.on('disconnect', () => {
    console.log('SocketIO disconnected');
    updateConnectionStatus(false);
});

function updateConnectionStatus(connected) {
    const el = document.getElementById('connectionStatus');
    const textEl = el?.querySelector('.status-text');
    if (connected) {
        el?.classList.remove('disconnected');
        if (textEl) textEl.textContent = '연결됨';
    } else {
        el?.classList.add('disconnected');
        if (textEl) textEl.textContent = '연결 끊김';
    }
}

// --- Korean timezone (KST, UTC+9) formatting ---
function toKST(ts) {
    if (!ts) return null;
    const d = new Date(ts);
    return new Date(d.toLocaleString('en-US', { timeZone: 'Asia/Seoul' }));
}

function fmtTime(ts) {
    if (!ts) return '--';
    const d = toKST(ts);
    if (!d) return '--';
    return d.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
}

function fmtDateTime(ts) {
    if (!ts) return '--';
    const d = toKST(ts);
    if (!d) return '--';
    const month = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    const hours = String(d.getHours()).padStart(2, '0');
    const mins = String(d.getMinutes()).padStart(2, '0');
    const secs = String(d.getSeconds()).padStart(2, '0');
    return `${month}/${day} ${hours}:${mins}:${secs}`;
}

function fmtClockTime() {
    const d = toKST(new Date().toISOString());
    if (!d) return '--:--:--';
    const hours = String(d.getHours()).padStart(2, '0');
    const mins = String(d.getMinutes()).padStart(2, '0');
    const secs = String(d.getSeconds()).padStart(2, '0');
    return `${hours}:${mins}:${secs}`;
}

// --- Real-time clock ---
function updateClock() {
    const clockEl = document.getElementById('clock');
    if (clockEl) {
        clockEl.textContent = fmtClockTime();
    }
}
setInterval(updateClock, 1000);
updateClock();

// --- Video feed ---
const videoFeed = document.getElementById('videoFeed');
const videoOverlay = document.getElementById('videoOverlay');

setTimeout(() => {
    if (videoFeed && videoFeed.naturalWidth > 0) {
        videoOverlay?.classList.remove('visible');
    }
}, 2000);

if (videoFeed) {
    videoFeed.onload = () => videoOverlay?.classList.remove('visible');
    videoFeed.onerror = () => {
        if (videoOverlay) {
            videoOverlay.classList.add('visible');
            videoOverlay.innerHTML = '<span>카메라 연결 끊김</span>';
        }
        updateConnectionStatus(false);
    };
}

// --- Audio playback via WebSocket ---
let audioCtx = null;
let audioEnabled = false;
let nextPlayTime = 0;
const AUDIO_SR = 16000;

const audioToggleBtn = document.getElementById('audioToggleBtn');
if (audioToggleBtn) {
    audioToggleBtn.addEventListener('click', () => {
        const icon = document.getElementById('audioIcon');
        if (audioEnabled) {
            audioEnabled = false;
            if (audioCtx) { audioCtx.close(); audioCtx = null; }
            if (icon) icon.innerHTML = '&#128266;';
            audioToggleBtn.classList.remove('active');
        } else {
            audioCtx = new AudioContext({ sampleRate: AUDIO_SR });
            audioEnabled = true;
            nextPlayTime = audioCtx.currentTime;
            if (icon) icon.innerHTML = '&#128264;';
            audioToggleBtn.classList.add('active');
        }
    });
}

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
const cameraSelect = document.getElementById('cameraSelect');
if (cameraSelect) {
    cameraSelect.addEventListener('change', async (e) => {
        const cameraId = parseInt(e.target.value);
        try {
            const resp = await fetch('/api/switch_camera', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ camera_id: cameraId }),
            });
            const data = await resp.json();
            if (data.success && videoFeed) videoFeed.src = '/video_feed?' + Date.now();
        } catch (err) { console.error('Camera switch failed:', err); }
    });
}

const micSelect = document.getElementById('micSelect');
if (micSelect) {
    micSelect.addEventListener('change', async (e) => {
        const micId = parseInt(e.target.value);
        try {
            await fetch('/api/switch_microphone', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ microphone_id: micId }),
            });
        } catch (err) { console.error('Mic switch failed:', err); }
    });
}

const testAlertBtn = document.getElementById('testAlertBtn');
if (testAlertBtn) {
    testAlertBtn.addEventListener('click', async () => {
        testAlertBtn.disabled = true;
        testAlertBtn.innerHTML = '<span>&#128276;</span> 전송 중...';
        try { await fetch('/api/test_alert', { method: 'POST' }); } catch (err) {}
        testAlertBtn.disabled = false;
        testAlertBtn.innerHTML = '<span>&#128276;</span> 테스트 알림';
    });
}

const forceReportBtn = document.getElementById('forceReportBtn');
if (forceReportBtn) {
    forceReportBtn.addEventListener('click', async () => {
        forceReportBtn.disabled = true;
        forceReportBtn.innerHTML = '<span>&#128172;</span> 전송 중...';
        try { await fetch('/api/force_report', { method: 'POST' }); } catch (err) {}
        forceReportBtn.disabled = false;
        forceReportBtn.innerHTML = '<span>&#128172;</span> 상태 보고';
    });
}

// --- Status polling ---
async function updateStatus() {
    try {
        const resp = await fetch('/api/status');
        const data = await resp.json();

        const baby = data.baby || {};
        const risk = baby.risk_level || 'safe';
        const riskKr = { safe: '안전', warning: '주의', danger: '위험' };

        // Risk badge
        const riskBadge = document.getElementById('riskBadge');
        if (riskBadge) {
            riskBadge.textContent = riskKr[risk] || risk.toUpperCase();
            riskBadge.className = 'risk-badge ' + risk;
        }

        // HUD risk indicator
        const hudRisk = document.getElementById('hudRisk');
        if (hudRisk) {
            const dot = hudRisk.querySelector('.risk-dot');
            const val = hudRisk.querySelector('.hud-value');
            if (dot) dot.className = 'risk-dot ' + risk;
            if (val) val.textContent = riskKr[risk] || risk;
        }

        // Baby status
        const posKr = { supine: '바로 누움', prone: '엎드림!', side: '옆으로', sitting: '앉음', unknown: '알 수 없음' };
        const babyPosition = document.getElementById('babyPosition');
        const babyInCrib = document.getElementById('babyInCrib');
        const babyFace = document.getElementById('babyFace');
        const babyDesc = document.getElementById('babyDesc');

        if (babyPosition) babyPosition.textContent = posKr[baby.position] || baby.position || '--';
        if (babyInCrib) babyInCrib.textContent = baby.in_crib !== undefined ? (baby.in_crib ? '예' : '아니오') : '--';
        if (babyFace) babyFace.textContent = baby.face_covered !== undefined ? (baby.face_covered ? '예!' : '아니오') : '--';

        const extras = [];
        if (baby.blanket_near_face) extras.push('이불이 얼굴 근처');
        if (baby.loose_objects) extras.push('위험 물체 있음');
        if (baby.eyes_open) extras.push('눈 뜸');
        if (!baby.baby_visible) extras.push('아기 안 보임');
        const extrasText = extras.length ? ` (${extras.join(', ')})` : '';
        if (babyDesc) babyDesc.textContent = (baby.description || 'AI 분석 대기 중...') + extrasText;

        // Baby card styling
        const babyCard = document.getElementById('babyCard');
        if (babyCard) {
            babyCard.className = 'status-card baby-card' +
                (risk === 'danger' ? ' card-danger' : risk === 'warning' ? ' card-warning' : '');
        }

        // Motion status
        const motion = data.motion || {};
        const motionStatus = document.getElementById('motionStatus');
        const motionMagnitude = document.getElementById('motionMagnitude');
        const motionDesc = document.getElementById('motionDesc');

        if (motionStatus) motionStatus.textContent = motion.has_motion ? '감지됨' : '없음';
        if (motionMagnitude) motionMagnitude.textContent = motion.motion_magnitude?.toFixed(2) ?? '--';
        if (motionDesc) motionDesc.textContent = motion.description || '움직임 분석 중...';

        // Audio status
        const audio = data.audio || {};
        const audioCrying = document.getElementById('audioCrying');
        const audioBreathing = document.getElementById('audioBreathing');
        const audioRms = document.getElementById('audioRms');
        const audioDesc = document.getElementById('audioDesc');

        if (audioCrying) audioCrying.textContent = audio.is_crying ? '감지됨!' : '없음';
        const brate = audio.breathing_rate ? ` (~${audio.breathing_rate.toFixed(0)} bpm)` : '';
        if (audioBreathing) audioBreathing.textContent = audio.breathing_detected ? '감지됨' + brate : '감지 안됨';
        if (audioRms) audioRms.textContent = `${audio.rms_level?.toFixed(3) ?? '--'}`;
        if (audioDesc) audioDesc.textContent = audio.description || '오디오 분석 중...';

        // Audio level meter
        const audioLevelFill = document.getElementById('audioLevelFill');
        if (audioLevelFill) {
            const rmsNorm = Math.min((audio.rms_level || 0) / 0.3, 1.0);
            audioLevelFill.style.width = (rmsNorm * 100) + '%';
            if (audio.is_crying) {
                audioLevelFill.style.background = 'linear-gradient(90deg, #ef4444, #dc2626)';
            } else if (rmsNorm > 0.5) {
                audioLevelFill.style.background = 'linear-gradient(90deg, #f59e0b, #d97706)';
            } else {
                audioLevelFill.style.background = 'linear-gradient(90deg, #22c55e, #16a34a)';
            }
        }

        // Update timestamps (KST)
        const lastVisionEl = document.getElementById('lastVisionUpdate');
        const lastMotionEl = document.getElementById('lastMotionUpdate');
        const lastAudioEl = document.getElementById('lastAudioUpdate');
        if (lastVisionEl) lastVisionEl.textContent = fmtDateTime(data.last_vision_update);
        if (lastMotionEl) lastMotionEl.textContent = fmtDateTime(data.last_motion_update);
        if (lastAudioEl) lastAudioEl.textContent = fmtDateTime(data.last_audio_update);

        // Update video timestamp HUD
        const videoTs = document.getElementById('videoTimestamp');
        if (videoTs) {
            const hudVal = videoTs.querySelector('.hud-value');
            if (hudVal) hudVal.textContent = fmtDateTime(new Date().toISOString());
        }

        updateConnectionStatus(true);
    } catch (err) {
        updateConnectionStatus(false);
    }
}

// --- Tabs ---
document.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('click', () => {
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
        tab.classList.add('active');
        document.getElementById('tab-' + tab.dataset.tab)?.classList.add('active');
    });
});

function riskDot(level) {
    const colors = { danger: '#ef4444', warning: '#f59e0b', safe: '#22c55e' };
    return `<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${colors[level]||'#64748b'};margin-right:6px"></span>`;
}

async function updateDiscordLog() {
    try {
        const rows = await (await fetch('/api/history/discord?limit=30')).json();
        const el = document.getElementById('discordLog');
        if (!el) return;
        if (!rows.length) {
            el.innerHTML = '<div class="log-empty">Discord 메시지가 아직 없습니다</div>';
            return;
        }
        el.innerHTML = rows.map(r => `
            <div class="log-item ${r.success ? '' : 'log-error'}">
                <span class="log-time">${fmtTime(r.timestamp)}</span>
                <span class="log-channel">${r.channel}</span>
                ${riskDot(r.risk_level)}
                <span class="log-title">${r.title || ''}</span>
                <span class="log-desc">${(r.description || '').substring(0, 60)}</span>
                ${r.has_image ? '<span class="log-badge">IMG</span>' : ''}
                ${!r.success ? '<span class="log-badge log-badge-err">FAIL</span>' : ''}
            </div>`).join('');
    } catch (e) {}
}

async function updateVisionLog() {
    try {
        const rows = await (await fetch('/api/history/vision?limit=30')).json();
        const el = document.getElementById('visionLog');
        if (!el) return;
        if (!rows.length) {
            el.innerHTML = '<div class="log-empty">AI 분석 데이터가 아직 없습니다</div>';
            return;
        }
        const posKr = { supine: '등', prone: '엎드림', side: '옆으로', sitting: '앉음', unknown: '?' };
        el.innerHTML = rows.map(r => `
            <div class="log-item">
                <span class="log-time">${fmtTime(r.timestamp)}</span>
                ${riskDot(r.risk_level)}
                <span class="log-badge">${posKr[r.position] || r.position}</span>
                <span class="log-desc">${r.description || ''}</span>
                ${r.face_covered ? '<span class="log-badge log-badge-err">얼굴</span>' : ''}
                ${!r.in_crib ? '<span class="log-badge log-badge-err">침대 밖</span>' : ''}
            </div>`).join('');
    } catch (e) {}
}

async function updateEventsLog() {
    try {
        const rows = await (await fetch('/api/history/events?limit=30')).json();
        const el = document.getElementById('eventsLog');
        if (!el) return;
        if (!rows.length) {
            el.innerHTML = '<div class="log-empty">이벤트가 아직 없습니다</div>';
            return;
        }
        el.innerHTML = rows.map(r => {
            let desc = '';
            try { desc = r.data ? JSON.stringify(JSON.parse(r.data)).substring(0, 60) : ''; } catch(e) {}
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
        const setVal = (id, val) => {
            const el = document.getElementById(id);
            if (el) el.textContent = val || 0;
        };
        setVal('statVision', s.vision_logs);
        setVal('statMotion', s.motion_logs);
        setVal('statAudio', s.audio_logs);
        setVal('statDiscord', s.discord_messages);
        setVal('statAlerts', s.alerts_count);
        setVal('statCries', s.cry_count);
    } catch (e) {}
}

function updateAllLogs() {
    updateDiscordLog();
    updateVisionLog();
    updateEventsLog();
    updateStats();
}

// Start polling
setInterval(updateStatus, 3000);
setInterval(updateAllLogs, 5000);
updateStatus();
updateAllLogs();

// --- Settings Section ---
const settingsSection = document.getElementById('settingsSection');
const settingsToggleBtn = document.getElementById('settingsToggleBtn');
const vlmPromptTextarea = document.getElementById('vlmPromptTextarea');
const aiCameraSelect = document.getElementById('aiCameraSelect');

if (settingsToggleBtn) {
    settingsToggleBtn.addEventListener('click', () => {
        const isHidden = settingsSection?.style.display === 'none';
        if (settingsSection) settingsSection.style.display = isHidden ? 'block' : 'none';
        settingsToggleBtn.innerHTML = isHidden ? '<span>&#9881;</span> 설정 닫기' : '<span>&#9881;</span> 설정';
        if (isHidden) loadSettings();
    });
}

async function loadSettings() {
    try {
        const config = await (await fetch('/api/config')).json();
        if (vlmPromptTextarea) vlmPromptTextarea.value = config.vlm_prompt || '';
        if (aiCameraSelect && config.ai_camera_id !== undefined) {
            aiCameraSelect.value = config.ai_camera_id;
        }
    } catch (e) {
        console.error('Failed to load settings:', e);
    }
}

const savePromptBtn = document.getElementById('savePromptBtn');
if (savePromptBtn) {
    savePromptBtn.addEventListener('click', async () => {
        const prompt = vlmPromptTextarea?.value.trim();
        if (!prompt) {
            alert('프롬프트를 입력해주세요.');
            return;
        }
        savePromptBtn.disabled = true;
        savePromptBtn.textContent = '저장 중...';
        try {
            const resp = await fetch('/api/config/vlm_prompt', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ value: prompt }),
            });
            alert(resp.ok ? '저장되었습니다.' : '저장 실패');
        } catch (e) {
            alert('저장 실패: ' + e);
        }
        savePromptBtn.disabled = false;
        savePromptBtn.textContent = '저장';
    });
}

const resetPromptBtn = document.getElementById('resetPromptBtn');
if (resetPromptBtn) {
    resetPromptBtn.addEventListener('click', async () => {
        resetPromptBtn.disabled = true;
        resetPromptBtn.textContent = '복원 중...';
        try {
            const defaultResp = await fetch('/api/config/vlm_prompt/default');
            const defaultData = await defaultResp.json();
            if (vlmPromptTextarea) vlmPromptTextarea.value = defaultData.value;
            await fetch('/api/config/vlm_prompt', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ value: defaultData.value }),
            });
            alert('기본값으로 복원되었습니다.');
        } catch (e) {
            alert('복원 실패: ' + e);
        }
        resetPromptBtn.disabled = false;
        resetPromptBtn.textContent = '기본값';
    });
}

const saveAiCameraBtn = document.getElementById('saveAiCameraBtn');
if (saveAiCameraBtn) {
    saveAiCameraBtn.addEventListener('click', async () => {
        const cameraId = parseInt(aiCameraSelect?.value);
        saveAiCameraBtn.disabled = true;
        saveAiCameraBtn.textContent = '저장 중...';
        try {
            const resp = await fetch('/api/switch_ai_camera', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ camera_id: cameraId }),
            });
            const data = await resp.json();
            alert(data.success ? 'AI 카메라가 설정되었습니다.' : 'AI 카메라 설정 실패');
        } catch (e) {
            alert('설정 실패: ' + e);
        }
        saveAiCameraBtn.disabled = false;
        saveAiCameraBtn.textContent = '저장';
    });
}
