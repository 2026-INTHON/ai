import asyncio
import math
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from pydantic import ValidationError

from malo_ai.audio import audio_metrics
from malo_ai.main import app
from malo_ai.providers import evaluate, mock_grade, reserve_quota
from malo_ai.schemas import EvaluationRequest, Grade, Scenario


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

    def test_native_language_answers_offer_target_expression_and_never_grade_as_mistakes(self):
        base = {"pack": "ko", "characterId": "professor", "personalityId": "calm", "situation": "과제 기한", "node": node()}
        for text in ["Could I submit it tomorrow?", "明日提出してもいいですか", "可以明天提交吗", "Tôi có thể nộp vào ngày mai không?"]:
            grade = mock_grade(EvaluationRequest(**base, text=text))
            self.assertTrue(grade.native)
            self.assertEqual(grade.outcome, "clarify")
            self.assertRegex(grade.betterExpression, r"[가-힣]")
            self.assertTrue(grade.action and grade.cues)
            self.assertGreaterEqual(len(grade.views), 2)
        self.assertFalse(mock_grade(EvaluationRequest(**base, text="123")).native)
        self.assertFalse(mock_grade(EvaluationRequest(**base, text="감사합니다. 내일 오후 5시에 제출하겠습니다.")).native)

    def test_staged_hints_reveal_no_thought_or_solution_until_step_two_and_make_no_llm_call(self):
        with patch.dict(os.environ, {"MALO_AI_SERVICE_TOKEN": "test-service-token", "MALO_ENV": "production"}), patch("malo_ai.providers.json_completion", new_callable=AsyncMock) as llm:
            client = TestClient(app)
            headers = {"X-AI-Service-Token": "test-service-token"}
            payload = {"characterId": "professor", "node": node(), "step": 1}
            first = client.post("/v1/hints", json=payload, headers=headers)
            self.assertEqual(first.status_code, 200)
            self.assertEqual(len(first.json()["clue"]), 3)
            self.assertIsNone(first.json()["thought"])
            self.assertIsNone(first.json()["tip"])
            del payload["step"]
            second = client.post("/v1/hints", json=payload, headers=headers)
            self.assertEqual(second.json()["step"], 2)
            self.assertEqual(second.json()["thought"], node()["hiddenThought"])
            self.assertEqual(second.json()["tip"], node()["tip"])
            self.assertEqual(client.post("/v1/hints", json={**payload, "step": 3}, headers=headers).status_code, 422)
            llm.assert_not_called()

    def test_live_evaluation_preserves_stage_directions_and_guards_native_answer(self):
        request = EvaluationRequest(mode="live", pack="ko", characterId="professor", personalityId="calm", situation="과제 기한", node=node(), text="Could I submit it tomorrow?", allowedRoutes=['direct'], allowedEndings=['happy'])
        malicious_grade = mock_grade(request).model_copy(update={"native": False, "outcome": "correct", "confidence": 0.99})
        with patch("malo_ai.providers.json_completion", new_callable=AsyncMock, return_value=(malicious_grade, "lablup")) as llm:
            grade, provider = asyncio.run(evaluate(request))
            self.assertEqual(provider, "lablup")
            self.assertTrue(grade.native)
            self.assertEqual(grade.outcome, "clarify")
            self.assertEqual(grade.views, malicious_grade.views)
            self.assertIn("native=true", llm.call_args.args[2])
            invalid = grade.model_dump()
            invalid["cues"] = [{"k": "unknown", "v": "bad"}]
            with self.assertRaises(ValidationError):
                Grade(**invalid)


if __name__ == "__main__":
    unittest.main()
