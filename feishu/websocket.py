"""
飞书 WebSocket 客户端模块
负责建立 WebSocket 连接并监听飞书消息事件
"""
import asyncio
import json
import logging
import websockets
from typing import Callable, Awaitable, Dict
from datetime import datetime, timedelta
from pathlib import Path
from feishu.feishu_api import ImMessage
from feishu.protobuf import PbFrame

SEEN_IDS_FILE = Path.home() / ".acp-link" / "data" / "seen_ids.json"


class FeishuWebSocket:
    """飞书 WebSocket 客户端"""

    def __init__(self, app_id: str, app_secret: str):
        self.app_id = app_id
        self.app_secret = app_secret
        self.ws_url = None
        self.seen_ids: Dict[str, str] = {}  # message_id -> ISO timestamp
        self._load_seen_ids()

    def _load_seen_ids(self):
        """从磁盘加载去重记录"""
        try:
            if SEEN_IDS_FILE.exists():
                data = json.loads(SEEN_IDS_FILE.read_text(encoding="utf-8"))
                cutoff = datetime.now() - timedelta(minutes=30)
                self.seen_ids = {k: v for k, v in data.items()
                                 if datetime.fromisoformat(v) > cutoff}
        except Exception as e:
            logging.warning(f"加载 seen_ids 失败: {e}")
            self.seen_ids = {}

    def _save_seen_ids(self):
        """持久化去重记录到磁盘"""
        try:
            SEEN_IDS_FILE.parent.mkdir(parents=True, exist_ok=True)
            SEEN_IDS_FILE.write_text(json.dumps(self.seen_ids), encoding="utf-8")
        except Exception as e:
            logging.warning(f"保存 seen_ids 失败: {e}")

    async def get_ws_endpoint(self) -> str:
        """
        获取 WebSocket 连接地址

        Returns:
            str: WebSocket URL
        """
        import aiohttp
        url = "https://open.feishu.cn/callback/ws/endpoint"
        data = {"AppID": self.app_id, "AppSecret": self.app_secret}

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=data) as resp:
                text = await resp.text()
                logging.debug(f"飞书 API 返回: {text[:200]}")

                # 尝试直接解析 JSON
                try:
                    data = json.loads(text)
                    if data["code"] != 0:
                        raise Exception(f"获取 WS 地址失败: {data}")
                    return data["data"]["URL"]
                except json.JSONDecodeError:
                    # 处理多行 JSON 响应
                    for line in text.strip().split('\n'):
                        if line.strip():
                            data = json.loads(line)
                            if data["code"] != 0:
                                raise Exception(f"获取 WS 地址失败: {data}")
                            return data["data"]["URL"]
                raise Exception("未获取到 WS 地址")

    async def listen(self, handler: Callable[[ImMessage], Awaitable[None]]):
        """
        监听飞书消息事件

        Args:
            handler: 消息处理函数
        """
        ws_url = await self.get_ws_endpoint()
        logging.info(f"连接到飞书 WebSocket: {ws_url}")

        async with websockets.connect(ws_url) as ws:
            logging.info("WebSocket 已连接")

            async for message in ws:
                try:
                    if isinstance(message, bytes):
                        # 解析 Protobuf 帧
                        frame = PbFrame.parse(message)

                        # 发送 ACK 确认
                        await ws.send(frame.encode_ack())

                        # method=1 表示数据帧
                        if frame.method == 1 and frame.payload:
                            data = json.loads(frame.payload.decode('utf-8'))
                            # 处理消息接收事件
                            if data.get("header", {}).get("event_type") == "im.message.receive_v1":
                                msg = self._parse_message(data)
                                if msg:
                                    # 消息去重（1天窗口）
                                    now = datetime.now()
                                    cutoff = now - timedelta(days=1)
                                    self.seen_ids = {k: v for k, v in self.seen_ids.items()
                                                    if datetime.fromisoformat(v) > cutoff}

                                    if msg.message_id in self.seen_ids:
                                        logging.debug(f"重复消息，跳过: {msg.message_id}")
                                        continue

                                    self.seen_ids[msg.message_id] = now.isoformat()
                                    self._save_seen_ids()
                                    # 异步处理消息，不阻塞 WebSocket 接收
                                    asyncio.create_task(handler(msg))
                except Exception as e:
                    logging.error(f"处理消息失败: {e}")

    def _parse_message(self, data: dict) -> ImMessage:
        """
        解析飞书消息事件数据

        Args:
            data: 事件数据

        Returns:
            ImMessage: 解析后的消息对象
        """
        event = data.get("event", {})
        message = event.get("message", {})

        return ImMessage(
            message_id=message.get("message_id", ""),
            chat_id=message.get("chat_id", ""),
            chat_type=message.get("chat_type", ""),
            sender_id=event.get("sender", {}).get("sender_id", {}).get("open_id", ""),
            content={"msg_type": message.get("message_type"), "content": message.get("content")},
            timestamp=int(message.get("create_time", 0)),
            topic_id=message.get("parent_id")
        )

