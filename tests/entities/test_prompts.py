"""Unit tests for render_system_instruction (backend/app/entities/prompts.py).

Pure string templating; no external services required. The professional
history fixture text is obviously fake, per CLAUDE.md's guardrail against
using the candidate's real history in tests.
"""

from app.entities.prompts import SYSTEM_INSTRUCTION_TEMPLATE, render_system_instruction


def test_render_system_instruction_interpolates_professional_history() -> None:
    result = render_system_instruction("# Fake history\n- Fake Corp, Fake Role, 2020-2022")

    assert "# Fake history\n- Fake Corp, Fake Role, 2020-2022" in result


def test_render_system_instruction_uses_the_template() -> None:
    result = render_system_instruction("# Fake history")

    assert result == SYSTEM_INSTRUCTION_TEMPLATE.format(professional_history="# Fake history")


def test_render_system_instruction_handles_empty_history() -> None:
    result = render_system_instruction("")

    assert result == SYSTEM_INSTRUCTION_TEMPLATE.format(professional_history="")
