from waf.models import Context, Policy, ToolCall, Verdict
from waf.rules import CHECKS


def evaluate(call: ToolCall, ctx: Context, policy: Policy) -> Verdict:
    """Pure. No I/O. Everything it needs arrives in ctx."""
    shadowed = None

    for rule in policy.rules:
        if not rule.matches_tool(call.tool):
            continue

        reason = CHECKS[rule.type](rule, call, ctx)
        if reason is None:
            continue

        if rule.shadow:
            shadowed = shadowed or Verdict(
                disposition="SHADOW_BLOCK", matched_rule=rule.name, reason=reason
            )
            continue

        return Verdict(disposition="BLOCK", matched_rule=rule.name, reason=reason)

    return shadowed or Verdict(disposition="ALLOW")
