# Telegram Video Uploader

批量下载 Telegram 频道/群组视频 → 自动上传到中国移动云盘

## 架构

```
Telegram API (Pyrogram)
       ↓ 下载视频 (每次最多12GB, 跳过>2GB单文件)
  本地 downloads/
       ↓ rclone WebDAV
  alist (localhost:5244)
       ↓ 中国移动云盘 API
  中国移动云盘 ☁️  (目录: /aaa)
```

## 功能

- ✅ 批量下载 Telegram 频道/群组视频
- ✅ 单文件 >2GB 自动跳过
- ✅ 每轮总量达 12GB 自动停止
- ✅ 通过 alist + rclone 上传到中国移动云盘 `/aaa` 目录
- ✅ 上传成功自动删除本地文件
- ✅ GitHub Actions 定时/手动运行
- ✅ Session 持久化，无需每次登录

## GitHub Secrets 配置

在仓库 `Settings → Secrets and variables → Actions` 添加 **5 个 Secrets**：

| Secret | 说明 | 获取方式 |
|--------|------|----------|
| `TG_API_ID` | Telegram API ID（纯数字） | [my.telegram.org/apps](https://my.telegram.org/apps) → API development tools |
| `TG_API_HASH` | Telegram API Hash | 同上 |
| `TG_CHAT_IDS` | 频道/群组 ID，多个用英文逗号分隔 | 公开频道写 `@频道名`；私有频道转发给 `@username_to_id_bot` 获取数字 ID |
| `MCLOUD_AUTHORIZATION` | 移动云盘 Authorization 令牌 | yun.139.com → F12 → Network → 搜索 `hcy/file/list` → 请求头 `Authorization: Basic xxx` 中 `Basic ` **后面的部分** |
| `ALIST_ADMIN_PASSWORD` | alist 管理员密码 | 自定义 |

### `TG_CHAT_IDS` 格式示例
```
@channel_name
```
或
```
@channel1,@channel2,-1001234567890
```

### 获取 `MCLOUD_AUTHORIZATION` 详细步骤

1. 电脑浏览器打开 [yun.139.com](https://yun.139.com/) 并登录
2. 按 `F12` → 切换到 `Network（网络）` 标签
3. 筛选框输入 `hcy/file/list`
4. 刷新页面（F5），点击 `hcy/file/list` 请求
5. 右侧 Request Headers 找到 `Authorization: Basic xxxxx`
6. 复制 **`Basic ` 后面的全部内容**（不含 `Basic ` 前缀）

## 运行

### 手动触发
`Actions → Download & Upload Telegram Videos → Run workflow`

### 自动定时
每 6 小时自动执行（北京时间 02:00 / 08:00 / 14:00 / 20:00）

### 本地运行
```bash
pip install -r requirements.txt
# 手动配置 alist + rclone
bash scripts/run.sh
```

## 首次运行注意事项

首次运行 Pyrogram 需要在 **GitHub Actions 日志**中输入手机号和 Telegram 验证码（日志可交互输入）。之后会自动保存 session，无需重复登录。

## 文件说明

```
telegram-video-uploader/
├── .github/workflows/download-upload.yml  # GitHub Actions 工作流
├── downloader/
│   ├── __init__.py
│   ├── telegram_downloader.py   # Telegram 视频下载
│   └── uploader.py              # rclone 上传
├── main.py                      # 本地运行入口
├── scripts/
│   ├── setup_alist.sh           # alist 环境初始化
│   └── run.sh                   # 本地一键运行
├── config/
│   ├── config.yaml.example      # 主配置模板
│   ├── alist_config.json.example # alist 配置模板
│   └── rclone.conf.example      # rclone 配置模板
└── requirements.txt
```
