import asyncio
import io
import tempfile
import unittest
import threading
from pathlib import Path
from unittest.mock import patch
from fastapi import HTTPException
from PIL import Image
from malo_ai import exports
from malo_ai.providers import typecast_voice
from malo_ai.schemas import SynthesisRequest

class ExportTests(unittest.TestCase):
    def test_pdf_does_not_wait_for_video_and_duplicate_video_renders_once(self):
        async def run():
            started=threading.Event();release=threading.Event();calls=[]
            def video(request,path,assets):
                calls.append('video');started.set();release.wait(5);path.write_bytes(b'video');return 10
            def pdf(request,path):
                calls.append('pdf');path.write_bytes(b'%PDF')
            request=exports.ExportRequest(exportId='12345678-1234-1234-1234-123456789012',format='video',title='Replay')
            with tempfile.TemporaryDirectory() as tmp,patch.object(exports.providers,'DATA_DIR',Path(tmp)),patch.object(exports,'render_video',video),patch.object(exports,'render_pdf',pdf),patch.object(exports,'_render_locks',{'video':asyncio.Lock(),'pdf':asyncio.Lock()}):
                first=asyncio.create_task(exports.render(request));duplicate=asyncio.create_task(exports.render(request))
                try:
                    await asyncio.to_thread(started.wait,2)
                    result=await asyncio.wait_for(exports.render(request.model_copy(update={'format':'pdf'})),1)
                    self.assertEqual(result['mimeType'],'application/pdf');self.assertFalse(first.done())
                finally:release.set()
                a,b=await asyncio.gather(first,duplicate)
                self.assertEqual(a,b);self.assertEqual(calls.count('video'),1)
        asyncio.run(run())

    def test_english_captions_wrap_at_word_boundaries(self):
        font=exports.ImageFont.truetype(str(exports.FONT),25)
        text='When can you submit the assignment?'
        lines=exports.wrapped(text,font,220)
        self.assertEqual(''.join(lines),text)
        self.assertTrue(all(line.endswith(' ') for line in lines[:-1]))

    def test_foreign_assets_and_path_traversal_are_rejected(self):
        for url in ['http://127.0.0.1/admin','https://example.com/image.png','https://bihmoysircqrbhljywlt.supabase.co.evil.test/storage/v1/object/public/x']:
            with self.assertRaises(HTTPException):asyncio.run(exports.image_bytes(url))
        with self.assertRaises(HTTPException):exports.file_path('../../secrets')

    def test_fullbody_contained_long_dialogue_paginated_and_pdf_written(self):
        actor=Image.new('RGBA',(100,600),'blue')
        actor.paste('red',(0,0,100,60));data=io.BytesIO();actor.save(data,format='PNG')
        req=exports.ExportRequest(exportId='12345678-1234-1234-1234-123456789012',format='video',title='첫 만남 / 初めまして / 初次见面',frames=[])
        frame=exports.ReplayFrame(speaker='npc',name='서윤',text='서로의 관심사를 이야기해요. '*80,imageUrl='actor')
        pages=list(exports.cards(req,frame,{'actor':data.getvalue()}))
        self.assertGreater(len(pages),1)
        # Head pixels remain visible on every page, including the longest text layout.
        self.assertTrue(all(any(r>200 and g<30 and b<30 for r,g,b in p.getdata()) for p in pages))
        self.assertEqual(''.join(exports.wrapped(frame.text,exports.ImageFont.truetype(str(exports.FONT),25),444)),frame.text)
        with tempfile.TemporaryDirectory() as tmp:
            req.format='pdf';req.sections=[exports.ReportSection(title='문화 팁 / 文化のヒント / 文化提示',lines=['정중하게 이야기했어요. 相手に丁寧に話しました。 礼貌地表达了想法。']*10)]*8
            path=Path(tmp)/'report.pdf';exports.render_pdf(req,path)
            self.assertTrue(path.read_bytes().startswith(b'%PDF'));self.assertGreater(path.stat().st_size,10000)

    def test_recovery_keeps_voice_identity_without_cheerful_preset(self):
        for character in ['girlfriend','professor']:
            bright=SynthesisRequest(text='알겠어요.',characterId=character,personalityId='playful',emotion='neutral')
            v,p,_=typecast_voice(bright);v2,p2,_=typecast_voice(bright.model_copy(update={'recoveryStage':'softening'}))
            self.assertEqual(v,v2);self.assertEqual(p['emotion_preset'],'toneup');self.assertEqual(p2['emotion_preset'],'normal')
            angry=bright.model_copy(update={'emotion':'angry','recoveryStage':'guarded'})
            self.assertLessEqual(typecast_voice(angry)[1]['emotion_intensity'],.65)
