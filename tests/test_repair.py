import asyncio
import unittest
from unittest.mock import AsyncMock, patch
from malo_ai.providers import evaluate, mock_grade
from malo_ai.schemas import EvaluationRequest
from test_pipeline import node


class RepairTests(unittest.TestCase):
    def request(self, **extra):
        return EvaluationRequest(mode='live', pack='ko', characterId='professor', personalityId='calm',
                                 situation='과제 기한', node=node(), text='무례하게 말해서 죄송합니다.', **extra)

    def test_pending_issue_hides_story_targets_and_requires_explicit_valid_resolution(self):
        repair=dict(kind='apology', issue='교수님을 무시하는 말을 함', triggerText='신경 꺼', resumeNpcText='언제까지 가능하죠?')
        request=self.request(repair=repair, nextCheckpoint=dict(goal='새 주제', draftLine='다음 질문'),
                             allowedRoutes=['direct'], allowedEndings=['happy'], closingAllowed=True)
        for action, mark, expected in [('none','O','continue'), ('resolved','X','continue'), ('resolved','?','continue'), ('resolved','O','resolved')]:
            result=mock_grade(request).model_copy(update=dict(repairAction=action, evaluationMark=mark,
                   goalAchieved=True, conversationComplete=True, confidence=.99, routeId='direct', endingId='happy'))
            with patch('malo_ai.providers.json_completion', new_callable=AsyncMock, return_value=(result,'test')) as llm:
                grade,_=asyncio.run(evaluate(request))
                self.assertEqual(grade.repairAction,expected)
                self.assertFalse(grade.goalAchieved)
                self.assertFalse(grade.conversationComplete)
                self.assertIsNone(grade.routeId)
                self.assertIsNone(grade.endingId)
                payload,instruction=llm.call_args.args[1:]
                self.assertEqual(payload['repair'],repair)
                self.assertIsNone(payload['nextCheckpoint'])
                self.assertEqual(payload['allowedRoutes'],[])
                self.assertFalse(payload['closingAllowed'])
                self.assertIn('Do NOT append the old task question',instruction)
                self.assertIn('respectful refusal/boundary',instruction)
                self.assertEqual(grade.evaluationMark,'△' if action=='none' else mark)

    def test_uncertainty_does_not_demand_apology_and_new_hostility_can_escalate(self):
        request=self.request()
        result=mock_grade(request).model_copy(update=dict(repairAction='request_apology',evaluationMark='?',confidence=.4))
        with patch('malo_ai.providers.json_completion',new_callable=AsyncMock,return_value=(result,'test')):
            grade,_=asyncio.run(evaluate(request))
            self.assertEqual(grade.repairAction,'request_clarification')
            self.assertEqual(grade.outcome,'clarify')
        request=self.request(repair=dict(kind='clarification',issue='뜻이 불명확함',triggerText='그거',resumeNpcText='언제까지 가능하죠?'))
        result=result.model_copy(update=dict(evaluationMark='X',confidence=.99,repairIssue='명확한 모욕'))
        with patch('malo_ai.providers.json_completion',new_callable=AsyncMock,return_value=(result,'test')):
            grade,_=asyncio.run(evaluate(request))
            self.assertEqual(grade.repairAction,'request_apology')
            self.assertEqual(grade.repairIssue,'명확한 모욕')

    def test_respectful_answer_has_no_repair_and_keeps_normal_progress(self):
        request=self.request()
        result=mock_grade(request).model_copy(update=dict(evaluationMark='O',goalAchieved=True,repairAction='none'))
        with patch('malo_ai.providers.json_completion',new_callable=AsyncMock,return_value=(result,'test')):
            grade,_=asyncio.run(evaluate(request))
            self.assertEqual(grade.repairAction,'none')
            self.assertTrue(grade.goalAchieved)
