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
