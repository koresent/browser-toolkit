import os
import time
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from playwright.sync_api import Page

from .gm_shim import GM_FULL_SHIM_JS
from .interaction import PageInteractor, execute_action_sequence
from .navigation import safe_goto
from .parser import parse_userscript, parse_userstyle, UserScriptInfo


INIT_PERF_TRACKER_JS = """
(() => {
  window.__bt_perf_stop = false;
  if (window.__bt_perf_installed) return;
  window.__bt_perf_installed = true;

  window.__bt_perf_long_tasks = [];
  window.__bt_perf_lcp = 0;
  window.__bt_perf_cls = 0;
  window.__bt_perf_mutations = { total: 0, added: 0, removed: 0, attributes: 0 };

  try {
    const ltObs = new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        window.__bt_perf_long_tasks.push({
          startTime: Math.round(entry.startTime),
          duration: Math.round(entry.duration),
          blockingTime: Math.round(Math.max(0, entry.duration - 50)),
          source: 'native'
        });
      }
    });
    ltObs.observe({ type: 'longtask', buffered: true });
    window.__bt_perf_lt_obs = ltObs;
  } catch (_) {}

  let lastTick = performance.now();
  function checkJank() {
    if (window.__bt_perf_stop) return;
    const now = performance.now();
    const elapsed = now - lastTick;
    if (elapsed > 50) {
      window.__bt_perf_long_tasks.push({
        startTime: Math.round(lastTick),
        duration: Math.round(elapsed),
        blockingTime: Math.round(elapsed - 50),
        source: 'timer'
      });
    }
    lastTick = performance.now();
    requestAnimationFrame(checkJank);
  }
  requestAnimationFrame(checkJank);

  try {
    const lcpObs = new PerformanceObserver((list) => {
      const entries = list.getEntries();
      if (entries.length > 0) {
        window.__bt_perf_lcp = Math.round(entries[entries.length - 1].startTime);
      }
    });
    lcpObs.observe({ type: 'largest-contentful-paint', buffered: true });
    window.__bt_perf_lcp_obs = lcpObs;
  } catch (_) {}

  try {
    const clsObs = new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        if (!entry.hadRecentInput) {
          window.__bt_perf_cls += entry.value;
        }
      }
    });
    clsObs.observe({ type: 'layout-shift', buffered: true });
    window.__bt_perf_cls_obs = clsObs;
  } catch (_) {}

  try {
    const observer = new MutationObserver((mutations) => {
      window.__bt_perf_mutations.total += mutations.length;
      for (let i = 0; i < mutations.length; i++) {
        const m = mutations[i];
        if (m.type === 'childList') {
          window.__bt_perf_mutations.added += m.addedNodes.length;
          window.__bt_perf_mutations.removed += m.removedNodes.length;
        } else if (m.type === 'attributes') {
          window.__bt_perf_mutations.attributes += 1;
        }
      }
    });
    const attach = () => {
      if (document.documentElement) {
        observer.observe(document.documentElement, { childList: true, subtree: true, attributes: true });
      }
    };
    attach();
    document.addEventListener('DOMContentLoaded', attach);
    window.__bt_perf_mutation_obs = observer;
  } catch (_) {}
})();
"""


