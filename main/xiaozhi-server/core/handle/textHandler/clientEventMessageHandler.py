"""
client_event 消息处理器

设备端通过 WebSocket 上报客户端事件（按键 / 状态切换 / 本地决定的 abort 等），
便于运营态在没有串口的情况下重建现场。

协议（client → server）：

    {
        "type": "client_event",
        "session_id": "<可选>",
        "ts": <设备本地相对启动时间 ms>,
        "category": "button" | "state" | "abort" | "listen" | "net" | "system",
        "name":     "<事件短名>",
        "data":     { ... 任意结构化键值对 }
    }

服务端只做一件事：用 connection logger 写一行结构化日志，
让运维 / 开发同学能够直接 grep 出来。
绝不影响任何业务流程，**不**主动回包，**不**修改 conn 状态。
"""
from typing import Any, Dict, TYPE_CHECKING

from core.handle.textMessageHandler import TextMessageHandler
from core.handle.textMessageType import TextMessageType

if TYPE_CHECKING:
    from core.connection import ConnectionHandler

TAG = __name__


class ClientEventTextMessageHandler(TextMessageHandler):
    """处理设备上报的 client_event 消息"""

    @property
    def message_type(self) -> TextMessageType:
        return TextMessageType.CLIENT_EVENT

    async def handle(self, conn: "ConnectionHandler", msg_json: Dict[str, Any]) -> None:
        category = msg_json.get("category", "?")
        name = msg_json.get("name", "?")
        ts = msg_json.get("ts", "?")
        data = msg_json.get("data", {})

        # 单行结构化日志：便于 grep "CLIENT_EVENT"
        conn.logger.bind(tag=TAG).info(
            f"CLIENT_EVENT category={category} name={name} ts={ts} data={data}"
        )
