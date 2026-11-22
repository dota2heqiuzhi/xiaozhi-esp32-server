import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from config import config_loader
from core.handle.textHandle import handleTextMessage


class SingleRoleTests(unittest.IsolatedAsyncioTestCase):
    async def test_legacy_role_switch_does_not_change_prompt_or_start_tts(self):
        dialogue = ["已经聊过的内容"]
        conn = SimpleNamespace(
            logger=Mock(),
            prompt="你是小智",
            change_system_prompt=Mock(),
            dialogue=SimpleNamespace(dialogue=dialogue.copy()),
            tts=Mock(),
            websocket=SimpleNamespace(send=AsyncMock()),
        )

        await handleTextMessage(conn, '{"type":"role_switch"}')

        self.assertEqual(conn.prompt, "你是小智")
        self.assertEqual(conn.dialogue.dialogue, dialogue)
        conn.change_system_prompt.assert_not_called()
        conn.websocket.send.assert_not_awaited()
        self.assertEqual(conn.tts.mock_calls, [])

    @patch.dict("os.environ", {"XIAOZHI_PROMPT_TEMPLATE": "data/agent-base-prompt.txt"})
    @patch.object(config_loader, "init_service")
    @patch.object(config_loader, "get_server_config", new_callable=AsyncMock)
    async def test_deployment_prompt_path_overrides_manager_path(self, get_server_config, init):
        get_server_config.return_value = {"server": {}, "prompt_template": "manager-prompt.txt"}

        config = await config_loader.get_config_from_api_async({
            "manager-api": {"url": "http://manager.example"},
            "prompt_template": "default-prompt.txt",
        })

        self.assertEqual(config["prompt_template"], "data/agent-base-prompt.txt")
