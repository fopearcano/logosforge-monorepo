"""``python -m logosforge.api`` -> start the API server."""

import sys

from logosforge.api.server import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
