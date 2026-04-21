from app.utils import is_same_domain, normalize_url


def test_normalize_url_relative():
    result = normalize_url("https://example.com/docs/", "page.html")
    assert result == "https://example.com/docs/page.html"


def test_normalize_url_fragment_removed():
    result = normalize_url("https://example.com", "https://example.com/page#section")
    assert result == "https://example.com/page"


def test_is_same_domain_true():
    assert is_same_domain("https://example.com/a", "https://example.com/b") is True


def test_is_same_domain_false():
    assert is_same_domain("https://example.com", "https://other.com") is False
