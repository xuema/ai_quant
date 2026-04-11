"""
Unified configuration for announcement_alpha daily run.
All parameters live here — edit once, used everywhere.
"""
import os

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_BASE_DIR = os.path.dirname(_SCRIPT_DIR)  # stock_selection/

def _project(path: str) -> str:
    """ Resolve path relative to project root (stock_selection/). """
    if os.path.isabs(path):
        return path
    return os.path.normpath(os.path.join(_SCRIPT_DIR, path))

CONFIG = {
    # ---- Data paths ----
    "announcement_dir": _project("data/raw_json"),
    "price_cache_dir": _project("../data_cache_daily"),
    "market_index_file": _project("data/market/000300.csv"),

    # ---- CAR (Cumulative Abnormal Return) ----
    "car_mode": "simple",        # "simple" | "market" (market = excess returns)
    "pre_window": 5,             # trading days before event
    "post_window": 3,            # trading days after event

    # ---- Signal generation ----
    "top_k": 20,                 # number of stocks to go long/short per day

    # ---- Risk model ----
    "factor_floor": -10,         # extreme factor lower bound filter
    "factor_cap": 10,            # extreme factor upper bound filter
    "winsor_lower": 0.05,        # winsorize lower quantile
    "winsor_upper": 0.95,        # winsorize upper quantile
}
