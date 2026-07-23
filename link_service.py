"""
链接服务模块
负责处理飞书消息、管理会话、调用 Claude API、处理云文档链接等核心业务逻辑
"""
import asyncio
import base64
import json
import logging
import random
import re
import zlib
from pathlib import Path
from uuid import uuid4
from typing import Awaitable, Callable, Dict, List
from datetime import datetime, timedelta

from config import AppConfig
from ai_client import AIClient
from feishu.feishu_api import FeishuClient, ImMessage
from store.resource_store import ResourceStore
from feishu.doc_client import FeishuDocClient
from agent.feishu_chat import FeishuChatAgent


def _mermaid_url(code: str) -> str:
    state = json.dumps({"code": code, "mermaid": {"theme": "default"}, "autoSync": True, "updateDiagram": True})
    compressed = zlib.compress(state.encode("utf-8"), level=9)
    raw_deflate = compressed[2:-4]
    b64 = base64.urlsafe_b64encode(raw_deflate).decode("ascii")
    return f"https://mermaid.ai/play#pako:{b64}"


def _append_mermaid_links(text: str) -> str:
    """检测回复中的 mermaid 代码块，追加在线可视化链接"""
    pattern = re.compile(r"```mermaid\n(.*?)```", re.DOTALL)
    links = []
    for m in pattern.finditer(text):
        code = m.group(1).strip()
        links.append(f"在线可视化编辑：{_mermaid_url(code)}")
    if links:
        text = text + "\n\n" + "\n".join(links)
    return text


