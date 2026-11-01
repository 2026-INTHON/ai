"""Private replay videos and reports from recorded data; no new dialogue generation."""
import asyncio
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse
from xml.sax.saxutils import escape

import httpx
from fastapi import HTTPException
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter
from pydantic import Field
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from . import providers, images
from .schemas import Model

FONT=Path(__file__).parent/'assets/fonts/NotoSansKR.ttf'
_render_locks={'video':asyncio.Lock(),'pdf':asyncio.Lock()}

class ReplayFrame(Model):
    speaker: Literal['npc','learner','score']
    name: str = Field(max_length=100)
    text: str = Field(max_length=4000)
    subtitle: str = Field(default='',max_length=2000)
    imageUrl: str | None = Field(default=None,max_length=2000)
    audioAssetId: str | None = Field(default=None,pattern=r'^a_[a-f0-9]{40}$')
    mark: str = Field(default='',max_length=1)
    lives: int = Field(default=3,ge=0,le=3)
    progress: str = Field(default='',max_length=30)
    emotion: Literal['neutral','happy','angry','sad','confused'] = 'neutral'
    action: str | None = Field(default=None,max_length=500)
    cues: list[str] | None = Field(default=None,max_length=5)

class ReportSection(Model):
    title: str = Field(max_length=200)
    lines: list[str] = Field(max_length=20)

class ExportRequest(Model):
    exportId: str = Field(pattern=r'^[a-f0-9-]{36}$')
    format: Literal['video','pdf']
    title: str = Field(max_length=200)
    subtitle: str = Field(default='',max_length=300)
    backgroundUrl: str | None = Field(default=None,max_length=2000)
    frames: list[ReplayFrame] = Field(default_factory=list,max_length=302)
    sections: list[ReportSection] = Field(default_factory=list,max_length=810)

def file_path(asset_id):
    if not re.fullmatch(r'e_[a-f0-9]{40}\.(mp4|pdf)',asset_id):
        raise HTTPException(404,{'code':'EXPORT_NOT_FOUND','message':'파일을 찾지 못했어요.','retryable':False})
    return providers.DATA_DIR/'exports'/asset_id

async def image_bytes(url):
    if not url:return None
    # Only saved app assets and this project's public storage; no arbitrary URL fetching.
    p=urlparse(url)
    if p.path.startswith('/api/v1/images/') and re.fullmatch(r'i_[a-f0-9]{40}',p.path.rsplit('/',1)[-1]):
        path=images.image_path(p.path.rsplit('/',1)[-1])
        if path.is_file():return path.read_bytes()
    allowed_storage=p.scheme=='https' and p.hostname=='bihmoysircqrbhljywlt.supabase.co' and p.path.startswith('/storage/v1/object/public/')
    public=urlparse(os.getenv('MALO_PUBLIC_BASE_URL','https://inthon-demo-20261031-dh.koreacentral.cloudapp.azure.com'))
    allowed_app=(not p.netloc or p.hostname==public.hostname) and re.fullmatch(r'/api/v1/catalog-assets/[a-zA-Z0-9_-]+\.png',p.path)
    if not (allowed_storage or allowed_app):
        raise HTTPException(422,{'code':'EXPORT_ASSET_INVALID','message':'내보낼 이미지 주소를 확인해 주세요.','retryable':False})
    target=url if allowed_storage else public.geturl().rstrip('/')+p.path
    async with httpx.AsyncClient(timeout=20,follow_redirects=False) as client:
        async with client.stream('GET',target) as response:
            response.raise_for_status()
            content=bytearray()
            async for chunk in response.aiter_bytes():
                content.extend(chunk)
                if len(content)>16*1024*1024:raise ValueError('Image too large')
    return bytes(content)

def wrapped(text,font,width):
    lines=[]
    for paragraph in text.split('\n'):
        line=''
        for token in re.findall(r"[A-Za-z0-9]+(?:['’.-][A-Za-z0-9]+)*|\s+|.",paragraph):
            if not token.isspace() and line and font.getlength(line+token)>width:lines.append(line);line=''
            for char in token:
                if not char.isspace() and line and font.getlength(line+char)>width:lines.append(line);line=''
                line+=char
        lines.append(line)
    return lines or ['']

