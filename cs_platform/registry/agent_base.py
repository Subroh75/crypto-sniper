"""
cs_platform/registry/agent_base.py
─────────────────────────────────────────────────────────────
Universal base class for every agent in every swarm.

NOTE: Folder renamed from platform/ to cs_platform/ to avoid
collision with Python's built-in 'platform' standard library.

Every agent in every department inherits from BaseAgent.
This is the platform contract that makes the entire
multi-department architecture possible.

Departments:
  signal   - market intelligence (Kalman, GARCH, ARIMA, Whale)
  bizdev   - business development (leads, outreach)
  sales    - subscriber lifecycle (TON payments, churn)
  ops      - platform health (monitoring, alerts)
  product  - analytics (usage, feedback)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
import logging
import time


@dataclass
class AgentIdentity:
    """
    Immutable identity declaration for every agent.
    Defined as a class attribute on every BaseAgent subclass.
    """
    department:       str
    name:             str
    version:          str
    description:      str
    reads:            list[str]
    writes:           list[str]
    schedule_seconds: int


@dataclass
class AgentResult:
    """
    Standardised return type for every agent.run() call.
    Agents return this — they never raise exceptions.
    """
    success:     bool
    data:        dict[str, Any]
    duration_ms: int
    error:       Optional[str]   = None
    warnings:    list[str]       = field(default_factory=list)


class BaseAgent(ABC):
    """
    Abstract base for all swarm agents.

    Subclass pattern:

        class KalmanAgent(BaseAgent):
            identity = AgentIdentity(
                department="signal",
                name="kalman",
                version="1.0.0",
                description="Cleans price feed via Kalman filter",
                reads=[],
                writes=["kalman_price", "kalman_velocity"],
                schedule_seconds=300,
            )

            async def run(self, asset: str, context: dict) -> AgentResult:
                t0 = time.monotonic()
                try:
                    # your logic here
                    return self._ok({"kalman_price": 43218.44}, t0)
                except Exception as e:
                    return self._fail(str(e), t0)
    """

    identity: AgentIdentity  # must declare in every subclass

    def __init__(self):
        self.logger = logging.getLogger(
            f"{self.identity.department}.{self.identity.name}"
        )

    @abstractmethod
    async def run(
        self,
        asset:   str,
        context: dict[str, Any],
    ) -> AgentResult:
        """
        Core agent logic. Called by the scheduler every cycle.
        asset   = the asset being analysed e.g. "BTC"
        context = current blackboard state for this asset
        Must return AgentResult. Never raise.
        """
        ...

    async def health_check(self) -> bool:
        """Override to add API connectivity checks. Default: True."""
        return True

    # ── Helpers ────────────────────────────────────────────────

    def _ok(
        self,
        data:     dict[str, Any],
        t0:       float,
        warnings: list[str] = None,
    ) -> AgentResult:
        ms = int((time.monotonic() - t0) * 1000)
        self.logger.debug(
            f"[{self.identity.name}] OK {ms}ms keys={list(data.keys())}"
        )
        return AgentResult(
            success=True,
            data=data,
            duration_ms=ms,
            warnings=warnings or [],
        )

    def _fail(self, error: str, t0: float) -> AgentResult:
        ms = int((time.monotonic() - t0) * 1000)
        self.logger.error(
            f"[{self.identity.department}/{self.identity.name}] "
            f"FAILED {ms}ms: {error}"
        )
        return AgentResult(
            success=False,
            data={},
            duration_ms=ms,
            error=error,
        )

    def _warn(self, message: str) -> None:
        self.logger.warning(f"[{self.identity.name}] {message}")

    def log_health(
        self,
        status:  str,
        details: Optional[dict] = None,
    ) -> None:
        """Write health status to Supabase agent_health table."""
        try:
            from swarm.db import insert
            insert("agent_health", {
                "department": self.identity.department,
                "agent":      self.identity.name,
                "status":     status,
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "details":    details or {},
            })
        except Exception as e:
            self.logger.error(f"log_health failed: {e}")

    @property
    def label(self) -> str:
        return f"{self.identity.department}/{self.identity.name}"

    def __repr__(self) -> str:
        return (
            f"<Agent {self.label} "
            f"v{self.identity.version} "
            f"every={self.identity.schedule_seconds}s>"
        )
