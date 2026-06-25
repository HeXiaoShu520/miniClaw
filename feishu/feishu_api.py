"""
飞书客户端模块
使用飞书官方 SDK 处理消息发送、资源下载等功能
保留手动实现的话题聚合和云文档提取功能
"""
import json
import logging
import aiohttp
from typing import Optional, List, Dict
from dataclasses import dataclass
from lark_oapi import Client
from lark_oapi.api.im.v1 import *
from lark_oapi.api.im.v1.model.emoji import Emoji


@dataclass
class ImMessage:
    """飞书即时消息"""
    message_id: str
    chat_id: str
    chat_type: str
    sender_id: str
    content: dict
    timestamp: int
    topic_id: Optional[str] = None


@dataclass
class ImageItem:
    """图片项"""
    message_id: str
    image_key: str


@dataclass
class FileItem:
    """文件项"""
    message_id: str
    file_key: str
    file_name: str


@dataclass
class TopicSubmission:
    """话题聚合结果"""
    topic_id: str
    chat_id: str
    texts: List[str]
    images: List[ImageItem]
    files: List[FileItem]
    links: List[str]


class FeishuClient:
    """飞书客户端，使用官方 SDK"""

    def __init__(self, app_id: str, app_secret: str):
        """初始化飞书客户端"""
        self.app_id = app_id
        self.app_secret = app_secret
        self.client = Client.builder().app_id(app_id).app_secret(app_secret).build()
        self.session = None

    async def _get_session(self):
        """获取或创建 aiohttp 会话（用于资源下载）"""
        if self.session is None:
            self.session = aiohttp.ClientSession()
        return self.session

    async def close(self):
        """关闭客户端，释放资源"""
        if self.session:
            await self.session.close()

    async def get_access_token(self) -> str:
        """获取租户访问令牌"""
        import lark_oapi as lark
        import json
        req = lark.api.auth.v3.InternalTenantAccessTokenRequest.builder().request_body(
            lark.api.auth.v3.InternalTenantAccessTokenRequestBody.builder()
            .app_id(self.app_id)
            .app_secret(self.app_secret)
            .build()
        ).build()
        resp = self.client.auth.v3.tenant_access_token.internal(req)
        if not resp.success():
            raise Exception(f"获取 token 失败: {resp.code}, {resp.msg}")
        # 从 raw.content 解析 token
        data = json.loads(resp.raw.content)
        return data["tenant_access_token"]

    async def refresh_token(self):
        """刷新访问令牌（SDK 自动管理，此方法保留兼容性）"""
        pass

    async def reply_message(self, message_id: str, text: str, use_thread: bool = True) -> tuple[str, str]:
        """
        回复消息（使用交互式卡片）

        Args:
            message_id: 要回复的消息 ID
            text: 回复内容（支持 Markdown）
            use_thread: 是否使用话题回复（默认 True）

        Returns:
            tuple[str, str]: (回复消息 ID, 话题 ID)
        """
        card = {"elements": [{"tag": "markdown", "content": text}]}
        req = ReplyMessageRequest.builder().message_id(message_id).request_body(
            ReplyMessageRequestBody.builder()
            .content(json.dumps(card))
            .msg_type("interactive")
            .reply_in_thread(use_thread)
            .build()
        ).build()

        resp = self.client.im.v1.message.reply(req)
        if not resp.success():
            raise Exception(f"回复消息失败: {resp.code}, {resp.msg}")

        msg = resp.data
        return msg.message_id, msg.thread_id or message_id

    async def update_message(self, message_id: str, text: str):
        """
        更新消息内容（仅支持卡片消息）

        Args:
            message_id: 消息 ID
            text: 新内容（支持 Markdown）
        """
        card = {"elements": [{"tag": "markdown", "content": text}]}
        req = PatchMessageRequest.builder().message_id(message_id).request_body(
            PatchMessageRequestBody.builder()
            .content(json.dumps(card))
            .build()
        ).build()

        resp = self.client.im.v1.message.patch(req)
        if not resp.success():
            logging.error(f"更新消息失败: {resp.code}, {resp.msg}")

    async def download_resource(self, message_id: str, file_key: str, resource_type: str) -> bytes:
        """
        下载资源文件（图片或文件）

        Args:
            message_id: 消息 ID
            file_key: 文件 key
            resource_type: 资源类型（image 或 file）

        Returns:
            bytes: 文件二进制数据
        """
        req = GetMessageResourceRequest.builder().message_id(message_id).file_key(file_key).type(resource_type).build()
        resp = self.client.im.v1.message_resource.get(req)
        if not resp.success():
            raise Exception(f"下载资源失败: {resp.code}, {resp.msg}")
        return resp.file.read()

    async def get_thread_messages(self, thread_id: str) -> List[Dict]:
        """
        获取话题内的所有消息（保留手动实现，SDK 分页处理复杂）

        Args:
            thread_id: 话题 ID

        Returns:
            List[Dict]: 消息列表
        """
        token = await self.get_access_token()
        session = await self._get_session()
        url = "https://open.feishu.cn/open-apis/im/v1/messages"
        headers = {"Authorization": f"Bearer {token}"}
        params = {"container_id_type": "thread", "container_id": thread_id, "page_size": 50}

        messages = []
        page_token = None

        while True:
            if page_token:
                params["page_token"] = page_token

            async with session.get(url, headers=headers, params=params) as resp:
                result = await resp.json()
                if result.get("code") != 0:
                    logging.error(f"获取话题消息失败: {result}")
                    break

                data = result.get("data", {})
                items = data.get("items", [])
                messages.extend(items)

                page_token = data.get("page_token")
                if not data.get("has_more"):
                    break

        return messages

    async def add_reaction(self, message_id: str, emoji_type: str):
        """给消息添加表情回应"""
        req = CreateMessageReactionRequest.builder().message_id(message_id).request_body(
            CreateMessageReactionRequestBody.builder()
            .reaction_type(Emoji.builder().emoji_type(emoji_type).build())
            .build()
        ).build()
        resp = self.client.im.v1.message_reaction.create(req)
        if not resp.success():
            logging.warning(f"添加表情失败: {resp.code}, {resp.msg}")
            return None
        return resp.data.reaction_id

    async def remove_reaction(self, message_id: str, reaction_id: str):
        """移除消息表情回应"""
        req = DeleteMessageReactionRequest.builder().message_id(message_id).reaction_id(reaction_id).build()
        resp = self.client.im.v1.message_reaction.delete(req)
        if not resp.success():
            logging.warning(f"移除表情失败: {resp.code}, {resp.msg}")

    async def send_text_to_user(self, open_id: str, text: str):
        """给指定用户发送文本消息"""
        req = CreateMessageRequest.builder().receive_id_type("open_id").request_body(
            CreateMessageRequestBody.builder()
            .receive_id(open_id)
            .msg_type("text")
            .content(json.dumps({"text": text}))
            .build()
        ).build()
        resp = self.client.im.v1.message.create(req)
        if not resp.success():
            logging.error(f"发送消息给用户失败: {resp.code}, {resp.msg}")

    async def send_audio(self, chat_id: str, audio_data: bytes) -> str:
        """上传音频并发送到会话，返回消息 ID"""
        token = await self.get_access_token()
        session = await self._get_session()

        # 上传音频文件
        form = aiohttp.FormData()
        form.add_field("file_type", "opus")
        form.add_field("file_name", "reply.opus")
        form.add_field("file", audio_data, filename="reply.opus", content_type="audio/opus")
        async with session.post(
            "https://open.feishu.cn/open-apis/im/v1/files",
            headers={"Authorization": f"Bearer {token}"},
            data=form
        ) as resp:
            result = await resp.json()
            if result.get("code") != 0:
                raise Exception(f"上传音频失败: {result}")
            file_key = result["data"]["file_key"]

        # 发送音频消息
        req = CreateMessageRequest.builder().receive_id_type("chat_id").request_body(
            CreateMessageRequestBody.builder()
            .receive_id(chat_id)
            .msg_type("audio")
            .content(json.dumps({"file_key": file_key}))
            .build()
        ).build()
        resp = self.client.im.v1.message.create(req)
        if not resp.success():
            raise Exception(f"发送音频失败: {resp.code}, {resp.msg}")
        return resp.data.message_id
        """
        聚合话题内的所有用户消息

        Args:
            topic_id: 话题 ID
            chat_id: 会话 ID

        Returns:
            TopicSubmission: 聚合结果
        """
        messages = await self.get_thread_messages(topic_id)

        texts = []
        images = []
        files = []
        links = []

        for msg in messages:
            message_id = msg.get("message_id", "")
            msg_type = msg.get("msg_type", "")
            content_str = msg.get("content", "{}")

            # 处理文本消息
            if msg_type == "text":
                try:
                    content = json.loads(content_str)
                    text = content.get("text", "").strip()
                    if text:
                        # 检查是否为飞书链接
                        if ".feishu.cn/" in text:
                            links.append(text)
                        else:
                            texts.append(text)
                except:
                    pass

            # 处理图片消息
            elif msg_type == "image":
                try:
                    content = json.loads(content_str)
                    image_key = content.get("image_key", "")
                    if image_key:
                        images.append(ImageItem(message_id, image_key))
                except:
                    pass

            # 处理文件消息
            elif msg_type == "file":
                try:
                    content = json.loads(content_str)
                    file_key = content.get("file_key", "")
                    file_name = content.get("file_name", "")
                    if file_key:
                        files.append(FileItem(message_id, file_key, file_name))
                except:
                    pass

        return TopicSubmission(topic_id, chat_id, texts, images, files, links)
