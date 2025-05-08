import asyncio
import os
import json
from datetime import datetime
from dotenv import load_dotenv
from playwright.async_api import async_playwright

load_dotenv()

FB_EMAIL = os.getenv("FB_EMAIL")
FB_PASSWORD = os.getenv("FB_PASSWORD")


async def scrape_facebook(link: str) -> dict:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)  # Set to True for CLI-only
        context = await browser.new_context()
        page = await context.new_page()

        print("🔐 Logging in to Facebook...")
        await page.goto("https://www.facebook.com/login")
        await page.fill('input[name="email"]', FB_EMAIL)
        await page.fill('input[name="pass"]', FB_PASSWORD)  
        # Wait for a bit to ensure the page is ready
        await page.click('button[name="login"]')
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(60)
        await asyncio.sleep(2)

        print(f"🔗 Navigating to {link}...")
        await page.goto(link, timeout=60000)
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(2)

        # Scroll a few times to load more content
        for _ in range(3):
            await page.mouse.wheel(0, 2500)
            await asyncio.sleep(2)

        data = {}

        # Profile Info
        data['profile_name'] = await try_text(page, 'h1')
        data['about'] = await try_text(page, '[data-testid="info_section_container"]')

        data['profile_picture'] = await try_attr(page, 'image[alt*="Profile picture"]', 'xlink:href')
        data['cover_photo'] = await try_attr(page, 'div[data-testid="cover_photo"] img', 'src')

        data['friends_count'] = await try_text(page, 'a[href*="friends"] span')
        data['followers_count'] = await try_text(page, 'a[href*="followers"] span')

        # Posts
        print("🧾 Extracting posts and comments...")
        post_data = []
        post_blocks = await page.query_selector_all('div[data-ad-preview="message"]')

        for post_el in post_blocks[:5]:  # Limit to 5 posts
            post_text = (await post_el.text_content()) or ''
            parent = await post_el.evaluate_handle('node => node.closest("div[role=\'article\']")')
            post_images = await parent.query_selector_all('img')

            images = []
            for img in post_images:
                src = await img.get_attribute('src')
                if src and 'scontent' in src:  # filter CDN images
                    images.append(src)

            # Try to get top-level comments
            comment_texts = []
            comment_blocks = await parent.query_selector_all('div[aria-label="Comment"]')
            for c in comment_blocks[:3]:  # Limit to 3 comments per post
                t = await c.text_content()
                if t:
                    comment_texts.append(t.strip())

            post_data.append({
                "text": post_text.strip(),
                "images": images,
                "comments": comment_texts
            })

        data['posts'] = post_data
        data['scraped_at'] = datetime.now().isoformat()

        await browser.close()
        return data


async def try_text(page, selector):
    try:
        el = await page.query_selector(selector)
        if el:
            return (await el.text_content()).strip()
    except:
        return None


async def try_attr(page, selector, attr):
    try:
        el = await page.query_selector(selector)
        if el:
            return await el.get_attribute(attr)
    except:
        return None


def save_to_json(data: dict, filename: str = "facebook_scrape_output.json"):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    print(f"✅ Data saved to {filename}")


def main():
    link = input("📥 Paste the Facebook link to scrape: ").strip()
    data = asyncio.run(scrape_facebook(link))
    save_to_json(data)


if __name__ == "__main__":
    main()