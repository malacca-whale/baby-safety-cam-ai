# Baby AI Cam - Technical Blueprint

## 1. Project Overview

실시간 아기 모니터링 시스템으로, 비전 AI와 오디오 분석을 활용하여 아기의 안전을 감시하고 부모에게 즉각적인 알림을 제공합니다.

### Core Features
- 실시간 비디오/오디오 스트리밍 웹 인터페이스
- AI 기반 위험 상황 감지 (질식, 침대 이탈 등)
- 움직임 추적 및 자세 분석
- 아기 울음/숨소리 감지
- Discord를 통한 이중 채널 알림 시스템

---

## 2. Technology Stack

### 2.1 Core Framework
- **Language**: Python 3.11+
- **Package Manager**: uv
- **Web Framework**: Flask

### 2.2 AI/ML Models

#### Vision Model: Qwen3-VL
- **Model**: `qwen3-vl:8b` (Ollama)
- **Why**:
  - 256K context window (long video understanding)
  - Structured output 지원
  - 로컬 실행 가능 (16GB RAM 환경)
  - GUI 인식 및 spatial reasoning 우수
- **Use Cases**:
  - 아기 자세 분석
  - 얼굴 가림 감지
  - 침대 위치 추적
  - 위험 상황 판단

#### Audio Models

##### 1. Baby Cry Detection
- **Primary Model**: `foduucom/baby-cry-classification` (Hugging Face)
- **Backup Model**: `CAPYLEE/CRSTC` (Causal temporal representation)
- **Features**:
  - Pre-trained on baby cry datasets
  - Multi-class classification (배고픔, 통증, 불편함 등)
  - Real-time inference capability

##### 2. Breathing Sound Detection
- **Approach**: Custom audio feature extraction
- **Methods**:
  - Dynamic Linear Prediction Coefficients (DLPCs)
  - Spectral entropy analysis
  - Short-time magnitude/energy detection
- **Libraries**:
  - `librosa`: Audio feature extraction
  - `pyaudio`: Real-time audio capture
  - `scipy`: Signal processing

### 2.3 Computer Vision

#### Motion Detection: Optical Flow
- **Library**: OpenCV 4.x
- **Methods**:
  - **Dense Optical Flow** (Farneback): 전체 프레임 움직임 분석
  - **Sparse Optical Flow** (Lucas-Kanade): 특정 포인트 추적 (더 빠름)
- **Implementation**:
  - `cv2.calcOpticalFlowFarneback()` for dense flow
  - `cv2.calcOpticalFlowPyrLK()` for sparse flow
  - Shi-Tomasi corner detection for feature points

#### Video Streaming
- **Protocol**: MJPEG over HTTP
- **Alternative**: WebRTC (낮은 latency, 양방향 통신)
- **Frame Processing**:
  - 해상도: 640x480
  - FPS: 15-30

### 2.4 Integration & Communication
- **Discord**: `discord-webhook`
- **HTTP Client**: `httpx` (async HTTP requests)
- **WebSocket**: `python-socketio`

### 2.5 Dependencies
- flask>=3.0.3
- flask-socketio>=5.4.1
- opencv-python>=4.10.0
- numpy>=1.26.4
- torch>=2.4.0
- transformers>=4.46.0
- librosa>=0.10.2
- pyaudio>=0.2.14
- discord-webhook>=1.3.1
- httpx>=0.27.0
- pydantic>=2.9.0
- python-dotenv>=1.0.0

---

## 3. Core Components

### 3.1 Vision Analysis Module
- Qwen3-VL을 사용한 아기 상태 분석
- Structured output으로 안전 상태 분석
- Pydantic 스키마:
  - `face_covered`: bool
  - `position`: "supine" | "prone" | "side"
  - `in_crib`: bool
  - `risk_level`: "safe" | "warning" | "danger"
  - `description`: str

### 3.2 Audio Analysis Module
- 아기 울음 감지 (Hugging Face 모델)
- 호흡음 분석 (DLPC, spectral entropy)
- 4초 단위 청크 처리

