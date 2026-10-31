"""Background-only blur using the FFmpeg runtime already installed for audio."""
import asyncio
import shutil
import subprocess
from fastapi import HTTPException

def _blur(content: bytes) -> bytes:
    ffmpeg=shutil.which('ffmpeg')
    if not ffmpeg:
        raise HTTPException(503,{'code':'IMAGE_PROCESSOR_UNAVAILABLE','message':'배경 이미지 처리 설정이 필요해요.','retryable':True})
    try:
        # At 1024px source width this is ~2.3px at a 390px phone viewport.
        result=subprocess.run([ffmpeg,'-v','error','-i','pipe:0','-vf','gblur=sigma=6','-frames:v','1','-f','image2pipe','-c:v','libwebp','-quality','85','pipe:1'],input=content,capture_output=True,timeout=30,check=True)
        if not result.stdout.startswith(b'RIFF'): raise ValueError('Invalid image')
        return result.stdout
    except (subprocess.SubprocessError,ValueError) as exc:
        raise HTTPException(502,{'code':'BACKGROUND_PROCESSING_FAILED','message':'배경 이미지 처리를 완료하지 못했어요.','retryable':True}) from exc

async def blur(content: bytes) -> bytes:
    return await asyncio.to_thread(_blur,content)
