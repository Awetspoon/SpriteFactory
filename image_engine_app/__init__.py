"""Package bootstrap for Sprite Factory image_engine_app.

This keeps legacy absolute imports (from `app`, `engine`, `ui`) working when the
package is imported as `image_engine_app.*` from the project root.
"""

from __future__ import annotations

from pathlib import Path
import sys

_PACKAGE_ROOT = Path(__file__).resolve().parent
if str(_PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PACKAGE_ROOT))
