import logging, os, uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, Header
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from waf import audit, state
from waf.engine import evaluate
from waf.models import Context, ToolCall, Verdict
from waf.policy import load_policy
from waf.tools import REGISTRY, ToolError

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("waf")

POLICY = load_policy(os.environ.get("POLICY_FILE", "policies/agent-support.yaml"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    audit.init_db()
    state.init_state()
    yield


app = FastAPI(title="Agent WAF", version="0.2.0", lifespan=lifespan)


class ToolCallRequest(BaseModel):
    agent_id: str
    session_id: str
    customer_id: str
    tool: str
    params: dict = {}


class ToolCallResponse(BaseModel):
    request_id: str
    verdict: Verdict
    result: dict | None = None


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/readyz")
def readyz():
    db_ok = audit.ping()
    return {"status": "ready" if db_ok else "degraded", "database": db_ok}


@app.get("/v1/audit")
def get_audit(agent_id: str | None = None, disposition: str | None = None, limit: int = 50):
    return {"records": audit.query(agent_id=agent_id, disposition=disposition, limit=limit)}


@app.post("/v1/tool-call", response_model=ToolCallResponse)
def tool_call(req: ToolCallRequest, x_request_id: str | None = Header(default=None)):
    request_id = x_request_id or str(uuid.uuid4())

    call = ToolCall(agent_id=req.agent_id, session_id=req.session_id,
                    tool=req.tool, params=req.params, request_id=request_id)

    ctx = Context(
        session_scope={"customer_id": req.customer_id},
        call_counts=state.counts_last_minute(req.session_id),
        called_tools=state.tools_called(req.session_id),
    )

    verdict = evaluate(call, ctx, POLICY)

    log.info("%s agent=%s tool=%s -> %s (%s)",
             request_id, req.agent_id, req.tool, verdict.disposition, verdict.matched_rule)

    audit.record(request_id=request_id, agent_id=req.agent_id, session_id=req.session_id,
                 tool=req.tool, params=req.params, verdict=verdict)

    if verdict.disposition == "BLOCK":
        return ToolCallResponse(request_id=request_id, verdict=verdict)

    state.record_call(req.session_id, req.tool)

    fn = REGISTRY.get(req.tool)
    if fn is None:
        return ToolCallResponse(request_id=request_id, verdict=verdict,
                                result={"error": f"unknown tool {req.tool}"})
    try:
        return ToolCallResponse(request_id=request_id, verdict=verdict,
                                result=fn(**req.params))
    except ToolError as e:
        return ToolCallResponse(request_id=request_id, verdict=verdict,
                                result={"error": str(e)})






@app.get("/", response_class=HTMLResponse)
def dashboard():
    return FileResponse("waf/static/dashboard.html")

