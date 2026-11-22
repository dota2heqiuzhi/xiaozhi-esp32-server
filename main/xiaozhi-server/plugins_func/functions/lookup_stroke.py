"""Display the stroke order for one character and optionally recite a poem."""

import asyncio
import json
import os
import random
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from config.logger import setup_logging
from core.utils.stroke_query import (
    GENERIC_CLARIFICATION,
    StrokeClarification,
    display_character,
    is_han_character,
    to_simplified,
    variant_examples,
)
from plugins_func.register import Action, ActionResponse, ToolType, register_function

if TYPE_CHECKING:
    from core.connection import ConnectionHandler

TAG = __name__
logger = setup_logging()

# Boilon V2 firmware rewrites this exact prefix to the Hong Kong LAN when available.
DEFAULT_IMAGE_BASE_URL = "http://175.178.247.160:18090/strokes"
MCP_TOOL_NAME = "self.screen.preview_image"
MCP_TIMEOUT_SECONDS = 5

_POEM_INDEX_PATH = Path(__file__).resolve().parents[2] / "data" / "poem_index.json"
try:
    with _POEM_INDEX_PATH.open(encoding="utf-8") as poem_file:
        POEM_INDEX = json.load(poem_file)
    logger.bind(tag=TAG).info(f"笔顺诗库已载入，覆盖 {len(POEM_INDEX)} 个字")
except (OSError, ValueError) as error:
    logger.bind(tag=TAG).warning(f"笔顺诗库不可用: {error}")
    POEM_INDEX = {}

lookup_stroke_function_desc = {
    "type": "function",
    "function": {
        "name": "lookup_stroke",
        "description": (
            "当孩子在问一个汉字的写法或笔顺，而服务端还没有确认字形时，调用此工具请孩子补充组词。"
            "答复以工具结果为准。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "character": {"type": "string", "description": "单个要查询的汉字。"},
                "context_phrase": {
                    "type": "string", "description": "用于确定字形的词组，例如‘努力’。"
                },
                "script": {
                    "type": "string",
                    "enum": ["traditional", "simplified"],
                    "description": "默认查繁体。用户明确要求简体时填 simplified。",
                },
            },
            "required": ["character"],
        },
    },
}


def _image_url(conn, character: str) -> str | None:
    options = conn.config.get("character_lookup") or {}
    base_url = (options.get("image_base_url") or DEFAULT_IMAGE_BASE_URL).strip().rstrip("/")
    parts = urlsplit(base_url)
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.query or parts.fragment:
        raise ValueError("character_lookup.image_base_url 必须是 HTTP(S) 目录地址")

    codepoint = f"{ord(character):x}"
    asset_directory = options.get("asset_directory") or os.environ.get("STROKE_ASSET_DIRECTORY")
    if not asset_directory:
        return f"{base_url}/{codepoint}.gif"

    directory = Path(asset_directory)
    if not directory.is_dir():
        raise OSError(f"笔顺图片目录不可用: {directory}")
    for extension in ("gif", "png"):
        filename = f"{codepoint}.{extension}"
        if (directory / filename).is_file():
            return f"{base_url}/{filename}"
    return None


async def _preview_image(conn, image_url: str, *, sentence_id: str | None = None):
    client = conn.mcp_client
    tool_id = await client.get_next_id()
    while tool_id < 3:  # 初始化和工具列表占用 ID 1、2。
        tool_id = await client.get_next_id()
    result_future = asyncio.get_running_loop().create_future()
    await client.register_call_result_future(tool_id, result_future)
    payload = {
        "jsonrpc": "2.0",
        "id": tool_id,
        "method": "tools/call",
        # This user-only tool can be called by trusted code and stays out of the LLM's tool list.
        "params": {"name": MCP_TOOL_NAME, "arguments": {"url": image_url}},
    }
    try:
        result = await asyncio.wait_for(
            _send_and_wait_for_preview(conn, payload, result_future, sentence_id),
            MCP_TIMEOUT_SECONDS,
        )
        if not isinstance(result, dict) or result.get("isError"):
            raise RuntimeError(f"设备未接受笔顺预览: {result}")
    finally:
        await client.cleanup_call_result(tool_id)


