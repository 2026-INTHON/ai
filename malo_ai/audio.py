import array
import asyncio
import math
import os
import re
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

import httpx
from fastapi import HTTPException

from .providers import reserve_quota
from .schemas import AudioMetrics

MAX_AUDIO_BYTES = 5 * 1024 * 1024
FORMATS = {".wav": "wav", ".mp3": "mp3", ".mp4": "mov", ".m4a": "mov", ".webm": "matroska", ".ogg": "ogg"}


def audio_metrics(pcm: list[int], sample_rate: int, text: str, pack: str) -> AudioMetrics:
    duration = len(pcm) / sample_rate
    frame_size = max(1, sample_rate // 50)
    rms = [math.sqrt(sum(x * x for x in pcm[i:i + frame_size]) / max(1, len(pcm[i:i + frame_size]))) for i in range(0, len(pcm), frame_size)]
    threshold = max(160, (sum(rms) / max(1, len(rms))) * 0.15)
    voiced = [value > threshold for value in rms]
    indexes = [i for i, value in enumerate(voiced) if value]
    active = voiced[indexes[0]:indexes[-1] + 1] if indexes else []
    pauses, run = 0, 0
    for value in active + [True]:
        if not value:
            run += 1
        else:
            pauses += int(run >= 20)  # 400ms of low volume; an estimate, not a psychological diagnosis.
            run = 0
    units = len(re.findall(r"[가-힣A-Za-z0-9]", text)) if pack == "ko" else len(re.findall(r"\b[\w']+\b", text))
    fillers = re.findall(r"(?<!\w)(?:음|어|저기|um|uh|erm)(?!\w)", text, re.I)
    return AudioMetrics(durationMs=round(duration * 1000), pauseCount=pauses,
        silenceRatio=round(1 - sum(voiced) / max(1, len(voiced)), 3), fillerCount=len(fillers),
        speed=round(units / max(duration / 60, 0.001), 1),
        speedUnit="characters_per_minute" if pack == "ko" else "words_per_minute",
        measurement="audio_rms_and_transcript")


async def transcribe(content: bytes, filename: str, pack: str):
    if not content or len(content) > MAX_AUDIO_BYTES:
        raise HTTPException(413, {"code": "AUDIO_TOO_LARGE", "message": "음성은 5MB 이하로 보내주세요.", "retryable": False})
    suffix = Path(filename or "audio.m4a").suffix.lower()
    if suffix not in FORMATS:
        raise HTTPException(415, {"code": "AUDIO_FORMAT_UNSUPPORTED", "message": "wav, mp3, m4a, mp4, webm, ogg 파일을 사용할 수 있어요.", "retryable": False})
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise HTTPException(503, {"code": "STT_NOT_CONFIGURED", "message": "STT API 설정이 필요해요.", "retryable": True})
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise HTTPException(503, {"code": "AUDIO_DECODER_UNAVAILABLE", "message": "음성 처리 도구를 준비하고 있어요.", "retryable": True})
    with tempfile.TemporaryDirectory(prefix="malo-audio-") as temporary:
        source, output = Path(temporary) / ("input" + suffix), Path(temporary) / "decoded.wav"
        source.write_bytes(content)
        try:
            await asyncio.to_thread(subprocess.run, [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-protocol_whitelist", "file,pipe", "-f", FORMATS[suffix], "-i", str(source), "-t", "61", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(output)], check=True, timeout=15, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            with wave.open(str(output), "rb") as reader:
                duration = reader.getnframes() / reader.getframerate()
                samples = array.array("h", reader.readframes(reader.getnframes()))
            if duration < 0.3 or duration > 60:
                raise HTTPException(422, {"code": "AUDIO_DURATION_INVALID", "message": "0.3초 이상, 60초 이하의 음성을 보내주세요.", "retryable": False})
        except (subprocess.SubprocessError, wave.Error, OSError) as exc:
            raise HTTPException(422, {"code": "AUDIO_INVALID", "message": "음성 파일을 읽지 못했어요. 다시 녹음해 주세요.", "retryable": True}) from exc
        reserve_quota("stt_minutes", duration / 60, float(os.getenv("MALO_STT_DAILY_MINUTES", "300")))
        try:
            async with httpx.AsyncClient(timeout=35) as client:
                response = await client.post("https://api.openai.com/v1/audio/transcriptions", headers={"Authorization": "Bearer " + key, "OpenAI-Project": os.getenv("OPENAI_PROJECT", "")},
                    data={"model": os.getenv("OPENAI_STT_MODEL", "gpt-transcribe"), "languages[]": pack}, files={"file": ("audio" + suffix, content)})
                response.raise_for_status()
            text = response.json().get("text", "").strip()
            if not text:
                raise HTTPException(422, {"code": "SPEECH_NOT_RECOGNIZED", "message": "말소리를 인식하지 못했어요. 체력 차감 없이 다시 말해 주세요.", "retryable": True})
            return {"text": text, "audioMetrics": audio_metrics(list(samples), 16000, text, pack).model_dump(), "provider": "openai", "editable": True}
        except httpx.HTTPError as exc:
            raise HTTPException(502, {"code": "STT_UNAVAILABLE", "message": "음성 인식에 연결하지 못했어요. 체력 차감 없이 다시 시도해 주세요.", "retryable": True}) from exc
