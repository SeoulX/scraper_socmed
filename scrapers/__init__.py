from .tiktok_scraper import TikTokScraper
from .fb_scraper import FacebookScraper
from .insta_scraper import InstagramScraper
from .x_scraper import XScraper

def get_scraper(platform):
    if platform == "tiktok":
        return TikTokScraper
    elif platform == "facebook":
        return FacebookScraper
    elif platform == "instagram":
        return InstagramScraper
    elif platform == "x":
        return XScraper
    else:
        raise ValueError(f"No scraper implemented for platform: {platform}")
