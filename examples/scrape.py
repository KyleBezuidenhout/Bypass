"""Scrape a protected page, auto-bypassing any CAPTCHA that appears.

Set a solver key (e.g. export ANTICAPTCHA_KEY=...) to enable the paid vision layer.
With no key set it still runs in free stealth mode.
"""
from captcha_bypass import Bypass

TARGET = "https://seleniumbase.io/apps/turnstile"

with Bypass() as b:
    b.goto(TARGET)
    result = b.solve_if_present()
    print("captcha handling:", result)
    html = b.page_source()
    print("page bytes:", len(html))
