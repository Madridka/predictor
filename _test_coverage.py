"""Test fallback risky pick coverage."""
import sys
sys.path.insert(0, ".")

from wc2026.data_loader import load_matches
from wc2026.results_loader import load_results
from wc2026.risky_scan import scan_positive_ev_picks

r = scan_positive_ev_picks()
print("matches", r["stats"]["matches"], "total picks", r["stats"]["total"], "scheduled", r["stats"]["scheduled_matches"])
