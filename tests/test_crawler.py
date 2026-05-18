import unittest

from src.crawler import SiteCrawl, discover_links, _normalize, _domain, _should_skip, _parse_sitemap_xml


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


class SitemapParseTests(unittest.TestCase):
    _HOME = "https://example.com"

    def _urlset(self, *locs: str) -> str:
        items = "".join(f"<url><loc>{loc}</loc></url>" for loc in locs)
        return f'<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{items}</urlset>'

    def test_parses_urlset(self):
        xml = self._urlset("https://example.com/page1", "https://example.com/page2")
        urls = _parse_sitemap_xml(xml, self._HOME)
        self.assertIn("https://example.com/page1", urls)
        self.assertIn("https://example.com/page2", urls)

    def test_excludes_external_urls(self):
        xml = self._urlset("https://example.com/p1", "https://other.com/p2")
        urls = _parse_sitemap_xml(xml, self._HOME)
        self.assertEqual(urls, ["https://example.com/p1"])

    def test_excludes_static_assets(self):
        xml = self._urlset("https://example.com/page", "https://example.com/img.jpg")
        urls = _parse_sitemap_xml(xml, self._HOME)
        self.assertEqual(urls, ["https://example.com/page"])

    def test_normalizes_trailing_slash(self):
        xml = self._urlset("https://example.com/page/")
        urls = _parse_sitemap_xml(xml, self._HOME)
        self.assertIn("https://example.com/page", urls)

    def test_returns_empty_on_invalid_xml(self):
        urls = _parse_sitemap_xml("not xml at all", self._HOME)
        self.assertEqual(urls, [])

    def test_returns_empty_on_empty_string(self):
        urls = _parse_sitemap_xml("", self._HOME)
        self.assertEqual(urls, [])

    def test_sitecrawl_without_sitemap_has_zero_count(self):
        crawl = SiteCrawl("https://example.com/", max_pages=5, use_sitemap=False)
        self.assertEqual(crawl.sitemap_urls_found, 0)

    def test_sitecrawl_seeds_queue_with_sitemap_urls(self):
        # Inject sitemap URLs manually by monkey-patching fetch
        import src.crawler as _crawler
        original = _crawler.fetch_sitemap_urls
        try:
            _crawler.fetch_sitemap_urls = lambda *a, **kw: [
                "https://example.com/p1",
                "https://example.com/p2",
            ]
            crawl = SiteCrawl("https://example.com/", max_pages=10, use_sitemap=True)
            self.assertEqual(crawl.sitemap_urls_found, 2)
            urls = list(crawl)
            self.assertIn("https://example.com/p1", urls)
            self.assertIn("https://example.com/p2", urls)
        finally:
            _crawler.fetch_sitemap_urls = original


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
