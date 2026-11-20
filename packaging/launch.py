import sys

from freethenoize.app import main

sys.exit(main(sys.argv[1:] or ["app"]))
