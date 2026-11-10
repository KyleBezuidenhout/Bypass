"""Solver registry. Picks the cheapest *available* solver that supports a captcha kind."""
from ..config import Config
from .base import BaseSolver, SolveError
from .anticaptcha import AntiCaptchaSolver
from .capsolver import CapSolverSolver
from .twocaptcha import TwoCaptchaSolver

ALL = [AntiCaptchaSolver, CapSolverSolver, TwoCaptchaSolver]


def available_solvers(config=None):
    """Return instantiated solvers for every provider whose key is set."""
    cfg = config or Config()
    out = []
    for cls in ALL:
        key = cfg.keys().get(cls.name)
        if key:
            try:
                out.append(cls(key, timeout=cfg.timeout, poll_interval=cfg.poll_interval))
            except SolveError:
                pass
    return out


def get_solver(kind, config=None):
    """Cheapest solver that supports `kind`, or None if no key is configured."""
    cfg = config or Config()
    candidates = [s for s in available_solvers(cfg) if kind in s.supports]
    if not candidates:
        return None
    if cfg.prefer:
        order = {name: i for i, name in enumerate(cfg.prefer)}
        candidates.sort(key=lambda s: order.get(s.name, 999))
    else:
        candidates.sort(key=lambda s: s.price.get(kind, 999))
    return candidates[0]
