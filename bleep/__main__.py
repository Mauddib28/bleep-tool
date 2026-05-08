"""Allow ``python -m bleep`` to launch the CLI."""

import sys

from bleep.cli import main

sys.exit(main())
