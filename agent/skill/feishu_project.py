"""
飞书项目技能：通过飞书项目 API 操作 Story / Epic / Task 等工作项
需在 .env 中配置：
  FEISHU_PROJECT_PLUGIN_ID=xxx
  FEISHU_PROJECT_PLUGIN_SECRET=xxx
  FEISHU_PROJECT_USER_KEY=xxx       # 操作人的 user_key（飞书项目内的用户标识）
  FEISHU_PROJECT_KEY=xxx            # 默认项目 key（可在 URL 中找到）

飞书项目 API 文档：https://project.feishu.cn/open-api
注意：飞书项目使用独立的 API 域名 project.feishu.cn，与普通飞书开放平台不同。
     字段 key（field_key）是动态生成的，不同项目/工作项类型不同，需先调用
     list_fields 查询后使用。

支持操作：
  - list_projects:    列出所有项目
  - list_work_items:  查询工作项列表（支持按类型/状态过滤）
  - get_work_item:    获取工作项详情
  - create_work_item: 创建工作项
  - update_work_item: 更新工作项字段
  - list_fields:      查询工作项类型的字段定义（用于获取 field_key）
  - list_members:     查询项目成员（用于获取 user_key）
  - add_comment:      给工作项添加评论
"""
import asyncio
import json
import logging
import os
import time
from typing import Optional

ENABLED = True

TOOL_DEF = {
    "name": "feishu_project",
    "description": (
        "操作飞书项目（project.feishu.cn），支持查询/创建/更新 Story、Epic、Task 等工作项，"
        "添加评论，查询项目成员和字段定义。当用户要求操作飞书项目相关功能时调用此工具。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "list_projects",
                    "list_work_items",
                    "get_work_item",
                    "create_work_item",
                    "update_work_item",
                    "list_fields",
                    "list_members",
                    "add_comment",
                ],
                "description": "要执行的操作"
            },
            "project_key": {
                "type": "string",
                "description": "项目 key，留空则使用环境变量 FEISHU_PROJECT_KEY"
            },
            "work_item_type_key": {
                "type": "string",
                "description": "工作项类型，如 story / epic / task / bug（list_work_items / create_work_item / list_fields 时使用）"
            },
            "work_item_id": {
                "type": "string",
                "description": "工作项 ID（get_work_item / update_work_item / add_comment 时使用）"
            },
            "name": {
                "type": "string",
                "description": "工作项标题（create_work_item 时使用）"
            },
            "fields": {
                "type": "object",
                "description": (
                    "字段键值对，key 为 field_key（可通过 list_fields 查询），value 为字段值。"
                    "例如：{\"field_633a8b2c\": [\"user_key_xxx\"]}（create_work_item / update_work_item 时使用）"
                )
            },
            "comment": {
                "type": "string",
                "description": "评论内容（add_comment 时使用）"
            },
            "status": {
                "type": "string",
                "description": "按状态过滤工作项（list_work_items 时可选）"
            },
            "page_size": {
                "type": "integer",
                "description": "每页数量，默认 20（list_work_items 时可选）"
            }
        },
        "required": ["action"]
    }
}

BASE_URL = "https://project.feishu.cn/open_api"

# 简单内存缓存 token，避免频繁刷新
_token_cache: dict = {"token": "", "expires_at": 0}


async def _get_token() -> str:
    """获取 plugin token，有效期内复用"""
    now = time.time()
    if _token_cache["token"] and now < _token_cache["expires_at"] - 60:
        return _token_cache["token"]

    plugin_id = os.environ.get("FEISHU_PROJECT_PLUGIN_ID", "")
    plugin_secret = os.environ.get("FEISHU_PROJECT_PLUGIN_SECRET", "")
    if not plugin_id or not plugin_secret:
        raise RuntimeError("未配置 FEISHU_PROJECT_PLUGIN_ID 或 FEISHU_PROJECT_PLUGIN_SECRET")

    import aiohttp
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{BASE_URL}/authen/plugin_token",
            json={"plugin_id": plugin_id, "plugin_secret": plugin_secret, "type": 0}
        ) as resp:
            data = await resp.json()
            if data.get("err_code", 0) != 0:
                raise RuntimeError(f"获取 token 失败: {data.get('err_msg')}")
            token = data["data"]["token"]
            expire = data["data"].get("expire_time", 7200)
            _token_cache["token"] = token
            _token_cache["expires_at"] = now + expire
            return token


