import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

MODULE_PATH = Path(__file__).with_name("dataforseo_prompts_fanout.py")
SPEC = importlib.util.spec_from_file_location("dataforseo_prompts_fanout", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("unable to load test target")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class DataForSeoPromptsFanoutTests(unittest.TestCase):
    @staticmethod
    def response(items, total_count=None):
        return {
            "status_code": 20000,
            "tasks": [{
                "status_code": 20000,
                "cost": 0.1,
                "result": [{
                    "items": items,
                    "total_count": len(items) if total_count is None else total_count,
                }],
            }],
        }

    def test_dedupe_preserves_verbatim_order(self):
        values = ["Dental Implants?", "Dental Implants?", "dental implants", ""]
        self.assertEqual(MODULE.dedupe(values), ["Dental Implants?", "dental implants"])

    def test_result_items_checks_both_status_levels(self):
        response = {
            "status_code": 20000,
            "tasks": [{"status_code": 20000, "result": [{"items": [{"question": "exact"}]}]}],
        }
        self.assertEqual(MODULE.result_items(response), [{"question": "exact"}])

    def test_task_error_is_not_silently_accepted(self):
        response = {"status_code": 20000, "tasks": [{"status_code": 40000, "result": []}]}
        with self.assertRaisesRegex(RuntimeError, "task status 40000"):
            MODULE.result_items(response)

    def test_empty_result_is_valid(self):
        response = {"status_code": 20000, "tasks": [{"status_code": 20000, "result": []}]}
        self.assertEqual(MODULE.result_items(response), [])

    def test_history_uses_two_scopes_and_preserves_provider_text(self):
        responses = [
            self.response([{"question": "Who uses 100% milk?"}]),
            self.response([{"fan_out_queries": ["milk supplier + wholesale", "milk supplier + wholesale"]}]),
        ]
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(MODULE, "request_json", side_effect=responses) as request:
            summary = MODULE.history("milk supplier", Path(tmp), "login", "password")
            self.assertEqual(request.call_count, 2)
            first_payload = request.call_args_list[0].args[1][0]
            second_payload = request.call_args_list[1].args[1][0]
            self.assertEqual(first_payload["target"][0]["search_scope"], ["question"])
            self.assertEqual(second_payload["target"][0]["search_scope"], ["fan_out_queries"])
            self.assertEqual(json.loads((Path(tmp) / "prompts.json").read_text()), ["Who uses 100% milk?"])
            self.assertEqual(json.loads((Path(tmp) / "fan_out_queries.json").read_text()), ["milk supplier + wholesale"])
            self.assertEqual(summary["prompts_count"], 1)

    def test_scrape_keeps_original_prompt_with_plus_and_percent(self):
        response = self.response([])
        response["tasks"][0]["result"] = [{
            "keyword": "A B 100%",
            "fan_out_queries": ["fan-out + exact"],
        }]
        prompt = "A+B 100%"
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(MODULE, "request_json", return_value=response) as request:
            MODULE.scrape(prompt, Path(tmp), "login", "password")
            self.assertEqual(json.loads((Path(tmp) / "prompt.json").read_text()), [prompt])
            payload = request.call_args.args[1][0]
            self.assertEqual(payload["keyword"], "A%2BB 100%25")

    def test_second_history_failure_leaves_no_partial_files(self):
        first = self.response([{"question": "exact"}])
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            MODULE, "request_json", side_effect=[first, RuntimeError("second call failed")]
        ):
            with self.assertRaisesRegex(RuntimeError, "second call failed"):
                MODULE.history("exact", Path(tmp), "login", "password")
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_redirects_are_blocked(self):
        handler = MODULE.NoRedirectHandler()
        request = MODULE.urllib.request.Request("https://api.dataforseo.com/start")
        with self.assertRaises(MODULE.urllib.error.HTTPError):
            handler.redirect_request(request, None, 302, "Found", {}, "https://example.com/")

    def test_malformed_tasks_shape_is_controlled(self):
        with self.assertRaisesRegex(RuntimeError, "tasks have an unexpected shape"):
            MODULE.checked_task({"status_code": 20000, "tasks": {"bad": "shape"}})

    def test_malformed_scrape_result_shape_is_controlled(self):
        response = {"status_code": 20000, "tasks": [{"status_code": 20000, "result": {"bad": "shape"}}]}
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(MODULE, "request_json", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "result has an unexpected shape"):
                MODULE.scrape("exact", Path(tmp), "login", "password")

    def test_falsey_non_list_result_is_rejected(self):
        for malformed in ({}, ""):
            response = {"status_code": 20000, "tasks": [{"status_code": 20000, "result": malformed}]}
            with self.subTest(malformed=malformed), self.assertRaisesRegex(RuntimeError, "result has an unexpected shape"):
                MODULE.result_items(response)

    def test_string_fan_out_queries_is_rejected(self):
        response = self.response([{"fan_out_queries": "ab"}])
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            MODULE, "request_json", side_effect=[self.response([]), response]
        ):
            with self.assertRaisesRegex(RuntimeError, "fan_out_queries have an unexpected shape"):
                MODULE.history("exact", Path(tmp), "login", "password")

    def test_falsey_non_list_and_non_object_items_are_rejected(self):
        for malformed in ({}, "", ["not-an-object"]):
            response = {
                "status_code": 20000,
                "tasks": [{"status_code": 20000, "result": [{"items": malformed}]}],
            }
            with self.subTest(malformed=malformed), self.assertRaisesRegex(RuntimeError, "items have an unexpected shape"):
                MODULE.result_items(response)

    def test_input_file_preserves_crlf_and_bare_cr(self):
        original = "line1\r\nline2\rline3"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "input.txt"
            with path.open("w", encoding="utf-8", newline="") as stream:
                stream.write(original)
            self.assertEqual(MODULE.read_input(str(path)), original)


if __name__ == "__main__":
    unittest.main()
