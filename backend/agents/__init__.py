"""The five Campus Customs agents. Import SPECS for the full roster."""

from models import AgentName

from . import accounting, boss, customer_service, facilities, inventory
from .base import HUMAN_ONLY_TOOLS, WRITE_TOOLS, AgentSpec

SPECS: dict[AgentName, AgentSpec] = {
    s.name: s
    for s in (boss.SPEC, inventory.SPEC, accounting.SPEC, facilities.SPEC, customer_service.SPEC)
}

__all__ = ["SPECS", "WRITE_TOOLS", "HUMAN_ONLY_TOOLS", "AgentSpec"]
