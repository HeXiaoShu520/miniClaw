# miniClaw / DyberPet 桌面 AI 宠物

本项目当前定位：**独立桌面 AI 宠物 + 可选外部事件接口 + 可选飞书插件后端**。

DyberPet 不是飞书的附属通知窗口。它首先是一个可以独立运行的桌面宠物软件：能陪聊、提醒、展示事件气泡、根据事件做动作；miniClaw / 飞书 / GitHub / 本地脚本等都只是它的外部事件源。

## 产品定位

一句话：

> 一个住在桌面上的 AI 宠物外设，能陪你聊天、提醒你做事、接收外部软件事件，并用动作和气泡表现当前状态。

核心方向：

- **独立可用**：不接飞书、不启动 miniClaw，也能作为桌面 AI 宠物使用。
- **事件驱动**：外部软件通过统一协议把消息、提醒、动作事件推给宠物。
- **人格化交互**：大模型配置 + 角色设定，让不同宠物拥有不同性格。
- **轻量工作流**：气泡按钮可以把用户选择回传给外部服务，例如发送回复、稍后提醒、忽略。
- **插件化扩展**：飞书只是第一个插件方向，后续可接 GitHub、日历、邮件、CI、本地脚本等。

## 当前已实现能力

### DyberPet 桌面客户端

- 右键菜单新增 **Chat / 聊天**。
- 新增独立 AI 聊天窗口。
- 新增 **大模型设置** 页面：API 地址、API Key、模型名、最大 Token、System Prompt。
- 支持 OpenAI 兼容接口，适配 OpenAI / DeepSeek / 通义 / Kimi / 本地 ollama 等。
- 右键菜单新增 **Fetch Back / 找回宠物**，用于把跑到屏幕外的宠物拉回主屏。
- 新增智能事件气泡：标题、发送人、摘要、建议、最多 3 个操作按钮。
- 新增通用外部事件入口：DyberPet 可监听 `ws://localhost:18888/ws/pet`。
- 气泡按钮点击后可选回调 `POST http://localhost:18888/actions/execute`。
- 启动入口已修正工作目录，支持从项目根目录直接运行 `DyberPet-main/run_DyberPet.py`。

### miniClaw 后端

- 当前仍保留原飞书 AI 机器人能力。
- 后续作为 DyberPet 的可选事件源和飞书插件后端。
- 负责连接飞书、分析消息、生成建议、执行飞书动作。

## 总体架构

```text
┌──────────────────────────┐
│        外部事件源          │
│ 飞书 / GitHub / 日历 / CI │
│ 本地脚本 / 其他应用        │
└─────────────┬────────────┘
              │ 通用事件协议
              │ WebSocket / HTTP
              ▼
┌──────────────────────────┐
│          miniClaw         │  可选
│ 事件接收 / AI 分析 / 动作执行 │
│ 飞书插件 / 未来插件网关      │
└─────────────┬────────────┘
              │ ws://localhost:18888/ws/pet
              ▼
┌──────────────────────────┐
│          DyberPet         │
│ 桌面宠物 / 气泡 / 动作 / AI聊天 │
│ 独立运行，不依赖 miniClaw     │
└──────────────────────────┘
```

分层：

1. **宠物本体层**
   - 动画
   - 气泡
   - 通知
   - 右键菜单
   - 找回宠物
   - 设置面板

2. **AI 能力层**
   - 大模型配置
   - 独立聊天窗口
   - 角色设定 / System Prompt
   - 后续：剪贴板总结、文本改写、日报生成、本地复盘

3. **事件接口层**
   - WebSocket 接收外部事件
   - 智能气泡展示
   - 宠物动作触发
   - 按钮动作回调

4. **插件后端层**
   - miniClaw
   - 飞书插件
   - 未来 GitHub / 日历 / 邮件 / CI 插件

## 技术栈

### DyberPet 客户端

- Python
- PySide6
- qfluentwidgets
- WebSocket client
- OpenAI 兼容 Chat Completions API
- 本地 JSON 配置与存储

### miniClaw 后端

- Python
- FastAPI
- WebSocket
- Anthropic SDK / OpenAI SDK
- 飞书 WebSocket 事件监听
- Function Calling 技能路由
- 本地历史与资源存储

## 目录结构

```text
miniClaw/
├── README.md                         # 当前总览与路线
├── FEISHU_PET_DESIGN.md              # 飞书插件方向设计文档
├── main.py                           # miniClaw 后端入口
├── link_service.py                   # miniClaw 核心消息处理
├── config.py                         # 后端配置
├── agent/                            # Agent 技能系统
├── feishu/                           # 飞书 API / WS / 文档能力
├── store/                            # 本地资源存储
└── DyberPet-main/
    ├── run_DyberPet.py               # DyberPet 启动入口
    ├── PET_EVENT_PROTOCOL.md         # 通用宠物事件协议
    └── DyberPet/
        ├── DyberPet.py               # 宠物主窗口与右键菜单
        ├── Notification.py           # 通知、普通气泡、智能气泡
        ├── miniclaw_client.py        # 外部事件 WebSocket 客户端
        ├── chat_window.py            # 独立 AI 聊天窗口
        ├── llm_client.py             # OpenAI 兼容 LLM 客户端
        └── DyberSettings/
            ├── DyberControlPanel.py  # 设置面板主窗口
            └── LLMSettingUI.py       # 大模型设置页
```

