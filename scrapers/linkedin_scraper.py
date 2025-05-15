import re
import os
import asyncio
import random
from TikTokApi import TikTokApi
from playwright.async_api import async_playwright  # async version

class LinkedInScraper:
    def __init__(self, config=None):
        self.browser = os.environ.get("TIKTOK_BROWSER", "chromium")
        self.ms_token = None

    def scrape(self, link):
        return asyncio.run(self.scrape_async(link))

    async def manual_login_and_get_token(self):
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            context = await browser.new_context()
            page = await context.new_page()
            await page.goto("https://www.tiktok.com/login/phone-or-email/email")

            print("🔐 Please log in manually.")
            await asyncio.sleep(60)  # wait 60 sec for login

            cookies = await context.cookies()
            for cookie in cookies:
                if cookie["name"] == "msToken":
                    self.ms_token = cookie["value"]
                    print("✅ ms_token retrieved from same session.")
                    break

            await browser.close()

        if not self.ms_token:
            raise RuntimeError("❌ ms_token not found. Login failed or session expired.")

    async def scrape_async(self, link):
        if not self.ms_token:
            await self.manual_login_and_get_token()

        async with TikTokApi() as api:
            await api.create_sessions(
                ms_tokens=[self.ms_token],
                num_sessions=1,
                sleep_after=3,
                headless=False,
                browser=self.browser
            )

            if "/@" in link:
                username = self.extract_username(link)
                user = api.user(username=username)
                return await self._get_user_profile_and_videos(api, user)

            elif "/video/" in link:
                video = api.video(url=link)
                return await self._get_video_with_comments(video)

            else:
                raise ValueError("Unsupported TikTok link format")

    async def _get_user_profile_and_videos(self, api, user):
        try:
            user_info_raw = await user.info()
        except Exception as e:
            raise RuntimeError("Failed to fetch user info. Possible expired or invalid ms_token.") from e

        if not user_info_raw or not user_info_raw.get("userInfo"):
            raise RuntimeError("TikTok returned no user info. Your ms_token may be expired or blocked.")

        user_info = user_info_raw["userInfo"]

        user_data = {
            "username": user_info.get("user", {}).get("uniqueId"),
            "nickname": user_info.get("user", {}).get("nickname"),
            "followers": user_info.get("stats", {}).get("followerCount"),
            "following": user_info.get("stats", {}).get("followingCount"),
            "likes": user_info.get("stats", {}).get("heartCount"),
            "videoCount": user_info.get("stats", {}).get("videoCount"),
            "videos": []
        }

        async for video in user.videos(count=10):
            video.url = f"https://www.tiktok.com/@{user.username}/video/{video.id}"
            video_info = await video.info()
            enriched = await self._get_video_with_comments(video)
            enriched.update({
                "id": video_info.get("id"),
                "description": video_info.get("desc"),
                "created": video_info.get("createTime"),
                "stats": video_info.get("stats"),
                "music": video_info.get("music", {}).get("title"),
                "video_url": video.url,
                "hashtags": [tag.get("hashtagName") for tag in video_info.get("textExtra", []) if tag.get("type") == 1]
            })
            user_data["videos"].append(enriched)

        return user_data

    async def _get_video_with_comments(self, video, max_retries=3):
        comments = []
        for attempt in range(max_retries):
            try:
                async for comment in video.comments(count=50):
                    replies = []
                    try:
                        async for reply in comment.replies(count=3):
                            replies.append({
                                "user": getattr(reply.user, "username", None),
                                "text": getattr(reply, "text", None),
                                "likes": getattr(reply.stats, "diggCount", None),
                                "timestamp": getattr(reply, "createTime", None)
                            })
                    except Exception as e:
                        replies.append({"error": f"Reply fetch error: {str(e)}"})

                    comments.append({
                        "user": getattr(comment.user, "username", None),
                        "text": getattr(comment, "text", None),
                        "likes": getattr(comment.stats, "diggCount", None),
                        "timestamp": getattr(comment, "createTime", None),
                        "replies": replies
                    })
                if comments:
                    break
            except Exception as e:
                if attempt < max_retries - 1:
                    await asyncio.sleep(random.uniform(2, 5))
                else:
                    comments.append({"error": f"Failed to fetch comments after retries: {str(e)}"})

        return {"comments": comments}

    def extract_video_id(self, url):
        match = re.search(r"/video/(\d+)", url)
        if match:
            return match.group(1)
        raise ValueError("Invalid video URL")

    def extract_username(self, url):
        match = re.search(r"tiktok\.com/@([\w\.-]+)", url)
        if match:
            return match.group(1)
        raise ValueError("Invalid profile URL")
