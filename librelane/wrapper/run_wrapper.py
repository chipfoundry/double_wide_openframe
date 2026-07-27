#!/usr/bin/env python3
"""Entry point that registers Wrapper.* steps then launches LibreLane."""
import wrapper_steps  # noqa: F401  — registers Wrapper.AddPowerEdgePorts
from librelane.__main__ import cli

if __name__ == "__main__":
    cli()
