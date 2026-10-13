"""SCE inflation-expectations study. Importing the package registers its four abc
implementations (env/pop/decision/collector) so engine.build_simulator can resolve them.

The only maintained source lives here in socioverse_challenge; the copy under
socioverse2_repo/studies/ is a one-way runtime export (scripts/export_study_runtime.py).
"""

from __future__ import annotations

from . import model  # noqa: F401  (side effect: @register decorators run)
from . import native_spending  # noqa: F401
from . import price_contact  # noqa: F401
from . import news_exposure  # noqa: F401
from . import confidence_experiment  # noqa: F401
from . import lifetime_experiment  # noqa: F401
from . import lifetime_text_experiment  # noqa: F401
from . import prior_belief_experiment  # noqa: F401

__all__ = ["model"]
