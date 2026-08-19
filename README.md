# Telegram Video Uploader

批量下载 Telegram 频道/群组视频 → 自动上传到 Google Drive

## 架构

```
Telegram API (Pyrogram)
       ↓ 下载视频 (每次最多12GB, 跳过>2GB单文件)
  本地 downloads/<来源>/
       ↓ Google Drive API (Service Account)
  Google Drive ☁️  (TelegramVideos/<来源>/)
```

## 功能

- ✅ 批量下载 Telegram 频道/群组/收藏(Saved Messages)视频
- ✅ **按来源自动分目录**：收藏 → `TelegramVideos/我的收藏/`，频道 → `TelegramVideos/<频道名>/`
- ✅ 单文件 >2GB 自动跳过
- ✅ 每轮总量达 12GB 自动停止
- ✅ 通过 Google Drive API 直接上传 (Service Account 认证, 支持大文件分块/断点续传)
- ✅ 上传到"共享给 SA"的文件夹 (文件直接进你的 Google Drive, 网页立即可见)
- ✅ 上传成功自动删除本地文件
- ✅ 同名文件自动跳过 (防重复上传)
- ✅ GitHub Actions 定时/手动运行
- ✅ Session 持久化 (Secret + artifact 双保险), 无需每次登录

## GitHub Secrets 配置

在仓库 `Settings → Secrets and variables → Actions` 添加 **5 个 Secrets**：

| Secret | 说明 | 获取方式 |
|--------|------|----------|
| `TG_API_ID` | Telegram API ID（纯数字） | [my.telegram.org/apps](https://my.telegram.org/apps) → API development tools |
| `TG_API_HASH` | Telegram API Hash | 同上 |
| `TG_CHAT_IDS` | 频道/群组/收藏 ID，多个用英文逗号分隔 | 收藏填 `me`；公开频道写 `@频道名`；私有频道转发消息给 `@username_to_id_bot` 获取数字 ID |
| `TG_SESSION_STRING` | Telegram 字符串会话 (纯文本, 不用 base64) | 本地跑一次 `scripts/login.py` 登录, 把打印的字符串填进来, 见下方步骤 |
| `GDRIVE_SA_B64` | Google Drive Service Account JSON (base64 编码) | 见下方详细步骤 |

### `TG_CHAT_IDS` 格式示例
```
me                              # 只拷贝收藏 (Saved Messages)
```
或
```
@channel1,-1001234567890,me     # 频道 + 私有频道 + 收藏, 逗号分隔
```

### 生成 `TG_SESSION_STRING` 详细步骤

GitHub Actions 无法交互输入手机验证码, 所以首次必须**本地登录一次**:

1. 本地安装依赖: `pip install -r requirements.txt`
2. 在**一台能正常连接 Telegram 的机器**上 (需要代理/梯子), 设置环境变量并登录 (在项目根目录执行):

```powershell
# Windows PowerShell
$env:TG_API_ID = "你的API_ID"
$env:TG_API_HASH = "你的API_HASH"
python scripts/login.py
```
```bash
# Linux / macOS
export TG_API_ID=你的API_ID
export TG_API_HASH=你的API_HASH
python scripts/login.py
```

3. 按提示输入手机号 (带国家码, 如 +8613800138000) 和 Telegram 验证码
4. 登录成功后, 终端会打印一段**纯文本字符串** (通常以 `1B` 或 `BQ` 开头, 几百字符长)
5. 把这段字符串**原样复制**, 作为 GitHub Secret `TG_SESSION_STRING` 的值 (不需要 base64, 不要加引号)

> ⚠️ 复制时要从开头到结尾**完整**复制, 漏一个字符都会导致登录失败。

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

> 💡 这一步很关键：上传时优先使用你共享给 SA 的文件夹，文件**直接进你的 Google Drive**（网页立即可见）；如果没共享，文件会落到 SA 自己的 15GB 网盘里，你网页上看不到。

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

- ⚠️ **GitHub Actions 无法交互输入验证码**，首次运行前必须先本地跑 `scripts/login.py` 登录，把打印的字符串配置为 `TG_SESSION_STRING` Secret（见上文步骤）。字符串会话一次生成永久有效，无需每次更新。
- 上传到 Google Drive 用的是 Service Account，文件会进你**共享给 SA 的** `TelegramVideos` 文件夹（网页立即可见）。
- Telegram 登录后频繁在不同 IP 登录可能触发风控，session 复用可避免此问题

## 分目录规则

上传到 Google Drive 时按来源自动分目录：

| 来源 | 本地目录 | Google Drive 目录 |
|------|---------|------------------|
| 收藏 (Saved Messages, `me`) | `downloads/我的收藏/` | `TelegramVideos/我的收藏/` |
| 频道/群组 | `downloads/<频道名或ID>/` | `TelegramVideos/<频道名或ID>/` |

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
│   ├── run.sh                              # 本地一键运行
│   └── login.py                            # 本地登录生成 session (首次必跑)
├── config/
│   ├── config.yaml.example                 # 主配置模板
│   └── gdrive_service_account.json.example # Service Account 模板 (参考)
└── requirements.txt
```
