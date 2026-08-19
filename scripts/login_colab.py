#!/ -*- coding: utf-8 -*-
"""
Google Colab / Jupyter 专用 Telegram 登录脚本

这台 WorkBuddy 机器连不上 Telegram, 所以用 Google Colab (在浏览器里跑,
Google 服务器在海外能连 Telegram) 来生成 session string。

使用方法:
  1. 打开 https://colab.research.google.com → 新建笔记本 (New notebook)
  2. 第一个 cell 粘贴并运行:
     !pip install -q pyrogram tgcrypto
  3. 第二个 cell 粘贴本文件全部内容, 运行
  4. 按提示输入 API ID / API Hash / 手机号 / 验证码
  5. 复制打印出的 session 字符串 → GitHub Secret TG_SESSION_STRING
"""
import asyncio
import os
import sys

# Colab 环境检测
def is_colab():
    try:
        import google.colab
        return True
    except ImportError:
        return False

# 安装依赖 (Colab 里 cell 1 用 !pip 安装; 这里做兜底)
try:
    from pyrogram import Client
except ImportError:
    print("⚠️ 未安装 pyrogram, 请先在上方 cell 运行: !pip install pyrogram tgcrypto")
    sys.exit(1)


def get_input(prompt: str) -> str:
    """Colab 兼容的 input (同步, 不阻塞 async 事件循环)"""
    if is_colab():
        try:
            import google.colab.input
            return google.colab.input.input(prompt)
        except Exception:
            pass
    return input(prompt)


async def main():
    print("=" * 50)
    print("  Telegram 登录 → 生成 Session String")
    print("=" * 50)

    # 1. 收集 API 凭证
    api_id_str = get_input("\n📝 Telegram API ID (纯数字, 如 31029219): ").strip()
    api_hash = get_input("📝 Telegram API Hash (32位十六进制): ").strip()
    phone = get_input("📝 手机号 (带国家码, 如 +8613800138000): ").strip()

    if not api_id_str or not api_hash or not phone:
        print("❌ 不能为空")
        return

    api_id = int(api_id_str)

    print(f"\n⏳ 正在连接 Telegram, 请等待验证码...")
    print(f"   (验证码会发到你的 Telegram APP)")

    # 2. 用 phone_number 预设, 避免 Pyrogram 第一步 ainput 卡住
    #    验证码那步 Pyrogram 会调 ainput, 在 Colab 里能正常弹输入框
    async with Client(
        "colab_login",
        api_id=api_id,
        api_hash=api_hash,
        phone_number=phone,
    ) as client:
        me = await client.get_me()
        name = me.first_name or me.username or str(me.id)
        print(f"\n✅ 登录成功! 用户: {name}")

        # 3. 导出 session string
        session_string = await client.export_session_string()

        print()
        print("=" * 60)
        print("🎉 复制下面这一整段字符串 (以 1B 或 BQ 开头, 不含引号):")
        print("-" * 60)
        print(session_string)
        print("-" * 60)
        print("→ 去 GitHub 仓库 Settings → Secrets → Actions")
        print("→ 新建 TG_SESSION_STRING = 上面这段字符串")
        print("→ (旧名 TG_SESSION_B64 如果还在就删掉)")
        print("=" * 60)


# Colab 里 asyncio.run() 可能在已有事件循环时报错, 用兜底
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except RuntimeError:
        # 已有事件循环 (Colab 某些版本)
        import nest_asyncio
        nest_asyncio.apply()
        asyncio.get_event_loop().run_until_complete(main())
