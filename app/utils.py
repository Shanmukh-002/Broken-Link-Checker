from urllib.parse import urldefrag, urljoin, urlparse

import validators


IGNORED_SCHEMES = {"mailto", "tel", "javascript"}


def normalize_url(base_url: str, href: str) -> str | None:
    """Resolve relative URLs and remove fragments."""
    if not href:
        return None

    href = href.strip()
    parsed = urlparse(href)

    if parsed.scheme in IGNORED_SCHEMES:
        return None

    absolute = urljoin(base_url, href)
    absolute, _fragment = urldefrag(absolute)

    if not validators.url(absolute):
        return None

    return absolute


def is_same_domain(url_a: str, url_b: str) -> bool:
    return urlparse(url_a).netloc == urlparse(url_b).netloc


def should_crawl(url: str, root_url: str, include_subpaths_only: bool = True) -> bool:
    if not is_same_domain(url, root_url):
        return False

    if not include_subpaths_only:
        return True

    root_path = urlparse(root_url).path.rstrip("/")
    url_path = urlparse(url).path.rstrip("/")
    return url_path.startswith(root_path) if root_path else True
