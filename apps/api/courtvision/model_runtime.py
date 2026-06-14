from __future__ import annotations

import sys
from importlib.metadata import version

_CURRENT_MODEL_RUNTIME = {
    "python": f"{sys.version_info.major}.{sys.version_info.minor}",
    "joblib": version("joblib"),
    "numpy": version("numpy"),
    "pandas": version("pandas"),
    "scikit_learn": version("scikit-learn"),
}


def current_model_runtime() -> dict[str, str]:
    return _CURRENT_MODEL_RUNTIME.copy()
