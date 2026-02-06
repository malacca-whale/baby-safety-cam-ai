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
    videoOverlay.innerHTML = '<span>카메라 연결 끊김</span>';
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
    btn.disabled = true; btn.textContent = '전송 중...';
    try { await fetch('/api/test_alert', { method: 'POST' }); } catch (err) {}
    btn.disabled = false; btn.textContent = '테스트 알림';
});

document.getElementById('forceReportBtn').addEventListener('click', async () => {
    const btn = document.getElementById('forceReportBtn');
    btn.disabled = true; btn.textContent = '전송 중...';
    try { await fetch('/api/force_report', { method: 'POST' }); } catch (err) {}
    btn.disabled = false; btn.textContent = '상태 보고';
});

// --- Status polling ---
async function updateStatus() {
    try {
        const resp = await fetch('/api/status');
        const data = await resp.json();

        const baby = data.baby || {};
        const risk = baby.risk_level || 'safe';
        const riskKr = { safe: '안전', warning: '주의', danger: '위험' };
        riskBadge.textContent = riskKr[risk] || risk.toUpperCase();
        riskBadge.className = 'risk-badge ' + risk;
        const posKr = { supine: '등(안전)', prone: '엎드림(위험)', side: '옆으로', sitting: '앉음', unknown: '알 수 없음' };
        babyPosition.textContent = `자세: ${posKr[baby.position] || baby.position || '--'}`;
        babyInCrib.textContent = `침대 안: ${baby.in_crib !== undefined ? (baby.in_crib ? '예' : '아니오') : '--'}`;
        babyFace.textContent = `얼굴 가려짐: ${baby.face_covered !== undefined ? (baby.face_covered ? '예!' : '아니오') : '--'}`;
        const extras = [];
        if (baby.blanket_near_face) extras.push('이불이 얼굴 근처');
        if (baby.loose_objects) extras.push('위험 물체 있음');
        if (baby.eyes_open) extras.push('눈 뜸');
        if (!baby.baby_visible) extras.push('아기 안 보임');
        const extrasText = extras.length ? ` | ${extras.join(', ')}` : '';
        babyDesc.textContent = (baby.description || '--') + extrasText;

        const babyCard = document.getElementById('babyCard');
        babyCard.className = 'status-card' + (risk === 'danger' ? ' card-danger' : risk === 'warning' ? ' card-warning' : '');

        const motion = data.motion || {};
        motionStatus.textContent = `움직임: ${motion.has_motion ? '있음' : '없음'}`;
        motionMagnitude.textContent = `강도: ${motion.motion_magnitude ?? '--'}`;
        motionDesc.textContent = motion.description || '--';

        const audio = data.audio || {};
        audioCrying.textContent = `울음: ${audio.is_crying ? '감지됨!' : '없음'}`;
        const brate = audio.breathing_rate ? ` (~${audio.breathing_rate} bpm)` : '';
        audioBreathing.textContent = `호흡: ${audio.breathing_detected ? '감지됨' + brate : '감지 안됨'}`;
        audioRms.textContent = `레벨: ${audio.rms_level ?? '--'} | 스펙트럼: ${audio.spectral_centroid ?? '--'}Hz`;
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
        if (!rows.length) { el.innerHTML = '<div class="log-empty">디스코드 메시지가 아직 없습니다</div>'; return; }
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
        if (!rows.length) { el.innerHTML = '<div class="log-empty">영상 분석 데이터가 아직 없습니다</div>'; return; }
        const posKr = { supine: '등', prone: '엎드림', side: '옆으로', sitting: '앉음', unknown: '알 수 없음' };
        el.innerHTML = rows.map(r => `
            <div class="log-item">
                <span class="log-time">${fmtTime(r.timestamp)}</span>
                ${riskDot(r.risk_level)}
                <span class="log-badge">${posKr[r.position] || r.position}</span>
                <span class="log-desc">${r.description || ''}</span>
                ${r.face_covered ? '<span class="log-badge log-badge-err">얼굴 가려짐</span>' : ''}
                ${!r.in_crib ? '<span class="log-badge log-badge-err">침대 밖</span>' : ''}
            </div>`).join('');
    } catch (e) {}
}

async function updateEventsLog() {
    try {
        const rows = await (await fetch('/api/history/events?limit=30')).json();
        const el = document.getElementById('eventsLog');
        if (!rows.length) { el.innerHTML = '<div class="log-empty">이벤트가 아직 없습니다</div>'; return; }
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

// --- Settings Section ---
const settingsSection = document.getElementById('settingsSection');
const settingsToggleBtn = document.getElementById('settingsToggleBtn');
const vlmPromptTextarea = document.getElementById('vlmPromptTextarea');
const aiCameraSelect = document.getElementById('aiCameraSelect');

// Toggle settings visibility
settingsToggleBtn.addEventListener('click', () => {
    const isHidden = settingsSection.style.display === 'none';
    settingsSection.style.display = isHidden ? 'block' : 'none';
    settingsToggleBtn.textContent = isHidden ? '설정 닫기' : '설정';
    if (isHidden) loadSettings();
});

// Load settings from server
async function loadSettings() {
    try {
        const config = await (await fetch('/api/config')).json();
        vlmPromptTextarea.value = config.vlm_prompt || '';
        if (config.ai_camera_id !== undefined) {
            aiCameraSelect.value = config.ai_camera_id;
        }
    } catch (e) {
        console.error('Failed to load settings:', e);
    }
}

// Save VLM prompt
document.getElementById('savePromptBtn').addEventListener('click', async () => {
    const btn = document.getElementById('savePromptBtn');
    const prompt = vlmPromptTextarea.value.trim();
    if (!prompt) {
        alert('프롬프트를 입력해주세요.');
        return;
    }
    btn.disabled = true;
    btn.textContent = '저장 중...';
    try {
        const resp = await fetch('/api/config/vlm_prompt', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ value: prompt }),
        });
        if (resp.ok) {
            alert('프롬프트가 저장되었습니다. 다음 분석부터 적용됩니다.');
        } else {
            alert('저장 실패');
        }
    } catch (e) {
        alert('저장 실패: ' + e);
    }
    btn.disabled = false;
    btn.textContent = '프롬프트 저장';
});

// Reset VLM prompt to default
document.getElementById('resetPromptBtn').addEventListener('click', async () => {
    const btn = document.getElementById('resetPromptBtn');
    btn.disabled = true;
    btn.textContent = '복원 중...';
    try {
        const defaultResp = await fetch('/api/config/vlm_prompt/default');
        const defaultData = await defaultResp.json();
        vlmPromptTextarea.value = defaultData.value;

        await fetch('/api/config/vlm_prompt', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ value: defaultData.value }),
        });
        alert('기본 프롬프트로 복원되었습니다.');
    } catch (e) {
        alert('복원 실패: ' + e);
    }
    btn.disabled = false;
    btn.textContent = '기본값 복원';
});

// Save AI camera selection
document.getElementById('saveAiCameraBtn').addEventListener('click', async () => {
    const btn = document.getElementById('saveAiCameraBtn');
    const cameraId = parseInt(aiCameraSelect.value);
    btn.disabled = true;
    btn.textContent = '저장 중...';
    try {
        const resp = await fetch('/api/switch_ai_camera', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ camera_id: cameraId }),
        });
        const data = await resp.json();
        if (data.success) {
            alert(`AI 카메라가 Camera ${cameraId}로 설정되었습니다.`);
        } else {
            alert('AI 카메라 설정 실패');
        }
    } catch (e) {
        alert('설정 실패: ' + e);
    }
    btn.disabled = false;
    btn.textContent = '저장';
});
