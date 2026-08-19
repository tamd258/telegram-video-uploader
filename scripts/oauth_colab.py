# -*- coding: utf-8 -*-
"""
Google Colab 专用: 生成 Google Drive OAuth Refresh Token

因为 WorkBuddy 机器连不上 Google, 用 Colab (Google 海外服务器) 在浏览器里完成
OAuth 授权, 拿到 refresh_token 后填进 GitHub Secret。

使用方法:
  1. 打开 https://colab.research.google.com → 新建笔记本
  2. 第一个 cell 运行: !pip install -q google-api-python-client google-auth-oauthlib
  3. 第二个 cell 粘贴本文件全部内容, 运行
  4. 按提示输入:
     - OAuth Client ID (从 Google Cloud Console 的 OAuth 2.0 Client ID 复制)
     - OAuth Client Secret
  5. 脚本打印一个授权链接 → 浏览器打开 → 用你的 Google 账号登录授权 →
     复制页面上的 code 粘贴回 Colab
  6. 脚本打印 GDRIVE_CLIENT_ID / GDRIVE_CLIENT_SECRET / GDRIVE_REFRESH_TOKEN
     → 复制这三个值, 分别填进 GitHub Secrets

前置条件 (Google Cloud Console):
  - 已启用 Google Drive API
  - 已创建 OAuth 2.0 Client ID (类型选"桌面应用 / Desktop app")
  - "OAuth 同意屏幕"中已把自己的 Google 账号加为"测试用户"
    (应用未发布时必需, 否则授权会报"应用未验证")
"""
import sys

try:
    from google_auth_oauthlib.flow import Flow
except ImportError:
    print("⚠️ 未安装 google-auth-oauthlib, 请先在上方 cell 运行:")
    print("   !pip install -q google-api-python-client google-auth-oauthlib")
    sys.exit(1)


def get_input(prompt):
    try:
        import google.colab.input
        return google.colab.input.input(prompt)
    except Exception:
        return input(prompt)


def main():
    print("=" * 50)
    print("  Google Drive OAuth → 生成 Refresh Token")
    print("=" * 50)

    client_id = get_input("\n📝 OAuth Client ID: ").strip()
    client_secret = get_input("📝 OAuth Client Secret: ").strip()
    if not client_id or not client_secret:
        print("❌ 不能为空")
        return

    SCOPES = ["https://www.googleapis.com/auth/drive"]

    flow = Flow.from_client_config(
        {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=SCOPES,
    )

    auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")
    print("\n🌐 打开下面链接, 用你的 Google 账号登录并授权:")
    print("-" * 60)
    print(auth_url)
    print("-" * 60)

    code = get_input("📝 授权后复制页面上的 code 粘贴到这里: ").strip()
    if not code:
        print("❌ code 为空")
        return

    flow.fetch_token(code=code)
    creds = flow.credentials

    print()
    print("=" * 60)
    print("🎉 复制下面三个值, 分别填进 GitHub Secrets:")
    print("-" * 60)
    print(f"GDRIVE_CLIENT_ID     = {client_id}")
    print(f"GDRIVE_CLIENT_SECRET = {client_secret}")
    print(f"GDRIVE_REFRESH_TOKEN = {creds.refresh_token}")
    print("-" * 60)
    print("→ 仓库 Settings → Secrets → Actions")
    print("→ 新建这三个 Secret (名称严格照抄, 区分大小写)")
    print("=" * 60)


if __name__ == "__main__":
    main()
