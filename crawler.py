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
        'username_selector': 'input[name="username"]',
        'password_selector': 'input[name="password"]',
        'submit_selector': 'button[type="submit"]',
        'verify_selector': '.user-profile, .logout-btn'
    },
    {
        'key': 'hpnet',
        'url': 'https://qlvb.hpnet.vn/',
        'login_url': 'https://qlvb.hpnet.vn/style/qlvb2013/Login.aspx',
        'username_env': 'HPNET_USERNAME',
        'password_env': 'HPNET_PASSWORD',
        'username_selector': 'input[name="username"]',
        'password_selector': 'input[name="password"]',
        'submit_selector': 'button[type="submit"]',
        'verify_selector': '.user-profile, .logout-btn'
    }
]

async def authenticate_and_save_session(config):
    try:
        username = os.getenv(config['username_env'])
        password = os.getenv(config['password_env'])

        if not username or not password:
            print(f"[{config['key']}] Missing credentials in .env or secrets.")
            return False

        async with async_playwright() as p:
            print(f"[{config['key']}] Starting browser...")
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()

            print(f"[{config['key']}] Navigating to login page...")
            await page.goto(config['login_url'], wait_until='networkidle')

            print(f"[{config['key']}] Filling credentials...")
            await page.fill(config['username_selector'], username)
            await page.fill(config['password_selector'], password)

            print(f"[{config['key']}] Submitting...")
            async with page.expect_navigation(wait_until="networkidle"):
                await page.click(config['submit_selector'])

            try:
                await page.wait_for_selector(config['verify_selector'], timeout=5000)
                print(f"[{config['key']}] Login successful!")
            except Exception:
                print(f"[{config['key']}] Login failed: could not find verification selector.")
                await browser.close()
                return False

            # Extract cookies
            cookies = await context.cookies()
            
            # Save to Database using raw sqlite3
            save_session(config['key'], cookies)
            
            print(f"[{config['key']}] Session saved to database.")
            await browser.close()
            return True
            
    except Exception as e:
        print(f"[{config['key']}] Authentication error: {e}")
        return False

async def run_crawler():
    print("--- Bắt đầu tiến trình Crawler Python ---")
    for sys in SYSTEMS:
        await authenticate_and_save_session(sys)
    print("--- Crawler Hoàn tất ---")

if __name__ == "__main__":
    asyncio.run(run_crawler())
