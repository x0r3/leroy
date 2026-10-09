import re
from graphlib import CycleError, TopologicalSorter
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import croniter
from pydantic import BaseModel, ConfigDict, Field, model_validator

IDENTIFIER = r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,99}$"
TERMINAL = frozenset({"succeeded", "failed", "cancelled", "skipped", "interrupted", "timed_out"})


class Parameter(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(pattern=IDENTIFIER)
    label: str = ""
    kind: Literal["string", "text", "boolean", "integer", "choice"] = "string"
    default: Any = None
    required: bool = False
    choices: list[str] = Field(default_factory=list)
    pattern: str | None = None
    description: str = ""

    @model_validator(mode="after")
    def validate_definition(self):
        if self.pattern:
            try:
                re.compile(self.pattern)
            except re.error as exc:
                raise ValueError(f"Invalid pattern for {self.name}") from exc
        if self.default is not None:
            self.validate_value(self.default)
        return self

    def validate_value(self, value):
        if value is None or (value == "" and self.kind != "boolean"):
            if self.required:
                raise ValueError(f"{self.name} is required")
            return value
        if self.kind == "boolean" and not isinstance(value, bool):
            raise ValueError(f"{self.name} must be a boolean")
        if self.kind == "integer" and (type(value) is not int or value < 0):
            raise ValueError(f"{self.name} must be a nonnegative integer")
        if self.kind in ("string", "text", "choice") and not isinstance(value, str):
            raise ValueError(f"{self.name} must be text")
        if self.kind == "choice" and value not in self.choices:
            raise ValueError(f"Invalid choice for {self.name}")
        if self.pattern and not re.fullmatch(self.pattern, str(value)):
            raise ValueError(f"Invalid format for {self.name}")
        if isinstance(value, str) and (len(value) > 32768 or "\x00" in value):
            raise ValueError(f"Invalid size or NUL in {self.name}")
        return value


class Step(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=IDENTIFIER)
    name: str
    action: str = "command"
    command: list[str] = Field(default_factory=list)
    needs: list[str] = Field(default_factory=list)
    timeout: int = Field(default=1800, ge=1, le=86400)
    condition: str | None = None
    always: bool = False
    continue_on_error: bool = False
    artifacts: list[str] = Field(default_factory=list)
    secrets: list[str] = Field(default_factory=list)
    options: dict[str, Any] = Field(default_factory=dict)


class Pipeline(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=IDENTIFIER)
    name: str
    description: str = ""
    group: str = "Custom"
    repository: str = ""
    ref: str = "master"
    profile: str = "default"
    timeout: int = Field(default=3600, ge=1, le=172800)
    concurrency: Literal["serial", "replace", "parallel"] = "serial"
    resource: str | None = None
    parameters: list[Parameter] = Field(default_factory=list)
    credential_parameters: dict[str, list[str]] = Field(default_factory=dict)
    steps: list[Step] = Field(min_length=1, max_length=300)
    schedule: str | None = None
    timezone: str = "Europe/Berlin"
    poll_seconds: int = Field(default=0, ge=0)
    enabled: bool = False
    retention_runs: int = Field(default=50, ge=1)
    source: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_graph(self):
        try:
            ZoneInfo(self.timezone)
        except (ValueError, ZoneInfoNotFoundError) as exc:
            raise ValueError("Unknown pipeline timezone") from exc
        if self.schedule and (
            len(self.schedule.split()) != 5 or not croniter.is_valid(self.schedule, hash_id=self.id)
        ):
            raise ValueError("Schedule must be a valid five-field cron expression")
        if self.poll_seconds and not self.repository:
            raise ValueError("SCM polling requires a repository")
        if self.schedule or self.poll_seconds:
            self.bind({})
        ids = {s.id for s in self.steps}
        if len(ids) != len(self.steps):
            raise ValueError("Step IDs must be unique")
        if len({p.name for p in self.parameters}) != len(self.parameters):
            raise ValueError("Parameter names must be unique")
        for step in self.steps:
            if set(step.needs) - ids:
                raise ValueError(f"Unknown dependencies for {step.id}")
            if step.action == "child":
                if not re.fullmatch(IDENTIFIER, str(step.options.get("pipeline", ""))):
                    raise ValueError(f"Child step {step.id} needs a pipeline ID")
                if not isinstance(step.options.get("parameters", {}), dict):
                    raise ValueError(f"Child step {step.id} parameters must be a mapping")
                sources = step.options.get("parameter_sources", {})
                if not isinstance(sources, dict) or any(
                    not isinstance(value, str)
                    or not re.fullmatch(r"commit|(?:parameters|values)\.[a-zA-Z0-9_.-]+", value)
                    for value in sources.values()
                ):
                    raise ValueError(f"Invalid parameter sources for {step.id}")
        try:
            tuple(TopologicalSorter({s.id: s.needs for s in self.steps}).static_order())
        except CycleError as exc:
            raise ValueError("Pipeline dependencies contain a cycle") from exc
        return self

    def bind(self, supplied):
        definitions = {p.name: p for p in self.parameters}
        if set(supplied) - definitions.keys():
            raise ValueError("Unknown parameters: " + ", ".join(sorted(set(supplied) - definitions.keys())))
        return {p.name: p.validate_value(supplied.get(p.name, p.default)) for p in self.parameters}
