"""
Google Drive 上传器 (替代原 OneDrive/Microsoft Graph 版)

为什么换: OneDrive2 会员到期后写不进去了(实测 401), 而这条链的下游本来就指向
GoogleDrive6 的 TelegramVideos —— 直接写过去, 省掉"OneDrive2 → gd2 → gd6"两次中转。

凭证走环境变量(和原来一样只换名字):
    GD_CLIENT_ID / GD_CLIENT_SECRET / GD_REFRESH_TOKEN     (GoogleDrive6 的 OAuth)
可选:
    GDRIVE_FOLDER  目标目录名, 默认 TelegramVideos

接口与 OneDriveUploader 保持一致, 所以 main.py / workflow 只需要换 import 和类名:
    uploader = GDriveUploader(remote_dir='/TelegramVideos', delete_after_upload=True)
    uploader.test_connection() -> bool
    uploader.upload_files(files, remote_dir='TelegramVideos/某来源') -> (success, failed)

实现要点(踩过的坑都在这):
  * resumable upload 对**中间块**回的是 308 Resume Incomplete —— 这不是错误! 按它返回的
    Range 头把进度推下去继续传; 当成失败会永远传不完大文件。
  * session 过期(404/410) -> 重建 session 重传; 5xx/429 -> 退避重试。
  * 传完再回读校验字节数, 不为 0 且一致才算成功。
  * 同名同大小 -> 跳过(幂等); 文件名带中文/括号没问题(路径做 quote)。
"""
import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

TOKEN_URL = "https://oauth2.googleapis.com/token"
API = "https://www.googleapis.com/drive/v3"
UPLOAD = "https://www.googleapis.com/upload/drive/v3"
FOLDER_MIME = "application/vnd.google-apps.folder"
_CHUNK = 8 * 1024 * 1024


