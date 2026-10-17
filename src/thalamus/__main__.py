"""`python -m thalamus` — how an installed wheel's hooks and registrations run the CLI."""

import sys

from thalamus.cli import main

# argparse names the program after argv[0], which under `-m` is this file's path.
sys.argv[0] = "thalamus"
main()
