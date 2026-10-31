import asyncio,os,unittest
from unittest.mock import AsyncMock,patch
import httpx
from pydantic import BaseModel
from fastapi import HTTPException
from malo_ai.providers import structured_response,json_completion

class Answer(BaseModel):
    value:int

def message(text,phase=None):
    return {'type':'message','phase':phase,'status':'completed','content':[{'type':'output_text','text':text}]}

class StructuredTests(unittest.TestCase):
    def test_only_final_message_is_parsed_and_partial_drafts_never_become_answers(self):
        response={'status':'completed','output':[message('intermediate draft','commentary'),message('{"value":2}','final_answer')]}
        self.assertEqual(structured_response(Answer,response).value,2)
        self.assertEqual(structured_response(Answer,{'output':[message('{"value":1}'),message('{"value":2}')]}).value,2)
        for bad in [dict(response,status='incomplete'),{'output':[message('{"value":1}','commentary')]},{'output':[message('{"value":1}{"value":2}','final_answer')]}]:
            with self.assertRaises(ValueError):structured_response(Answer,bad)

    def test_invalid_final_output_has_one_bounded_counted_retry(self):
        def response(status):return httpx.Response(200,json={'status':status,'output':[message('{"value":3}','final_answer')]},request=httpx.Request('POST','https://api.openai.com/v1/responses'))
        with patch.dict(os.environ,{'OPENAI_API_KEY':'test-only','LABLUP_BASE_URL':''}),patch('malo_ai.providers.reserve_quota') as quota,patch('httpx.AsyncClient.post',new_callable=AsyncMock,side_effect=[response('incomplete'),response('completed')]) as post:
            result,provider=asyncio.run(json_completion(Answer,{},'Return the answer.'))
            self.assertEqual((result.value,provider),(3,'openai'));self.assertEqual(post.call_count,2);self.assertEqual(quota.call_count,2)
        with patch.dict(os.environ,{'OPENAI_API_KEY':'test-only','LABLUP_BASE_URL':''}),patch('malo_ai.providers.reserve_quota'),patch('httpx.AsyncClient.post',new_callable=AsyncMock,return_value=response('incomplete')) as post:
            with self.assertRaises(HTTPException):asyncio.run(json_completion(Answer,{},'Return the answer.'))
            self.assertEqual(post.call_count,2)

    def test_batch_retry_is_left_to_the_durable_worker_lease(self):
        schema=type('ReportDraft',(Answer,),{})
        response=httpx.Response(200,json={'status':'incomplete','output':[message('{"value":3}')]},request=httpx.Request('POST','https://api.openai.com/v1/responses'))
        with patch.dict(os.environ,{'OPENAI_API_KEY':'test-only','LABLUP_BASE_URL':''}),patch('malo_ai.providers.reserve_quota') as quota,patch('httpx.AsyncClient.post',new_callable=AsyncMock,return_value=response) as post:
            with self.assertRaises(HTTPException):asyncio.run(json_completion(schema,{},'Return the answer.'))
            self.assertEqual(post.call_count,1);self.assertEqual(quota.call_count,1)
