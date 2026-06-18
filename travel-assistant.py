#!/usr/bin/env python3
"""
Deploys a flight_agent (with MCP gateway tool) and a supervisor_agent to
Amazon Bedrock AgentCore using the Strands SDK + starter toolkit.

Reads gateway/cognito config from config.json produced by deploy-gateway.py.
Writes agent ARNs to SSM Parameter Store and merges into config.json.

Usage:
    python travel-assistant.py          # deploy both agents
    python travel-assistant.py --test   # deploy + run a quick smoke test
"""

import boto3
import json
import os
import sys
import time
import tempfile
import shutil
from botocore.exceptions import ClientError

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
GW_CONFIG_PATH = os.path.join(SCRIPT_DIR, "config.json")
PREFIX = "exec"

account_id = boto3.client("sts", region_name=REGION).get_caller_identity()["Account"]
iam = boto3.client("iam", region_name=REGION)
ssm = boto3.client("ssm", region_name=REGION)
secretsmanager = boto3.client("secretsmanager", region_name=REGION)

# ---------------------------------------------------------------------------
# Load gateway config
# ---------------------------------------------------------------------------
if not os.path.exists(GW_CONFIG_PATH):
    print(f"❌ {GW_CONFIG_PATH} not found. Run deploy-gateway.py first.")
    sys.exit(1)

with open(GW_CONFIG_PATH) as f:
    gw_config = json.load(f)

GATEWAY_URL = gw_config["gateway_url"]
COGNITO_POOL_ID = gw_config["cognito_user_pool_id"]
COGNITO_SECRET_NAME = gw_config["cognito_secret_name"]
COGNITO_RESOURCE_SERVER_ID = f"{PREFIX}-agentcore-gateway-id"
COGNITO_SCOPE_STRING = gw_config["cognito_scope_string"]

# Fetch Cognito credentials from Secrets Manager
_cognito_secret = json.loads(
    secretsmanager.get_secret_value(SecretId=COGNITO_SECRET_NAME)["SecretString"]
)
COGNITO_CLIENT_ID = _cognito_secret["cognito_client_id"]
COGNITO_CLIENT_SECRET = _cognito_secret["cognito_client_secret"]


# ---------------------------------------------------------------------------
# IAM helpers
# ---------------------------------------------------------------------------
def _agentcore_trust_policy():
    return json.dumps({
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": "bedrock-agentcore.amazonaws.com"},
            "Action": "sts:AssumeRole",
            "Condition": {
                "StringEquals": {"aws:SourceAccount": account_id},
                "ArnLike": {"aws:SourceArn": f"arn:aws:bedrock-agentcore:{REGION}:{account_id}:*"},
            },
        }],
    })


