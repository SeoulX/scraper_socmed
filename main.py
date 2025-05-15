import argparse
import yaml
import json
import os
import asyncio
from dotenv import load_dotenv
from scrapers import get_scraper

load_dotenv()

def load_config(path):
    with open(path, 'r') as f:
        return yaml.safe_load(f)

async def run_scraper(args, config):
    scraper = get_scraper(args.target)(config)

    if args.mode == "discovery" and args.target == "facebook-event":
        return await scraper.scrape_discovery_events(limit=args.limit)
    elif args.mode == "single":
        if not args.link:
            raise ValueError("You must specify --link for single mode")
        # create a temporary playwright instance inside main
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            return await scraper.scrape_event_async(p, args.link)
    else:
        raise ValueError("Invalid mode or unsupported target for discovery")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--conf", required=True)
    parser.add_argument("--target", required=True, choices=["facebook", "instagram", "linkedin", "x", "facebook-event"])
    parser.add_argument("--mode", choices=["single", "discovery"], default="single")
    parser.add_argument("--link", help="URL of the Facebook event")
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()

    config = load_config(args.conf)

    result = asyncio.run(run_scraper(args, config))

    os.makedirs("outputs", exist_ok=True)
    output_path = os.path.join("outputs", f"{args.target}_output.json")

    if os.path.exists(output_path):
        with open(output_path, "r", encoding="utf-8") as f:
            try:
                existing_data = json.load(f)
                combined_data = existing_data if isinstance(existing_data, list) else [existing_data]
            except json.JSONDecodeError:
                combined_data = []
    else:
        combined_data = []

    if isinstance(result, list):
        combined_data.extend(result)
    else:
        combined_data.append(result)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(combined_data, f, ensure_ascii=False, indent=4)

    print(f"✅ Scraped data saved to {output_path}")

if __name__ == "__main__":
    main()
