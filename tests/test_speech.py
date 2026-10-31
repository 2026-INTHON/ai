import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import HTTPException

from malo_ai.providers import synthesize
from malo_ai.schemas import SynthesisRequest


class SpeechTests(unittest.IsolatedAsyncioTestCase):
    async def test_typecast_uses_catalogued_young_female_conversation_voices_and_emotional_presets(self):
        response=httpx.Response(200,content=b'ID3'+bytes(100),request=httpx.Request('POST','https://api.typecast.ai/v1/text-to-speech'))
        with tempfile.TemporaryDirectory() as tmp,patch('malo_ai.providers.DATA_DIR',Path(tmp)),patch.dict('os.environ',{'TYPECAST_API_KEY':'test-key','MALO_GIRLFRIEND_TTS_PROVIDER':'typecast'}),patch('httpx.AsyncClient.post',new_callable=AsyncMock,return_value=response) as post:
            seen=set()
            for personality in ['playful','calm','strict']:
                request=SynthesisRequest(text='이번 주말에 하고 싶은 거 있어?',characterId='girlfriend',personalityId=personality)
                result=await synthesize(request);seen.add(result['voice'])
                payload=post.call_args.kwargs['json'];self.assertEqual(payload['model'],'ssfm-v31');self.assertEqual(payload['language'],'kor');self.assertEqual(payload['text'],request.text);self.assertEqual(payload['output']['audio_format'],'mp3')
                self.assertEqual(payload['prompt']['emotion_preset'],'toneup' if personality=='playful' else 'normal')
                self.assertTrue((await synthesize(request))['cached'])
            self.assertEqual(len(seen),3);self.assertEqual(post.await_count,3)
            await synthesize(SynthesisRequest(text='정말 너무해.',characterId='girlfriend',emotion='sad',reaction='sobbing'))
            self.assertEqual(post.call_args.kwargs['json']['prompt']['emotion_preset'],'sad');self.assertGreater(post.call_args.kwargs['json']['prompt']['emotion_intensity'],1.5)

    async def test_girlfriend_personality_emotion_and_reaction_control_voice_and_cache(self):
        response = httpx.Response(200, content=b"ID3" + bytes(100), request=httpx.Request("POST", "https://api.openai.com/v1/audio/speech"))
        with tempfile.TemporaryDirectory() as tmp, patch("malo_ai.providers.DATA_DIR", Path(tmp)), patch.dict("os.environ", {"OPENAI_API_KEY": "test-key", "MALO_OPENAI_TTS_DAILY_CHAR_LIMIT": "1000"}), patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=response) as post:
            ids = set()
            for personality, voice in [("playful", "coral"), ("calm", "marin"), ("strict", "sage")]:
                request = SynthesisRequest(text="이번 주말에 시간 있어?", characterId="girlfriend", personalityId=personality, emotion="happy")
                result = await synthesize(request)
                self.assertEqual(result["voice"], voice)
                payload = post.call_args.kwargs["json"]
                self.assertEqual(payload["input"], request.text)
                self.assertEqual(payload["voice"], voice)
                self.assertIn("young adult woman", payload["instructions"])
                self.assertIn("native Korean", payload["instructions"])
                self.assertIn("pleased", payload["instructions"])
                self.assertEqual((await synthesize(request))["cached"], True)
                ids.add(result["assetId"])
            self.assertEqual(len(ids), 3)
            self.assertEqual(post.await_count, 3)
            for emotion, reaction, direction in [("angry", "contempt", "Cold contempt"), ("sad", "sobbing", "Tearful"), ("confused", None, "Puzzled")]:
                request = SynthesisRequest(text="어떻게 그런 말을 할 수가 있어?", characterId="girlfriend", emotion=emotion, reaction=reaction)
                result = await synthesize(request)
                self.assertIn(direction, post.call_args.kwargs["json"]["instructions"])
                self.assertNotIn(result["assetId"], ids)
                ids.add(result["assetId"])

    async def test_paid_limit_and_provider_failure_do_not_silently_use_narrator_voice(self):
        response = httpx.Response(429, request=httpx.Request("POST", "https://api.openai.com/v1/audio/speech"))
        with tempfile.TemporaryDirectory() as tmp, patch("malo_ai.providers.DATA_DIR", Path(tmp)), patch.dict("os.environ", {"OPENAI_API_KEY": "test-key", "MALO_OPENAI_TTS_DAILY_CHAR_LIMIT": "10"}), patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=response) as post:
            with self.assertRaises(HTTPException) as error:
                await synthesize(SynthesisRequest(text="안녕", characterId="girlfriend"))
            self.assertEqual(error.exception.status_code, 502)
            self.assertEqual(post.await_count, 1)
            with self.assertRaises(HTTPException) as error:
                await synthesize(SynthesisRequest(text="한도를 넘는 새로운 긴 문장입니다.", characterId="girlfriend"))
            self.assertEqual(error.exception.status_code, 429)
            self.assertEqual(post.await_count, 1)

    async def test_other_characters_keep_azure_voice_and_cache(self):
        response = httpx.Response(200, content=b"ID3" + bytes(100), request=httpx.Request("POST", "https://azure.test"))
        with tempfile.TemporaryDirectory() as tmp, patch("malo_ai.providers.DATA_DIR", Path(tmp)), patch.dict("os.environ", {"AZURE_SPEECH_KEY": "test-key"}), patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=response) as post, patch("malo_ai.providers.asyncio.sleep", new_callable=AsyncMock):
            request = SynthesisRequest(text="다음 주에 오세요.", characterId="professor")
            result = await synthesize(request)
            self.assertEqual(result["voice"], "ko-KR-InJoonNeural")
            self.assertIn(b"ko-KR-InJoonNeural", post.call_args.kwargs["content"])
            self.assertEqual((await synthesize(request))["cached"], True)
            self.assertEqual(post.await_count, 1)
