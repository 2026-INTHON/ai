import math
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import ValidationError

from malo_ai.audio import audio_metrics
from malo_ai.main import app
from malo_ai.providers import mock_grade, reserve_quota
from malo_ai.schemas import EvaluationRequest, Scenario


def node(id="start", next_id=None):
    return {"id": id, "npcText": "언제까지 가능하죠?", "goal": "구체적 기한 제안", "goodExample": "내일 오후 5시까지 제출하겠습니다.", "hiddenThought": "일정을 알고 싶다.", "tip": "시간을 제안하세요.", "choices": [{"id": "a", "text": "내일 제출하겠습니다."}, {"id": "b", "text": "몰라요."}], "nextNodeId": next_id}


class PipelineTests(unittest.TestCase):
    def test_mock_grade_distinguishes_ambiguity_and_mistake(self):
        base = {"pack": "ko", "characterId": "professor", "personalityId": "calm", "situation": "과제 기한", "node": node()}
        good = mock_grade(EvaluationRequest(**base, text="교수님, 내일 오후 5시까지 제출하겠습니다."))
        unclear = mock_grade(EvaluationRequest(**base, text="네"))
        bad = mock_grade(EvaluationRequest(**base, text="몰라요"))
        self.assertEqual((good.outcome, unclear.outcome, bad.outcome), ("correct", "clarify", "misunderstanding"))
        self.assertLess(unclear.confidence, 0.75)

    def test_generated_graph_rejects_dangling_edges(self):
        values = {"title": "기한", "situation": "기한 조정", "goal": "기한 합의", "pack": "ko", "characterId": "professor", "personalityId": "calm", "nodes": [node("first", "missing"), node("last")]}
        with self.assertRaises(ValidationError):
            Scenario(**values)

    def test_measured_pause_does_not_invent_psychological_state(self):
        tone = [int(1500 * math.sin(index * 0.15)) for index in range(16000)]
        metrics = audio_metrics(tone + [0] * 8000 + tone, 16000, "교수님 감사합니다", "ko")
        self.assertEqual(metrics.pauseCount, 1)
        self.assertEqual(metrics.durationMs, 2500)
        self.assertEqual(metrics.speedUnit, "characters_per_minute")
        self.assertTrue(metrics.estimated)

    def test_daily_quota_is_atomic_and_persistent(self):
        with tempfile.TemporaryDirectory() as directory, patch("malo_ai.providers.DATA_DIR", Path(directory)):
            reserve_quota("test", 1, 1)
            with self.assertRaises(Exception) as raised:
                reserve_quota("test", 1, 1)
            self.assertEqual(raised.exception.status_code, 429)

    def test_service_token_protects_ai_routes(self):
        with patch.dict(os.environ, {"MALO_AI_SERVICE_TOKEN": "test-service-token", "MALO_ENV": "production"}):
            client = TestClient(app)
            self.assertEqual(client.get("/v1/persona-assets").status_code, 401)
            response = client.get("/v1/persona-assets", headers={"X-AI-Service-Token": "test-service-token"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.json()["items"]), 20)


if __name__ == "__main__":
    unittest.main()
