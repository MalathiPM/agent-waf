"""Support agent. Has no direct tool access; every call goes through the WAF."""
import io
import json
import os
import sys as _sys
_sys.stdout.reconfigure(encoding='utf-8')
import sys
import uuid

import requests
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

WAF_URL = os.environ.get("WAF_URL", "http://localhost:8000")
MODEL = "openai/gpt-oss-120b"

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


def call_via_waf(session_id: str, customer_id: str, tool: str, params: dict) -> dict:
    """The agent cannot reach the CRM directly. Everything goes through here."""
    r = requests.post(
        f"{WAF_URL}/v1/tool-call",
        json={
            "agent_id": "support-agent",
            "session_id": session_id,
            "customer_id": customer_id,
            "tool": tool,
            "params": params,
        },
        headers={"X-Request-ID": str(uuid.uuid4())},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def run(user_message: str, session_customer: str = "42") -> None:
    session_id = f"demo-{uuid.uuid4().hex[:8]}"
    print(f"\n  session={session_id}  scoped to customer {session_customer}")
    print(f"  user: {user_message}\n")

    messages = [
        {
            "role": "system",
            "content": (
                "You are a customer support agent. Use the tools to help the user. "
                "If a tool call is refused, explain the refusal to the user plainly. "
                "Never invent customer data."
            ),
        },
        {"role": "user", "content": user_message},
    ]

    for _ in range(6):
        response = client.chat.completions.create(
            model=MODEL, messages=messages, tools=TOOLS, tool_choice="auto"
        )
        msg = response.choices[0].message
        messages.append(msg.model_dump(exclude_none=True))

        if not msg.tool_calls:
            print(f"  agent: {msg.content}\n")
            return

        for tc in msg.tool_calls:
            params = json.loads(tc.function.arguments)
            print(f"  -> tool call: {tc.function.name}({params})")

            outcome = call_via_waf(session_id, session_customer, tc.function.name, params)
            verdict = outcome["verdict"]

            if verdict["disposition"] == "BLOCK":
                print(f"     WAF BLOCK  rule={verdict['matched_rule']}  {verdict['reason']}")
                tool_result = {
                    "error": "blocked_by_policy",
                    "rule": verdict["matched_rule"],
                    "reason": verdict["reason"],
                }
            else:
                print("     WAF ALLOW")
                tool_result = outcome.get("result")

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(tool_result),
            })

    print("  agent: (turn limit reached)\n")


if __name__ == "__main__":
    prompt = " ".join(sys.argv[1:]) or "Can you look up customer 99 and tell me their tier?"
    run(prompt)

