"""Solve a Cloudflare Turnstile widget and verify success.

Requires one solver key (the paid layer). Turnstile is the cheapest kind.
"""
from captcha_bypass import Bypass, get_solver

with Bypass() as b:
    b.goto("https://seleniumbase.io/apps/turnstile", solve=False)
    solver = get_solver("turnstile")
    print("using solver:", solver.name if solver else "none (free click-only)")

    res = b.solve_if_present()
    print("result:", res)

    b.sleep(2)
    if b.evaluate("!!document.querySelector('img#captcha-success')"):
        print("SUCCESS: turnstile bypassed")
    else:
        print("not confirmed")
