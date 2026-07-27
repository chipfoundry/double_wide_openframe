"""Custom LibreLane steps for the double-wide padframe flow.

Registers ``Padframe.ResetSpecialNets``, inserted right before
``OpenROAD.GlobalRouting`` (see config.yaml ``meta.substituting_steps``:
``-OpenROAD.GlobalRouting``). It marks the whole reset subsystem's nets SPECIAL so
TritonRoute leaves them alone -- their exact geometry is copied from openframe at
the magic integrate step (scripts/integrate_openframe.tcl). This mirrors caravel,
which hand-routes the reset subsystem in magic.
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
class BridgeDM0(OdbpyStep):
    id = "Padframe.BridgeDM0"
    name = "Bridge each gpio_dm0 route to its DM[0] pad pin (same-net met2 patch)"

    def get_script_path(self):
        return os.path.join(os.path.dirname(__file__), "bridge_dm0.py")
