"""Private persistent speech registry; audio files stay in the same durable volume."""
import json
import sqlite3
from contextlib import contextmanager

@contextmanager
def database(root):
    root.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(root/'speech-cache.db',timeout=10)
    try:
        db.execute('''CREATE TABLE IF NOT EXISTS speech_assets (
            cache_key TEXT PRIMARY KEY, asset_id TEXT NOT NULL,
            provider TEXT NOT NULL, model TEXT NOT NULL, voice_id TEXT NOT NULL,
            text TEXT NOT NULL, settings_json TEXT NOT NULL,
            hits INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_used_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
        db.execute('''CREATE TABLE IF NOT EXISTS speech_tags (
            cache_key TEXT NOT NULL, character_id TEXT NOT NULL, personality_id TEXT NOT NULL,
            pack TEXT NOT NULL, emotion TEXT NOT NULL, reaction TEXT NOT NULL,
            recovery_stage TEXT NOT NULL, speed REAL NOT NULL,
            PRIMARY KEY(cache_key,character_id,personality_id,pack,emotion,reaction,recovery_stage,speed))''')
        db.execute('CREATE INDEX IF NOT EXISTS speech_voice_idx ON speech_assets(provider,voice_id)')
        db.execute('CREATE INDEX IF NOT EXISTS speech_persona_idx ON speech_tags(character_id,personality_id,emotion)')
        with db:yield db
    finally:db.close()

def find(root,key):
    with database(root) as db:
        row=db.execute('SELECT asset_id FROM speech_assets WHERE cache_key=?',(key,)).fetchone()
    return row[0] if row and (root/'audio'/(row[0]+'.mp3')).is_file() else None

def remember(root,key,asset,config,request,cached):
    with database(root) as db:
        db.execute('''INSERT INTO speech_assets(cache_key,asset_id,provider,model,voice_id,text,settings_json,hits)
          VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(cache_key) DO UPDATE SET
          asset_id=excluded.asset_id,hits=speech_assets.hits+excluded.hits,last_used_at=CURRENT_TIMESTAMP''',
          (key,asset,config['provider'],config['model'],config['voice'],config['text'],json.dumps(config,ensure_ascii=False,sort_keys=True),int(cached)))
        db.execute('INSERT OR IGNORE INTO speech_tags VALUES(?,?,?,?,?,?,?,?)',
          (key,request.characterId,request.personalityId,request.pack,request.emotion,request.reaction or '',request.recoveryStage or '',request.speed))

def stats(root):
    with database(root) as db:
        count,hits=db.execute('SELECT count(*),coalesce(sum(hits),0) FROM speech_assets').fetchone()
        tags=db.execute('SELECT count(*) FROM speech_tags').fetchone()[0]
        voices=[{'provider':p,'voiceId':v,'assets':n} for p,v,n in db.execute('SELECT provider,voice_id,count(*) FROM speech_assets GROUP BY provider,voice_id')]
    return {'assets':count,'tags':tags,'cacheHits':hits,'voices':voices}
