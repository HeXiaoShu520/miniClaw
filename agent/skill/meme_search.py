"""表情包搜索技能：搜索图片、下载并发送到当前飞书会话。"""
import json
import logging
import os
import re
from urllib.parse import urlsplit

import aiohttp

from agent.skill import doubao_search

ENABLED = True

# 进程内去重：同一个关键词连续搜索时，优先发送没发过的图片。
# 豆包图片 URL 每次会换签名参数，所以只记录路径里的图片对象 ID。
_sent_image_ids_by_query: dict[str, set[str]] = {}
_search_round_by_query: dict[str, int] = {}

TOOL_DEF = {
    "name": "meme_search",
    "description": (
        "搜索表情包/斗图素材，并把找到的图片下载后上传发送到当前飞书会话。"
        "当用户说帮我搜索某个表情包、找个表情包、来个表情包、斗图、发张图时优先使用此工具，"
        "不要只返回图片链接。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "要搜索的表情包关键词，例如：猫猫表情包、无语表情包、谢谢老板表情包"
            },
            "index": {
                "type": "integer",
                "description": "发送第几张结果，从 1 开始，默认 1"
            },
            "count": {
                "type": "integer",
                "description": "搜索候选数量，最多 5，默认 5"
            },
            "send_count": {
                "type": "integer",
                "description": "要发送的表情包张数，最多 5，默认 1。用户说多来几张/发3张/一组表情包时使用"
            },
            "extra_keywords": {
                "type": "array",
                "items": {"type": "string"},
                "description": "附加搜索关键词。用于主动拉开搜索结果差异，例如 ['捂鼻', '散味', '打工']。用户要求换一批/别重复/更具体风格时由大模型填写"
            },
            "image_shape": {
                "type": "string",
                "enum": ["横长方形", "竖长方形", "方形"],
                "description": "图片形状，表情包默认方形"
            }
        },
        "required": ["query"]
    }
}


def _image_id(url: str) -> str:
    """提取稳定图片 ID，忽略每次变化的签名参数。"""
    path = urlsplit(url).path
    name = path.rsplit("/", 1)[-1]
    match = re.match(r"([^~?]+)", name)
    return match.group(1) if match else url


def _query_variants(query: str, round_no: int, extra_keywords: list[str] | None = None) -> list[str]:
    base = query.strip()
    suffix_groups = [
        ["动图", "gif", "搞笑", "可爱", "无字", "高清"],
        ["捂鼻", "散味", "跳舞", "打工", "上班", "工资"],
        ["微信", "透明底", "热门", "原图", "高清", "合集"],
    ]
    suffixes = [k.strip() for k in (extra_keywords or []) if k and k.strip()]
    if not suffixes:
        suffixes = suffix_groups[round_no % len(suffix_groups)]

    variants = [base]
    for suffix in suffixes[:8]:
        if suffix not in base:
            variants.append(f"{base} {suffix}")
    return variants


def _dedupe_items(items: list[dict]) -> list[dict]:
    seen = set()
    result = []
    for item in items:
        image = item.get("image") or {}
        url = image.get("Url") or image.get("url") or ""
        if not url:
            continue
        key = _image_id(url)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _sort_items(items: list[dict]) -> list[dict]:
    def score(item: dict):
        image = item.get("image") or {}
        watermark = 1 if str(image.get("Watermark", "")) == "0" else 0
        clear = 1 if image.get("BlurDes") == "清晰" else 0
        width = image.get("Width") or 0
        height = image.get("Height") or 0
        size_ok = 1 if 160 <= width <= 800 and 160 <= height <= 800 else 0
        return (watermark, clear, size_ok, item.get("rank_score") or 0)
    return sorted(items, key=score, reverse=True)


def _search_error_text(result: str) -> bool:
    return result.startswith("未配置") or result.startswith("缺少") or result.startswith("执行异常")


def _detect_image_type(data: bytes, content_type: str = "") -> tuple[str, str]:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image.png", "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image.jpg", "image/jpeg"
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return "image.gif", "image/gif"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image.webp", "image/webp"
    if content_type.startswith("image/"):
        ext = content_type.split("/", 1)[1].split(";", 1)[0] or "jpg"
        return f"image.{ext}", content_type.split(";", 1)[0]
    return "image.jpg", "image/jpeg"