def _agent_role_policy(agent_name):
    return json.dumps({
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
                "Resource": [
                    f"arn:aws:bedrock:*::foundation-model/*",
                    f"arn:aws:bedrock:{REGION}:{account_id}:inference-profile/*",
                    f"arn:aws:bedrock:*:{account_id}:inference-profile/*",
                ],
            },
            {
                "Effect": "Allow",
                "Action": ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"],
                "Resource": [f"arn:aws:ecr:{REGION}:{account_id}:repository/bedrock-agentcore-{PREFIX}_*"],
            },
            {
                "Effect": "Allow",
                "Action": ["ecr:GetAuthorizationToken"],
                "Resource": "*",
            },
            {
                "Effect": "Allow",
                "Action": ["logs:CreateLogGroup", "logs:DescribeLogStreams"],
                "Resource": [f"arn:aws:logs:{REGION}:{account_id}:log-group:/aws/bedrock-agentcore/runtimes/*"],
            },
            {
                "Effect": "Allow",
                "Action": ["logs:DescribeLogGroups"],
                "Resource": [f"arn:aws:logs:{REGION}:{account_id}:log-group:*"],
            },
            {
                "Effect": "Allow",
                "Action": ["logs:CreateLogStream", "logs:PutLogEvents"],
                "Resource": [f"arn:aws:logs:{REGION}:{account_id}:log-group:/aws/bedrock-agentcore/runtimes/*:log-stream:*"],
            },
            {
                "Effect": "Allow",
                "Action": ["xray:PutTraceSegments", "xray:PutTelemetryRecords",
                           "xray:GetSamplingRules", "xray:GetSamplingTargets"],
                "Resource": ["*"],
            },
            {
                "Effect": "Allow",
                "Action": "cloudwatch:PutMetricData",
                "Resource": "*",
                "Condition": {"StringEquals": {"cloudwatch:namespace": "bedrock-agentcore"}},
            },
            {
                "Effect": "Allow",
                "Action": [
                    "bedrock-agentcore:InvokeAgentRuntime",
                    "bedrock-agentcore:GetAgentRuntime",
                    "bedrock-agentcore:ListAgentRuntimes",
                ],
                "Resource": [f"arn:aws:bedrock-agentcore:{REGION}:{account_id}:runtime/{PREFIX}_*"],
            },
            {
                "Effect": "Allow",
                "Action": ["iam:PassRole"],
                "Resource": [f"arn:aws:iam::{account_id}:role/agentcore-{PREFIX}-{agent_name}-role"],
            },
            {
                "Effect": "Allow",
                "Action": ["cognito-idp:InitiateAuth", "cognito-idp:DescribeUserPoolClient"],
                "Resource": [f"arn:aws:cognito-idp:{REGION}:{account_id}:userpool/{COGNITO_POOL_ID}"],
            },
            {
                "Effect": "Allow",
                "Action": ["secretsmanager:GetSecretValue"],
                "Resource": [f"arn:aws:secretsmanager:{REGION}:{account_id}:secret:{COGNITO_SECRET_NAME}-*"],
            },
            {
                "Effect": "Allow",
                "Action": ["bedrock-agentcore:GetWorkloadAccessToken",
                           "bedrock-agentcore:GetWorkloadAccessTokenForJWT",
                           "bedrock-agentcore:GetWorkloadAccessTokenForUserId"],
                "Resource": [
                    f"arn:aws:bedrock-agentcore:{REGION}:{account_id}:workload-identity-directory/default",
                    f"arn:aws:bedrock-agentcore:{REGION}:{account_id}:workload-identity-directory/default/workload-identity/{agent_name}-*",
                ],
            },
        ],
    })


def create_agent_role(agent_name):
    role_name = f"agentcore-{PREFIX}-{agent_name}-role"
    trust = _agentcore_trust_policy()
    policy = _agent_role_policy(agent_name)
    try:
        resp = iam.create_role(RoleName=role_name, AssumeRolePolicyDocument=trust)
        print(f"  ✅ Created role: {role_name}")
        time.sleep(10)
    except ClientError as e:
        if e.response["Error"]["Code"] == "EntityAlreadyExists":
            # Clean up and recreate
            for p in iam.list_role_policies(RoleName=role_name)["PolicyNames"]:
                iam.delete_role_policy(RoleName=role_name, PolicyName=p)
            for p in iam.list_attached_role_policies(RoleName=role_name)["AttachedPolicies"]:
                iam.detach_role_policy(RoleName=role_name, PolicyArn=p["PolicyArn"])
            iam.delete_role(RoleName=role_name)
            resp = iam.create_role(RoleName=role_name, AssumeRolePolicyDocument=trust)
            print(f"  ✅ Recreated role: {role_name}")
            time.sleep(10)
        else:
            raise
    iam.put_role_policy(RoleName=role_name, PolicyName="AgentCorePolicy", PolicyDocument=policy)
    print(f"  ✅ Attached inline AgentCorePolicy to {role_name}")
    return resp["Role"]["Arn"], role_name


