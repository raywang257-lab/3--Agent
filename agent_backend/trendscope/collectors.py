from __future__ import annotations

import asyncio
import html
import json
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Awaitable, Callable
from urllib.parse import quote_plus, urlsplit

import feedparser
import httpx

from .config import Settings
from .models import MonitoringTask, SourceItem, SourceMetrics, utc_now


PRIMARY_RSS_DOMAINS = {
    "openai.com",
    "blog.google",
    "deepmind.google",
    "github.blog",
    "huggingface.co",
    "federalreserve.gov",
    "ecb.europa.eu",
    "bankofengland.co.uk",
    "sec.gov",
    "fda.gov",
    "blog.cloudflare.com",
    "blogs.nvidia.com",
    "aws.amazon.com",
    "microsoft.com",
    "who.int",
}


def _is_primary_rss_source(url: str) -> bool:
    hostname = (urlsplit(url).hostname or "").lower()
    return any(hostname == domain or hostname.endswith(f".{domain}") for domain in PRIMARY_RSS_DOMAINS)


def _safe_datetime(value: str | None, fallback: datetime | None = None) -> datetime:
    fallback = fallback or utc_now()
    if not value:
        return fallback
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return fallback
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _clean_html(value: str | None) -> str:
    if not value:
        return ""
    text = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()[:3000]


async def collect_github(task: MonitoringTask, settings: Settings) -> list[SourceItem]:
    since = (utc_now() - timedelta(hours=task.time_window_hours)).date().isoformat()
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"
    async with httpx.AsyncClient(timeout=settings.request_timeout_seconds, follow_redirects=True) as client:
        # GitHub Search 对复杂 OR 查询限制较多。分别查询再由程序去重更稳定，
        # 同时将调用数限制为 3，避免匿名 API 很快触发限额。
        async def search(keyword: str, mode: str) -> list[tuple[dict, str]]:
            qualifier = "created" if mode == "repository_created" else "pushed"
            params = {
                "q": f'"{keyword}" in:name,description {qualifier}:>={since}',
                "sort": "updated",
                "order": "desc",
                "per_page": min(10, settings.max_items_per_source),
            }
            response = await client.get("https://api.github.com/search/repositories", params=params, headers=headers)
            response.raise_for_status()
            return [(repo, mode) for repo in response.json().get("items", [])]

        searches = [
            search(keyword, mode)
            for keyword in task.keywords[:3]
            for mode in ("repository_created", "repository_updated")
        ]
        groups = await asyncio.gather(*searches)
    repos: dict[int, tuple[dict, str]] = {}
    for group in groups:
        for repo, mode in group:
            repo_id = int(repo["id"])
            previous = repos.get(repo_id)
            if previous is None or mode == "repository_created":
                repos[repo_id] = (repo, mode)
    items: list[SourceItem] = []
    ordered = sorted(
        repos.values(),
        key=lambda pair: pair[0].get("created_at" if pair[1] == "repository_created" else "pushed_at", ""),
        reverse=True,
    )
    # pushed_at 只能证明普通 push。额外查询 Release API，只把真实发布记录
    # 标为 release_published，避免将日常代码活动伪装成新产品事件。
    release_targets = [repo for repo, _ in ordered[:8] if repo.get("full_name")]
    async with httpx.AsyncClient(timeout=settings.request_timeout_seconds, follow_redirects=True) as client:
        async def latest_release(repo: dict) -> tuple[dict, dict] | None:
            response = await client.get(
                f'https://api.github.com/repos/{repo["full_name"]}/releases/latest', headers=headers,
            )
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return repo, response.json()

        release_results = await asyncio.gather(
            *(latest_release(repo) for repo in release_targets), return_exceptions=True,
        )
    cutoff = utc_now() - timedelta(hours=task.time_window_hours)
    for result in release_results:
        if not result or isinstance(result, Exception):
            continue
        repo, release = result
        published_at = _safe_datetime(release.get("published_at") or release.get("created_at"))
        if published_at < cutoff:
            continue
        items.append(SourceItem(
            source="github",
            external_id=f'{repo["id"]}:release:{release.get("id")}',
            title=f'{repo["full_name"]} 发布 {release.get("name") or release.get("tag_name") or "新版本"}',
            url=release.get("html_url") or repo["html_url"],
            author=(release.get("author") or {}).get("login") or (repo.get("owner") or {}).get("login"),
            content=_clean_html(release.get("body")),
            published_at=published_at,
            released_at=published_at,
            event_type="release_published",
            metrics=SourceMetrics(stars=repo.get("stargazers_count"), forks=repo.get("forks_count")),
            is_primary_source=True,
        ))
    for repo, event_type in ordered:
        if len(items) >= settings.max_items_per_source:
            break
        created_at = _safe_datetime(repo.get("created_at"))
        updated_at = _safe_datetime(repo.get("updated_at"))
        pushed_at = _safe_datetime(repo.get("pushed_at"))
        event_time = created_at if event_type == "repository_created" else pushed_at
        suffix = "新建仓库" if event_type == "repository_created" else "近期活跃"
        items.append(SourceItem(
            source="github",
            external_id=f'{repo["id"]}:{event_type}',
            title=f'{repo.get("full_name") or repo.get("name") or "Untitled repository"} {suffix}',
            url=repo["html_url"],
            author=(repo.get("owner") or {}).get("login"),
            content=repo.get("description") or "",
            published_at=event_time,
            created_at=created_at,
            updated_at=updated_at,
            pushed_at=pushed_at,
            event_type=event_type,
            metrics=SourceMetrics(stars=repo.get("stargazers_count"), forks=repo.get("forks_count")),
            is_primary_source=True,
        ))
    return items


