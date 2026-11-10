"""Synthetic tests only: no live API calls and no real credentials."""
import csv
from contextlib import redirect_stderr
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import compare_backlinks as cb


SPEC = {
    "focal_domain": "focus.example",
    "clusters": {
        "doors": [
            "http://focus.example/doors",
            "https://competitor.example/doors?type=oak",
        ]
    },
}


def fixture_payload():
    return {
        "collected_at": "2026-01-01T00:00:00+00:00",
        "ahrefs": {
            "domain_ratings": {
                "focus.example": {"domain_rating": 42},
                "competitor.example": {"domain_rating": 55},
            },
            "backlinks": {
                "http://focus.example/doors": [
                    {
                        "url_from": "https://News.Example/posts/oak-guide",
                        "url_to": "https://focus.example/doors",
                        "first_seen_link": "2025-01-01T00:00:00+00:00",
                        "title": "Oak guide",
                    },
                    {
                        "url_from": "https://news.example/posts/second",
                        "url_to": "http://focus.example/doors",
                        "first_seen_link": "2025-07-02T00:00:00+00:00",
                        "title": "Second guide",
                    },
                    {
                        "url_from": "https://profiles.example/users/alice",
                        "url_to": "http://focus.example/doors",
                        "first_seen_link": "2025-07-01T00:00:00+00:00",
                    },
                ],
                "https://competitor.example/doors?type=oak": [
                    {
                        "url_from": "https://casino-spam.example/buy-links",
                        "url_to": "https://competitor.example/final-doors",
                        "first_seen_link": "2025-12-30T00:00:00+00:00",
                    },
                    {
                        "url_from": "https://brand.example/",
                        "url_to": "https://competitor.example/doors?type=oak",
                        "first_seen_link": "2024-01-01T00:00:00+00:00",
                    },
                ],
            },
        },
        "dataforseo": {
            "page_summaries": {
                "http://focus.example/doors": {"backlinks": 10, "referring_domains": 4},
                "https://competitor.example/doors?type=oak": {"backlinks": 20, "referring_domains": 8},
            },
            "backlinks": {
                "http://focus.example/doors": [
                    {"url_from": "https://news.example/a", "url_to": "http://focus.example/doors"},
                    {"url_from": "https://NEWS.example/b", "url_to": "https://focus.example/doors"},
                    {"url_from": "https://other.example/x", "url_to": "http://focus.example/doors"},
                ],
                "https://competitor.example/doors?type=oak": [
                    {"url_from": "https://dfs-only.example/a", "url_to": "https://competitor.example/doors?type=oak"}
                ],
            },
        },
    }


