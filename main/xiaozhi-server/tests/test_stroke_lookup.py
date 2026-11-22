import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from core.handle import intentHandler
from core.providers.asr.base import ASRProviderBase
from core.providers.tools.device_mcp import MCPClient
from core.providers.tools.server_plugins import ServerPluginExecutor
from core.providers.tts.dto.dto import ContentType, SentenceType
from core.utils.dialogue import Dialogue
from core.utils.stroke_query import (
    display_character, get_stroke_clarification, looks_like_stroke_query,
    parse_stroke_follow_up, parse_stroke_query, to_simplified,
)
from plugins_func.functions import lookup_stroke
from plugins_func.register import Action


class StrokeQueryTests(unittest.TestCase):
    def test_explicit_and_contextual_requests(self):
        cases = {
            "努力的努字怎么写？": "努",
            "努力的弩字怎么写？": "努",
            "小智，请问龙的繁体字怎么写？": "龍",
            "繁體字的「龍」字怎麼寫？": "龍",
            "努力嘅努字點寫？": "努",
            "烏龜的歸字怎麼寫？": "龜",
            "龍字的筆順是什麼？": "龍",
            "海洋的洋字怎么写？": "洋",
            "教我寫愛字": "愛",
            "國字的簡體怎麼寫？": "国",
            "头发的发字怎么写？": "髮",
            "出发的发字怎么写？": "發",
            "皇后的后字怎么写？": "后",
            "前后的后字怎么写？": "後",
            "松树的松字怎么写？": "松",
            "放松的松字怎么写？": "鬆",
            "不劳而获的获字怎么写？": "獲",
            "不劳而获的货字怎么写？": "獲",
            "不勞而獲的惑字怎麼寫？": "獲",
            "收获的获字怎么写？": "穫",
            "发字的繁体怎么写？": None,
        }
        for query, expected in cases.items():
            with self.subTest(query=query):
                args = parse_stroke_query(query)
                self.assertIsNotNone(args)
                self.assertEqual(display_character(**args), expected)

    def test_ambiguous_asr_and_conversation_fall_through(self):
        for query in ("道路的怒字怎么写？", "写一篇关于努力的故事", "我想玩跑团游戏", "你怎么看？"):
            with self.subTest(query=query):
                self.assertIsNone(parse_stroke_query(query))

    def test_long_homophones_keep_the_word_and_requested_script(self):
        for query, expected in (
            ("玲珑的珑字怎么写？", "瓏"),
            ("珑门的珑字怎么写？", "瓏"),
            ("玲瓏的瓏字用简体怎么写？", "珑"),
            ("龙门的龙字怎么写？", "龍"),
        ):
            with self.subTest(query=query):
                self.assertEqual(display_character(**parse_stroke_query(query, spoken=True)), expected)

    def test_huo_context_survives_asr_confusions_and_short_fragment(self):
        cases = {
            "而获的祸字怎么写？": "而获",
            "不劳而祸的祸字怎么写？": "不劳而获",
            "不劳而霍的霍字怎么写？": "不劳而获",
            "不劳而霍霍的霍字怎么写？": "不劳而获",
            "小智，请问不老尔。而获的，祸字，怎么写？": "不劳而获",
            "不劳而获的那个货字怎么写？": "不劳而获",
            "不勞而獲的貨字怎麼寫？": "不勞而獲",
        }
        for query, expected_context in cases.items():
            with self.subTest(query=query):
                args = parse_stroke_query(query, spoken=True)
                self.assertIsNotNone(args)
                self.assertEqual(args["context_phrase"], expected_context)
                self.assertEqual(display_character(**args), "獲")
        self.assertFalse(looks_like_stroke_query("不老尔。"))
        self.assertEqual(
            display_character(**parse_stroke_query("不劳而祸的祸字怎么写？")), "禍"
        )

    def test_pronunciation_dictionary_uses_the_word_reading(self):
        args = parse_stroke_query("你知道银行的杭字怎么写吗？", spoken=True)
        self.assertIsNotNone(args)
        self.assertEqual(args["character"], "行")
        args = parse_stroke_query("花园的圆字怎么写？", spoken=True)
        self.assertIsNotNone(args)
        self.assertEqual(display_character(**args), "園")

    def test_spoken_literal_is_ambiguous_when_context_has_another_homophone(self):
        request = "他们和她们的他字怎么写？"
        self.assertEqual(parse_stroke_query(request)["character"], "他")
        self.assertIsNone(parse_stroke_query(request, spoken=True))
        self.assertTrue(looks_like_stroke_query(request))

    def test_cantonese_word_and_numbered_requests_resolve_directly(self):
        cases = {
            "課室嘅嗰個室字點樣寫㗎？": "室",
            "學校個學字點樣寫吖？": "學",
            "幫我睇吓書包嘅包字": "包",
            "練習簿嘅第二個字點樣寫㗎？": "習",
            "圖書館的最後一個字怎麼寫？": "館",
            "圖書館的最後一個字的簡體怎麼寫？": "馆",
        }
        for request, expected in cases.items():
            with self.subTest(request=request):
                args = parse_stroke_query(request, spoken=True)
                self.assertIsNotNone(args)
                self.assertEqual(display_character(**args), expected)
        self.assertIsNone(parse_stroke_query("這個成語的最後一個字點寫？", spoken=True))
        self.assertIsNone(parse_stroke_query("圖書館的第九個字怎麼寫？", spoken=True))

    def test_numbered_request_requires_an_explicit_word(self):
        for request in (
            "我的名字的第一个字怎么写？",
            "刚才你说的第一个字怎么写？",
            "这两个字的第一个字怎么写？",
            "你說的那三個字最後一個字點樣寫？",
        ):
            with self.subTest(request=request):
                self.assertTrue(looks_like_stroke_query(request, spoken=True))
                self.assertIsNone(parse_stroke_query(request, spoken=True))
                clarification = get_stroke_clarification(request, spoken=True)
                self.assertIn("第几个字", clarification.prompt)
                self.assertIsNone(parse_stroke_follow_up("圖書館", clarification))

    def test_single_near_tone_in_known_school_word_resolves_directly(self):
        args = parse_stroke_query("課室的棵字怎么写？", spoken=True)
        self.assertIsNotNone(args)
        self.assertEqual(display_character(**args), "課")
        self.assertIsNone(parse_stroke_query("課桌的棵字怎么写？", spoken=True))

    def test_short_follow_up_uses_the_matching_word_and_leaves_chat_alone(self):
        clarification = get_stroke_clarification("市字怎么写？", spoken=True)
        self.assertIn("課室", clarification.prompt)
        self.assertIn("说词就可以", clarification.prompt)
        for answer, expected in (("課室", "室"), ("市場", "市"), ("是試卷裡的", "試")):
            with self.subTest(answer=answer):
                args = parse_stroke_follow_up(answer, clarification)
                self.assertIsNotNone(args)
                self.assertEqual(display_character(**args), expected)
        self.assertIsNone(parse_stroke_follow_up("我想听故事", clarification))

        clarification = get_stroke_clarification("貨字怎麼寫？", spoken=True)
        args = parse_stroke_follow_up("不勞而獲", clarification)
        self.assertIsNotNone(args)
        self.assertEqual(display_character(**args), "獲")

    def test_short_follow_up_ignores_spoken_particles_and_pointing_words(self):
        clarification = get_stroke_clarification("发字怎么写？", spoken=True)
        for answer in ("頭髮呀", "頭髮那個", "頭髮呢個呀", "係頭髮嗰個字囉", "就是頭髮啊"):
            with self.subTest(answer=answer):
                args = parse_stroke_follow_up(answer, clarification)
                self.assertIsNotNone(args)
                self.assertEqual(args["context_phrase"], "頭髮")
                self.assertEqual(display_character(**args), "髮")
        self.assertIsNone(parse_stroke_follow_up("讲个故事啦", clarification))
        request = "努力和愤怒的怒字怎么写？"
        self.assertIsNone(parse_stroke_query(request, spoken=True))
        self.assertTrue(looks_like_stroke_query(request))


class StrokeToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_tool_sends_gif_on_connection_loop_and_uses_local_poem(self):
        with TemporaryDirectory() as folder, patch.dict(
            "os.environ", {"STROKE_ASSET_DIRECTORY": folder}
        ):
            (Path(folder) / "52aa.gif").touch()
            conn = SimpleNamespace(config={}, mcp_client=MCPClient())
            sent = []
            connection_loop = asyncio.get_running_loop()

            async def send(data):
                self.assertIs(asyncio.get_running_loop(), connection_loop)
                payload = json.loads(data)["payload"]
                sent.append(payload)
                await conn.mcp_client.resolve_call_result(
                    payload["id"], {"isError": False, "content": [{"type": "text", "text": "true"}]}
                )

            conn.websocket = SimpleNamespace(send=send)
            result = await lookup_stroke.show_confirmed_stroke(
                conn, **parse_stroke_query("努力的努字怎么写？")
            )

        self.assertIs(result.action, Action.RESPONSE)
        self.assertIn("少壮不努力，老大徒伤悲", result.response)
        self.assertEqual(len(sent), 1)
        self.assertGreater(sent[0]["id"], 2)
        self.assertEqual(sent[0]["params"], {
            "name": "self.screen.preview_image",
            "arguments": {"url": f"{lookup_stroke.DEFAULT_IMAGE_BASE_URL}/52aa.gif"},
        })
        self.assertEqual(conn.mcp_client.call_results, {})

    async def test_missing_asset_and_no_mcp_are_spoken_without_sending(self):
        with TemporaryDirectory() as folder:
            conn = SimpleNamespace(
                config={"character_lookup": {"asset_directory": folder}},
                mcp_client=MCPClient(),
                websocket=SimpleNamespace(send=AsyncMock()),
            )
            missing = await lookup_stroke.show_confirmed_stroke(conn, "龍")
            self.assertIn("暂时找不到", missing.response)
            conn.mcp_client = None
            no_mcp = await lookup_stroke.show_confirmed_stroke(conn, "努")
            self.assertIn("不能显示", no_mcp.response)
            conn.websocket.send.assert_not_awaited()

    async def test_asset_url_override_and_png_fallback(self):
        with TemporaryDirectory() as folder:
            (Path(folder) / "9f8d.png").touch()
            conn = SimpleNamespace(config={"character_lookup": {
                "image_base_url": "http://192.0.2.4/strokes/",
                "asset_directory": folder,
            }}, mcp_client=MCPClient())
            with patch.object(lookup_stroke, "_preview_image", new_callable=AsyncMock) as preview:
                result = await lookup_stroke.show_confirmed_stroke(conn, "龙")
            preview.assert_awaited_once()
            self.assertEqual(preview.await_args.args[:2], (conn, "http://192.0.2.4/strokes/9f8d.png"))
            self.assertIn("龍", result.result)

    async def test_mcp_timeout_cleans_up_the_future(self):
        with TemporaryDirectory() as folder:
            (Path(folder) / "52aa.gif").touch()
            conn = SimpleNamespace(
                config={"character_lookup": {"asset_directory": folder}},
                mcp_client=MCPClient(),
                websocket=SimpleNamespace(send=AsyncMock()),
            )
            with patch.object(lookup_stroke, "MCP_TIMEOUT_SECONDS", 0.01):
                result = await lookup_stroke.show_confirmed_stroke(conn, "努")
            self.assertIn("暂时没能打开", result.response)
            self.assertEqual(conn.mcp_client.call_results, {})

    async def test_ambiguous_or_multi_character_arguments_do_not_send(self):
        conn = SimpleNamespace(mcp_client=MCPClient(), websocket=SimpleNamespace(send=AsyncMock()))
        ambiguous = await lookup_stroke.show_confirmed_stroke(conn, "发")
        multi = await lookup_stroke.show_confirmed_stroke(conn, "努力")
        self.assertIn("頭髮", ambiguous.response)
        self.assertIn("一个字", multi.response)
        conn.websocket.send.assert_not_awaited()

    async def test_confirmed_lookup_uses_the_corrected_word_and_variant(self):
        cases = (
            ("不劳而祸的祸字怎么写？", "不劳而获", "獲", "7372.gif"),
            ("收获的祸字怎么写？", "收获", "穫", "7a6b.gif"),
        )
        with TemporaryDirectory() as folder:
            conn = SimpleNamespace(
                config={"character_lookup": {"asset_directory": folder}}, mcp_client=MCPClient()
            )
            for request, context, glyph, filename in cases:
                with self.subTest(request=request):
                    (Path(folder) / filename).touch()
                    args = parse_stroke_query(request, spoken=True)
                    self.assertIsNotNone(args)
                    with patch.object(lookup_stroke, "_preview_image", new_callable=AsyncMock) as preview:
                        result = await lookup_stroke.show_confirmed_stroke(conn, **args)
                    preview.assert_awaited_once()
                    self.assertEqual(
                        preview.await_args.args[:2], (conn, f"{lookup_stroke.DEFAULT_IMAGE_BASE_URL}/{filename}")
                    )
                    self.assertIn(glyph, result.result)
                    self.assertIn(context, to_simplified(result.response))
                    self.assertNotIn("祸", to_simplified(result.response))

    async def test_model_tool_does_not_show_its_own_character_guess(self):
        conn = SimpleNamespace(config={}, mcp_client=MCPClient(), websocket=SimpleNamespace(send=AsyncMock()))
        result = await ServerPluginExecutor(conn).execute(conn, "lookup_stroke", {
            "character": "禍", "context_phrase": "禍害", "script": "traditional",
        })
        self.assertIs(result.action, Action.RESPONSE)
        self.assertIn("词", result.response)
        conn.websocket.send.assert_not_awaited()


