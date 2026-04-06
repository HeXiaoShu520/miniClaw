# MiniClaw飞书 AI 机器人

飞书AI机器人，支持 **Anthropic Claude** 和 **OpenAI** 双 provider，基于 function calling 的技能路由架构。

## 功能特性

- 飞书 WebSocket 实时消息监听
- 双 AI Provider 支持（Anthropic / OpenAI，`.env` 一键切换）
- Agent 技能路由（基于 function calling 自动分发）
- 流式 / 非流式回复（可配置）
- 话题回复支持（可配置）
- 图片识别（下载飞书图片 → AI 视觉理解）
- Mermaid 自动链接（回复含 mermaid 代码块时，自动追加 mermaid.ai 在线可视化编辑链接）
- 飞书云文档提取（知识库 / docx / doc）
- HTTP API 接口（MCP Server）（已移除）
- 多轮对话上下文管理（本地持久化）
- 消息去重（持久化 seen_ids）
- 定时清理过期数据

## 技术栈

- **Anthropic SDK** / **OpenAI SDK** - AI 对话
- **FastAPI** - HTTP API 服务
- **WebSocket** - 飞书实时消息
- **Pydantic** - 配置与数据验证

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置

创建 `.env` 文件：

```env
# 日志级别
LOG_LEVEL=debug

# 是否使用话题回复
USE_TOPIC_REPLY=false

# 是否使用流式回复
USE_STREAM=false

# 飞书配置
FEISHU_APP_ID=cli_xxxxxxxxxxxxxx
FEISHU_APP_SECRET=xxxxxxxxxxxxxxxx

# AI 提供商（anthropic 或 openai）
AI_PROVIDER=anthropic

# Claude 配置（AI_PROVIDER=anthropic 时使用）
CLAUDE_API_KEY=sk-ant-xxxxxxxxxx
CLAUDE_MODEL=claude-sonnet-4-6
CLAUDE_BASE_URL=                   # 可选，自定义 API 地址

# OpenAI 配置（AI_PROVIDER=openai 时使用）
OPENAI_API_KEY=sk-xxxxxxxxxx
OPENAI_MODEL=gpt-4o
OPENAI_BASE_URL=                   # 可选，兼容 API 地址

# 系统提示词（可选）
SYSTEM_PROMPT=你是一个聪明、高效的 AI 助手。请直接回答用户的问题，不要说废话。

# 对话上下文轮数
MAX_HISTORY_TURNS=10
```

### 3. 运行

```bash
python main.py
```

## 项目结构

```
python-version/
├── main.py                  # 主程序入口
├── config.py                # 配置管理（.env / config.toml）
├── ai_client.py             # AI 客户端抽象基类
├── claude_client.py         # Anthropic Claude 实现
├── openai_client.py         # OpenAI 实现
├── link_service.py          # 核心业务逻辑
├── feishu/
│   ├── feishu_api.py        # 飞书 API 客户端
│   ├── websocket.py         # WebSocket 监听（含消息去重）
│   ├── protobuf.py          # 飞书 WS protobuf 协议解析
│   └── doc_client.py        # 飞书云文档内容提取
├── store/
│   └── resource_store.py    # 资源文件存储（SHA256 去重）
└── agent/
    ├── feishu_chat.py       # 主路由 Agent（function calling 分发）
    └── skill/
        ├── doc_reader.py    # 技能：飞书文档解读
        ├── feishu_mermaid.py  # 技能：图片转 Mermaid
        └── tts_reply.py     # 技能：文字转语音 (腾讯云 TTS)
```

## 配置说明

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `AI_PROVIDER` | AI 提供商 (`anthropic` / `openai`) | `anthropic` |
| `USE_STREAM` | 是否使用流式回复 | `true` |
| `USE_TOPIC_REPLY` | 是否使用话题回复 | `true` |
| `MAX_HISTORY_TURNS` | 对话上下文轮数 | `10` |
| `LOG_LEVEL` | 日志级别 | `info` |
| `FEISHU_APP_ID` | 飞书应用 ID | - |
| `FEISHU_APP_SECRET` | 飞书应用密钥 | - |
| `CLAUDE_API_KEY` | Claude API Key | - |
| `CLAUDE_MODEL` | Claude 模型 | `claude-sonnet-4-6` |
| `CLAUDE_BASE_URL` | Claude 自定义地址 | - |
| `OPENAI_API_KEY` | OpenAI API Key | - |
| `OPENAI_MODEL` | OpenAI 模型 | `gpt-4o` |
| `OPENAI_BASE_URL` | OpenAI 兼容地址 | - |

## 技能扩展

在 `agent/skill/` 下新建 Python 文件即可添加技能：

```python
"""示例技能"""
ENABLED = True  # 设为 False 可禁用

TOOL_DEF = {
    "name": "my_skill",
    "description": "技能描述",
    "input_schema": {
        "type": "object",
        "properties": {
            "param": {"type": "string", "description": "参数说明"}
        },
        "required": ["param"]
    }
}

async def execute(param: str) -> str:
    return "技能执行结果"
```

启动时终端会显示技能加载状态：
```
==================== 技能加载 ====================
  [✓] read_feishu_doc
  [✓] read_image
==================================================
```

## 数据目录

```
~/.acp-link/
├── sessions.json        # 会话映射
├── history.json         # 多轮对话历史
├── data/
│   ├── seen_ids.json    # 消息去重记录
│   └── ...              # 资源文件
├── logs/                # 日志文件
└── temp/                # 临时文件
```

## License

MIT
