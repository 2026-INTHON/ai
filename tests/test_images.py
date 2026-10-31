import asyncio
import base64
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi import HTTPException
from fastapi.testclient import TestClient

from malo_ai import images
from malo_ai.main import app
from malo_ai.schemas import PersonaImageRequest


class ImageTests(unittest.IsolatedAsyncioTestCase):
    async def test_generate_edit_cache_cost_and_service_access(self):
        calls = []
        client_type = httpx.AsyncClient
        usage = {"input_tokens_details": {"text_tokens": 100, "image_tokens": 1000}, "output_tokens": 1000}

        def handle(request):
            data = json.loads(request.content)
            calls.append((request.url.path, data))
            self.assertEqual(data["quality"], "medium")
            self.assertEqual(data["size"], "1024x1536")
            self.assertEqual(data["background"], "transparent")
            self.assertEqual(data["n"], 1)
            fake_webp = b"RIFF0000WEBP" + request.url.path.encode()
            return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(fake_webp).decode()}], "usage": usage})

        with tempfile.TemporaryDirectory() as folder, patch("malo_ai.providers.DATA_DIR", Path(folder)), patch.dict(os.environ, {"OPENAI_API_KEY": "fake-test-key", "MALO_AI_SERVICE_TOKEN": "test-image-service", "MALO_IMAGE_DAILY_LIMIT": "20"}), patch("malo_ai.images._lock", asyncio.Lock()), patch("malo_ai.images.httpx.AsyncClient", side_effect=lambda **kwargs: client_type(transport=httpx.MockTransport(handle), **kwargs)):
            neutral = PersonaImageRequest(characterId="friend", emotion="neutral")
            first, duplicate = await asyncio.gather(images.generate(neutral), images.generate(neutral))
            self.assertEqual(len(calls), 1)
            self.assertFalse(first["cached"])
            self.assertTrue(duplicate["cached"])
            self.assertAlmostEqual(first["estimatedCostUsd"], 0.0385)
            edited = await images.generate(PersonaImageRequest(characterId="friend", emotion="happy"))
            self.assertEqual(calls[1][0], "/v1/images/edits")
            self.assertTrue(calls[1][1]["images"][0]["image_url"].startswith("data:image/webp;base64,"))
            self.assertEqual(edited["referenceAssetId"], first["assetId"])
            self.assertEqual(sum(item["assetId"] is not None for item in images.catalog()["items"]), 2)
            self.assertEqual(len(calls), 2)  # Catalog reads do not generate or bill.
            client = TestClient(app)
            self.assertEqual(client.get("/v1/images/" + first["assetId"]).status_code, 401)
            self.assertEqual(client.post("/v1/images/personas/generate", json=neutral.model_dump()).status_code, 401)
            r = client.post("/v1/images/personas/generate", headers={"X-AI-Service-Token": "test-image-service"}, json=neutral.model_dump())
            self.assertEqual(r.status_code, 200)
            self.assertTrue(r.json()["cached"])

    async def test_budget_blocks_provider_call_and_missing_usage_stays_unknown(self):
        with tempfile.TemporaryDirectory() as folder, patch("malo_ai.providers.DATA_DIR", Path(folder)), patch.dict(os.environ, {"OPENAI_API_KEY": "fake-test-key", "MALO_IMAGE_DAILY_BUDGET_USD": "0"}):
            with self.assertRaises(HTTPException) as caught:
                await images.generate(PersonaImageRequest(characterId="manager"))
            self.assertEqual(caught.exception.status_code, 429)
            self.assertFalse(any(item["assetId"] for item in images.catalog()["items"]))
        self.assertIsNone(images.estimated_cost({}))
        with self.assertRaises(HTTPException):
            images.image_path("../../private")