class GDriveUploader:
    def __init__(self, remote_dir="/TelegramVideos", delete_after_upload=True,
                 client_id=None, client_secret=None, refresh_token=None, chunk_mb=8):
        self.remote_dir = "/" + (remote_dir or "TelegramVideos").strip("/")
        self.delete_after_upload = delete_after_upload
        self.client_id = client_id or os.environ.get("GD_CLIENT_ID", "")
        self.client_secret = client_secret or os.environ.get("GD_CLIENT_SECRET", "")
        self.refresh_token = refresh_token or os.environ.get("GD_REFRESH_TOKEN", "")
        self.chunk = max(1, int(chunk_mb)) * 1024 * 1024
        self._at = ""
        self._exp = 0.0
        self._ids = {}
        self.scanned = 0
        self.skipped = 0

    # ---------------- 基础 ----------------
    def _request(self, url, method="GET", data=None, headers=None, timeout=300, raw=False):
        hdr = dict(headers or {})
        body = None
        if isinstance(data, dict):
            body = json.dumps(data).encode()
            hdr["Content-Type"] = "application/json"
        elif data is not None:
            body = data
        req = urllib.request.Request(url, data=body, headers=hdr, method=method)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            b = r.read()
        if raw:
            return b
        return json.loads(b.decode()) if b else {}

    def _token(self):
        if self._at and time.time() < self._exp - 60:
            return self._at
        if not (self.client_id and self.client_secret and self.refresh_token):
            raise RuntimeError("缺 GD_CLIENT_ID / GD_CLIENT_SECRET / GD_REFRESH_TOKEN")
        d = urllib.parse.urlencode({
            "client_id": self.client_id, "client_secret": self.client_secret,
            "refresh_token": self.refresh_token, "grant_type": "refresh_token"}).encode()
        req = urllib.request.Request(TOKEN_URL, data=d, method="POST",
                                     headers={"Content-Type": "application/x-www-form-urlencoded"})
        with urllib.request.urlopen(req, timeout=60) as r:
            j = json.loads(r.read().decode())
        self._at = j["access_token"]
        self._exp = time.time() + j.get("expires_in", 3600)
        return self._at

    def _h(self):
        return {"Authorization": "Bearer " + self._token()}

    def test_connection(self):
        try:
            d = self._request(API + "/about?fields=user,storageQuota", headers=self._h())
            q = d.get("storageQuota") or {}
            lim = int(q.get("limit") or 0)
            logger.info("Google Drive 连接 OK: %s | 已用 %.2f TB%s",
                        (d.get("user") or {}).get("emailAddress"),
                        int(q.get("usage") or 0) / 1024 ** 4,
                        (" / %.2f TB" % (lim / 1024 ** 4)) if lim else " (无上限)")
            return True
        except Exception as e:
            logger.error("Google Drive 连接失败: %s", str(e)[:200])
            return False

    # ---------------- 目录 ----------------
    def _children(self, parent_id):
        out, tok = [], ""
        while True:
            q = urllib.parse.quote("'%s' in parents and trashed=false" % parent_id)
            u = ("%s/files?q=%s&pageSize=1000&fields=nextPageToken,files(id,name,size,mimeType)"
                 "&supportsAllDrives=true&includeItemsFromAllDrives=true" % (API, q))
            if tok:
                u += "&pageToken=" + tok
            d = self._request(u, headers=self._h())
            out += d.get("files") or []
            tok = d.get("nextPageToken") or ""
            if not tok:
                return out

    def _ensure(self, name, parent_id):
        q = urllib.parse.quote("name='%s' and '%s' in parents and trashed=false and mimeType='%s'"
                               % (name.replace("'", "\\'"), parent_id, FOLDER_MIME))
        d = self._request("%s/files?q=%s&supportsAllDrives=true&fields=files(id,name)" % (API, q),
                          headers=self._h())
        if d.get("files"):
            return d["files"][0]["id"]
        d = self._request("%s/files?supportsAllDrives=true&fields=id" % API, "POST",
                          {"name": name, "mimeType": FOLDER_MIME, "parents": [parent_id]},
                          headers=self._h())
        return d["id"]

    def folder_id(self, path):
        """'TelegramVideos/我的收藏' -> 目录 id(逐段创建并缓存)"""
        key = (path or "").strip("/")
        if key in self._ids:
            return self._ids[key]
        pid, cur = self._ids.get("", "root"), ""
        if "" not in self._ids:
            self._ids[""] = "root"
        for seg in [x for x in key.split("/") if x]:
            cur = (cur + "/" + seg) if cur else seg
            if cur not in self._ids:
                self._ids[cur] = self._ensure(seg, pid)
            pid = self._ids[cur]
        return pid

    def ensure_dir(self, path):
        self.folder_id(path)

    def _existing_names(self, dir_path):
        fid = self.folder_id(dir_path)
        return {x["name"]: int(x.get("size") or 0) for x in self._children(fid)
                if x.get("mimeType") != FOLDER_MIME}

    def _find(self, path):
        parent, _, name = (path or "").rpartition("/")
        try:
            fid = self.folder_id(parent)
        except Exception:
            return None
        for x in self._children(fid):
            if x["name"] == name:
                return x
        return None

    # ---------------- 上传 ----------------
    def _new_session(self, folder_id, name):
        req = urllib.request.Request(
            "%s/files?uploadType=resumable&supportsAllDrives=true&fields=id,name,size" % UPLOAD,
            data=json.dumps({"name": name, "parents": [folder_id]}).encode(), method="POST",
            headers=dict(self._h(), **{"Content-Type": "application/json"}))
        with urllib.request.urlopen(req, timeout=300) as r:
            return r.headers.get("Location")

    def _upload_file_resumable(self, file_path, folder_id, size):
        attempts = 0
        while True:
            attempts += 1
            if attempts > 3:
                raise RuntimeError("session 反复失效, 放弃")
            sess = self._new_session(folder_id, Path(file_path).name)
            if not sess:
                raise RuntimeError("拿不到 resumable session")
            sent, done = 0, False
            with open(file_path, "rb") as f:
                while sent < size:
                    f.seek(sent)
                    buf = f.read(self.chunk)
                    if not buf:
                        break
                    hdr = {"Content-Length": str(len(buf)),
                           "Content-Range": "bytes %d-%d/%d" % (sent, sent + len(buf) - 1, size)}
                    for attempt in range(4):
                        try:
                            with urllib.request.urlopen(
                                    urllib.request.Request(sess, data=buf, method="PUT", headers=hdr),
                                    timeout=1800) as r:
                                r.read()
                            sent, done = size, True
                            break
                        except urllib.error.HTTPError as e:
                            if e.code == 308:                      # 中间块: 正常, 按服务器进度继续
                                rng = e.headers.get("Range") or ""
                                nxt = sent + len(buf)
                                if rng.startswith("bytes=0-"):
                                    try:
                                        nxt = int(rng.split("-")[1]) + 1
                                    except Exception:
                                        pass
                                sent = nxt
                                break
                            if e.code in (404, 410):               # session 没了 -> 外层重建
                                sent, done = -1, False
                                break
                            if e.code in (429, 500, 502, 503, 504):
                                time.sleep(2 * (attempt + 1))
                                continue
                            raise
                    if sent == -1:
                        break
                    if done:
                        break
            if done:
                return
            if sent >= size:
                return

    def upload_files(self, files, remote_dir=None):
        """files: 本地路径列表 -> 目标 directory。返回 (成功数, 失败数)"""
        target = ("/" + (remote_dir or self.remote_dir).strip("/"))
        folder_id = self.folder_id(target)
        existing = self._existing_names(target)
        logger.info("目标 %s 现有 %d 个文件", target, len(existing))
        ok = fail = 0
        for fp in files:
            fp = Path(fp)
            if not fp.is_file():
                logger.warning("跳过(不存在): %s", fp)
                continue
            size = fp.stat().st_size
            if size <= 1024:
                logger.warning("跳过(空/近空文件): %s (%d 字节)", fp.name, size)
                self.scanned += 1
                continue
            if existing.get(fp.name) == size:
                logger.info("跳过(目标已有同大小): %s", fp.name)
                self.scanned += 1
                self.skipped += 1
                if self.delete_after_upload:
                    fp.unlink(missing_ok=True)
                continue
            try:
                t0 = time.time()
                self._upload_file_resumable(fp, folder_id, size)
                got = self._find(target + "/" + fp.name)
                got_size = int((got or {}).get("size") or 0)
                if got_size != size:
                    raise RuntimeError("回读校验不符: 远端 %s / 本地 %s" % (got_size, size))
                el = max(time.time() - t0, 0.001)
                logger.info("✓ 上传 %s (%.1f MB, %.2f MB/s, 校验 OK)",
                            fp.name, size / 1048576, size / el / 1048576)
                existing[fp.name] = size
                ok += 1
                self.scanned += 1
                if self.delete_after_upload:
                    fp.unlink(missing_ok=True)
            except Exception as e:
                logger.error("✗ 上传失败 %s: %s", fp.name, str(e)[:200])
                fail += 1
                self.scanned += 1
        return ok, fail

    def upload_directory(self, directory):
        d = Path(directory)
        files = [p for p in d.rglob("*") if p.is_file()]
        return self.upload_files(files)
