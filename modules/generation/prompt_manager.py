"""Versioned prompt files (Person 3).

Each prompt file starts with `# version: name@vN`, then a SYSTEM: and a USER: section.
Variables use <<name>> so they never clash with the {placeholder} syntax used in emails.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class RenderedPrompt:
    name: str
    version: str
    system: str
    user: str


class PromptManager:
    def __init__(self, prompts_dir: Path):
        self.dir = Path(prompts_dir)

    def _load(self, name: str) -> tuple[str, str, str]:
        raw = (self.dir / f"{name}.txt").read_text(encoding="utf-8")
        lines = raw.splitlines()
        version = f"{name}@v0"
        if lines and lines[0].startswith("# version:"):
            version = lines[0].split(":", 1)[1].strip()
            raw = "\n".join(lines[1:])
        if "USER:" not in raw:
            raise ValueError(f"Prompt {name} has no USER: section")
        system, user = raw.split("USER:", 1)
        return version, system.replace("SYSTEM:", "", 1).strip(), user.strip()

    def version(self, name: str) -> str:
        return self._load(name)[0]

    def render(self, name: str, **variables: object) -> RenderedPrompt:
        version, system, user = self._load(name)
        for key, value in variables.items():
            token = f"<<{key}>>"
            system = system.replace(token, str(value))
            user = user.replace(token, str(value))
        return RenderedPrompt(name=name, version=version, system=system, user=user)

    def list_prompts(self) -> dict[str, str]:
        return {p.stem: self.version(p.stem) for p in sorted(self.dir.glob("*.txt"))}