# ---------------------------------------------------------------------------
# Agent source scaffolding
# ---------------------------------------------------------------------------
FLIGHT_AGENT_CODE = '''
import os, json, logging, boto3, requests, time
from boto3.session import Session
from strands import Agent
from strands.models import BedrockModel
from strands.tools.mcp.mcp_client import MCPClient
from mcp.client.streamable_http import streamablehttp_client
from bedrock_agentcore.runtime import BedrockAgentCoreApp

logging.basicConfig(format="%(levelname)s | %(name)s | %(message)s", handlers=[logging.StreamHandler()])
logging.getLogger("strands").setLevel(logging.INFO)

app = BedrockAgentCoreApp()

# Load config from agent_env.json if environment variables are not set
_config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent_env.json")
if os.path.exists(_config_path):
    with open(_config_path) as _f:
        _env_config = json.load(_f)
    for _key, _val in _env_config.items():
        os.environ.setdefault(_key, _val)

REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
COGNITO_POOL_ID = os.environ["COGNITO_POOL_ID"]
COGNITO_SECRET_NAME = os.environ["COGNITO_SECRET_NAME"]
COGNITO_RESOURCE_SERVER_ID = os.environ["COGNITO_RESOURCE_SERVER_ID"]
GATEWAY_URL = os.environ["GATEWAY_URL"]

def _get_cognito_credentials():
    """Fetch Cognito client credentials from AWS Secrets Manager."""
    sm = boto3.client("secretsmanager", region_name=REGION)
    secret = json.loads(sm.get_secret_value(SecretId=COGNITO_SECRET_NAME)["SecretString"])
    return secret["cognito_client_id"], secret["cognito_client_secret"]

def get_token():
    client_id, client_secret = _get_cognito_credentials()
    pool_no_underscore = COGNITO_POOL_ID.replace("_", "")
    url = f"https://{pool_no_underscore}.auth.{REGION}.amazoncognito.com/oauth2/token"
    scope = f"{COGNITO_RESOURCE_SERVER_ID}/gateway:read {COGNITO_RESOURCE_SERVER_ID}/gateway:write"
    resp = requests.post(url, headers={"Content-Type": "application/x-www-form-urlencoded"}, data={
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": scope,
    })
    resp.raise_for_status()
    return resp.json()["access_token"]

def create_transport():
    token = get_token()
    return streamablehttp_client(f"{GATEWAY_URL}", headers={"Authorization": f"Bearer {token}"})

client = MCPClient(create_transport)
model = BedrockModel(model_id="us.anthropic.claude-sonnet-4-5-20250929-v1:0")

with client:
    tools = client.list_tools_sync()
    agent = Agent(model=model, tools=tools)
    print(f"Flight agent tools: {agent.tool_names}")

    @app.entrypoint
    def flight_agent_entrypoint(payload):
        user_input = payload.get("prompt", "")
        system = """You are a flight assistant. Use the search_flights tool to find flights and the book_flights tool to book flights.
search_flights requires origin. destination and seat_class (economy/business) are optional filters.
Default to economy class.
When the user asks to book a flight, use the book_flights tool directly without requiring any input parameters. Confirm that one of the flights is booked.
FORMATTING: Never use markdown tables. Always present flight results as a numbered bullet list. For each flight use this format:
- **Flight**: <flight_number> | <airline>
  - Route: <origin> → <destination>
  - Duration: <duration> hours
  - Class: <seat_class> | Price: $<price>"""
        response = agent(f"{system}\\n\\nUser: {user_input}")
        content = response.message.get("content", [])
        return content[0].get("text", "No response") if content else "No response"

    if __name__ == "__main__":
        app.run()
'''

SUPERVISOR_AGENT_CODE = '''
import json, logging, boto3, os
from botocore.config import Config
from strands import Agent, tool
from strands.models import BedrockModel
from bedrock_agentcore.runtime import BedrockAgentCoreApp

logging.basicConfig(format="%(levelname)s | %(name)s | %(message)s", handlers=[logging.StreamHandler()])
logging.getLogger("strands").setLevel(logging.INFO)

app = BedrockAgentCoreApp()

def get_agent_arn(name):
    ssm = boto3.client("ssm")
    return ssm.get_parameter(Name=f"/agents/{name}_arn")["Parameter"]["Value"]

def invoke_sub_agent(agent_arn, query):
    client = boto3.client("bedrock-agentcore", config=Config(read_timeout=300))
    resp = client.invoke_agent_runtime(
        agentRuntimeArn=agent_arn, qualifier="DEFAULT",
        payload=json.dumps({"prompt": query}),
    )
    if "text/event-stream" in resp.get("contentType", ""):
        result = ""
        for line in resp["response"].iter_lines(chunk_size=1):
            if line:
                line = line.decode("utf-8")[6:]
                if line.startswith(\'"\') and line.endswith(\'"\'): line = line[1:-1]
                result += line.replace("\\\\n", "\\n")
        return result
    body = resp["response"].read()
    return json.loads(body)

@tool
def call_flight_agent(user_query):
    """Call the flight agent to search for flights or book flights."""
    try:
        return invoke_sub_agent(get_agent_arn("flight_agent"), user_query)
    except Exception as e:
        return str(e)

model = BedrockModel(model_id="us.anthropic.claude-sonnet-4-5-20250929-v1:0")
agent = Agent(
    model=model,
    system_prompt="""You are a travel planning supervisor. Coordinate with the flight agent to help users plan trips.
- search_flights requires origin. destination and seat_class (economy/business) are optional filters.
- Default to economy class.
- Only provide flight info when asked about flights. Do not fabricate data.
- Always use the call_flight_agent tool for flight queries and booking requests.
- When the user asks to book a flight, use call_flight_agent to process the booking.
- IMPORTANT: Always use "Bengaluru" (not "Bangalore") when referring to the city.
- FORMATTING: Never use markdown tables. Always present flight results as a numbered bullet list. For each flight use this format:
  1. **Flight**: <flight_number> | <airline>
     - Route: <origin> → <destination>
     - Duration: <duration> hours
     - Class: <seat_class> | Price: $<price>""",
    tools=[call_flight_agent],
)

def parse_event(event):
    if any(k in event for k in ["init_event_loop", "start", "start_event_loop"]):
        return ""
    if "data" in event and isinstance(event["data"], str):
        return event["data"]
    if "event" in event:
        ed = event["event"]
        if "contentBlockStart" in ed and "start" in ed["contentBlockStart"]:
            if "toolUse" in ed["contentBlockStart"]["start"]:
                return f"\\n\\n[Executing: {ed['contentBlockStart']['start']['toolUse']['name']}]\\n\\n"
    return ""

@app.entrypoint
async def supervisor_entrypoint(payload):
    user_input = payload.get("prompt")
    try:
        async for event in agent.stream_async(user_input):
            text = parse_event(event)
            if text:
                yield text
    except Exception as e:
        yield json.dumps({"error": str(e)})

if __name__ == "__main__":
    app.run()
'''

