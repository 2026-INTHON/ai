import asyncio
import unittest
from unittest.mock import AsyncMock, patch
from pydantic import ValidationError
from malo_ai.schemas import EvaluationRequest
from malo_ai.providers import evaluate, mock_grade
from test_pipeline import node


class PersonaTests(unittest.TestCase):
    def test_selected_profile_reaches_live_prompt_and_mismatch_is_rejected(self):
        persona = dict(characterId='girlfriend', personalityId='calm', revision='v1', name='차분', short='차분한 말투', description='조용히 경청해요.',
            profile=dict(age='24세',role='친구',occupation='디자인 전공 대학생',introduction='서윤이에요.',relationship='첫 만남',values=['존중'],traits=['차분한'],likes=['독립서점'],dislikes=['재촉'],hobbies=['독서'],speakingStyle='첫 만남은 해요체',sampleLines=['어떤 책 좋아하세요?']),dialogueRules=['장면 관계에 맞는 말투를 유지한다.'])
        request = EvaluationRequest(mode='live', pack='ko', characterId='girlfriend',personalityId='calm',situation='카페에서 처음 만남',node=node(),text='저도 책 읽는 걸 좋아해요.',persona=persona)
        result=mock_grade(request)
        with patch('malo_ai.providers.json_completion',new_callable=AsyncMock,return_value=(result,'test')) as llm:
            asyncio.run(evaluate(request))
            payload,instruction=llm.call_args.args[1:]
            self.assertEqual(payload['persona']['profile']['likes'],['독립서점'])
            self.assertEqual(payload['personaGuidance'],persona['dialogueRules'])
            self.assertIn('Preferences are not correctness criteria',instruction)
            self.assertIn('first meeting',instruction)
        with self.assertRaises(ValidationError):
            EvaluationRequest(**{**request.model_dump(),'personalityId':'strict'})
