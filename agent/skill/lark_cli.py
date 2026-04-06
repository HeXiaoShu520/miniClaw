"""
lark-cli 技能：通过用户身份（OAuth）操作飞书
需提前在终端执行 `lark-cli auth login` 完成授权。

支持操作：
  - send_message: 发消息给用户
  - get_agenda: 查看日程
  - create_event: 创建日历事件
  - create_task: 创建任务
  - query_freebusy: 查询空闲时间
  - search_user: 搜索/获取用户信息
  - sheets_read: 读取表格数据
  - sheets_write: 写入表格数据
  - sheets_append: 追加表格数据
  - drive_upload: 上传文件到云盘
  - drive_download: 从云盘下载文件
  - drive_add_comment: 给文档添加评论
  - wiki_list_spaces: 列出知识库空间
  - wiki_list_nodes: 列出知识库节点
  - base_create: 创建多维表格
  - base_read: 读取多维表格记录
  - base_write: 写入多维表格记录
"""
import asyncio
import json
from typing import Optional

ENABLED = True

TOOL_DEF = {
    "name": "lark_cli",
    "description": (
        "通过用户身份操作飞书，支持：发消息、查看/创建日程、创建任务、查询空闲时间、"
        "搜索用户、读写表格、上传/下载云盘文件、给文档添加评论、查看知识库、读写多维表格。"
        "当用户要求操作飞书相关功能时调用此工具。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "send_message", "get_agenda", "create_event", "create_task", "query_freebusy",
                    "search_user", "sheets_read", "sheets_write", "sheets_append",
                    "drive_upload", "drive_download", "drive_add_comment",
                    "wiki_list_spaces", "wiki_list_nodes",
                    "base_create", "base_read", "base_write"
                ],
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
                "description": "日期，格式 YYYY-MM-DD（get_agenda / query_freebusy 时使用，默认今天）"
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
            },
            "query": {
                "type": "string",
                "description": "搜索关键词（search_user 时使用）"
            },
            "spreadsheet_url": {
                "type": "string",
                "description": "表格 URL（sheets_read / sheets_write / sheets_append 时使用）"
            },
            "sheet_id": {
                "type": "string",
                "description": "Sheet ID（sheets_read / sheets_write / sheets_append 时使用）"
            },
            "range": {
                "type": "string",
                "description": "单元格范围，如 A1:D10（sheets_read / sheets_write / sheets_append 时使用）"
            },
            "values": {
                "type": "array",
                "items": {"type": "array"},
                "description": "二维数组数据（sheets_write / sheets_append 时使用）"
            },
            "file_path": {
                "type": "string",
                "description": "本地文件路径（drive_upload 时使用，必须是相对路径）"
            },
            "file_name": {
                "type": "string",
                "description": "上传后的文件名（drive_upload 时可选）"
            },
            "file_token": {
                "type": "string",
                "description": "云盘文件 token（drive_download 时使用）"
            },
            "output_path": {
                "type": "string",
                "description": "下载保存路径（drive_download 时使用）"
            },
            "doc": {
                "type": "string",
                "description": "文档 URL 或 token，支持 wiki URL（drive_add_comment 时使用）"
            },
            "comment": {
                "type": "string",
                "description": "评论内容文本（drive_add_comment 时使用）"
            },
            "space_id": {
                "type": "string",
                "description": "知识库空间 ID（wiki_list_nodes 时使用）"
            },
            "base_token": {
                "type": "string",
                "description": "多维表格 token（base_read / base_write 时使用）"
            },
            "table_id": {
                "type": "string",
                "description": "多维表格数据表 ID（base_read / base_write 时使用）"
            },
            "base_name": {
                "type": "string",
                "description": "多维表格名称（base_create 时使用）"
            },
            "record": {
                "type": "object",
                "description": "要写入的记录字段，如 {\"文本\": \"内容\"}（base_write 时使用）"
            },
            "record_id": {
                "type": "string",
                "description": "记录 ID（base_write 更新时可选）"
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
    query: str = "",
    spreadsheet_url: str = "",
    sheet_id: str = "",
    range: str = "",
    values: Optional[list] = None,
    file_path: str = "",
    file_name: str = "",
    file_token: str = "",
    output_path: str = "",
    doc: str = "",
    comment: str = "",
    space_id: str = "",
    base_token: str = "",
    table_id: str = "",
    base_name: str = "",
    record: Optional[dict] = None,
    record_id: str = "",
) -> str:
    try:
        # ── 消息 ──────────────────────────────────────────────
        if action == "send_message":
            if not user_id or not text:
                return "缺少 user_id 或 text 参数"
            result = await _run(["im", "+messages-send", "--user-id", user_id, "--text", text], no_format=True)
            return f"消息已发送：{json.dumps(result, ensure_ascii=False)}"

        # ── 日历 ──────────────────────────────────────────────
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

        elif action == "query_freebusy":
            if not user_id:
                return "缺少 user_id 参数"
            args = ["calendar", "+freebusy", "--user-id", user_id]
            if date:
                args += ["--start", f"{date}T00:00:00+08:00", "--end", f"{date}T23:59:59+08:00"]
            result = await _run(args)
            return json.dumps(result, ensure_ascii=False, indent=2)

        # ── 任务 ──────────────────────────────────────────────
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

        # ── 联系人 ────────────────────────────────────────────
        elif action == "search_user":
            if query:
                result = await _run(["contact", "+search-user", "--query", query])
            else:
                result = await _run(["contact", "+get-user"] + (["--user-id", user_id] if user_id else []))
            return json.dumps(result, ensure_ascii=False, indent=2)

        # ── 表格 ──────────────────────────────────────────────
        elif action == "sheets_read":
            if not spreadsheet_url or not sheet_id or not range:
                return "缺少 spreadsheet_url、sheet_id 或 range 参数"
            result = await _run(["sheets", "+read", "--url", spreadsheet_url, "--sheet-id", sheet_id, "--range", range])
            return json.dumps(result, ensure_ascii=False, indent=2)

        elif action == "sheets_write":
            if not spreadsheet_url or not sheet_id or not range or values is None:
                return "缺少 spreadsheet_url、sheet_id、range 或 values 参数"
            result = await _run(["sheets", "+write", "--url", spreadsheet_url, "--sheet-id", sheet_id,
                                  "--range", range, "--values", json.dumps(values, ensure_ascii=False)])
            return json.dumps(result, ensure_ascii=False, indent=2)

        elif action == "sheets_append":
            if not spreadsheet_url or not sheet_id or not range or values is None:
                return "缺少 spreadsheet_url、sheet_id、range 或 values 参数"
            result = await _run(["sheets", "+append", "--url", spreadsheet_url, "--sheet-id", sheet_id,
                                  "--range", range, "--values", json.dumps(values, ensure_ascii=False)])
            return json.dumps(result, ensure_ascii=False, indent=2)

        # ── 云盘 ──────────────────────────────────────────────
        elif action == "drive_upload":
            if not file_path:
                return "缺少 file_path 参数"
            args = ["drive", "+upload", "--file", file_path]
            if file_name:
                args += ["--name", file_name]
            result = await _run(args)
            return json.dumps(result, ensure_ascii=False, indent=2)

        elif action == "drive_download":
            if not file_token or not output_path:
                return "缺少 file_token 或 output_path 参数"
            result = await _run(["drive", "+download", "--file-token", file_token, "--output", output_path, "--overwrite"])
            return json.dumps(result, ensure_ascii=False, indent=2)

        elif action == "drive_add_comment":
            if not doc or not comment:
                return "缺少 doc 或 comment 参数"
            content = json.dumps([{"type": "text", "text": comment}], ensure_ascii=False)
            result = await _run(["drive", "+add-comment", "--doc", doc, "--content", content, "--full-comment"])
            return json.dumps(result, ensure_ascii=False, indent=2)

        # ── 知识库 ────────────────────────────────────────────
        elif action == "wiki_list_spaces":
            result = await _run(["wiki", "spaces", "list"])
            return json.dumps(result, ensure_ascii=False, indent=2)

        elif action == "wiki_list_nodes":
            if not space_id:
                return "缺少 space_id 参数"
            result = await _run(["wiki", "nodes", "list", "--params", json.dumps({"space_id": space_id})])
            return json.dumps(result, ensure_ascii=False, indent=2)

        # ── 多维表格 ──────────────────────────────────────────
        elif action == "base_create":
            if not base_name:
                return "缺少 base_name 参数"
            result = await _run(["base", "+base-create", "--name", base_name, "--time-zone", "Asia/Shanghai"])
            return json.dumps(result, ensure_ascii=False, indent=2)

        elif action == "base_read":
            if not base_token or not table_id:
                return "缺少 base_token 或 table_id 参数"
            result = await _run(["base", "+record-list", "--base-token", base_token, "--table-id", table_id])
            return json.dumps(result, ensure_ascii=False, indent=2)

        elif action == "base_write":
            if not base_token or not table_id or record is None:
                return "缺少 base_token、table_id 或 record 参数"
            args = ["base", "+record-upsert", "--base-token", base_token, "--table-id", table_id,
                    "--json", json.dumps(record, ensure_ascii=False)]
            if record_id:
                args += ["--record-id", record_id]
            result = await _run(args)
            return json.dumps(result, ensure_ascii=False, indent=2)

        else:
            return f"未知操作: {action}"

    except RuntimeError as e:
        return f"执行失败: {e}"