async def collect_hacker_news(task: MonitoringTask, settings: Settings) -> list[SourceItem]:
    base = "https://hacker-news.firebaseio.com/v0"
    async with httpx.AsyncClient(timeout=settings.request_timeout_seconds, follow_redirects=True) as client:
        ids_response = await client.get(f"{base}/newstories.json")
        ids_response.raise_for_status()
        story_ids = ids_response.json()[: max(60, settings.max_items_per_source * 4)]

        semaphore = asyncio.Semaphore(12)

        async def fetch(story_id: int) -> dict | None:
            async with semaphore:
                try:
                    response = await client.get(f"{base}/item/{story_id}.json")
                    response.raise_for_status()
                    return response.json()
                except (httpx.HTTPError, ValueError):
                    return None

        stories = await asyncio.gather(*(fetch(story_id) for story_id in story_ids))

    cutoff = utc_now() - timedelta(hours=task.time_window_hours)
    keywords = [word.lower() for word in task.keywords]
    result: list[SourceItem] = []
    for story in stories:
        if not story or story.get("type") != "story" or not story.get("title"):
            continue
        published = datetime.fromtimestamp(story.get("time", 0), tz=timezone.utc)
        if published < cutoff:
            continue
        haystack = f"{story.get('title', '')} {story.get('text', '')}".lower()
        if not any(keyword in haystack for keyword in keywords):
            continue
        story_id = str(story["id"])
        discussion_url = f"https://news.ycombinator.com/item?id={story_id}"
        result.append(SourceItem(
            source="hacker_news",
            external_id=story_id,
            title=story["title"],
            url=story.get("url") or discussion_url,
            discussion_url=discussion_url,
            author=story.get("by"),
            content=_clean_html(story.get("text")),
            published_at=published,
            created_at=published,
            event_type="discussion_created",
            metrics=SourceMetrics(score=story.get("score"), comments=story.get("descendants")),
            is_primary_source=False,
        ))
        if len(result) >= settings.max_items_per_source:
            break
    return result