class PureAggregationTests(unittest.TestCase):
    def test_classifies_article_profile_home_spam_and_other(self):
        cases = [
            ({"url_from": "https://site.test/blog/post"}, "article"),
            ({"url_from": "https://site.test/users/alice"}, "profile"),
            ({"url_from": "https://site.test/"}, "home"),
            ({"url_from": "https://casino-links.test/page"}, "spam"),
            ({"url_from": "https://site.test/resources"}, "other"),
        ]
        for row, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(cb.classify_ahrefs_link(row), expected)

    def test_ahrefs_provider_fields_take_precedence_over_url_heuristics(self):
        cases = [
            ({"url_from": "https://site.test/blog/post", "is_spam": True}, "spam"),
            ({"url_from": "https://site.test/blog/post", "page_type_source": "Profile"}, "profile"),
            ({"url_from": "https://site.test/users/alice", "page_type_source": "/Article"}, "article"),
            ({"url_from": "https://site.test/users/alice", "is_content": True}, "article"),
            ({"url_from": "https://site.test/blog/post", "page_type_source": "Homepage"}, "home"),
        ]
        for row, expected in cases:
            with self.subTest(row=row):
                self.assertEqual(cb.classify_ahrefs_link(row), expected)

    def test_root_domain_name_is_not_used_as_page_type(self):
        row = {
            "url_from": "https://author-home.example/resources",
            "root_name_source": "author-home.example",
            "page_type_source": None,
            "is_content": False,
        }
        self.assertEqual(cb.classify_ahrefs_link(row), "other")

    def test_ahrefs_summary_counts_dofollow_rows(self):
        payload = fixture_payload()
        rows = payload["ahrefs"]["backlinks"]["http://focus.example/doors"]
        rows[0]["is_dofollow"] = True
        rows[1]["is_dofollow"] = False
        rows[2]["is_dofollow"] = True
        summary = cb.aggregate(SPEC, payload)
        self.assertEqual(summary["targets"]["http://focus.example/doors"]["ahrefs"]["dofollow_rows"], 2)

    def test_age_windows_include_exact_365_and_183_day_boundaries(self):
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        rows = [
            {"first_seen_link": "2025-01-01T00:00:00+00:00"},
            {"first_seen_link": "2024-12-31T23:59:59+00:00"},
            {"first_seen_link": "2025-07-02T00:00:00+00:00"},
            {"first_seen_link": "2025-07-01T23:59:59+00:00"},
        ]
        self.assertEqual(cb.count_new_links(rows, now), {"days_365": 3, "days_183": 1})

    def test_unique_donors_are_deduplicated_per_source(self):
        summary = cb.aggregate(SPEC, fixture_payload())
        focus = summary["targets"]["http://focus.example/doors"]
        self.assertEqual(focus["ahrefs"]["raw_backlink_rows"], 3)
        self.assertEqual(focus["ahrefs"]["unique_donor_domains"], 2)
        self.assertEqual(focus["dataforseo"]["raw_backlink_rows"], 3)
        self.assertEqual(focus["dataforseo"]["unique_donor_domains"], 2)

    def test_ahrefs_root_name_source_deduplicates_donor_subdomains(self):
        payload = fixture_payload()
        payload["ahrefs"]["backlinks"]["http://focus.example/doors"] = [
            {"url_from": "https://blog.example.com/post", "root_name_source": "example.com"},
            {"url_from": "https://shop.example.com/item", "root_name_source": "example.com"},
        ]
        summary = cb.aggregate(SPEC, payload)
        focus = summary["targets"]["http://focus.example/doors"]
        self.assertEqual(focus["ahrefs"]["unique_donor_domains"], 1)

    def test_sources_remain_non_additive_and_unmerged(self):
        summary = cb.aggregate(SPEC, fixture_payload())
        self.assertNotIn("total_backlinks", summary)
        self.assertEqual(summary["source_policy"], "separate_non_additive")
        self.assertIn("must not be merged", summary["warnings"][1].lower())
        focus = summary["targets"]["http://focus.example/doors"]
        self.assertEqual(set(focus), {"cluster", "domain", "is_focal", "requested_target_url", "ahrefs", "dataforseo", "target_observations"})

    def test_requested_and_observed_target_urls_are_preserved_exactly(self):
        summary = cb.aggregate(SPEC, fixture_payload())
        focus = summary["targets"]["http://focus.example/doors"]
        self.assertEqual(focus["requested_target_url"], "http://focus.example/doors")
        self.assertEqual(
            focus["target_observations"]["ahrefs_observed_urls"],
            ["http://focus.example/doors", "https://focus.example/doors"],
        )

    def test_focal_domain_is_canonicalized_and_targets_are_marked_without_url_rewrite(self):
        spec = {
            "focal_domain": "WWW.Focus.Example",
            "clusters": {"doors": ["http://www.focus.example/doors", "https://competitor.example/doors"]},
        }
        validated = cb.validate_spec(spec)
        summary = cb.aggregate(validated, {"collected_at": "2026-01-01T00:00:00+00:00"})
        self.assertEqual(validated["focal_domain"], "focus.example")
        self.assertEqual(spec["focal_domain"], "WWW.Focus.Example")
        self.assertTrue(summary["targets"]["http://www.focus.example/doors"]["is_focal"])
        self.assertFalse(summary["targets"]["https://competitor.example/doors"]["is_focal"])
        self.assertEqual(
            summary["targets"]["http://www.focus.example/doors"]["requested_target_url"],
            "http://www.focus.example/doors",
        )

    def test_focal_domain_rejects_non_hostname_forms(self):
        invalid = [
            "https://focus.example", "focus.example/path", "focus.example?q=1",
            "focus.example value", " focus.example", "focus.example ", "focus.example:443",
        ]
        for focal_domain in invalid:
            with self.subTest(focal_domain=focal_domain):
                with self.assertRaisesRegex(ValueError, "focal_domain"):
                    cb.validate_spec({"focal_domain": focal_domain, "clusters": SPEC["clusters"]})

    def test_row_limit_accepts_1000_and_rejects_1001(self):
        self.assertEqual(cb.validate_spec({**SPEC, "row_limit": 1000})["row_limit"], 1000)
        with self.assertRaisesRegex(ValueError, "1 to 1000"):
            cb.validate_spec({**SPEC, "row_limit": 1001})
    def test_bulk_summary_limits_accept_boundaries_and_reject_oversize_before_network(self):
        boundary_urls = [f"https://d{i % 100}.example/page/{i}" for i in range(1000)]
        boundary = {"focal_domain": "d0.example", "clusters": {"all": boundary_urls}}
        self.assertEqual(len(cb.target_entries(cb.validate_spec(boundary))), 1000)

        calls = []
        oversized_urls = boundary_urls + ["https://d0.example/page/1000"]
        with self.assertRaisesRegex(ValueError, "at most 1000 target URLs") as url_error:
            cb.collect_live(
                {"focal_domain": "d0.example", "clusters": {"all": oversized_urls}},
                {"AHREFS_API_KEY": "test", "DFS_LOGIN": "test", "DFS_PASSWORD": "test"},
                ahrefs_transport=lambda request: calls.append(request),
                dfs_transport=lambda request: calls.append(request),
            )
        self.assertEqual(calls, [])
        self.assertNotIn("https://", str(url_error.exception))

        domain_boundary = [f"https://d{i}.example/page" for i in range(100)]
        cb.validate_spec({"focal_domain": "d0.example", "clusters": {"all": domain_boundary}})
        with self.assertRaisesRegex(ValueError, "at most 100 unique target domains") as domain_error:
            cb.validate_spec({
                "focal_domain": "d0.example",
                "clusters": {"all": domain_boundary + ["https://d100.example/page"]},
            })
        self.assertNotIn("d100.example", str(domain_error.exception))


