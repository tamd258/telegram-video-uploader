# Telegram Video Uploader

批量下载 Telegram 频道/群组视频 → 自动上传到 Google Drive

## 架构

```
Telegram API (Pyrogram)
       ↓ 下载视频 (每次最多12GB, 跳过>2GB单文件)
  本地 downloads/<来源>/
       ↓ Google Drive API (OAuth 用户凭证, 用你的配额)
  Google Drive ☁️  (TelegramVideos/<来源>/)
```

## 功能

- ✅ 批量下载 Telegram 频道/群组/收藏(Saved Messages)视频
- ✅ **按来源自动分目录**：收藏 → `TelegramVideos/我的收藏/`，频道 → `TelegramVideos/<频道名>/`
- ✅ 单文件 >2GB 自动跳过
- ✅ 每轮总量达 12GB 自动停止
- ✅ 通过 Google Drive API 直接上传 (OAuth 用户凭证认证, 用你的存储配额, 支持大文件分块/断点续传)
- ✅ 文件直接进你**自己的 Google Drive** (`TelegramVideos` 文件夹, 网页立即可见)
- ✅ 上传成功自动删除本地文件
- ✅ 同名文件自动跳过 (防重复上传)
- ✅ GitHub Actions 定时/手动运行
- ✅ Session 持久化 (Secret + artifact 双保险), 无需每次登录

## GitHub Secrets 配置

在仓库 `Settings → Secrets and variables → Actions` 添加 **7 个 Secrets**：

| Secret | 说明 | 获取方式 |
|--------|------|----------|
| `TG_API_ID` | Telegram API ID（纯数字） | [my.telegram.org/apps](https://my.telegram.org/apps) → API development tools |
| `TG_API_HASH` | Telegram API Hash | 同上 |
| `TG_CHAT_IDS` | 频道/群组/收藏 ID，多个用英文逗号分隔 | 收藏填 `me`；公开频道写 `@频道名`；私有频道转发消息给 `@username_to_id_bot` 获取数字 ID |
| `TG_SESSION_STRING` | Telegram 字符串会话 (纯文本, 不用 base64) | 本地跑一次 `scripts/login.py` 登录, 把打印的字符串填进来, 见下方步骤 |
| `GDRIVE_CLIENT_ID` | Google OAuth Client ID | 见下方"获取 Google Drive OAuth 凭证"步骤 |
| `GDRIVE_CLIENT_SECRET` | Google OAuth Client Secret | 同上 |
| `GDRIVE_REFRESH_TOKEN` | Google OAuth Refresh Token | 同上 (用 `scripts/oauth_colab.py` 生成) |

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

#### 方式二: 用 Google Colab (推荐, 无需本地装任何东西)

如果本地无法连接 Telegram, 用浏览器在 Google Colab 上生成 (Google 服务器在海外, 能连 Telegram):

1. 打开 [Google Colab](https://colab.research.google.com) → 新建笔记本
2. 第一个 cell 输入并运行: `!pip install -q pyrogram tgcrypto`
3. 第二个 cell 把项目里 `scripts/login_colab.py` 的**全部内容**粘贴进去, 运行
4. 按提示输入 API ID、API Hash、手机号, 等 Telegram 验证码, 输入验证码
5. 复制打印出的 session 字符串 → 填入 Secret `TG_SESSION_STRING`

### 获取 Google Drive OAuth 凭证 (GDRIVE_CLIENT_ID / SECRET / REFRESH_TOKEN)

> ⚠️ **为什么用 OAuth 而不是 Service Account？** 个人 Google 账号的 Service Account
> **没有存储配额**，上传必报 `403 storageQuotaExceeded`。OAuth 用你自己的账号上传，
> 文件存进你的 Drive、用你的 15GB 配额，才能正常上传。

#### 1. 创建 Google Cloud 项目 & 启用 Drive API

1. 打开 [Google Cloud Console](https://console.cloud.google.com/)
2. 点击顶部项目选择器 → **新建项目** (或选择已有项目)
3. 进入 **APIs & Services → Library**，搜索 **Google Drive API**，点击 **Enable**

#### 2. 配置 OAuth 同意屏幕

1. 进入 **APIs & Services → OAuth consent screen**
2. 用户类型选 **外部 / External**，点击 **Create**
3. 填写应用名称 (如 `telegram-uploader`)、用户支持邮箱、开发者邮箱
4. 到 **Test users（测试用户）** 步骤，把**你自己的 Google 账号**添加为测试用户
5. 保存

> 💡 应用未发布时必须把自己加为测试用户，否则授权时会报"应用未验证"。

#### 3. 创建 OAuth Client ID

1. 进入 **APIs & Services → Credentials**
2. 点击 **Create Credentials → OAuth client ID**
3. 应用类型选 **桌面应用 / Desktop app**
4. 创建后复制 **Client ID** 和 **Client Secret**（下一步要用）

#### 4. 生成 Refresh Token (用 Google Colab, 本机连不上 Google 时用)

1. 打开 [Google Colab](https://colab.research.google.com) → 新建笔记本
2. 第一个 cell 运行: `!pip install -q google-api-python-client google-auth-oauthlib`
3. 第二个 cell 把项目里 `scripts/oauth_colab.py` 的**全部内容**粘贴进去, 运行
4. 按提示输入刚复制的 **Client ID** 和 **Client Secret**
5. 脚本打印一个授权链接 → **浏览器打开** → 用你自己的 Google 账号登录并授权 →
   复制页面上的 `code` 粘贴回 Colab
6. 脚本打印三个值, 分别添加为 GitHub Secret：
   - `GDRIVE_CLIENT_ID` = 你的 Client ID
   - `GDRIVE_CLIENT_SECRET` = 你的 Client Secret
   - `GDRIVE_REFRESH_TOKEN` = 打印的 refresh token

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

# 2. 配置 Google Drive OAuth 凭证 (本地运行用)
#    设置环境变量 GDRIVE_CLIENT_ID / GDRIVE_CLIENT_SECRET / GDRIVE_REFRESH_TOKEN
#    (与 GitHub Secrets 相同的值)

# 3. 运行
bash scripts/run.sh
```

## 首次运行注意事项

- ⚠️ **GitHub Actions 无法交互输入验证码**，首次运行前必须先本地跑 `scripts/login.py` 登录，把打印的字符串配置为 `TG_SESSION_STRING` Secret（见上文步骤）。字符串会话一次生成永久有效，无需每次更新。
- 上传到 Google Drive 用的是 **OAuth 用户凭证**，文件直接进**你自己的** `TelegramVideos` 文件夹（网页立即可见），用你的存储配额。
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