async def collect_rss(task: MonitoringTask, settings: Settings) -> list[SourceItem]:
    feed_urls = task.rss_feeds or settings.rss_feeds
    if not feed_urls:
        return []
    cutoff = utc_now() - timedelta(hours=task.time_window_hours)
    keywords = [word.lower() for word in task.keywords]
    result: list[SourceItem] = []
    per_feed_limit = max(4, settings.max_items_per_source // len(feed_urls))
    async with httpx.AsyncClient(timeout=settings.request_timeout_seconds, follow_redirects=True) as client:
        for feed_url in feed_urls:
            try:
                response = await client.get(feed_url, headers={"User-Agent": "TrendScope/0.2 (public-source research agent)"})
                response.raise_for_status()
                parsed = feedparser.parse(response.content)
            except (httpx.HTTPError, ValueError):
                # 某个订阅源异常时继续读取同一行业的其他权威源。
                continue
            feed_count = 0
            for entry in parsed.entries:
                title = str(entry.get("title", "")).strip()
                link = str(entry.get("link", "")).strip()
                content = _clean_html(entry.get("summary") or entry.get("description"))
                published_raw = entry.get("published") or entry.get("updated")
                if not published_raw:
                    continue
                published = _safe_datetime(published_raw)
                if not title or not link or published < cutoff:
                    continue
                if not any(keyword in f"{title} {content}".lower() for keyword in keywords):
                    continue
                result.append(SourceItem(
                    source="rss",
                    external_id=str(entry.get("id") or link),
                    title=title,
                    url=link,
                    author=entry.get("author"),
                    content=content,
                    published_at=published,
                    created_at=published,
                    event_type="news_published",
                    is_primary_source=_is_primary_rss_source(link or feed_url),
                ))
                feed_count += 1
                if feed_count >= per_feed_limit:
                    break
    return sorted(result, key=lambda item: item.published_at, reverse=True)[:settings.max_items_per_source]


async def collect_google_news(task: MonitoringTask, settings: Settings) -> list[SourceItem]:
    """Google News RSS 是新闻发现源，不是官方事实来源。"""
    terms = [task.topic, *task.keywords[:4]]
    terms = [term for term in terms if len(term.strip()) >= 2]
    query = " OR ".join(f'"{term}"' if " " in term else term for term in terms) + " when:7d"
    encoded = quote_plus(query)
    feed_urls = [
        f"https://news.google.com/rss/search?q={encoded}&hl=en-US&gl=US&ceid=US:en",
        f"https://news.google.com/rss/search?q={encoded}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
    ]
    cutoff = utc_now() - timedelta(hours=task.time_window_hours)
    results: list[SourceItem] = []
    async with httpx.AsyncClient(timeout=settings.request_timeout_seconds, follow_redirects=True) as client:
        for feed_url in feed_urls:
            response = await client.get(feed_url, headers={"User-Agent": "TrendScope/0.3"})
            response.raise_for_status()
            parsed = feedparser.parse(response.content)
            for entry in parsed.entries[: settings.max_items_per_source]:
                published = _safe_datetime(entry.get("published") or entry.get("updated"))
                if published < cutoff:
                    continue
                source = entry.get("source") or {}
                publisher = str(source.get("title") or "Google News")
                raw_title = str(entry.get("title") or "").strip()
                suffix = f" - {publisher}"
                title = raw_title[:-len(suffix)] if raw_title.endswith(suffix) else raw_title
                link = str(entry.get("link") or "").strip()
                if not title or not link:
                    continue
                results.append(SourceItem(
                    source="google_news",
                    external_id=str(entry.get("id") or link),
                    title=title,
                    url=link,
                    author=publisher,
                    content=_clean_html(entry.get("summary")),
                    published_at=published,
                    created_at=published,
                    event_type="news_published",
                    is_primary_source=False,
                ))
    unique: dict[str, SourceItem] = {}
    for item in sorted(results, key=lambda value: value.published_at, reverse=True):
        unique.setdefault(item.external_id, item)
    return list(unique.values())[:settings.max_items_per_source]


async def collect_google_trends(task: MonitoringTask, settings: Settings) -> list[SourceItem]:
    """引入 Google Trends 真实搜索趋势；仍由相关性门槛决定是否入榜。"""
    feed_url = "https://trends.google.com/trending/rss?geo=US"
    async with httpx.AsyncClient(timeout=settings.request_timeout_seconds, follow_redirects=True) as client:
        response = await client.get(feed_url, headers={"User-Agent": "TrendScope/0.3"})
        response.raise_for_status()
    parsed = feedparser.parse(response.content)
    results: list[SourceItem] = []
    for entry in parsed.entries[: settings.max_items_per_source]:
        title = str(entry.get("title") or "").strip()
        if not title:
            continue
        traffic_text = str(entry.get("ht_approx_traffic") or "0")
        traffic = int(re.sub(r"[^0-9]", "", traffic_text) or 0)
        published = _safe_datetime(entry.get("published") or entry.get("updated"))
        results.append(SourceItem(
            source="google_trends",
            external_id=f"US:{published.date().isoformat()}:{normalize_google_trend_id(title)}",
            title=title,
            url=f"https://trends.google.com/trends/explore?q={quote_plus(title)}&geo=US",
            content=f"Google Trends US approximate search traffic: {traffic_text}",
            published_at=published,
            created_at=published,
            event_type="discussion_created",
            metrics=SourceMetrics(score=traffic),
            is_primary_source=False,
        ))
    return results


async def collect_arxiv(task: MonitoringTask, settings: Settings) -> list[SourceItem]:
    """arXiv 作为论文首发源，用于发现早期研究信号，不等同于产业热点。"""
    terms = [task.topic, *task.keywords[:3]]
    query = " OR ".join(f'all:"{term}"' for term in terms if term.strip())
    params = {
        "search_query": query, "start": "0",
        "max_results": str(min(settings.max_items_per_source, 15)),
        "sortBy": "submittedDate", "sortOrder": "descending",
    }
    async with httpx.AsyncClient(timeout=settings.request_timeout_seconds, follow_redirects=True) as client:
        response = await client.get("https://export.arxiv.org/api/query", params=params, headers={"User-Agent": "TrendScope/0.4"})
        response.raise_for_status()
    parsed = feedparser.parse(response.content)
    cutoff = utc_now() - timedelta(hours=task.time_window_hours)
    results: list[SourceItem] = []
    for entry in parsed.entries:
        title = re.sub(r"\s+", " ", str(entry.get("title") or "")).strip()
        url = str(entry.get("link") or entry.get("id") or "").strip()
        published = _safe_datetime(entry.get("published") or entry.get("updated"))
        if not title or not url or published < cutoff:
            continue
        results.append(SourceItem(
            source="arxiv", external_id=str(entry.get("id") or url), title=title, url=url,
            author=", ".join(str(author.get("name")) for author in entry.get("authors", [])[:4]),
            content=_clean_html(entry.get("summary")), published_at=published, created_at=published,
            event_type="paper_published", is_primary_source=True,
        ))
    return results[: settings.max_items_per_source]


async def collect_devto(task: MonitoringTask, settings: Settings) -> list[SourceItem]:
    """DEV Community 提供开发者实践和早期采用信号，仅用于科技与 AI 任务。"""
    tag = "ai" if task.id in {1, 5} else "programming"
    params = {"tag": tag, "per_page": min(settings.max_items_per_source, 20), "top": 7}
    async with httpx.AsyncClient(timeout=settings.request_timeout_seconds, follow_redirects=True) as client:
        response = await client.get("https://dev.to/api/articles", params=params, headers={"User-Agent": "TrendScope/0.4"})
        response.raise_for_status()
        articles = response.json()
    cutoff = utc_now() - timedelta(hours=task.time_window_hours)
    keywords = [normalize_google_trend_id(word).replace("-", " ") for word in task.keywords]
    results: list[SourceItem] = []
    for article in articles:
        title = str(article.get("title") or "").strip()
        description = str(article.get("description") or "").strip()
        haystack = f"{title} {description} {' '.join(article.get('tag_list') or [])}".lower()
        if not any(keyword in haystack for keyword in keywords if keyword):
            continue
        published = _safe_datetime(article.get("published_at") or article.get("created_at"))
        if published < cutoff:
            continue
        results.append(SourceItem(
            source="devto", external_id=str(article["id"]), title=title, url=str(article.get("url") or ""),
            author=str((article.get("user") or {}).get("username") or ""), content=description,
            published_at=published, created_at=published, event_type="article_published",
            metrics=SourceMetrics(score=article.get("public_reactions_count"), comments=article.get("comments_count")),
            is_primary_source=False,
        ))
    return results[: settings.max_items_per_source]


async def collect_v2ex(task: MonitoringTask, settings: Settings) -> list[SourceItem]:
    """V2EX 公开 API 提供中文开发者讨论信号。"""
    nodes = ["programmer", "create", "python"]
    cutoff = utc_now() - timedelta(hours=task.time_window_hours)
    keywords = [word.lower() for word in task.keywords]
    results: list[SourceItem] = []
    async with httpx.AsyncClient(timeout=settings.request_timeout_seconds, follow_redirects=True) as client:
        for node in nodes:
            response = await client.get(
                "https://www.v2ex.com/api/topics/show.json", params={"node_name": node, "page": 1},
                headers={"User-Agent": "TrendScope/0.4"},
            )
            response.raise_for_status()
            for topic in response.json():
                title = str(topic.get("title") or "").strip()
                content = _clean_html(topic.get("content_rendered") or topic.get("content"))
                if not any(keyword in f"{title} {content}".lower() for keyword in keywords):
                    continue
                published = datetime.fromtimestamp(int(topic.get("created") or 0), tz=timezone.utc)
                if published < cutoff:
                    continue
                topic_id = str(topic["id"])
                results.append(SourceItem(
                    source="v2ex", external_id=topic_id, title=title,
                    url=str(topic.get("url") or f"https://www.v2ex.com/t/{topic_id}"),
                    author=str((topic.get("member") or {}).get("username") or ""), content=content,
                    published_at=published, created_at=published, event_type="discussion_created",
                    metrics=SourceMetrics(comments=topic.get("replies")), is_primary_source=False,
                ))
    unique = {item.external_id: item for item in results}
    return sorted(unique.values(), key=lambda item: item.published_at, reverse=True)[: settings.max_items_per_source]


def _parse_compact_count(value: object) -> int:
    text = str(value or "0").strip().lower().replace(",", "")
    multiplier = 10000 if "万" in text else 1000 if "k" in text else 1
    match = re.search(r"[0-9.]+", text)
    return int(float(match.group()) * multiplier) if match else 0


async def collect_bilibili(task: MonitoringTask, settings: Settings) -> list[SourceItem]:
    """B站搜索用于中文内容传播信号；搜索命中不等于事实已被证实。"""
    params = {
        "search_type": "video", "keyword": task.topic, "page": 1,
        "page_size": min(settings.max_items_per_source, 20), "order": "pubdate",
    }
    headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://search.bilibili.com/"}
    async with httpx.AsyncClient(timeout=settings.request_timeout_seconds, follow_redirects=True) as client:
        response = await client.get("https://api.bilibili.com/x/web-interface/search/type", params=params, headers=headers)
        response.raise_for_status()
        payload = response.json()
    if payload.get("code") != 0:
        raise ValueError(f"Bilibili API error: {payload.get('message')}")
    cutoff = utc_now() - timedelta(hours=task.time_window_hours)
    results: list[SourceItem] = []
    for video in (payload.get("data") or {}).get("result") or []:
        published = datetime.fromtimestamp(int(video.get("pubdate") or 0), tz=timezone.utc)
        if published < cutoff:
            continue
        bvid = str(video.get("bvid") or "")
        title = _clean_html(video.get("title"))
        if not bvid or not title:
            continue
        results.append(SourceItem(
            source="bilibili", external_id=bvid, title=title, url=f"https://www.bilibili.com/video/{bvid}",
            author=str(video.get("author") or ""), content=_clean_html(video.get("description")),
            published_at=published, created_at=published, event_type="video_published",
            metrics=SourceMetrics(score=_parse_compact_count(video.get("play")), comments=_parse_compact_count(video.get("danmaku"))),
            is_primary_source=False,
        ))
    return results


async def collect_chinanews(task: MonitoringTask, settings: Settings) -> list[SourceItem]:
    """中国新闻网官方主题搜索优先，官方 RSS 补充，并保留平台身份。"""
    feed_path = "finance.xml" if task.id == 3 else "health.xml" if task.id == 4 else "scroll-news.xml"
    feed_url = f"https://www.chinanews.com.cn/rss/{feed_path}"
    async with httpx.AsyncClient(timeout=settings.request_timeout_seconds, follow_redirects=True) as client:
        rss_response, search_response = await asyncio.gather(
            client.get(feed_url, headers={"User-Agent": "TrendScope/0.4"}),
            client.get("https://sou.chinanews.com.cn/search.do", params={"q": task.topic}, headers={"User-Agent": "TrendScope/0.4"}),
        )
        rss_response.raise_for_status()
        search_response.raise_for_status()
    cutoff = utc_now() - timedelta(hours=task.time_window_hours)
    keywords = [word.lower() for word in task.keywords]
    results: list[SourceItem] = []
    china_tz = timezone(timedelta(hours=8))
    search_match = re.search(r"var\s+docArr\s*=\s*(\[.*?\]);", search_response.text, flags=re.DOTALL)
    if search_match:
        for article in json.loads(search_match.group(1)):
            title = _clean_html(article.get("title"))
            url = str(article.get("url") or "").replace("http://", "https://", 1)
            content = _clean_html(article.get("content_without_tag"))
            try:
                published = datetime.fromisoformat(str(article.get("pubtime"))).replace(tzinfo=china_tz).astimezone(timezone.utc)
            except ValueError:
                continue
            if not title or not url or published < cutoff:
                continue
            results.append(SourceItem(
                source="chinanews", external_id=str(article.get("unique_id") or url), title=title, url=url,
                author="中国新闻网", content=content, published_at=published, created_at=published,
                event_type="news_published", is_primary_source=True,
            ))

    parsed = feedparser.parse(rss_response.content)
    for entry in parsed.entries:
        title = str(entry.get("title") or "").strip()
        url = str(entry.get("link") or "").strip()
        content = _clean_html(entry.get("summary") or entry.get("description"))
        published = _safe_datetime(entry.get("published") or entry.get("updated"))
        if not title or not url or published < cutoff:
            continue
        if not any(keyword in f"{title} {content}".lower() for keyword in keywords):
            continue
        if any(item.url == url for item in results):
            continue
        results.append(SourceItem(
            source="chinanews", external_id=str(entry.get("id") or url), title=title, url=url,
            author="中国新闻网", content=content, published_at=published, created_at=published,
            event_type="news_published", is_primary_source=True,
        ))
    return sorted(results, key=lambda item: item.published_at, reverse=True)[: settings.max_items_per_source]


async def collect_cctv_news(task: MonitoringTask, settings: Settings) -> list[SourceItem]:
    """央视网新闻公开列表接口；按行业选择科技、经济或健康频道。"""
    category = "economy" if task.id == 3 else "health" if task.id == 4 else "tech"
    endpoint = f"https://news.cctv.com/2019/07/gaiban/cmsdatainterface/page/{category}_1.jsonp"
    async with httpx.AsyncClient(timeout=settings.request_timeout_seconds, follow_redirects=True) as client:
        response = await client.get(endpoint, headers={"User-Agent": "TrendScope/0.4", "Referer": "https://news.cctv.com/"})
        response.raise_for_status()
    match = re.match(r"^\w+\((.*)\)\s*;?\s*$", response.text, flags=re.DOTALL)
    if not match:
        raise ValueError("央视新闻接口返回了无法识别的 JSONP")
    payload = json.loads(match.group(1))
    cutoff = utc_now() - timedelta(hours=task.time_window_hours)
    keywords = [word.lower() for word in task.keywords]
    china_tz = timezone(timedelta(hours=8))
    results: list[SourceItem] = []
    for article in (payload.get("data") or {}).get("list") or []:
        title = str(article.get("title") or "").strip()
        url = str(article.get("url") or "").strip()
        content = _clean_html(article.get("brief"))
        keyword_text = str(article.get("keywords") or "")
        try:
            published = datetime.fromisoformat(str(article.get("focus_date"))).replace(tzinfo=china_tz).astimezone(timezone.utc)
        except ValueError:
            continue
        if not title or not url or published < cutoff:
            continue
        if not any(keyword in f"{title} {content} {keyword_text}".lower() for keyword in keywords):
            continue
        results.append(SourceItem(
            source="cctv_news", external_id=str(article.get("id") or url), title=title, url=url,
            author="央视网新闻", content=content, published_at=published, created_at=published,
            event_type="news_published", is_primary_source=True,
        ))
        if len(results) >= settings.max_items_per_source:
            break
    return results


def normalize_google_trend_id(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


Collector = Callable[[MonitoringTask, Settings], Awaitable[list[SourceItem]]]


async def collect_all(
    task: MonitoringTask,
    settings: Settings,
    on_result: Callable[[str, int, str | None], None] | None = None,
) -> list[SourceItem]:
    collectors: list[tuple[str, Collector]] = [
        ("GitHub", collect_github),
        ("Hacker News", collect_hacker_news),
        ("Google News", collect_google_news),
        ("Google Trends", collect_google_trends),
        ("arXiv", collect_arxiv),
        ("中国新闻网", collect_chinanews),
        ("央视新闻", collect_cctv_news),
    ]
    if task.id in {1, 2, 5}:
        collectors.extend([
            ("DEV Community", collect_devto),
            ("V2EX", collect_v2ex),
            ("Bilibili", collect_bilibili),
        ])
    if task.rss_feeds or settings.rss_feeds:
        collectors.append(("RSS", collect_rss))

    async def guarded(name: str, collector: Collector) -> list[SourceItem]:
        try:
            items = await collector(task, settings)
            if on_result:
                on_result(name, len(items), None)
            return items
        except Exception as exc:  # 单个来源失败不能拖垮整轮任务
            if on_result:
                on_result(name, 0, f"{type(exc).__name__}: {exc}")
            return []

    groups = await asyncio.gather(*(guarded(name, collector) for name, collector in collectors))
    return [item for group in groups for item in group]
