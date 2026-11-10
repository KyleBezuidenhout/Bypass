"""captcha-bypass: stealth (free) + optional paid vision solvers, one interface."""
from .bypass import Bypass
from .config import Config
from .solvers import get_solver, available_solvers

__all__ = ["Bypass", "Config", "get_solver", "available_solvers"]
__version__ = "1.0.0"
