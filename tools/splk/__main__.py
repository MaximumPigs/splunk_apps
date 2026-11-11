"""Allow ``python -m splk`` when the package is importable but not installed."""

import sys

from splk.cli import main

sys.exit(main())
