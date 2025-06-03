import os
import requests
from urllib.parse import urlparse
import pickle
from dotenv import load_dotenv
from playwright.async_api import async_playwright, Browser


from main_content_extractor import MainContentExtractor

load_dotenv()


URL_CONTENT_CACHE = {}
CACHE_DIR = ".cache/search_agent/memory"
BLACKLIST_DOMAINS = set()

async def load_cache():
    global URL_CONTENT_CACHE
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)
    cache_file = os.path.join(CACHE_DIR, "url_cache.pkl")
    if os.path.exists(cache_file):
        with open(cache_file, "rb") as f:
            URL_CONTENT_CACHE = pickle.load(f)
    blacklist_file = os.path.join(CACHE_DIR, "blacklist.pkl")
    if os.path.exists(blacklist_file):
        with open(blacklist_file, "rb") as f:
            global BLACKLIST_DOMAINS
            BLACKLIST_DOMAINS = pickle.load(f)

async def save_cache():
    cache_file = os.path.join(CACHE_DIR, "url_cache.pkl")
    with open(cache_file, "wb") as f:
        pickle.dump(URL_CONTENT_CACHE, f)

async def save_blacklist():
    blacklist_file = os.path.join(CACHE_DIR, "blacklist.pkl")
    with open(blacklist_file, "wb") as f:
        pickle.dump(BLACKLIST_DOMAINS, f)

def batch_search_google(queries: list[str], num_results: int = 3) -> list[str]:
    """Search Google using the Custom Search API for multiple queries."""
    api_key = os.environ.get("GOOGLE_API_KEY")
    search_engine_id = os.environ.get("GOOGLE_SEARCH_ENGINE_ID")
    if not api_key or not search_engine_id:
        return ["Error: Google API key or Search Engine ID not configured."]

    url = "https://www.googleapis.com/customsearch/v1"
    results = []
    for query in queries:
        params = {
            "key": api_key,
            "cx": search_engine_id,
            "q": query,
            "num": num_results,
        }
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()  # Raise an exception for bad status codes
            results.append(response.json())
        except requests.exceptions.RequestException as e:
            results.append(f"Error during Google search: {str(e)}")
    return results

async def get_content(browser: Browser, url: str) -> str:
    """Get the content of a URL as a markdown string.
    Cache the content for 3 days.
    """
    await load_cache()
    parsed_url = urlparse(url)
    domain = parsed_url.netloc
    if domain in BLACKLIST_DOMAINS:
        print(f"Skipping blacklisted domain: {domain}")
        return None

    now = int(os.times().elapsed) # type: ignore
    if url in URL_CONTENT_CACHE and now - URL_CONTENT_CACHE[url]["timestamp"] < 60 * 60 * 24 * 3:
        print(f"Cache hit for {url}")
        content = URL_CONTENT_CACHE[url]["content"]
        # MainContentExtractor が HTML 文字列を受け取ることを想定
        md = MainContentExtractor.extract(content, include_links=False, output_format="markdown")
        return md
    else:
        print(f"Cache miss for {url}")

    page = await browser.new_page()
    try:
        response = await page.goto(url, timeout=60000)
        if response is None:
            BLACKLIST_DOMAINS.add(domain)
            print(f"Error: No response from {url}")
            await page.close() # エラー時もページは閉じる
            return None
        if response.status >= 400:
            print(f"Error: HTTP status code {response.status} for {url}")
            BLACKLIST_DOMAINS.add(domain)
            await page.close() # エラー時もページは閉じる
            return None
        content = await page.content()

        # Cache the content
        URL_CONTENT_CACHE[url] = {
            "content": content,
            "timestamp": int(os.times().elapsed), # type: ignore
        }

        # MainContentExtractor が HTML 文字列を受け取ることを想定
        md = MainContentExtractor.extract(content, include_links=True, output_format="markdown")
        return md
    except Exception:
        import traceback
        BLACKLIST_DOMAINS.add(domain)
        print(f"Error getting content from {url}")
        print(traceback.format_exc())
        return None
    finally:
        # ページを閉じる処理は finally に含める
        if not page.is_closed():
             await page.close()
        await save_cache()
        await save_blacklist()



async def batch_search(queries: list[str], num_results: int = 3) -> list[dict]:
    """Search Google and get content of each link, including title, snippet, and og:description."""
    await load_cache()
    search_results = batch_search_google(queries, num_results)
    final_results = []
    for result in search_results:
        if isinstance(result, str):
            continue
        items = result.get("items", [])
        for item in items:
            link = item.get("link")
            title = item.get("title")
            snippet = item.get("snippet")
            og_description = ""
            if "pagemap" in item and "metatags" in item["pagemap"]:
                metatags = item["pagemap"]["metatags"]
                if metatags and isinstance(metatags, list) and len(metatags) > 0:
                    og_description = metatags[0].get("og:description", "")

            if not link:
                continue
            parsed_url = urlparse(link)
            domain = parsed_url.netloc
            if domain in BLACKLIST_DOMAINS:
                print(f"Skipping blacklisted domain: {domain}")
                continue

            final_results.append({
                "link": link,
                "title": title,
                "snippet": snippet,
                "og:description": og_description
            })
    await save_cache()
    await save_blacklist()
    return final_results



