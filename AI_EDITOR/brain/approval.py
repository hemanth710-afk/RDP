"""Human approval gate for AI-generated editing plans."""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock

from .editing_plan import EditingPlan


class ApprovalError(RuntimeError):
    """Raised when an editing plan cannot be approved."""


@dataclass(frozen=True, slots=True)
class ApprovalResult:
    """Result of an approval decision."""

    approved: bool
    plan_title: str
    action_count: int


class EditingPlanApproval:
    """Require explicit user approval before execution."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._pending_plan: EditingPlan | None = None

    @property
    def has_pending_plan(self) -> bool:
        """Return True when a plan is waiting for approval."""

        with self._lock:
            return self._pending_plan is not None

    def submit(self, plan: EditingPlan) -> None:
        """Place a validated plan into the approval queue."""

        if not isinstance(plan, EditingPlan):
            raise TypeError(
                "plan must be an EditingPlan."
            )

        with self._lock:
            if self._pending_plan is not None:
                raise ApprovalError(
                    "Another editing plan is already awaiting approval."
                )

            self._pending_plan = plan

    def get_pending(self) -> EditingPlan | None:
        """Return the pending plan, if one exists."""

        with self._lock:
            return self._pending_plan

    def approve(self) -> EditingPlan:
        """Approve and release the pending plan for execution."""

        with self._lock:
            if self._pending_plan is None:
                raise ApprovalError(
                    "There is no editing plan awaiting approval."
                )

            plan = self._pending_plan
            self._pending_plan = None

        return plan

    def reject(self) -> ApprovalResult:
        """Reject and discard the pending plan."""

        with self._lock:
            if self._pending_plan is None:
                raise ApprovalError(
                    "There is no editing plan awaiting approval."
                )

            plan = self._pending_plan
            self._pending_plan = None

        return ApprovalResult(
            approved=False,
            plan_title=plan.title,
            action_count=plan.action_count,
        )

    def cancel(self) -> None:
        """Cancel the pending plan without approving it."""

        with self._lock:
            self._pending_plan = None

    def describe_pending(self) -> str:
        """Return a concise human-readable plan summary."""

        plan = self.get_pending()

        if plan is None:
            raise ApprovalError(
                "There is no editing plan awaiting approval."
            )

        return (
            f"Title: {plan.title}\n"
            f"Duration: {plan.duration:.2f}s\n"
            f"Resolution: {plan.width}x{plan.height}\n"
            f"Frame rate: {plan.frame_rate:g} FPS\n"
            f"Actions: {plan.action_count}\n"
            f"Source files: {len(plan.source_files)}"
        )