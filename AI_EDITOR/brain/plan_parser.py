"""Parser and validator for AI-generated editing plans."""

from __future__ import annotations

import json
from typing import Any, Mapping

from .editing_plan import (
    EditingAction,
    EditingPlan,
    EditingPlanError,
)


class PlanParserError(EditingPlanError):
    """Raised when an AI editing plan cannot be parsed safely."""


class EditingPlanParser:
    """Convert validated JSON data into an EditingPlan."""

    REQUIRED_FIELDS = frozenset({
        "title",
        "duration",
        "actions",
    })

    ALLOWED_ACTIONS = frozenset({
        "create_project",
        "create_composition",
        "import_footage",
        "add_layer",
        "add_text",
        "add_solid",
        "add_null",
        "add_adjustment_layer",
        "set_transform",
        "set_keyframe",
        "add_effect",
        "remove_effect",
        "set_effect_property",
        "enable_effect",
        "delete_layer",
        "duplicate_layer",
        "move_layer",
        "set_parent",
        "rename_layer",
        "set_enabled",
        "cut",
        "wait",
        "save_project",
        "export_video",
    })

    def parse(self, payload: str | Mapping[str, Any]) -> EditingPlan:
        """Parse JSON text or a mapping into a validated plan."""

        data = self._load_payload(payload)

        missing = (
            self.REQUIRED_FIELDS
            - set(data.keys())
        )

        if missing:
            raise PlanParserError(
                "Missing required plan fields: "
                + ", ".join(sorted(missing))
            )

        actions_data = data["actions"]

        if not isinstance(
            actions_data,
            list,
        ):
            raise PlanParserError(
                "'actions' must be a list."
            )

        actions: list[EditingAction] = []

        for index, item in enumerate(
            actions_data
        ):
            if not isinstance(
                item,
                Mapping,
            ):
                raise PlanParserError(
                    f"Action {index} must be an object."
                )

            action_name = item.get(
                "action"
            )

            if action_name not in self.ALLOWED_ACTIONS:
                raise PlanParserError(
                    f"Unsupported action at index "
                    f"{index}: {action_name!r}"
                )

            parameters = item.get(
                "parameters",
                {},
            )

            if not isinstance(
                parameters,
                Mapping,
            ):
                raise PlanParserError(
                    f"Action {index} parameters "
                    "must be an object."
                )

            try:
                actions.append(
                    EditingAction(
                        action=str(
                            action_name
                        ),
                        parameters=dict(
                            parameters
                        ),
                        start_time=item.get(
                            "start_time"
                        ),
                        end_time=item.get(
                            "end_time"
                        ),
                    )
                )
            except (
                EditingPlanError,
                TypeError,
                ValueError,
            ) as exc:
                raise PlanParserError(
                    f"Invalid action at index "
                    f"{index}: {exc}"
                ) from exc

        try:
            return EditingPlan(
                title=str(
                    data["title"]
                ),
                duration=float(
                    data["duration"]
                ),
                frame_rate=float(
                    data.get(
                        "frame_rate",
                        30.0,
                    )
                ),
                width=int(
                    data.get(
                        "width",
                        1080,
                    )
                ),
                height=int(
                    data.get(
                        "height",
                        1920,
                    )
                ),
                actions=tuple(actions),
                source_files=tuple(
                    str(value)
                    for value in data.get(
                        "source_files",
                        [],
                    )
                ),
                notes=str(
                    data.get(
                        "notes",
                        "",
                    )
                ),
            )
        except (
            EditingPlanError,
            TypeError,
            ValueError,
        ) as exc:
            raise PlanParserError(
                f"Invalid editing plan: {exc}"
            ) from exc

    def _load_payload(
        self,
        payload: str | Mapping[str, Any],
    ) -> Mapping[str, Any]:
        if isinstance(
            payload,
            str,
        ):
            cleaned = payload.strip()
            if cleaned.startswith("```"):
                lines = cleaned.split("\n")
                # Remove opening fence line
                lines = lines[1:]
                # Remove closing fence if present
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                cleaned = "\n".join(lines)

            try:
                data = json.loads(
                    cleaned
                )
            except json.JSONDecodeError as exc:
                raise PlanParserError(
                    f"Invalid JSON: {exc}"
                ) from exc
        elif isinstance(
            payload,
            Mapping,
        ):
            data = payload
        else:
            raise TypeError(
                "payload must be JSON text or a mapping."
            )

        if not isinstance(
            data,
            Mapping,
        ):
            raise PlanParserError(
                "The plan root must be a JSON object."
            )

        return data