COLLECT_PERF_METRICS_JS = """
(() => {
  window.__bt_perf_stop = true;
  window.__bt_perf_installed = false;
  try { if (window.__bt_perf_lt_obs) window.__bt_perf_lt_obs.disconnect(); } catch (_) {}
  try { if (window.__bt_perf_lcp_obs) window.__bt_perf_lcp_obs.disconnect(); } catch (_) {}
  try { if (window.__bt_perf_cls_obs) window.__bt_perf_cls_obs.disconnect(); } catch (_) {}
  try { if (window.__bt_perf_mutation_obs) window.__bt_perf_mutation_obs.disconnect(); } catch (_) {}

  const nav = performance.getEntriesByType('navigation')[0] || {};
  const paints = performance.getEntriesByType('paint');
  let fp = 0;
  let fcp = 0;
  for (const p of paints) {
    if (p.name === 'first-paint') fp = Math.round(p.startTime);
    if (p.name === 'first-contentful-paint') fcp = Math.round(p.startTime);
  }

  const rawTasks = window.__bt_perf_long_tasks || [];
  const tasks = [];
  for (const t of rawTasks) {
    if (!tasks.some(existing => Math.abs(existing.startTime - t.startTime) < 30)) {
      tasks.push(t);
    }
  }
  tasks.sort((a, b) => a.startTime - b.startTime);

  let totalBlockingTime = 0;
  let maxTaskDuration = 0;
  for (const t of tasks) {
    totalBlockingTime += t.blockingTime;
    if (t.duration > maxTaskDuration) maxTaskDuration = t.duration;
  }

  const resources = performance.getEntriesByType('resource');
  const typeMap = {};
  let totalTransfer = 0;
  let totalDecoded = 0;
  const resourceList = [];

  for (const r of resources) {
    const type = r.initiatorType || 'other';
    const transfer = r.transferSize || 0;
    const decoded = r.decodedBodySize || 0;
    const duration = Math.round(r.duration || 0);

    totalTransfer += transfer;
    totalDecoded += decoded;

    if (!typeMap[type]) {
      typeMap[type] = { count: 0, transfer_bytes: 0, decoded_bytes: 0, total_duration_ms: 0 };
    }
    typeMap[type].count += 1;
    typeMap[type].transfer_bytes += transfer;
    typeMap[type].decoded_bytes += decoded;
    typeMap[type].total_duration_ms += duration;

    resourceList.push({
      url: r.name,
      initiator: type,
      duration_ms: duration,
      transfer_bytes: transfer,
      decoded_bytes: decoded,
    });
  }

  resourceList.sort((a, b) => b.duration_ms - a.duration_ms);
  const slowest = resourceList.slice(0, 5).map(r => ({
    url: r.url,
    initiator: r.initiator,
    duration_ms: r.duration_ms,
    size_kb: Math.round((r.transfer_bytes / 1024) * 10) / 10,
  }));

  resourceList.sort((a, b) => b.transfer_bytes - a.transfer_bytes);
  const largest = resourceList.slice(0, 5).map(r => ({
    url: r.url,
    initiator: r.initiator,
    duration_ms: r.duration_ms,
    size_kb: Math.round((r.transfer_bytes / 1024) * 10) / 10,
  }));

  const byType = {};
  for (const [k, v] of Object.entries(typeMap)) {
    byType[k] = {
      count: v.count,
      transfer_kb: Math.round((v.transfer_bytes / 1024) * 10) / 10,
      decoded_kb: Math.round((v.decoded_bytes / 1024) * 10) / 10,
      total_duration_ms: v.total_duration_ms,
    };
  }

  return {
    navigation: {
      ttfb_ms: nav.responseStart && nav.requestStart ? Math.round(nav.responseStart - nav.requestStart) : 0,
      dom_interactive_ms: nav.domInteractive ? Math.round(nav.domInteractive) : 0,
      dom_content_loaded_ms: nav.domContentLoadedEventEnd ? Math.round(nav.domContentLoadedEventEnd) : 0,
      load_event_ms: nav.loadEventEnd ? Math.round(nav.loadEventEnd) : 0,
      duration_ms: nav.duration ? Math.round(nav.duration) : 0,
      transfer_kb: nav.transferSize ? Math.round((nav.transferSize / 1024) * 10) / 10 : 0,
      decoded_kb: nav.decodedBodySize ? Math.round((nav.decodedBodySize / 1024) * 10) / 10 : 0,
    },
    paint: {
      fp_ms: fp,
      fcp_ms: fcp,
      lcp_ms: window.__bt_perf_lcp || 0,
    },
    layout: {
      cls: Math.round((window.__bt_perf_cls || 0) * 1000) / 1000,
    },
    long_tasks: {
      count: tasks.length,
      total_blocking_time_ms: totalBlockingTime,
      max_duration_ms: maxTaskDuration,
      tasks: tasks.slice(0, 5),
    },
    resources: {
      total_requests: resources.length,
      total_transfer_kb: Math.round((totalTransfer / 1024) * 10) / 10,
      total_decoded_kb: Math.round((totalDecoded / 1024) * 10) / 10,
      by_type: byType,
      slowest: slowest,
      largest: largest,
    },
    dom_mutations: window.__bt_perf_mutations || { total: 0, added: 0, removed: 0, attributes: 0 },
  };
})()
"""