async def _request(method: str, path: str, body: dict = None) -> dict:
    """发起飞书项目 API 请求"""
    import aiohttp
    token = await _get_token()
    user_key = os.environ.get("FEISHU_PROJECT_USER_KEY", "")
    headers = {
        "X-PLUGIN-TOKEN": token,
        "Content-Type": "application/json",
    }
    if user_key:
        headers["X-USER-KEY"] = user_key

    url = f"{BASE_URL}{path}"
    async with aiohttp.ClientSession() as session:
        if method == "GET":
            async with session.get(url, headers=headers) as resp:
                return await resp.json()
        else:
            async with session.post(url, headers=headers, json=body or {}) as resp:
                return await resp.json()


def _project_key(override: str = "") -> str:
    return override or os.environ.get("FEISHU_PROJECT_KEY", "")


async def execute(
    action: str,
    project_key: str = "",
    work_item_type_key: str = "",
    work_item_id: str = "",
    name: str = "",
    fields: Optional[dict] = None,
    comment: str = "",
    status: str = "",
    page_size: int = 20,
) -> str:
    try:
        pk = _project_key(project_key)

        # ── 列出项目 ──────────────────────────────────────────
        if action == "list_projects":
            data = await _request("POST", "/project/list", {"page_size": 50})
            return json.dumps(data, ensure_ascii=False, indent=2)

        # ── 查询工作项列表 ────────────────────────────────────
        elif action == "list_work_items":
            if not pk:
                return "缺少 project_key 参数（或未配置 FEISHU_PROJECT_KEY）"
            body: dict = {"page_size": page_size}
            if work_item_type_key:
                body["work_item_type_keys"] = [work_item_type_key]
            if status:
                body["statuses"] = [status]
            data = await _request("POST", f"/{pk}/work_item/filter", body)
            return json.dumps(data, ensure_ascii=False, indent=2)

        # ── 获取工作项详情 ────────────────────────────────────
        elif action == "get_work_item":
            if not pk or not work_item_id:
                return "缺少 project_key 或 work_item_id 参数"
            if not work_item_type_key:
                return "缺少 work_item_type_key 参数"
            data = await _request("GET", f"/{pk}/work_item/{work_item_type_key}/{work_item_id}")
            return json.dumps(data, ensure_ascii=False, indent=2)

        # ── 创建工作项 ────────────────────────────────────────
        elif action == "create_work_item":
            if not pk or not work_item_type_key or not name:
                return "缺少 project_key、work_item_type_key 或 name 参数"
            body = {"work_item_type_key": work_item_type_key, "name": name}
            if fields:
                body["fields"] = [{"field_key": k, "field_value": v} for k, v in fields.items()]
            data = await _request("POST", f"/{pk}/work_item/create", body)
            return json.dumps(data, ensure_ascii=False, indent=2)

        # ── 更新工作项 ────────────────────────────────────────
        elif action == "update_work_item":
            if not pk or not work_item_type_key or not work_item_id:
                return "缺少 project_key、work_item_type_key 或 work_item_id 参数"
            if not fields:
                return "缺少 fields 参数"
            body = {
                "fields": [{"field_key": k, "field_value": v} for k, v in fields.items()]
            }
            data = await _request("POST", f"/{pk}/work_item/{work_item_type_key}/{work_item_id}/update", body)
            return json.dumps(data, ensure_ascii=False, indent=2)

        # ── 查询字段定义 ──────────────────────────────────────
        elif action == "list_fields":
            if not pk or not work_item_type_key:
                return "缺少 project_key 或 work_item_type_key 参数"
            data = await _request("GET", f"/{pk}/work_item_type/{work_item_type_key}/fields")
            return json.dumps(data, ensure_ascii=False, indent=2)

        # ── 查询项目成员 ──────────────────────────────────────
        elif action == "list_members":
            if not pk:
                return "缺少 project_key 参数"
            data = await _request("POST", f"/{pk}/member/list", {"page_size": 100})
            return json.dumps(data, ensure_ascii=False, indent=2)

        # ── 添加评论 ──────────────────────────────────────────
        elif action == "add_comment":
            if not pk or not work_item_type_key or not work_item_id or not comment:
                return "缺少 project_key、work_item_type_key、work_item_id 或 comment 参数"
            body = {"content": comment}
            data = await _request("POST", f"/{pk}/work_item/{work_item_type_key}/{work_item_id}/comment/create", body)
            return json.dumps(data, ensure_ascii=False, indent=2)

        else:
            return f"未知操作: {action}"

    except RuntimeError as e:
        return f"执行失败: {e}"
    except Exception as e:
        logging.exception("feishu_project skill 异常")
        return f"执行异常: {e}"
