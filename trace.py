#!/usr/bin/env python3
"""Entry-point wrapper — allows running `python trace.py <args>` directly."""

import sys
from tracer.cli import run

if __name__ == "__main__":
    run(sys.argv[1:])
