# Malo AI Pipeline

Malo Backend가 호출하는 내부 FastAPI 서비스입니다. FE는 Backend API만 사용합니다.

**[배포 AI 문서](https://inthon-demo-20261031-dh.koreacentral.cloudapp.azure.com/ai/docs)** · [백엔드](https://github.com/2026-INTHON/backend)

## 파이프라인

```mermaid
flowchart LR
  A[Expo 녹음] --> B[Backend]
  B --> C[ffmpeg 검증·PCM 측정]
  C --> D[OpenAI STT]
  D --> E[인식 문장 확인·수정]
  E --> F[대화 평가]
  F --> G[Lablup 우선]
  G -->|미설정·오류| H[OpenAI fallback]
  G --> I[Pydantic JSON 검증]
  H --> I
  I --> J[Backend 상태·체력·오답·보상]
  J --> K[Azure Speech TTS·캐시]
```

| API | 역할 |
|---|---|
| `POST /v1/turns/evaluate` | 문맥·목표·성격을 바탕으로 대화 평가. mock/live |
| `POST /v1/scenarios/generate` | seed 기반 3개 노드 장면 생성, 연결 그래프 검증 |
| `POST /v1/hints` | 미리 정의된 가상 캐릭터의 걱정/목표·학습 힌트 |
| `POST /v1/speech/transcribe` | 파일 검증 → STT → 수정 가능한 문장 + 음성 지표 |
| `POST /v1/speech/synthesize` | Azure TTS, 텍스트·목소리·감정·속도별 캐시 |
| `GET /v1/audio/{asset_id}` | 내부 음성 파일. Backend가 임시 서명 URL로 중계 |
| `GET /v1/persona-assets` | 사전 생성 이미지 assetKey. 이미지 자체는 아직 미등록 |
| `GET /health` | 키 값 없이 준비된 기능 여부만 공개 |

## 비용과 동작

- Mock은 단순 규칙이며 API 비용 0원입니다. Mock 자유 입력 채점은 실제 학습 품질을 대표하지 않습니다.
- `LABLUP_BASE_URL`, `LABLUP_API_KEY`가 있으면 Lablup OpenAI 호환 Chat Completions를 먼저 호출합니다. 현재 Lablup 키는 미설정이며 실제 호출 테스트는 남아 있습니다.
- Lablup 미설정/연결·JSON 실패 시 `OPENAI_FALLBACK_MODEL=gpt-6-luna` Responses API를 한 번 호출합니다. Pydantic 검증 실패/제공자 오류는 재시도 오류이며 틀린 답으로 처리하지 않습니다.
- STT는 `gpt-transcribe`, TTS는 Azure Speech F0입니다. 이미지 생성은 런타임에 호출하지 않고 사전 생성 파일을 연결합니다.
- 기본 일일 한도(KST)는 LLM 1000건, STT 300분, TTS 20만 자입니다. 실제 청구 상한 보장은 아니며 계정의 다른 사용량은 포함하지 않습니다. 제공자 요청 실패도 보수적으로 예약 사용량에 포함됩니다.
- TTS는 캐시, 약 3.1초 요청 간격(20회/분 수준)으로 F0 요청 한도를 배려합니다. 단일 worker 기준입니다. F0 월 50만 자 한도를 다른 앱과 공유하므로 장기 사용 시 콘솔을 확인하세요.
- 한국어는 여자친구 SunHi, 나머지 InJoon. 영어는 Jenny. 영어 지원 감정 스타일만 사용하고 한국어 감정 음성 스타일은 가정하지 않습니다.
- 톤은 **텍스트의 공손함**, 속도는 문자/단어 수 ÷ 녹음 길이, 멈춤은 PCM 낮은 음량 구간의 추정입니다. 감정 진단·발음 정확도 평가는 아닙니다. text/choice는 음성 지표가 없습니다.
- LLM은 상태/체력/재화를 결정하지 않습니다. Backend만 결정합니다. 가상 '속마음'은 캐릭터 설정으로 모델의 내부 추론을 노출하지 않습니다.

## 실행

Python 3.12+와 ffmpeg가 필요합니다. Docker에는 ffmpeg가 포함됩니다.

```sh
python -m venv .venv
# Windows: .venv\Scripts\activate / macOS·Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn malo_ai.main:app --host 127.0.0.1 --port 8000
```

Swagger `http://localhost:8000/docs`. `MALO_AI_SERVICE_TOKEN`을 Backend와 동일하게 설정하고 `X-AI-Service-Token` 헤더로 전달합니다. production은 토큰 누락 시 호출을 거부합니다. 공개 데모의 서비스 토큰을 FE에 배포하지 마세요.

```sh
python -m unittest discover -s tests -v
python scripts/export_openapi.py
```

## 확장 전 남은 것

Google OAuth 설정은 Backend 인수인계 참조. Lablup 실제 endpoint/key 연결, 캐릭터 표정별 이미지 업로드, TTS 음색/인격별 프롬프트 품질 조정은 팀 작업입니다. 모델이 반환한 가상 평가를 실제 사람의 성격이나 능력 판단으로 쓰지 않습니다.

해커톤 범위에서는 한 VM/한 Uvicorn worker, SQLite 사용량 장부와 파일 캐시를 사용합니다. 여러 worker/서버로 확장할 때 공유 큐·캐시·사용량 제한을 도입하세요. 현재 업로드 원본은 요청이 끝나면 임시 디렉터리에서 지우며, 변환된 TTS 파일만 캐시합니다.
