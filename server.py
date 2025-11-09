
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
from uuid import uuid4
from datetime import datetime
import os, re, json, hashlib

app = FastAPI(title="Agent Runtime Demo", version="0.1.0")

# ----- Models -----
class TaskRequest(BaseModel):
    capability: str = Field(..., description="code_quality | summarize_code")
    inputs: Dict[str, Any]
    context: Optional[Dict[str, Any]] = None
    policy: Optional[str] = "safe-readonly"
    callback_url: Optional[str] = None

class Artifact(BaseModel):
    name: str
    path: str
    sha256: Optional[str] = None

class Fact(BaseModel):
    type: str
    data: Dict[str, Any]

class TaskResult(BaseModel):
    task_id: str
    status: str
    capability: str
    facts: List[Fact] = []
    artifacts: List[Artifact] = []
    sources: List[Dict[str, Any]] = []
    timestamps: Dict[str, str] = {}
    stable_id: str
    message: Optional[str] = None

class TaskStatus(BaseModel):
    task_id: str
    status: str
    result: Optional[TaskResult] = None

CAPABILITIES = [
    {
        "name": "code_quality",
        "description": "Analyze Python code for rough issues (TODOs, long lines, missing docstrings).",
        "inputs_schema": {"code": "str", "filename": "str"},
        "policy": "safe-readonly"
    },
    {
        "name": "summarize_code",
        "description": "Summarize the purpose of a Python file (heuristic).",
        "inputs_schema": {"code": "str", "filename": "str"},
        "policy": "safe-readonly"
    },
]

# ----- Storage -----
TASKS: Dict[str, TaskStatus] = {}
ARTIFACT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "artifacts"))
os.makedirs(ARTIFACT_DIR, exist_ok=True)

def artifact_path(name: str) -> str:
    return os.path.join(ARTIFACT_DIR, name)

def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

# ----- Engine -----
def run_task(task_id: str, req: TaskRequest) -> TaskResult:
    queued = datetime.utcnow().isoformat() + "Z"
    facts: List[Fact] = []
    artifacts: List[Artifact] = []
    sources: List[Dict[str, Any]] = []
    message = ""

    if req.capability == "code_quality":
        code = req.inputs.get("code", "")
        filename = req.inputs.get("filename", "unknown.py")
        issues = []
        lines = code.splitlines()
        for idx, line in enumerate(lines, start=1):
            if "TODO" in line:
                issues.append({"line": idx, "message": "TODO found"})
            if len(line) > 100:
                issues.append({"line": idx, "message": "Line longer than 100 chars"})
        # very rough docstring heuristic
        if not re.search(r'^\s*def\s+\w+\(.*\):\n\s+"""', code, flags=re.M):
            issues.append({"line": 1, "message": "Functions may lack docstrings (heuristic)"})

        # artifact report
        report = {"filename": filename, "issue_count": len(issues), "issues": issues}
        report_json = json.dumps(report, ensure_ascii=False, indent=2)
        name = f"{task_id}_lint_report.json"
        path = artifact_path(name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(report_json)

        facts = [Fact(type="lint_issue", data=i) for i in issues]
        artifacts = [Artifact(name=name, path=path, sha256=_sha256(report_json))]
        sources = [{"type": "in_memory_code", "ref": filename}]
        message = f"{len(issues)} potential issues found."

    elif req.capability == "summarize_code":
        code = req.inputs.get("code", "")
        filename = req.inputs.get("filename", "unknown.py")
        funcs = re.findall(r'^\s*def\s+(\w+)\(', code, flags=re.M)
        facts = [Fact(type="functions", data={"names": funcs})]
        artifacts = []
        sources = [{"type": "in_memory_code", "ref": filename}]
        message = "This file defines: " + (", ".join(funcs) if funcs else "no functions detected")

    else:
        message = "Unknown capability"

    ended = datetime.utcnow().isoformat() + "Z"
    return TaskResult(
        task_id=task_id,
        status="SUCCEEDED",
        capability=req.capability,
        facts=facts,
        artifacts=artifacts,
        sources=sources,
        timestamps={"queued": queued, "ended": ended},
        stable_id=f"run_{task_id}",
        message=message
    )

# ----- API -----
@app.get("/capabilities")
def capabilities():
    return CAPABILITIES

@app.post("/tasks")
def create_task(req: TaskRequest):
    if req.capability not in [c["name"] for c in CAPABILITIES]:
        raise HTTPException(status_code=400, detail="Unknown capability")
    task_id = f"t-{uuid4().hex[:8]}"
    # Mark scheduled
    TASKS[task_id] = TaskStatus(task_id=task_id, status="SCHEDULED")
    # Run immediately (sync) for demo simplicity
    result = run_task(task_id, req)
    TASKS[task_id] = TaskStatus(task_id=task_id, status="SUCCEEDED", result=result)
    return {"task_id": task_id, "status": "SCHEDULED"}

@app.get("/tasks/{task_id}")
def task_status(task_id: str):
    st = TASKS.get(task_id)
    if not st:
        raise HTTPException(status_code=404, detail="Task not found")
    return st
    
@app.get("/")
def root():
    return {"ok": True, "hint": "Try /capabilities or /docs"}
