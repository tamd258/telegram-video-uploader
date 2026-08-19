# Telegram Video Uploader

批量下载 Telegram 频道/群组视频 → 自动上传到 Google Drive

## 架构

```
Telegram API (Pyrogram)
       ↓ 下载视频 (每次最多12GB, 跳过>2GB单文件)
  本地 downloads/
       ↓ Google Drive API (Service Account)
  Google Drive ☁️  (文件夹: /TelegramVideos)
```

## 功能

- ✅ 批量下载 Telegram 频道/群组视频
- ✅ 单文件 >2GB 自动跳过
- ✅ 每轮总量达 12GB 自动停止
- ✅ 通过 Google Drive API 直接上传 (Service Account 认证, 支持大文件分块/断点续传)
- ✅ 上传成功自动删除本地文件
- ✅ 同名文件自动跳过 (防重复上传)
- ✅ GitHub Actions 定时/手动运行
- ✅ Session 持久化，无需每次登录

## GitHub Secrets 配置

在仓库 `Settings → Secrets and variables → Actions` 添加 **4 个 Secrets**：

| Secret | 说明 | 获取方式 |
|--------|------|----------|
| `TG_API_ID` | Telegram API ID（纯数字） | [my.telegram.org/apps](https://my.telegram.org/apps) → API development tools |
| `TG_API_HASH` | Telegram API Hash | 同上 |
| `TG_CHAT_IDS` | 频道/群组 ID，多个用英文逗号分隔 | 公开频道写 `@频道名`；私有频道转发给 `@username_to_id_bot` 获取数字 ID |
| `GDRIVE_SA_B64` | Google Drive Service Account JSON (base64 编码) | 见下方详细步骤 |

### `TG_CHAT_IDS` 格式示例
```
@channel_name
```
或
```
@channel1,@channel2,-1001234567890
```

### 获取 `GDRIVE_SA_B64` 详细步骤

#### 1. 创建 Google Cloud 项目 & 启用 Drive API

1. 打开 [Google Cloud Console](https://console.cloud.google.com/)
2. 点击顶部项目选择器 → **新建项目** (或选择已有项目)
3. 进入 **APIs & Services → Library**，搜索 **Google Drive API**，点击 **Enable**

#### 2. 创建 Service Account

1. 进入 **IAM & Admin → Service Accounts**
2. 点击 **Create Service Account**
3. 填写名称 (如 `telegram-uploader`)，点击 **Create and Continue**
4. 跳过角色分配，点击 **Done**

#### 3. 生成 JSON 密钥

1. 点击刚创建的 Service Account
2. 进入 **Keys** 标签 → **Add Key → Create new key**
3. 选择 **JSON** 格式，点击 **Create**
4. 浏览器会自动下载一个 `.json` 文件 — **这就是你的 Service Account 密钥**

#### 4. 共享 Google Drive 文件夹给 Service Account

1. 打开 [Google Drive](https://drive.google.com/)
2. 创建一个文件夹 (如 `TelegramVideos`)
3. 右键该文件夹 → **Share**
4. 粘贴 Service Account 的邮箱地址 (形如 `xxx@your-project.iam.gserviceaccount.com`，在 JSON 文件的 `client_email` 字段)
5. 权限选 **Editor**，点击 **Share**

#### 5. Base64 编码并添加为 GitHub Secret

**Linux / macOS / Git Bash:**
```bash
base64 -w 0 service-account.json
```

**Windows PowerShell:**
```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("service-account.json"))
```

复制输出的 base64 字符串，添加为 GitHub Secret `GDRIVE_SA_B64`。

## 运行

### 手动触发
`Actions → Download & Upload Telegram Videos → Run workflow`

可在 workflow 输入中指定 `max_size_gb` (下载上限) 和 `gdrive_folder` (目标文件夹)。

### 自动定时
每 6 小时自动执行（北京时间 02:00 / 08:00 / 14:00 / 20:00）

### 本地运行
```bash
# 1. 复制配置模板
cp config/config.yaml.example config/config.yaml
# 编辑 config.yaml 填入 Telegram API 信息

# 2. 放置 Service Account JSON
cp config/gdrive_service_account.json.example config/gdrive_service_account.json
# 用下载的真实 JSON 替换上面的文件

# 3. 运行
bash scripts/run.sh
```

## 首次运行注意事项

首次运行 Pyrogram 需要在 **GitHub Actions 日志**中输入手机号和 Telegram 验证码（日志可交互输入）。之后会自动保存 session，无需重复登录。

## 文件说明

```
telegram-video-uploader/
├── .github/workflows/download-upload.yml   # GitHub Actions 工作流
├── downloader/
│   ├── __init__.py
│   ├── telegram_downloader.py              # Telegram 视频下载
│   └── uploader.py                         # Google Drive API 上传
├── main.py                                 # 本地运行入口
├── scripts/
│   └── run.sh                              # 本地一键运行
├── config/
│   ├── config.yaml.example                 # 主配置模板
│   └── gdrive_service_account.json.example # Service Account 模板 (参考)
└── requirements.txt
```
