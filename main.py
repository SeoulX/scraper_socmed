import argparse
import yaml
import json
import os
from dotenv import load_dotenv
from scrapers import get_scraper

load_dotenv()

def load_config(path):
    with open(path, 'r') as f:
        return yaml.safe_load(f)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--conf", required=True)
    parser.add_argument("--target", required=True, choices=["facebook", "instagram", "tiktok", "x"])
    parser.add_argument("--link", required=True)
    args = parser.parse_args()

    config = load_config(args.conf)
    scraper = get_scraper(args.target)(config)

    result = scraper.scrape(args.link)

    os.makedirs("outputs", exist_ok=True)
    output_path = os.path.join("outputs", f"{args.target}_output.json")

    if os.path.exists(output_path):
        with open(output_path, "r", encoding="utf-8") as f:
            try:
                existing_data = json.load(f)
                if isinstance(existing_data, list):
                    combined_data = existing_data
                else:
                    combined_data = [existing_data]
            except json.JSONDecodeError:
                combined_data = []
    else:
        combined_data = []

    combined_data.append(result)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(combined_data, f, ensure_ascii=False, indent=4)

    print(f"Scraped data saved to {output_path}")

if __name__ == "__main__":
    main()
