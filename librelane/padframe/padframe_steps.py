"""Custom LibreLane steps for the double-wide padframe flow.

Registers:
  * ``Padframe.ResetSpecialNets`` -- before GlobalRouting; marks POR/reset nets
    SPECIAL so TritonRoute leaves them alone.
  * ``Padframe.PorbRing`` -- right after ResetSpecialNets; draws the openframe
    porb_h met1 loop around the user area plus a via1/met2 tap to every pad
    ENABLE_H / ENABLE_VDDA_H pin and to simple_por.
  * ``Padframe.XresLoops`` -- right after PorbRing; draws the reset pad's local
    tie-off and loopback wiring, as hand-drawn in the openframe.
  * ``Padframe.ClampLinks`` -- right after XresLoops; joins each user domain's
    vccd and vssd clamp pads with two met5 straps.
  * ``Padframe.UserIdPower`` -- right after ClampLinks; straps the
    user_id_programming block's rails to the pad ring's vccd / vssd rails.
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
class PorbRing(OdbpyStep):
    id = "Padframe.PorbRing"
    name = "Hand-drawn porb_h met1 loop + pad enable taps (openframe-style)"

    def get_script_path(self):
        return os.path.join(os.path.dirname(__file__), "porb_ring.py")


@Step.factory.register()
class XresLoops(OdbpyStep):
    id = "Padframe.XresLoops"
    name = "Hand-drawn reset pad tie-off and loopback wiring (openframe-style)"

    def get_script_path(self):
        return os.path.join(os.path.dirname(__file__), "xres_loops.py")


@Step.factory.register()
class ClampLinks(OdbpyStep):
    id = "Padframe.ClampLinks"
    name = "met5 straps joining each user domain's vccd and vssd clamp pads"

    def get_script_path(self):
        return os.path.join(os.path.dirname(__file__), "clamp_links.py")


@Step.factory.register()
class UserIdPower(OdbpyStep):
    id = "Padframe.UserIdPower"
    name = "Hand-drawn power hookup of user_id_programming (openframe-style)"

    def get_script_path(self):
        return os.path.join(os.path.dirname(__file__), "user_id_power.py")


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
