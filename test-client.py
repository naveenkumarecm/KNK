#!/usr/bin/env python3
"""
Interactive multi-turn client for the deployed supervisor agent.
Reads supervisor_agent_arn from config.json.

Usage:
    python test-client.py
    python test-client.py --agent-arn arn:aws:bedrock-agentcore:us-east-1:123456:runtime/supervisor_agent-XXXXX
"""

import boto3
import json
import os
import sys
import uuid
from botocore.config import Config

REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, "config.json")


def get_agent_arn():
    """Get ARN from --agent-arn flag or config.json."""
    for i, arg in enumerate(sys.argv):
        if arg == "--agent-arn" and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            return json.load(f).get("supervisor_agent_arn")
    print("❌ No agent ARN. Pass --agent-arn or run travel-assistant.py first.")
    sys.exit(1)


def invoke(client, agent_arn, prompt, session_id):
    """Invoke agent and stream response. Returns (response_text, session_id)."""
    kwargs = {
        "agentRuntimeArn": agent_arn,
        "qualifier": "DEFAULT",
        "payload": json.dumps({"prompt": prompt}),
    }
    if session_id:
        kwargs["runtimeSessionId"] = session_id

    resp = client.invoke_agent_runtime(**kwargs)
    session_id = resp.get("runtimeSessionId", session_id)
    result = ""

    if "text/event-stream" in resp.get("contentType", ""):
        for line in resp["response"].iter_lines(chunk_size=1):
            if line:
                line = line.decode("utf-8")
                if line.startswith("data:"):
                    data = line[5:].strip()
                else:
                    continue
                try:
                    text = json.loads(data)
                except (json.JSONDecodeError, TypeError):
                    text = data
                if isinstance(text, str):
                    print(text, end="", flush=True)
                    result += text
    else:
        body = json.loads(resp["response"].read())
        text = str(body)
        print(text)
        result = text

    print()
    return result, session_id


def main():
    agent_arn = get_agent_arn()
    client = boto3.client(
        "bedrock-agentcore", region_name=REGION,
        config=Config(read_timeout=300),
    )
    session_id = None

    print("=" * 60)
    print("  AnyCompany AI Travel Assistant — Interactive Client")
    print("=" * 60)
    print(f"  Agent: {agent_arn}")
    print(f"  Type 'quit' or 'exit' to end. 'new' to start a new session.\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit"):
            print("Bye!")
            break
        if user_input.lower() == "new":
            session_id = None
            print("🔄 New session started.\n")
            continue

        print("\nAgent: ", end="", flush=True)
        try:
            _, session_id = invoke(client, agent_arn, user_input, session_id)
        except Exception as e:
            print(f"\n❌ Error: {e}")
        print()


if __name__ == "__main__":
    main()