class LiveRequestContractTests(unittest.TestCase):
    def test_live_requests_preserve_exact_targets_limits_and_provider_options(self):
        ahrefs_requests = []
        dfs_requests = []

        def ahrefs_transport(request):
            ahrefs_requests.append(request)
            return {"backlinks": []}

        def dfs_transport(request):
            dfs_requests.append(request)
            return {
                "status_code": 20000,
                "status_message": "Ok.",
                "tasks": [{"status_code": 20000, "status_message": "Ok.", "result": []}],
            }

        spec = {**SPEC, "row_limit": 37}
        cb.collect_live(
            cb.validate_spec(spec),
            {"AHREFS_API_KEY": "test", "DFS_LOGIN": "test", "DFS_PASSWORD": "test"},
            ahrefs_transport=ahrefs_transport,
            dfs_transport=dfs_transport,
        )

        backlink_queries = [
            parse_qs(urlsplit(request.full_url).query)
            for request in ahrefs_requests
            if urlsplit(request.full_url).path.endswith("/all-backlinks")
        ]
        self.assertEqual(len(backlink_queries), 2)
        required_select = {
            "url_from", "url_to", "first_seen_link", "title", "anchor", "link_type",
            "is_spam", "page_type_source", "is_content", "is_dofollow", "root_name_source",
        }
        for query, target in zip(backlink_queries, SPEC["clusters"]["doors"]):
            self.assertEqual(query["target"], [target])
            self.assertEqual(query["mode"], ["exact"])
            self.assertEqual(query["history"], ["live"])
            self.assertEqual(query["aggregation"], ["all"])
            self.assertEqual(query["limit"], ["37"])
            self.assertTrue(required_select.issubset(set(query["select"][0].split(","))))

        row_requests = [request for request in dfs_requests if request.full_url.endswith("/backlinks/backlinks/live")]
        self.assertEqual(len(row_requests), 2)
        for request, target in zip(row_requests, SPEC["clusters"]["doors"]):
            self.assertEqual(json.loads(request.data), [{"target": target, "mode": "as_is", "limit": 37}])

    def test_dataforseo_top_level_and_task_errors_are_rejected(self):
        errors = [
            {"status_code": 40100, "status_message": "Authentication failed", "tasks": []},
            {
                "status_code": 20000,
                "status_message": "Ok.",
                "tasks": [{"status_code": 40501, "status_message": "Invalid target", "result": []}],
            },
        ]

        def ahrefs_transport(request):
            return {"backlinks": []}

        for response in errors:
            with self.subTest(response=response):
                with self.assertRaisesRegex(RuntimeError, str(response.get("status_code") if response["status_code"] != 20000 else 40501)):
                    cb.collect_live(
                        SPEC,
                        {"AHREFS_API_KEY": "test", "DFS_LOGIN": "test", "DFS_PASSWORD": "test"},
                        ahrefs_transport=ahrefs_transport,
                        dfs_transport=lambda request, response=response: response,
                    )
    def test_dataforseo_errors_never_expose_provider_status_message(self):
        sentinel = "SECRET https://client.example/private"
        responses = [
            {"status_code": 40100, "status_message": sentinel, "tasks": []},
            {
                "status_code": 20000,
                "status_message": "Ok.",
                "tasks": [{"status_code": 40501, "status_message": sentinel, "result": []}],
            },
        ]
        for response, level, code in ((responses[0], "top-level", "40100"), (responses[1], "task", "40501")):
            with self.subTest(level=level):
                with self.assertRaises(RuntimeError) as caught:
                    cb._validate_dfs_response(response)
                message = str(caught.exception)
                self.assertIn(level, message)
                self.assertIn(code, message)
                self.assertNotIn(sentinel, message)
                self.assertNotIn("client.example", message)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec_path = root / "spec.json"
            spec_path.write_text(json.dumps(SPEC), encoding="utf-8")
            stderr = io.StringIO()

            def rejected_collection(spec, credentials):
                cb._validate_dfs_response(responses[0])

            with mock.patch.object(cb, "load_credentials", return_value={}), mock.patch.object(cb, "collect_live", side_effect=rejected_collection):
                with redirect_stderr(stderr):
                    result = cb.main(["--spec", str(spec_path), "--out", str(root / "out")])
            self.assertEqual(result, 2)
            self.assertNotIn(sentinel, stderr.getvalue())
            self.assertNotIn("client.example", stderr.getvalue())


