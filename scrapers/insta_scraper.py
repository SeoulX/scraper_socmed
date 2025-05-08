import os
import json
import time
import re
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# Load environment variables
load_dotenv()
INST_USERNAME = os.getenv("INSTAGRAM_USERNAME")
INST_PASSWORD = os.getenv("INSTAGRAM_PASSWORD")
# Store session file in a dedicated directory
SESSION_DIR = os.path.join(os.path.dirname(__file__), os.pardir, "session")
SESSION_FILE = os.path.join(SESSION_DIR, "instagram_storage_state.json")
LOGIN_URL = "https://www.instagram.com/accounts/login/"
PROFILE_URL_TEMPLATE = "https://www.instagram.com/{username}/"

class InstagramScraper:
    def __init__(self, config):
        # config is unused for Instagram; credentials come from .env
        # Ensure session directory exists
        os.makedirs(SESSION_DIR, exist_ok=True)
        self.session_file = SESSION_FILE

    def scrape(self, link):
        """
        Entry point matching scraper interface: accepts profile URL and returns scraped data.
        """
        username = self.extract_username(link)
        return self.scrape_profile(username)

    def save_session(self):
        """
        Manual login flow to generate and save session state.
        """
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            context = browser.new_context()
            page = context.new_page()
            page.goto(LOGIN_URL)
            page.wait_for_selector("input[name='username']", timeout=15000)
            page.fill("input[name='username']", INST_USERNAME)
            page.fill("input[name='password']", INST_PASSWORD)
            page.click("button[type='submit']")
            print("🟢 Logging in, complete any CAPTCHA if prompted...")
            try:
                page.wait_for_url("https://www.instagram.com/*", timeout=30000)
            except PlaywrightTimeoutError:
                print("⚠️ Additional login steps required, waiting 30s...")
                time.sleep(30)
            # Ensure session directory exists
            os.makedirs(os.path.dirname(self.session_file), exist_ok=True)
            context.storage_state(path=self.session_file)
            print(f"✅ Instagram session saved to {self.session_file}")
            browser.close()

    def _get_context(self, playwright):
        """
        Return a browser context with stored session or perform fresh login.
        """
        browser = playwright.chromium.launch(headless=False)
        if os.path.exists(self.session_file):
            context = browser.new_context(storage_state=self.session_file)
        else:
            context = browser.new_context()
            page = context.new_page()
            page.goto(LOGIN_URL)
            page.wait_for_selector("input[name='username']")
            page.fill("input[name='username']", INST_USERNAME)
            page.fill("input[name='password']", INST_PASSWORD)
            page.click("button[type='submit']")
            print("🟢 Performing initial Instagram login...")
            try:
                page.wait_for_url("https://www.instagram.com/*", timeout=30000)
            except PlaywrightTimeoutError:
                print("⚠️ Additional login steps required, waiting 30s...")
                time.sleep(30)
            # Ensure session directory exists
            os.makedirs(os.path.dirname(self.session_file), exist_ok=True)
            context.storage_state(path=self.session_file)
            print(f"✅ Instagram session state saved to {self.session_file}")
        return context

    def scrape_profile(self, username, post_limit=5):
        """
        Navigate to the user profile, extract bio, stats, and recent post URLs.
        """
        with sync_playwright() as p:
            context = self._get_context(p)
            page = context.new_page()
            profile_url = PROFILE_URL_TEMPLATE.format(username=username)
            page.goto(profile_url)
            page.wait_for_selector("header", timeout=15000)
            print(f"✅ Loaded Instagram profile: {username}")
            data = {"username": username}
            # Full name
            try:
                data["full_name"] = page.query_selector("header section div h1").inner_text().strip()
            except:
                data["full_name"] = None
            # Stats: posts, followers, following
            try:
                stats = page.query_selector_all("header li span span")
                data["posts_count"] = stats[0].inner_text().replace(',', '')
                data["followers_count"] = stats[1].get_attribute('title') or stats[1].inner_text()
                data["following_count"] = stats[2].inner_text()
            except:
                data.update({"posts_count": None, "followers_count": None, "following_count": None})
            # Bio
            try:
                data["bio"] = page.query_selector("header section div span").inner_text().strip()
            except:
                data["bio"] = None
            # Recent posts (with cookie acceptance and bounded scrolling)
            # Accept cookie banner if present
            try:
                page.click("button:has-text('Accept All')", timeout=5000)
                page.wait_for_timeout(2000)
            except:
                pass
            post_urls = set()
            scroll_attempts = 0
            max_scroll_attempts = 5
            while len(post_urls) < post_limit and scroll_attempts < max_scroll_attempts:
                thumbs = page.query_selector_all("article a[href^='/']")
                for thumb in thumbs:
                    href = thumb.get_attribute('href')
                    if href and href.startswith("/"):
                        post_urls.add(f"https://www.instagram.com{href}")
                        if len(post_urls) >= post_limit:
                            break
                # Scroll down
                page.evaluate("window.scrollBy(0, document.body.scrollHeight)")
                time.sleep(2)
                scroll_attempts += 1
            if not post_urls:
                print("⚠️ No posts found. You may need to check your login/session or selectors.")
            data["recent_posts"] = list(post_urls)[:post_limit][:post_limit]
            context.close()
            return data

    @staticmethod
    def extract_username(url):
        """
        Extract Instagram username from profile URL.
        """
        match = re.search(r"instagram\.com/([^/]+)/?", url)
        if match:
            return match.group(1)
        raise ValueError(f"Invalid Instagram profile URL: {url}")
