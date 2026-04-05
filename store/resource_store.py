"""
资源文件存储模块
支持 SHA256 去重和过期清理
"""
import hashlib
import logging
from pathlib import Path
from datetime import datetime, timedelta


class ResourceStore:
    """资源文件存储管理器，使用 SHA256 哈希去重"""

    def __init__(self, save_dir: Path):
        """
        初始化资源存储

        Args:
            save_dir: 存储目录路径
        """
        self.save_dir = save_dir
        self.save_dir.mkdir(parents=True, exist_ok=True)

    async def save_resource(
        self,
        feishu_client,
        message_id: str,
        file_key: str,
        resource_type: str,
        original_name: str
    ) -> Path:
        """
        下载并保存资源文件，返回本地路径
        使用 SHA256 哈希去重，相同文件只存储一次

        Args:
            feishu_client: 飞书客户端实例
            message_id: 消息 ID
            file_key: 文件 key
            resource_type: 资源类型（image 或 file）
            original_name: 原始文件名

        Returns:
            Path: 本地文件路径
        """
        # 下载资源
        data = await feishu_client.download_resource(message_id, file_key, resource_type)

        # 计算 SHA256 哈希
        hash_obj = hashlib.sha256(data)
        file_hash = hash_obj.hexdigest()

        # 提取扩展名
        ext = Path(original_name).suffix or ".bin"
        filename = f"{file_hash}{ext}"
        file_path = self.save_dir / filename

        # 如果文件已存在，更新修改时间（用于过期清理）
        if file_path.exists():
            file_path.touch()
            logging.debug(f"资源已存在，跳过: {filename}")
        else:
            file_path.write_bytes(data)
            logging.info(f"资源已保存: {filename} ({len(data)} bytes)")

        return file_path

    def cleanup_expired(self, retention_days: int) -> int:
        """
        清理过期资源文件

        Args:
            retention_days: 保留天数

        Returns:
            int: 清理的文件数量
        """
        if not self.save_dir.exists():
            return 0

        cutoff = datetime.now() - timedelta(days=retention_days)
        removed = 0

        for file_path in self.save_dir.iterdir():
            if not file_path.is_file():
                continue

            # 检查文件修改时间
            mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
            if mtime < cutoff:
                try:
                    file_path.unlink()
                    removed += 1
                except Exception as e:
                    logging.warning(f"删除过期资源失败: {file_path} - {e}")

        if removed > 0:
            logging.info(f"资源清理完成: 删除 {removed} 个过期文件")

        return removed
