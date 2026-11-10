"""Orchestrator: navigate stealthily, detect CAPTCHAs, solve with the cheapest
available solver, inject the token, and fall back to free click-only solving."""
from . import browser, detect as _detect
from .config import Config
from .solvers import get_solver


class Bypass:
    def __init__(self, config=None, solver=None, launch_kwargs=None):
        self.cfg = config or Config()
        self._fixed_solver = solver
        self.sb = browser.launch(**(launch_kwargs or {}))

    # --- navigation ---
    def goto(self, url, solve=True):
        self.sb.goto(url)
        self.sb.sleep(1)
        if solve:
            self.solve_if_present()
        return self

    # --- core ---
    def solve_if_present(self):
        """Detect and solve every CAPTCHA on the page. Returns a list of results."""
        found = _detect.detect(self.sb)
        results = []
        for cap in found:
            kind = cap["kind"]
            solver = self._fixed_solver or get_solver(kind, self.cfg)
            token = None
            if solver and kind in solver.supports:
                token = solver.solve(kind, cap["sitekey"], self.sb.get_current_url(), action=cap.get("cb"))
            if token:
                _detect.inject(self.sb, kind, token, cap.get("cb"))
                results.append({"kind": kind, "method": "solver:" + solver.name})
            else:
                # free fallback: let SeleniumBase click / drag it
                try:
                    self.sb.solve_captcha()
                    results.append({"kind": kind, "method": "click-only"})
                except Exception as e:  # noqa
                    results.append({"kind": kind, "method": "unsolved", "error": str(e)})
        return results

    # --- passthroughs ---
    def page_source(self):
        return self.sb.get_page_source()

    def evaluate(self, js):
        return self.sb.evaluate(js)

    def get_current_url(self):
        return self.sb.get_current_url()

    def sleep(self, s):
        self.sb.sleep(s)
        return self

    # --- lifecycle ---
    def quit(self):
        try:
            self.sb.quit()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.quit()
