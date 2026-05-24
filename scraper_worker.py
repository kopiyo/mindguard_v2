"""
scraper_worker.py
=================
Runs Facebook and Twitter Playwright scraping in a completely separate
Python process to avoid the asyncio conflict with Streamlit on Windows.

Called by the main app via subprocess.run() and communicates via JSON stdout.

Usage (internal):
    python scraper_worker.py facebook https://www.facebook.com/zuck 3
    python scraper_worker.py twitter  https://x.com/elonmusk 3
"""

import sys
import json
import time
import datetime

def scrape_facebook(url: str, months: int) -> list:
    from playwright.sync_api import sync_playwright

    posts = []
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox","--disable-dev-shm-usage",
                  "--disable-blink-features=AutomationControlled"]
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
            locale="en-US",
        )
        page = context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(4)

            # Dismiss popups
            for selector in [
                '[aria-label="Allow all cookies"]',
                '[data-testid="cookie-policy-manage-dialog-accept-button"]',
                'button:has-text("Accept All")',
                '[aria-label="Close"]',
            ]:
                try:
                    btn = page.locator(selector).first
                    if btn.is_visible(timeout=1500):
                        btn.click()
                        time.sleep(1)
                except Exception:
                    pass

            # Click Posts tab if present
            try:
                tab = page.locator('a:has-text("Posts")').first
                if tab.is_visible(timeout=3000):
                    tab.click()
                    time.sleep(3)
            except Exception:
                pass

            seen = set()
            for scroll_i in range(15):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(2.5)

                extracted = page.evaluate("""() => {
                    const absoluteUrl = (href) => {
                        try {
                            return new URL(href, window.location.origin).toString();
                        } catch {
                            return '';
                        }
                    };
                    const cleanFacebookUrl = (href) => {
                        const full = absoluteUrl(href);
                        if (!full) return '';
                        try {
                            const url = new URL(full);
                            if (!url.hostname.includes('facebook.com')) return '';
                            for (const key of [...url.searchParams.keys()]) {
                                if (key.startsWith('__') || key === 'ref' || key === 'refid' || key === 'mibextid') {
                                    url.searchParams.delete(key);
                                }
                            }
                            url.hash = '';
                            return url.toString();
                        } catch {
                            return full;
                        }
                    };
                    const isPostLink = (href) => {
                        if (!href) return false;
                        return /\\/posts\\/|\\/permalink\\.php|\\/story\\.php|story_fbid=|\\/photo\\/?|fbid=|\\/videos\\/|\\/watch\\/|\\/reel\\//i.test(href);
                    };
                    const pickPostUrl = (container) => {
                        const links = [...container.querySelectorAll('a[href]')]
                            .map((a) => a.getAttribute('href') || '')
                            .filter(isPostLink);
                        const best = links.find((href) => /\\/posts\\/|\\/permalink\\.php|\\/story\\.php|story_fbid=/i.test(href)) || links[0] || '';
                        return cleanFacebookUrl(best);
                    };
                    const messageSelectors = [
                        '[data-ad-preview="message"]',
                        '[data-testid="post_message"]',
                        '.userContent',
                        'div[data-ad-comet-preview="message"]'
                    ];

                    const results = [];
                    const seen = new Set();
                    const containers = [
                        ...document.querySelectorAll('[role="article"], div[data-pagelet^="FeedUnit_"], div[data-pagelet*="FeedUnit"]')
                    ];
                    for (const container of containers) {
                        let txt = '';
                        for (const sel of messageSelectors) {
                            const el = container.querySelector(sel);
                            if (el && el.innerText && el.innerText.trim().length > txt.length) {
                                txt = el.innerText.trim();
                            }
                        }
                        if (!txt) {
                            const spans = [...container.querySelectorAll('div[dir="auto"] > span[dir="auto"]')]
                                .map((el) => el.innerText.trim())
                                .filter((text) => text.length > 15);
                            txt = spans.join("\\n").trim();
                        }
                        if (txt.length > 15 && !seen.has(txt)) {
                            seen.add(txt);
                            results.push({ text: txt, url: pickPostUrl(container) });
                        }
                    }

                    const selectors = [
                        '[data-ad-preview="message"]',
                        '[data-testid="post_message"]',
                        '.userContent',
                        'div[dir="auto"] > span[dir="auto"]',
                        'div[data-ad-comet-preview="message"]',
                    ];
                    for (const sel of selectors) {
                        document.querySelectorAll(sel).forEach(el => {
                            const txt = el.innerText.trim();
                            if (txt.length > 15 && !seen.has(txt)) {
                                seen.add(txt);
                                results.push({ text: txt, url: pickPostUrl(el.closest('[role="article"], div[data-pagelet^="FeedUnit_"], div[data-pagelet*="FeedUnit"]') || el) });
                            }
                        });
                    }
                    return results;
                }""")

                for item in extracted:
                    if isinstance(item, dict):
                        text = item.get("text", "")
                        post_url = item.get("url") or url
                    else:
                        text = str(item)
                        post_url = url
                    clean = text.strip()
                    if len(clean) > 15 and clean not in seen:
                        seen.add(clean)
                        dt = (datetime.datetime.utcnow() -
                              datetime.timedelta(days=scroll_i * 5)).isoformat()
                        posts.append({"text": clean, "date": dt, "url": post_url})

                if len(posts) >= 100:
                    break
        finally:
            browser.close()
    return posts


