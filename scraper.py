#!/usr/bin/env python3
"""
AAU Update News Scraper
Scrapes news from AAU Update and generates a static HTML image board.
"""

import json
import re
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright


def scrape_news(url: str = "https://www.en.update.aau.dk/news", max_items: int = 10) -> list[dict]:
    """Scrape news articles from AAU Update."""
    articles = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Navigate and wait for content to load
        page.goto(url, wait_until="networkidle")
        page.wait_for_timeout(2000)  # Extra wait for dynamic content

        # Find news article elements - adjust selectors based on actual page structure
        # AAU Update typically uses article cards with images and titles
        article_elements = page.query_selector_all("article, .news-item, [class*='news'], [class*='article'], a[href*='/news/']")

        if not article_elements:
            # Try alternative: look for links with images that lead to news articles
            article_elements = page.query_selector_all("a[href*='/news/'][href*='202']")

        for elem in article_elements[:max_items]:
            try:
                article = {}

                # Get the link
                href = elem.get_attribute("href")
                if not href:
                    link_elem = elem.query_selector("a")
                    href = link_elem.get_attribute("href") if link_elem else None

                if href:
                    if href.startswith("/"):
                        href = f"https://www.en.update.aau.dk{href}"
                    article["url"] = href

                # Get the title
                title_elem = elem.query_selector("h2, h3, h4, [class*='title'], [class*='heading']")
                if title_elem:
                    article["title"] = title_elem.inner_text().strip()
                else:
                    # Try getting text from the element itself
                    text = elem.inner_text().strip()
                    if text and len(text) < 200:
                        article["title"] = text.split("\n")[0]

                # Get the image
                img_elem = elem.query_selector("img")
                if img_elem:
                    img_src = img_elem.get_attribute("src") or img_elem.get_attribute("data-src")
                    if img_src:
                        if img_src.startswith("/"):
                            img_src = f"https://www.en.update.aau.dk{img_src}"
                        # Remove tiny width parameter and request a proper size
                        if "?width=" in img_src:
                            img_src = img_src.split("?width=")[0] + "?width=800"
                        article["image"] = img_src

                # Try to get date
                date_elem = elem.query_selector("time, [class*='date'], [class*='time']")
                if date_elem:
                    article["date"] = date_elem.inner_text().strip()

                # Only add if we have at least a title and URL, and it's not a duplicate
                if article.get("title") and article.get("url"):
                    # Check for duplicates based on URL
                    if not any(a.get("url") == article["url"] for a in articles):
                        articles.append(article)

            except Exception as e:
                print(f"Error processing article: {e}")
                continue

        # If we didn't find articles with the above method, try extracting from __NEXT_DATA__
        if not articles:
            print("Trying to extract from __NEXT_DATA__...")
            next_data = page.query_selector("script#__NEXT_DATA__")
            if next_data:
                try:
                    data = json.loads(next_data.inner_text())
                    # Navigate through the Next.js data structure to find articles
                    articles = extract_from_next_data(data)
                except Exception as e:
                    print(f"Error parsing __NEXT_DATA__: {e}")

        browser.close()

    return articles[:max_items]


def extract_from_next_data(data: dict) -> list[dict]:
    """Extract articles from Next.js __NEXT_DATA__ JSON."""
    articles = []

    def find_articles(obj, path=""):
        """Recursively search for article-like objects."""
        if isinstance(obj, dict):
            # Check if this looks like an article
            if "title" in obj or "headline" in obj or "name" in obj:
                has_url = any(k in obj for k in ["url", "href", "link", "slug"])
                has_image = any(k in obj for k in ["image", "img", "thumbnail", "media", "photo"])

                if has_url or has_image:
                    article = {}

                    # Extract title
                    for key in ["title", "headline", "name"]:
                        if key in obj and isinstance(obj[key], str):
                            article["title"] = obj[key]
                            break

                    # Extract URL
                    for key in ["url", "href", "link"]:
                        if key in obj and isinstance(obj[key], str):
                            article["url"] = obj[key]
                            break
                    if "slug" in obj:
                        article["url"] = f"https://www.en.update.aau.dk/news/{obj['slug']}"

                    # Extract image
                    for key in ["image", "img", "thumbnail", "media", "photo"]:
                        if key in obj:
                            img = obj[key]
                            if isinstance(img, str):
                                article["image"] = img
                            elif isinstance(img, dict):
                                article["image"] = img.get("url") or img.get("src") or img.get("href")
                            break

                    # Extract date
                    for key in ["date", "publishedAt", "createdAt", "updateDate", "createDate"]:
                        if key in obj:
                            article["date"] = str(obj[key])[:10]
                            break

                    if article.get("title"):
                        articles.append(article)

            # Continue searching
            for k, v in obj.items():
                find_articles(v, f"{path}.{k}")

        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                find_articles(item, f"{path}[{i}]")

    find_articles(data)
    return articles


