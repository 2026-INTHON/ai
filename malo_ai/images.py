"""Shared Malo characters: generate once, edit expressions from the base, serve from disk."""
import asyncio
import base64
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import httpx
from fastapi import HTTPException

from . import providers
from .schemas import PersonaImageRequest

MODEL = "gpt-image-2.5-flare"
QUALITY, SIZE = "medium", "1024x1536"
CHARACTERS = {
    "girlfriend": "Seoyun, a fictional adult Korean woman in her mid-twenties, long dark brown hair with a small pink flower hairclip, cream cardigan over a white top, sage green trousers, holding an iced coffee",
    "friend": "Minjun, a fictional adult Korean man in his mid-twenties, friendly short dark hair, dark knit beanie, navy casual sweater, beige trousers, canvas crossbody bag",
    "manager": "Han, a fictional Korean male office manager in his forties, neat short black hair, rectangular black glasses, charcoal suit, white shirt, slightly loose navy tie, employee lanyard, holding a takeaway coffee",
    "professor": "Professor Kim, a fictional Korean man in his fifties, neat salt-and-pepper hair, round glasses, warm brown jacket over a cream knit vest and light shirt, dark trousers, holding a closed book",
}
EXPRESSIONS = {
    "neutral": "a calm neutral attentive expression",
    "happy": "a warm pleased smile with naturally smiling eyes",
    "confused": "a subtly puzzled expression, slightly raised eyebrows, a gentle questioning look",
    "sad": "a mildly disappointed, wistful expression, still gentle and approachable",
    "angry": "a mildly annoyed expression with slightly furrowed eyebrows; restrained, never threatening",
}
# ponytail: A single Uvicorn worker serializes generation and manifest updates. Use a shared queue before scaling.
_lock = asyncio.Lock()


def _metadata_path(character: str, emotion: str) -> Path:
    return providers.DATA_DIR / "personas" / character / (emotion + ".json")


def _read_metadata(character: str, emotion: str):
    try:
        metadata = json.loads(_metadata_path(character, emotion).read_text(encoding="utf-8"))
        return metadata if image_path(metadata["assetId"]).is_file() else None
    except (FileNotFoundError, KeyError, ValueError):
        return None


def image_path(asset_id: str) -> Path:
    import re
    if not re.fullmatch(r"i_[a-f0-9]{40}", asset_id):
        raise HTTPException(404, {"code": "IMAGE_NOT_FOUND", "message": "이미지를 찾지 못했어요.", "retryable": False})
    return providers.DATA_DIR / "images" / (asset_id + ".webp")


def catalog():
    items = []
    for character in CHARACTERS:
        for emotion in EXPRESSIONS:
            metadata = _read_metadata(character, emotion)
            items.append({"characterId": character, "emotion": emotion, "assetKey": f"characters/{character}/{emotion}",
                "assetId": metadata["assetId"] if metadata else None, "imageUrl": None,
                "provider": "openai" if metadata else None, "source": "pre_generated"})
    return {"generation": "openai_api_cached", "runtimeImageApiCalls": False, "items": items}


def estimated_cost(usage: dict) -> float | None:
    """Standard USD estimate from the returned GPT Image 2.5 token usage; never invent missing usage."""
    details = usage.get("input_tokens_details", {})
    output = usage.get("output_tokens_details", {}).get("image_tokens", usage.get("output_tokens"))
    if output is None or "text_tokens" not in details or "image_tokens" not in details:
        return None
    return round((details["text_tokens"] * 5 + details["image_tokens"] * 8 + output * 30) / 1_000_000, 6)


