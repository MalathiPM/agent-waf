from __future__ import annotations
from datetime import datetime, timezone
from typing import Annotated, Literal, Optional, Union
from pydantic import BaseModel, Field


class ToolCall(BaseModel):
    agent_id: str
    session_id: str
    tool: str
    params: dict = Field(default_factory=dict)
    request_id: str


class Verdict(BaseModel):
    disposition: Literal["ALLOW", "BLOCK", "SHADOW_BLOCK"]
    matched_rule: Optional[str] = None
    reason: Optional[str] = None


class Context(BaseModel):
    session_scope: dict = Field(default_factory=dict)
    call_counts: dict = Field(default_factory=dict)
    called_tools: list = Field(default_factory=list)
    now: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class BaseRule(BaseModel):
    name: str
    applies_to: list = Field(default_factory=lambda: ["*"])
    shadow: bool = False

    def matches_tool(self, tool: str) -> bool:
        return "*" in self.applies_to or tool in self.applies_to


class ParameterRule(BaseRule):
    type: Literal["parameter"]
    deny_patterns: list = Field(default_factory=list)
    max_value_length: Optional[int] = None


class RateLimitRule(BaseRule):
    type: Literal["rate_limit"]
    max_per_minute: int


class DataScopeRule(BaseRule):
    type: Literal["data_scope"]
    param: str
    must_equal: str


class SequenceRule(BaseRule):
    type: Literal["sequence"]
    requires_prior: str


Rule = Annotated[
    Union[ParameterRule, RateLimitRule, DataScopeRule, SequenceRule],
    Field(discriminator="type"),
]


class Policy(BaseModel):
    agent_id: str
    scope: dict = Field(default_factory=dict)
    rules: list[Rule] = Field(default_factory=list)
