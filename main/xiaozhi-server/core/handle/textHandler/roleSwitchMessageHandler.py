"""
role_switch 消息处理器

设备端三击电源键时发送 {"type":"role_switch"} 消息。
服务端收到后直接 toggle 角色（小智 ↔ 英语老师），不经过 LLM。
"""
import uuid
import asyncio
from typing import Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from core.connection import ConnectionHandler

from core.handle.textMessageHandler import TextMessageHandler
from core.handle.textMessageType import TextMessageType
from core.handle.sendAudioHandle import sendAudioMessage, send_tts_message
from core.providers.tts.dto.dto import SentenceType
from core.utils.dialogue import Message

TAG = __name__


class RoleSwitchMessageHandler(TextMessageHandler):
    """Role Switch 消息处理器 —— 按键直接切换角色"""

    @property
    def message_type(self) -> TextMessageType:
        return TextMessageType.ROLE_SWITCH

    async def handle(self, conn: "ConnectionHandler", msg_json: Dict[str, Any]) -> None:
        conn.logger.bind(tag=TAG).info("收到 role_switch 消息，执行角色切换")

        try:
            from plugins_func.functions.change_role import role_configs, DEFAULT_ROLE_PROMPT
            import plugins_func.functions.change_role as cr_module

            # Toggle 逻辑：当前是默认小智 → 切英语老师，否则切回小智
            if cr_module._current_role == "默认小智":
                target_role = "英语老师"
            else:
                target_role = "默认小智"

            config = role_configs[target_role]

            if config["prompt"] == DEFAULT_ROLE_PROMPT:
                # 切回默认角色：恢复原始 system prompt
                conn.restore_default_prompt()
                conn.logger.bind(tag=TAG).info("恢复默认角色: 小智")
            else:
                # 切到英语老师：整体替换 system prompt
                new_prompt = config["prompt"]
                conn.change_system_prompt(new_prompt)
                conn.logger.bind(tag=TAG).info(f"切换角色成功: {target_role}")

            cr_module._current_role = target_role

            # 重置对话历史（角色切换后清空上下文）
            if hasattr(conn, 'dialogue'):
                conn.dialogue.dialogue = []
                conn.dialogue.dialogue.append(
                    Message(role="system", content=conn.prompt)
                )

            # 播报欢迎语 —— 和 helloHandle.py 中播放唤醒词回复的方式一致
            welcome_text = config["response"]
            conn.logger.bind(tag=TAG).info(f"播报切换欢迎语: {welcome_text}")

            # 通知客户端 TTS 开始
            await send_tts_message(conn, "start")

            # 生成 TTS 音频
            conn.client_abort = False
            conn.sentence_id = str(uuid.uuid4().hex)

            tts_result = await asyncio.to_thread(conn.tts.to_tts, welcome_text)
            if tts_result:
                await sendAudioMessage(conn, SentenceType.FIRST, tts_result, welcome_text)
                await sendAudioMessage(conn, SentenceType.LAST, [], None)

                # 记录到对话历史
                conn.dialogue.put(Message(role="assistant", content=welcome_text))
            else:
                conn.logger.bind(tag=TAG).error("TTS 生成欢迎语失败")
                await send_tts_message(conn, "stop", None)

        except Exception as e:
            conn.logger.bind(tag=TAG).error(f"角色切换失败: {e}")
            import traceback
            conn.logger.bind(tag=TAG).error(traceback.format_exc())
