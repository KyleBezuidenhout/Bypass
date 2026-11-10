"""2Captcha (https://2captcha.com) — human workers. Docs: https://2captcha.com/2captcha-api"""
import requests
from .base import BaseSolver, SolveError

API = "https://2captcha.com"

METHOD = {
    "recaptcha_v2": "userrecaptcha",
    "recaptcha_v3": "userrecaptcha",
    "turnstile": "turnstile",
    "hcaptcha": "hcaptcha",
    "image": "base64",
}


class TwoCaptchaSolver(BaseSolver):
    name = "twocaptcha"
    supports = ("recaptcha_v2", "recaptcha_v3", "turnstile", "hcaptcha")
    price = {"recaptcha_v2": 1.0, "recaptcha_v3": 1.45, "turnstile": 1.45, "hcaptcha": 2.99}

    def solve(self, kind, sitekey, url, action=None, min_score=None):
        data = {"key": self.key, "method": METHOD[kind], "pageurl": url, "json": 1}
        if kind in ("recaptcha_v2", "recaptcha_v3"):
            data["googlekey"] = sitekey
            if kind == "recaptcha_v3":
                data["version"] = "v3"
                if action:
                    data["action"] = action
                if min_score is not None:
                    data["min_score"] = min_score
        else:
            data["sitekey"] = sitekey

        r = requests.post(f"{API}/in.php", data=data, timeout=30).json()
        if str(r.get("status")) != "1":
            raise SolveError(f"2captcha submit: {r.get('request')}")
        task_id = r["request"]

        def check():
            res = requests.get(
                f"{API}/res.php",
                params={"key": self.key, "action": "get", "id": task_id, "json": 1},
                timeout=30,
            ).json()
            if str(res.get("status")) == "1":
                return res["request"]
            return "CAPCHA_NOT_READY"

        return self._poll(check)
