"""飞书聊天主路由 Agent：用 function calling 决定调用哪个技能"""
import importlib
import logging
import pkgutil
from typing import Optional, Dict, Any

import agent.skill as skill_pkg
from ai_client import AIClient

GREEN = "\033[92m"
GRAY = "\033[90m"
RESET = "\033[0m"


def _log_route(skill_name: str):
    print(f"{GREEN}[路由 -> {skill_name}]{RESET}")
    logging.info(f"[路由 -> {skill_name}]")


def load_skills() -> tuple[list[dict], Dict[str, Any]]:
    """
    扫描 agent/skill 目录，加载所有技能模块，打印加载状态
    返回 (tools_list, skill_modules_dict)
    """
    tools = []
    modules = {}

    print(f"\n{'='*20} 技能加载 {'='*20}")
    for importer, mod_name, is_pkg in pkgutil.iter_modules(skill_pkg.__path__):
        if mod_name.startswith("_"):
            continue
        try:
            mod = importlib.import_module(f"agent.skill.{mod_name}")
            enabled = getattr(mod, "ENABLED", False)
            tool_def = getattr(mod, "TOOL_DEF", None)
            name = tool_def["name"] if tool_def else mod_name

            if enabled and tool_def:
                tools.append(tool_def)
                modules[name] = mod
                print(f"  {GREEN}[✓] {name}{RESET}")
            else:
                print(f"  {GRAY}[✗] {name} (已禁用){RESET}")
        except Exception as e:
            print(f"  {GRAY}[✗] {mod_name} (加载失败: {e}){RESET}")
    print(f"{'='*50}\n")

    return tools, modules


class FeishuChatAgent:
    def __init__(self, ai_client: AIClient, feishu_client):
        self.ai = ai_client
        self.feishu = feishu_client
        self.tools, self.skill_modules = load_skills()

    async def run(self, messages: list, system_prompt: Optional[str] = None, image_key: Optional[str] = None, message_id: Optional[str] = None, chat_id: Optional[str] = None) -> str:
        """
        主入口：先让大模型决定是否调用技能，再执行并返回最终回复
        """
        if not self.tools:
            # 没有技能，直接调用
            return await self.ai.call(messages, system=system_prompt)

        # 第一次调用：让模型决定是否使用工具
        result = await self.ai.create_with_tools(messages, self.tools, system=system_prompt)

        if result["tool_call"] is None:
            _log_route("直接回复")
            return result["text"] or ""

        # 执行技能
        tool_call = result["tool_call"]
        tool_name = tool_call["name"]
        tool_input = tool_call["input"]
        _log_route(tool_name)

        mod = self.skill_modules.get(tool_name)
        if not mod:
            tool_result = f"未知技能: {tool_name}"
        elif tool_name == "read_feishu_doc":
            tool_result = await mod.execute(tool_input["url"], self.feishu)
        elif tool_name == "image_to_mermaid":
            img_key = tool_input.get("image_key") or image_key
            msg_id = tool_input.get("message_id") or message_id
            tool_result = await mod.execute(msg_id, img_key, self.feishu, self.ai)
            return tool_result
        elif tool_name == "tts_reply":
            text = tool_input.get("text", "")
            cid = tool_input.get("chat_id") or chat_id or ""
            tool_result = await mod.execute(text, cid, self.feishu, self.ai)
            # tts_reply 直接发送音频，无需第二次 AI 调用
            return tool_result
        elif tool_name == "meme_search":
            cid = tool_input.get("chat_id") or chat_id or ""
            tool_result = await mod.execute(
                query=tool_input.get("query", ""),
                chat_id=cid,
                feishu_client=self.feishu,
                index=tool_input.get("index", 1),
                count=tool_input.get("count", 5),
                send_count=tool_input.get("send_count", 1),
                extra_keywords=tool_input.get("extra_keywords"),
                image_shape=tool_input.get("image_shape", "方形"),
            )
            # meme_search 会直接发送图片，无需第二次 AI 调用
            return tool_result
        else:
            tool_result = await mod.execute(**tool_input)

        # 第二次调用：把技能结果发回模型，得到最终回复
        try:
            return await self.ai.create_with_tool_result(
                messages, self.tools, result["raw_content"], tool_call["id"], tool_result, system=system_prompt
            )
        except Exception as e:
            logging.warning(f"工具结果回传不可用，直接返回技能结果: {e}")
            return str(tool_result)