class OutputAndCredentialTests(unittest.TestCase):
    def test_report_escapes_cluster_names_and_exact_urls(self):
        unsafe_url = "https://competitor.example/path?x=a|b`c"
        unsafe_spec = {
            "focal_domain": "focus.example",
            "clusters": {"doors | injected\n## bad": [unsafe_url]},
        }
        payload = {
            "collected_at": "2026-01-01T00:00:00+00:00",
            "ahrefs": {"domain_ratings": {}, "backlinks": {unsafe_url: []}},
            "dataforseo": {"page_summaries": {}, "backlinks": {unsafe_url: []}},
        }
        report = cb.render_report(cb.aggregate(unsafe_spec, payload))
        self.assertNotIn("\n## bad", report)
        self.assertIn("doors \\| injected ## bad", report)
        self.assertIn("<code>https://competitor.example/path?x=a&#124;b`c</code>", report)

    def test_russian_report_has_cluster_comparison_table_focal_marker_and_separate_dfs_summary(self):
        summary = cb.aggregate(SPEC, fixture_payload())
        report = cb.render_report(summary)
        self.assertIn("## Кластер: doors", report)
        self.assertIn("| Роль | Точный URL |", report)
        self.assertIn("| **Основной сайт** | `http://focus.example/doors` |", report)
        self.assertIn("| Конкурент | `https://competitor.example/doors?type=oak` |", report)
        self.assertIn("DataForSEO summary (точные метрики страницы): backlinks — 10; referring_domains — 4.", report)
        self.assertIn("ограниченная выборка строк", report)
        self.assertIn("dofollow", report)

    def test_writes_summary_raw_csvs_and_one_russian_markdown_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "result"
            cb.write_outputs(SPEC, fixture_payload(), out)
            expected = {
                "summary.json",
                "ahrefs_backlinks_raw.csv",
                "dataforseo_backlinks_raw.csv",
                "report.ru.md",
            }
            self.assertTrue(expected.issubset({p.name for p in out.iterdir()}))
            report = (out / "report.ru.md").read_text(encoding="utf-8")
            self.assertIn("Сравнение ссылочных профилей", report)
            self.assertIn("DR нельзя складывать", report)
            self.assertIn("Ahrefs и DataForSEO нельзя объединять", report)
            summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["domain_ratings"]["competitor.example"], 55)
            with (out / "ahrefs_backlinks_raw.csv").open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["requested_target_url"], "http://focus.example/doors")
            self.assertIn(rows[0]["classification"], {"article", "profile", "home", "spam", "other"})

    @unittest.skipUnless(os.name == "posix", "POSIX permissions only")
    def test_new_output_directory_and_live_cache_have_private_modes(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "result"
            cb.write_outputs(SPEC, fixture_payload(), out, include_cache=True)
            self.assertEqual(out.stat().st_mode & 0o777, 0o700)
            self.assertEqual((out / "api-cache.json").stat().st_mode & 0o777, 0o600)

    @unittest.skipUnless(os.name == "posix", "POSIX permissions only")
    def test_existing_empty_output_directory_is_secured_before_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "result"
            out.mkdir(mode=0o755)
            cb.write_outputs(SPEC, fixture_payload(), out)
            self.assertEqual(out.stat().st_mode & 0o777, 0o700)

    def test_credentials_use_environment_then_active_hermes_env_without_leaking(self):
        secret_values = {"AHREFS_API_KEY": "ahrefs-secret", "DFS_LOGIN": "dfs-user", "DFS_PASSWORD": "dfs-secret"}
        self.assertEqual(cb.load_credentials(secret_values), secret_values)
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            env_path.write_text("AHREFS_API_KEY='file-ahrefs'\nDFS_LOGIN=file-user\nDFS_PASSWORD=file-pass\n", encoding="utf-8")
            if os.name == "posix":
                env_path.chmod(0o600)
            loaded = cb.load_credentials({"HERMES_HOME": tmp})
            self.assertEqual(loaded["DFS_PASSWORD"], "file-pass")
            with self.assertRaisesRegex(ValueError, "DFS_PASSWORD") as caught:
                cb.load_credentials({"HERMES_HOME": str(Path(tmp) / "missing"), **secret_values, "DFS_PASSWORD": ""})
            self.assertNotIn("ahrefs-secret", str(caught.exception))
            self.assertNotIn("dfs-user", str(caught.exception))

    def test_cli_from_cache_needs_no_credentials_and_refuses_nonempty_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec = root / "spec.json"
            cache = root / "cache"
            out = root / "out"
            cache.mkdir()
            spec.write_text(json.dumps(SPEC), encoding="utf-8")
            (cache / "api-cache.json").write_text(json.dumps(fixture_payload()), encoding="utf-8")
            command = [sys.executable, str(ROOT / "compare_backlinks.py"), "--spec", str(spec), "--out", str(out), "--from-cache", str(cache)]
            env = {"PATH": os.environ.get("PATH", ""), "HERMES_HOME": str(root / "no-profile")}
            first = subprocess.run(command, capture_output=True, text=True, env=env)
            self.assertEqual(first.returncode, 0, first.stderr)
            second = subprocess.run(command, capture_output=True, text=True, env=env)
            self.assertNotEqual(second.returncode, 0)
            self.assertIn("nonempty", (second.stdout + second.stderr).lower())

    def test_missing_credentials_fail_without_network_or_secret_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec = root / "spec.json"
            spec.write_text(json.dumps(SPEC), encoding="utf-8")
            command = [sys.executable, str(ROOT / "compare_backlinks.py"), "--spec", str(spec), "--out", str(root / "out")]
            env = {"PATH": os.environ.get("PATH", ""), "HERMES_HOME": str(root / "missing"), "AHREFS_API_KEY": "visible-secret", "DFS_LOGIN": "", "DFS_PASSWORD": ""}
            proc = subprocess.run(command, capture_output=True, text=True, env=env)
            self.assertEqual(proc.returncode, 2)
            combined = proc.stdout + proc.stderr
            self.assertIn("DFS_LOGIN", combined)
            self.assertNotIn("visible-secret", combined)
            self.assertFalse((root / "out").exists())


if __name__ == "__main__":
    unittest.main()
