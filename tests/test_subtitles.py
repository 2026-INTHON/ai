import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock,patch
from fastapi import HTTPException
from malo_ai.subtitles import Request,Translations,translate
from malo_ai.providers import strict_schema
from malo_ai.schemas import Grade

class SubtitleTests(unittest.TestCase):
    def test_translation_count_cache_and_language_are_preserved(self):
        with tempfile.TemporaryDirectory() as tmp,patch('malo_ai.providers.DATA_DIR',Path(tmp)),patch('malo_ai.providers.json_completion',new_callable=AsyncMock,return_value=(Translations(texts=['Hello.','Thank you.']),'test')) as llm:
            request=Request(language='en',texts=['안녕하세요.','감사합니다.'])
            self.assertEqual(asyncio.run(translate(request))['texts'],['Hello.','Thank you.'])
            self.assertEqual(asyncio.run(translate(request))['texts'],['Hello.','Thank you.'])
            self.assertEqual(llm.await_count,1)
            self.assertEqual(llm.call_args.args[1]['language'],'en')
        with tempfile.TemporaryDirectory() as tmp,patch('malo_ai.providers.DATA_DIR',Path(tmp)),patch('malo_ai.providers.json_completion',new_callable=AsyncMock,return_value=(Translations(texts=['Hello.']),'test')):
            with self.assertRaises(HTTPException):asyncio.run(translate(request))

    def test_structured_response_schema_requires_nullable_fields_without_defaults(self):
        schema=strict_schema(Grade.model_json_schema())
        self.assertFalse(schema['additionalProperties'])
        self.assertEqual(set(schema['required']),set(schema['properties']))
        self.assertNotIn('default',schema['properties']['routeId'])