## miniPet 通用卡片协议

miniClaw 通过 `pet_gateway.py` 暴露 miniPet 网关：

```text
ws://127.0.0.1:18889/ws/minipet
```

设置页点击“检测 MiniPet 协议”时，miniPet 会先发送 `session.probe`，miniClaw 回 `session.probe.result`，用于确认后端支持 MiniPet 协议，但不进入正式会话：

```json
{
  "type": "session.probe.result",
  "source": "miniclaw",
  "payload": {
    "ok": true,
    "server": {"name": "miniClaw", "kind": "desktop-agent"},
    "protocol": "minipet.v1",
    "accepted_surface_kinds": ["card"]
  }
}
```

miniPet 正式连接后发送 `session.hello`，miniClaw 回 `session.ready`，并声明只接受通用卡片：

```json
{
  "type": "session.ready",
  "source": "miniclaw",
  "payload": {
    "server": {"name": "miniClaw", "kind": "desktop-agent"},
    "protocol": "minipet.v1",
    "accepted_surface_kinds": ["card"]
  }
}
```

miniPet 发给 miniClaw 的用户输入固定为 `user.input`：

```json
{
  "type": "user.input",
  "source": "minipet",
  "payload": {
    "text": "帮我总结今天需要处理的事",
    "preview": "帮我总结今天需要处理的事",
    "mode": "text",
    "surface": "pet_popup"
  }
}
```

带图片时，miniPet 会把图片作为 base64 附件放在 `attachments`。miniClaw 会自动解码并传给当前大模型：

```json
{
  "type": "user.input",
  "source": "minipet",
  "payload": {
    "text": "帮我看看这张图",
    "preview": "帮我看看这张图\n[图片] × 1",
    "mode": "text",
    "surface": "pet_popup",
    "attachments": [
      {
        "type": "image",
        "name": "image_1.png",
        "mime_type": "image/png",
        "encoding": "base64",
        "data": "iVBORw0KGgo...",
        "source": "message"
      }
    ]
  }
}
```

miniClaw 返回内容统一使用 `surface.show` / `surface.update` / `surface.close`，`kind` 固定为 `card`。普通文字、流式回复、选择、输入和按钮都放进同一种卡片 payload：

```text
Card
├─ elements：展示内容，普通文本、Markdown、分隔线等
├─ controls：输入/选择控件，文本框、单选、多选、自定义输入等
└─ actions：按钮，提交、取消、确认、复制、重试等
```

流式回复示例：

```json
{
  "type": "surface.show",
  "source": "miniclaw",
  "payload": {
    "surface_id": "desktop-reply-1",
    "kind": "card",
    "title": "miniClaw",
    "content": "正在生成回复...",
    "status": "streaming",
    "timeout_ms": 0
  }
}
```

```json
{
  "type": "surface.update",
  "source": "miniclaw",
  "payload": {
    "surface_id": "desktop-reply-1",
    "kind": "card",
    "content": "这是最终回复。",
    "status": "done",
    "done": true,
    "timeout_ms": 10000
  }
}
```

带选择、自定义输入和按钮的卡片示例：

```json
{
  "type": "surface.show",
  "source": "miniclaw",
  "payload": {
    "surface_id": "plan-choice-1",
    "kind": "card",
    "title": "请选择方案",
    "elements": [
      {"type": "markdown", "content": "请选择一种实现方式，也可以输入其他方案。"}
    ],
    "controls": [
      {
        "id": "plan",
        "type": "radio_group",
        "label": "方案",
        "options": [
          {"id": "simple", "label": "简单方案"},
          {"id": "full", "label": "完整方案"}
        ],
        "allow_custom": true
      }
    ],
    "actions": [
      {"id": "cancel", "label": "取消", "style": "quiet"},
      {"id": "submit", "label": "提交", "style": "primary"}
    ]
  }
}
```

用户点击按钮后，miniPet 回传 `user.action`；如果卡片包含 `controls`，控件值会放在 `payload.values`：

```json
{
  "type": "user.action",
  "source": "minipet",
  "payload": {
    "surface_id": "plan-choice-1",
    "action_id": "submit",
    "values": {"plan": "simple"},
    "action": {"id": "submit", "label": "提交", "style": "primary"},
    "metadata": {}
  }
}
```

## 预期特性路线

### v0.1 独立宠物基础版

目标：不依赖飞书，先让 DyberPet 作为独立软件成立。

