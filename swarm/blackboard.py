"""
swarm/blackboard.py
─────────────────────────────────────────────────────────────
Persistent shared blackboard for the Crypto Sniper agent swarm.

Every agent writes its findings here. The orchestrator reads the
complete state and scores convergence. Supabase is the backing
store so agents can crash/restart without losing state and the
Markov layer has history to fit on in Week 3.

Tables required (see swarm/schema.sql):
  agent_writes  - latest write per agent per asset
  signals       - every fired signal + outcome tracking
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ── Supabase client (lazy init) ────────────────────────────────────

_sb = None


def _client():
    global _sb
    if _sb is None:
        try:
            from supabase import create_client
            url = os.environ["SUPABASE_URL"]
            key = os.environ["SUPABASE_KEY"]
            _sb = create_client(url, key)
        except Exception as e:
            logger.error(f"Supabase init failed: {e}")
            raise
    return _sb


# ── Blackboard class ───────────────────────────────────────────────

class Blackboard:
    """
    Shared state store for all swarm agents.

    Usage:
        from swarm.blackboard import blackboard as bb

        # Agent writes
        bb.write("signal", "BTC", {"kalman_price": 43218.44})

        # Orchestrator reads full state
        state = bb.read("BTC")
    """

    def write(
        self,
        agent:     str,
        asset:     str,
        data:      dict[str, Any],
        run_ms:    Optional[int] = None,
    ) -> bool:
        """
        Upsert agent output to the blackboard.
        Uses UNIQUE(department, agent, namespace) constraint.
        Returns True on success.
        """
        try:
            payload = {
                "department": "signal",
                "agent":      agent,
                "namespace":  asset.upper(),
                "data":       data,
                "written_at": datetime.now(timezone.utc).isoformat(),
            }
            if run_ms is not None:
                payload["run_ms"] = run_ms

            _client().table("agent_writes").upsert(
                payload,
                on_conflict="department,agent,namespace"
            ).execute()

            logger.debug(f"Blackboard write: {agent}/{asset} keys={list(data.keys())}")
            return True

        except Exception as e:
            logger.error(f"Blackboard write failed [{agent}/{asset}]: {e}")
            return False

    def read(self, asset: str) -> dict[str, Any]:
        """
        Read all agent outputs for an asset.
        Merges all agent writes into a single flat dict.
        Most recent write per agent wins.
        Returns empty dict if no data or on error.
        """
        try:
            rows = (
                _client()
                .table("agent_writes")
                .select("agent, data, written_at")
                .eq("department", "signal")
                .eq("namespace", asset.upper())
                .execute()
            )

            merged = {}
            for row in (rows.data or []):
                agent_data = row.get("data", {})
                if isinstance(agent_data, str):
                    agent_data = json.loads(agent_data)
                merged.update(agent_data)

            return merged

        except Exception as e:
            logger.error(f"Blackboard read failed [{asset}]: {e}")
            return {}

    def read_agent(
        self,
        agent: str,
        asset: str,
    ) -> dict[str, Any]:
        """
        Read output from a specific agent for an asset.
        Returns empty dict if not found or on error.
        """
        try:
            row = (
                _client()
                .table("agent_writes")
                .select("data")
                .eq("department", "signal")
                .eq("agent", agent)
                .eq("namespace", asset.upper())
                .single()
                .execute()
            )

            if row.data:
                data = row.data.get("data", {})
                if isinstance(data, str):
                    data = json.loads(data)
                return data
            return {}

        except Exception as e:
            logger.debug(f"Blackboard read_agent [{agent}/{asset}]: {e}")
            return {}

    def clear(self, asset: str) -> bool:
        """
        Clear all agent writes for an asset.
        Used for testing and pipeline resets.
        """
        try:
            _client().table("agent_writes").delete().eq(
                "namespace", asset.upper()
            ).eq("department", "signal").execute()
            return True
        except Exception as e:
            logger.error(f"Blackboard clear failed [{asset}]: {e}")
            return False

    def ping(self) -> bool:
        """Check Supabase connectivity."""
        try:
            _client().table("agent_writes").select("id").limit(1).execute()
            return True
        except Exception:
            return False


# ── Singleton ──────────────────────────────────────────────────────

blackboard = Blackboard()
