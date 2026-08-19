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


def test_data_scope_blocks_other_customer():
    v = evaluate(call("get_customer", customer_id="99"),
                 Context(session_scope={"customer_id": "42"}), POLICY)
    assert v.disposition == "BLOCK"
    assert v.matched_rule == "own-customer-only"


def test_rate_limit_blocks_after_quota():
    ctx = Context(session_scope={"customer_id": "42"}, call_counts={"get_customer": 10})
    v = evaluate(call("get_customer", customer_id="42"), ctx, POLICY)
    assert v.disposition == "BLOCK"
    assert v.matched_rule == "crm-read-limit"


def test_sequence_requires_prior_fetch():
    cold = evaluate(call("delete_customer", customer_id="42"),
                    Context(session_scope={"customer_id": "42"}), POLICY)
    assert cold.disposition == "BLOCK"
    assert cold.matched_rule == "fetch-before-delete"

    warm = evaluate(call("delete_customer", customer_id="42"),
                    Context(session_scope={"customer_id": "42"},
                            called_tools=["get_customer"]), POLICY)
    assert warm.disposition == "ALLOW"


def test_shadow_rule_allows_but_records():
    shadow_policy = load_policy("policies/agent-support-shadow.yaml")
    v = evaluate(call("update_customer", customer_id="42", note="DROP TABLE x"),
                 Context(session_scope={"customer_id": "42"}), shadow_policy)
    assert v.disposition == "SHADOW_BLOCK"
    assert v.matched_rule == "no-injection-keywords"
