"""Accept legacy role-switch messages from older firmware."""

from typing import Any, Dict, TYPE_CHECKING

from core.handle.textMessageHandler import TextMessageHandler
from core.handle.textMessageType import TextMessageType

if TYPE_CHECKING:
    from core.connection import ConnectionHandler


class RoleSwitchMessageHandler(TextMessageHandler):
    @property
    def message_type(self) -> TextMessageType:
        return TextMessageType.ROLE_SWITCH

    async def handle(self, conn: "ConnectionHandler", msg_json: Dict[str, Any]) -> None:
        conn.logger.bind(tag=__name__).debug("单角色模式忽略旧固件的 role_switch 消息")
