#!/usr/bin/env python3
"""Compatibility alias for the renamed SSHelp CLI."""

from sshelp import *  # noqa: F401,F403 - preserve the tested Python API.


if __name__ == "__main__":
    raise SystemExit(main())
