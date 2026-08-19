"""
本地登录 Telegram 生成 session 文件 (供 GitHub Actions 使用)

GitHub Actions 无法交互输入验证码, 所以首次必须本地登录一次,
把生成的 downloader.session 文件 base64 后存为 GitHub Secret: TG_SESSION_B64

用法 (Windows PowerShell):
    $env:TG_API_ID = "12345678"
    $env:TG_API_HASH = "你的api_hash"
    python scripts/login.py

用法 (Linux / macOS):
    export TG_API_ID=12345678
    export TG_API_HASH=你的api_hash
    python scripts/login.py

登录成功后当前目录会生成 downloader.session 文件,
base64 编码后添加为 GitHub Secret: TG_SESSION_B64
"""
import asyncio
import os

from pyrogram import Client


async def main():
    api_id = int(os.environ["TG_API_ID"])
    api_hash = os.environ["TG_API_HASH"]

    print("按提示输入手机号 (带国家码, 如 +8613800138000) 和 Telegram 验证码...")
    async with Client("downloader", api_id=api_id, api_hash=api_hash) as client:
        me = await client.get_me()
        name = me.first_name or me.username or str(me.id)
        print(f"✅ 登录成功: {name}")
        print()
        print("session 文件已生成: downloader.session")
        print("下一步: base64 编码后添加为 GitHub Secret TG_SESSION_B64")
        print("  Windows PowerShell:")
        print('  [Convert]::ToBase64String([IO.File]::ReadAllBytes("downloader.session"))')
        print("  Linux / macOS:")
        print("  base64 -w 0 downloader.session")


if __name__ == "__main__":
    asyncio.run(main())
