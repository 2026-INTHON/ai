import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from malo_ai.evaluation_prompt import evaluation_payload, persona_context
from malo_ai.providers import evaluate, mock_grade
from malo_ai.schemas import EvaluationRequest, PersonaContext
from test_pipeline import node


class DialogueContextTests(unittest.TestCase):
    def request(self, **extra):
        return EvaluationRequest(mode='live', pack='ko', characterId='girlfriend', personalityId='calm',
            situation='캠퍼스에서 처음 만남', node=node(), text='아까 제가 무슨 전공이라고 했죠?', **extra)

    def test_long_conversation_keeps_early_facts_and_questions_without_repeating_adjacent_npc_lines(self):
        history = [{'prompt': '전공이 뭐예요?', 'user': '저는 도예 전공이에요.', 'npc': '도자기를 만드는군요.'}]
        for i in range(99):
            history.append({'prompt': history[-1]['npc'], 'user': f'추가 답변 {i}', 'npc': f'반응 {i}'})
        request = self.request(history=history)
        request.node.npcText = history[-1]['npc']
        with patch('malo_ai.providers.json_completion', new_callable=AsyncMock,
                   return_value=(mock_grade(request), 'test')) as llm:
            asyncio.run(evaluate(request))
        payload = llm.call_args.args[1]
        lines = payload['history'] + [['npc', payload['npcText']]]
        self.assertEqual(lines[0], ['npc', '전공이 뭐예요?'])
        self.assertEqual(lines[1], ['learner', '저는 도예 전공이에요.'])
        self.assertEqual(len(lines), 201)
        for i, turn in enumerate(history):
            self.assertEqual(lines[2*i+1:2*i+3], [['learner', turn['user']], ['npc', turn['npc']]])

    def test_correction_restores_its_actual_prompt_and_legacy_history_is_readable(self):
        history = [dict(user='내일이요.', npc='몇 시에 볼까요?'),
                   dict(prompt='어느 날에 만날까요?', user='아니요, 모레요.', npc='모레로 바꿀게요.')]
        lines = evaluation_payload(self.request(history=history))['history']
        self.assertEqual(lines[2], ['npc', '어느 날에 만날까요?'])
        self.assertEqual(lines[3], ['learner', '아니요, 모레요.'])
        self.assertEqual(lines[-1], ['npc', '모레로 바꿀게요.'])

    def test_persona_merges_card_facts_without_losing_distinct_preferences(self):
        persona = PersonaContext(characterId='girlfriend', personalityId='calm', revision='v1', name='차분',
            short='UI 태그', description='천천히 친해져요.', dialogueRules=['차분하게 경계를 말한다.'],
            profile=dict(age='24세', role='친구', occupation='시각디자인 전공 대학생', introduction='서윤이에요.',
                relationship='첫 만남', values=['존중'], traits=['차분한'], likes=['서점'], dislikes=['재촉'],
                hobbies=['독서'], speakingStyle='해요체', sampleLines=['어떤 책 좋아하세요?']),
            cardProfile=dict(name='서윤', age='24세', occupation='시각디자인 전공 대학생', hobbies=['독서','필름 사진'],
                favoriteFoods=['국수'], dislikes=['재촉'], currentInterests=['독립출판']))
        result = persona_context(persona)
        for key, value in persona.profile.model_dump().items():
            if isinstance(value, list):
                self.assertTrue(set(value) <= set(result['profile'][key]))
            else:
                self.assertEqual(result['profile'][key], value)
        for key, value in persona.cardProfile.model_dump().items():
            if isinstance(value, list):
                self.assertTrue(set(value) <= set(result['profile'][key]))
            else:
                self.assertEqual(result['profile'][key], value)
        self.assertEqual(result['dialogueRules'], persona.dialogueRules)
        self.assertNotIn('cardProfile', result)

    def test_clear_hostility_in_other_language_keeps_x_but_language_help_keeps_retry(self):
        request = self.request()
        request.text = 'Stop bothering me, idiot.'
        for mark, outcome in [('X','misunderstanding'), ('△','clarify')]:
            result = mock_grade(request).model_copy(update={'native': True, 'evaluationMark': mark,
                'goalAchieved': False, 'confidence': .99})
            with patch('malo_ai.providers.json_completion', new_callable=AsyncMock, return_value=(result,'test')):
                grade, _ = asyncio.run(evaluate(request))
            self.assertEqual(grade.outcome, outcome)
            self.assertEqual(grade.evaluationMark, mark)
