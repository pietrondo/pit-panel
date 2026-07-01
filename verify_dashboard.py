from playwright.sync_api import sync_playwright

def verify(page):
    # Log in
    page.goto("http://localhost:8000/login")
    page.fill('input[name="username"]', "admin")
    page.fill('input[name="password"]', "admin")
    page.click('button[type="submit"]')
    page.wait_for_url("http://localhost:8000/")

    # Wait for the stats to load via HTMX
    page.wait_for_selector('text=Containers')

    # Take screenshot
    page.screenshot(path="dashboard_stats.png", full_page=True)

if __name__ == "__main__":
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        try:
            verify(page)
            print("Screenshot saved to dashboard_stats.png")
        finally:
            browser.close()
