#!/usr/bin/env python3
"""Entry point that registers Padframe.* steps then launches LibreLane."""
import padframe_steps  # noqa: F401  — registers the Padframe.* steps
from librelane.__main__ import cli

if __name__ == "__main__":
    cli()
