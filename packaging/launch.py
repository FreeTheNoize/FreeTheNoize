import sys

from freethenoize import runtime

# Windowed build double-clicked on Windows: no stdout/stderr. Fix before anything logs.
runtime.ensure_std_streams()

from freethenoize.app import main  # noqa: E402

sys.exit(main(sys.argv[1:] or ["app"]))
