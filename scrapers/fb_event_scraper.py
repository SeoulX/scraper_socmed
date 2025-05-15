# ✅ scrapers/fb_event_scraper.py (Async Implementation Fixes)
import os
import time
import re
import asyncio
from urllib.parse import urlparse
from dotenv import load_dotenv
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

# Load environment variables
dotenv_path = os.path.join(os.path.dirname(__file__), os.pardir, '.env')
load_dotenv(dotenv_path)

FB_EMAIL = os.getenv("FB_EMAIL")
FB_PASSWORD = os.getenv("FB_PASSWORD")
SESSION_DIR = os.path.join(os.path.dirname(__file__), os.pardir, "session")
SESSION_FILE = os.path.join(SESSION_DIR, "facebook_storage_state.json")

class FacebookEventScraper:
    def __init__(self, config=None):
        os.makedirs(SESSION_DIR, exist_ok=True)
        self.session_file = SESSION_FILE
        self.headless = config.get("facebook", {}).get("headless") if config else True

    async def _login_async(self, p):
        browser = await p.chromium.launch(headless=self.headless)
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto("https://www.facebook.com/login")
        await page.fill("input#email", FB_EMAIL)
        await page.fill("input#pass", FB_PASSWORD)
        await page.click("button[name='login']")
        print("🟢 Logging in...")
        try:
            await page.wait_for_url("https://www.facebook.com/", timeout=60000)
        except PlaywrightTimeoutError:
            print("⚠️ Extra wait for 2FA...")
            await asyncio.sleep(30)
        await context.storage_state(path=self.session_file)
        await browser.close()

    async def scrape_event_async(self, p, url):
        parsed = urlparse(url)
        page_url = url if parsed.scheme else f"https://{url}"

        # Launch a browser and context
        browser = await p.chromium.launch(headless=self.headless)
        context = await browser.new_context(storage_state=self.session_file)
        page = await context.new_page()

        # Navigate and wait
        await page.goto(page_url)
        await page.wait_for_selector("div[role='main']", timeout=30000)
        print(f"✅ Loaded event page: {page_url}")

        data = {"link": page_url}
        try:
            # Target the innermost span with class html-span under h1
            span = await page.query_selector("h1 span.html-span")
            if span:
                print("1st attempt to get event name")
                name = await span.inner_text()
                data["event_name"] = name.strip()
            else:
                # fallback: strip h1 inner_html
                h1 = await page.query_selector("h1")
                print("2nd attempt to get event name")
                html = await h1.inner_html()
                html = re.sub(r'<img [^>]*alt=\"([^\"]+)\"[^>]*>', r'\1', html)
                text = re.sub(r'<[^>]+>', '', html).strip()
                data["event_name"] = text if text.lower() != "events" else None
        except Exception as e:
            print("⚠️ Failed to extract event name:", e)
            data["event_name"] = None
        
        try:
            spans = await page.query_selector_all("span[dir='auto']")
            date_text = None
            for s in spans:
                txt = (await s.inner_text()).strip()
                # Format: 'Thursday, September 4, 2025 at 9:30 AM PST'
                if re.match(r"^[A-Za-z]+, [A-Za-z]+ \d{1,2}, \d{4} at .+", txt):
                    date_text = txt
                    break
                # Format: 'May 24 at 11 PM – May 26 at 5 AM PST'
                if re.match(r"^[A-Za-z]+ \d{1,2} at .+ – [A-Za-z]+ \d{1,2} at .+", txt):
                    date_text = txt
                    break
            data["event_datetime"] = date_text
        except Exception as e:
            print("⚠️ Failed to extract datetime:", e)
            data["event_datetime"] = None
        
         # Extract responses count (e.g., '31.8K people responded')
        try:
            resp = None
            for s in spans:
                txt = (await s.inner_text()).strip()
                if re.search(r"people responded", txt):
                    resp = txt
                    break
            data["responses_count"] = resp
        except Exception as e:
            print("⚠️ Failed to extract responses_count:", e)
            data["responses_count"] = None

        # Extract organizer (Event by ...)
        try:
            org_name = None
            org_url = None
            for s in spans:
                text = (await s.inner_text()).strip()
                if text.startswith("Event by"):
                    # find link inside this span
                    a = await s.query_selector("a")
                    if a:
                        org_name = await a.inner_text()
                        org_url = await a.get_attribute("href")
                    break
            data["organizer_name"] = org_name
            data["organizer_url"] = org_url
        except Exception as e:
            print("⚠️ Failed to extract organizer:", e)
            data["organizer_name"] = None
            data["organizer_url"] = None

        try:
            venue_el = await page.query_selector("div[role='listitem'] span[dir='auto'] div[role='button']")
            if venue_el:
                data["venue_name"] = (await venue_el.inner_text()).strip()
            else:
                data["venue_name"] = None
        except Exception as e:
            print("⚠️ Failed to extract venue:", e)
            data["venue_name"] = None

        # Extract tickets info (span after div with 'Tickets')
        try:
            ticket_elem = await page.query_selector("a[aria-label='Find tickets for this event']")
            if ticket_elem:
                ticket_url = await ticket_elem.get_attribute("href")
                data["tickets_url"] = ticket_url
                # optionally get the link text or nested span text
                ticket_text = (await ticket_elem.inner_text()).strip()
                data["tickets_info"] = ticket_text
            else:
                data["tickets_url"] = None
                data["tickets_info"] = None
        except Exception as e:
            print("⚠️ Failed to extract tickets info:", e)
            data["tickets_url"] = None
            data["tickets_info"] = None

        # Clean up
        await context.close()
        await browser.close()
        return data

    async def scrape_discovery_events(self, limit=10):
        events = []
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)

            # Ensure logged in
            if not os.path.exists(self.session_file):
                await self._login_async(p)

            context = await browser.new_context(storage_state=self.session_file)
            page = await context.new_page()
            await page.goto("https://www.facebook.com/events/discovery/")
            await page.wait_for_selector("div[role='main']", timeout=30000)
            print("🔄 Scrolling to load events...")

            for _ in range(3):
                await page.mouse.wheel(0, 3000)
                await asyncio.sleep(2)

            links = await page.eval_on_selector_all(
                "a[href*='/events/']", "els => els.map(e => e.href)"
            )
            # Filter only direct event pages
            event_links = [ln for ln in set(links)
                           if re.search(r"/events/\d{5,20}(?:/|\?|$)", ln)]
            print("✅ Filtered event links:", event_links)
            print(f"🔗 Found {len(event_links)} unique event links.")
            limitation = len(event_links)

            for link in event_links[:limitation]:
                try:
                    data = await self.scrape_event_async(p, link)
                    events.append(data)
                except Exception as e:
                    print(f"❌ Failed to scrape {link}: {e}")

            await context.close()
            await browser.close()
        return events