async def _download_image(url: str) -> tuple[bytes, str, str]:
    timeout = aiohttp.ClientTimeout(total=30)
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
    }
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url, headers=headers) as resp:
            if resp.status >= 400:
                raise RuntimeError(f"下载图片失败，HTTP {resp.status}")
            data = await resp.read()
            if not data:
                raise RuntimeError("下载图片失败：内容为空")
            content_type = resp.headers.get("Content-Type", "")
    filename, mime = _detect_image_type(data, content_type)
    return data, filename, mime


async def execute(
    query: str,
    chat_id: str,
    feishu_client,
    index: int = 1,
    count: int = 5,
    send_count: int = 1,
    extra_keywords: list[str] | None = None,
    image_shape: str = "方形",
) -> str:
    try:
        if not chat_id:
            return "缺少 chat_id，无法发送到飞书会话"
        if not os.environ.get("DOUBAO_SEARCH_API_KEY", ""):
            return "未配置 DOUBAO_SEARCH_API_KEY，无法搜索表情包"

        query = (query or "").strip()
        if not query:
            return "缺少 query 参数"
        if "表情" not in query and "斗图" not in query:
            query = f"{query} 表情包"

        send_count = max(1, min(int(send_count or 1), 5))
        search_count = max(send_count, max(1, min(int(count or 5), 5)))

        round_no = _search_round_by_query.get(query, 0)
        _search_round_by_query[query] = round_no + 1

        all_results = []
        search_errors = []
        for variant in _query_variants(query, round_no, extra_keywords):
            if len(all_results) >= send_count * 3:
                break
            search_result = await doubao_search.execute(
                query=variant,
                search_type="image",
                count=search_count,
                image_shapes=[image_shape] if image_shape else ["方形"],
                raw=False,
            )
            if _search_error_text(search_result):
                search_errors.append(search_result)
                continue
            data = json.loads(search_result)
            all_results.extend(data.get("image_results") or [])

        image_results = _sort_items(_dedupe_items(all_results))
        if not image_results:
            return f"没搜到表情包：{query}" if not search_errors else f"搜索表情包失败：{search_errors[-1]}"

        start = max(0, int(index or 1) - 1)
        rotated_results = image_results[start:] + image_results[:start]
        sent_image_ids = _sent_image_ids_by_query.setdefault(query, set())
        fresh_results = [
            item for item in rotated_results
            if _image_id((item.get("image") or {}).get("Url") or (item.get("image") or {}).get("url") or "") not in sent_image_ids
        ]
        candidates = fresh_results + [item for item in rotated_results if item not in fresh_results]

        sent = []
        errors = []
        used_image_ids = []
        for item in candidates:
            if len(sent) >= send_count:
                break
            image = item.get("image") or {}
            url = image.get("Url") or image.get("url")
            if not url:
                continue
            try:
                image_data, filename, mime = await _download_image(url)
                msg_id = await feishu_client.send_image(chat_id, image_data, filename=filename, content_type=mime)
                sent.append({
                    "title": item.get("title") or query,
                    "size": f"{image.get('Width', '?')}x{image.get('Height', '?')}",
                    "message_id": msg_id,
                })
                used_image_ids.append(_image_id(url))
            except Exception as e:
                errors.append(str(e))
                logging.warning(f"发送表情包候选失败: {e}")

        if sent:
            sent_image_ids.update(used_image_ids)
            if len(sent_image_ids) > 100:
                _sent_image_ids_by_query[query] = set(list(sent_image_ids)[-100:])
            detail = "；".join(f"{item['title']}（{item['size']}）" for item in sent)
            suffix = f"，失败 {len(errors)} 张" if errors else ""
            return f"已发送 {len(sent)} 张表情包：{detail}{suffix}"

        return f"搜到了表情包，但下载或上传失败：{'; '.join(errors[-3:])}"

    except json.JSONDecodeError:
        return f"搜索表情包失败：{search_result}"
    except Exception as e:
        logging.exception("meme_search skill 异常")
        return f"执行异常: {e}"
