from collections import deque
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
import threading

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter

from app.utils import normalize_url, should_crawl


class SiteCrawler:
    def __init__(
        self,
        root_url: str,
        max_pages: int = 50,
        max_workers: int = 8,
        timeout: int = 10,
        verify_ssl: bool = True,
    ):
        self.root_url = root_url
        self.max_pages = max_pages
        self.max_workers = max_workers
        self.timeout = timeout
        self.verify_ssl = verify_ssl
        self._local = threading.local()

    def _get_session(self) -> requests.Session:
        session = getattr(self._local, "session", None)
        if session is not None:
            return session

        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": "BrokenLinkChecker/1.0 (+https://example.local)",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
        )
        pool_size = max(10, self.max_workers * 2)
        adapter = HTTPAdapter(pool_connections=pool_size, pool_maxsize=pool_size)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        self._local.session = session
        return session

    def fetch_html(self, url: str) -> str | None:
        session = self._get_session()
        response = session.get(url, timeout=self.timeout, verify=self.verify_ssl)
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "")
        if "text/html" not in content_type:
            return None
        return response.text

    def extract_links(self, source_url: str, html: str) -> list[tuple[str, str, str]]:
        soup = BeautifulSoup(html, "lxml")
        links: list[tuple[str, str, str]] = []
        for a_tag in soup.find_all("a", href=True):
            href = a_tag.get("href", "")
            target_url = normalize_url(source_url, href)
            if not target_url:
                continue
            anchor_text = a_tag.get_text(" ", strip=True)
            links.append((source_url, target_url, anchor_text))
        return links

    def crawl(self) -> tuple[list[str], list[tuple[str, str, str]], list[str]]:
        visited: set[str] = set()
        queue = deque([self.root_url])
        page_urls: list[str] = []
        all_links: list[tuple[str, str, str]] = []
        crawl_errors: list[str] = []

        in_flight: dict[Future[str | None], str] = {}
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            while (queue or in_flight) and len(page_urls) < self.max_pages:
                while (
                    queue
                    and len(in_flight) < self.max_workers
                    and (len(page_urls) + len(in_flight)) < self.max_pages
                ):
                    current = queue.popleft()
                    if current in visited:
                        continue
                    visited.add(current)
                    in_flight[executor.submit(self.fetch_html, current)] = current

                if not in_flight:
                    continue

                done, _pending = wait(in_flight.keys(), return_when=FIRST_COMPLETED)
                for future in done:
                    current = in_flight.pop(future)
                    try:
                        html = future.result()
                        if html is None:
                            continue

                        page_urls.append(current)
                        page_links = self.extract_links(current, html)
                        all_links.extend(page_links)

                        for _source, target, _text in page_links:
                            if target not in visited and should_crawl(target, self.root_url):
                                queue.append(target)
                    except requests.RequestException as exc:
                        crawl_errors.append(f"{current}: {exc}")
                    if len(page_urls) >= self.max_pages:
                        break

        return page_urls, all_links, crawl_errors