class StrokeIntentTests(unittest.IsolatedAsyncioTestCase):
    @patch.object(intentHandler, "enqueue_tool_report")
    @patch.object(intentHandler, "checkWakeupWords", return_value=False)
    @patch.object(intentHandler, "send_stt_message")
    async def test_enabled_tool_bypasses_llm_and_queues_tts(self, send_stt, check_wakeup, report):
        conn = SimpleNamespace(
            config={},
            cmd_exit=[],
            intent_type="function_call",
            logger=Mock(),
            loop=asyncio.get_running_loop(),
            dialogue=Dialogue(),
            tts=Mock(),
            mcp_client=None,
        )
        conn.func_handler = SimpleNamespace(
            has_tool=lambda _: True, handle_llm_function_call=AsyncMock()
        )
        with ThreadPoolExecutor(max_workers=1) as executor:
            futures = []
            conn.executor = SimpleNamespace(submit=lambda work: futures.append(executor.submit(work)))
            self.assertTrue(await intentHandler.handle_user_intent(conn, "努力的努字怎么写？"))
            await asyncio.wrap_future(futures[0])

        send_stt.assert_awaited_once_with(conn, "查字 努")
        conn.func_handler.handle_llm_function_call.assert_not_awaited()
        (arguments, kwargs) = conn.tts.tts_one_sentence.call_args
        self.assertEqual(arguments, (conn, ContentType.TEXT))
        self.assertIn("努字", kwargs["content_detail"])
        self.assertEqual(kwargs["sentence_id"], conn.sentence_id)
        self.assertEqual(
            [call.args[0].sentence_type for call in conn.tts.tts_text_queue.put.call_args_list],
            [SentenceType.FIRST, SentenceType.LAST],
        )

    @patch.object(intentHandler, "checkWakeupWords", return_value=False)
    async def test_voice_stop_shows_supported_glyph_or_clarifies(self, check_wakeup):
        cases = (
            ("而获的祸字怎么写？", "獲", "7372.gif"),
            ("收获的祸字怎么写？", "穫", "7a6b.gif"),
            ("珑门的珑字怎么写？", "瓏", "74cf.gif"),
            ("龙门的龙字怎么写？", "龍", "9f8d.gif"),
            ("货字怎么写？", None, None),
            ("或有收获的货字怎么写？", None, None),
        )
        for transcript, glyph, filename in cases:
            with self.subTest(transcript=transcript), TemporaryDirectory() as folder:
                if filename:
                    (Path(folder) / filename).touch()
                conn = SimpleNamespace(
                    config={"character_lookup": {"asset_directory": folder}},
                    cmd_exit=[],
                    intent_type="function_call",
                    logger=Mock(),
                    loop=asyncio.get_running_loop(),
                    dialogue=Dialogue(),
                    tts=Mock(),
                    mcp_client=MCPClient(),
                    audio_format="pcm",
                    active_listen_start_id=0,
                    latest_listen_start_id=0,
                    voiceprint_provider=None,
                    session_id="stroke-test",
                    read_config_from_api=False,
                    need_bind=False,
                    max_output_size=0,
                    client_is_speaking=False,
                    chat=Mock(),
                    func_handler=SimpleNamespace(
                        has_tool=lambda _: True, handle_llm_function_call=AsyncMock()
                    ),
                )
                sent = []

                async def send(data):
                    message = json.loads(data)
                    sent.append(message)
                    if message["type"] == "mcp":
                        await conn.mcp_client.resolve_call_result(
                            message["payload"]["id"], {"isError": False}
                        )

                conn.websocket = SimpleNamespace(send=send)
                provider = SimpleNamespace(
                    stop_ws_connection=Mock(),
                    speech_to_text_wrapper=AsyncMock(
                        return_value=({"content": transcript, "language": "zh"}, None)
                    ),
                )
                futures = []
                with ThreadPoolExecutor(max_workers=1) as executor:
                    conn.executor = SimpleNamespace(
                        submit=lambda work, *args: futures.append(executor.submit(work, *args))
                    )
                    # Exercise ASR's normal handoff after an injected transcript.
                    await ASRProviderBase.handle_voice_stop(provider, conn, [bytes(32)])
                    self.assertEqual(len(futures), 1)
                    await asyncio.wrap_future(futures[0])

                conn.chat.assert_not_called()
                conn.func_handler.handle_llm_function_call.assert_not_awaited()
                stt = [message["text"] for message in sent if message["type"] == "stt"]
                previews = [message["payload"] for message in sent if message["type"] == "mcp"]
                readback = conn.tts.tts_one_sentence.call_args.kwargs["content_detail"]
                if filename:
                    self.assertEqual(len(previews), 1)
                    self.assertTrue(previews[0]["params"]["arguments"]["url"].endswith(filename))
                    self.assertIn(glyph, stt[0])
                    self.assertIn(glyph, readback)
                else:
                    self.assertEqual(previews, [])
                    self.assertEqual(stt, ["查字"])
                    self.assertIn("说词就可以", readback)
                self.assertNotIn("祸", stt[0])
                self.assertNotIn("禍", readback)

    @patch.object(intentHandler, "checkWakeupWords", return_value=False)
    async def test_disabled_tool_leaves_normal_chat_untouched(self, check_wakeup):
        conn = SimpleNamespace(
            cmd_exit=[], intent_type="function_call", func_handler=SimpleNamespace(has_tool=lambda _: False)
        )
        self.assertFalse(await intentHandler.handle_user_intent(conn, "努力的努字怎么写？"))
