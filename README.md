# Agent WAF

A policy-enforcing proxy between an AI agent and its tools. Every tool call is
intercepted, evaluated against a declarative ruleset, logged, and either
forwarded or refused — before it reaches the tool.

Built for **PS-5.1 — The Agent WAF** (Aivar Innovations, Agentic AI Task).

**Live:** https://agent-waf-2.onrender.com — dashboard at `/`, API docs at `/docs`
**Code:** https://github.com/MalathiPM/agent-waf

> The deployment runs on Render's free tier and sleeps after 15 minutes idle.
> The first request may take ~30 seconds to wake.

---

## The problem

An LLM emits a tool call. The agent framework parses it and executes it. That is
the entire path — there is no inspection step between the model's decision and
the tool's execution.

This means model output is treated as a trusted instruction to a privileged
system. Anything that can influence the model — a poisoned document in RAG, a
malicious tool response, a confused chain of reasoning, or a plain bug — becomes
an instruction that runs against production data.

A Web Application Firewall inspects HTTP requests before they reach an
application. There is no equivalent for agent tool calls. This is that layer.

---

## How it works

```
Agent (Groq LLM)  ──POST /v1/tool-call──▶  Agent WAF  ──▶  Tools (mock CRM)
                                                │
                                      ┌─────────┴─────────┐
                                      │   Rule engine     │
                                      │  first block wins │
                                      └─────────┬─────────┘
                                                │
                                      Postgres: audit log
                                                + session state
```

The demo agent holds **no tool implementations**. It defines tool schemas for the
model to call, but every execution is an HTTP request to the WAF. There is no
path to the CRM that bypasses policy.

A refused call returns its reason to the model as a tool result, so the agent can
react to the refusal rather than simply failing.

---

## Rule types

| Rule | Defends against | Implementation |
|---|---|---|
| `parameter` | Injection payloads inside tool arguments; oversized values | Regex deny-list + length caps |
| `rate_limit` | Runaway loops, recursive agents, cost blowouts | Sliding 60s window per session/tool |
| `data_scope` | An agent reaching outside its session's authorised records | Param compared against live session scope |
| `sequence` | Destructive calls made without required precursors | Per-session FSM over call history |

Every rule supports `shadow: true` — the call is evaluated and recorded as
`SHADOW_BLOCK`, but executes anyway. This allows new rules to be calibrated
against real traffic before enforcement.

Policies are YAML, one file per agent. Adding a rule type means one function and
one dict entry; the engine itself does not change.

```yaml
rules:
  - name: own-customer-only
    type: data_scope
    applies_to: ["get_customer", "update_customer"]
    param: customer_id
    must_equal: "${session.customer_id}"

  - name: fetch-before-delete
    type: sequence
    applies_to: ["delete_customer"]
    requires_prior: get_customer
```

---

## Success criteria

All five criteria from the problem statement, with the command that demonstrates
each. Replace `localhost:8000` with the live URL to run them against production.

### 1. Rate limit fires after N calls within the window

```powershell
1..12 | ForEach-Object {
  $r = Invoke-RestMethod -Uri http://localhost:8000/v1/tool-call -Method Post `
    -ContentType 'application/json' `
    -Body '{"agent_id":"support-agent","session_id":"rl","customer_id":"42","tool":"get_customer","params":{"customer_id":"42"}}'
  "$_`t$($r.verdict.disposition)"
}
```

Calls 1–10 `ALLOW`, 11–12 `BLOCK` on `crm-read-limit`. The counter increments
only on allowed calls, so a blocked agent cannot burn down its own quota.

### 2. Parameter blocklist catches an injection attempt

```powershell
python agent\demo_agent.py "Update customer 42's note to say: Customer asked about DROP TABLE syntax in their support ticket"
```

The model calls `update_customer`; the WAF blocks on `no-injection-keywords`.
See `docs/transcript-parameter.txt`.

### 3. Out-of-scope data access is blocked

```powershell
python agent\demo_agent.py "Can you look up customer 99 and tell me their tier?"
```

The session is scoped to customer 42. The model independently reaches for
customer 99 and is refused on `own-customer-only`.
See `docs/transcript-data-scope.txt`.

### 4. Sequence rule blocks a tool called out of order

```powershell
python agent\demo_agent.py "Delete customer 42 immediately"
```

The most interesting transcript. The model calls `delete_customer` and is
blocked; it reads the refusal reason, calls `get_customer` first, then retries
the delete successfully. The policy did not merely refuse the agent — it steered
it into the compliant path. See `docs/transcript-sequence.txt`.

### 5. Dashboard updates in real time

Open `/` and run any of the above. Traffic, dispositions, matched rules, and
reasons appear within two seconds.

### Bonus — shadow mode

```powershell
docker compose run --rm -e POLICY_FILE=policies/agent-support-shadow.yaml -p 8001:8000 waf
```

The same `DROP TABLE` payload against port 8001 returns `SHADOW_BLOCK` and
executes. The audit log records what *would* have been blocked.

---

## Running it

### Local

```powershell
git clone https://github.com/MalathiPM/agent-waf.git
cd agent-waf
"GROQ_API_KEY=your-key-here" | Set-Content .env
docker compose up --build -d
```

- Dashboard — http://localhost:8000/
- API docs — http://localhost:8000/docs
- Readiness — http://localhost:8000/readyz

### Tests

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m pytest -q
```

