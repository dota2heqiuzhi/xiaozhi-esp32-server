import base64
import json
import unittest
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from core.providers.llm.openai.openai import LLMProvider
from core.providers.tts.tencent import TTSProvider


class TokenHubTests(unittest.TestCase):
    @patch("core.providers.llm.openai.openai.openai.OpenAI")
    def test_flash_disables_thinking_for_chat_and_tools(self, client):
        create = client.return_value.chat.completions.create
        create.side_effect = [MagicMock(), MagicMock()]
        provider = LLMProvider({
            "base_url": "https://tokenhub-intl.tencentcloudmaas.com/v1",
            "model_name": "hy4-flash",
            "api_key": "test-key",
        })
        messages = [{"role": "user", "content": "你好"}]

        list(provider.response("test", messages))
        list(provider.response_with_functions("test", messages, [{"type": "function"}]))

        for request in create.call_args_list:
            self.assertEqual(request.kwargs["extra_body"], {"thinking": {"type": "disabled"}})
            self.assertTrue(request.kwargs["stream"])
        self.assertEqual(create.call_args.kwargs["tools"], [{"type": "function"}])

    @patch("core.providers.llm.openai.openai.openai.OpenAI")
    def test_tokenhub_combines_system_context_without_mutating_tools(self, client):
        create = client.return_value.chat.completions.create
        provider = LLMProvider({
            "base_url": "https://tokenhub-intl.tencentmaas.com/v1",
            "model_name": "hy4-flash",
            "api_key": "test-key",
        })
        tool_call = {
            "id": "call_1",
            "type": "function",
            "function": {"name": "lookup_stroke", "arguments": '{"character":"努"}'},
        }
        tool = {"type": "function", "function": {"name": "lookup_stroke"}}
        messages = [
            {"role": "system", "content": "你是小智"},
            {"role": "user", "content": "注意查字工具"},
            {"role": "system", "content": "今天有点冷"},
            {"role": "user", "content": "努力的努怎么写？"},
            {"role": "assistant", "tool_calls": [tool_call]},
            {"role": "tool", "tool_call_id": "call_1", "content": "努"},
        ]
        original = deepcopy(messages)

        list(provider.response("test", messages))
        list(provider.response_with_functions("test", messages, [tool]))

        for request in create.call_args_list:
            self.assertEqual(request.kwargs["messages"], [
                {"role": "system", "content": "你是小智\n\n今天有点冷"},
                {"role": "user", "content": "注意查字工具\n\n努力的努怎么写？"},
                {**original[4], "content": ""},
                original[5],
            ])
        self.assertEqual(create.call_args.kwargs["tools"], [tool])
        self.assertEqual(messages, original)


class TencentTTSTests(unittest.IsolatedAsyncioTestCase):
    @patch("core.providers.tts.tencent.requests.post")
    async def test_host_region_and_audio_format(self, post):
        post.return_value.status_code = 200
        post.return_value.json.return_value = {
            "Response": {"Audio": base64.b64encode(b"audio").decode("ascii")},
        }
        cases = [
            ("ap-hongkong", "tts.ap-hongkong.tencentcloudapi.com", None, 24000),
            ("ap-singapore", "tts.intl.tencentcloudapi.com", "ap-singapore", 16000),
            ("ap-guangzhou", "tts.tencentcloudapi.com", "ap-guangzhou", 24000),
        ]
        for region, host, header_region, rate in cases:
            with self.subTest(region=region):
                provider = TTSProvider({
                    "region": region,
                    "secret_id": "test-id",
                    "secret_key": "test-key",
                    "voice": 101001,
                }, delete_audio_file=True)
                provider.conn = SimpleNamespace(sample_rate=24000)

                self.assertEqual(await provider.text_to_speak("努", None), b"audio")

                (url, body), kwargs = post.call_args
                self.assertEqual(url, f"https://{host}")
                self.assertEqual(kwargs["headers"]["Host"], host)
                self.assertEqual(kwargs["headers"].get("X-TC-Region"), header_region)
                self.assertIn("SignedHeaders=content-type;host", kwargs["headers"]["Authorization"])
                self.assertEqual(json.loads(body)["SampleRate"], rate)
                self.assertEqual(kwargs["timeout"], (3, 10))
