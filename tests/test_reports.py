import asyncio
import unittest
from unittest.mock import AsyncMock,patch
from fastapi import HTTPException
from malo_ai.reports import ReportDraft,ReportRequest,generate

class ReportTests(unittest.TestCase):
    def test_report_keeps_requested_language_and_exact_recorded_nodes(self):
        draft=ReportDraft(language='en',headline='Clear request',overallFeedback='You communicated your intention.',strengths=['You gave a deadline.'],improvements=[],culturalTakeaways=['Honorifics depend on the relationship.'],nextPractice=['Try a confirmation question.'],nodes=[{'nodeId':'n1','implicitIntent':'The professor needs a specific time.','culturalContext':'A polite request can include a concrete deadline; people vary.','practiceTip':'Add a feasible time.'}])
        request=ReportRequest(language='en',context={'pack':'ko'},nodes=[{'nodeId':'n1'}],recordedResult={'score':100})
        with patch('malo_ai.providers.json_completion',new_callable=AsyncMock,return_value=(draft,'test')),patch('malo_ai.reports.moderate',new_callable=AsyncMock):
            self.assertEqual(asyncio.run(generate(request))['report']['headline'],'Clear request')
            request.language='ja'
            with self.assertRaises(HTTPException):asyncio.run(generate(request))
            request.language='en'
            request.nodes=[{'nodeId':'invented'}]
            with self.assertRaises(HTTPException):asyncio.run(generate(request))
