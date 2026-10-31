"""Issue short-lived transcription-only credentials; never send the project API key."""
import hashlib
import os
import httpx
from fastapi import HTTPException
from pydantic import Field
from .schemas import Model, Pack
from .providers import reserve_quota

class Request(Model):
    pack: Pack = 'ko'
    userId: str = Field(min_length=1, max_length=100)

async def create(request: Request):
    key=os.getenv('OPENAI_API_KEY')
    if not key: raise HTTPException(503, {'code':'STT_NOT_CONFIGURED','message':'음성 인식 설정이 필요해요.','retryable':False})
    reserve_quota('realtime_sessions',1,int(os.getenv('MALO_REALTIME_DAILY_SESSIONS','100')))
    session={'type':'transcription','audio':{'input':{'format':{'type':'audio/pcm','rate':24000},'transcription':{'model':'gpt-live-transcribe','languages':[request.pack],'delay':'low'},'turn_detection':None}}}
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r=await client.post('https://api.openai.com/v1/realtime/client_secrets',headers={'Authorization':'Bearer '+key,'OpenAI-Safety-Identifier':hashlib.sha256(request.userId.encode()).hexdigest()},json={'expires_after':{'anchor':'created_at','seconds':60},'session':session})
            r.raise_for_status()
        data=r.json()
        return {'value':data['value'],'expiresAt':data['expires_at'],'model':'gpt-live-transcribe','sampleRate':24000,'session':session,'websocketUrl':'wss://api.openai.com/v1/realtime?intent=transcription'}
    except (httpx.HTTPError,KeyError,ValueError) as exc:
        raise HTTPException(502,{'code':'REALTIME_STT_UNAVAILABLE','message':'실시간 음성 인식에 연결하지 못했어요. 다시 시도하거나 파일 인식을 사용해 주세요.','retryable':True}) from exc
