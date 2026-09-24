"""Concatenate a prompt template and the JSON render into one file.

JSON is always built here. ``--format`` does not have to be json.
"""
from __future__ import annotations

from pathlib import Path

from .render_json import render_json

MARKER = "{{SKYLINE_DATA}}"
_DEFAULT = Path(__file__).parent / "prompts" / "review.md"


def load_template(path: str = "") -> str:
    source = Path(path) if path else _DEFAULT
    return source.read_text(encoding="utf-8")


def render_prompt(diff, base_ref: str, head_ref: str, review, template: str) -> str:
    if MARKER not in template:
        raise ValueError(
            f"prompt template is missing {MARKER}. "
            "The structural model would be omitted."
        )
    payload = render_json(diff, base_ref, head_ref, review).rstrip("\n")
    return template.replace(MARKER, payload) + "\n"
