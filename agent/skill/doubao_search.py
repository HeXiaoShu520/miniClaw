"""
豆包搜索 Custom 版技能：调用火山引擎联网搜索 / 融合信息搜索接口。

需在 .env 中配置：
  DOUBAO_SEARCH_API_KEY=xxx

当前使用 APIKey 接入：
  POST https://open.feedcoopapi.com/search_api/web_search
  Authorization: Bearer <API_KEY>

支持：
  - web 搜索：返回网页结果，可按时间、站点、权威度、行业等过滤
  - image 搜索：返回图片结果，可按尺寸、形状过滤
"""
import json
import logging
import os
from typing import Optional

ENABLED = True

TOOL_DEF = {
    "name": "doubao_search",
    "description": (
        "调用豆包搜索 Custom 版（火山引擎联网搜索 / 融合信息搜索）获取 web 网页或 image 图片搜索结果。"
        "适合需要联网查询、按站点/时间/权威度过滤、获取网页摘要/正文或图片链接时使用。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索词，1~100 个字符，不支持多词搜索"
            },
            "search_type": {
                "type": "string",
                "enum": ["web", "image"],
                "description": "搜索类型：web 网页搜索；image 图片搜索，默认 web"
            },
            "count": {
                "type": "integer",
                "description": "返回结果条数。web 最多 50 条、默认 10 条；image 最多 5 条、默认 5 条"
            },
            "time_range": {
                "type": "string",
                "description": "web 搜索发文时间：OneDay、OneWeek、OneMonth、OneYear 或 YYYY-MM-DD..YYYY-MM-DD"
            },
            "need_content": {
                "type": "boolean",
                "description": "web 搜索：是否仅返回有正文的结果，默认 false"
            },
            "need_url": {
                "type": "boolean",
                "description": "web 搜索：是否仅返回有原文链接的结果，默认 false"
            },
            "sites": {
                "type": "string",
                "description": "web 搜索：限定站点范围，多个完整域名用 | 分隔，最多 20 个，如 aliyun.com|mp.qq.com"
            },
            "block_hosts": {
                "type": "string",
                "description": "web 搜索：屏蔽站点，多个完整域名用 | 分隔，最多 5 个"
            },
            "auth_info_level": {
                "type": "integer",
                "enum": [0, 1],
                "description": "web 搜索：0 不限制；1 仅非常权威内容，默认 0"
            },
            "query_rewrite": {
                "type": "boolean",
                "description": "是否开启 Query 改写，开启会增加耗时，默认 false"
            },
            "content_formats": {
                "type": "string",
                "enum": ["text", "markdown"],
                "description": "web 搜索正文格式：text 或 markdown，默认 text"
            },
            "industry": {
                "type": "string",
                "enum": ["finance", "game", "gov"],
                "description": "web 搜索行业类型：finance 金融、game 游戏、gov 政府/央媒/国家机构等"
            },
            "image_width_min": {
                "type": "integer",
                "description": "image 搜索：最小图片宽度"
            },
            "image_height_min": {
                "type": "integer",
                "description": "image 搜索：最小图片高度"
            },
            "image_width_max": {
                "type": "integer",
                "description": "image 搜索：最大图片宽度"
            },
            "image_height_max": {
                "type": "integer",
                "description": "image 搜索：最大图片高度"
            },
            "image_shapes": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": ["横长方形", "竖长方形", "方形"]
                },
                "description": "image 搜索：允许的图片形状"
            },
            "raw": {
                "type": "boolean",
                "description": "是否返回原始完整 JSON，默认 false。false 时会返回压缩后的搜索结果摘要"
            }
        },
        "required": ["query"]
    }
}

BASE_URL = "https://open.feedcoopapi.com/search_api/web_search"


def _trim_text(text: str, limit: int) -> str:
    if not text:
        return ""
    return text if len(text) <= limit else text[:limit].rstrip() + "..."


def _clean_empty(value):
    if isinstance(value, dict):
        return {k: _clean_empty(v) for k, v in value.items() if v not in (None, "", [], {})}
    return value


def _build_body(
    query: str,
    search_type: str,
    count: Optional[int],
    time_range: str,
    need_content: Optional[bool],
    need_url: Optional[bool],
    sites: str,
    block_hosts: str,
    auth_info_level: Optional[int],
    query_rewrite: Optional[bool],
    content_formats: str,
    industry: str,
    image_width_min: Optional[int],
    image_height_min: Optional[int],
    image_width_max: Optional[int],
    image_height_max: Optional[int],
    image_shapes: Optional[list[str]],
) -> dict:
    body: dict = {
        "Query": query,
        "SearchType": search_type,
    }

    if count is not None:
        max_count = 5 if search_type == "image" else 50
        body["Count"] = max(1, min(int(count), max_count))
    elif search_type == "image":
        body["Count"] = 5

    if query_rewrite is not None:
        body["QueryControl"] = {"QueryRewrite": query_rewrite}

    if search_type == "web":
        filter_body = {}
        if need_content is not None:
            filter_body["NeedContent"] = need_content
        if need_url is not None:
            filter_body["NeedUrl"] = need_url
        if sites:
            filter_body["Sites"] = sites
        if block_hosts:
            filter_body["BlockHosts"] = block_hosts
        if auth_info_level is not None:
            filter_body["AuthInfoLevel"] = auth_info_level
        if filter_body:
            body["Filter"] = filter_body
        if time_range:
            body["TimeRange"] = time_range
        if content_formats:
            body["ContentFormats"] = content_formats
        if industry:
            body["Industry"] = industry
    else:
        filter_body = {}
        if image_width_min is not None:
            filter_body["ImageWidthMin"] = image_width_min
        if image_height_min is not None:
            filter_body["ImageHeightMin"] = image_height_min
        if image_width_max is not None:
            filter_body["ImageWidthMax"] = image_width_max
        if image_height_max is not None:
            filter_body["ImageHeightMax"] = image_height_max
        if image_shapes:
            filter_body["ImageShapes"] = image_shapes
        if filter_body:
            body["Filter"] = filter_body

    return _clean_empty(body)


