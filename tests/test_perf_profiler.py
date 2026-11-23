import time
import unittest
from pathlib import Path
from playwright.sync_api import sync_playwright

from browser_toolkit.cli import build_parser
from browser_toolkit.perf_profiler import (
    INIT_PERF_TRACKER_JS,
    COLLECT_PERF_METRICS_JS,
    PerformanceReport,
    SystemResourceMonitor,
    audit_page_performance,
)


class TestPerfProfiler(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.firefox.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def test_cli_perf_args(self):
        parser = build_parser()
        args = parser.parse_args([
            "perf", "https://example.com",
            "--script", "test.user.js",
            "--css", "style.user.css",
            "--duration", "1.5",
            "--sample-interval", "0.05",
            "--actions", '[{"action": "click", "selector": "#btn"}]',
            "--toon",
        ])
        self.assertEqual(args.command, "perf")
        self.assertEqual(args.url, "https://example.com")
        self.assertEqual(args.script, "test.user.js")
        self.assertEqual(args.css, "style.user.css")
        self.assertEqual(args.duration, 1.5)
        self.assertEqual(args.sample_interval, 0.05)
        self.assertTrue(args.toon)

        # Test session perf subcommand
        s_args = parser.parse_args([
            "session", "perf",
            "--duration", "3.0",
            "--name", "test-sess",
            "--actions", '[{"action": "wait", "ms": 200}]',
        ])
        self.assertEqual(s_args.command, "session")
        self.assertEqual(s_args.session_command, "perf")
        self.assertEqual(s_args.duration, 3.0)
        self.assertEqual(s_args.name, "test-sess")

    def test_system_resource_monitor(self):
        mon = SystemResourceMonitor(interval=0.05)
        mon.start()
        time.sleep(0.2)
        metrics = mon.stop()

        self.assertIn("process_count", metrics)
        self.assertIn("start_rss_mb", metrics)
        self.assertIn("peak_rss_mb", metrics)
        self.assertIn("end_rss_mb", metrics)
        self.assertIn("avg_cpu_percent", metrics)
        self.assertGreaterEqual(metrics["samples_count"], 1)

    def test_in_browser_perf_tracking(self):
        page = self.browser.new_page()
        page.add_init_script(INIT_PERF_TRACKER_JS)
        html = "data:text/html,<html><head><title>Perf Test</title></head><body><h1 id='title'>Perf</h1><div id='container'></div></body></html>"
        page.goto(html)

        # Trigger DOM mutations
        page.evaluate("""() => {
            const c = document.getElementById('container');
            for (let i = 0; i < 5; i++) {
                const p = document.createElement('p');
                p.textContent = 'Node ' + i;
                p.setAttribute('data-idx', String(i));
                c.appendChild(p);
            }
        }""")

        # Trigger a simulated blocking task (>50ms)
        page.evaluate("""() => {
            const start = performance.now();
            while (performance.now() - start < 100) {}
        }""")
        page.wait_for_timeout(100)

        raw = page.evaluate(COLLECT_PERF_METRICS_JS)
        page.close()

        self.assertIn("navigation", raw)
        self.assertIn("paint", raw)
        self.assertIn("layout", raw)
        self.assertIn("long_tasks", raw)
        self.assertIn("dom_mutations", raw)

        # Verify DOM mutations were tracked
        muts = raw["dom_mutations"]
        self.assertGreaterEqual(muts["total"], 5)
        self.assertGreaterEqual(muts["added"], 5)

        # Verify long tasks detection
        lt = raw["long_tasks"]
        self.assertGreaterEqual(lt["count"], 1)
        self.assertGreaterEqual(lt["total_blocking_time_ms"], 30)

    def test_performance_report_serialization(self):
        report = PerformanceReport(
            url="https://example.com",
            duration_seconds=1.5,
            navigation={"ttfb_ms": 25, "dom_content_loaded_ms": 120, "load_event_ms": 150},
            paint={"fp_ms": 100, "fcp_ms": 110, "lcp_ms": 140},
            layout={"cls": 0.05},
            long_tasks={"count": 1, "total_blocking_time_ms": 60, "max_duration_ms": 110, "tasks": []},
            resources={"total_requests": 5, "total_transfer_kb": 120.0, "total_decoded_kb": 250.0, "by_type": {}, "slowest": [], "largest": []},
            dom_mutations={"total": 10, "added": 8, "removed": 2, "attributes": 0, "rate_per_sec": 6.7},
            system_resources={"process_count": 4, "start_rss_mb": 100.0, "end_rss_mb": 120.0, "peak_rss_mb": 125.0, "rss_delta_mb": 20.0, "avg_cpu_percent": 15.0, "peak_cpu_percent": 35.0},
            script_impact={"execution_ms": 3.5},
            css_impact={"injection_ms": 0.5, "reflow_recalc_ms": 4.0, "total_impact_ms": 4.5},
        )
        d = report.to_dict()
        self.assertEqual(d["type"], "performance_profile")
        self.assertEqual(d["url"], "https://example.com")
        self.assertEqual(d["web_vitals"]["fcp_ms"], 110)
        self.assertEqual(d["main_thread"]["total_blocking_time_ms"], 60)
        self.assertEqual(d["script_impact"]["execution_ms"], 3.5)
        self.assertEqual(d["css_impact"]["total_impact_ms"], 4.5)
