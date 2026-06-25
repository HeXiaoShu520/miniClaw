"""
桌面宠物 HTTP API
为桌面宠物气泡窗口提供对话接口，复用现有 AI 客户端
"""
import asyncio
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import AppConfig

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# 全局 AI 客户端（启动时初始化）
_ai_client = None
_system_prompt = "你是一个可爱的桌面宠物小月，用简短、俏皮的语气回复，不超过50字。"


class ChatRequest(BaseModel):
    message: str


@app.on_event("startup")
async def startup():
    global _ai_client
    config = AppConfig.discover()
    if config.ai_provider == "openai":
        from openai_client import OpenAIClient
        _ai_client = OpenAIClient(config.openai.api_key, config.openai.model, config.openai.base_url)
    else:
        from claude_client import AnthropicClient
        _ai_client = AnthropicClient(config.claude.api_key, config.claude.model, config.claude.base_url)


@app.post("/chat")
async def chat(req: ChatRequest):
    try:
        reply = await _ai_client.call(
            messages=[{"role": "user", "content": req.message}],
            system=_system_prompt
        )
        return {"reply": reply}
    except Exception as e:
        return {"error": str(e)}, 500


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8765)
