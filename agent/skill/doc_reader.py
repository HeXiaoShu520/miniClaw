"""文档解读技能：提取飞书文档内容"""
import re

from feishu.doc_client import FeishuDocClient

ENABLED = True

# Function calling 工具定义
TOOL_DEF = {
    "name": "read_feishu_doc",
    "description": "读取飞书文档/知识库链接的内容，返回文档文字内容",
    "input_schema": {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "飞书文档链接"}
        },
        "required": ["url"]
    }
}


async def execute(url: str, feishu_client) -> str:
    """执行文档读取"""
    token = await feishu_client.get_access_token()
    doc_client = FeishuDocClient(token)

    try:
        wiki_match = re.search(r'feishu\.cn/wiki/([a-zA-Z0-9]+)', url)
        if wiki_match:
            content = await doc_client.extract_wiki(wiki_match.group(1))
            return f"[飞书知识库文档]\n{content}" if content else "文档内容为空"

        docx_match = re.search(r'feishu\.cn/docx/([a-zA-Z0-9]+)', url)
        if docx_match:
            content = await doc_client.extract_docx(docx_match.group(1))
            return f"[飞书文档]\n{content}" if content else "文档内容为空"

        doc_match = re.search(r'feishu\.cn/docs/([a-zA-Z0-9]+)', url)
        if doc_match:
            content = await doc_client.extract_doc(doc_match.group(1))
            return f"[飞书文档]\n{content}" if content else "文档内容为空"

        return f"无法识别的飞书文档链接: {url}"
    finally:
        await doc_client.close()
