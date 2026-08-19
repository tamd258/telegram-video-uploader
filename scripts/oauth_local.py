#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本地生成 Google Drive OAuth Refresh Token (本机能连 Google 时使用)

比 Colab 更简单: 自动打开浏览器授权, 授权后自动回调, 无需手动复制 code。

前提:
  1. Google Cloud Console 已启用 Google Drive API
  2. 已建 OAuth 2.0 客户端 (类型: 桌面应用), 拿到 Client ID + Client Secret
  3. "OAuth 同意屏幕" 已把你的 Google 账号加为测试用户
  4. 本机已装依赖: pip install google-auth-oauthlib

用法:
  python oauth_local.py
  按提示输入 Client ID / Client Secret -> 浏览器自动打开 -> 登录授权 ->
  自动回调 -> 打印 GDRIVE_CLIENT_ID / GDRIVE_CLIENT_SECRET / GDRIVE_REFRESH_TOKEN
"""
import sys

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError:
    print("未安装 google-auth-oauthlib, 请先运行: pip install google-auth-oauthlib")
    sys.exit(1)

SCOPES = ["https://www.googleapis.com/auth/drive"]


def main():
    print("=" * 50)
    print("  Google Drive OAuth -> 生成 Refresh Token (本地)")
    print("=" * 50)

    client_id = input("\nOAuth Client ID: ").strip()
    client_secret = input("OAuth Client Secret: ").strip()
    if not client_id or not client_secret:
        print("不能为空")
        return

    flow = InstalledAppFlow.from_client_config(
        {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uris": ["http://localhost"],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=SCOPES,
    )

    print("\n正在打开浏览器, 请用你的 Google 账号登录并授权...")
    try:
        creds = flow.run_local_server(port=0)
    except Exception as e:
        print(f"自动回调失败: {e}")
        print("   若无法自动打开浏览器, 改用 scripts/oauth_colab.py (手动复制 code 模式)")
        return

    print()
    print("=" * 60)
    print("复制下面三个值, 分别填进 GitHub Secrets:")
    print("-" * 60)
    print(f"GDRIVE_CLIENT_ID     = {client_id}")
    print(f"GDRIVE_CLIENT_SECRET = {client_secret}")
    print(f"GDRIVE_REFRESH_TOKEN = {creds.refresh_token}")
    print("-" * 60)
    print("-> 仓库 Settings -> Secrets -> Actions -> 新建这三个 Secret")
    print("=" * 60)


if __name__ == "__main__":
    main()
