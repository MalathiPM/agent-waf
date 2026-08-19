import re
from waf.models import (
    Context, ToolCall, ParameterRule, RateLimitRule, DataScopeRule, SequenceRule,
)

SCOPE_REF = re.compile(r"^\$\{session\.(\w+)\}$")


def resolve(value: str, ctx: Context):
    """Turn "${session.customer_id}" into the live session value."""
    m = SCOPE_REF.match(str(value))
    return ctx.session_scope.get(m.group(1)) if m else value


def check_parameter(rule: ParameterRule, call: ToolCall, ctx: Context):
    for key, value in call.params.items():
        text = str(value)
        if rule.max_value_length and len(text) > rule.max_value_length:
            return f"param '{key}' exceeds {rule.max_value_length} chars"
        for pattern in rule.deny_patterns:
            if re.search(pattern, text):
                return f"param '{key}' matched denied pattern"
    return None


def check_rate_limit(rule: RateLimitRule, call: ToolCall, ctx: Context):
    used = ctx.call_counts.get(call.tool, 0)
    if used >= rule.max_per_minute:
        return f"{call.tool} called {used} times, limit is {rule.max_per_minute}/min"
    return None


def check_data_scope(rule: DataScopeRule, call: ToolCall, ctx: Context):
    expected = resolve(rule.must_equal, ctx)
    actual = call.params.get(rule.param)
    if actual is None:
        return f"required param '{rule.param}' missing"
    if str(actual) != str(expected):
        return f"'{rule.param}' is outside session scope"
    return None


def check_sequence(rule: SequenceRule, call: ToolCall, ctx: Context):
    if rule.requires_prior not in ctx.called_tools:
        return f"{call.tool} requires {rule.requires_prior} first"
    return None


CHECKS = {
    "parameter": check_parameter,
    "rate_limit": check_rate_limit,
    "data_scope": check_data_scope,
    "sequence": check_sequence,
}
