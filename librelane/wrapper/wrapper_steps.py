"""Custom LibreLane steps for the empty double-wide wrapper harden."""

import os
from typing import List

from librelane.steps import Step
from librelane.steps.odb import OdbpyStep

# Same file as FP_DEF_TEMPLATE in config.json (cannot redeclare that Variable).
_PIN_TEMPLATE = os.path.join(os.path.dirname(__file__), "pin_template.def")


@Step.factory.register()
class AddPowerEdgePorts(OdbpyStep):
    id = "Wrapper.AddPowerEdgePorts"
    name = "Append clamp-aligned met3 edge power ports (keep PDN ring ports)"

    def get_script_path(self):
        return os.path.join(os.path.dirname(__file__), "add_power_edge_ports.py")

    def get_command(self) -> List[str]:
        return super().get_command() + [
            "--def-template",
            _PIN_TEMPLATE,
        ]