async def _send_and_wait_for_preview(conn, payload, result_future, sentence_id):
    if sentence_id is not None and (conn.sentence_id != sentence_id or conn.client_abort):
        raise RuntimeError("本轮查字已结束")
    await conn.websocket.send(json.dumps({"type": "mcp", "payload": payload}))
    return await result_future


@register_function("lookup_stroke", lookup_stroke_function_desc, ToolType.SYSTEM_CTL)
async def lookup_stroke(
    conn: "ConnectionHandler", character: str = "", context_phrase: str = "", script: str = "traditional"
):
    """Ask for spoken context when the model cannot verify the desired character."""
    return ActionResponse(
        action=Action.RESPONSE,
        result="需要组词确认字形",
        response=GENERIC_CLARIFICATION,
    )


async def show_confirmed_stroke(
    conn: "ConnectionHandler", character: str, context_phrase: str = "", script: str = "traditional",
    *, sentence_id: str | None = None,
):
    """Send one local stroke asset selected by the server-side utterance parser."""
    char = character.strip() if isinstance(character, str) else ""
    if not is_han_character(char):
        return ActionResponse(
            action=Action.RESPONSE,
            result="需要单个汉字",
            response="你想查哪个字呀？告诉我一个字就好！",
        )

    context = context_phrase.strip() if isinstance(context_phrase, str) else ""
    display_char = display_character(char, context, script)
    if display_char is None:
        return ActionResponse(
            action=Action.RESPONSE,
            result="需要组词确认字形",
            response=StrokeClarification(char, script, variant_examples(char)).prompt,
        )

    if context and char in context:
        display_context = context.replace(char, display_char)
        intro = f"这是{display_context}的{display_char}字。"
    elif display_char != char:
        script_name = "简体" if script == "simplified" else "繁体"
        intro = f"这是{script_name}的{display_char}字。"
    else:
        intro = f"这是{char}字。"

    if not getattr(conn, "mcp_client", None):
        return ActionResponse(
            action=Action.RESPONSE,
            result="设备不支持屏幕预览",
            response=intro + "这台设备不能显示笔顺图。",
        )

    try:
        image_url = _image_url(conn, display_char)
    except (AttributeError, OSError, TypeError, ValueError) as error:
        logger.bind(tag=TAG).error(f"笔顺图片配置错误: {error}")
        image_url = None
    if image_url is None:
        logger.bind(tag=TAG).warning(f"笔顺图片不可用: {display_char} U+{ord(display_char):04X}")
        return ActionResponse(
            action=Action.RESPONSE,
            result="没有可用的笔顺图片",
            response=intro + "我暂时找不到这个字的笔顺图。",
        )

    try:
        await _preview_image(conn, image_url, sentence_id=sentence_id)
    except Exception as error:
        logger.bind(tag=TAG).warning(f"设备笔顺预览失败: {type(error).__name__}: {error}")
        return ActionResponse(
            action=Action.RESPONSE,
            result="设备笔顺预览未确认",
            response=intro + "屏幕暂时没能打开笔顺图。",
        )

    logger.bind(tag=TAG).info(f"设备已回复笔顺预览: {display_char} U+{ord(display_char):04X}")
    source_char = to_simplified(char)
    poems = [
        poem for poem in POEM_INDEX.get(source_char, ())
        if display_character(source_char, poem, script) == display_char
    ]
    if display_char != source_char:
        poems.extend(POEM_INDEX.get(display_char, ()))
    response = f"{intro}{random.choice(poems)}。" if poems else intro
    return ActionResponse(
        action=Action.RESPONSE,
        result=f"设备已处理 {display_char} 的笔顺预览",
        response=response,
    )