class SystemResourceMonitor:
    def __init__(self, root_pid: Optional[int] = None, interval: float = 0.1):
        self.root_pid = root_pid or os.getpid()
        self.interval = interval
        try:
            self.clk_tck = os.sysconf(os.sysconf_names.get("SC_CLK_TCK", "SC_CLK_TCK")) or 100
        except Exception:
            self.clk_tck = 100
        self.samples: List[Dict[str, Any]] = []
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def _get_descendants(self) -> List[int]:
        try:
            all_procs: Dict[int, int] = {}
            for p in Path("/proc").iterdir():
                if p.name.isdigit():
                    try:
                        stat = (p / "stat").read_text()
                        rparen = stat.rfind(")")
                        fields = stat[rparen + 2:].split()
                        ppid = int(fields[1])
                        all_procs[int(p.name)] = ppid
                    except Exception:
                        pass
            queue = [self.root_pid]
            descendants: set[int] = set()
            while queue:
                curr = queue.pop()
                for pid, ppid in all_procs.items():
                    if ppid == curr and pid not in descendants:
                        descendants.add(pid)
                        queue.append(pid)
            return list(descendants)
        except Exception:
            return []

    def _sample_once(self, pids: List[int]) -> tuple[float, float, int, int]:
        rss_kb = 0
        ticks = 0
        active_count = 0
        for pid in pids:
            try:
                stat_text = Path(f"/proc/{pid}/stat").read_text()
                rparen = stat_text.rfind(")")
                fields = stat_text[rparen + 2:].split()
                utime = int(fields[11])
                stime = int(fields[12])

                status_text = Path(f"/proc/{pid}/status").read_text()
                cur_rss = 0
                for line in status_text.splitlines():
                    if line.startswith("VmRSS:"):
                        cur_rss = int(line.split()[1])
                        break
                rss_kb += cur_rss
                ticks += (utime + stime)
                active_count += 1
            except Exception:
                pass
        return time.time(), rss_kb / 1024.0, ticks, active_count

    def start(self) -> None:
        self._stop.clear()
        pids = self._get_descendants()
        if not pids:
            pids = [self.root_pid]

        def _worker():
            prev_time, prev_rss, prev_ticks, _ = self._sample_once(pids)
            self.samples.append({
                "time": prev_time,
                "rss_mb": prev_rss,
                "cpu_pct": 0.0,
                "proc_count": len(pids),
            })
            while not self._stop.is_set():
                time.sleep(self.interval)
                curr_time, curr_rss, curr_ticks, count = self._sample_once(pids)
                dt = curr_time - prev_time
                dticks = curr_ticks - prev_ticks
                if dt > 0 and self.clk_tck > 0:
                    cpu_pct = (dticks / (dt * self.clk_tck)) * 100.0
                else:
                    cpu_pct = 0.0
                self.samples.append({
                    "time": curr_time,
                    "rss_mb": curr_rss,
                    "cpu_pct": max(0.0, cpu_pct),
                    "proc_count": count,
                })
                prev_time, prev_rss, prev_ticks = curr_time, curr_rss, curr_ticks

        self._thread = threading.Thread(target=_worker, daemon=True)
        self._thread.start()

    def stop(self) -> Dict[str, Any]:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1.0)

        if not self.samples:
            return {
                "process_count": 0,
                "start_rss_mb": 0.0,
                "peak_rss_mb": 0.0,
                "end_rss_mb": 0.0,
                "rss_delta_mb": 0.0,
                "avg_cpu_percent": 0.0,
                "peak_cpu_percent": 0.0,
                "samples_count": 0,
            }

        rss_values = [s["rss_mb"] for s in self.samples]
        cpu_values = [s["cpu_pct"] for s in self.samples[1:]] or [0.0]
        proc_counts = [s["proc_count"] for s in self.samples]

        start_rss = round(rss_values[0], 2)
        end_rss = round(rss_values[-1], 2)
        peak_rss = round(max(rss_values), 2)
        rss_delta = round(end_rss - start_rss, 2)
        avg_cpu = round(sum(cpu_values) / len(cpu_values), 1)
        peak_cpu = round(max(cpu_values), 1)

        return {
            "process_count": max(proc_counts) if proc_counts else 1,
            "start_rss_mb": start_rss,
            "peak_rss_mb": peak_rss,
            "end_rss_mb": end_rss,
            "rss_delta_mb": rss_delta,
            "avg_cpu_percent": avg_cpu,
            "peak_cpu_percent": peak_cpu,
            "samples_count": len(self.samples),
        }