def _format_result(data: dict, search_type: str) -> str:
    metadata = data.get("ResponseMetadata") or {}
    error = metadata.get("Error")
    if error:
        return json.dumps({"error": error, "request_id": metadata.get("RequestId")}, ensure_ascii=False, indent=2)

    result = data.get("Result") or {}
    payload = {
        "result_count": result.get("ResultCount", 0),
        "time_cost_ms": result.get("TimeCost"),
        "log_id": result.get("LogId"),
        "search_context": result.get("SearchContext"),
    }

    if search_type == "image":
        payload["image_results"] = [
            {
                "sort_id": item.get("SortId"),
                "title": item.get("Title"),
                "site_name": item.get("SiteName"),
                "url": item.get("Url"),
                "publish_time": item.get("PublishTime"),
                "image": item.get("Image"),
                "rank_score": item.get("RankScore"),
            }
            for item in result.get("ImageResults") or []
        ]
    else:
        payload["web_results"] = [
            {
                "sort_id": item.get("SortId"),
                "title": item.get("Title"),
                "site_name": item.get("SiteName"),
                "url": item.get("Url"),
                "snippet": _trim_text(item.get("Snippet") or "", 300),
                "summary": _trim_text(item.get("Summary") or "", 1200),
                "content": _trim_text(item.get("Content") or "", 2000),
                "publish_time": item.get("PublishTime"),
                "rank_score": item.get("RankScore"),
                "auth_info_des": item.get("AuthInfoDes"),
                "auth_info_level": item.get("AuthInfoLevel"),
                "content_formats": item.get("ContentFormats"),
                "ruyi_info": item.get("RuyiInfo"),
            }
            for item in result.get("WebResults") or []
        ]
        if result.get("CardResults"):
            payload["card_results"] = result.get("CardResults")

    return json.dumps(_clean_empty(payload), ensure_ascii=False, indent=2)


async def execute(
    query: str,
    search_type: str = "web",
    count: Optional[int] = None,
    time_range: str = "",
    need_content: Optional[bool] = None,
    need_url: Optional[bool] = None,
    sites: str = "",
    block_hosts: str = "",
    auth_info_level: Optional[int] = None,
    query_rewrite: Optional[bool] = None,
    content_formats: str = "",
    industry: str = "",
    image_width_min: Optional[int] = None,
    image_height_min: Optional[int] = None,
    image_width_max: Optional[int] = None,
    image_height_max: Optional[int] = None,
    image_shapes: Optional[list[str]] = None,
    raw: bool = False,
) -> str:
    try:
        api_key = os.environ.get("DOUBAO_SEARCH_API_KEY", "")
        if not api_key:
            return "未配置 DOUBAO_SEARCH_API_KEY，无法调用豆包搜索 Custom 版"

        query = (query or "").strip()
        if not query:
            return "缺少 query 参数"
        if len(query) > 100:
            query = query[:100]

        search_type = search_type or "web"
        if search_type not in {"web", "image"}:
            return "search_type 仅支持 web 或 image"

        body = _build_body(
            query=query,
            search_type=search_type,
            count=count,
            time_range=time_range,
            need_content=need_content,
            need_url=need_url,
            sites=sites,
            block_hosts=block_hosts,
            auth_info_level=auth_info_level,
            query_rewrite=query_rewrite,
            content_formats=content_formats,
            industry=industry,
            image_width_min=image_width_min,
            image_height_min=image_height_min,
            image_width_max=image_width_max,
            image_height_max=image_height_max,
            image_shapes=image_shapes,
        )

        import aiohttp
        timeout = aiohttp.ClientTimeout(total=30)
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(BASE_URL, headers=headers, json=body) as resp:
                text = await resp.text()
                try:
                    data = json.loads(text)
                except json.JSONDecodeError:
                    return f"豆包搜索返回非 JSON 响应，HTTP {resp.status}: {_trim_text(text, 1000)}"

        if raw:
            return json.dumps(data, ensure_ascii=False, indent=2)
        return _format_result(data, search_type)

    except Exception as e:
        logging.exception("doubao_search skill 异常")
        return f"执行异常: {e}"
