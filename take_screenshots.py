#!/usr/bin/env python3
"""Take screenshots of the Shrimpicus web app pages."""

from playwright.sync_api import sync_playwright
import time

def take_screenshots():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = context.new_page()

        print("📸 Taking screenshots...")

        # Navigate to login page
        page.goto("http://127.0.0.1:5005/login")
        time.sleep(1)
        page.screenshot(path="docs/screenshots/login.png", full_page=True)
        print("✓ Captured login page")

        # Login as testuser123
        page.fill('input[name="username"]', 'testuser123')
        page.fill('input[name="password"]', 'Test1234!')
        page.click('button[type="submit"]')
        time.sleep(1)

        # Capture board page
        page.goto("http://127.0.0.1:5005/board")
        time.sleep(1)
        page.screenshot(path="docs/screenshots/board.png", full_page=True)
        print("✓ Captured board page")

        # Capture habits page
        page.goto("http://127.0.0.1:5005/habits")
        time.sleep(1)
        page.screenshot(path="docs/screenshots/habits.png", full_page=True)
        print("✓ Captured habits page")

        # Capture social page if it exists
        try:
            page.goto("http://127.0.0.1:5005/social")
            time.sleep(1)
            page.screenshot(path="docs/screenshots/social.png", full_page=True)
            print("✓ Captured social page")
        except:
            print("⚠ Social page not available")

        browser.close()
        print("\n✅ All screenshots saved to docs/screenshots/")

if __name__ == "__main__":
    take_screenshots()
