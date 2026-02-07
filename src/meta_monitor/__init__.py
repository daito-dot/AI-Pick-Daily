"""Meta-monitor: autonomous performance improvement agent.

Detect → Diagnose → Act → Evaluate cycle that runs as Step 7
of the daily review pipeline.
"""

from .service import run_meta_monitor

__all__ = ["run_meta_monitor"]
