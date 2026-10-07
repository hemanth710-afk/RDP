"""Manual integration test for AI status + visible AE 2022."""

from __future__ import annotations

import time

from ai_status import AIActivityService
from ae_visual import (
    AEVisualController,
    AEVisualSession,
)


def main() -> None:
    service = AIActivityService()

    controller = AEVisualController()

    session = AEVisualSession(
        ae_controller=controller,
        activity_service=service,
    )

    print("Starting AI + After Effects session...")
    session.start()

    print("AI STATE:", service.controller.state.value)
    print("SESSION ACTIVE:", session.is_active)
    print("AE RUNNING:", controller.is_running)

    print()
    print("The blue AI indicator should now be running.")
    print("After Effects 2022 should be visible.")
    print("Waiting 10 seconds...")
    print()

    for remaining in range(10, 0, -1):
        print(f"Running... {remaining}s")
        time.sleep(1)

    print()
    print("Requesting STOP...")

    session.request_stop()
    session.wait(timeout=5)

    print("AI STATE:", service.controller.state.value)
    print("SESSION ACTIVE:", session.is_active)
    print("STOP REQUESTED:", session.is_stop_requested)

    print()
    print("Integration test finished.")


if __name__ == "__main__":
    main()