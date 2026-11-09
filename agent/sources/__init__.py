from agent.sources.brac import BRAC
from agent.sources.egp import EGP
from agent.sources.smef import SMEF
from agent.sources.undp import UNDP
from agent.sources.ungm import UNGM

# Order matters for cross-portal dedup: the first portal to report a reference keeps the notice.
REGISTRY = {cls.name: cls for cls in (UNDP, UNGM, EGP, BRAC, SMEF)}
