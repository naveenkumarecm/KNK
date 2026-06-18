
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
                if line.startswith('"') and line.endswith('"'): line = line[1:-1]
                result += line.replace("\\n", "\n")
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
                return f"\n\n[Executing: {ed['contentBlockStart']['start']['toolUse']['name']}]\n\n"
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
