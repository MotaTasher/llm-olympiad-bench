"""Run only final-task pairs without a successful Kimi inference."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.run_model_batch import main


if __name__ == "__main__":
    sys.argv[1:1] = ["--competition", "math-cup-2026-final", "--models", "kimi:kimi-k2.5", "--problems", "01,02,03,04,05,06,07,08,09", "--max-tokens", "256000", "--only-missing"]
    raise SystemExit(main())
