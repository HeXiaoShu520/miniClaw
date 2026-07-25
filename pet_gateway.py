"""
miniPet FastAPI 网关。

miniClaw 通过此模块暴露本地 WebSocket/HTTP 接口，让 miniPet 作为外部智能体客户端接入。
"""
import json
import logging
from typing import Awaitable, Callable
from uuid import uuid4

import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from link_service import LinkService

SESSION_HELLO = "session.hello"
SESSION_READY = "session.ready"
SESSION_PONG = "session.pong"
USER_COMMAND = "user.command"
USER_ACTION = "user.action"
USER_INPUT = "user.input"
USER_DROP = "user.drop"
SURFACE_SHOW = "surface.show"


def _event(event_type: str, payload: dict | None = None, request_id: str | None = None) -> dict:
    data = {
        "version": "1.0",
        "type": event_type,
        "source": "miniclaw",
        "payload": payload or {},
    }
    if request_id:
        data["request_id"] = request_id
    return data


def _extract_text(event: dict) -> str:
    payload = event.get("payload") or {}
    for key in ("content", "text", "message"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _conv_key(client_id: str, event: dict) -> str:
    payload = event.get("payload") or {}
    context = payload.get("context") or {}
    session_id = payload.get("session_id") or context.get("session_id") or client_id
    return f"desktop:{session_id}"


async def _send_json(send_event: Callable[[dict], Awaitable[None]], event_type: str, payload: dict | None = None, request_id: str | None = None):
    await send_event(_event(event_type, payload, request_id))


async def _handle_client_event(service: LinkService, client_id: str, event: dict, send_event: Callable[[dict], Awaitable[None]]):
    event_type = event.get("type") or ""
    request_id = event.get("request_id")

    if event_type == SESSION_HELLO:
        await _send_json(send_event, SESSION_READY, {
            "server": {
                "name": "miniClaw",
                "kind": "desktop-agent",
            },
            "protocol": "minipet.v1",
            "accepted_surface_kinds": ["card"],
        }, request_id)
        return

    if event_type == SESSION_PONG:
        return

    if event_type in (USER_COMMAND, USER_ACTION, USER_INPUT, USER_DROP):
        text = _extract_text(event)
        metadata = {
            "provider": "miniclaw",
            "client_id": client_id,
            "event_type": event_type,
        }
        metadata.update((event.get("payload") or {}).get("metadata") or {})

        if text:
            await service.handle_desktop_command(_conv_key(client_id, event), text, send_event, metadata)
        else:
            await _send_json(send_event, SURFACE_SHOW, {
                "kind": "card",
                "title": "miniClaw",
                "content": "这个动作暂时还没有可处理的文本内容。",
                "status": "done",
                "done": True,
                "timeout_ms": 6000,
                "metadata": metadata,
            }, request_id)

        return

    logging.debug(f"[pet_gateway] 忽略未知事件: {event_type}")


def create_app(service: LinkService) -> FastAPI:
    app = FastAPI(title="miniClaw miniPet Gateway")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health():
        return {"ok": True}

    @app.websocket("/ws/minipet")
    async def minipet_ws(ws: WebSocket):
        await ws.accept()
        client_id = uuid4().hex
        logging.info(f"[pet_gateway] miniPet 已连接: {client_id}")

        async def send_event(event: dict):
            await ws.send_text(json.dumps(event, ensure_ascii=False))

        try:
            while True:
                raw = await ws.receive_text()
                try:
                    event = json.loads(raw)
                except Exception:
                    await _send_json(send_event, SURFACE_SHOW, {
                        "kind": "card",
                        "title": "miniClaw",
                        "content": "收到的消息不是有效 JSON。",
                        "status": "failed",
                        "timeout_ms": 6000,
                    })
                    continue
                if isinstance(event, dict):
                    await _handle_client_event(service, client_id, event, send_event)
        except WebSocketDisconnect:
            logging.info(f"[pet_gateway] miniPet 已断开: {client_id}")

    @app.post("/actions/execute")
    async def execute_action(request: Request):
        event = await request.json()
        client_id = "http-fallback"
        replies: list[dict] = []

        async def collect_event(reply: dict):
            replies.append(reply)

        if isinstance(event, dict):
            await _handle_client_event(service, client_id, event, collect_event)
        return {"ok": True, "events": replies}

    return app


async def run_pet_gateway(service: LinkService, host: str = "127.0.0.1", port: int = 18889):
    app = create_app(service)
    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    logging.info(f"[pet_gateway] 启动，监听 ws://{host}:{port}/ws/minipet")
    await server.serve()
