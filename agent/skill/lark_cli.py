"""
lark-cli 技能：通过用户身份（OAuth）操作飞书
需提前在终端执行 `lark-cli auth login` 完成授权。

支持操作：
  - send_message: 发消息给用户
  - get_agenda: 查看日程
  - create_event: 创建日历事件
  - create_task: 创建任务
  - query_freebusy: 查询空闲时间
"""
import asyncio
import json
from typing import Optional

ENABLED = True

TOOL_DEF = {
    "name": "lark_cli",
    "description": (
        "通过用户身份操作飞书，支持：发消息、查看/创建日程、创建任务、查询空闲时间。"
        "当用户要求创建日程、添加任务、查看日历、发消息给某人时调用此工具。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["send_message", "get_agenda", "create_event", "create_task", "query_freebusy"],
                "description": "要执行的操作"
            },
            "user_id": {
                "type": "string",
                "description": "目标用户 open_id（send_message / query_freebusy 时使用）"
            },
            "text": {
                "type": "string",
                "description": "消息内容（send_message 时使用）"
            },
            "date": {
                "type": "string",
                "description": "日期，格式 YYYY-MM-DD（get_agenda 时使用，默认今天）"
            },
            "summary": {
                "type": "string",
                "description": "日程/任务标题"
            },
            "start": {
                "type": "string",
                "description": "开始时间，ISO 8601 格式，如 2026-04-07T14:00:00+08:00（create_event 时使用）"
            },
            "end": {
                "type": "string",
                "description": "结束时间，ISO 8601 格式（create_event 时使用）"
            },
            "description": {
                "type": "string",
                "description": "日程/任务描述（可选）"
            },
            "attendees": {
                "type": "array",
                "items": {"type": "string"},
                "description": "参与者 open_id 列表（create_event 时可选）"
            },
            "due": {
                "type": "string",
                "description": "任务截止时间，ISO 8601 格式（create_task 时可选）"
            },
            "notify_user_id": {
                "type": "string",
                "description": "创建任务/日程后，将结果链接发送给该用户的 open_id（可选）"
            }
        },
        "required": ["action"]
    }
}


async def _run(args: list[str], no_format: bool = False) -> dict:
    """执行 lark-cli 命令，返回解析后的结果"""
    cmd = ["lark-cli"] + args + ([] if no_format else ["--format", "json"])
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(stderr.decode().strip())
    return json.loads(stdout.decode().strip()) if stdout.strip() else {}


async def execute(
    action: str,
    user_id: str = "",
    text: str = "",
    date: str = "",
    summary: str = "",
    start: str = "",
    end: str = "",
    description: str = "",
    attendees: Optional[list] = None,
    due: str = "",
    notify_user_id: str = "",
) -> str:
    try:
        if action == "send_message":
            if not user_id or not text:
                return "缺少 user_id 或 text 参数"
            result = await _run(["im", "+messages-send", "--user-id", user_id, "--text", text], no_format=True)
            return f"消息已发送：{json.dumps(result, ensure_ascii=False)}"

        elif action == "get_agenda":
            args = ["calendar", "+agenda"]
            if date:
                args += ["--start", f"{date}T00:00:00+08:00", "--end", f"{date}T23:59:59+08:00"]
            result = await _run(args)
            return json.dumps(result, ensure_ascii=False, indent=2)

        elif action == "create_event":
            if not summary or not start or not end:
                return "缺少 summary、start 或 end 参数"
            args = ["calendar", "+create", "--summary", summary, "--start", start, "--end", end]
            if description:
                args += ["--description", description]
            if attendees:
                args += ["--attendees", ",".join(attendees)]
            result = await _run(args)
            event_link = result.get("data", {}).get("app_link", "")
            if notify_user_id and event_link:
                await _run(["im", "+messages-send", "--user-id", notify_user_id,
                            "--text", f"📅 日程已创建：{summary}\n🕐 {start} ~ {end}\n🔗 {event_link}"], no_format=True)
            return f"日程已创建：{json.dumps(result, ensure_ascii=False)}"

        elif action == "create_task":
            if not summary:
                return "缺少 summary 参数"
            args = ["task", "+create", "--summary", summary]
            if due:
                args += ["--due", due]
            if description:
                args += ["--description", description]
            result = await _run(args)
            task_url = result.get("data", {}).get("url", "")
            if notify_user_id and task_url:
                await _run(["im", "+messages-send", "--user-id", notify_user_id,
                            "--text", f"✅ 任务已创建：{summary}\n🔗 {task_url}"], no_format=True)
            return f"任务已创建：{json.dumps(result, ensure_ascii=False)}"

        elif action == "query_freebusy":
            if not user_id:
                return "缺少 user_id 参数"
            args = ["calendar", "+freebusy", "--user-id", user_id]
            if date:
                args += ["--start", f"{date}T00:00:00+08:00", "--end", f"{date}T23:59:59+08:00"]
            result = await _run(args)
            return json.dumps(result, ensure_ascii=False, indent=2)

        else:
            return f"未知操作: {action}"

    except RuntimeError as e:
        return f"执行失败: {e}"