@dataclass
class PerformanceReport:
    url: str
    duration_seconds: float
    navigation: Dict[str, Any]
    paint: Dict[str, Any]
    layout: Dict[str, Any]
    long_tasks: Dict[str, Any]
    resources: Dict[str, Any]
    dom_mutations: Dict[str, Any]
    system_resources: Dict[str, Any]
    script_impact: Optional[Dict[str, Any]] = None
    css_impact: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        out = {
            "type": "performance_profile",
            "url": self.url,
            "duration_seconds": self.duration_seconds,
            "web_vitals": {
                "ttfb_ms": self.navigation.get("ttfb_ms", 0),
                "fcp_ms": self.paint.get("fcp_ms", 0),
                "lcp_ms": self.paint.get("lcp_ms", 0),
                "dom_content_loaded_ms": self.navigation.get("dom_content_loaded_ms", 0),
                "load_event_ms": self.navigation.get("load_event_ms", 0),
                "cls": self.layout.get("cls", 0.0),
            },
            "main_thread": {
                "long_tasks_count": self.long_tasks.get("count", 0),
                "total_blocking_time_ms": self.long_tasks.get("total_blocking_time_ms", 0),
                "max_task_duration_ms": self.long_tasks.get("max_duration_ms", 0),
                "tasks": self.long_tasks.get("tasks", []),
            },
            "system_resources": self.system_resources,
            "dom_mutations": self.dom_mutations,
            "resources_summary": {
                "total_requests": self.resources.get("total_requests", 0),
                "total_transfer_kb": self.resources.get("total_transfer_kb", 0.0),
                "total_decoded_kb": self.resources.get("total_decoded_kb", 0.0),
                "by_type": self.resources.get("by_type", {}),
            },
            "slowest_resources": self.resources.get("slowest", []),
            "largest_resources": self.resources.get("largest", []),
        }
        if self.script_impact:
            out["script_impact"] = self.script_impact
        if self.css_impact:
            out["css_impact"] = self.css_impact
        return out


