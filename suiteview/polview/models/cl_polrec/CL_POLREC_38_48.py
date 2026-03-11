"""
CL_POLREC_38_48 — Agent Records (Records 38, 48)
==================================================

DB2 tables
----------
Record 38 — Agent Commission
    LH_AGT_COM_AMT      Agent commission amounts per phase

Record 48 — Writing Agent Name
    LH_CTT_COM_PHA_WA   Writing agent name/info
"""

from __future__ import annotations

from decimal import Decimal
from typing import List, Optional

from .cyberlife_base import PolicyDataAccessor
from .policy_data_classes import AgentInfo


class AgentRecords:
    """System-layer access for agent Cyberlife policy records."""

    TABLES = (
        "LH_AGT_COM_AMT",
        "LH_CTT_COM_PHA_WA",
    )

    def __init__(self, policy: PolicyDataAccessor) -> None:
        self._policy = policy
        self._agents: Optional[List[AgentInfo]] = None

    def invalidate(self) -> None:
        self._agents = None

    # =====================================================================
    # AGENT COMMISSION (LH_AGT_COM_AMT)
    # =====================================================================

    @property
    def agent_count(self) -> int:
        return self._policy.data_item_count("LH_AGT_COM_AMT")

    def get_agents(self) -> List[AgentInfo]:
        if self._agents is not None:
            return self._agents
        self._agents = []
        for row in self._policy.fetch_table("LH_AGT_COM_AMT"):
            agent = AgentInfo(
                agt_com_pha_nbr=int(row.get("AGT_COM_PHA_NBR", 0)),
                agent_id=str(row.get("AGT_ID", "")),
                commission_pct=None,    # COM_PCT does not exist on LH_AGT_COM_AMT
                market_org_cd="",       # MKT_ORG_CD does not exist on LH_AGT_COM_AMT
                svc_agt_ind="",         # SVC_AGT_IND does not exist on LH_AGT_COM_AMT
                raw_data=row,
            )
            self._agents.append(agent)
        return self._agents

    @property
    def writing_agent_id(self) -> str:
        agents = self.get_agents()
        for agt in agents:
            if agt.agt_com_pha_nbr == 1:
                return agt.agent_id
        return agents[0].agent_id if agents else ""

    # =====================================================================
    # WRITING AGENT NAME (LH_CTT_COM_PHA_WA)
    # =====================================================================

    @property
    def writing_agent_name(self) -> str:
        return str(self._policy.data_item("LH_CTT_COM_PHA_WA", "WRT_AGT_NM") or "").strip()