async def _call_openai(prompt: str, character: str, reference: bytes | None):
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise HTTPException(503, {"code": "IMAGE_NOT_CONFIGURED", "message": "OpenAI 이미지 API 설정이 필요해요.", "retryable": False})
    # Reserve before every provider call, including attempts that fail; cached reads reserve nothing.
    providers.reserve_quota("image_generations", 1, int(os.getenv("MALO_IMAGE_DAILY_LIMIT", "20")))
    budget = int(float(os.getenv("MALO_IMAGE_DAILY_BUDGET_USD", "2")) * 1_000_000)
    providers.reserve_quota("image_budget_microusd", 100_000, budget)
    body = {"model": MODEL, "prompt": prompt, "quality": QUALITY, "size": SIZE, "n": 1,
        "output_format": "webp", "output_compression": 85, "background": "transparent",
        "safety_identifier": hashlib.sha256(("malo-shared-persona:" + character).encode()).hexdigest()}
    path = "generations"
    if reference:
        path = "edits"
        body["images"] = [{"image_url": "data:image/webp;base64," + base64.b64encode(reference).decode()}]
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(180, connect=10)) as client:
            response = await client.post("https://api.openai.com/v1/images/" + path,
                headers={"Authorization": "Bearer " + key, "OpenAI-Project": os.getenv("OPENAI_PROJECT", "")}, json=body)
        if response.status_code in (401, 403):
            raise HTTPException(503, {"code": "IMAGE_ACCESS_REQUIRED", "message": "이미지 API 사용 권한 또는 조직 인증을 확인해 주세요.", "retryable": False})
        if response.status_code == 429:
            raise HTTPException(429, {"code": "IMAGE_PROVIDER_LIMIT", "message": "이미지 API 사용량 또는 크레딧을 확인해 주세요.", "retryable": True})
        response.raise_for_status()
        result = response.json()
        encoded = result["data"][0]["b64_json"]
        if len(encoded) > 40 * 1024 * 1024:
            raise ValueError("Image exceeds cache limit")
        content = base64.b64decode(encoded, validate=True)
        if not (content[:4] == b"RIFF" and content[8:12] == b"WEBP"):
            raise ValueError("Expected WebP output")
        usage = result.get("usage") or {}
        cost = estimated_cost(usage)
        # Account for any excess over the conservative $0.10 reservation before accepting another call.
        if cost is not None and cost > 0.10:
            providers.reserve_quota("image_budget_microusd", round((cost - 0.10) * 1_000_000), 1e15)
        return content, usage, cost
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
        raise HTTPException(502, {"code": "IMAGE_UNAVAILABLE", "message": "이미지 생성에 실패했어요. 기존 이미지는 계속 사용할 수 있어요.", "retryable": True}) from exc


async def _generate(character: str, emotion: str, reference: bytes | None):
    if reference:
        prompt = ("Edit this exact Malo character portrait. Preserve the same adult person's identity, face shape, hair, clothing, accessories, "
            "body proportions, pose, framing, colors and rendering style. Change ONLY the facial expression to " + EXPRESSIONS[emotion] + ". "
            "Keep the full head and the same body visible, clean edges and transparent background. No text, logos or additional people.")
    else:
        prompt = ("Create one premium 3D chibi character asset for Malo, a friendly mobile conversation practice game. "
            "Original fictional adult character: " + CHARACTERS[character] + ". Expression: " + EXPRESSIONS[emotion] + ". "
            "Stylized collectible figurine with a slightly oversized head, expressive eyes, soft tactile fabric, polished anime-inspired "
            "3D rendering, contemporary Korean everyday styling, soft studio light, friendly and slightly playful. "
            "Single character centered, front three-quarter view facing the viewer, full head and body within frame, generous transparent "
            "margins, crisp silhouette. Transparent background. No room, ground, speech bubbles, text, logos or UI. Never photorealistic.")
    digest = hashlib.sha256(json.dumps(["malo-chibi-v1", MODEL, QUALITY, SIZE, prompt,
        hashlib.sha256(reference).hexdigest() if reference else None], ensure_ascii=False).encode()).hexdigest()
    cached = _read_metadata(character, emotion)
    if cached and cached.get("requestHash") == digest:
        return {**cached, "cached": True}
    content, usage, cost = await _call_openai(prompt, character, reference)
    asset_id = "i_" + hashlib.sha256(content).hexdigest()[:40]
    path = image_path(asset_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    temporary.write_bytes(content)
    temporary.replace(path)
    metadata = {"assetKey": f"characters/{character}/{emotion}", "assetId": asset_id, "characterId": character, "emotion": emotion,
        "model": MODEL, "quality": QUALITY, "size": SIZE, "mimeType": "image/webp", "provider": "openai", "isMock": False,
        "usage": usage, "estimatedCostUsd": cost, "createdAt": datetime.now(timezone.utc).isoformat(), "requestHash": digest,
        "referenceAssetId": "i_" + hashlib.sha256(reference).hexdigest()[:40] if reference else None}
    destination = _metadata_path(character, emotion)
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.with_name(destination.name + "." + uuid4().hex + ".tmp")
    staging.write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
    staging.replace(destination)
    return {**metadata, "cached": False}


async def generate(request: PersonaImageRequest):
    async with _lock:
        base = await _generate(request.characterId, "neutral", None)
        if request.emotion == "neutral":
            return base
        return await _generate(request.characterId, request.emotion, image_path(base["assetId"]).read_bytes())