def scrape_twitter(url: str, months: int) -> list:
    from playwright.sync_api import sync_playwright

    posts = []
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox","--disable-dev-shm-usage",
                  "--disable-blink-features=AutomationControlled"]
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
            locale="en-US",
        )
        page = context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(3)

            seen = set()
            for scroll_i in range(20):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(2)

                extracted = page.evaluate("""() => {
                    const cleanTweetUrl = (href) => {
                        if (!href) return '';
                        try {
                            const url = new URL(href, window.location.origin);
                            if (!url.hostname.includes('twitter.com') && !url.hostname.includes('x.com')) return '';
                            url.hostname = 'x.com';
                            url.search = '';
                            url.hash = '';
                            return url.toString();
                        } catch {
                            return '';
                        }
                    };
                    const results = [];
                    document.querySelectorAll('article[data-testid="tweet"]').forEach(article => {
                        const textEl = article.querySelector('[data-testid="tweetText"]');
                        const text = textEl?.innerText?.trim() || '';
                        if (text.length <= 5) return;

                        const timeEl = article.querySelector('time');
                        const href = timeEl?.closest('a')?.getAttribute('href') || '';
                        results.push({
                            text,
                            date: timeEl?.getAttribute('datetime') || '',
                            url: cleanTweetUrl(href),
                        });
                    });
                    if (results.length) return results;

                    const fallbackResults = [];
                    document.querySelectorAll('[data-testid="tweetText"]').forEach(el => {
                        const txt = el.innerText.trim();
                        if (txt.length > 5) fallbackResults.push({ text: txt, date: '', url: '' });
                    });
                    const seen = new Set();
                    return fallbackResults.filter((item) => {
                        if (seen.has(item.text)) return false;
                        seen.add(item.text);
                        return true;
                    });
                }""")

                for i, item in enumerate(extracted):
                    if isinstance(item, dict):
                        text = item.get("text", "")
                        tweet_date = item.get("date", "")
                        tweet_url = item.get("url") or ""
                    else:
                        text = str(item)
                        tweet_date = ""
                        tweet_url = ""
                    if text not in seen and len(text) > 5:
                        seen.add(text)
                        dt = (datetime.datetime.utcnow() -
                              datetime.timedelta(days=scroll_i * 2 + i)).isoformat()
                        if tweet_date:
                            try:
                                dt = tweet_date.replace("Z", "")
                            except Exception:
                                pass
                        posts.append({"text": text, "date": dt, "url": tweet_url})

                if len(posts) >= 100:
                    break
        finally:
            browser.close()
    return posts


if __name__ == "__main__":
    platform = sys.argv[1]  # "facebook" or "twitter"
    url      = sys.argv[2]
    months   = int(sys.argv[3]) if len(sys.argv) > 3 else 3

    try:
        if platform == "facebook":
            posts = scrape_facebook(url, months)
        elif platform == "twitter":
            posts = scrape_twitter(url, months)
        else:
            posts = []
        print(json.dumps({"ok": True, "posts": posts}))
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}))
