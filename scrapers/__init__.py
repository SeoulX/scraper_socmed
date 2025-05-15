from .fb_scraper import FacebookScraper
from .fb_event_scraper import FacebookEventScraper
from .insta_scraper import InstagramScraper
from .x_scraper import XScraper
from .linkedin_scraper import LinkedInScraper

def get_scraper(platform):
    if platform == "facebook":
        return FacebookScraper
    elif platform == "facebook-event":
        return FacebookEventScraper
    elif platform == "instagram":
        return InstagramScraper
    elif platform == "x":
        return XScraper
    elif platform == "linkedin":
        return LinkedInScraper
    else:
        raise ValueError(f"Unsupported platform: {platform}")
