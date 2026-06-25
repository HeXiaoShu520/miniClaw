"""
桌面宠物 WebSocket 推送网关
miniClaw 收到飞书消息后，通过此模块推送给 DyberPet
"""
import json
import logging
import asyncio
import websockets

_clients: set = set()


async def serve(host="localhost", port=18888):
    async def handler(ws):
        _clients.add(ws)
        logging.info(f"[pet_gateway] 宠物客户端连接: {ws.remote_address}")
        try:
            await ws.wait_closed()
        finally:
            _clients.discard(ws)
            logging.info(f"[pet_gateway] 宠物客户端断开")

    async with websockets.serve(handler, host, port):
        logging.info(f"[pet_gateway] 启动，监听 ws://{host}:{port}")
        await asyncio.Future()  # 永久运行


async def broadcast(event: dict):
    if not _clients:
        return
    data = json.dumps(event, ensure_ascii=False)
    await asyncio.gather(*[ws.send(data) for ws in list(_clients)], return_exceptions=True)
