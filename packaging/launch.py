import sys

from freethenoize import runtime

# Windowed build double-clicked on Windows: no stdout/stderr. Fix before anything logs.
runtime.ensure_std_streams()

from freethenoize.app import main  # noqa: E402

try:
    sys.exit(main(sys.argv[1:] or ["app"]))
except SystemExit:
    raise
except BaseException as exc:  # noqa: BLE001 - last resort: never die silently
    import logging
    import traceback

    logging.getLogger("freethenoize").exception("fatal error")
    traceback.print_exc()
    from freethenoize import logs

    runtime.alert("FreeTheNoize no ha podido arrancar",
                  f"{type(exc).__name__}: {exc}\n\nDetalles en:\n{logs.default_file()}")
    sys.exit(1)