### 3.3 Motion Detection Module
- OpenCV Optical Flow
- Lucas-Kanade sparse flow (기본)
- Farneback dense flow (옵션)
- 움직임 magnitude 계산

### 3.4 Alert Manager
- Discord 2채널 시스템
- 경고 채널: 위험 상황 즉시 알림
- 상태 채널: 5분마다 요약 보고
- 비동기 메시지 전송
- Retry 메커니즘

### 3.5 Web Streaming Server
- Flask 기반 웹 서버
- MJPEG 스트리밍 엔드포인트
- 복수 카메라/마이크 관리
- WebSocket을 통한 오디오 전송

---

## 4. Data Flow & Processing

### 4.1 처리 주기

| Component | Processing Rate | Reason |
|-----------|----------------|--------|
| Video Capture | 30 FPS | 부드러운 스트리밍 |
| Vision Analysis (Qwen3-VL) | 2 FPS | GPU/CPU 리소스 고려 |
| Optical Flow | 15 FPS | 실시간 움직임 감지 |
| Audio Analysis | 250ms 청크 | 울음 즉시 감지 |
| Status Report | 5분 | 요약 알림 |

### 4.2 비동기 처리 파이프라인
- Frame Queue (maxsize=30)
- Audio Queue (maxsize=20)
- Alert Queue
- Vision + Motion 병렬 처리
- asyncio 기반 이벤트 루프

---

## 5. Configuration

### 5.1 환경 변수 (.env)
```env
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=qwen3-vl:8b

DISCORD_WARNING_WEBHOOK=https://discord.com/api/webhooks/...
DISCORD_STATUS_WEBHOOK=https://discord.com/api/webhooks/...

CAMERA_ID=0
MICROPHONE_ID=0

VISION_FPS=2
MOTION_FPS=15
VIDEO_STREAM_FPS=30

STATUS_REPORT_INTERVAL=300  # 5 minutes
```

### 5.2 Ollama Setup
```bash
# Qwen3-VL 모델 다운로드
ollama pull qwen3-vl:8b

# 모델 테스트
ollama run qwen3-vl:8b "Describe this image" --image test.jpg
```

---

## 6. Implementation Phases

### Phase 1: 웹 UI 구축 (Week 1)
**목표**: 사용자가 볼 수 있는 웹 인터페이스 완성

- [ ] 프로젝트 구조 설정 (uv)
- [ ] Flask 웹 서버 기본 구조
- [ ] HTML/CSS/JS 프론트엔드 UI
  - 비디오 표시 영역
  - 오디오 플레이어 영역
  - 카메라/마이크 선택 드롭다운
  - 상태 표시 패널
- [ ] 반응형 디자인 (모바일 지원)
- [ ] 기본 라우팅 및 API 엔드포인트 설계

**Deliverable**: 작동하는 웹페이지 (데이터 없음, UI만)

---

### Phase 2: 이미지 전송 완성 (Week 2)
**목표**: 실시간 비디오 스트리밍 구현

- [ ] 카메라 디바이스 감지 및 관리
  - OpenCV VideoCapture 통합
  - 복수 카메라 자동 검색
  - 카메라 전환 기능
- [ ] MJPEG 스트리밍 구현
  - `/video_feed` 엔드포인트
  - 프레임 버퍼링 및 인코딩
  - FPS 조절 (30fps)
- [ ] 프론트엔드 비디오 표시
  - `<img>` 태그로 MJPEG 스트림 렌더링
  - 로딩 상태 표시
  - 연결 끊김 처리
- [ ] 성능 최적화
  - 해상도 설정 (640x480)
  - JPEG 품질 조절
  - 메모리 관리

**Deliverable**: 실시간 카메라 영상을 웹에서 볼 수 있음

---

### Phase 3: Discord Alert System (Week 3)
**목표**: Discord를 통한 알림 인프라 구축

- [ ] Discord webhook 설정
  - 경고 채널 webhook
  - 상태 보고 채널 webhook
  - .env 환경 변수 관리
- [ ] Alert Manager 구현
  - 비동기 메시지 전송
  - Retry 메커니즘
  - Rate limiting (Discord API 제한 고려)
