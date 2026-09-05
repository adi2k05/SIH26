from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

print("Launching Stealth Browser and Playwright Inspector...")

with Stealth().use_sync(sync_playwright()) as p:
    # We use Chromium here because Stealth is highly optimized for it
    browser = p.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        viewport={"width": 1920, "height": 1080}
    )
    page = context.new_page()
    

    page.goto("https://www.spicejet.com/", timeout=60000)
    
    # 2. This command pauses the execution and opens the Playwright Inspector UI!
    page.pause()
    
    browser.close()