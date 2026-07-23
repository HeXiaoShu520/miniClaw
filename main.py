#!/usr/bin/env python3
"""
飞书-Claude 桥接服务主程序
负责启动 WebSocket 监听、MCP Server 和定时清理任务
"""
import asyncio
import logging
import signal
from pathlib import Path
from datetime import datetime, timedelta

from config import AppConfig
from feishu.feishu_api import FeishuClient
from feishu.websocket import FeishuWebSocket
from link_service import LinkService
from pet_gateway import run_pet_gateway


async def cleanup_old_logs(log_dir: Path, retention_days: int):
    """
    清理过期日志文件

    Args:
        log_dir: 日志目录
        retention_days: 保留天数
    """
    if not log_dir.exists():
        return

    cutoff = datetime.now() - timedelta(days=retention_days)
    removed = 0

    for log_file in log_dir.glob("acp-link.log.*"):
        if not log_file.is_file():
            continue

        mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
        if mtime < cutoff:
            try:
                log_file.unlink()
                removed += 1
            except Exception as e:
                logging.warning(f"删除过期日志失败: {log_file} - {e}")

    if removed > 0:
        logging.info(f"日志清理完成: 删除 {removed} 个过期文件")


async def cleanup_temp_dir(retention_days: int):
    """
    清理临时目录中的过期文件

    Args:
        retention_days: 保留天数
    """
    temp_dir = AppConfig.temp_dir()
    if not temp_dir.exists():
        return

    cutoff = datetime.now() - timedelta(days=retention_days)
    removed = 0

    for temp_file in temp_dir.iterdir():
        if not temp_file.is_file():
            continue

        mtime = datetime.fromtimestamp(temp_file.stat().st_mtime)
        if mtime < cutoff:
            try:
                temp_file.unlink()
                removed += 1
            except Exception as e:
                logging.warning(f"删除过期临时文件失败: {temp_file} - {e}")

    if removed > 0:
        logging.info(f"临时目录清理完成: 删除 {removed} 个过期文件")


async def run_cleanup(service: LinkService, config: AppConfig):
    """
    执行定时清理任务（每小时一次）

    Args:
        service: LinkService 实例
        config: 应用配置
    """
    while True:
        await asyncio.sleep(3600)  # 每小时执行一次
        try:
            service.cleanup_sessions(config.session_retention)
            # 清理过期会话
            # 清理过期资源文件
            service.cleanup_resources()
            # 清理临时目录
            await cleanup_temp_dir(config.resource_retention)
            # 清理过期日志
            await cleanup_old_logs(AppConfig.log_dir(), config.log_retention)
        except Exception as e:
            logging.error(f"清理任务失败: {e}")


async def main():
    """主函数：初始化并启动所有服务"""
    print("feishu-claude v0.3.0 (Python)")

    # 加载配置
    config = AppConfig.discover()
    print(f"==================== 配置加载 ====================")
    print(f"AI_PROVIDER={config.ai_provider}")
    print(f"USE_TOPIC_REPLY={config.use_topic_reply}")
    print(f"==================================================\n")

    # 初始化日志
    log_dir = AppConfig.log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)

    # 先降低第三方库的日志级别（必须在 basicConfig 之前）
    logging.getLogger('websockets.client').setLevel(logging.WARNING)
    logging.getLogger('urllib3.connectionpool').setLevel(logging.WARNING)
    logging.getLogger('httpcore.http11').setLevel(logging.WARNING)
    logging.getLogger('httpcore.connection').setLevel(logging.WARNING)
    logging.getLogger('httpcore.proxy').setLevel(logging.WARNING)
    logging.getLogger('anthropic._base_client').setLevel(logging.WARNING)
    logging.getLogger('httpx').setLevel(logging.WARNING)

    logging.basicConfig(
        level=config.log_level.upper(),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_dir / "acp-link.log", encoding='utf-8'),
            logging.StreamHandler()
        ]
    )

    # 初始化客户端
    feishu = FeishuClient(config.feishu.app_id, config.feishu.app_secret)
    ws_client = FeishuWebSocket(config.feishu.app_id, config.feishu.app_secret)

    # 根据 AI_PROVIDER 创建对应的 AI 客户端
    if config.ai_provider == "openai":
        from openai_client import OpenAIClient
        ai_client = OpenAIClient(config.openai.api_key, config.openai.model, config.openai.base_url)
        print(f"AI Provider: OpenAI ({config.openai.model})")
    else:
        from claude_client import AnthropicClient
        ai_client = AnthropicClient(config.claude.api_key, config.claude.model, config.claude.base_url)
        print(f"AI Provider: Anthropic ({config.claude.model})")

    # 启动服务
    service = LinkService(config, feishu, ai_client)

    logging.info("服务启动成功")

    # 通知管理员上线
    if config.admin_open_id and config.admin_online_msg:
        try:
            await feishu.send_text_to_user(config.admin_open_id, config.admin_online_msg)
        except Exception as e:
            logging.warning(f"通知管理员上线失败: {e}")

    # 启动 WebSocket 监听（自动重连）
    async def run_ws():
        """WebSocket 监听任务，断线自动重连"""
        while True:
            try:
                await ws_client.listen(service.handle_message)
            except Exception as e:
                logging.error(f"WebSocket 断开: {e}, 5秒后重连...")
                await asyncio.sleep(5)

    async def run_pet_api():
        """miniPet 本地网关任务，失败不影响飞书链路。"""
        try:
            await run_pet_gateway(service, host=config.desktop_host, port=config.desktop_port)
        except Exception as e:
            logging.error(f"miniPet 网关启动失败: {e}", exc_info=True)

    ws_task = asyncio.create_task(run_ws())
    cleanup_task = asyncio.create_task(run_cleanup(service, config))
    pet_task = asyncio.create_task(run_pet_api()) if config.desktop_enabled else None

    # 等待关机信号
    stop_event = asyncio.Event()

    def signal_handler():
        """处理关机信号"""
        logging.info("收到关机信号")
        stop_event.set()

    # Windows 兼容的信号处理
    try:
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, signal_handler)
    except NotImplementedError:
        # Windows 不支持 add_signal_handler
        signal.signal(signal.SIGINT, lambda s, f: stop_event.set())

    await stop_event.wait()

    # 清理资源
    cleanup_task.cancel()
    ws_task.cancel()
    if pet_task:
        pet_task.cancel()
    service.save_sessions()

    # 通知管理员下线
    if config.admin_open_id and config.admin_offline_msg:
        try:
            await feishu.send_text_to_user(config.admin_open_id, config.admin_offline_msg)
        except Exception as e:
            logging.warning(f"通知管理员下线失败: {e}")

    await feishu.close()


if __name__ == "__main__":
    asyncio.run(main())
