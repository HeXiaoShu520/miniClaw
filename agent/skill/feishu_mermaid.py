"""图片转 Mermaid 技能"""
import base64
import json
import re
import zlib

ENABLED = False

TOOL_DEF = {
    "name": "image_to_mermaid",
    "description": "当用户要求把图片转换/识别成 Mermaid 图表、流程图、时序图等代码时，必须调用此工具处理，而不是直接回复。无需提供任何参数，直接调用即可。",
    "input_schema": {
        "type": "object",
        "properties": {
            "message_id": {"type": "string", "description": "飞书消息 ID"},
            "image_key": {"type": "string", "description": "图片 key"}
        },
        "required": []
    }
}

PROMPT = """请分析上传的图片内容，自动选择最合适的 Mermaid 图表类型（如 flowchart、sequenceDiagram、classDiagram、erDiagram、gantt、mindmap 等），并根据图片结构生成对应的 Mermaid 代码。

要求：
1. **自动选择最合适的图表类型**：根据图片的布局、节点关系和图表特征，自动选择 Mermaid 图表类型。常见的类型包括但不限于 `flowchart`（流程图）、`sequenceDiagram`（时序图）、`classDiagram`（类图）、`erDiagram`（实体关系图）、`gantt`（甘特图）、`mindmap`（思维导图）。如果不确定，优先选择 `flowchart`，然后根据结构进一步推断。
2. **准确还原节点与关系**：完整、准确地还原图片中的所有节点、连接关系、决策分支和循环结构。确保每个节点都正确表示，箭头和连接关系的方向保持一致。对图片中呈现的逻辑（如条件判断、重复流程等）进行合理推断，并还原为 Mermaid 代码中的条件分支或循环结构。
3. **确保不遗漏任何信息**：对于图中的每个元素，确保 Mermaid 代码中都有相应的表达，且信息完整无缺。如果图中存在多条路径、循环或嵌套，生成的代码应涵盖所有路径，并且保证逻辑上的一致性。
4. **Mermaid 代码生成规范**：生成的 Mermaid 代码应符合 Mermaid 语法规范，使用合适的图表布局（如 `flowchart TD`、`sequenceDiagram` 等），并确保代码简洁、结构清晰。代码应该尽量优化，避免冗余或复杂的节点定义，使其更易于理解和维护。
5. **特殊结构的处理**：对于复杂的结构，自动识别并正确表达，如条件判断（if/else）、循环（loop/while）、并发等。使用合适的 Mermaid 语法表达这些特殊逻辑，确保图表呈现完整的流程逻辑。
6. **只输出 Mermaid 代码**：请仅输出 Mermaid 代码，不要附加任何解释或附加信息。代码应直接可用，能够准确渲染出图表。

"""


def _mermaid_url(code: str) -> str:
    state = json.dumps({
        "code": code,
        "mermaid": {"theme": "default"},
        "autoSync": True,
        "updateDiagram": True,
    })
    compressed = zlib.compress(state.encode("utf-8"), level=9)
    raw_deflate = compressed[2:-4]
    b64 = base64.urlsafe_b64encode(raw_deflate).decode("ascii")
    return f"https://mermaid.ai/play#pako:{b64}"


async def execute(message_id: str, image_key: str, feishu_client, claude_client) -> str:
    data = await feishu_client.download_resource(message_id, image_key, "image")

    if data.startswith(b'\x89PNG'):
        mime = "image/png"
    elif data.startswith(b'\xFF\xD8\xFF'):
        mime = "image/jpeg"
    else:
        mime = "image/png"

    b64 = base64.b64encode(data).decode()
    messages = [{
        "role": "user",
        "content": [
            {"type": "image", "source": {"type": "base64", "media_type": mime, "data": b64}},
            {"type": "text", "text": PROMPT}
        ]
    }]
    code = await claude_client.call(messages)
    code = re.sub(r"^```(?:mermaid)?\n?", "", code, flags=re.IGNORECASE).rstrip("`").strip()
    url = _mermaid_url(code)
    return f"```mermaid\n{code}\n```\n\n在线可视化编辑：{url}"
