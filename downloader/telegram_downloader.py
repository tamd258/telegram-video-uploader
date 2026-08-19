"""
Telegram 视频下载器
基于 Pyrogram，支持大小限制和断点续传
"""
import os
import asyncio
import logging
from pathlib import Path
from typing import Optional

from pyrogram import Client, StringSession

logger = logging.getLogger(__name__)

# 视频文件扩展名
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v", ".mpg", ".mpeg"}


class SizeTracker:
    """跟踪下载总大小，到达上限自动停止"""

    def __init__(self, max_total_bytes: int = 12 * 1024 * 1024 * 1024):
        self.max_total_bytes = max_total_bytes
        self.downloaded_bytes = 0
        self.file_count = 0

    def can_download(self, file_size: int) -> bool:
        return (self.downloaded_bytes + file_size) <= self.max_total_bytes

    def add(self, file_size: int):
        self.downloaded_bytes += file_size
        self.file_count += 1

    @property
    def downloaded_gb(self) -> float:
        return self.downloaded_bytes / (1024 ** 3)

    @property
    def max_gb(self) -> float:
        return self.max_total_bytes / (1024 ** 3)


def is_video(message) -> bool:
    """判断消息是否包含视频"""
    if message.video:
        return True
    if message.document:
        mime = message.document.mime_type or ""
        file_name = message.document.file_name or ""
        if mime.startswith("video/"):
            return True
        ext = Path(file_name).suffix.lower()
        if ext in VIDEO_EXTENSIONS:
            return True
    return False


def get_file_info(message) -> tuple:
    """获取 (文件大小, 文件名)"""
    if message.video:
        return message.video.file_size or 0, message.video.file_name or f"{message.id}.mp4"
    if message.document:
        return message.document.file_size or 0, message.document.file_name or f"{message.id}.unknown"
    return 0, f"{message.id}.unknown"


class TelegramVideoDownloader:
    """Telegram 视频下载器"""

    def __init__(
        self,
        api_id: int,
        api_hash: str,
        session_name: str = "downloader",
        download_dir: str = "./downloads",
        max_total_size_gb: float = 12.0,
        skip_larger_than_gb: float = 2.0,
    ):
        self.api_id = api_id
        self.api_hash = api_hash
        self.session_name = session_name
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.tracker = SizeTracker(int(max_total_size_gb * 1024 ** 3))
        self.max_single = int(skip_larger_than_gb * 1024 ** 3)

    async def _resolve_source_name(self, client, chat_id) -> str:
        """把 chat_id 解析为友好的目录名 (用于分目录存放)"""
        s = str(chat_id).strip()
        if s.lower() in ("me", "self"):
            return "我的收藏"
        name = s
        try:
            chat = await client.get_chat(chat_id)
            name = chat.title or chat.first_name or chat.username or s
        except Exception as e:
            logger.warning(f"解析 chat 名称失败 ({chat_id}): {e}, 使用原始 ID 作为目录名")
        # 清理路径非法字符
        name = "".join(c for c in str(name) if c not in '\\/:*?"<>|').strip()
        return name or s

    async def download_chat_videos(
        self,
        chat_id: str,
        last_message_id: int = 0,
    ) -> tuple[list[Path], int]:
        """下载指定 chat 的视频，返回 (文件列表, 最新消息ID)"""
        downloaded_files = []
        latest_msg_id = last_message_id

        # 优先使用字符串会话 (GitHub Actions 场景, 从 Secret TG_SESSION_STRING 读取)
        # 本地开发可保留文件会话 (downloader.session)
        session_string = os.environ.get("TG_SESSION_STRING")
        client_kwargs = {
            "api_id": self.api_id,
            "api_hash": self.api_hash,
        }
        if session_string:
            client_kwargs["session"] = StringSession(session_string)
            logger.info("使用 TG_SESSION_STRING 字符串会话登录")
        else:
            client_kwargs["session"] = self.session_name
            client_kwargs["workdir"] = str(self.download_dir.parent)
            logger.info("使用本地文件会话登录")

        async with Client(**client_kwargs) as client:
            # 分目录: 每个 chat 的文件存到 downloads/<来源名>/ 子目录
            source_name = await self._resolve_source_name(client, chat_id)
            source_dir = self.download_dir / source_name
            source_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"开始扫描: {chat_id} → 存放目录: {source_name}")

            async for message in client.get_chat_history(
                chat_id=chat_id,
                offset_id=last_message_id if last_message_id > 0 else 0,
            ):
                # 记录最新的消息 ID
                if latest_msg_id == 0 or message.id < latest_msg_id:
                    pass
                if message.id > latest_msg_id:
                    latest_msg_id = message.id

                if not is_video(message):
                    continue

                file_size, file_name = get_file_info(message)
                if file_size <= 0:
                    continue

                # 跳过超大文件 (>2GB)
                if file_size > self.max_single:
                    logger.info(f"跳过过大文件: {file_name} ({file_size / 1024**3:.2f}GB)")
                    continue

                # 检查总量是否已到 12GB 上限
                if not self.tracker.can_download(file_size):
                    logger.info(f"已达到总量限制 {self.tracker.max_gb:.1f}GB, 停止")
                    break

                # 跳过已存在的文件
                dest_path = source_dir / file_name
                if dest_path.exists() and dest_path.stat().st_size == file_size:
                    logger.info(f"已存在跳过: {file_name}")
                    self.tracker.add(file_size)
                    downloaded_files.append(dest_path)
                    continue

                logger.info(
                    f"下载: {file_name} ({file_size / 1024**3:.2f}GB) "
                    f"[{self.tracker.downloaded_gb:.1f}/{self.tracker.max_gb:.1f}GB]"
                )

                try:
                    downloaded = await message.download(file_name=str(dest_path))
                    if downloaded:
                        self.tracker.add(file_size)
                        downloaded_files.append(Path(downloaded))
                except Exception as e:
                    logger.error(f"下载失败 {file_name}: {e}")

        logger.info(
            f"下载完成: {self.tracker.file_count} 个文件, "
            f"总计 {self.tracker.downloaded_gb:.2f}GB"
        )
        return downloaded_files, latest_msg_id


# 测试入口
async def main():
    import yaml

    with open("config/config.yaml", "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    dl = TelegramVideoDownloader(
        api_id=cfg["telegram"]["api_id"],
        api_hash=cfg["telegram"]["api_hash"],
        download_dir=cfg.get("download_dir", "./downloads"),
        max_total_size_gb=cfg.get("max_total_size_gb", 12.0),
        skip_larger_than_gb=cfg.get("skip_larger_than_gb", 2.0),
    )

    for chat in cfg["chats"]:
        files, _ = await dl.download_chat_videos(
            chat_id=chat["chat_id"],
            last_message_id=chat.get("last_message_id", 0),
        )
        print(f"频道 {chat['chat_id']}: 下载 {len(files)} 个文件")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
