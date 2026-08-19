"""
Google Drive 上传器
优先使用 OAuth 用户凭证 (refresh token): 文件以你的个人 Google 账号身份上传,
存进你的 Drive, 使用你的存储配额 (个人账号推荐, Service Account 无配额会 403)。
Service Account 仅适用于 Google Workspace 账号。
支持大文件分块/断点续传上传。
"""
import os
import json
import logging
from pathlib import Path
from typing import Optional

from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

logger = logging.getLogger(__name__)

# Google Drive API scopes
SCOPES = ["https://www.googleapis.com/auth/drive"]
# OAuth token 刷新地址
TOKEN_URI = "https://oauth2.googleapis.com/token"

# 分块大小 (10MB，适合大文件断点续传)
DEFAULT_CHUNKSIZE = 10 * 1024 * 1024


class GoogleDriveUploader:
    """通过 Google Drive API 上传文件 (OAuth 用户凭证优先, Service Account 兜底)"""

    def __init__(
        self,
        service_account_json: str = None,
        service_account_file: str = None,
        remote_dir: str = "/TelegramVideos",
        delete_after_upload: bool = True,
        chunksize: int = DEFAULT_CHUNKSIZE,
    ):
        """
        初始化 Google Drive 上传器

        认证优先级:
          1. OAuth 用户凭证: 环境变量 GDRIVE_CLIENT_ID + GDRIVE_CLIENT_SECRET + GDRIVE_REFRESH_TOKEN
             (个人 Google 账号推荐, 文件存进你的 Drive, 使用你的配额)
          2. Service Account: service_account_json / service_account_file / GDRIVE_SERVICE_ACCOUNT_JSON
             (仅适用于 Google Workspace 账号; 个人账号无配额会上传报 403)

        Args:
            service_account_json: Service Account JSON 字符串
            service_account_file: Service Account JSON 文件路径
            remote_dir: Google Drive 上的目标文件夹路径，如 /Folder1/SubFolder
            delete_after_upload: 上传成功后删除本地文件
            chunksize: 分块上传大小 (字节)
        """
        self.remote_dir = remote_dir.strip("/")
        self.delete_after_upload = delete_after_upload
        self.chunksize = chunksize

        # 1. 优先 OAuth 用户凭证 (个人账号推荐)
        cid = os.environ.get("GDRIVE_CLIENT_ID")
        csec = os.environ.get("GDRIVE_CLIENT_SECRET")
        crt = os.environ.get("GDRIVE_REFRESH_TOKEN")
        if cid and csec and crt:
            self.credentials = Credentials(
                token=None,
                refresh_token=crt,
                token_uri=TOKEN_URI,
                client_id=cid,
                client_secret=csec,
                scopes=SCOPES,
            )
            self.auth_type = "oauth"
            self.account = "personal (OAuth)"
        # 2. Service Account 兜底 (Workspace 账号)
        elif service_account_json:
            info = json.loads(service_account_json)
            self.credentials = service_account.Credentials.from_service_account_info(
                info, scopes=SCOPES
            )
            self.account = info.get("client_email", "unknown")
        elif service_account_file:
            self.credentials = service_account.Credentials.from_service_account_file(
                service_account_file, scopes=SCOPES
            )
            with open(service_account_file, "r") as f:
                info = json.load(f)
                self.account = info.get("client_email", "unknown")
        else:
            env_json = os.environ.get("GDRIVE_SERVICE_ACCOUNT_JSON")
            if env_json:
                info = json.loads(env_json)
                self.credentials = service_account.Credentials.from_service_account_info(
                    info, scopes=SCOPES
                )
                self.account = info.get("client_email", "unknown")
            else:
                raise ValueError(
                    "需要 OAuth 环境变量 (GDRIVE_CLIENT_ID/SECRET/REFRESH_TOKEN) "
                    "或 Service Account 凭证"
                )

        # 主动刷新一次 token, 提前验证 refresh_token 有效
        if not self.credentials.valid:
            try:
                from google.auth.transport.requests import Request

                self.credentials.refresh(Request())
            except Exception as e:
                raise ValueError(f"OAuth token 刷新失败, 请重新生成 refresh token: {e}")

        # static_discovery=True: 使用内置 discovery 文档, 无需额外请求 googleapis.com
        self.service = build("drive", "v3", credentials=self.credentials, static_discovery=True)
        logger.info(f"Google Drive 上传器已初始化, 认证方式: {self.account}")

    def test_connection(self) -> bool:
        """测试 Google Drive 连接 (列出根目录文件)"""
        try:
            results = self.service.files().list(
                pageSize=1, fields="files(id, name)"
            ).execute()
            files = results.get("files", [])
            logger.info(f"Google Drive 连接成功, 根目录可见 {len(files)} 个文件")
            return True
        except Exception as e:
            logger.error(f"Google Drive 连接失败: {e}")
            return False

    def _find_folder(
        self, folder_name: str, parent_id: Optional[str] = None, include_shared: bool = False
    ) -> Optional[str]:
        """按名称查找文件夹，返回 folder_id 或 None

        include_shared=True 时查找"共享给 Service Account 的文件夹"
        (仅 Service Account 模式下用于定位共享目录; OAuth 个人模式用 root 查找)
        """
        safe_name = folder_name.replace("'", "\\'")
        query = (
            f"name = '{safe_name}' and mimeType = 'application/vnd.google-apps.folder' "
            f"and trashed = false"
        )
        if parent_id:
            query += f" and '{parent_id}' in parents"
        elif include_shared:
            query += " and sharedWithMe = true"
        else:
            query += " and 'root' in parents"

        results = self.service.files().list(
            q=query, pageSize=1, fields="files(id, name)"
        ).execute()
        files = results.get("files", [])
        return files[0]["id"] if files else None

    def _create_folder(self, folder_name: str, parent_id: Optional[str] = None) -> str:
        """创建文件夹，返回 folder_id"""
        file_metadata = {
            "name": folder_name,
            "mimeType": "application/vnd.google-apps.folder",
        }
        if parent_id:
            file_metadata["parents"] = [parent_id]
        else:
            file_metadata["parents"] = ["root"]

        folder = self.service.files().create(
            body=file_metadata, fields="id"
        ).execute()
        logger.info(f"创建文件夹: {folder_name} (id={folder.get('id')})")
        return folder.get("id")

    def _get_or_create_folder_path(self, path_str: str) -> str:
        """
        按路径获取或创建文件夹 (支持多级路径 /A/B/C)
        返回最深一级文件夹的 folder_id
        使用 OAuth 个人身份时, 文件夹在 'root' (你的 Drive 根目录) 下查找/创建
        """
        if not path_str:
            return "root"

        parts = [p.strip() for p in path_str.split("/") if p.strip()]
        parent_id = None  # None = root (你的 Drive 根目录)

        for part in parts:
            folder_id = self._find_folder(part, parent_id)
            if folder_id:
                logger.debug(f"文件夹已存在: {part}")
            else:
                folder_id = self._create_folder(part, parent_id)
            parent_id = folder_id

        return parent_id or "root"

    def upload_files(self, files: list, remote_dir: str = None) -> tuple:
        """
        上传文件列表到 Google Drive

        Args:
            files: 本地文件路径列表
            remote_dir: 目标文件夹路径 (可选, 覆盖默认值; 用于按来源分目录上传)

        Returns:
            (success_count, failed_count)
        """
        success = 0
        failed = 0

        target_dir = (remote_dir or self.remote_dir).strip("/")
        # 确保目标文件夹存在
        folder_id = self._get_or_create_folder_path(target_dir)
        logger.info(f"目标文件夹: {target_dir} (id={folder_id})")

        for file_path in files:
            file_path = Path(file_path)
            if not file_path.exists():
                logger.warning(f"文件不存在: {file_path}")
                failed += 1
                continue

            file_size = file_path.stat().st_size
            file_size_gb = file_size / (1024 ** 3)
            logger.info(f"上传: {file_path.name} ({file_size_gb:.2f}GB)")

            try:
                # 检查文件是否已存在于 Google Drive (按文件名)
                if self._file_exists(file_path.name, folder_id):
                    logger.info(f"Google Drive 上已存在同名文件, 跳过: {file_path.name}")
                    if self.delete_after_upload:
                        file_path.unlink()
                        logger.debug(f"已删除本地文件: {file_path.name}")
                    success += 1
                    continue

                # 分块/断点续传上传
                media = MediaFileUpload(
                    str(file_path),
                    mimetype="application/octet-stream",
                    resumable=True,
                    chunksize=self.chunksize,
                )

                file_metadata = {
                    "name": file_path.name,
                    "parents": [folder_id],
                }

                request = self.service.files().create(
                    body=file_metadata, media_body=media, fields="id, name"
                )

                # 分块上传循环
                response = None
                last_progress = 0
                while response is None:
                    status, response = request.next_chunk()
                    if status:
                        progress = int(status.progress() * 100)
                        if progress - last_progress >= 10 or progress == 100:
                            logger.info(f"  {file_path.name}: {progress}%")
                            last_progress = progress

                logger.info(f"上传成功: {file_path.name}")

                if self.delete_after_upload:
                    file_path.unlink()
                    logger.debug(f"已删除本地文件: {file_path.name}")

                success += 1

            except Exception as e:
                logger.error(f"上传失败: {file_path.name} - {e}")
                failed += 1

        return success, failed

    def _file_exists(self, file_name: str, folder_id: str) -> bool:
        """检查 Google Drive 上指定文件夹中是否已存在同名文件"""
        safe_name = file_name.replace("'", "\\'")
        query = (
            f"name = '{safe_name}' and trashed = false "
            f"and '{folder_id}' in parents"
        )
        try:
            results = self.service.files().list(
                q=query, pageSize=1, fields="files(id, name)"
            ).execute()
            return len(results.get("files", [])) > 0
        except Exception:
            return False

    def upload_directory(self, directory) -> tuple:
        """上传整个目录"""
        directory = Path(directory)
        files = [f for f in directory.glob("*") if f.is_file()]
        return self.upload_files(files)


def setup_gdrive_from_env(rclone_config_path: str = None, *args, **kwargs):
    """
    兼容旧接口: 从环境变量设置 Google Drive
    (原 setup_rclone_for_alist 的替代, 保留函数签名以兼容 main.py 调用)
    """
    logger.info("Google Drive 上传器通过环境变量/配置文件初始化, 无需额外设置")