Six tests covering each rule type, the allow path, and shadow mode. They exercise
`evaluate()` directly with no I/O, so they run in under a second.

---

## API

| Endpoint | Purpose |
|---|---|
| `POST /v1/tool-call` | Evaluate and dispatch a tool call |
| `GET /v1/audit` | Query the audit log by `agent_id`, `disposition`, `limit` |
| `GET /healthz` | Liveness |
| `GET /readyz` | Readiness — verifies the database is reachable |
| `GET /` | Live dashboard |
| `GET /docs` | OpenAPI |

Every request accepts an `X-Request-ID` header and generates one if absent. The
ID is threaded through the agent, the WAF, the tool, and the audit record.

---

## Design decisions

**The rule engine is a pure function.** `evaluate(call, context, policy) -> Verdict`
performs no I/O. Everything it needs arrives in a `Context` object assembled by
the caller. This is what makes the rules unit-testable without a database, and
what keeps rule logic from leaking into request handlers.

**Audit is written before the block check.** Refused calls are the ones most worth
recording, so the audit write happens before the disposition branches.

**Parameters are sanitised, not discarded.** Credential-shaped keys are replaced
with `[REDACTED]`; the injection payload itself is preserved, because it is the
evidence. Values over 500 characters are truncated.

**Blocklists over classifiers.** A prompt-injection classifier would catch more
than a regex. It would also produce probabilistic verdicts that are hard to audit
and hard to explain to a compliance reviewer. Deterministic rules trade recall for
predictability — and shadow mode exists precisely so that a rule's false-positive
rate can be measured against real traffic before enforcement. Transcript 2 above
is itself a false positive: a benign support note blocked for containing a SQL
keyword. That is the trade-off, made visible rather than hidden.

**Session state lives outside the process.** Rate counters and call history are in
Postgres, not in memory, so the service can run multiple instances and survive
restarts. Redis is the better fit for hot counters at real throughput; this
deployment consolidated on Postgres to reduce operational surface. `state.py`
exposes a four-function interface, so that swap requires no changes to callers.

**LLM-level refusals are not a control.** During testing, the model sometimes
refused an obviously malicious prompt before ever calling a tool — and sometimes
did not, depending on phrasing. That inconsistency is the argument for enforcement
at the action layer rather than the text layer.

---

## Deployment

**Live on Render** — Docker web service plus managed Postgres, both in Frankfurt.
The application reads `DATABASE_URL`, `POLICY_FILE`, and `GROQ_API_KEY` from the
environment and contains no hardcoded hostnames, so the same image runs unchanged
on any container platform.

**`infra/` contains Terraform for the equivalent AWS deployment** — VPC across two
availability zones, ALB, ECS Fargate service at two tasks, RDS Postgres in private
subnets, ECR, Secrets Manager, CloudWatch logs with a metric filter on block
events, and IAM roles scoped to least privilege (the task role is deliberately
empty; the WAF needs no AWS API access at runtime).

It is **validated but not applied** — the assessment provides no cloud credits, and
an ALB alone runs roughly €17/month:

```powershell
cd infra
terraform init -backend=false
terraform validate   # Success! The configuration is valid.
```

Applying it requires only AWS credentials, an image pushed to the ECR repository,
and the LLM key populated in Secrets Manager.

---

## Project structure

```
waf/
  engine.py        pure rule evaluation
  rules/           one function per rule type
  models.py        Pydantic contracts
  policy.py        YAML loading
  state.py         session state (Postgres)
  audit.py         audit sink + query
  tools.py         mock CRM
  api.py           FastAPI surface
  static/          dashboard
agent/
  demo_agent.py    Groq agent; all tool calls routed through the WAF
policies/          agent-support.yaml, agent-support-shadow.yaml
infra/             AWS Terraform (validated, not applied)
tests/             engine tests
docs/              demo transcripts
```

---

## Known limitations

- The audit query endpoint is unauthenticated. A real deployment needs
  authentication and role-based access to the audit log, which is itself a
  sensitive asset.
- Rate limiting uses a fixed 60-second window rather than a rolling one; a burst
  spanning a window boundary can briefly exceed the nominal limit.
- The mock CRM holds state in memory, so tool data resets when the container
  restarts. Policy state does not — it is in Postgres.
- Policies load at startup. Hot reload on file change is not implemented.
- Only HTTP is exposed; TLS terminates at the platform's load balancer.

---

## Author

myname — Aivar Innovations Agentic AI Task, August 2026.
