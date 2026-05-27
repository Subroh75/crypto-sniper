"""
swarm/blackboard.py
───────────────────
Persistent shared blackboard for the Crypto Sniper agent swarm.

Every agent writes its findings here. The orchestrator reads the
complete state and scores convergence. Supabase is the backing
store so agents can crash/restart without losing state and the
Markov layer has history to fit on in Week 3.

Tables required (see swarm/schema.sql):
  agent_writes    — latest write per agent per asset
    signal_history  — every fired signal + outcome tracking
    """

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────
# Supabase client (lazy init)
# ─────────────────────────────────────────
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


# ─────────────────────────────────────────
# Blackboard
# ─────────────────────────────────────────
class Blackboard:
      """
          Shared state store for all swarm agents.

              Write pattern  : each agent calls write() with its findings
                  Read pattern   : orchestrator calls read() to get merged state
                      History pattern: markov_agent calls history() to fit HMM
                          """

    def write(
              self,
              agent: str,
              asset: str,
              data: dict[str, Any],
    ) -> None:
              """
                      Upsert agent findings for an asset.
                              One row per (agent, asset) — latest write wins.
                                      """
              payload = {
                  "agent": agent,
                  "asset": asset.upper(),
                  "data": json.dumps(data),
                  "written_at": datetime.now(timezone.utc).isoformat(),
              }
              try:
                            _client().table("agent_writes").upsert(
                                              payload,
                                              on_conflict="agent,asset"
                            ).execute()
                            logger.debug(f"[{agent}] wrote {asset}: {list(data.keys())}")
except Exception as e:
            logger.error(f"Blackboard.write failed [{agent}/{asset}]: {e}")

    def read(self, asset: str) -> dict[str, Any]:
              """
                      Merge latest writes from ALL agents for an asset.
                              Returns flat dict — later agents overwrite earlier keys.
                                      """
              try:
                            rows = (
                                              _client().table("agent_writes")
                                              .select("agent, data, written_at")
                                              .eq("asset", asset.upper())
                                              .execute()
                            )
                            state: dict[str, Any] = {}
                            seen: set[str] = set()
                            # rows already ordered by upsert recency
                            for row in rows.data:
                                              if row["agent"] not in seen:
                                                                    state.update(json.loads(row["data"]))
                                                                    seen.add(row["agent"])
                                                            return state
except Exception as e:
            logger.error(f"Blackboard.read failed [{asset}]: {e}")
            return {}

    def read_all_assets(self) -> dict[str, dict[str, Any]]:
              """Return merged state for every asset currently on the board."""
              try:
                            rows = (
                                              _client().table("agent_writes")
                                              .select("agent, asset, data, written_at")
                                              .execute()
                            )
                            assets: dict[str, dict] = {}
                            for row in rows.data:
                                              a = row["asset"]
                                              if a not in assets:
                                                                    assets[a] = {}
                                                                assets[a].update(json.loads(row["data"]))
                                          return assets
except Exception as e:
            logger.error(f"Blackboard.read_all_assets failed: {e}")
            return {}

    def record_signal(
              self,
              asset: str,
              direction: str,          # LONG | SHORT | NEUTRAL
              conviction: int,         # 0-100
              signal_type: str,        # CEX_SWARM | DEX_GEM
              state_snapshot: dict,    # full blackboard state at fire time
              rr_ratio: float = 0.0,
              entry: float = 0.0,
              stop: float = 0.0,
              target: float = 0.0,
    ) -> None:
              """
                      Persist every fired signal for accuracy tracking + Markov.
                              outcome is filled in later by signal_tracker.py.
                                      """
              payload = {
                  "asset": asset.upper(),
                  "direction": direction,
                  "conviction": conviction,
                  "signal_type": signal_type,
                  "rr_ratio": rr_ratio,
                  "entry": entry,
                  "stop": stop,
                  "target": target,
                  "state_snapshot": json.dumps(state_snapshot),
                  "fired_at": datetime.now(timezone.utc).isoformat(),
                  "outcome": None,        # WIN | LOSS | STOPPED | OPEN
                  "outcome_pct": None,    # actual % move after signal
                  "resolved_at": None,
              }
              try:
                            _client().table("signal_history").insert(payload).execute()
                            logger.info(
                                f"Signal recorded: {asset} {direction} "
                                f"conviction={conviction} rr={rr_ratio:.1f}"
                            )
except Exception as e:
            logger.error(f"Blackboard.record_signal failed: {e}")

    def history(
              self,
              asset: str,
              limit: int = 500,
      
