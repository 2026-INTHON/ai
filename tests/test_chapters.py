import asyncio
import unittest
from unittest.mock import AsyncMock, patch
from fastapi import HTTPException
from pydantic import ValidationError
from malo_ai.chapters import ChapterRequest, Lesson, Outline, outline, lesson, LessonRequest
from test_pipeline import node
from malo_ai.learning_policy import DIALOGUE_STYLE

class ChapterTests(unittest.TestCase):
    def test_bounded_routes_reject_broken_edges_and_wrong_overrides(self):
        nodes=[node('n'+str(i),'n'+str(i+1) if i<7 else None) for i in range(8)]
        for n in nodes:
            n.update(cues=[{'k':'표정','v':'미소'}],clue=[{'k':'주목 표현','v':'무엇을 확인하는가'}],views=[{'who':'교수님','meaning':'감사합니다.','cue':'정중히'},{'who':'친구','meaning':'고마워.','cue':'편하게'}])
        data={'title':'인사','situation':'첫 면담','goal':'인사하기','nodes':nodes,'routes':[{'id':id,'label':id,'overrides':[{'nodeId':n['id'],'npcText':n['npcText'],'goodExample':n['goodExample'],'hiddenThought':n['hiddenThought']} for n in nodes[3:6]]} for id in ('direct','considerate')],'endings':[{'id':id,'kind':'happy' if id=='happy' else 'bad','title':id,'text':'대화를 마칩니다.'} for id in ('happy','deferred','breakdown')]}
        Lesson(**data)
        data['routes'][0]['overrides'][0]['nodeId']='unknown'
        with self.assertRaises(ValidationError): Lesson(**data)

    def test_safety_failure_stops_generation_and_count_is_enforced(self):
        request=ChapterRequest(prompt='교수님과 첫 인사',characterId='professor',personalityId='calm',persona={},lessonCount=3)
        with patch('malo_ai.chapters.moderate',new_callable=AsyncMock,side_effect=HTTPException(422,'blocked')),patch('malo_ai.providers.json_completion',new_callable=AsyncMock) as llm:
            with self.assertRaises(HTTPException): asyncio.run(outline(request))
            llm.assert_not_called()
        topic={'title':'인사','goal':'자기소개','situation':'첫 면담'}
        bad=Outline(title='인사',summary='면담',continuity='소개',background='연구실',existingBackground='office',lessons=[topic,topic])
        with patch('malo_ai.chapters.moderate',new_callable=AsyncMock),patch('malo_ai.providers.json_completion',new_callable=AsyncMock,return_value=(bad,'test')) as llm:
            with self.assertRaises(HTTPException): asyncio.run(outline(request))
            self.assertIn(DIALOGUE_STYLE,llm.call_args.args[2])
