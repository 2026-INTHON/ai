"""Register a reviewed, pre-generated WebP pose without calling an image API."""
import argparse
import hashlib
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from malo_ai import images,providers

parser=argparse.ArgumentParser()
parser.add_argument('file',type=Path)
parser.add_argument('--character',required=True,choices=list(images.CHARACTERS))
parser.add_argument('--emotion',required=True,choices=list(images.EXPRESSIONS))
parser.add_argument('--gesture',required=True,choices=['nod','tilt','thinking','open_hand','arms_crossed'])
args=parser.parse_args()
content=args.file.read_bytes()
if not(content[:4]==b'RIFF' and content[8:12]==b'WEBP'):parser.error('Provide a WebP image with the reviewed character identity and transparency.')
asset='i_'+hashlib.sha256(content).hexdigest()[:40]
destination=images.image_path(asset);destination.parent.mkdir(parents=True,exist_ok=True)
destination.write_bytes(content)
path=providers.DATA_DIR/'character-variants.json'
variants=json.loads(path.read_text(encoding='utf-8')) if path.is_file() else []
key=(args.character,args.emotion,args.gesture)
variants=[v for v in variants if (v['characterId'],v['emotion'],v['gesture'])!=key]
variants.append({'characterId':args.character,'emotion':args.emotion,'gesture':args.gesture,'assetId':asset})
temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(variants,ensure_ascii=False,indent=2),encoding='utf-8');temporary.replace(path)
print({'registered':asset,'character':args.character,'emotion':args.emotion,'gesture':args.gesture})
