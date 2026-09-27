"""PolicyInformation agents section."""

from __future__ import annotations

from .base import PolicySection
from ..cl_polrec.policy_data_classes import AgentInfo
from ..cl_polrec.policy_translations import translate_market_org
from decimal import Decimal
from typing import List


class AgentsSection(PolicySection):
    """Cohesive PolicyInformation agents view."""

    TABLES = frozenset(('AGT_COM_PHA_NBR', 'AGT_ID', 'COM_PCT', 'LH_AGT_COM_AMT', 'LH_CTT_COM_PHA_WA', 'MKT_ORG_CD', 'SERVICING_AGENT_NUMBER', 'SERVICING_BRANCH_CODE', 'SVC_AGT_IND', 'WRT_AGT_NM',))
    CACHE_ATTRS = ('_agents',)

    @property
    def agent_count(self) -> int:
        """Number of agent records."""
        return self.data_item_count("LH_AGT_COM_AMT")

    def get_agents(self) -> List[AgentInfo]:
        """Get all agent records."""
        if self._agents is not None:
            return self._agents

        self._agents = []
        for row in self.fetch_table("LH_AGT_COM_AMT"):
            agent = AgentInfo(
                agt_com_pha_nbr=int(row.get("AGT_COM_PHA_NBR", 0)),
                agent_id=str(row.get("AGT_ID", "")),
                commission_pct=Decimal(str(row["COM_PCT"])) if row.get("COM_PCT") else None,
                market_org_cd=str(row.get("MKT_ORG_CD", "")),
                svc_agt_ind=str(row.get("SVC_AGT_IND", "")),
                raw_data=row
            )
            self._agents.append(agent)

        return self._agents

    @property
    def writing_agent(self) -> str:
        """Primary writing agent ID."""
        agents = self.get_agents()
        for agt in agents:
            if agt.agt_com_pha_nbr == 1:
                return agt.agent_id
        return agents[0].agent_id if agents else ""

    @property
    def servicing_agent_number(self) -> str:
        """Servicing agent number."""
        return str(self._field("servicing_agent_number") or "")

    @property
    def servicing_branch_code(self) -> str:
        """Servicing branch/agency code."""
        return str(self._field("servicing_branch_code") or "")

    @property
    def servicing_market_org(self) -> str:
        """Determine market organization from company and agent codes."""
        branch = self.servicing_branch_code
        agent_code = branch[0] if branch else ""
        return translate_market_org(self.identity.company_code, agent_code)

    @property
    def agency_branch_code(self) -> str:
        """Extract agency branch code from servicing branch code."""
        branch = self.servicing_branch_code
        return branch[1:5] if len(branch) >= 5 else branch

    @property
    def writing_agent_name(self) -> str:
        """Writing agent name."""
        return str(self.data_item("LH_CTT_COM_PHA_WA", "WRT_AGT_NM") or "").strip()
