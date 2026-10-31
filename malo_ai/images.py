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
from .schemas import Model,Emotion,Gesture
from pydantic import Field

MODEL = "gpt-image-2.5-flare"
QUALITY, SIZE = "medium", "1024x1536"
CHARACTERS = {
    "girlfriend": "Seoyun, a stylish Korean woman in her mid-20s, long dark brown hair as chunky faceted strands with a small understated flower hairclip, small slightly half-lidded eyes, composed knowing expression; cropped textured ivory cardigan over a white top, high-waisted olive cargo trousers, black belt with a small silver key charm, understated silver earrings and low-profile sneakers; holding an iced latte, the other hand in a pocket",
    "friend": "a laid-back young Korean guy in his 20s, the user's close friend, messy two-block haircut in chestnut brown as chunky faceted strands, a small silver earring, playful lopsided grin, oversized washed blue hoodie under an open olive green varsity jacket, loose grey sweatpants, chunky black and white sneakers, one hand waving casually and the other holding a smartphone, a canvas tote bag on one shoulder",
    "manager": "Han, a Korean male office manager in his late 30s to early 40s, tousled angular black hair, narrow rectangular black glasses, small tired eyes and a dry reserved expression; slightly oversized charcoal blazer, crisp white shirt with loosened collar, relaxed navy tie, pleated wide charcoal trousers, black leather loafers, plain employee lanyard, a small silver key clip at the waist and a simple wristwatch; takeaway coffee in one hand, the other hand in a pocket; understated contemporary office streetwear",
    "professor": "a Korean university professor in her 50s, short silver-grey bob haircut as chunky faceted strands, round tortoiseshell glasses, calm but sharp knowing look, a long camel trench coat over a cream turtleneck, wide navy trousers, brown leather loafers, holding a thick book and a red pen against her chest",
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


class Variant(Model):
    characterId: str
    emotion: Emotion
    gesture: Gesture
    assetId: str=Field(pattern=r'^i_[a-f0-9]{40}$')


def variants():
    items=[{**item,'gesture':'idle'} for item in catalog()['items']]
    seen={item['assetKey'] for item in items}
    path=providers.DATA_DIR/'character-variants.json'
    if path.is_file():
        try:
            for value in json.loads(path.read_text(encoding='utf-8')):
                v=Variant.model_validate(value)
                if v.characterId not in CHARACTERS or v.gesture=='idle' or not image_path(v.assetId).is_file():
                    raise ValueError('Invalid registered variant')
                key=f'characters/{v.characterId}/{v.emotion}/{v.gesture}'
                if key in seen:raise ValueError('Duplicate variant key')
                seen.add(key)
                items.append({**v.model_dump(),'assetKey':key,'source':'pre_generated'})
        except (ValueError,KeyError,TypeError) as exc:
            raise HTTPException(503,{'code':'ASSET_MANIFEST_INVALID','message':'캐릭터 이미지 구성을 확인해야 해요.','retryable':True}) from exc
    return {'renderMode':'image_variants','runtimeImageApiCalls':False,'items':items}


def estimated_cost(usage: dict) -> float | None:
    """Standard USD estimate from the returned GPT Image 2.5 token usage; never invent missing usage."""
    details = usage.get("input_tokens_details", {})
    output = usage.get("output_tokens_details", {}).get("image_tokens", usage.get("output_tokens"))
    if output is None or "text_tokens" not in details or "image_tokens" not in details:
        return None
    return round((details["text_tokens"] * 5 + details["image_tokens"] * 8 + output * 30) / 1_000_000, 6)


async def _call_openai(prompt: str, character: str, reference: bytes | None, background: str = 'transparent'):
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise HTTPException(503, {"code": "IMAGE_NOT_CONFIGURED", "message": "OpenAI 이미지 API 설정이 필요해요.", "retryable": False})
    # Reserve before every provider call, including attempts that fail; cached reads reserve nothing.
    providers.reserve_quota("image_generations", 1, int(os.getenv("MALO_IMAGE_DAILY_LIMIT", "20")))
    budget = int(float(os.getenv("MALO_IMAGE_DAILY_BUDGET_USD", "2")) * 1_000_000)
    providers.reserve_quota("image_budget_microusd", 100_000, budget)
    body = {"model": MODEL, "prompt": prompt, "quality": QUALITY, "size": SIZE, "n": 1,
        "output_format": "webp", "output_compression": 85, "background": background,
        "safety_identifier": hashlib.sha256(("malo-shared-persona:" + character).encode()).hexdigest()}
    path = "generations"
    if reference:
        path = "edits"
        mime = "image/png" if reference.startswith(b"\x89PNG\r\n\x1a\n") else "image/webp"
        body["images"] = [{"image_url": f"data:{mime};base64," + base64.b64encode(reference).decode()}]
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
    if emotion != "neutral":
        prompt = ("Edit this exact Malo character portrait. Preserve the same adult person's identity, face shape, hair, clothing, accessories, "
            "the reference's stylized proportions, half-lidded anime eyes, tiny simplified nose and mouth, smooth face, sculpted hair, "
            "matte material, pose, framing, colors and rendering style. "
            "Change ONLY the facial expression to " + EXPRESSIONS[emotion] + ". Keep the full head and the same body visible, clean edges "
            "and transparent background. Do not enlarge the head, eyes or cheeks. No text, logos or additional people.")
    else:
        prompt = ("Use the uploaded character lineup as the exact style reference for Malo. Match the face design, head-to-body ratio, "
            "sculpted hair, clothing materials and lighting. Output only ONE character, not the lineup. "
            "Original fictional adult character: " + CHARACTERS[character] + ". Expression: " + EXPRESSIONS[emotion] + ". "
            "Preserve the corresponding character's appealing simplified anime face from the reference: restrained half-lidded almond eyes, "
            "tiny simple nose and mouth, smooth unsegmented facial surfaces, sculpted chunky hair, slightly large head, slim stylized body. "
            "Soft matte 3D figure rendering. Keep the source face appeal and individually styled outfits. "
            "Do not reinterpret as a realistic person, introduce carved cheekbones, a long realistic nose, wrinkled skin, polygon-faceted "
            "face planes, or fashion-model anatomy. Do not turn it into a baby-faced doll with giant glossy eyes or short chibi limbs. "
            "Single character centered, front three-quarter view facing the viewer, full head and body within frame, generous transparent "
            "margins, crisp silhouette. Transparent background. No room, ground, speech bubbles, text, logos or UI. Never photorealistic.")
    digest = hashlib.sha256(json.dumps(["malo-reference-anime-v3", MODEL, QUALITY, SIZE, prompt,
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
        "referenceAssetId": "i_" + hashlib.sha256(reference).hexdigest()[:40] if reference and emotion != "neutral" else None}
    destination = _metadata_path(character, emotion)
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.with_name(destination.name + "." + uuid4().hex + ".tmp")
    staging.write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
    staging.replace(destination)
    return {**metadata, "cached": False}


async def generate(request: PersonaImageRequest):
    async with _lock:
        style_file = Path(__file__).with_name("style-reference.png")
        base = await _generate(request.characterId, "neutral", style_file.read_bytes() if style_file.is_file() else None)
        if request.emotion == "neutral":
            return base
        return await _generate(request.characterId, request.emotion, image_path(base["assetId"]).read_bytes())
