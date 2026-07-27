"""Custom LibreLane steps for the double-wide padframe flow.

Registers:
  * ``Padframe.ResetSpecialNets`` -- before GlobalRouting; marks POR/reset nets
    SPECIAL so TritonRoute leaves them alone.
  * ``Padframe.BridgePowerPads`` -- after InsertECODiodes / before DRT; draws
    wide special met3 straps from each clamp domain pin to the wrapper edge.
  * ``Padframe.BridgeDM0`` -- after DetailedRouting; same-net met2 patch for
    gpio_dm0 tip stubs.
"""

import os

from librelane.steps import Step
from librelane.steps.odb import OdbpyStep


@Step.factory.register()
class ResetSpecialNets(OdbpyStep):
    id = "Padframe.ResetSpecialNets"
    name = "Mark reset subsystem nets SPECIAL (routed from openframe at integrate)"

    def get_script_path(self):
        return os.path.join(os.path.dirname(__file__), "reset_special_nets.py")


@Step.factory.register()
class BridgePowerPads(OdbpyStep):
    id = "Padframe.BridgePowerPads"
    name = "Wide met3 straps from clamp power stubs to wrapper edge ports"

    def get_script_path(self):
        return os.path.join(os.path.dirname(__file__), "bridge_power_pads.py")


@Step.factory.register()
class BridgeDM0(OdbpyStep):
    id = "Padframe.BridgeDM0"
    name = "Bridge each gpio_dm0 route to its DM[0] pad pin (same-net met2 patch)"

    def get_script_path(self):
        return os.path.join(os.path.dirname(__file__), "bridge_dm0.py")
