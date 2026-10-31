import hmac
import os
import re
from typing import Annotated

from dotenv import load_dotenv

load_dotenv()

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import APIKeyHeader

from . import audio, providers, images, chapters, realtime, subtitles, reports
from .schemas import Evaluation, EvaluationRequest, HintRequest, HintResult, ScenarioRequest, ScenarioResult, SynthesisRequest, SynthesisResult, TranscriptionResult, PersonaImageRequest, PersonaImageResult

app = FastAPI(title="Malo AI Pipeline", version="0.1.0", root_path=os.getenv("MALO_AI_ROOT_PATH", ""),
    description="내부 AI 서비스입니다. FE는 Backend API를 사용하세요. mock 평가, Lablup/OpenAI 평가, STT, Azure TTS를 제공합니다.")
service_header = APIKeyHeader(name="X-AI-Service-Token", auto_error=False)


def authorize(token: Annotated[str | None, Depends(service_header)]):
    expected = os.getenv("MALO_AI_SERVICE_TOKEN", "")
    if not expected:
        if os.getenv("MALO_ENV") == "production":
            raise HTTPException(503, {"code": "SERVICE_TOKEN_NOT_CONFIGURED", "message": "AI 서비스 인증 설정이 필요합니다.", "retryable": False})
        return
    if not token or not hmac.compare_digest(token, expected):
        raise HTTPException(401, {"code": "AI_UNAUTHORIZED", "message": "AI 서비스 토큰이 필요합니다.", "retryable": False})


@app.post('/v1/chapters/outline', dependencies=[Depends(authorize)], tags=['챕터 생성'])
async def chapter_outline(request: chapters.ChapterRequest):
    return await chapters.outline(request)


@app.post('/v1/chapters/lesson', dependencies=[Depends(authorize)], tags=['챕터 생성'])
async def chapter_lesson(request: chapters.LessonRequest):
    return await chapters.lesson(request)


class BackgroundRequest(chapters.Model):
    description: str = chapters.Field(min_length=2, max_length=400)


@app.post('/v1/chapters/background', dependencies=[Depends(authorize)], tags=['챕터 생성'])
async def chapter_background(request: BackgroundRequest):
    return await chapters.background(request.description)


@app.post('/v1/speech/realtime-session', dependencies=[Depends(authorize)], tags=['STT'])
async def realtime_session(request: realtime.Request):
    return await realtime.create(request)


@app.post('/v1/subtitles',dependencies=[Depends(authorize)],tags=['자막'])
async def translate_subtitles(request:subtitles.Request):
    return await subtitles.translate(request)


@app.post('/v1/reports/generate',dependencies=[Depends(authorize)],tags=['학습 보고서'])
async def learning_report(request:reports.ReportRequest):
    return await reports.generate(request)


@app.exception_handler(HTTPException)
async def http_error(_, error: HTTPException):
    detail = error.detail if isinstance(error.detail, dict) else {"code": "AI_ERROR", "message": str(error.detail), "retryable": error.status_code >= 500}
    return JSONResponse({"error": detail}, status_code=error.status_code)


@app.get("/health", tags=["상태"])
def health():
    return {"status": "ok", "service": "malo-ai", "version": "0.1.0", "capabilities": {
        "mock": True, "lablup": bool(os.getenv("LABLUP_API_KEY") and os.getenv("LABLUP_BASE_URL")),
        "openai": bool(os.getenv("OPENAI_API_KEY")), "azureTts": bool(os.getenv("AZURE_SPEECH_KEY")), "openaiImages": bool(os.getenv("OPENAI_API_KEY")),
    }}


@app.post("/v1/turns/evaluate", response_model=Evaluation, dependencies=[Depends(authorize)], tags=["대화 평가"])
async def evaluate(request: EvaluationRequest):
    grade, provider = await providers.evaluate(request)
    return {**grade.model_dump(), "provider": provider, "isMock": provider == "mock", "audioMetrics": request.audioMetrics}


@app.post("/v1/scenarios/generate", response_model=ScenarioResult, dependencies=[Depends(authorize)], tags=["장면 생성"])
async def scenario(request: ScenarioRequest):
    result, provider = await providers.generate_scenario(request)
    return {"scenario": result.model_dump(), "provider": provider, "isMock": provider == "mock"}


@app.post("/v1/hints", response_model=HintResult, dependencies=[Depends(authorize)], tags=["속마음 힌트"])
def hint(request: HintRequest):
    node = request.node
    return {"nodeId": node.id, "step": request.step,
        "clue": node.clue or [{"k": "주목 표현", "v": node.npcText}, {"k": "행동", "v": node.action}, {"k": "상황 단서", "v": node.goal}],
        "thought": node.hiddenThought if request.step == 2 else None,
        "tip": node.tip if request.step == 2 else None, "source": "fictional_character_goal"}


@app.post("/v1/speech/transcribe", response_model=TranscriptionResult, dependencies=[Depends(authorize)], tags=["STT"])
async def transcribe(file: Annotated[UploadFile, File()], pack: Annotated[str, Form()] = "ko"):
    if pack not in {"ko", "en"}:
        raise HTTPException(422, {"code": "PACK_INVALID", "message": "ko 또는 en 팩을 선택하세요.", "retryable": False})
    try:
        content = await file.read(audio.MAX_AUDIO_BYTES + 1)
        return await audio.transcribe(content, file.filename or "audio.m4a", pack)
    finally:
        await file.close()


@app.post("/v1/speech/synthesize", response_model=SynthesisResult, dependencies=[Depends(authorize)], tags=["TTS"])
async def synthesize(request: SynthesisRequest):
    return await providers.synthesize(request)


@app.get("/v1/audio/{asset_id}", dependencies=[Depends(authorize)], tags=["TTS"])
def get_audio(asset_id: str):
    if not re.fullmatch(r"a_[a-f0-9]{40}", asset_id):
        raise HTTPException(404, "Audio not found")
    path = providers.DATA_DIR / "audio" / (asset_id + ".mp3")
    if not path.is_file():
        raise HTTPException(404, "Audio not found")
    return FileResponse(path, media_type="audio/mpeg", headers={"Cache-Control": "private, max-age=86400"})


@app.get("/v1/persona-assets", dependencies=[Depends(authorize)], tags=["사전 생성 에셋"])
def assets():
    return images.catalog()


@app.get('/v1/character-variants',dependencies=[Depends(authorize)],tags=['사전 생성 에셋'])
def character_variants():
    return images.variants()


@app.post("/v1/images/personas/generate", response_model=PersonaImageResult, dependencies=[Depends(authorize)], tags=["이미지 생성"])
async def generate_persona(request: PersonaImageRequest):
    """운영자용. 고정 medium 품질, 기본 이미지에서 표정 편집, 캐시 적중 시 과금 없음. 최대 20회/일."""
    result = await images.generate(request)
    result.pop("requestHash", None)
    return result


@app.get("/v1/images/{asset_id}", dependencies=[Depends(authorize)], tags=["이미지 생성"])
def get_image(asset_id: str):
    path = images.image_path(asset_id)
    if not path.is_file():
        raise HTTPException(404, {"code": "IMAGE_NOT_FOUND", "message": "이미지를 찾지 못했어요.", "retryable": False})
    return FileResponse(path, media_type="image/webp", headers={"Cache-Control": "public, max-age=31536000, immutable"})
