import asyncio
import unittest
from unittest.mock import AsyncMock,patch
from fastapi import HTTPException
from malo_ai.reports import ReportDraft,ReportRequest,generate

def draft(ids=('turn-1',),language='en'):
    return ReportDraft(language=language,headline='Clear request',overallFeedback='You communicated your intention.',strengths=['You gave a deadline.'],improvements=[],culturalTakeaways=['Honorifics depend on the relationship.'],nextPractice=['Try a confirmation question.'],nodes=[{'nodeId':key,'implicitIntent':'Feedback for '+key,'culturalContext':'A polite request can include a concrete deadline; people vary.','practiceTip':'Add a feasible time.'} for key in ids])

class ReportTests(unittest.TestCase):
    def request(self,ids=('original-id',)):
        return ReportRequest(language='en',context={'pack':'ko'},nodes=[{'nodeId':key,'npcText':'안녕하세요.'} for key in ids],recordedResult={'score':100})

    def test_short_keys_restore_original_ids_and_order_without_mixing_feedback(self):
        request=self.request(('5cab3d40-3417-4c61-bf58-9e52b184c6d6','37bdfd25-3e67-4453-b561-c8331d6f2e52'))
        with patch('malo_ai.providers.json_completion',new_callable=AsyncMock,return_value=(draft(('turn-2','turn-1')),'test')) as provider,patch('malo_ai.reports.moderate',new_callable=AsyncMock):
            report=asyncio.run(generate(request))['report']
        payload=provider.call_args.args[1]
        self.assertEqual([n['nodeId'] for n in payload['nodes']],['turn-1','turn-2'])
        self.assertEqual([n['nodeId'] for n in report['nodes']],[n['nodeId'] for n in request.nodes])
        self.assertEqual([n['implicitIntent'] for n in report['nodes']],['Feedback for turn-1','Feedback for turn-2'])
        self.assertEqual(payload['recordedResult'],{'score':100})

    def test_missing_unknown_or_wrong_language_feedback_is_not_attached(self):
        for result in (draft(('turn-1',)),draft(('turn-1','invented')),draft(('turn-1','turn-2'),language='ja')):
            with self.subTest(result=result),patch('malo_ai.providers.json_completion',new_callable=AsyncMock,return_value=(result,'test')),patch('malo_ai.reports.moderate',new_callable=AsyncMock):
                with self.assertRaises(HTTPException) as caught:asyncio.run(generate(self.request(('id-1','id-2'))))
                self.assertEqual(caught.exception.detail['code'],'REPORT_INVALID')

    def test_invalid_input_ids_fail_before_provider_call(self):
        with patch('malo_ai.providers.json_completion',new_callable=AsyncMock) as provider:
            with self.assertRaises(HTTPException):asyncio.run(generate(self.request(('duplicate','duplicate'))))
            provider.assert_not_awaited()
