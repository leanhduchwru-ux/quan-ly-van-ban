import asyncio
import os
import json
from playwright.async_api import async_playwright
from database import save_session
from dotenv import load_dotenv

load_dotenv()

SYSTEMS = [
    {
        'key': 'vpdt',
        'url': 'https://vanban.vpdt.com.vn/',
        'login_url': 'https://vanban.vpdt.com.vn/login',
        'username_env': 'VPDT_USERNAME',
        'password_env': 'VPDT_PASSWORD',
        'username_selector': 'input[type="text"]',
        'password_selector': 'input[type="password"]',
        'submit_selector': 'button, .z-button',
        'verify_selector': '.z-window-embedded, .z-label'
    },
    {
        'key': 'hpnet',
        'url': 'https://qlvb.hpnet.vn/',
        'login_url': 'https://qlvb.hpnet.vn/style/qlvb2013/Login.aspx',
        'username_env': 'HPNET_USERNAME',
        'password_env': 'HPNET_PASSWORD',
        'username_selector': '#Login1_UserName',
        'password_selector': '#Login1_Password',
        'submit_selector': '#Login1_Login',
        'verify_selector': '.user-profile, .logout-btn, a[href*="logout"]'
    }
]

async def authenticate_and_save_session(config):
    log_messages = []
    try:
        username = os.getenv(config['username_env'])
        password = os.getenv(config['password_env'])

        if not username or not password:
            return False, f"[{config['key']}] LỖI: Chưa cấu hình thông tin đăng nhập trong Secrets!"

        # Install browser binary dynamically for Streamlit Cloud
        os.system("playwright install chromium")

        async with async_playwright() as p:
            log_messages.append(f"[{config['key']}] Bắt đầu mở trình duyệt ảo...")
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(ignore_https_errors=True)
            page = await context.new_page()

            log_messages.append(f"[{config['key']}] Đang truy cập trang đăng nhập...")
            await page.goto(config['login_url'], wait_until='networkidle')

            log_messages.append(f"[{config['key']}] Đang điền tài khoản và mật khẩu...")
            await page.fill(config['username_selector'], username)
            await page.fill(config['password_selector'], password)

            log_messages.append(f"[{config['key']}] Bấm nút Đăng nhập...")
            async with page.expect_navigation(wait_until="networkidle"):
                await page.click(config['submit_selector'])

            try:
                await page.wait_for_selector(config['verify_selector'], timeout=5000)
                log_messages.append(f"[{config['key']}] Đăng nhập THÀNH CÔNG!")
            except Exception:
                log_messages.append(f"[{config['key']}] LỖI: Đăng nhập thất bại (Sai mật khẩu hoặc Selector sai).")
                await browser.close()
                return False, "\n".join(log_messages)

            # Extract cookies
            cookies = await context.cookies()
            
            # Save to Database using raw sqlite3
            save_session(config['key'], cookies)
            
            log_messages.append(f"[{config['key']}] Đã lưu Cookie phiên đăng nhập.")
            await browser.close()
            return True, "\n".join(log_messages)
            
    except Exception as e:
        return False, f"[{config['key']}] LỖI KỸ THUẬT: {e}"

async def run_crawler():
    results = []
    for sys in SYSTEMS:
        success, msg = await authenticate_and_save_session(sys)
        results.append(msg)
    return results

if __name__ == "__main__":
    asyncio.run(run_crawler())
