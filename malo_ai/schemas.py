from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Pack = Literal["ko", "en"]
Emotion = Literal["neutral", "happy", "confused", "sad", "angry"]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Choice(Model):
    id: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=600)


class SceneNode(Model):
    id: str = Field(min_length=1, max_length=80)
    npcText: str = Field(min_length=1, max_length=800)
    goal: str = Field(min_length=1, max_length=500)
    goodExample: str = Field(min_length=1, max_length=600)
    hiddenThought: str = Field(min_length=1, max_length=400)
    tip: str = Field(min_length=1, max_length=400)
    choices: list[Choice] = Field(min_length=2, max_length=4)
    nextNodeId: str | None


class Scenario(Model):
    title: str = Field(min_length=1, max_length=100)
    situation: str = Field(min_length=1, max_length=800)
    goal: str = Field(min_length=1, max_length=500)
    pack: Pack
    characterId: str = Field(min_length=1, max_length=60)
    personalityId: str = Field(min_length=1, max_length=60)
    nodes: list[SceneNode] = Field(min_length=2, max_length=5)

    @model_validator(mode="after")
    def connected_linear_graph(self):
        ids = [node.id for node in self.nodes]
        if len(ids) != len(set(ids)):
            raise ValueError("Node IDs must be unique")
        for index, node in enumerate(self.nodes):
            expected = ids[index + 1] if index + 1 < len(ids) else None
            if node.nextNodeId != expected:
                raise ValueError("The MVP scenario must be a connected, ordered graph")
        return self


class ScenarioRequest(Model):
    mode: Literal["mock", "live"] = "mock"
    situation: str = Field(min_length=1, max_length=800)
    seed: Scenario


class AudioMetrics(Model):
    durationMs: int = Field(ge=0, le=61000)
    pauseCount: int = Field(ge=0)
    silenceRatio: float = Field(ge=0, le=1)
    fillerCount: int = Field(ge=0)
    speed: float = Field(ge=0)
    speedUnit: Literal["characters_per_minute", "words_per_minute"]
    measurement: Literal["audio_rms_and_transcript", "duration_and_transcript"]
    estimated: bool = True


class EvaluationRequest(Model):
    mode: Literal["mock", "live"] = "mock"
    pack: Pack
    characterId: str = Field(min_length=1, max_length=60)
    personalityId: str = Field(min_length=1, max_length=60)
    situation: str = Field(min_length=1, max_length=800)
    node: SceneNode
    text: str = Field(min_length=1, max_length=1200)
    history: list[dict[str, str]] = Field(default_factory=list, max_length=12)
    audioMetrics: AudioMetrics | None = None


class Grade(Model):
    outcome: Literal["correct", "misunderstanding", "clarify"]
    confidence: float = Field(ge=0, le=1)
    toneScore: int = Field(ge=0, le=100)
    toneLabel: str = Field(min_length=1, max_length=80)
    feedback: str = Field(min_length=1, max_length=400)
    betterExpression: str = Field(min_length=1, max_length=600)
    reason: str = Field(min_length=1, max_length=600)
    npcReply: str = Field(min_length=1, max_length=800)
    emotion: Emotion


class Evaluation(Grade):
    provider: str
    isMock: bool
    toneSource: Literal["text_politeness"] = "text_politeness"
    audioMetrics: AudioMetrics | None = None


class HintRequest(Model):
    node: SceneNode
    characterId: str = Field(min_length=1, max_length=60)


class SynthesisRequest(Model):
    text: str = Field(min_length=1, max_length=1400)
    pack: Pack = "ko"
    characterId: str = Field(default="professor", max_length=60)
    emotion: Emotion = "neutral"
    speed: float = Field(default=1, ge=0.5, le=1.5)


class SynthesisResult(Model):
    assetId: str
    mimeType: Literal["audio/mpeg"] = "audio/mpeg"
    cached: bool
    voice: str


class TranscriptionResult(Model):
    text: str
    audioMetrics: AudioMetrics
    provider: Literal["openai"]
    editable: Literal[True] = True


class ScenarioResult(Model):
    scenario: Scenario
    provider: str
    isMock: bool


class HintResult(Model):
    thought: str
    tip: str
    source: Literal["fictional_character_goal"]
