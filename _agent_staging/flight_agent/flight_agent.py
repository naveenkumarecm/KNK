
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
        response = agent(f"{system}\n\nUser: {user_input}")
        content = response.message.get("content", [])
        return content[0].get("text", "No response") if content else "No response"

    if __name__ == "__main__":
        app.run()