# レスポンスのサンプル
# ```
# "items":[{
#       "kind": "customsearch#result",
#       "title": "Amazon.co.jp: カ ル ビ ー フルーツグラノーラ フルグラ 1200g : 食品 ...",
#       "htmlTitle": "Amazon.co.jp: カ ル ビ ー <b>フルーツグラノーラ</b> フルグラ 1200g : 食品 ...",
#       "link": "https://www.amazon.co.jp/%E3%82%AB-%E3%83%AB-%E3%83%95%E3%83%AB%E3%83%BC%E3%83%84%E3%82%B0%E3%83%A9%E3%83%8E%E3%83%BC%E3%83%A9-%E3%83%95%E3%83%AB%E3%82%B0%E3%83%A9-1200g/dp/B0D29DSC69",
#       "displayLink": "www.amazon.co.jp",
#       "snippet": "カ ル ビ ー フルーツグラノーラ フルグラ 1200g · 定期おトク便で最大5%OFF · ご希望の頻度でお届け · 次回配送分のキャンセルも可能 · カートに追加されました · すべて ...",
#       "htmlSnippet": "カ ル ビ ー <b>フルーツグラノーラ</b> フルグラ 1200g &middot; 定期おトク便で最大5%OFF &middot; ご希望の頻度でお届け &middot; 次回配送分のキャンセルも可能 &middot; カートに追加されました &middot; すべて&nbsp;...",
#       "formattedUrl": "https://www.amazon.co.jp/カ-ル-フルーツグラノーラ.../dp/B0D29DSC69",
#       "htmlFormattedUrl": "https://www.amazon.co.jp/カ-ル-<b>フルーツグラノーラ</b>.../dp/B0D29DSC69",
#       "pagemap": {
#         "cse_thumbnail": [
#           {
#             "src": "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRLE_k-A6HOKY-ScCuwMKtZmkMvsimoFHX2_qL41NosIR0ylY1hyl0CpHY&s",
#             "width": "310",
#             "height": "162"
#           }
#         ],
#         "metatags": [
#           {
#             "og:image": "https://m.media-amazon.com/images/I/51p97sY70RL._BO30,255,255,255_UF900,850_SR1910,1000,0,C_ZA17,500,900,420,420,AmazonEmber,50,4,0,0_PIRIOFOURANDHALF-medium,BottomLeft,30,-20_QL100_.jpg",
#             "theme-color": "#131921",
#             "og:type": "product",
#             "og:image:width": "1910",
#             "viewport": "width=device-width, maximum-scale=2, minimum-scale=1, initial-scale=1, shrink-to-fit=no",
#             "og:sitename": "Amazon.co.jp",
#             "og:title": "カ ル ビ ー フルーツグラノーラ フルグラ 1200g",
#             "og:image:height": "1000",
#             "title": "Amazon.co.jp: カ ル ビ ー フルーツグラノーラ フルグラ 1200g : 食品・飲料・お酒",
#             "og:url": "https://www.amazon.co.jp/dp/B0D29DSC69",
#             "og:description": "オーツ麦を主原料とし、複数の穀物を香ばしく焼き上げたザクザク食感のグラノーラとフルーツの酸味と甘みがひとさじで楽しめる朝食シリアル。食物繊維たっぷり＋オリゴ糖入り、鉄分＆8種のビタミンもたっぷり。おいしさと栄養がうれしいワンボウル朝食でここちのよい目覚めにぴったりです。",
#             "encrypted-slate-token": "AnYxiqUmfjzr4w5YcxrSTe5KFMKoou+HzZu41zWa2VXw7isMxfBdOLYF8JWNZdY2IRYwJh0k7iT6aUrfeHEYfCOr9mJEJ0qp52IU4ssd36j39K4xhYFCqRRdqzV6nTi+oLkHLk0oxZ7Lf5nKCcp+EL+QD7NDAe/CTgMkl1vUSkoRFVwRK90Uz3NVhrdcqZP4Tg1Yny5NV+hxmhKr7yafysoWKlQAsv6U3HYvVH/AK+sdc+29GHHW0M+IdOQS1F0/MkRirBihXJYJ8T40OYPfIDGbl9lbiBxgRXYq"
#           }
#         ],
#         "cse_image": [
#           {
#             "src": "https://m.media-amazon.com/images/I/51p97sY70RL._BO30,255,255,255_UF900,850_SR1910,1000,0,C_ZA17,500,900,420,420,AmazonEmber,50,4,0,0_PIRIOFOURANDHALF-medium,BottomLeft,30,-20_QL100_.jpg"
#           }
#         ]
#       }
#     },
# ]