def generate_html(articles: list[dict], output_path: str = "index.html"):
    """Generate the image board HTML."""

    # Format dates nicely
    for article in articles:
        if article.get("date"):
            try:
                # Try to parse and format the date
                date_str = article["date"]
                if "T" in date_str:
                    date_str = date_str.split("T")[0]
                dt = datetime.strptime(date_str[:10], "%Y-%m-%d")
                article["formatted_date"] = dt.strftime("%d.%m.%Y")
            except:
                article["formatted_date"] = article["date"]
        else:
            article["formatted_date"] = ""

    # Default placeholder image
    placeholder = "https://www.en.update.aau.dk/media/aau-logo.png"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=2632, height=1222">
    <meta http-equiv="refresh" content="3600">
    <title>AAU Update News</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        html, body {{
            width: 2632px;
            height: 1222px;
            overflow: hidden;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: #e8e8e8;
        }}

        .grid {{
            display: grid;
            grid-template-columns: 1fr 1fr 1fr 1fr;
            grid-template-rows: 1fr 1fr;
            gap: 12px;
            padding: 12px;
            width: 2632px;
            height: 1222px;
        }}

        .article {{
            position: relative;
            overflow: hidden;
            border-radius: 6px;
            background: #333;
        }}

        /* First two articles are large (each spans 2 columns) */
        .article:nth-child(1),
        .article:nth-child(2) {{
            grid-column: span 2;
        }}

        .article img {{
            width: 100%;
            height: 100%;
            object-fit: cover;
        }}

        .article-overlay {{
            position: absolute;
            bottom: 0;
            left: 0;
            right: 0;
            padding: 60px 25px 25px;
            background: linear-gradient(transparent, rgba(0,0,0,0.85));
            color: white;
        }}

        /* Large articles (1st and 2nd) */
        .article:nth-child(1) .article-overlay,
        .article:nth-child(2) .article-overlay {{
            padding: 80px 35px 35px;
        }}

        .article-title {{
            font-size: 26px;
            font-weight: 600;
            line-height: 1.25;
            margin-bottom: 8px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.5);
        }}

        /* Large articles get bigger titles */
        .article:nth-child(1) .article-title,
        .article:nth-child(2) .article-title {{
            font-size: 38px;
            line-height: 1.2;
        }}

        .article-meta {{
            font-size: 16px;
            opacity: 0.85;
        }}

        .article:nth-child(1) .article-meta,
        .article:nth-child(2) .article-meta {{
            font-size: 20px;
        }}

        .article a {{
            position: absolute;
            inset: 0;
            z-index: 1;
        }}
    </style>
</head>
<body>
    <div class="grid">
"""

    for i, article in enumerate(articles[:6]):
        image = article.get("image", placeholder)
        title = article.get("title", "News Article")
        url = article.get("url", "#")
        date = article.get("formatted_date", "")

        html += f"""        <div class="article">
            <img src="{image}" alt="{title}" loading="lazy" onerror="this.src='{placeholder}'">
            <div class="article-overlay">
                <h2 class="article-title">{title}</h2>
                <div class="article-meta">update.aau.dk &bull; {date}</div>
            </div>
            <a href="{url}" target="_blank" rel="noopener"></a>
        </div>
"""

    html += """    </div>
</body>
</html>
"""

    Path(output_path).write_text(html, encoding="utf-8")
    print(f"Generated {output_path}")


def main():
    print("Scraping AAU Update news...")
    articles = scrape_news()

    if articles:
        print(f"Found {len(articles)} articles")
        for a in articles:
            print(f"  - {a.get('title', 'No title')[:50]}...")
        generate_html(articles)
    else:
        print("No articles found! Generating placeholder page...")
        # Generate a page with a message
        generate_html([{
            "title": "News temporarily unavailable",
            "url": "https://www.en.update.aau.dk/news",
            "image": "https://www.aau.dk/digitalAssets/1075/1075444_aau-logo-rgb.png",
            "date": datetime.now().strftime("%Y-%m-%d")
        }])


if __name__ == "__main__":
    main()
