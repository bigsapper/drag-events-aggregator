"""RSS crawler strategy."""


def crawl_rss_impl(source: dict, state: dict, *, parse_feed) -> list[dict]:
    url = source["url"]
    print(f"  {url}")
    feed = parse_feed(url)
    new_items = []
    for entry in feed.entries:
        link = entry.get("link", "")
        if link in state.get("seen_urls", []):
            continue
        state.setdefault("seen_urls", []).append(link)
        new_items.append({
            "title": entry.get("title", ""),
            "published": entry.get("published", ""),
            "summary": entry.get("summary", ""),
            "source_url": link,
            "source": source["name"],
        })
    print(f"  Found {len(new_items)} new RSS items")
    return new_items
