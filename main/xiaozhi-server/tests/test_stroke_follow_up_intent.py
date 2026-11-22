import unittest
from types import SimpleNamespace
from unittest.mock import patch

from core.handle import intentHandler
from core.utils.stroke_query import display_character


class StrokeFollowUpIntentTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.conn = SimpleNamespace(
            cmd_exit=[], intent_type="function_call",
            func_handler=SimpleNamespace(has_tool=lambda name: name == "lookup_stroke"),
        )
        self.enterContext(patch.object(intentHandler, "checkWakeupWords", return_value=False))
        self.process = self.enterContext(patch.object(intentHandler, "process_intent_result", return_value=True))

    async def test_short_answer_uses_verified_word_and_requested_script(self):
        self.assertTrue(await intentHandler.handle_user_intent(self.conn, "祸字怎么写？", spoken=True))
        question = self.process.await_args.kwargs
        self.assertIsNone(question["confirmed_stroke"])
        self.assertIn("说词就可以", question["stroke_clarification"])

        self.assertTrue(await intentHandler.handle_user_intent(self.conn, "不劳而获。", spoken=True))
        follow_up = self.process.await_args.kwargs
        self.assertEqual(display_character(**follow_up["confirmed_stroke"]), "獲")
        self.assertIsNone(follow_up["stroke_clarification"])
        self.assertIsNone(self.conn.pending_stroke_clarification)

    async def test_unrelated_next_turn_consumes_the_context(self):
        await intentHandler.handle_user_intent(self.conn, "货字怎么写？", spoken=True)
        for text in ("今天天气真好", "不劳而获"):
            self.assertFalse(await intentHandler.handle_user_intent(self.conn, text, spoken=True))
        self.assertEqual(self.process.await_count, 1)

    async def test_expired_question_never_captures_later_conversation(self):
        await intentHandler.handle_user_intent(self.conn, "货字怎么写？", spoken=True)
        _, clarification = self.conn.pending_stroke_clarification
        self.conn.pending_stroke_clarification = (0, clarification)
        self.assertFalse(await intentHandler.handle_user_intent(self.conn, "不劳而获", spoken=True))
        self.assertIsNone(self.conn.pending_stroke_clarification)

    async def test_new_explicit_question_uses_its_own_context(self):
        await intentHandler.handle_user_intent(self.conn, "货字怎么写？", spoken=True)
        text = "課室嘅嗰個室字點樣寫㗎"
        self.assertTrue(await intentHandler.handle_user_intent(self.conn, text, spoken=True))
        self.assertEqual(display_character(**self.process.await_args.kwargs["confirmed_stroke"]), "室")
        self.assertIsNone(self.conn.pending_stroke_clarification)

    async def test_partial_phrase_after_missing_target_asks_about_the_recognized_word(self):
        self.assertTrue(await intentHandler.handle_user_intent(self.conn, "字怎么写？", spoken=True))
        self.assertIsNone(self.process.await_args.kwargs["confirmed_stroke"])
        self.assertTrue(await intentHandler.handle_user_intent(self.conn, "龙门的龙。", spoken=True))
        question = self.process.await_args.kwargs
        self.assertIsNone(question["confirmed_stroke"])
        self.assertIn("龍門，还是玲瓏", question["stroke_clarification"])

        self.assertTrue(await intentHandler.handle_user_intent(self.conn, "玲珑。", spoken=True))
        self.assertEqual(display_character(**self.process.await_args.kwargs["confirmed_stroke"]), "瓏")
        self.assertIsNone(self.conn.pending_stroke_clarification)

    async def test_short_unambiguous_school_word_answers_without_another_question(self):
        await intentHandler.handle_user_intent(self.conn, "字點寫？", spoken=True)
        self.assertTrue(await intentHandler.handle_user_intent(self.conn, "圖書館嘅館。", spoken=True))
        self.assertEqual(display_character(**self.process.await_args.kwargs["confirmed_stroke"]), "館")
        self.assertIsNone(self.conn.pending_stroke_clarification)

    async def test_partial_phrase_requires_live_spelling_context(self):
        self.assertFalse(await intentHandler.handle_user_intent(self.conn, "龙门的龙。", spoken=True))
        await intentHandler.handle_user_intent(self.conn, "字怎么写？", spoken=True)
        self.assertFalse(await intentHandler.handle_user_intent(self.conn, "这是我的书。", spoken=True))
        self.assertIsNone(self.conn.pending_stroke_clarification)
