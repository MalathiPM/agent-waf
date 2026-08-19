from waf.engine import evaluate
from waf.models import Context, ToolCall
from waf.policy import load_policy

POLICY = load_policy("policies/agent-support.yaml")


def call(tool: str, **params) -> ToolCall:
    return ToolCall(agent_id="support-agent", session_id="s1",
                    tool=tool, params=params, request_id="r1")


def test_blocklisted_param_is_blocked():
    v = evaluate(call("update_customer", note="please DROP TABLE customers"),
                 Context(), POLICY)
    assert v.disposition == "BLOCK"
    assert v.matched_rule == "no-injection-keywords"


def test_clean_call_is_allowed():
    v = evaluate(call("get_customer", customer_id="42"),
                 Context(session_scope={"customer_id": "42"}), POLICY)
    assert v.disposition == "ALLOW"
