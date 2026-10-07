"""AI chat session for AI EDITOR.

Keeps conversation state and optional PDF-script context separate from
the After Effects automation layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence

from .pdf_reader import PDFScriptReader


class ChatError(RuntimeError):
    """Raised when the chat session cannot process a request."""


@dataclass
class ChatMessage:
    """One message in the AI conversation."""

    role: str
    content: str


@dataclass
class AIChatSession:
    """Maintain an AI EDITOR conversation."""

    pdf_reader: PDFScriptReader = field(
        default_factory=PDFScriptReader
    )
    messages: list[ChatMessage] = field(
        default_factory=list
    )
    script_text: Optional[str] = None
    script_path: Optional[str] = None

    def add_user_message(
        self,
        content: str,
    ) -> None:
        """Add a user message to the conversation."""

        self._validate_message(content)

        self.messages.append(
            ChatMessage(
                role="user",
                content=content.strip(),
            )
        )

    def add_assistant_message(
        self,
        content: str,
    ) -> None:
        """Add an AI response to the conversation."""

        self._validate_message(content)

        self.messages.append(
            ChatMessage(
                role="assistant",
                content=content.strip(),
            )
        )

    def attach_pdf(
        self,
        pdf_path: str,
    ) -> str:
        """Read and attach an editing-script PDF."""

        text = self.pdf_reader.read(
            pdf_path
        )

        if not text.strip():
            raise ChatError(
                "The PDF contains no extractable text."
            )

        self.script_text = text
        self.script_path = str(
            pdf_path
        )

        return text

    def clear_pdf(self) -> None:
        """Remove the currently attached PDF context."""

        self.script_text = None
        self.script_path = None

    def clear_messages(self) -> None:
        """Clear the conversation history."""

        self.messages.clear()

    def conversation(
        self,
    ) -> list[ChatMessage]:
        """Return a copy of the conversation."""

        return list(
            self.messages
        )

    def build_context(
        self,
        *,
        include_script: bool = True,
    ) -> str:
        """Build the context that can later be sent to an AI provider."""

        sections: list[str] = []

        if include_script and self.script_text:
            sections.append(
                "UPLOADED EDITING SCRIPT:\n"
                + self.script_text
            )

        if self.messages:
            conversation_lines: list[str] = []

            for message in self.messages:
                conversation_lines.append(
                    f"{message.role.upper()}: "
                    f"{message.content}"
                )

            sections.append(
                "CONVERSATION:\n"
                + "\n".join(
                    conversation_lines
                )
            )

        return "\n\n".join(
            sections
        )

    def latest_user_message(
        self,
    ) -> Optional[str]:
        """Return the most recent user message."""

        for message in reversed(
            self.messages
        ):
            if message.role == "user":
                return message.content

        return None

    def _validate_message(
        self,
        content: str,
    ) -> None:
        if not isinstance(
            content,
            str,
        ):
            raise TypeError(
                "Chat message content must be a string."
            )

        if not content.strip():
            raise ValueError(
                "Chat message cannot be empty."
            )