AGENT_REQUIREMENTS = "strands-agents\nstrands-agents-tools\nuv\nboto3\nbedrock-agentcore\nbedrock-agentcore-starter-toolkit\n"
FLIGHT_REQUIREMENTS = AGENT_REQUIREMENTS + "requests\n"


def write_agent_dir(base_dir, filename, code, requirements, env_vars=None):
    """Create a temp agent directory with entrypoint + requirements.txt + env config."""
    os.makedirs(base_dir, exist_ok=True)
    with open(os.path.join(base_dir, filename), "w") as f:
        f.write(code)
    with open(os.path.join(base_dir, "requirements.txt"), "w") as f:
        f.write(requirements)
    if env_vars:
        with open(os.path.join(base_dir, "agent_env.json"), "w") as f:
            json.dump(env_vars, f, indent=2)
    return base_dir


# ---------------------------------------------------------------------------
# Deploy an agent via starter toolkit
# ---------------------------------------------------------------------------
def deploy_agent(agent_name, role_arn, entrypoint_file, agent_dir):
    from bedrock_agentcore_starter_toolkit import Runtime
    original_cwd = os.getcwd()
    os.chdir(agent_dir)
    try:
        rt = Runtime()
        rt.configure(
            entrypoint=entrypoint_file,
            execution_role=role_arn,
            auto_create_ecr=True,
            requirements_file="requirements.txt",
            region=REGION,
            agent_name=agent_name,
        )
        result = rt.launch()
        return result.agent_arn, rt
    finally:
        os.chdir(original_cwd)