- [x] 独立聊天窗口
- [x] 大模型设置
- [x] 找回宠物
- [x] 通用事件 WebSocket 客户端
- [x] 智能气泡
- [x] 气泡按钮回调
- [ ] 本地提醒功能
- [ ] 今日待办功能
- [ ] 本地复盘窗口
- [ ] 托盘菜单显示连接状态

### v0.2 桌面 AI 助手版

目标：让宠物具备常用桌面 AI 工具能力。

- [ ] 总结剪贴板
- [ ] 改写剪贴板文本
- [ ] 翻译选中文本 / 剪贴板
- [ ] 解释报错
- [ ] 生成日报草稿
- [ ] 快速记笔记
- [ ] 角色模板：萌妹 / 温柔秘书 / 毒舌监督 / 严肃 PM
- [ ] 按角色保存不同 System Prompt

### v0.3 事件外设版

目标：让任何软件都能把状态推给宠物。

- [ ] miniClaw mock 推送工具
- [ ] HTTP 本地事件接收端点
- [ ] 本地脚本 CLI：`petctl send ...`
- [ ] 事件历史记录
- [ ] 事件过滤规则
- [ ] 优先级策略：普通 / 高优先级 / 紧急
- [ ] 状态映射：空闲 / 忙碌 / 焦虑 / 开心 / 警报

### v0.4 飞书插件版

目标：把飞书作为一个插件接进来，而不是强绑定 DyberPet。

- [ ] 飞书消息转通用宠物事件
- [ ] AI 生成摘要和建议回复
- [ ] 点击气泡按钮发送飞书回复
- [ ] 自动提取待办和承诺
- [ ] 晚间飞书复盘
- [ ] 飞书任务同步
- [ ] 会议前提醒与会议后收尾

### v0.5 插件生态版

目标：让宠物成为桌面事件中枢。

- [ ] GitHub PR / CI 插件
- [ ] 日历提醒插件
- [ ] 邮件提醒插件
- [ ] 本地命令完成提醒
- [ ] 自定义插件配置
- [ ] 插件市场或插件目录规范

## 技术路线

### 近期优先级

1. **稳定 DyberPet 独立能力**
   - 聊天窗口可用
   - LLM 配置可用
   - 本地提醒和待办可用
   - 不启动 miniClaw 也能正常运行

2. **补齐事件输入闭环**
   - WebSocket 推事件
   - 智能气泡显示
   - 点击按钮回调
   - 提供 mock 推送脚本

3. **再接 miniClaw / 飞书**
   - miniClaw 负责把飞书消息转成通用事件
   - DyberPet 不直接理解飞书，只理解宠物事件协议
   - 飞书能力作为插件实现

### 设计原则

- **DyberPet 不直接绑定飞书业务字段**：飞书字段在 miniClaw 内转换成通用事件。
- **外部服务不可用时 DyberPet 仍可运行**：按钮回调失败只静默忽略或提示，不阻塞宠物。
- **原宠物功能不被破坏**：智能气泡与原普通气泡分离实现。
- **优先做闭环，不先做复杂 Agent**：先做到“事件进来 → 宠物表现 → 用户操作 → 外部回调”。
- **插件化扩展**：新软件接入时只需要生产通用事件。

## 快速开始

### 启动 DyberPet

```bash
python DyberPet-main/run_DyberPet.py
```

如果已运行一个实例，程序会提示：

```text
Another instance is already running, quitting.
```

### 配置大模型

打开 DyberPet 右键菜单：

```text
System → 大模型
```

填写：

- API 地址，例如 `https://api.openai.com/v1`
- API Key
- 模型名，例如 `gpt-4o-mini`、`deepseek-chat`、`qwen-plus`
- 最大 Token
- 宠物 System Prompt

### 启动 miniClaw 后端

```bash
python main.py
```

miniClaw 当前仍主要承担飞书 AI 机器人能力。后续会逐步改造成 DyberPet 的可选事件源和插件后端。

## miniClaw 原有飞书 AI 能力

当前保留：

- 飞书 WebSocket 实时消息监听
- Anthropic / OpenAI 双 provider
- Function Calling 技能路由
- 流式 / 非流式回复
- 话题回复
- 图片识别
- 飞书云文档提取
- Mermaid 自动链接
- 多轮对话上下文管理
- 消息去重
- 定时清理过期数据

原飞书插件设计见：[FEISHU_PET_DESIGN.md](FEISHU_PET_DESIGN.md)

## 下一步开发建议

新开终端后建议先做这几个：

1. 新增一个 `pet_event_mock.py`，本地模拟向 DyberPet 推送事件。
2. 做本地提醒窗口：内容、时间、重复、到点气泡。
3. 做今日待办 JSON 存储和简单 UI。
4. 给智能气泡按钮加本地动作：稍后提醒、复制建议、打开聊天。
5. 再把 miniClaw 飞书消息转换成通用事件协议。

## License

MIT
