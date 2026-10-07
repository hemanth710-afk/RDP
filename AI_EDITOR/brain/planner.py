"""AI editing-plan generation bridge.

Connects the AMV script/brief to Claude for professional
editing plan generation. The AI is treated as a creative
professional, not a literal command executor.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from interface.ai_chat import AIChatProvider
from interface.chat import AIChatSession

from .editing_plan import EditingPlan
from .plan_parser import EditingPlanParser, PlanParserError

logger = logging.getLogger("ai_editor.planner")


class PlannerError(RuntimeError):
    """Raised when an editing plan cannot be generated."""


AMV_SYSTEM_PROMPT = """\
You are a professional AMV editor inside AI_EDITOR.

You are designing a professional Anime Music Video (AMV) edit.
The user's script is a CREATIVE BRIEF, not an immutable command list.

You have full professional discretion to:
- Reorder, shorten, extend, or replace weak clip choices
- Change pacing, cut timing, and transitions
- Improve beat synchronization and lyric timing
- Improve storytelling, visual continuity, and emotional progression
- Add or remove visual emphasis and effects

However, you MUST preserve:
1. Explicit user requirements and must-have content
2. The supplied song and source clips (do not invent files)
3. The requested target duration
4. Technical validity

PRIORITY ORDER:
1. Explicit user requirements
2. Supplied song and source clips
3. Requested target duration
4. Technical validity
5. Professional editing judgment
6. Creative improvements

THINK LIKE A STRONG PROFESSIONAL EDITOR:
- Consider song structure: intro, verse, pre-chorus, chorus, drop, breakdown, climax, outro
- Match cut density to beat density and emotional intensity
- Maintain character and visual continuity
- Use restraint — professional editing is about timing, contrast, rhythm, and storytelling
- Avoid stacking effects mindlessly
- Prefer strong storytelling over flashy effects
- Use the best supplied clip when multiple options exist

THERE IS NO HARDCODED DURATION LIMIT. The script/brief determines duration.
Examples: 2 seconds, 30 seconds, 5 minutes, 30 minutes, or longer.

SUPPORTED ACTIONS (use ONLY these):
- create_project
- create_composition: {name, width, height, duration, frame_rate, pixel_aspect, background_color}
- import_footage: {footage_path}
- add_layer: {composition_name, layer_name, layer_type, kwargs}
- add_text: {composition_name, layer_name, text}
- add_solid: {composition_name, layer_name, color, width, height, duration}
- add_null: {composition_name, layer_name}
- add_adjustment_layer: {composition_name, layer_name}
- cut: {composition_name, layer_name, timeline_start, timeline_end, source_start}
- set_transform: {composition_name, layer_name, properties}
- set_keyframe: {composition_name, layer_name, property_name, time, value}
- add_effect: {composition_name, layer_name, effect_name, match_name}
- remove_effect: {composition_name, layer_name, effect_name, match_name}
- set_effect_property: {composition_name, layer_name, effect_name, property_name, value, match_name}
- enable_effect: {composition_name, layer_name, effect_name, enabled, match_name}
- delete_layer: {composition_name, layer_name}
- duplicate_layer: {composition_name, layer_name, new_name}
- move_layer: {composition_name, layer_name, target_index}
- set_parent: {composition_name, child_layer_name, parent_layer_name}
- rename_layer: {composition_name, layer_name, new_name}
- set_enabled: {composition_name, layer_name, enabled}
- wait: {seconds}

Do NOT invent actions not in this list.
Do NOT invent source files that were not supplied.
Do NOT emit Python, shell commands, or arbitrary JSX.

When asked to produce a plan, return ONLY valid JSON with this structure:
{
  "title": "...",
  "duration": <number from brief>,
  "frame_rate": <number>,
  "width": <number>,
  "height": <number>,
  "actions": [
    {"action": "<action_name>", "parameters": {...}, "start_time": <number|null>, "end_time": <number|null>}
  ],
  "source_files": ["..."],
  "notes": "..."
}

Do not include markdown fences or explanatory text around the JSON.
"""


class AIEditingPlanner:
    """Generate and validate structured AMV editing plans."""

    def __init__(
        self,
        chat_provider: AIChatProvider,
        parser: EditingPlanParser | None = None,
    ) -> None:
        self.chat_provider = chat_provider
        self.parser = parser or EditingPlanParser()

    def generate(
        self,
        session: AIChatSession,
        *,
        amv_context: str = "",
    ) -> EditingPlan:
        """Ask the AI for a structured AMV editing plan.

        Parameters
        ----------
        session:
            The current chat session containing conversation history.
        amv_context:
            Optional pre-built context string containing the AMV brief,
            clip inventory, and song information. Appended to the
            planning instruction to give Claude full creative context.
        """
        instruction = (
            f"{AMV_SYSTEM_PROMPT}\n\n"
            "Create a structured AMV editing plan for the user's "
            "creative brief. Use your professional judgment to "
            "produce the best possible edit. Return ONLY valid JSON "
            "matching the documented plan structure. Use only "
            "supported action names."
        )

        if amv_context:
            instruction = f"{instruction}\n\n{amv_context}"

        session.add_user_message(instruction)

        logger.info("Requesting AMV editing plan from AI provider.")

        try:
            response = self.chat_provider.send(
                session
            )
        except Exception as exc:
            logger.error("AI provider request failed: %s", exc)
            raise PlannerError(
                f"Unable to obtain an editing plan from AI: {exc}"
            ) from exc

        logger.info(
            "Received AI response (%d characters).",
            len(response),
        )

        try:
            plan = self.parser.parse(response)
        except PlanParserError as exc:
            logger.error("Plan parsing failed: %s", exc)
            raise PlannerError(
                "AI returned a response that could not be "
                f"converted into a valid editing plan: {exc}"
            ) from exc

        logger.info(
            "Parsed editing plan: %s (%d actions, %.1fs duration).",
            plan.title,
            plan.action_count,
            plan.duration,
        )

        return plan

    def build_amv_context(
        self,
        *,
        title: str = "",
        song_path: str = "",
        clip_inventory: str = "",
        target_duration: float | None = None,
        lyrics: str = "",
        mood: str = "",
        editing_style: str = "",
        special_requirements: str = "",
        notes: str = "",
        frame_rate: float = 30.0,
        width: int = 1920,
        height: int = 1080,
    ) -> str:
        """Build a concise AMV context string for the planner."""
        sections = []

        if title:
            sections.append(f"PROJECT TITLE: {title}")

        if song_path:
            sections.append(f"SONG: {song_path}")

        if target_duration is not None:
            sections.append(
                f"TARGET DURATION: {target_duration}s"
            )

        sections.append(
            f"RESOLUTION: {width}x{height} @ {frame_rate} FPS"
        )

        if clip_inventory:
            sections.append(
                f"AVAILABLE CLIPS:\n{clip_inventory}"
            )

        if lyrics:
            sections.append(f"LYRICS/DIALOGUE:\n{lyrics}")

        if mood:
            sections.append(f"MOOD: {mood}")

        if editing_style:
            sections.append(
                f"EDITING STYLE: {editing_style}"
            )

        if special_requirements:
            sections.append(
                f"SPECIAL REQUIREMENTS:\n{special_requirements}"
            )

        if notes:
            sections.append(f"NOTES:\n{notes}")

        return "\n\n".join(sections)