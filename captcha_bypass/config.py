import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


class Config:
    """Reads solver keys from the environment. All keys are optional."""

    def __init__(self, **overrides):
        self.anticaptcha_key = os.getenv("ANTICAPTCHA_KEY")
        self.capsolver_key = os.getenv("CAPSOLVER_KEY")
        self.twocaptcha_key = os.getenv("TWOCAPTCHA_KEY")
        self.timeout = int(os.getenv("CAPTCHA_TIMEOUT", "120"))
        self.poll_interval = float(os.getenv("CAPTCHA_POLL_INTERVAL", "3"))
        # explicit preference order (cheapest-first default)
        self.prefer = [p.strip() for p in os.getenv("CAPTCHA_PREFER", "").split(",") if p.strip()]
        for k, v in overrides.items():
            setattr(self, k, v)

    def keys(self):
        return {
            "anticaptcha": self.anticaptcha_key,
            "capsolver": self.capsolver_key,
            "twocaptcha": self.twocaptcha_key,
        }
