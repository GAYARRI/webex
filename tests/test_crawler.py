import unittest

from src.crawler import SiteCrawl, discover_links, _normalize, _domain, _should_skip


class DiscoverLinksTests(unittest.TestCase):
    def test_returns_same_domain_links(self):
        html = '<a href="/about">About</a><a href="https://example.com/contact">Contact</a>'
        links = discover_links(html, "https://example.com/", "https://example.com/")
        self.assertIn("https://example.com/about", links)
        self.assertIn("https://example.com/contact", links)

    def test_excludes_external_links(self):
        html = '<a href="https://other.com/page">External</a>'
        links = discover_links(html, "https://example.com/", "https://example.com/")
        self.assertEqual(links, [])

    def test_excludes_mailto_and_tel(self):
        html = '<a href="mailto:a@b.com">Mail</a><a href="tel:123">Tel</a>'
        links = discover_links(html, "https://example.com/", "https://example.com/")
        self.assertEqual(links, [])

    def test_excludes_static_assets(self):
        html = '<a href="/image.jpg">Img</a><a href="/doc.pdf">PDF</a>'
        links = discover_links(html, "https://example.com/", "https://example.com/")
        self.assertEqual(links, [])

    def test_excludes_system_segments(self):
        html = '<a href="/admin/panel">Admin</a><a href="/login">Login</a>'
        links = discover_links(html, "https://example.com/", "https://example.com/")
        self.assertEqual(links, [])

    def test_normalizes_trailing_slash(self):
        html = '<a href="/page/">Page</a>'
        links = discover_links(html, "https://example.com/", "https://example.com/")
        self.assertIn("https://example.com/page", links)

    def test_strips_fragment_and_query(self):
        html = '<a href="/page?ref=1#section">Page</a>'
        links = discover_links(html, "https://example.com/", "https://example.com/")
        self.assertIn("https://example.com/page", links)

    def test_www_treated_as_same_domain(self):
        html = '<a href="https://www.example.com/page">Page</a>'
        links = discover_links(html, "https://example.com/", "https://example.com/")
        self.assertIn("https://www.example.com/page", links)


class SiteCrawlTests(unittest.TestCase):
    def test_yields_home_url_first(self):
        crawl = SiteCrawl("https://example.com/", max_pages=10)
        first = next(crawl)
        self.assertIn("example.com", first)

    def test_respects_max_pages(self):
        crawl = SiteCrawl("https://example.com/", max_pages=2)
        html_with_links = (
            '<a href="/p1">P1</a><a href="/p2">P2</a>'
            '<a href="/p3">P3</a><a href="/p4">P4</a>'
        )
        urls = []
        for url in crawl:
            urls.append(url)
            crawl.feed(html_with_links, url)
        self.assertEqual(len(urls), 2)

    def test_does_not_revisit_urls(self):
        crawl = SiteCrawl("https://example.com/", max_pages=10)
        html = '<a href="https://example.com">Home</a><a href="/p1">P1</a>'
        visited = []
        for url in crawl:
            visited.append(url)
            crawl.feed(html, url)
            if len(visited) >= 3:
                break
        self.assertEqual(len(set(visited)), len(visited))

    def test_visited_count_property(self):
        crawl = SiteCrawl("https://example.com/", max_pages=5)
        list(crawl)
        self.assertEqual(crawl.visited_count, 1)

    def test_stops_when_queue_empty(self):
        crawl = SiteCrawl("https://example.com/", max_pages=10)
        urls = list(crawl)
        self.assertEqual(len(urls), 1)


class NormalizeTests(unittest.TestCase):
    def test_strips_fragment(self):
        self.assertEqual(_normalize("https://x.com/p#s"), "https://x.com/p")

    def test_strips_query(self):
        self.assertEqual(_normalize("https://x.com/p?q=1"), "https://x.com/p")

    def test_strips_trailing_slash(self):
        self.assertEqual(_normalize("https://x.com/p/"), "https://x.com/p")

    def test_keeps_root_slash(self):
        result = _normalize("https://x.com/")
        self.assertIn("x.com", result)

    def test_returns_none_for_non_http(self):
        self.assertIsNone(_normalize("ftp://x.com/"))


class ShouldSkipTests(unittest.TestCase):
    def test_skips_pdf(self):
        self.assertTrue(_should_skip("https://x.com/file.pdf"))

    def test_skips_admin_segment(self):
        self.assertTrue(_should_skip("https://x.com/admin/users"))

    def test_does_not_skip_normal_page(self):
        self.assertFalse(_should_skip("https://x.com/about-us"))


if __name__ == "__main__":
    unittest.main()
