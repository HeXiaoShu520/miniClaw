"""
Anthropic (Claude) 客户端实现
"""
from typing import AsyncIterator

import httpx
from anthropic import AsyncAnthropic

from ai_client import AIClient


class AnthropicClient(AIClient):
    """Anthropic Claude API 客户端"""

    def __init__(self, api_key: str, model: str, base_url: str = None):
        super().__init__(model)
        http_client = httpx.AsyncClient(
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        )
        self.client = AsyncAnthropic(
            api_key=api_key,
            base_url=base_url,
            http_client=http_client
        )

    async def call(self, messages: list[dict], system: str = None) -> str:
        kwargs = {"model": self.model, "max_tokens": 4096, "messages": messages}
        if system:
            kwargs["system"] = system
        response = await self.client.messages.create(**kwargs)
        return response.content[0].text

    async def stream(self, messages: list[dict], system: str = None) -> AsyncIterator[str]:
        kwargs = {"model": self.model, "max_tokens": 4096, "messages": messages}
        if system:
            kwargs["system"] = system
        async with self.client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield text

    async def create_with_tools(self, messages: list[dict], tools: list[dict]) -> dict:
        kwargs = {"model": self.model, "max_tokens": 4096, "messages": messages, "tools": tools}
        response = await self.client.messages.create(**kwargs)

        tool_use = next((b for b in response.content if b.type == "tool_use"), None)
        text = next((b.text for b in response.content if b.type == "text"), None)

        if tool_use:
            return {
                "text": text,
                "tool_call": {"id": tool_use.id, "name": tool_use.name, "input": tool_use.input},
                "raw_content": response.content,
            }
        return {"text": text or "", "tool_call": None, "raw_content": response.content}

    async def create_with_tool_result(self, messages: list[dict], tools: list[dict],
                                       assistant_content, tool_call_id: str, tool_result: str, system: str = None) -> str:
        messages_with_result = messages + [
            {"role": "assistant", "content": assistant_content},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tool_call_id, "content": tool_result}]}
        ]
        kwargs = {"model": self.model, "max_tokens": 4096, "messages": messages_with_result, "tools": tools}
        if system:
            kwargs["system"] = system
        response = await self.client.messages.create(**kwargs)
        return next((b.text for b in response.content if b.type == "text"), "")
