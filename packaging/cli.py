# Console entry point (ftn / ftn.exe): same app, but with a terminal attached,
# so `ftn get URL` and `ftn serve` print their output. No arguments = help.
import sys

from freethenoize.app import main

sys.exit(main(sys.argv[1:] or ["--help"]))
