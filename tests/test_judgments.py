import asyncio
import unittest
from unittest.mock import AsyncMock,patch
from malo_ai.providers import evaluate,mock_grade
from malo_ai.schemas import EvaluationRequest,Grade
from test_pipeline import node

class JudgmentTests(unittest.TestCase):
    def test_four_marks_preserve_actor_emotion_and_use_authored_context(self):
        request=EvaluationRequest(mode='live',pack='ko',characterId='professor',personalityId='strict',situation='과제 기한',node=node(),text='교수님, 내일 오후까지 제출하겠습니다.')
        for mark,outcome in [('O','correct'),('△','correct'),('X','misunderstanding'),('?','clarify')]:
            data=mock_grade(request).model_dump()
            data.update({'evaluationMark':mark,'reaction':None,'goalAchieved':True,'emotion':'sad','action':'잠시 눈길을 내린다.','cues':[{'k':'침묵','v':'짧게 말을 멈춘다.'}]})
            result=Grade.model_validate(data)
            with patch('malo_ai.providers.json_completion',new_callable=AsyncMock,return_value=(result,'test')) as llm:
                grade,_=asyncio.run(evaluate(request))
                self.assertEqual(grade.outcome,outcome)
                self.assertEqual(grade.emotion,'sad')
                self.assertEqual(grade.evaluationMark,mark)
                self.assertEqual(grade.action,result.action)
                self.assertEqual(grade.cues,result.cues)
                payload,instruction=llm.call_args.args[1:]
                self.assertEqual(payload['fictionalIntent'],request.node.hiddenThought)
                self.assertIn('Precise',payload['personaGuidance'])
                self.assertIn('Allow minor errors',instruction)
                self.assertIn('corrupted speech transcript',instruction)
                self.assertIn('네 교수님. 내일 2시에 갈게요.',instruction)
                self.assertIn('교수님, 내일 수업은 휴강인가요?',instruction)
                self.assertIn('교수님, 내일... 아니 그때 제가... 시간...',instruction)
                self.assertIn('그래서 뭐 어떡하라고?',instruction)
                self.assertIn('genuine polite',instruction)

    def test_context_image_is_allowlisted_and_fluent_korean_is_not_native_language_help(self):
        option={'assetKey':'characters/professor/time_aware','emotion':'neutral','gesture':'idle','useWhen':'다음 일정 확인','pose':'checking_watch'}
        request=EvaluationRequest(mode='live',pack='ko',characterId='professor',personalityId='calm',situation='면담 마무리',node=node(),text='교수님, 오늘 시간 내 주셔서 감사합니다. 다음에 찾아뵙겠습니다.',imageOptions=[option])
        for key in [option['assetKey'],'characters/girlfriend/other']:
            result=mock_grade(request).model_copy(update={'evaluationMark':'O','native':True,'goalAchieved':True,'imageAssetKey':key})
            with patch('malo_ai.providers.json_completion',new_callable=AsyncMock,return_value=(result,'test')) as llm:
                grade,_=asyncio.run(evaluate(request))
                self.assertFalse(grade.native);self.assertEqual(grade.outcome,'correct')
                self.assertEqual(grade.imageAssetKey,key if key==option['assetKey'] else None)
                self.assertEqual(llm.call_args.args[1]['imageOptions'][0]['useWhen'],'다음 일정 확인')

    def test_last_life_and_negative_image_guidance_reach_the_prompt_without_changing_the_mark(self):
        option={'assetKey':'characters/girlfriend/contempt','emotion':'angry','gesture':'arms_crossed','reaction':'contempt','endingPreferred':True}
        request=EvaluationRequest(mode='live',pack='ko',characterId='girlfriend',personalityId='calm',situation='약속에 관한 갈등',node=node(),text='내가 알아서 할 테니까 신경 쓰지 마.',imageOptions=[option],livesRemaining=1)
        result=mock_grade(request).model_copy(update={'evaluationMark':'X','emotion':'angry','imageAssetKey':option['assetKey']})
        with patch('malo_ai.providers.json_completion',new_callable=AsyncMock,return_value=(result,'test')) as llm:
            grade,_=asyncio.run(evaluate(request))
            self.assertEqual(grade.evaluationMark,'X');self.assertEqual(grade.imageAssetKey,option['assetKey'])
            self.assertEqual(llm.call_args.args[1]['livesRemaining'],1)
            self.assertTrue(llm.call_args.args[1]['imageOptions'][0]['endingPreferred'])
            self.assertIn('cold contempt or sadness',llm.call_args.args[2])
            self.assertIn('뭐, 너 뭐라고 했어? 장난해?',llm.call_args.args[2])
            self.assertIn('어떻게 그런 말을 할 수가 있어? 정말 너무해.',llm.call_args.args[2])
            self.assertIn('never for minor mistakes',llm.call_args.args[2])