class LinkService:
    """飞书-Claude 桥接服务核心类"""

    def __init__(self, config: AppConfig, feishu: FeishuClient, ai_client: AIClient):
        """
        初始化链接服务

        Args:
            config: 应用配置
            feishu: 飞书客户端
            ai_client: AI 客户端（Anthropic 或 OpenAI）
        """
        self.config = config
        self.feishu = feishu
        self.ai = ai_client
        self.conversations: Dict[str, List[dict]] = {}  # 对话历史
        self.session_map: Dict[str, str] = {}  # 消息ID到话题ID的映射
        self.sessions_file = Path.home() / ".acp-link" / "sessions.json"
        self.history_file = Path.home() / ".acp-link" / "history.json"
        self.resource_store = ResourceStore(AppConfig.data_dir())
        self.doc_client = None  # 延迟初始化文档客户端
        self.active_tasks: Dict[str, asyncio.Task] = {}  # 活跃的消息处理任务
        self.pending_images: Dict[str, dict] = {}  # conv_key -> {image_key, message_id, timer_task}
        self.agent = FeishuChatAgent(ai_client, feishu)
        self._load_sessions()
        self._load_history()

    def _load_history(self):
        """从文件加载本地多轮对话历史"""
        if self.history_file.exists():
            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    self.conversations = json.load(f)
                logging.info(f"成功加载本地聊天记录: {len(self.conversations)} 个会话")
            except Exception as e:
                logging.error(f"加载本地聊天记录失败: {e}")
                self.conversations = {}

    def _save_history(self):
        """保存多轮对话历史到本地文件"""
        try:
            self.history_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump(self.conversations, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logging.error(f"保存本地聊天记录失败: {e}")

    def _load_sessions(self):
        """从文件加载会话映射"""
        if self.sessions_file.exists():
            with open(self.sessions_file) as f:
                data = json.load(f)
                # 兼容旧格式和新格式（带时间戳）
                if isinstance(data, dict):
                    self.session_map = data
                else:
                    self.session_map = {}

    def _save_sessions(self):
        """保存会话映射到文件"""
        self.sessions_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.sessions_file, "w") as f:
            json.dump(self.session_map, f, indent=2)

    def save_sessions(self):
        """公开方法：保存会话映射和聊天历史"""
        self._save_sessions()
        self._save_history()

    def cleanup_sessions(self, retention_days: int):
        """
        清理过期会话

        Args:
            retention_days: 保留天数
        """
        cutoff = datetime.now() - timedelta(days=retention_days)
        removed_keys = []

        for key, value in list(self.session_map.items()):
            # 如果值是字典且包含时间戳，检查是否过期
            if isinstance(value, dict) and "timestamp" in value:
                timestamp = datetime.fromisoformat(value["timestamp"])
                if timestamp < cutoff:
                    removed_keys.append(key)
                    del self.session_map[key]
                    # 同时清理对话历史
                    thread_id = value.get("thread_id")
                    if thread_id and thread_id in self.conversations:
                        del self.conversations[thread_id]

        if removed_keys:
            logging.info(f"Session 清理完成: 删除 {len(removed_keys)} 个过期会话")
            self._save_sessions()

    def cleanup_resources(self):
        """清理过期资源文件"""
        try:
            self.resource_store.cleanup_expired(self.config.resource_retention)
        except Exception as e:
            logging.error(f"资源清理失败: {e}")

    async def handle_message(self, msg: ImMessage):
        """
        处理单条消息（并发入口，带去重）

        Args:
            msg: 飞书消息对象
        """
        # 去重：如果消息正在处理中，直接返回
        if msg.message_id in self.active_tasks:
            logging.debug(f"消息 {msg.message_id} 正在处理中，跳过")
            return

        task = asyncio.create_task(self._handle_message_task(msg))
        self.active_tasks[msg.message_id] = task

        try:
            await task
        finally:
            self.active_tasks.pop(msg.message_id, None)

    async def _handle_message_task(self, msg: ImMessage):
        """处理单条消息的实际逻辑"""
        logging.info(f"收到消息: {msg.message_id}")
        logging.info(f"消息内容: {msg.content}")
        print(f"[发送者 open_id] {msg.sender_id}")

        # 添加表情回应（表示正在处理）
        reaction_id = None
        if self.config.emoji_types:
            emoji = random.choice(self.config.emoji_types)
            reaction_id = await self.feishu.add_reaction(msg.message_id, emoji)

        try:
            # 判断消息类型
            msg_type = msg.content.get("msg_type", "")
            is_text = msg_type == "text"
            is_image = msg_type == "image"
            is_post = msg_type == "post"

            # 提取图片 key 和文本
            image_key = None
            text = None

            try:
                content_obj = json.loads(msg.content.get("content", "{}"))
            except Exception:
                content_obj = {}

            if is_text:
                text = content_obj.get("text", "")
            elif is_image:
                image_key = content_obj.get("image_key")
            elif is_post:
                # post 格式有两种：
                # 1. {"zh_cn": {"content": [[...]]}}
                # 2. {"title": "", "content": [[...]]}  (直接格式)
                texts, image_keys = [], []
                if "content" in content_obj and isinstance(content_obj["content"], list):
                    lang_content = content_obj
                else:
                    lang_content = content_obj.get("zh_cn") or content_obj.get("en_us") or next(iter(content_obj.values()), {})
                    if isinstance(lang_content, str):
                        try:
                            lang_content = json.loads(lang_content)
                        except Exception:
                            lang_content = {}
                for line in lang_content.get("content", []):
                    for block in line:
                        if block.get("tag") == "text":
                            texts.append(block.get("text", ""))
                        elif block.get("tag") == "img":
                            image_keys.append(block.get("image_key"))
                text = "".join(texts).strip() or None
                image_key = image_keys[0] if image_keys else None

            # 如果是单聊且不使用话题，我们用 chat_id + sender_id 作为会话 ID，使得同一个人在这个群聊/单聊内享有独立的上下文
            conv_key = f"{msg.chat_id}:{msg.sender_id}"
            if msg.topic_id and self.config.use_topic_reply:
                conv_key = msg.topic_id

            # 纯图片消息：用占位文本触发 agent
            if is_image and image_key and not text:
                text = "[图片]"

            # 检查是否是对待处理图片的选择指令
            pending = self.pending_images.get(conv_key)
            image_message_id = None  # 图片所在消息的ID（用于下载）
            if pending and text and text.strip() in ("1", "2"):
                choice = text.strip()
                self.pending_images.pop(conv_key, None)
                image_key = pending["image_key"]
                image_message_id = pending["message_id"]
                text = "请将图片转换为 Mermaid 图表代码" if choice == "1" else "请描述这张图片的内容"

            # 处理会话逻辑
            if not msg.topic_id:
                # 新会话
                reply_msg_id, thread_id = await self.feishu.reply_message(
                    msg.message_id, "...", self.config.use_topic_reply
                )
                if self.config.use_topic_reply:
                    self.session_map[msg.message_id] = thread_id
                    self._save_sessions()
                    conv_key = thread_id

                if text:
                    await self._stream_reply(conv_key, reply_msg_id, msg.chat_id, text, is_new=True,
                                             image_key=image_key, message_id=image_message_id or msg.message_id)
            else:
                # 已有会话
                thread_id = self.session_map.get(msg.topic_id) if self.config.use_topic_reply else msg.topic_id
                if not thread_id:
                    reply_msg_id, thread_id = await self.feishu.reply_message(
                        msg.message_id, "...", self.config.use_topic_reply
                    )
                    if self.config.use_topic_reply:
                        self.session_map[msg.topic_id] = thread_id
                        self._save_sessions()
                        conv_key = thread_id

                    if text:
                        await self._stream_reply(conv_key, reply_msg_id, msg.chat_id, text, is_new=True,
                                                 image_key=image_key, message_id=image_message_id or msg.message_id)
                else:
                    if self.config.use_topic_reply:
                        conv_key = thread_id

                    if text:
                        reply_msg_id, _ = await self.feishu.reply_message(
                            msg.message_id, "...", self.config.use_topic_reply
                        )
                        await self._stream_reply(conv_key, reply_msg_id, msg.chat_id, text, is_new=False,
                                                 image_key=image_key, message_id=image_message_id or msg.message_id)
        finally:
            # 移除表情回应
            if reaction_id:
                await self.feishu.remove_reaction(msg.message_id, reaction_id)

    def _detect_image_mime(self, data: bytes) -> str:
        """
        通过文件头（魔数）检测图片 MIME 类型

        Args:
            data: 图片二进制数据

        Returns:
            str: MIME 类型（image/png, image/jpeg, image/gif, image/webp）
        """
        if data.startswith(b'\x89PNG'):
            return "image/png"
        elif data.startswith(b'\xFF\xD8\xFF'):
            return "image/jpeg"
        elif data.startswith(b'GIF'):
            return "image/gif"
        elif data.startswith(b'RIFF') and len(data) >= 12 and data[8:12] == b'WEBP':
            return "image/webp"
        else:
            return "image/png"  # 默认返回 PNG

    async def _process_link(self, link: str) -> str:
        """
        处理飞书链接，提取文档内容

        支持三种类型的飞书文档：
        1. 知识库文档 (wiki)
        2. 新版文档 (docx)
        3. 旧版文档 (doc)

        Args:
            link: 飞书文档链接

        Returns:
            str: 文档内容或原始链接
        """
        # 匹配知识库链接 (feishu.cn/wiki/xxx)
        wiki_match = re.search(r'feishu\.cn/wiki/([a-zA-Z0-9]+)', link)
        if wiki_match:
            node_token = wiki_match.group(1)
            if not self.doc_client:
                token = await self.feishu.get_access_token()
                self.doc_client = FeishuDocClient(token)
            content = await self.doc_client.extract_wiki(node_token)
            if content:
                return f"[飞书知识库文档]\n{content}"

        # 匹配新版文档链接 (feishu.cn/docx/xxx)
        docx_match = re.search(r'feishu\.cn/docx/([a-zA-Z0-9]+)', link)
        if docx_match:
            document_id = docx_match.group(1)
            if not self.doc_client:
                token = await self.feishu.get_access_token()
                self.doc_client = FeishuDocClient(token)
            content = await self.doc_client.extract_docx(document_id)
            if content:
                return f"[飞书文档]\n{content}"

        # 匹配旧版文档链接 (feishu.cn/docs/xxx)
        doc_match = re.search(r'feishu\.cn/docs/([a-zA-Z0-9]+)', link)
        if doc_match:
            doc_token = doc_match.group(1)
            if not self.doc_client:
                token = await self.feishu.get_access_token()
                self.doc_client = FeishuDocClient(token)
            content = await self.doc_client.extract_doc(doc_token)
            if content:
                return f"[飞书文档]\n{content}"

        # 普通链接直接返回
        return link

    async def _prepare_prompt(self, conv_key: str, chat_id: str, text: str, is_new: bool) -> List[dict]:
        """
        准备发送给 Claude 的 prompt 内容结构
        这里使用标准 [{"role": "user/assistant", "content": [...]}, ...] 结构

        Args:
            conv_key: 话题 ID 或者 组合(chat_id:sender_id) 会话 ID
            chat_id: 飞书原始群/会话 ID
            text: 当前消息文本
            is_new: 是否为飞书上的新会话节点

        Returns:
            List[dict]: 历史+当前消息组装出来的多轮对话
        """
        if conv_key not in self.conversations:
            self.conversations[conv_key] = []

        history = self.conversations[conv_key]

        # 当前用户的新输入块（目前只支持文本，如需支持图片需要另外聚合单条消息的图片，这比较复杂）
        user_content = [self.ai.text_block(text)]

        # 不再走飞书的 aggregate_topic 接口拉取漫游记录。
        # 上下文全权交由本地 history 接管（重启也会从 history.json 恢复）

        # 始终把当前的真实问句作为独立的 User 角色压进去！
        history.append({"role": "user", "content": user_content})

        # ------ 控制轮次逻辑 ------
        # 我们保留最近 N 轮（一问一答算两轮 -> history中有两个对象），再加上最前面的系统提示词等
        max_msgs = self.config.max_history_turns * 2
        # 去掉超出的最早期消息（保留最后N句即可，不用太复杂）
        if len(history) > max_msgs:
            # 删去旧轮次，但确保留下的一定是以 user 开始！
            while len(history) > max_msgs:
                history.pop(0)
            if history and history[0]["role"] == "assistant":
                history.pop(0)

        # 把变更实时存进文件（你发的话）
        self._save_history()

        # 这里其实不用再返回出去了，直接拿 self.conversations[conv_key]
        return history.copy()

    async def handle_desktop_command(
        self,
        conv_key: str,
        text: str,
        send_event: Callable[[dict], Awaitable[None]],
        metadata: dict | None = None,
    ) -> str:
        """处理 miniPet 桌宠消息，不触碰飞书回复链路。"""
        text = (text or "").strip()
        if not text:
            await send_event({
                "version": "1.0",
                "type": "surface.show",
                "source": "miniclaw",
                "payload": {
                    "kind": "bubble",
                    "title": "miniClaw",
                    "content": "我没有收到要处理的内容。",
                    "timeout_ms": 6000,
                },
            })
            return ""

        chat_id = conv_key
        try:
            messages = await self._prepare_prompt(conv_key, chat_id, text, is_new=False)

            surface_id = f"desktop-reply-{uuid4().hex}"
            await send_event({
                "version": "1.0",
                "type": "surface.show",
                "source": "miniclaw",
                "payload": {
                    "surface_id": surface_id,
                    "kind": "bubble",
                    "title": "miniClaw",
                    "content": "",
                    "streaming": True,
                    "timeout_ms": 60000,
                    "metadata": metadata or {},
                },
            })

            if self.config.use_stream:
                full_text = ""
                last_update = asyncio.get_event_loop().time()
                async for chunk in self.ai.stream(messages, system=self.config.system_prompt):
                    full_text += chunk
                    now = asyncio.get_event_loop().time()
                    if now - last_update >= 0.15:
                        await send_event({
                            "version": "1.0",
                            "type": "surface.update",
                            "source": "miniclaw",
                            "payload": {
                                "surface_id": surface_id,
                                "content": full_text,
                                "done": False,
                                "timeout_ms": 60000,
                                "metadata": metadata or {},
                            },
                        })
                        last_update = now
            else:
                full_text = await self.agent.run(
                    messages,
                    system_prompt=self.config.system_prompt,
                    chat_id=chat_id,
                )

            full_text = _append_mermaid_links((full_text or "").strip())
            if not full_text:
                full_text = "(无响应)"

            self.conversations[conv_key].append({"role": "assistant", "content": [self.ai.text_block(full_text)]})
            self._save_history()

            await send_event({
                "version": "1.0",
                "type": "surface.update",
                "source": "miniclaw",
                "payload": {
                    "surface_id": surface_id,
                    "content": full_text,
                    "done": True,
                    "timeout_ms": 10000,
                    "metadata": metadata or {},
                },
            })
            return full_text
        except Exception as e:
            logging.error(f"桌宠消息处理失败: {e}", exc_info=True)
            if conv_key in self.conversations and self.conversations[conv_key]:
                self.conversations[conv_key].pop()
                self._save_history()
            await send_event({
                "version": "1.0",
                "type": "surface.show",
                "source": "miniclaw",
                "payload": {
                    "kind": "bubble",
                    "title": "miniClaw 出错了",
                    "content": "处理失败，请稍后重试",
                    "timeout_ms": 8000,
                    "metadata": metadata or {},
                },
            })
            return ""

    async def _stream_reply(self, conv_key: str, reply_msg_id: str, chat_id: str, text: str, is_new: bool,
                            image_key: str = None, message_id: str = None):
        """
        调用 Agent 并更新飞书消息，支持流式和非流式两种模式

        Args:
            conv_key: 话题或对话组合键 ID
            reply_msg_id: 回复消息 ID
            chat_id: 会话 ID
            text: 用户消息文本
            is_new: 是否为新会话
            image_key: 图片 key（可选）
            message_id: 飞书消息 ID（图片下载需要）
        """
        try:
            # 准备 prompt 内容（里面包含最近历史）
            messages = await self._prepare_prompt(conv_key, chat_id, text, is_new)

            # 如果有图片，下载并追加到最后一条 user message
            if image_key and message_id:
                try:
                    img_data = await self.feishu.download_resource(message_id, image_key, "image")
                    mime = self._detect_image_mime(img_data)
                    messages[-1]["content"].append(self.ai.image_block(img_data, mime))
                except Exception as e:
                    logging.warning(f"图片下载失败: {e}")

            if self.config.use_stream:
                # 流式调用 Claude API（agent 暂不支持流式，直接用 claude.stream）
                full_text = ""
                last_update = asyncio.get_event_loop().time()
                chunk_count = 0

                logging.info(f"开始流式处理，历史条数(不是块数): {len(messages)}")

                async for chunk in self.ai.stream(messages, system=self.config.system_prompt):
                    chunk_count += 1
                    full_text += chunk
                    now = asyncio.get_event_loop().time()

                    # 每 100ms 更新一次飞书消息（节流）
                    if now - last_update >= 0.1:
                        await self.feishu.update_message(reply_msg_id, full_text.strip())
                        last_update = now

                logging.info(f"流式处理完成，收到 {chunk_count} 个块，总长度: {len(full_text)}")
            else:
                # 通过 agent 处理（支持 function calling 技能路由）
                logging.info(f"开始 Agent 处理，历史条数: {len(messages)}")
                full_text = await self.agent.run(
                    messages,
                    system_prompt=self.config.system_prompt,
                    image_key=image_key,
                    message_id=message_id,
                    chat_id=chat_id
                )
                logging.info(f"Agent 处理完成，总长度: {len(full_text)}")

            logging.info(f"大模型响应内容: {full_text.strip()[:100]}")

            full_text = _append_mermaid_links(full_text)

            # 最终更新消息，并把它当做 assistant 存起来！
            if full_text.strip():
                await self.feishu.update_message(reply_msg_id, full_text.strip())
                # 保存助手回复到对话历史，严格作为 assistant
                self.conversations[conv_key].append({"role": "assistant", "content": [self.ai.text_block(full_text.strip())]})
                # 存盘
                self._save_history()
            else:
                logging.warning("收到空响应")
                await self.feishu.update_message(reply_msg_id, "(无响应)")

        except Exception as e:
            logging.error(f"流式处理失败: {e}", exc_info=True)

            # 根据错误类型提供友好提示
            error_str = str(e)
            if "blocked" in error_str.lower() or "permission" in error_str.lower():
                user_msg = "请求被拦截"
                # 清空当前会话最后一条用户消息，避免重复触发
                if conv_key in self.conversations and self.conversations[conv_key]:
                    self.conversations[conv_key].pop()
                    self._save_history()
            elif "502" in error_str or "upstream" in error_str.lower():
                user_msg = "Claude 服务暂时不可用，请稍后重试"
            elif "429" in error_str or "rate_limit" in error_str.lower():
                user_msg = "请求过于频繁，请稍后再试"
            elif "401" in error_str or "authentication" in error_str.lower():
                user_msg = "API 认证失败，请检查配置"
            elif "timeout" in error_str.lower():
                user_msg = "请求超时，请重试"
            else:
                user_msg = "处理失败，请重试或联系管理员"

            await self.feishu.update_message(reply_msg_id, user_msg)
