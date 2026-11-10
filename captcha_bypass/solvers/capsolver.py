"""CapSolver (https://capsolver.com) — ML solver. Docs: https://docs.capsolver.com"""
import requests
from .base import BaseSolver, SolveError

API = "https://api.capsolver.com"

TASK_TYPE = {
    "recaptcha_v2": "ReCaptchaV2TaskProxyLess",
    "recaptcha_v3": "ReCaptchaV3TaskProxyLess",
    "turnstile": "AntiTurnstileTaskProxyLess",
    "hcaptcha": "HCaptchaTaskProxyLess",
}


class CapSolverSolver(BaseSolver):
    name = "capsolver"
    supports = ("recaptcha_v2", "recaptcha_v3", "turnstile", "hcaptcha")
    price = {"recaptcha_v2": 0.80, "recaptcha_v3": 1.00, "turnstile": 1.20, "hcaptcha": 1.00}

    def solve(self, kind, sitekey, url, action=None, min_score=None):
        task = {"type": TASK_TYPE[kind], "websiteURL": url, "websiteKey": sitekey}
        if kind == "recaptcha_v3":
            task["pageAction"] = action or "verify"
            task["minScore"] = min_score if min_score is not None else 0.3

        r = requests.post(
            f"{API}/createTask",
            json={"clientKey": self.key, "task": task},
            timeout=30,
        ).json()
        if r.get("errorId"):
            raise SolveError(f"capsolver submit: {r.get('errorCode')} {r.get('errorDescription')}")
        task_id = r["taskId"]

        def check():
            res = requests.post(
                f"{API}/getTaskResult",
                json={"clientKey": self.key, "taskId": task_id},
                timeout=30,
            ).json()
            if res.get("errorId"):
                raise SolveError(f"capsolver poll: {res.get('errorCode')}")
            if res.get("status") == "ready":
                sol = res["solution"]
                return sol.get("gRecaptchaResponse") or sol.get("token")
            return "processing"

        return self._poll(check)
