import asyncio
import unittest
from unittest.mock import AsyncMock, patch
from pydantic import ValidationError
from fastapi import HTTPException
from malo_ai.schemas import EvaluationRequest
from malo_ai.providers import evaluate, mock_grade
from test_pipeline import node
from malo_ai.learning_policy import DIALOGUE_STYLE


class PersonaTests(unittest.TestCase):
    def test_missing_style_uses_ordinary_route_without_guessing_story_branches(self):
        for routes,route,expected in [(['direct','considerate'],None,'direct'),(['direct','considerate'],'considerate','considerate'),(['direct','considerate'],'unknown',None),(['accept','decline'],None,None)]:
            with self.subTest(routes=routes,route=route):
                request=EvaluationRequest(mode='live',pack='ko',characterId='girlfriend',personalityId='calm',situation='첫 만남',node=node(),text='스물넷이에요.',allowedRoutes=routes)
                result=mock_grade(request).model_copy(update={'evaluationMark':'O','goalAchieved':True,'native':False,'routeId':route})
                with patch('malo_ai.providers.json_completion',new_callable=AsyncMock,return_value=(result,'test')):
                    if expected is None:
                        with self.assertRaises(HTTPException) as error:asyncio.run(evaluate(request))
                        self.assertEqual(error.exception.detail['code'],'STORY_ROUTE_INVALID')
                    else:
                        grade,_=asyncio.run(evaluate(request))
                        self.assertEqual(grade.routeId,expected)
                        self.assertEqual(grade.evaluationMark,'O')

    def test_only_appropriate_late_closing_can_complete_a_conversation(self):
        for allowed,mark,native,expected in [(False,'O',False,False),(True,'O',False,True),(True,'X',False,False),(True,'?',False,False),(True,'△',True,False)]:
            with self.subTest(allowed=allowed,mark=mark,native=native):
                request=EvaluationRequest(mode='live',pack='ko',characterId='girlfriend',personalityId='calm',situation='첫 만남 마무리',node={**node(),'npcText':'다음에 호칭을 정해 봐요.'},text='네, 조심히 들어가세요!',closingAllowed=allowed)
                result=mock_grade(request).model_copy(update={'conversationComplete':True,'evaluationMark':mark,'reaction':None,'goalAchieved':mark=='O','native':native,'outcome':'correct' if mark=='O' else 'misunderstanding' if mark=='X' else 'clarify'})
                with patch('malo_ai.providers.json_completion',new_callable=AsyncMock,return_value=(result,'test')) as llm:
                    grade,_=asyncio.run(evaluate(request))
                    self.assertEqual(llm.call_args.args[1]['closingAllowed'],allowed)
                    self.assertEqual(grade.conversationComplete,expected)

    def test_selected_profile_reaches_live_prompt_and_mismatch_is_rejected(self):
        persona = dict(characterId='girlfriend', personalityId='calm', revision='v1', name='차분', short='차분한 말투', description='조용히 경청해요.',
            profile=dict(age='24세',role='친구',occupation='디자인 전공 대학생',introduction='서윤이에요.',relationship='첫 만남',values=['존중'],traits=['차분한'],likes=['독립서점'],dislikes=['재촉'],hobbies=['독서'],speakingStyle='첫 만남은 해요체',sampleLines=['어떤 책 좋아하세요?']),dialogueRules=['장면 관계에 맞는 말투를 유지한다.'])
        request = EvaluationRequest(mode='live', pack='ko', characterId='girlfriend',personalityId='calm',situation='카페에서 처음 만남',node=node(),text='저도 책 읽는 걸 좋아해요.',persona=persona,nextCheckpoint=dict(goal='취향 묻기',draftLine='어떤 책 좋아하세요?',routeLines={'considerate':'괜찮으시면 좋아하는 책을 알려 주세요.'}))
        result=mock_grade(request)
        with patch('malo_ai.providers.json_completion',new_callable=AsyncMock,return_value=(result,'test')) as llm:
            asyncio.run(evaluate(request))
            payload,instruction=llm.call_args.args[1:]
            self.assertEqual(payload['persona']['profile']['likes'],['독립서점'])
            self.assertEqual(payload['personaGuidance'],persona['dialogueRules'])
            self.assertIn('Preferences are not correctness criteria',instruction)
            self.assertIn('first meeting',instruction)
            # Old sessions may still contain polite-padding scaffolds; the live policy must override that style.
            self.assertIn(DIALOGUE_STYLE,instruction)
            self.assertEqual(payload['nextCheckpoint']['goal'],'취향 묻기')
            self.assertEqual(payload['nextCheckpoint'],{'goal':'취향 묻기'})
            self.assertNotIn('goodExample',payload)
            self.assertNotIn('fictionalIntent',payload)
        with self.assertRaises(ValidationError):
            EvaluationRequest(**{**request.model_dump(),'personalityId':'strict'})

    def test_register_persists_without_explicit_permission_and_keeps_recent_context(self):
        for allowed,returned,expected in [(False,'casual','polite'),(True,'casual','casual'),(True,None,'polite')]:
            with self.subTest(allowed=allowed,returned=returned):
                history=[dict(user=f'질문 {i}',npc=f'대답 {i}') for i in range(10)]
                request=EvaluationRequest(mode='live',pack='ko',characterId='girlfriend',personalityId='calm',situation='점심 식사',node=node(),text='슴슴한 음식을 좋아하세요?',npcSpeechLevel='polite',allowSpeechLevelChange=allowed,history=history)
                result=mock_grade(request).model_copy(update={'npcSpeechLevel':returned})
                with patch('malo_ai.providers.json_completion',new_callable=AsyncMock,return_value=(result,'test')) as llm:
                    grade,_=asyncio.run(evaluate(request))
                    self.assertEqual(grade.npcSpeechLevel,expected)
                    self.assertEqual(len(llm.call_args.args[1]['history']),10)
