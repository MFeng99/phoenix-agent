"""HTTP-Based Job Search — 用Bing搜索找到Upwork岗位（DuckDuckGo在国内不可用）"""
import json
import os
import re
import time
import urllib.parse
import urllib.request

SEARCH_CACHE_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "agent-memory/freelance/search_cache.json",
)
os.makedirs(os.path.dirname(SEARCH_CACHE_FILE), exist_ok=True)

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"


def _bing_search(query: str, max_results: int = 10) -> list[dict]:
    """Bing search — 在国内可访问"""
    url = f"https://www.bing.com/search?q={urllib.parse.quote(query)}&count={max_results}"
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.5"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        return [{"error": str(e)}]

    results = []

    # Bing result pattern: <li class="b_algo">...<h2><a href="...">title</a></h2>
    # Extract all result blocks
    for block in re.finditer(
        r'<li\s+class="b_algo"[^>]*>(.*?)</li>', html, re.DOTALL
    ):
        content = block.group(1)

        # Title + URL
        link_match = re.search(
            r'<a\s+href="(https?://[^"]+)"[^>]*>(.*?)</a>', content, re.DOTALL
        )
        if not link_match:
            continue
        url = link_match.group(1)
        title = re.sub(r"<[^>]+>", "", link_match.group(2)).strip()

        # Description
        desc_match = re.search(r'<p[^>]*>(.*?)</p>', content, re.DOTALL)
        description = ""
        if desc_match:
            description = re.sub(r"<[^>]+>", "", desc_match.group(1)).strip()

        results.append(
            {
                "title": title,
                "url": url,
                "description": description,
            }
        )

    return results


def search_upwork_jobs(
    search_terms: list[str] | None = None, max_per_query: int = 10
) -> list[dict]:
    """搜索Upwork工作——用Bing找site:upwork.com/freelance-jobs/apply"""
    if search_terms is None:
        search_terms = [
            '"Python" "Web Scraping" job',
            '"Selenium" scraping python job',
            '"n8n" automation job freelance',
            '"AI" workflow automation job freelance',
            '"Data Extraction" python job',
        ]

    seen_urls = set()
    all_jobs = []

    for term in search_terms:
        query = f"site:upwork.com/freelance-jobs/apply {term}"
        results = _bing_search(query, max_results=max_per_query)
        for r in results:
            if "error" in r:
                continue
            url = r.get("url", "")
            title = r.get("title", "").replace(" - Upwork", "").strip()

            if not url or url in seen_urls:
                continue
            if "freelance-jobs/apply/" not in url:
                continue
            if any(skip in title.lower() for skip in ["top ", "best ", "hire ", "near "]):
                continue

            seen_urls.add(url)
            all_jobs.append({
                "title": title,
                "url": url,
                "snippet": r.get("description", ""),
                "source_term": term,
                "found_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            })

    return all_jobs


def deduplicate_jobs(new_jobs: list[dict], old_jobs: list[dict]) -> list[dict]:
    old_urls = {j.get("url", "") for j in old_jobs}
    return [j for j in new_jobs if j.get("url", "") not in old_urls]


def save_search_results(jobs: list[dict]) -> None:
    old = load_search_results()
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    all_urls = {j.get("url", "") for j in old}
    merged = list(old)
    for j in jobs:
        if j.get("url", "") not in all_urls:
            merged.append(j)
            all_urls.add(j.get("url", ""))
    merged = merged[-200:]
    data = {"last_search": now, "total_found": len(merged), "jobs": merged}
    with open(SEARCH_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_search_results() -> list[dict]:
    if os.path.exists(SEARCH_CACHE_FILE):
        try:
            with open(SEARCH_CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("jobs", [])
        except Exception:
            pass
    return []