# ---------------------------------------------------------------------------
# Supervisor permissions to invoke sub-agents + read SSM
# ---------------------------------------------------------------------------
def grant_supervisor_permissions(supervisor_role_name, flight_agent_arn, flight_param_arn):
    policy = json.dumps({
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": ["bedrock-agentcore:InvokeAgentRuntime"],
                "Resource": [flight_agent_arn, f"{flight_agent_arn}/runtime-endpoint/DEFAULT"],
            },
            {
                "Effect": "Allow",
                "Action": ["ssm:GetParameter"],
                "Resource": [flight_param_arn],
            },
        ],
    })
    iam.put_role_policy(
        RoleName=supervisor_role_name,
        PolicyName="SubAgentPermissions",
        PolicyDocument=policy,
    )
    print(f"  ✅ Granted supervisor invoke + SSM permissions")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    test_mode = "--test" in sys.argv

    print("=" * 60)
    print("  AnyCompany AI Travel Assistant Agent Deployment")
    print("=" * 60)
    print(f"  Region:      {REGION}")
    print(f"  Gateway URL: {GATEWAY_URL}")
    print()

    # --- 1. Create IAM roles ---
    print("🔐 Step 1: Creating IAM roles...")
    flight_role_arn, flight_role_name = create_agent_role("flight_agent")
    supervisor_role_arn, supervisor_role_name = create_agent_role("supervisor_agent")

    # --- 2. Scaffold agent directories ---
    print("\n📁 Step 2: Preparing agent source code...")
    staging = os.path.join(SCRIPT_DIR, "_agent_staging")
    flight_env_vars = {
        "COGNITO_POOL_ID": COGNITO_POOL_ID,
        "COGNITO_SECRET_NAME": COGNITO_SECRET_NAME,
        "COGNITO_RESOURCE_SERVER_ID": COGNITO_RESOURCE_SERVER_ID,
        "GATEWAY_URL": GATEWAY_URL,
    }
    flight_dir = write_agent_dir(
        os.path.join(staging, "flight_agent"), "flight_agent.py",
        FLIGHT_AGENT_CODE, FLIGHT_REQUIREMENTS, env_vars=flight_env_vars,
    )
    supervisor_dir = write_agent_dir(
        os.path.join(staging, "supervisor_agent"), "supervisor_agent.py",
        SUPERVISOR_AGENT_CODE, AGENT_REQUIREMENTS,
    )
    print("  ✅ Agent source prepared")

    # --- 3. Deploy flight agent ---
    print("\n🛫 Step 3: Deploying flight_agent to AgentCore...")
    flight_agent_arn, flight_rt = deploy_agent(
        f"{PREFIX}_flight_agent", flight_role_arn, "flight_agent.py", flight_dir,
    )
    print(f"  ✅ flight_agent ARN: {flight_agent_arn}")

    # Store in SSM
    ssm.put_parameter(Name="/agents/flight_agent_arn", Value=flight_agent_arn,
                       Type="String", Overwrite=True)
    flight_param_arn = ssm.get_parameter(Name="/agents/flight_agent_arn")["Parameter"]["ARN"]
    print(f"  ✅ Stored in SSM: /agents/flight_agent_arn")

    # --- 4. Grant supervisor permissions ---
    print("\n🔐 Step 4: Granting supervisor permissions...")
    grant_supervisor_permissions(supervisor_role_name, flight_agent_arn, flight_param_arn)

    # --- 5. Deploy supervisor agent ---
    print("\n🎯 Step 5: Deploying supervisor_agent to AgentCore...")
    supervisor_agent_arn, supervisor_rt = deploy_agent(
        f"{PREFIX}_supervisor_agent", supervisor_role_arn, "supervisor_agent.py", supervisor_dir,
    )
    print(f"  ✅ supervisor_agent ARN: {supervisor_agent_arn}")

    ssm.put_parameter(Name="/agents/supervisor_agent_arn", Value=supervisor_agent_arn,
                       Type="String", Overwrite=True)
    print(f"  ✅ Stored in SSM: /agents/supervisor_agent_arn")

    # --- Save config (merge into existing config.json) ---
    gw_config["flight_agent_arn"] = flight_agent_arn
    gw_config["supervisor_agent_arn"] = supervisor_agent_arn
    gw_config["flight_role_name"] = flight_role_name
    gw_config["supervisor_role_name"] = supervisor_role_name
    with open(GW_CONFIG_PATH, "w") as f:
        json.dump(gw_config, f, indent=2)

    print("\n" + "=" * 60)
    print("🎉 Deployment complete!")
    print(f"  Flight Agent:     {flight_agent_arn}")
    print(f"  Supervisor Agent: {supervisor_agent_arn}")
    print(f"  Config saved to:  {GW_CONFIG_PATH}")
    print("=" * 60)

    # --- Optional smoke test ---
    if test_mode:
        print("\n🧪 Running smoke test...")
        from botocore.config import Config
        client = boto3.client("bedrock-agentcore", region_name=REGION,
                              config=Config(read_timeout=300))
        resp = client.invoke_agent_runtime(
            agentRuntimeArn=supervisor_agent_arn, qualifier="DEFAULT",
            payload=json.dumps({"prompt": "Find flights from New York to Paris on 2026-04-15"}),
        )
        if "text/event-stream" in resp.get("contentType", ""):
            print("Streaming response:\n")
            for line in resp["response"].iter_lines(chunk_size=1):
                if line:
                    line = line.decode("utf-8")[6:]
                    if line.startswith('"') and line.endswith('"'):
                        line = line[1:-1]
                    print(line.replace("\\n", "\n"), end="", flush=True)
            print()
        else:
            print(json.loads(resp["response"].read()))


if __name__ == "__main__":
    main()
