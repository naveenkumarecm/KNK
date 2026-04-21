#!/usr/bin/env python3
"""
FastAPI backend that proxies requests to the supervisor agent with SSE streaming.
Reads supervisor_agent_arn from config.json.

Usage:
    pip install fastapi uvicorn
    python backend.py
"""

import boto3
import json
import os
from botocore.config import Config
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles

REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(os.path.dirname(SCRIPT_DIR), "config.json")

with open(CONFIG_PATH) as f:
    config = json.load(f)

AGENT_ARN = config["supervisor_agent_arn"]
client = boto3.client("bedrock-agentcore", region_name=REGION, config=Config(read_timeout=300))

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.post("/api/chat")
async def chat(request: Request):
    body = await request.json()
    prompt = body.get("prompt", "")
    session_id = body.get("session_id")

    kwargs = {
        "agentRuntimeArn": AGENT_ARN,
        "qualifier": "DEFAULT",
        "payload": json.dumps({"prompt": prompt}),
    }
    if session_id:
        kwargs["runtimeSessionId"] = session_id

    resp = client.invoke_agent_runtime(**kwargs)
    resp_session_id = resp.get("runtimeSessionId", session_id or "")

    def stream():
        # Send session ID as first event
        yield f"data: {json.dumps({'type': 'session', 'session_id': resp_session_id})}\n\n"

        if "text/event-stream" in resp.get("contentType", ""):
            for line in resp["response"].iter_lines(chunk_size=1):
                if line:
                    decoded = line.decode("utf-8")
                    if decoded.startswith("data:"):
                        data = decoded[5:].strip()
                        try:
                            text = json.loads(data)
                        except (json.JSONDecodeError, TypeError):
                            text = data
                        if isinstance(text, str):
                            yield f"data: {json.dumps({'type': 'text', 'content': text})}\n\n"
        else:
            body = resp["response"].read().decode("utf-8")
            yield f"data: {json.dumps({'type': 'text', 'content': body})}\n\n"

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


# Serve React build
build_dir = os.path.join(SCRIPT_DIR, "build")
if os.path.exists(build_dir):
    app.mount("/static", StaticFiles(directory=os.path.join(build_dir, "static")), name="static")

    @app.get("/{path:path}")
    async def serve_react(path: str):
        file_path = os.path.join(build_dir, path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(build_dir, "index.html"))


if __name__ == "__main__":
    import uvicorn
    print(f"Agent ARN: {AGENT_ARN}")
    print(f"Starting server at http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
