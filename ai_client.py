"""
AI 客户端统一抽象层
支持 Anthropic (Claude) 和 OpenAI 两种 provider，对外暴露统一接口
"""
import base64
import logging
from abc import ABC, abstractmethod
from typing import AsyncIterator

import httpx


class AIClient(ABC):
    """AI 客户端抽象基类"""

    def __init__(self, model: str):
        self.model = model

    @abstractmethod
    async def call(self, messages: list[dict], system: str = None) -> str:
        """非流式调用，返回完整文本"""

    @abstractmethod
    async def stream(self, messages: list[dict], system: str = None) -> AsyncIterator[str]:
        """流式调用，逐块返回文本"""

    @abstractmethod
    async def create_with_tools(self, messages: list[dict], tools: list[dict], system: str = None) -> dict:
        """
        带 function calling 的调用，返回统一格式:
        {
            "text": str | None,
            "tool_call": {"id": str, "name": str, "input": dict} | None,
            "raw_content": <原始 content，用于回传第二轮>
        }
        """

    @abstractmethod
    async def create_with_tool_result(self, messages: list[dict], tools: list[dict],
                                       assistant_content, tool_call_id: str, tool_result: str, system: str = None) -> str:
        """把技能执行结果回传给模型，获取最终回复"""

    @staticmethod
    def text_block(text: str) -> dict:
        return {"type": "text", "text": text}

    @staticmethod
    def image_block(data: bytes, mime_type: str) -> dict:
        b64 = base64.b64encode(data).decode()
        return {"type": "image", "source": {"type": "base64", "media_type": mime_type, "data": b64}}