def cards(request,frame,assets):
    regular=ImageFont.truetype(str(FONT),25);small=ImageFont.truetype(str(FONT),19)
    lines=[(line,False) for line in wrapped(frame.text,regular,444)]
    if frame.subtitle:lines +=[(line,True) for line in wrapped(frame.subtitle,small,444)]
    for cue in ([frame.action] if frame.action else [])+(frame.cues or []):
        lines += [(line,True) for line in wrapped(cue,small,444)]
    pages=[lines[i:i+11] for i in range(0,len(lines),11)]
    for page,chunk in enumerate(pages):
        im=Image.new('RGB',(540,960),'#F3F2EE')
        if request.backgroundUrl and assets.get(request.backgroundUrl):
            bg=Image.open(io.BytesIO(assets[request.backgroundUrl])).convert('RGB')
            im=ImageOps.fit(bg,(540,960)).filter(ImageFilter.GaussianBlur(3))
        d=ImageDraw.Draw(im)
        d.rounded_rectangle((18,18,522,125),radius=20,fill='#FFFFFF')
        title='\n'.join(wrapped(request.title,small,450)[:2]);d.multiline_text((36,27),title,font=small,fill='#111111',spacing=3)
        d.text((36,76),'Malo · '+request.subtitle[:30],font=ImageFont.truetype(str(FONT),13),fill='#6B6B6B')
        d.text((36,101),frame.progress,font=ImageFont.truetype(str(FONT),14),fill='#111111')
        for i in range(3):d.ellipse((448+i*19,104,459+i*19,115),fill='#FF4FA3' if i<frame.lives else '#DDDDDD')
        height=64+sum(28 if sub else 35 for _,sub in chunk)
        top=860-height
        if frame.imageUrl and assets.get(frame.imageUrl):
            actor=Image.open(io.BytesIO(assets[frame.imageUrl])).convert('RGBA')
            actor=ImageOps.contain(actor,(490,max(160,top-140)))
            im.paste(actor,((540-actor.width)//2,136),actor)
        d=ImageDraw.Draw(im)
        dark=frame.speaker=='learner';fill='#111111' if dark else '#FFFFFF'
        d.rounded_rectangle((24,top,516,864),radius=24,fill=fill)
        d.text((44,top+15),frame.name,font=small,fill='#D4FF4F' if dark else '#111111')
        if frame.mark:
            d.ellipse((464,top+10,500,top+46),fill='#D4FF4F',outline='#111111',width=2)
            d.text((473,top+12),frame.mark,font=small,fill='#111111')
        y=top+49
        for line,sub in chunk:
            d.text((44,y),line,font=small if sub else regular,fill=('#CFCFCF' if dark else '#6B6B6B') if sub else ('white' if dark else '#111111'))
            y+=28 if sub else 35
        # Whole scene composition, including familiar conversation controls.
        d.ellipse((238,883,302,947),fill='#D4FF4F' if dark else '#111111')
        ink='#111111' if dark else '#D4FF4F'
        d.rounded_rectangle((263,897,277,921),radius=7,outline=ink,width=2)
        d.arc((258,908,282,929),0,180,fill=ink,width=2);d.line((270,929,270,937),fill=ink,width=2)
        for x in (103,413):
            d.ellipse((x-23,892,x+23,938),fill='#FFFFFF')
            for y in (906,914,922):d.line((x-9,y,x+9,y),fill='#111111',width=2)
        if len(pages)>1:d.text((459,942),f'{page+1}/{len(pages)}',font=ImageFont.truetype(str(FONT),12),fill='#6B6B6B')
        yield im

def command(args,timeout=180):
    result=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout)
    if result.returncode:raise RuntimeError('Media renderer failed')
    return result.stdout

def render_video(request,path,assets):
    with tempfile.TemporaryDirectory(dir=path.parent) as directory:
        temp=Path(directory);manifest=[];total=0.;count=0
        with wave.open(str(temp/'audio.wav'),'wb') as track:
            track.setnchannels(1);track.setsampwidth(2);track.setframerate(24000)
            for frame in request.frames:
                pages=list(cards(request,frame,assets));pcm=b''
                if frame.audioAssetId:
                    audio=providers.DATA_DIR/'audio'/(frame.audioAssetId+'.mp3')
                    if not audio.is_file():raise FileNotFoundError('Recorded speech missing')
                    pcm=command(['ffmpeg','-v','error','-i',str(audio),'-f','s16le','-ar','24000','-ac','1','pipe:1'],60)
                duration=max(len(pcm)/48000+.5,4.0 if frame.speaker=='score' else 3.0,len(frame.text)/10,len(pages)*3.0)
                total+=duration
                if total>1800:raise ValueError('Replay exceeds 30 minutes')
                track.writeframesraw(pcm)
                track.writeframesraw(b'\0'*max(0,int(duration*24000)*2-len(pcm)))
                for im in pages:
                    name=f'frame-{count:04}.png';im.save(temp/name,compress_level=1);count+=1
                    manifest += [f"file '{name}'",f'duration {duration/len(pages):.6f}']
        manifest += [f"file 'frame-{count-1:04}.png'"]
        (temp/'frames.txt').write_text('\n'.join(manifest),encoding='utf-8')
        # Scene cards are still images; six frames/s keeps transitions within 167ms
        # while avoiding encoding twelve copies of the same screen every second.
        command(['ffmpeg','-v','error','-y','-f','concat','-safe','1','-i',str(temp/'frames.txt'),'-i',str(temp/'audio.wav'),'-t',str(total),'-vf','fps=6','-c:v','libx264','-preset','veryfast','-crf','24','-pix_fmt','yuv420p','-threads','1','-c:a','aac','-b:a','64k','-movflags','+faststart',str(path)],220)
        return round(total,2)

def render_pdf(request,path):
    if 'Malo' not in pdfmetrics.getRegisteredFontNames():pdfmetrics.registerFont(TTFont('Malo',str(FONT)))
    body=ParagraphStyle('body',fontName='Malo',fontSize=10,leading=16,wordWrap='CJK',textColor=colors.HexColor('#111111'),spaceAfter=6)
    heading=ParagraphStyle('heading',parent=body,fontSize=13,leading=20,spaceBefore=15,spaceAfter=8,keepWithNext=True)
    title=ParagraphStyle('title',parent=body,fontSize=22,leading=30,spaceAfter=14)
    def p(text,style=body):return Paragraph(escape(text).replace('\n','<br/>'),style)
    flow=[p('Malo · '+request.title,title),p(request.subtitle),Spacer(1,10)]
    for section in request.sections:
        flow.append(p(section.title,heading))
        flow.extend(p(line) for line in section.lines)
    def footer(canvas,doc):
        canvas.setFont('Malo',8);canvas.setFillColor(colors.HexColor('#6B6B6B'));canvas.drawString(42,23,'Malo');canvas.drawRightString(553,23,str(doc.page))
    SimpleDocTemplate(str(path),pagesize=(595,842),rightMargin=42,leftMargin=42,topMargin=42,bottomMargin=42,title=request.title,author='Malo').build(flow,onFirstPage=footer,onLaterPages=footer)

async def render(request:ExportRequest):
    digest=hashlib.sha256(('replay-v3:'+request.model_dump_json()).encode()).hexdigest()[:40]
    asset=f'e_{digest}.'+('mp4' if request.format=='video' else 'pdf');path=file_path(asset)
    # A PDF must not wait for a multi-minute video. Keep duplicate work serialized
    # within each format so retries cannot race the same output file.
    async with _render_locks[request.format]:
        if not path.is_file():
            path.parent.mkdir(parents=True,exist_ok=True)
            if shutil.disk_usage(path.parent).free<500*1024*1024:raise HTTPException(507,{'code':'EXPORT_STORAGE_FULL','message':'내보내기 저장 공간이 부족해요.','retryable':True})
            urls={f.imageUrl for f in request.frames if f.imageUrl}|({request.backgroundUrl} if request.backgroundUrl else set())
            assets={}
            if request.format=='video':
                semaphore=asyncio.Semaphore(4)
                async def load(url):
                    async with semaphore:return url,await image_bytes(url)
                assets=dict(await asyncio.gather(*(load(url) for url in urls)))
            temporary=path.with_name(path.stem+'.pending'+path.suffix)
            try:
                duration=await asyncio.to_thread(render_video,request,temporary,assets) if request.format=='video' else None
                if request.format=='pdf':await asyncio.to_thread(render_pdf,request,temporary)
                temporary.replace(path)
                path.with_suffix('.json').write_text(json.dumps({'durationSeconds':duration}),encoding='utf-8')
            finally:temporary.unlink(missing_ok=True)
        meta=json.loads(path.with_suffix('.json').read_text()) if path.with_suffix('.json').is_file() else {}
        return {'assetId':asset,'mimeType':'video/mp4' if request.format=='video' else 'application/pdf','bytes':path.stat().st_size,**meta}
