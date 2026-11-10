"""Base solver interface + shared helpers."""

import time


class SolveError(Exception):
    pass


class BaseSolver:
    name = "base"
    supports = ()          # tuple of captcha kinds this solver can handle
    price = {}             # kind -> USD per 1000 solves (for cheapest-first routing)

    def __init__(self, key, timeout=120, poll_interval=3):
        if not key:
            raise SolveError(f"{self.name}: missing API key")
        self.key = key
        self.timeout = timeout
        self.poll_interval = poll_interval

    def solve(self, kind, sitekey, url, action=None, min_score=None):
        raise NotImplementedError

    # --- helpers ---
    def _deadline(self):
        return time.time() + self.timeout

    def _poll(self, check, describe="solution"):
        deadline = self._deadline()
        while time.time() < deadline:
            time.sleep(self.poll_interval)
            result = check()
            if result not in (None, "processing", "CAPCHA_NOT_READY", "not_ready"):
                return result
        raise SolveError(f"{self.name}: timeout waiting for {describe}")
