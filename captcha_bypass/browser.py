"""Stealth browser via SeleniumBase CDP mode (free, no keys)."""

def launch(**kwargs):
    """Return a SeleniumBase pure-CDP session object.

    Uses `sb_cdp.Chrome()` which drives Chrome over the DevTools Protocol and
    is far harder for anti-bot systems to detect than plain WebDriver.
    """
    from seleniumbase import sb_cdp
    # Defaults tuned for stealth; override via kwargs if needed.
    kwargs.setdefault("incognito", True)
    return sb_cdp.Chrome(**kwargs)
