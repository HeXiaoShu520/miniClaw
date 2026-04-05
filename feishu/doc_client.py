"""
飞书云文档客户端模块
保留手动实现（飞书 SDK 的文档 API 支持不完善）
"""
import aiohttp
import logging
from typing import Optional


class FeishuDocClient:
    """飞书云文档内容提取客户端（保留手动实现）"""

    def __init__(self, access_token: str):
        """
        初始化文档客户端

        Args:
            access_token: 飞书访问令牌
        """
        self.access_token = access_token
        self.session = None

    async def _get_session(self):
        """获取或创建 aiohttp 会话"""
        if self.session is None:
            self.session = aiohttp.ClientSession()
        return self.session

    async def close(self):
        """关闭客户端，释放资源"""
        if self.session:
            await self.session.close()

    async def extract_wiki(self, node_token: str) -> Optional[str]:
        """
        提取知识库文档内容

        Args:
            node_token: 知识库节点 token

        Returns:
            Optional[str]: 文档内容，失败返回 None
        """
        try:
            session = await self._get_session()
            url = f"https://open.feishu.cn/open-apis/wiki/v2/spaces/get_node?token={node_token}"
            headers = {"Authorization": f"Bearer {self.access_token}"}

            async with session.get(url, headers=headers) as resp:
                result = await resp.json()
                if result.get("code") != 0:
                    logging.error(f"获取知识库节点失败: {result}")
                    return None

                node = result.get("data", {}).get("node", {})
                obj_token = node.get("obj_token")
                obj_type = node.get("obj_type")

                # 根据文档类型调用对应的提取方法
                if obj_type == "doc":
                    return await self.extract_doc(obj_token)
                elif obj_type == "docx":
                    return await self.extract_docx(obj_token)

                return None
        except Exception as e:
            logging.error(f"提取知识库文档失败: {e}")
            return None

    async def extract_doc(self, doc_token: str) -> Optional[str]:
        """
        提取旧版文档内容

        Args:
            doc_token: 文档 token

        Returns:
            Optional[str]: 文档内容，失败返回 None
        """
        try:
            session = await self._get_session()
            url = f"https://open.feishu.cn/open-apis/doc/v2/{doc_token}/raw_content"
            headers = {"Authorization": f"Bearer {self.access_token}"}

            async with session.get(url, headers=headers) as resp:
                result = await resp.json()
                if result.get("code") != 0:
                    logging.error(f"获取旧版文档失败: {result}")
                    return None

                return result.get("data", {}).get("content", "")
        except Exception as e:
            logging.error(f"提取旧版文档失败: {e}")
            return None

    async def extract_docx(self, document_id: str) -> Optional[str]:
        """
        提取新版文档内容

        Args:
            document_id: 文档 ID

        Returns:
            Optional[str]: 文档内容，失败返回 None
        """
        try:
            session = await self._get_session()
            url = f"https://open.feishu.cn/open-apis/docx/v1/documents/{document_id}/raw_content"
            headers = {"Authorization": f"Bearer {self.access_token}"}

            async with session.get(url, headers=headers) as resp:
                result = await resp.json()
                if result.get("code") != 0:
                    logging.error(f"获取新版文档失败: {result}")
                    return None

                return result.get("data", {}).get("content", "")
        except Exception as e:
            logging.error(f"提取新版文档失败: {e}")
            return None
