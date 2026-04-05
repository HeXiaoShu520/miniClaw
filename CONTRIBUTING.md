# Contributing

欢迎提交 Issue 和 Pull Request。

## 开发流程

1. Fork 本仓库
2. 创建功能分支：`git checkout -b feature/your-feature`
3. 提交更改：`git commit -m 'feat: add some feature'`
4. 推送分支：`git push origin feature/your-feature`
5. 创建 Pull Request

## 添加技能

在 `agent/skill/` 下新建 Python 文件：

```python
ENABLED = True

TOOL_DEF = {
    "name": "skill_name",
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
    return "结果"
```

## Commit 规范

- `feat:` 新功能
- `fix:` 修复 bug
- `docs:` 文档更新
- `refactor:` 重构
- `chore:` 杂项
