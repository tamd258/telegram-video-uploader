"""
OneDrive 上传器 (Microsoft Graph API)
用 OAuth refresh token 认证, 文件以 OneDrive2 账号 (yanfatd@gmail.com) 身份上传,
存进该账号的网盘, 使用它的 1TB 配额。

环境变量:
  OD_CLIENT_ID      Azure 应用 Client ID (alist 公共 app)
  OD_CLIENT_SECRET  Azure 应用 Client Secret
  OD_REFRESH_TOKEN  OneDrive2 账号的 refresh token (从本地 alist 数据库
                    x_storages 表 mount_path='/OneDrive2' 的 addition 里提取)

特性:
  - 大文件分块上传 (upload session, 5MB 块, 单块自动重试)
  - 同名文件自动跳过 (防重复上传)
  - 按路径自动创建多级目录 (/TelegramVideos/<来源>/)
  - 上传成功自动删除本地文件
仅用标准库, 无需 pip 安装任何东西。
"""
import os
import time
import json
import logging
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

GRAPH = "https://graph.microsoft.com/v1.0"
TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
SCOPE = "https://graph.microsoft.com/Files.ReadWrite.All offline_access"
# 5MB (必须是 320KB 的倍数)
DEFAULT_CHUNKSIZE = 5 * 1024 * 1024


