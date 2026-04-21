import time
import threading
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from requests import Response
from requests.adapters import HTTPAdapter
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.models import LinkResult
from app.utils import is_same_domain

DEFAULT_HEADERS = {
    "User-Agent": "BrokenLinkChecker/1.0 (+https://example.local)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}

TIMEOUT = 10
BROKEN_STATUS_CODES = {404, 410, 500, 502, 503, 504}
BLOCKED_STATUS_CODES = {401, 403, 429}


class LinkChecker:
    def __init__(self, max_workers: int = 10, verify_ssl: bool = True):
        self.max_workers = max_workers
        self.verify_ssl = verify_ssl
        self._local = threading.local()

    def _get_session(self) -> requests.Session:
        session = getattr(self._local, "session", None)
        if session is not None:
            return session

        session = requests.Session()
        session.headers.update(DEFAULT_HEADERS)
        # A session (and its connection pool) is not guaranteed to be thread-safe across workers.
        # Use a per-thread session with a tuned pool to improve throughput.
        pool_size = max(10, self.max_workers * 2)
        adapter = HTTPAdapter(pool_connections=pool_size, pool_maxsize=pool_size)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        self._local.session = session
        return session

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        retry=retry_if_exception_type((requests.RequestException,)),
        reraise=True,
    )
    def _request(self, url: str) -> Response:
        session = self._get_session()
        try:
            response = session.head(
                url,
                allow_redirects=True,
                timeout=TIMEOUT,
                verify=self.verify_ssl,
            )
            if response.status_code == 405:
                response = session.get(
                    url,
                    allow_redirects=True,
                    timeout=TIMEOUT,
                    verify=self.verify_ssl,
                )
            # Some sites block non-browser clients on HEAD or return a false 403/401/429.
            # Retry with GET once to reduce false positives.
            elif response.status_code in BLOCKED_STATUS_CODES:
                response = session.get(
                    url,
                    allow_redirects=True,
                    timeout=TIMEOUT,
                    verify=self.verify_ssl,
                )
            return response
        except requests.RequestException:
            raise

    def _check_target(
        self,
        target_url: str,
        root_url: str,
    ) -> tuple[int | None, bool, bool, str | None, float | None]:
        start = time.perf_counter()
        try:
            response = self._request(target_url)
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
            is_blocked = response.status_code in BLOCKED_STATUS_CODES
            # "Blocked" is different from "broken": it often means bot protection / auth required.
            broken = (response.status_code in BROKEN_STATUS_CODES or response.status_code >= 400) and not is_blocked
            return response.status_code, broken, is_blocked, None, elapsed_ms
        except requests.RequestException as exc:
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
            return None, True, False, str(exc), elapsed_ms

    def check_one(self, source_url: str, target_url: str, anchor_text: str, root_url: str) -> LinkResult:
        status_code, broken, is_blocked, error, elapsed_ms = self._check_target(target_url, root_url)
        return LinkResult(
            source_url=source_url,
            target_url=target_url,
            anchor_text=anchor_text,
            status_code=status_code,
            is_broken=broken,
            is_blocked=is_blocked,
            error=error,
            is_internal=is_same_domain(target_url, root_url),
            response_time_ms=elapsed_ms,
        )

    def iter_check_many(self, links: list[tuple[str, str, str]], root_url: str) -> Iterator[tuple[str, list[LinkResult]]]:
        """
        Stream results as each unique target URL completes.

        Yields:
          (target_url, results_for_all_occurrences)
        """
        link_groups: dict[str, list[tuple[str, str]]] = {}
        for source_url, target_url, anchor_text in links:
            link_groups.setdefault(target_url, []).append((source_url, anchor_text))

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(self._check_target, target_url, root_url): target_url
                for target_url in link_groups.keys()
            }
            for future in as_completed(futures):
                target_url = futures[future]
                status_code, broken, is_blocked, error, elapsed_ms = future.result()
                internal = is_same_domain(target_url, root_url)

                results_for_target: list[LinkResult] = []
                for source_url, anchor_text in link_groups[target_url]:
                    results_for_target.append(
                        LinkResult(
                            source_url=source_url,
                            target_url=target_url,
                            anchor_text=anchor_text,
                            status_code=status_code,
                            is_broken=broken,
                            is_blocked=is_blocked,
                            error=error,
                            is_internal=internal,
                            response_time_ms=elapsed_ms,
                        )
                    )

                yield target_url, results_for_target

    def check_many(self, links: list[tuple[str, str, str]], root_url: str) -> list[LinkResult]:
        results: list[LinkResult] = []
        for _target_url, items in self.iter_check_many(links, root_url):
            results.extend(items)
        return results