- [ ] 이미지 첨부 기능
  - 현재 프레임 캡처
  - Discord에 이미지 업로드
- [ ] 테스트 알림 시스템
  - 수동 테스트 버튼
  - 주기적 테스트 알림 (헬스체크)
- [ ] 알림 포맷 디자인
  - Embed 메시지 템플릿
  - 시간 정보 포함
  - 심각도별 색상 코딩

**Deliverable**: Discord로 메시지와 이미지를 전송할 수 있음

---

### Phase 4: Ollama Vision 경고 시스템 (Week 4)
**목표**: AI 비전으로 위험 상황 자동 감지

- [ ] Ollama 설치 및 설정
  - Qwen3-VL 모델 다운로드
  - API 연동 테스트
- [ ] Vision Analyzer 구현
  - Structured output 스키마 정의 (Pydantic)
  - 안전 상태 분석 함수
  - 위험도 판단 로직
- [ ] 위험 상황 감지 로직
  - 얼굴 가림 감지
  - 뒤집힘 감지 (prone position)
  - 침대 이탈 감지
- [ ] Optical Flow 움직임 감지
  - Lucas-Kanade sparse flow
  - 움직임 magnitude 계산
  - 움직임 히스토리 추적
- [ ] Vision-Discord 통합
  - 위험 감지 시 즉시 경고 전송
  - 캡처 이미지와 분석 결과 포함
  - False positive 필터링
- [ ] 5분 요약 보고서
  - 상태 버퍼링 (5분간 데이터 수집)
  - 요약 생성 (평균 자세, 움직임 패턴)
  - 상태 채널로 전송

**Deliverable**: 카메라로 아기를 보고 위험 상황 자동 감지 및 Discord 알림

---

### Phase 5: 오디오 분석 추가 (Week 5)
**목표**: 울음 및 호흡음 감지 기능 추가

- [ ] 오디오 캡처 구현
  - PyAudio 통합
  - 마이크 디바이스 감지
  - 실시간 오디오 스트리밍 (WebSocket)
- [ ] 웹 오디오 재생
  - WebRTC 또는 WebSocket으로 오디오 전송
  - 브라우저에서 재생
  - 마이크 선택 기능
- [ ] Baby Cry Detection
  - Hugging Face 모델 다운로드
  - 4초 청크 처리
  - 울음 분류 (배고픔, 통증, 불편함 등)
- [ ] 호흡음 분석
  - Audio feature extraction (DLPC, spectral entropy)
  - 호흡 패턴 감지
  - 호흡률 추정
- [ ] Audio-Vision Fusion
  - 오디오와 비전 결과 결합
  - 통합 위험도 평가
  - 종합 알림 생성
- [ ] Discord 알림 업데이트
  - 오디오 이벤트 포함 (울음 감지, 호흡 이상)
  - 5분 요약에 오디오 정보 추가

**Deliverable**: 울음과 호흡음까지 감지하는 완전한 모니터링 시스템

---

### Phase 6: Testing & Optimization (Week 6)
**목표**: 안정성 및 성능 최적화

- [ ] 단위 테스트 작성
  - Vision analyzer 테스트
  - Audio analyzer 테스트
  - Alert manager 테스트
- [ ] 통합 테스트
  - End-to-end 파이프라인 테스트
  - Discord 전송 테스트
  - 멀티 디바이스 테스트
- [ ] 성능 최적화
  - CPU/메모리 프로파일링
  - Latency 측정 및 개선
  - 프레임 드롭 최소화
- [ ] 24시간 스트레스 테스트
  - 장시간 안정성 확인
  - 메모리 누수 체크
  - 자동 복구 메커니즘
- [ ] 문서화
  - 설치 가이드
  - 설정 가이드
  - 트러블슈팅 가이드
- [ ] 배포 준비
  - Docker 이미지 (선택)
  - Systemd 서비스 설정
  - 자동 시작 스크립트

**Deliverable**: 프로덕션 배포 가능한 안정적인 시스템

---

## 7. Key Technical Decisions

### 7.1 Why Qwen3-VL?
- ✅ 256K context: 긴 비디오 시퀀스 이해
- ✅ Structured output: JSON 직접 반환
- ✅ Local deployment: 프라이버시 보호
- ✅ Ollama 공식 지원

