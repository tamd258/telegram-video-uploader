"""
主入口：下载 Telegram 视频 → 上传到 Google Drive
适用于 GitHub Actions 环境和本地运行
"""
import os
import sys
import yaml
import asyncio
import logging
from pathlib import Path

from downloader.telegram_downloader import TelegramVideoDownloader
from downloader.uploader import GoogleDriveUploader

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

    # 1. 下载 Telegram 视频
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
        files, latest_id = await downloader.download_chat_videos(
            chat_id=chat_id,
            last_message_id=last_id,
        )
        all_files.extend(files)

        # 更新状态
        if latest_id > 0:
            state[str(chat_id)] = latest_id

    logger.info(f"下载完成: {len(all_files)} 个文件, {downloader.tracker.downloaded_gb:.2f}GB")

    if not all_files:
        logger.info("没有新文件需要下载")
        return

    # 2. 上传到 Google Drive
    logger.info("=== 开始上传到 Google Drive ===")
    cloud_cfg = cfg.get("cloud", {})

    # 上传器优先从环境变量读取 OAuth 凭证 (GDRIVE_CLIENT_ID/SECRET/REFRESH_TOKEN)
    # 个人 Google 账号推荐 OAuth 方式, 文件存进你的 Drive, 使用你的配额
    uploader = GoogleDriveUploader(
        remote_dir=cloud_cfg.get("remote_dir", "/TelegramVideos"),
        delete_after_upload=cloud_cfg.get("delete_after_upload", True),
    )

    if not uploader.test_connection():
        logger.error("无法连接到 Google Drive, 退出")
        sys.exit(1)

    # 按来源子目录分组上传: downloads/<来源>/<文件> → Drive/<remote_dir>/<来源>/
    from collections import defaultdict

    download_root = Path(download_dir)
    groups = defaultdict(list)
    for f in all_files:
        f = Path(f)
        try:
            rel = f.relative_to(download_root)
        except ValueError:
            rel = f
        source = rel.parts[0] if len(rel.parts) > 1 else ""
        groups[source].append(f)

    base_remote = cloud_cfg.get("remote_dir", "/TelegramVideos").rstrip("/")
    total_success = 0
    total_failed = 0
    for source, group_files in groups.items():
        remote = base_remote + ("/" + source if source else "")
        logger.info(f"上传 [{source or '根目录'}] {len(group_files)} 个文件 → {remote}")
        success, failed = uploader.upload_files(group_files, remote_dir=remote)
        total_success += success
        total_failed += failed

    logger.info(f"上传完成: 成功 {total_success}, 失败 {total_failed}")

    # 3. 保存状态
    if total_success > 0:
        save_state(state)
        logger.info("状态已保存")


if __name__ == "__main__":
    asyncio.run(run_pipeline())
