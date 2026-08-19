"""
本地登录 Telegram 生成「字符串会话」(StringSession), 供 GitHub Actions 使用

GitHub Actions 无法交互输入验证码, 所以必须本地登录一次。
登录成功后会打印一段纯文本字符串 (通常以 1B / BQ 开头),
把它作为 GitHub Secret: TG_SESSION_STRING 的值即可 (不需要 base64)。

用法 (Windows PowerShell):
    $env:TG_API_ID = "12345678"
    $env:TG_API_HASH = "你的api_hash"
    python scripts/login.py

用法 (Linux / macOS):
    export TG_API_ID=12345678
    export TG_API_HASH=你的api_hash
    python scripts/login.py

⚠️ 必须在一台能正常连接 Telegram 的机器上运行 (需要代理/梯子)。
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

        # 导出字符串会话 (纯文本, 跨机器可用)
        session_string = await client.export_session_string()

        print("=" * 60)
        print("复制下面这一整段字符串 (从 1B 或 BQ 开头到结尾, 不含引号):")
        print("-" * 60)
        print(session_string)
        print("-" * 60)
        print("把它作为 GitHub Secret: TG_SESSION_STRING 的值")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