### 7.2 Why Flask?
- ✅ MJPEG streaming 간단
- ✅ SocketIO 통합 용이
- ✅ 간단한 배포

### 7.3 Sparse vs Dense Optical Flow?
- **Default: Sparse (Lucas-Kanade)** - 빠름, 실시간 적합
- **Dense (Farneback)** - 정확하지만 CPU 부하 높음

### 7.4 Audio Processing: 4-second chunks
- 아기 울음 감지에 최적
- 실시간성 유지
- 호흡음 패턴 분석에 충분

---

## 8. Risk Mitigation

### 8.1 Model Performance Issues
- **Risk**: Qwen3-VL이 느려서 real-time 불가
- **Mitigation**: 2 FPS로 분석 제한, Frame skipping

### 8.2 False Positives
- **Risk**: 과도한 false alarm
- **Mitigation**: 2회 연속 감지 후 알림, Confidence threshold

### 8.3 Network Latency
- **Risk**: Discord webhook 지연
- **Mitigation**: 비동기 전송, Retry 메커니즘

### 8.4 Privacy Concerns
- **Risk**: 데이터 유출
- **Mitigation**: 로컬 처리만, 프레임 메모리에만 저장

---

## 9. Testing Strategy

### 9.1 Unit Tests
- Vision analyzer 구조 테스트
- Audio analyzer 울음 감지 테스트
- Alert manager 전송 테스트

### 9.2 Integration Tests
- End-to-end pipeline test
- Discord webhook delivery test
- Multi-camera switching test

### 9.3 Performance Tests
- Latency measurement
- CPU/Memory profiling
- 24-hour continuous run test

---

## 10. Project Structure

```
baby-ai-cam/
├── pyproject.toml
├── .env
├── README.md
├── BLUEPRINT.md
├── PRD.md
│
├── src/
│   ├── main.py
│   ├── vision/
│   │   ├── analyzer.py
│   │   ├── motion.py
│   │   └── schemas.py
│   ├── audio/
│   │   ├── analyzer.py
│   │   ├── features.py
│   │   └── models.py
│   ├── alert/
│   │   ├── manager.py
│   │   ├── discord.py
│   │   └── summarizer.py
│   ├── streaming/
│   │   ├── server.py
│   │   ├── camera.py
│   │   └── audio_stream.py
│   ├── pipeline/
│   │   ├── processor.py
│   │   └── queues.py
│   └── utils/
│       ├── config.py
│       └── logging.py
│
├── templates/
│   └── index.html
├── static/
│   ├── css/
│   └── js/
├── tests/
└── scripts/
```

---

## 11. Quick Start

```bash
# 1. Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Setup project
cd baby-ai-cam
uv sync

# 3. Install Ollama
brew install ollama  # macOS
ollama pull qwen3-vl:8b

# 4. Configure
cp .env.example .env
# Edit .env with Discord webhooks

# 5. Run
uv run python src/main.py

# 6. Open browser
open http://localhost:5000
```

---

## 12. References

### AI Models
- [Qwen3-VL on Ollama](https://ollama.com/library/qwen3-vl)
- [Baby Cry Classification (Hugging Face)](https://huggingface.co/foduucom/baby-cry-classification)
- [CAPYLEE/CRSTC Cry Detection](https://huggingface.co/CAPYLEE/CRSTC)

### Technical Documentation
- [OpenCV Optical Flow Tutorial](https://docs.opencv.org/3.4/d4/dee/tutorial_optical_flow.html)
- [Flask Video Streaming Guide](https://cloudinary.com/guides/live-streaming-video/python-video-streaming)
- [Real-time Motion Detection](https://learnopencv.com/optical-flow-in-opencv/)

### Libraries
- [uv - Python Package Manager](https://github.com/astral-sh/uv)
- [librosa - Audio Analysis](https://librosa.org/)
- [Flask-SocketIO](https://flask-socketio.readthedocs.io/)

---

**Blueprint Version**: 1.0
**Last Updated**: 2026-02-06
