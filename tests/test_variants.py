import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi import HTTPException
from malo_ai import images

class VariantTests(unittest.TestCase):
    def test_registered_gesture_uses_existing_asset_and_duplicate_keys_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp,patch('malo_ai.providers.DATA_DIR',Path(tmp)):
            asset='i_'+'b'*40
            image=images.image_path(asset);image.parent.mkdir();image.write_bytes(b'RIFFxxxxWEBP')
            entry={'characterId':'girlfriend','emotion':'happy','gesture':'nod','assetId':asset}
            path=Path(tmp)/'character-variants.json';path.write_text(json.dumps([entry]),encoding='utf-8')
            result=images.variants();self.assertEqual(len(result['items']),21);self.assertFalse(result['runtimeImageApiCalls'])
            self.assertEqual(result['items'][-1]['assetKey'],'characters/girlfriend/happy/nod')
            path.write_text(json.dumps([entry,entry]),encoding='utf-8')
            with self.assertRaises(HTTPException):images.variants()
