const videoFeed = document.getElementById('videoFeed');
const videoOverlay = document.getElementById('videoOverlay');
const connectionStatus = document.getElementById('connectionStatus');

// Status elements
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
const audioDesc = document.getElementById('audioDesc');

// Video feed error handling
videoFeed.onload = () => {
    videoOverlay.classList.remove('visible');
};

videoFeed.onerror = () => {
    videoOverlay.classList.add('visible');
    videoOverlay.innerHTML = '<span>Camera disconnected</span>';
    connectionStatus.classList.add('disconnected');
    connectionStatus.querySelector('span:last-child') || connectionStatus.append(' Disconnected');
};

// Camera switch
document.getElementById('cameraSelect').addEventListener('change', async (e) => {
    const cameraId = parseInt(e.target.value);
    try {
        const resp = await fetch('/api/switch_camera', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ camera_id: cameraId }),
        });
        const data = await resp.json();
        if (data.success) {
            // Reload video feed
            videoFeed.src = '/video_feed?' + Date.now();
        }
    } catch (err) {
        console.error('Camera switch failed:', err);
    }
});

// Microphone switch
document.getElementById('micSelect').addEventListener('change', async (e) => {
    const micId = parseInt(e.target.value);
    try {
        await fetch('/api/switch_microphone', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ microphone_id: micId }),
        });
    } catch (err) {
        console.error('Mic switch failed:', err);
    }
});

// Test alert
document.getElementById('testAlertBtn').addEventListener('click', async () => {
    const btn = document.getElementById('testAlertBtn');
    btn.disabled = true;
    btn.textContent = 'Sending...';
    try {
        await fetch('/api/test_alert', { method: 'POST' });
    } catch (err) {
        console.error('Test alert failed:', err);
    }
    btn.disabled = false;
    btn.textContent = 'Test Discord Alert';
});

// Force report
document.getElementById('forceReportBtn').addEventListener('click', async () => {
    const btn = document.getElementById('forceReportBtn');
    btn.disabled = true;
    btn.textContent = 'Sending...';
    try {
        await fetch('/api/force_report', { method: 'POST' });
    } catch (err) {
        console.error('Force report failed:', err);
    }
    btn.disabled = false;
    btn.textContent = 'Send Status Report';
});

// Poll status
async function updateStatus() {
    try {
        const resp = await fetch('/api/status');
        const data = await resp.json();

        // Baby status
        const baby = data.baby || {};
        const risk = baby.risk_level || 'safe';
        riskBadge.textContent = risk.toUpperCase();
        riskBadge.className = 'risk-badge ' + risk;
        babyPosition.textContent = `Position: ${baby.position || '--'}`;
        babyInCrib.textContent = `In crib: ${baby.in_crib !== undefined ? (baby.in_crib ? 'Yes' : 'No') : '--'}`;
        babyFace.textContent = `Face covered: ${baby.face_covered !== undefined ? (baby.face_covered ? 'YES ⚠️' : 'No') : '--'}`;
        babyDesc.textContent = baby.description || '--';

        // Update card border color
        const babyCard = document.getElementById('babyCard');
        babyCard.style.borderColor = risk === 'danger' ? '#ef4444' : risk === 'warning' ? '#f59e0b' : '#27272a';

        // Motion status
        const motion = data.motion || {};
        motionStatus.textContent = `Motion: ${motion.has_motion ? 'Yes' : 'No'}`;
        motionMagnitude.textContent = `Magnitude: ${motion.motion_magnitude ?? '--'}`;
        motionDesc.textContent = motion.description || '--';

        // Audio status
        const audio = data.audio || {};
        audioCrying.textContent = `Crying: ${audio.is_crying ? 'YES 🔴' : 'No'}`;
        audioBreathing.textContent = `Breathing: ${audio.breathing_detected ? 'Detected' : 'Not detected'}`;
        audioDesc.textContent = audio.description || '--';

        connectionStatus.classList.remove('disconnected');
    } catch (err) {
        connectionStatus.classList.add('disconnected');
    }
}

// Update status every 3 seconds
setInterval(updateStatus, 3000);
updateStatus();
