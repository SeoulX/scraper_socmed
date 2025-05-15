import os
import re
import time
from urllib.parse import urlparse
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# Load environment variables from .env (located one level up)
dotenv_path = os.path.join(os.path.dirname(__file__), os.pardir, '.env')
load_dotenv(dotenv_path)

# Facebook credentials
FB_EMAIL = os.getenv("FB_EMAIL")
FB_PASSWORD = os.getenv("FB_PASSWORD")
if not FB_EMAIL or not FB_PASSWORD:
    raise EnvironmentError("Missing FB_EMAIL or FB_PASSWORD in your environment variables. Please set them in your .env file.")

# Session storage paths
SESSION_DIR = os.path.join(os.path.dirname(__file__), os.pardir, "session")
SESSION_FILE = os.path.join(SESSION_DIR, "facebook_storage_state.json")

class FacebookScraper:
    def __init__(self, config=None):
        # Ensure session directory exists
        os.makedirs(SESSION_DIR, exist_ok=True)
        self.session_file = SESSION_FILE

    def scrape(self, link):
        """
        Main entry: ensures login, then scrapes page and returns dict.
        """
        return self._scrape_page(link)

    def _scrape_page(self, url):
        """
        Navigates to Facebook page, logs in if needed, scrapes metadata, posts, and comments.
        """
        parsed = urlparse(url)
        page_url = url if parsed.scheme else f"https://{url}"

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)

            # Perform login + save session if none exists
            if not os.path.exists(self.session_file):
                ctx_login = browser.new_context()
                page = ctx_login.new_page()
                page.goto("https://www.facebook.com/login")
                page.fill("input#email", FB_EMAIL)
                page.fill("input#pass", FB_PASSWORD)
                page.click("button[name='login']")
                print("🟢 Logging in to Facebook, complete any verification...")
                try:
                    page.wait_for_url("https://web.facebook.com/", timeout=60000)
                except PlaywrightTimeoutError:
                    print("⚠️ Waiting extra 30s for manual steps...")
                    time.sleep(30)
                os.makedirs(os.path.dirname(self.session_file), exist_ok=True)
                ctx_login.storage_state(path=self.session_file)
                page.close()
                print(f"✅ Saved session to {self.session_file}")

            # Create context using stored session
            context = browser.new_context(storage_state=self.session_file)
            page = context.new_page()
            page.goto(page_url)

            # Remove any login dialog
            page.evaluate("""
                const dlg = document.querySelector('div[role="dialog"]');
                if(dlg) dlg.remove();
            """)

            # Wait for main content
            page.wait_for_selector("div[role='main']", timeout=30000)
            print(f"✅ Loaded Facebook page: {page_url}")
            
            print("🔄 Scraping...", page)

            data = {"link": page_url}

            # Profile / Page name
            # Profile / Page name and nickname
            try:
                name_el = page.query_selector("h1")
                if name_el:
                    # Extract full name (first text node)
                    full_name = name_el.evaluate("node => node.childNodes[0].textContent.trim()")
                    # Extract nickname if present (last span text)
                    nick_el = page.query_selector("h1 span:last-child")
                    nickname = None
                    if nick_el:
                        raw_nick = nick_el.inner_text().strip()
                        nickname = raw_nick.strip("()\u00A0 ")
                    data["name"] = full_name
                    data["nickname"] = nickname
                else:
                    data["name"] = None
                    data["nickname"] = None
            except:
                data["name"] = None
                data["nickname"] = None
                
            try:
                cover_el = page.query_selector("img[data-imgperflogname='profileCoverPhoto']")
                data["cover_photo"] = cover_el.get_attribute('src') if cover_el else None
            except:
                data["cover_photo"] = None
            
            try:
                profile_name = data.get("name")
                selector = f"svg[aria-label=\"{profile_name}\"] image"
                profile_svg_img = page.query_selector(selector)
                if profile_svg_img:
                    data["profile_photo"] = profile_svg_img.get_attribute('xlink:href') or profile_svg_img.get_attribute('href')
                else:
                    data["profile_photo"] = None
            except:
                data["profile_photo"] = None

            try:
                count_el = page.query_selector("a[href*='/friends']:has-text('friends'), a[href*='/followers']:has-text('followers'), a[href*='/members']:has-text('members')")
                raw_text = count_el.inner_text().strip() if count_el else None
                match = re.search(r"([\d\.]+[KMkm]?)", raw_text) if raw_text else None
                data["connections_count"] = match.group(1) if match else raw_text
            except Exception as e:
                print("ERROR fetching connections count:", e)
                data["connections_count"] = None
                
            try:
                about_card = (
                    page
                    .locator("h2:has-text(\"About\")")
                    .locator("xpath=ancestor::div[contains(@class,'html-div')]")
                    .first
                )
                data["about_raw"] = about_card.inner_text().strip()
            except Exception:
                data["about_raw"] = None

            posts = []
            for _ in range(5):  # scroll iterations
                articles = page.query_selector_all("div[role='main'] div[role='article']")
                for art in articles:
                    # Content
                    try:
                        content = art.query_selector("div[dir='auto']").inner_text()
                    except:
                        content = None
                    # Timestamp
                    try:
                        ts = art.query_selector("abbr").get_attribute('title')
                    except:
                        ts = None
                    # Permalink
                    try:
                        link_el = art.query_selector("a[aria-hidden='true']")
                        permalink = link_el.get_attribute('href')
                    except:
                        permalink = None
                    # Comments
                    comps = []
                    try:
                        more = art.query_selector("div[aria-label='See more comments']")
                        if more:
                            more.click()
                            time.sleep(1)
                        cels = art.query_selector_all("div[aria-label='Comment']")
                        for c in cels:
                            try:
                                user = c.query_selector("strong").inner_text()
                                txt = c.query_selector("span[dir='auto']").inner_text()
                            except:
                                user, txt = None, None
                            comps.append({"user": user, "text": txt})
                    except:
                        pass

                    posts.append({
                        "content": content,
                        "timestamp": ts,
                        "permalink": permalink,
                        "comments": comps
                    })

                page.evaluate("window.scrollBy(0, document.body.scrollHeight)")
                time.sleep(2)

            data["posts"] = posts

            context.close()
            browser.close()

            return data