"""Support agent. Has no direct tool access; every call goes through the WAF.

The agent defines tool schemas for the model to call, but holds no tool
implementations. Every tool call the model emits is forwarded to the Agent WAF
over HTTP, which evaluates it against policy before it reaches the CRM.

Usage:
    python agent/waf_agent.py "What tier is customer 42 on?"
    python agent/waf_agent.py 99 "What tier is customer 99 on?"
    python agent/waf_agent.py 42,99,17 "What tier is customer 99 on?"

An optional leading argument sets the customers the session is authorised for
(default 42). A single ID exercises the `data_scope` rule (must_equal); a
comma-separated list exercises `data_scope_list` (must_be_in), which needs a WAF
running the account-manager policy:

    docker compose run --rm -e POLICY_FILE=policies/agent-account-manager.yaml -p 8002:8000 waf
    $env:AGENT_ID="account-manager"; $env:WAF_URL="http://localhost:8002"
"""
import json
import os
import sys
import uuid

import requests
from dotenv import load_dotenv
from groq import Groq

sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()

WAF_URL = os.environ.get("WAF_URL", "http://localhost:8000")
AGENT_ID = os.environ.get("AGENT_ID", "support-agent")
MODEL = "openai/gpt-oss-120b"
MAX_TURNS = 6

client = Groq(api_key=os.environ["GROQ_API_KEY"])

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_customer",
            "description": "Look up a customer record by ID.",
            "parameters": {
                "type": "object",
                "properties": {"customer_id": {"type": "string"}},
                "required": ["customer_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_customer",
            "description": "Update a field on a customer record.",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_id": {"type": "string"},
                    "note": {"type": "string"},
                },
                "required": ["customer_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_customer",
            "description": "Delete a customer record.",
            "parameters": {
                "type": "object",
                "properties": {"customer_id": {"type": "string"}},
                "required": ["customer_id"],
            },
        },
    },
]

SYSTEM_PROMPT = (
    "You are a customer support agent. Use the tools to help the user. "
    "If a tool call is refused, explain the refusal to the user plainly. "
    "Never invent customer data."
)


def call_via_waf(session_id: str, authorised: list, tool: str, params: dict) -> dict:
    """The agent cannot reach the CRM directly. Everything goes through here."""
    response = requests.post(
        f"{WAF_URL}/v1/tool-call",
        json={
            "agent_id": AGENT_ID,
            "session_id": session_id,
            "customer_id": authorised[0],
            "authorised_customers": authorised,
            "tool": tool,
            "params": params,
        },
        headers={"X-Request-ID": str(uuid.uuid4())},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def run(user_message: str, authorised: list) -> None:
    session_id = f"sess-{uuid.uuid4().hex[:8]}"
    print(f"\n  session={session_id}  authorised for {', '.join(authorised)}")
    print(f"  user: {user_message}\n")

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    for _ in range(MAX_TURNS):
        response = client.chat.completions.create(
            model=MODEL, messages=messages, tools=TOOLS, tool_choice="auto"
        )
        message = response.choices[0].message
        messages.append(message.model_dump(exclude_none=True))

        if not message.tool_calls:
            print(f"  agent: {message.content}\n")
            return

        for tool_call in message.tool_calls:
            params = json.loads(tool_call.function.arguments)
            print(f"  -> tool call: {tool_call.function.name}({params})")

            outcome = call_via_waf(
                session_id, authorised, tool_call.function.name, params
            )
            verdict = outcome["verdict"]

            if verdict["disposition"] == "BLOCK":
                print(
                    f"     WAF BLOCK  rule={verdict['matched_rule']}  "
                    f"{verdict['reason']}"
                )
                # The refusal reason is returned to the model as the tool result,
                # so the agent can react to policy rather than simply failing.
                tool_result = {
                    "error": "blocked_by_policy",
                    "rule": verdict["matched_rule"],
                    "reason": verdict["reason"],
                }
            else:
                print(f"     WAF {verdict['disposition']}")
                tool_result = outcome.get("result")

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(tool_result),
                }
            )

    print(f"  agent: (turn limit of {MAX_TURNS} reached)\n")


def is_scope_arg(value: str) -> bool:
    """A leading '42' or '42,99,17' is a scope, not part of the prompt."""
    parts = [part.strip() for part in value.split(",")]
    return bool(parts) and all(part.isdigit() for part in parts)


def parse_args(argv: list) -> tuple:
    if len(argv) > 1 and is_scope_arg(argv[0]):
        authorised = [part.strip() for part in argv[0].split(",")]
        return " ".join(argv[1:]), authorised
    prompt = " ".join(argv) or "What tier is customer 42 on?"
    return prompt, ["42"]


if __name__ == "__main__":
    prompt, authorised = parse_args(sys.argv[1:])
    run(prompt, authorised)