def audit_page_performance(
    page: Page,
    url: str,
    script_path: Optional[str | Path] = None,
    css_path: Optional[str | Path] = None,
    actions: Optional[List[Dict[str, Any]]] = None,
    duration: float = 2.0,
    wait: Optional[str | int] = None,
    settle_ms: int = 500,
    sample_interval: float = 0.1,
) -> PerformanceReport:
    """Measures page lifecycle timings, main thread jank, DOM mutations, network assets,

    and system resource utilization (CPU & RAM), with optional script or style impact.
    """
    page.add_init_script(INIT_PERF_TRACKER_JS)

    script_info = None
    if script_path:
        p = Path(script_path).resolve()
        try:
            script_info = parse_userscript(p)
        except Exception:
            content = p.read_text(encoding="utf-8", errors="replace")
            script_info = UserScriptInfo(filepath=p, raw_js=content)

    if script_info and getattr(script_info, "run_at", "") == "document-start":
        page.add_init_script(GM_FULL_SHIM_JS)
        page.add_init_script(script_info.raw_js)

    sys_mon = SystemResourceMonitor(interval=sample_interval)
    sys_mon.start()

    t_start = time.time()
    safe_goto(page, url, wait_until="domcontentloaded")

    if wait:
        try:
            wait_ms = int(wait)
            page.wait_for_timeout(wait_ms)
        except ValueError:
            try:
                page.wait_for_selector(str(wait), timeout=10000)
            except Exception:
                pass

    script_impact = None
    if script_info and getattr(script_info, "run_at", "") != "document-start":
        page.evaluate(GM_FULL_SHIM_JS)
        inject_wrapper = f"""(() => {{
          const t0 = performance.now();
          try {{
            {script_info.raw_js}
          }} catch (err) {{
            return {{ error: String(err) }};
          }}
          const t1 = performance.now();
          return {{ execution_ms: Math.round((t1 - t0) * 100) / 100 }};
        }})()"""
        script_res = page.evaluate(inject_wrapper)
        script_impact = script_res or {}

    css_impact = None
    if css_path:
        p_css = Path(css_path).resolve()
        css_text = ""
        try:
            style_info = parse_userstyle(p_css)
            css_text = style_info.get_combined_css_for_url(url) or style_info.raw_css
        except Exception:
            css_text = p_css.read_text(encoding="utf-8", errors="replace")
        if not css_text:
            css_text = p_css.read_text(encoding="utf-8", errors="replace")

        css_eval = f"""(() => {{
          const t0 = performance.now();
          const s = document.createElement('style');
          s.setAttribute('data-browser-toolkit-perf', '1');
          s.textContent = {repr(css_text)};
          document.head.appendChild(s);
          const tInject = performance.now();
          const h = document.body ? document.body.getBoundingClientRect().height : 0;
          const tRecalc = performance.now();
          return {{
            injection_ms: Math.round((tInject - t0) * 100) / 100,
            reflow_recalc_ms: Math.round((tRecalc - tInject) * 100) / 100,
            total_impact_ms: Math.round((tRecalc - t0) * 100) / 100
          }};
        }})()"""
        css_impact = page.evaluate(css_eval)

    if actions:
        execute_action_sequence(page, actions)

    if duration > 0:
        page.wait_for_timeout(int(duration * 1000))
    elif settle_ms > 0:
        page.wait_for_timeout(settle_ms)

    raw_metrics = page.evaluate(COLLECT_PERF_METRICS_JS)
    sys_metrics = sys_mon.stop()
    t_end = time.time()
    total_duration = round(t_end - t_start, 2)

    # Compute mutation rate per second
    dom_muts = raw_metrics.get("dom_mutations", {})
    total_muts = dom_muts.get("total", 0)
    dom_muts["rate_per_sec"] = round(total_muts / total_duration, 1) if total_duration > 0 else 0.0

    return PerformanceReport(
        url=url,
        duration_seconds=total_duration,
        navigation=raw_metrics.get("navigation", {}),
        paint=raw_metrics.get("paint", {}),
        layout=raw_metrics.get("layout", {}),
        long_tasks=raw_metrics.get("long_tasks", {}),
        resources=raw_metrics.get("resources", {}),
        dom_mutations=dom_muts,
        system_resources=sys_metrics,
        script_impact=script_impact,
        css_impact=css_impact,
    )
