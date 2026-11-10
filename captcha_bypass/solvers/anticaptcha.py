"""Anti-Captcha (https://anti-captcha.com) — human workers. Docs: https://anti-captcha.com/apidoc"""
import requests
from .base import BaseSolver, SolveError

API = "https://api.anti-captcha.com"

TASK_TYPE = {
    "recaptcha_v2": "RecaptchaV2TaskProxyless",
    "recaptcha_v3": "RecaptchaV3TaskProxyless",
    "turnstile": "TurnstileTaskProxyless",
    "hcaptcha": "HCaptchaTaskProxyless",
}


class AntiCaptchaSolver(BaseSolver):
    name = "anticaptcha"
    supports = ("recaptcha_v2", "recaptcha_v3", "turnstile", "hcaptcha")
    price = {"recaptcha_v2": 0.95, "recaptcha_v3": 1.0, "turnstile": 2.0, "hcaptcha": 2.0}

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
            raise SolveError(f"anticaptcha submit: {r.get('errorCode')} {r.get('errorDescription')}")
        task_id = r["taskId"]

        def check():
            res = requests.post(
                f"{API}/getTaskResult",
                json={"clientKey": self.key, "taskId": task_id},
                timeout=30,
            ).json()
            if res.get("errorId"):
                raise SolveError(f"anticaptcha poll: {res.get('errorCode')}")
            if res.get("status") == "ready":
                sol = res["solution"]
                return sol.get("gRecaptchaResponse") or sol.get("token")
            return "processing"

        return self._poll(check)
