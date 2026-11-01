import asyncio
import hashlib
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import AsyncMock,patch
import httpx
from malo_ai import providers,speech_cache
from malo_ai.schemas import SynthesisRequest

class SpeechCacheTests(unittest.IsolatedAsyncioTestCase):
    async def test_existing_file_is_indexed_without_credits_then_reused_after_restart(self):
        request=SynthesisRequest(text='뭐야 이 사람, 이상한 사람 아니야?',characterId='girlfriend',personalityId='strict',emotion='angry',reaction='contempt')
        voice,prompt,tempo=providers.typecast_voice(request)
        instructions=json.dumps([prompt,tempo],sort_keys=True)
        legacy='a_'+hashlib.sha256(json.dumps(['selected-voice-v2','typecast','ssfm-v31','ko','girlfriend',request.text,voice,'strict','angry','contempt',instructions,request.speed],ensure_ascii=False).encode()).hexdigest()[:40]
        with tempfile.TemporaryDirectory() as tmp,patch('malo_ai.providers.DATA_DIR',Path(tmp)),patch.dict('os.environ',{},clear=True),patch('malo_ai.providers.reserve_quota') as quota,patch('httpx.AsyncClient.post',new_callable=AsyncMock) as post:
            root=Path(tmp);(root/'audio').mkdir();(root/'audio'/(legacy+'.mp3')).write_bytes(b'ID3existing')
            self.assertEqual((await providers.synthesize(request,cache_only=True))['assetId'],legacy)
            self.assertEqual((await providers.synthesize(request))['assetId'],legacy)
            self.assertTrue((await providers.synthesize(request.model_copy(update={'text':'  뭐야 이 사람,  이상한 사람 아니야?  '})))['cached'])
            quota.assert_not_called();post.assert_not_awaited()
            with closing(sqlite3.connect(root/'speech-cache.db')) as db:
                self.assertEqual(db.execute('select character_id,personality_id,emotion,reaction from speech_tags').fetchone(),('girlfriend','strict','angry','contempt'))
                self.assertEqual(db.execute('select voice_id from speech_assets').fetchone()[0],voice)
            self.assertEqual(speech_cache.stats(root)['assets'],1)

    async def test_index_miss_never_calls_provider_and_missing_asset_is_regenerated(self):
        response=httpx.Response(200,content=b'ID3fresh',request=httpx.Request('POST','https://api.typecast.ai/v1/text-to-speech'))
        request=SynthesisRequest(text='안녕하세요.',characterId='professor')
        with tempfile.TemporaryDirectory() as tmp,patch('malo_ai.providers.DATA_DIR',Path(tmp)),patch.dict('os.environ',{'TYPECAST_API_KEY':'test'},clear=True),patch('httpx.AsyncClient.post',new_callable=AsyncMock,return_value=response) as post:
            self.assertIsNone(await providers.synthesize(request,cache_only=True));post.assert_not_awaited()
            first=await providers.synthesize(request);(Path(tmp)/'audio'/(first['assetId']+'.mp3')).unlink()
            second=await providers.synthesize(request)
            self.assertFalse(second['cached']);self.assertEqual(post.await_count,2)

    async def test_concurrent_requests_generate_once_and_changed_voice_does_not_match(self):
        response=httpx.Response(200,content=b'ID3fresh',request=httpx.Request('POST','https://api.typecast.ai/v1/text-to-speech'))
        request=SynthesisRequest(text='만나서 반가워요.',characterId='girlfriend')
        with tempfile.TemporaryDirectory() as tmp,patch('malo_ai.providers.DATA_DIR',Path(tmp)),patch.dict('os.environ',{'TYPECAST_API_KEY':'test'},clear=True),patch('malo_ai.providers._tts_lock',asyncio.Lock()),patch('httpx.AsyncClient.post',new_callable=AsyncMock,return_value=response) as post:
            results=await asyncio.gather(*[providers.synthesize(request) for _ in range(5)])
            self.assertEqual(post.await_count,1);self.assertEqual(len({r['assetId'] for r in results}),1)
            with patch.dict('os.environ',{'TYPECAST_VOICE_GIRLFRIEND_CALM':'new-voice'}):
                changed=await providers.synthesize(request)
                self.assertNotEqual(changed['assetId'],results[0]['assetId']);self.assertEqual(post.await_count,2)
