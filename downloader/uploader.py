"""
将下载目录的视频通过 alist WebDAV + rclone 上传到中国移动云盘
"""
import subprocess
import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

# alist 默认 WebDAV 地址
ALIST_WEBDAV_URL = "http://localhost:5244/dav"
# rclone 默认配置路径 (与 GitHub Actions 中 setup rclone 步骤一致)
DEFAULT_RCLONE_CONFIG = str(Path.home() / ".config" / "rclone" / "rclone.conf")


class RcloneUploader:
    """通过 rclone + alist WebDAV 上传到移动云盘"""

    def __init__(
        self,
        remote_name: str = "mcloud",
        remote_dir: str = "/aaa",
        rclone_config: str = None,
        delete_after_upload: bool = True,
    ):
        self.remote_name = remote_name
        self.remote_dir = remote_dir
        self.rclone_config = Path(rclone_config or DEFAULT_RCLONE_CONFIG)
        self.delete_after_upload = delete_after_upload

    def _rclone(self, *args) -> subprocess.CompletedProcess:
        """运行 rclone 命令"""
        cmd = [
            "rclone",
            f"--config={self.rclone_config}",
            *args,
        ]
        logger.debug(f"执行: {' '.join(cmd)}")
        return subprocess.run(cmd, capture_output=True, text=True, timeout=3600)

    def test_connection(self) -> bool:
        """测试与 alist WebDAV 的连接"""
        result = self._rclone("lsd", f"{self.remote_name}:")
        if result.returncode == 0:
            logger.info("rclone 连接 alist WebDAV 成功")
            return True
        else:
            logger.error(f"rclone 连接失败: {result.stderr}")
            return False

    def upload_files(self, files: list[Path]) -> tuple[int, int]:
        """
        上传文件列表到云盘
        返回 (成功数, 失败数)
        """
        success = 0
        failed = 0
        dest = f"{self.remote_name}:{self.remote_dir}"

        # 确保远程目录存在
        self._rclone("mkdir", dest)

        for file_path in files:
            if not file_path.exists():
                logger.warning(f"文件不存在: {file_path}")
                failed += 1
                continue

            file_size_gb = file_path.stat().st_size / (1024 ** 3)
            logger.info(f"上传: {file_path.name} ({file_size_gb:.2f}GB)")

            try:
                result = self._rclone(
                    "copy",
                    str(file_path),
                    dest,
                    "--progress",
                    "--transfers=2",
                )
                if result.returncode == 0:
                    logger.info(f"上传成功: {file_path.name}")
                    success += 1
                    if self.delete_after_upload:
                        file_path.unlink()
                        logger.debug(f"已删除本地文件: {file_path.name}")
                else:
                    logger.error(f"上传失败: {file_path.name} - {result.stderr}")
                    failed += 1
            except Exception as e:
                logger.error(f"上传异常: {file_path.name} - {e}")
                failed += 1

        return success, failed

    def upload_directory(self, directory: Path) -> tuple[int, int]:
        """上传整个目录"""
        files = list(directory.glob("*"))
        files = [f for f in files if f.is_file()]
        return self.upload_files(files)


def setup_rclone_for_alist(rclone_config_path: str, alist_url: str = ALIST_WEBDAV_URL):
    """配置 rclone 连接 alist WebDAV"""
    config_content = f"""[mcloud]
type = webdav
url = {alist_url}
vendor = other
user = admin
pass = admin
"""
    path = Path(rclone_config_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(config_content)
    logger.info(f"rclone 配置已写入: {rclone_config_path}")
