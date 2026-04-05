"""
OpenAI 客户端实现
消息格式在内部从 Anthropic 风格转换为 OpenAI 风格
"""
import json
import logging
from typing import AsyncIterator

from openai import AsyncOpenAI

from ai_client import AIClient


def _convert_messages(messages: list[dict], system: str = None) -> list[dict]:
    """将 Anthropic 格式的消息转换为 OpenAI 格式"""
    result = []
    if system:
        result.append({"role": "system", "content": system})

    for msg in messages:
        role = msg["role"]
        content = msg.get("content")

        # 纯字符串内容直接用
        if isinstance(content, str):
            result.append({"role": role, "content": content})
            continue

        # Anthropic 的 content 是 list[block]，需要转换
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, dict):
                    btype = block.get("type")
                    if btype == "text":
                        parts.append({"type": "text", "text": block["text"]})
                    elif btype == "image":
                        source = block.get("source", {})
                        b64 = source.get("data", "")
                        mime = source.get("media_type", "image/png")
                        parts.append({
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{b64}"}
                        })
                else:
                    parts.append({"type": "text", "text": str(block)})

            if len(parts) == 1 and parts[0]["type"] == "text":
                result.append({"role": role, "content": parts[0]["text"]})
            else:
                result.append({"role": role, "content": parts})
        else:
            result.append({"role": role, "content": str(content)})

    return result


def _convert_tools(tools: list[dict]) -> list[dict]:
    """将 Anthropic 格式的 tools 转换为 OpenAI function calling 格式"""
    result = []
    for tool in tools:
        result.append({
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool.get("input_schema", {"type": "object", "properties": {}})
            }
        })
    return result


class OpenAIClient(AIClient):
    """OpenAI API 客户端"""

    def __init__(self, api_key: str, model: str, base_url: str = None):
        super().__init__(model)
        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self.client = AsyncOpenAI(**kwargs)

    async def call(self, messages: list[dict], system: str = None) -> str:
        oai_msgs = _convert_messages(messages, system)
        response = await self.client.chat.completions.create(
            model=self.model, messages=oai_msgs, max_tokens=4096
        )
        return response.choices[0].message.content or ""

    async def stream(self, messages: list[dict], system: str = None) -> AsyncIterator[str]:
        oai_msgs = _convert_messages(messages, system)
        stream = await self.client.chat.completions.create(
            model=self.model, messages=oai_msgs, max_tokens=4096, stream=True
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                yield delta.content

    async def create_with_tools(self, messages: list[dict], tools: list[dict], system: str = None) -> dict:
        oai_msgs = _convert_messages(messages, system)
        oai_tools = _convert_tools(tools)
        response = await self.client.chat.completions.create(
            model=self.model, messages=oai_msgs, max_tokens=4096, tools=oai_tools
        )
        msg = response.choices[0].message
        tool_calls = msg.tool_calls

        if tool_calls and len(tool_calls) > 0:
            tc = tool_calls[0]
            return {
                "text": msg.content,
                "tool_call": {
                    "id": tc.id,
                    "name": tc.function.name,
                    "input": json.loads(tc.function.arguments)
                },
                "raw_content": msg,
            }
        return {"text": msg.content or "", "tool_call": None, "raw_content": msg}

    async def create_with_tool_result(self, messages: list[dict], tools: list[dict],
                                       assistant_content, tool_call_id: str, tool_result: str, system: str = None) -> str:
        oai_msgs = _convert_messages(messages, system)
        # 追加 assistant 的 tool_calls 消息
        assistant_msg = {
            "role": "assistant",
            "content": assistant_content.content,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments}
                }
                for tc in (assistant_content.tool_calls or [])
            ]
        }
        oai_msgs.append(assistant_msg)
        # 追加 tool result
        oai_msgs.append({"role": "tool", "tool_call_id": tool_call_id, "content": tool_result})

        oai_tools = _convert_tools(tools)
        response = await self.client.chat.completions.create(
            model=self.model, messages=oai_msgs, max_tokens=4096, tools=oai_tools
        )
        return response.choices[0].message.content or ""
