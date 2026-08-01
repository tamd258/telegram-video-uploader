"""
主入口：下载 Telegram 视频 → 上传到中国移动云盘
适用于 GitHub Actions 环境
"""
import os
import sys
import yaml
import asyncio
import logging
from pathlib import Path

from downloader.telegram_downloader import TelegramVideoDownloader
from downloader.uploader import RcloneUploader, setup_rclone_for_alist

logger = logging.getLogger(__name__)


def load_config(config_path: str = "config/config.yaml") -> dict:
    """加载配置文件"""
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_state(state_path: str = "config/state.yaml") -> dict:
    """加载状态文件 (记录上次下载位置)"""
    if not Path(state_path).exists():
        return {}
    with open(state_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def save_state(state: dict, state_path: str = "config/state.yaml"):
    """保存状态文件"""
    Path(state_path).parent.mkdir(parents=True, exist_ok=True)
    with open(state_path, "w", encoding="utf-8") as f:
        yaml.dump(state, f, allow_unicode=True)


async def run_pipeline():
    """运行完整的下载→上传流水线"""
    cfg = load_config()

    # 设置日志
    logging.basicConfig(
        level=getattr(logging, cfg.get("log_level", "INFO")),
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    # 1. 配置 rclone 连接 alist WebDAV
    logger.info("=== 配置 rclone ===")
    alist_url = os.environ.get("ALIST_WEBDAV_URL", "http://localhost:5244/dav")
    setup_rclone_for_alist("config/rclone.conf", alist_url)

    # 2. 下载 Telegram 视频
    logger.info("=== 开始下载 Telegram 视频 ===")
    download_dir = cfg.get("download_dir", "./downloads")
    Path(download_dir).mkdir(parents=True, exist_ok=True)

    state = load_state()

    downloader = TelegramVideoDownloader(
        api_id=cfg["telegram"]["api_id"],
        api_hash=cfg["telegram"]["api_hash"],
        session_name=cfg["telegram"].get("session_name", "downloader"),
        download_dir=download_dir,
        max_total_size_gb=cfg.get("max_total_size_gb", 12.0),
        skip_larger_than_gb=cfg.get("skip_larger_than_gb", 2.0),
    )

    all_files = []
    for chat_cfg in cfg["chats"]:
        chat_id = chat_cfg["chat_id"]

        # 读取上次下载位置
        last_id = state.get(str(chat_id), chat_cfg.get("last_message_id", 0))

        logger.info(f"处理频道: {chat_id}, 从消息 {last_id} 开始")
        files = await downloader.download_chat_videos(
            chat_id=chat_id,
            last_message_id=last_id,
        )
        all_files.extend(files)

        # 更新状态 (记录已下载到的最新消息 ID)
        if files:
            # 实际上需要记录扫描过的最新消息 ID
            # 这里简化处理，实际使用时应从下载循环中获取
            pass

    logger.info(f"下载完成: {len(all_files)} 个文件, {downloader.tracker.downloaded_gb:.2f}GB")

    if not all_files:
        logger.info("没有新文件需要下载")
        return

    # 3. 上传到移动云盘
    logger.info("=== 开始上传到中国移动云盘 ===")
    uploader = RcloneUploader(
        remote_name=cfg["cloud"].get("rclone_remote", "mcloud"),
        remote_dir=cfg["cloud"].get("remote_dir", "/aaa"),
        rclone_config="config/rclone.conf",
        delete_after_upload=cfg["cloud"].get("delete_after_upload", True),
    )

    if not uploader.test_connection():
        logger.error("无法连接到云盘, 退出")
        sys.exit(1)

    success, failed = uploader.upload_files(all_files)
    logger.info(f"上传完成: 成功 {success}, 失败 {failed}")

    # 4. 清理
    if success > 0:
        save_state(state)
        logger.info("状态已保存")


if __name__ == "__main__":
    asyncio.run(run_pipeline())
