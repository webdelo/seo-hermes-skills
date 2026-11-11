import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).with_name("extract_page_text.py")
SPEC = importlib.util.spec_from_file_location("extract_page_text", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class ExtractPageTextTests(unittest.TestCase):
    def extract(self, html, **kwargs):
        return MOD.extract_html(html.encode("utf-8"), source="fixture", **kwargs)

    def test_prefers_h1_and_stops_before_related_and_comments(self):
        html = """
        <html><body>
          <header><h2>Header teaser</h2></header>
          <main>
            <h1>Main title</h1>
            <p>First paragraph.</p>
            <ul><li>Alpha</li><li>Beta</li></ul>
            <div>Simple direct text <span>with inline detail</span>.</div>
            <table><caption>Prices</caption><tr><th>Plan</th><th>Price</th></tr><tr><td>Pro</td><td>10</td></tr></table>
            <section class="related-articles"><h2>Related articles</h2><p>Must not appear.</p></section>
            <section id="comments"><p>Comment must not appear.</p></section>
          </main>
        </body></html>
        """
        data = self.extract(html)
        text = data["text"]
        self.assertEqual(data["start"]["tag"], "h1")
        self.assertIn("Main title", text)
        self.assertIn("First paragraph.", text)
        self.assertIn("- Alpha", text)
        self.assertIn("Simple direct text with inline detail.", text)
        self.assertIn("Plan\tPrice", text)
        self.assertNotIn("Header teaser", text)
        self.assertNotIn("Must not appear", text)
        self.assertNotIn("Comment must not appear", text)
        self.assertEqual(data["stop"]["reason"], "related-articles")

    def test_excludes_alt_and_media_attributes(self):
        html = """
        <h1>Title</h1>
        <p>Visible copy.</p>
        <img alt="SECRET IMAGE ALT" title="IMAGE TITLE">
        <video aria-label="SECRET VIDEO"><track label="SECRET TRACK"></video>
        <p>After media.</p>
        """
        data = self.extract(html)
        text = data["text"]
        self.assertIn("Visible copy.", text)
        self.assertIn("After media.", text)
        self.assertNotIn("SECRET", text)
        self.assertNotIn("IMAGE TITLE", text)

    def test_falls_back_to_first_h2_when_h1_missing(self):
        data = self.extract("<h2>Fallback</h2><p>Body</p>")
        self.assertEqual(data["start"]["tag"], "h2")
        self.assertIn("Body", data["text"])
        self.assertIn("no_h1", data["warnings"])

    def test_no_heading_does_not_scrape_whole_page(self):
        data = self.extract("<p>Orphan copy</p>")
        self.assertEqual(data["error"], "no_start_heading")
        self.assertEqual(data["text"], "")
        self.assertEqual(data["blocks"], [])

    def test_stops_before_article_footer(self):
        html = "<h1>T</h1><p>Keep</p><div class='article-detail__footer'><p>Rating</p></div><section><p>Related</p></section>"
        data = self.extract(html)
        self.assertIn("Keep", data["text"])
        self.assertNotIn("Rating", data["text"])
        self.assertNotIn("Related", data["text"])
        self.assertEqual(data["stop"]["reason"], "article-detail-footer")

    def test_custom_stop_token(self):
        html = "<h1>T</h1><p>Keep</p><div class='promo-grid'><p>Drop</p></div><p>Also drop</p>"
        data = self.extract(html, extra_stop_tokens=["promo-grid"])
        self.assertIn("Keep", data["text"])
        self.assertNotIn("Drop", data["text"])
        self.assertNotIn("Also drop", data["text"])
        self.assertEqual(data["stop"]["reason"], "promo-grid")


if __name__ == "__main__":
    unittest.main()