class OneDriveUploader:
    """通过 Microsoft Graph API 上传文件到 OneDrive (refresh token 认证)"""

    def __init__(
        self,
        remote_dir: str = "/TelegramVideos",
        delete_after_upload: bool = True,
        chunksize: int = DEFAULT_CHUNKSIZE,
    ):
        self.remote_dir = (remote_dir or "/TelegramVideos").strip("/")
        self.delete_after_upload = delete_after_upload
        self.chunksize = chunksize

        self.client_id = os.environ.get("OD_CLIENT_ID")
        self.client_secret = os.environ.get("OD_CLIENT_SECRET")
        self.refresh_token = os.environ.get("OD_REFRESH_TOKEN")
        if not (self.client_id and self.client_secret and self.refresh_token):
            raise ValueError(
                "需要环境变量 OD_CLIENT_ID / OD_CLIENT_SECRET / OD_REFRESH_TOKEN"
            )

        self._access_token: Optional[str] = None
        self._token_exp = 0.0

    # ------------------------------------------------------------------
    # 认证
    # ------------------------------------------------------------------
    def _refresh_access_token(self) -> str:
        data = {
            "grant_type": "refresh_token",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": self.refresh_token,
            "scope": SCOPE,
        }
        req = urllib.request.Request(
            TOKEN_URL,
            data=urllib.parse.urlencode(data).encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as r:
            tok = json.loads(r.read().decode())
        # 微软会轮换 refresh token; 实测旧 RT 短期内仍有效, 但优先用新的
        self.refresh_token = tok.get("refresh_token", self.refresh_token)
        self._access_token = tok["access_token"]
        self._token_exp = time.time() + int(tok.get("expires_in", 3600)) - 120
        logger.info("OneDrive access token 已刷新 (有效期 %ss)", tok.get("expires_in"))
        return self._access_token

    def _token(self) -> str:
        if not self._access_token or time.time() >= self._token_exp:
            return self._refresh_access_token()
        return self._access_token

    def _request(
        self,
        method: str,
        url: str,
        *,
        json_body=None,
        data=None,
        headers=None,
        _retried_auth=False,
        _retries=0,
        timeout=300,
    ):
        """带 401 自动刷新 / 429+5xx 自动重试的请求。返回 (status, json_or_bytes)"""
        h = {"Authorization": "Bearer " + self._token()}
        if json_body is not None:
            data = json.dumps(json_body).encode()
            h["Content-Type"] = "application/json"
        if headers:
            h.update(headers)
        req = urllib.request.Request(url, data=data, headers=h, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                status = r.status
                raw = r.read()
        except urllib.error.HTTPError as e:
            status = e.code
            raw = e.read()

        if status == 401 and not _retried_auth:
            logger.info("token 过期 (401), 自动刷新重试")
            self._refresh_access_token()
            return self._request(
                method, url, json_body=json_body,
                data=None if json_body is not None else data,
                headers=headers, _retried_auth=True, _retries=_retries,
                timeout=timeout,
            )
        if status in (429, 500, 502, 503, 504) and _retries < 5:
            wait = min(60, 2 ** _retries * 3)
            logger.warning("HTTP %s, %ss 后重试 (%s)", status, wait, url[:80])
            time.sleep(wait)
            return self._request(
                method, url, json_body=json_body,
                data=None if json_body is not None else data,
                headers=headers, _retried_auth=_retried_auth,
                _retries=_retries + 1, timeout=timeout,
            )
        if 200 <= status < 300:
            try:
                return status, json.loads(raw.decode()) if raw else None
            except (ValueError, UnicodeDecodeError):
                return status, raw
        # 其他错误: 抛出带响应体的异常
        raise RuntimeError(f"Graph API {method} {url[:100]} -> HTTP {status}: {raw.decode(errors='replace')[:300]}")

    # ------------------------------------------------------------------
    # 连接测试
    # ------------------------------------------------------------------
    def test_connection(self) -> bool:
        try:
            _, d = self._request("GET", f"{GRAPH}/me/drive")
            logger.info(
                "OneDrive 连接成功: driveType=%s, 总容量 %.0fGB",
                d.get("driveType"), d.get("quota", {}).get("total", 0) / 1024 ** 3,
            )
            return True
        except Exception as e:
            logger.error("OneDrive 连接失败: %s", e)
            return False

    # ------------------------------------------------------------------
    # 目录
    # ------------------------------------------------------------------
    def _item_url(self, path: str) -> str:
        """按路径访问 driveItem: /me/drive/root:/a/b/c"""
        clean = "/" + "/".join(p for p in path.split("/") if p)
        return f"{GRAPH}/me/drive/root:{urllib.parse.quote(clean)}"

    def _children_url(self, parent: str) -> str:
        """列/建子项。注意 /children 必须在路径冒号段之外: root:/a/b:/children"""
        if parent and parent.strip("/"):
            return f"{self._item_url(parent)}:/children"
        return f"{GRAPH}/me/drive/root/children"

    def ensure_dir(self, path: str) -> None:
        """逐级确保目录存在 (GET 404 则创建)"""
        parts = [p for p in path.split("/") if p]
        cur = ""
        for seg in parts:
            parent = cur
            cur = f"{cur}/{seg}" if cur else seg
            try:
                self._request("GET", self._item_url(cur))
                continue  # 已存在
            except RuntimeError as e:
                if "HTTP 404" not in str(e):
                    raise
            body = {"name": seg, "folder": {}, "@microsoft.graph.conflictBehavior": "fail"}
            try:
                self._request("POST", self._children_url(parent), json_body=body)
                logger.info("创建文件夹: %s", cur)
            except RuntimeError as e:
                if "409" not in str(e):  # 并发创建冲突视为已存在
                    raise

    def _existing_names(self, dir_path: str) -> set:
        """列出目录下已有文件名 (分页取全)"""
        names = set()
        url = f"{self._children_url(dir_path)}?$select=name&$top=200"
        while url:
            _, d = self._request("GET", url)
            for it in d.get("value", []):
                names.add(it.get("name"))
            url = d.get("@odata.nextLink")
        return names

    # ------------------------------------------------------------------
    # 上传
    # ------------------------------------------------------------------
    def upload_files(self, files: list, remote_dir: str = None) -> tuple:
        """
        上传文件列表到 OneDrive

        Args:
            files: 本地文件路径列表
            remote_dir: 目标文件夹路径 (可选, 覆盖默认值; 用于按来源分目录上传)

        Returns:
            (success_count, failed_count)
        """
        success = 0
        failed = 0
        target_dir = (remote_dir or self.remote_dir).strip("/")
        self.ensure_dir(target_dir)
        logger.info("目标文件夹: /%s", target_dir)
        existing = self._existing_names(target_dir)
        folder_id = self._folder_id(target_dir)

        for file_path in files:
            file_path = Path(file_path)
            if not file_path.exists():
                # 同名文件在同一批里重复出现时, 前一个已上传并删掉了本地副本,
                # 这属于"本轮已传过", 不是失败, 跳过即可 (否则会误判 failed → 整步 exit 1)
                if file_path.name in existing:
                    logger.info("本轮已上传(本地已清理), 跳过: %s", file_path.name)
                    success += 1
                else:
                    logger.warning("文件不存在: %s", file_path)
                    failed += 1
                continue

            size = file_path.stat().st_size
            logger.info("上传: %s (%.2fGB)", file_path.name, size / 1024 ** 3)

            try:
                if file_path.name in existing:
                    logger.info("OneDrive 上已存在同名文件, 跳过: %s", file_path.name)
                    if self.delete_after_upload:
                        file_path.unlink()
                    success += 1
                    continue

                self._upload_file_resumable(file_path, folder_id, size)
                logger.info("上传成功: %s", file_path.name)
                existing.add(file_path.name)   # 记入本轮已传, 后续同名重复项直接跳过
                if self.delete_after_upload:
                    file_path.unlink()
                    logger.debug("已删除本地文件: %s", file_path.name)
                success += 1
            except Exception as e:
                logger.error("上传失败: %s - %s", file_path.name, e)
                failed += 1

        return success, failed

    def _folder_id(self, dir_path: str) -> str:
        """解析目录的 driveItem id (路径寻址在上传会话上不可靠, 用 id 稳妥)"""
        _, item = self._request("GET", self._item_url(dir_path))
        return item["id"]

    def _put_chunk(self, upload_url: str, chunk: bytes, headers: dict, _retries: int = 0):
        """
        分块 PUT 到 upload session。
        ⚠️ uploadUrl 自带鉴权令牌, 绝对不能再加 Authorization 头 (加了反而 401)。
        """
        req = urllib.request.Request(upload_url, data=chunk, headers=headers, method="PUT")
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                raw = r.read()
        except urllib.error.HTTPError as e:
            status = e.code
            raw = e.read()
            if status in (429, 500, 502, 503, 504) and _retries < 5:
                wait = min(60, 2 ** _retries * 3)
                logger.warning("分块上传 HTTP %s, %ss 后重试", status, wait)
                time.sleep(wait)
                return self._put_chunk(upload_url, chunk, headers, _retries + 1)
            raise RuntimeError(f"分块上传 -> HTTP {status}: {raw.decode(errors='replace')[:200]}")
        try:
            return raw and json.loads(raw.decode()), None
        except (ValueError, UnicodeDecodeError):
            return None, raw

    def _upload_file_resumable(self, file_path: Path, folder_id: str, size: int) -> None:
        # 1. 创建 upload session (conflictBehavior=fail: 已存在则报 409)
        _, session = self._request(
            "POST",
            f"{GRAPH}/me/drive/items/{folder_id}:/{urllib.parse.quote(file_path.name)}:/createUploadSession",
            json_body={"item": {"@microsoft.graph.conflictBehavior": "fail"}},
        )
        upload_url = session["uploadUrl"]

        # 2. 分块 PUT (5MB 一块, 单块失败自动重试)
        with open(file_path, "rb") as f:
            sent = 0
            last_progress = 0
            while sent < size:
                chunk = f.read(self.chunksize)
                end = sent + len(chunk) - 1
                headers = {
                    "Content-Range": f"bytes {sent}-{end}/{size}",
                    "Content-Length": str(len(chunk)),
                }
                try:
                    resp, _raw = self._put_chunk(upload_url, chunk, headers)
                except RuntimeError as e:
                    # 416 = 服务器已收到全部字节 (最后一块重复), 视为完成
                    if "416" in str(e) and end >= size - 1:
                        break
                    raise
                sent = end + 1
                pct = int(sent * 100 / size) if size else 100
                if pct - last_progress >= 10 or pct == 100:
                    logger.info("  %s: %d%%", file_path.name, pct)
                    last_progress = pct
                if isinstance(resp, dict) and "id" in resp:
                    break  # 服务器返回 driveItem = 上传完成

    def upload_directory(self, directory) -> tuple:
        """上传整个目录"""
        directory = Path(directory)
        files = [f for f in directory.glob("*") if f.is_file()]
        return self.upload_files(files)
