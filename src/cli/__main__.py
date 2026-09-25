"""Package execution shim so ``python -m cli`` works in development."""

import sys

from cli.app import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
