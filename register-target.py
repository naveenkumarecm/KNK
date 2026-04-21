#!/usr/bin/env python3
"""
Registers MCP gateway targets (search_flights, book_flights)
against the AgentCore Gateway created by deploy-gateway.py.

Reads gateway_id and lambda_arns from config.json.
"""

import boto3
import json
import os
from botocore.exceptions import ClientError

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")

with open(CONFIG_PATH) as f:
    config = json.load(f)

REGION = config["region"]
GATEWAY_ID = config["gateway_id"]
LAMBDA_ARNS = config["lambda_arns"]
PREFIX = "exec"

gateway_client = boto3.client("bedrock-agentcore-control", region_name=REGION)
CREDENTIAL_CONFIG = [{"credentialProviderType": "GATEWAY_IAM_ROLE"}]


def _tool_schema(lambda_arn, name, description, properties, required):
    return {
        "mcp": {
            "lambda": {
                "lambdaArn": lambda_arn,
                "toolSchema": {
                    "inlinePayload": [{
                        "name": name,
                        "description": description,
                        "inputSchema": {
                            "type": "object",
                            "properties": properties,
                            "required": required,
                        },
                    }]
                },
            }
        }
    }


TARGETS = [
    {
        "lambda_key": f"{PREFIX}_search_flights_lambda",
        "target_name": f"{PREFIX}-SearchFlightMCPTarget",
        "description": "Flight search MCP target using Lambda function for travel planning",
        "tool_name": "search_flights",
        "tool_description": "Search for flights based on origin, optional destination, and optional seat class. Returns available flight options with pricing and duration.",
        "properties": {
            "origin": {"type": "string", "description": "Origin airport code or city name (e.g., 'JFK', 'New York')"},
            "destination": {"type": "string", "description": "Optional destination airport code or city name (e.g., 'CDG', 'Paris')"},
            "seat_class": {"type": "string", "description": "Optional seat class preference: economy or business"},
        },
        "required": ["origin"],
    },
    {
        "lambda_key": f"{PREFIX}_book_flight_lambda",
        "target_name": f"{PREFIX}-BookFlightMCPTarget",
        "description": "Flight booking MCP target using Lambda function",
        "tool_name": "book_flights",
        "tool_description": "Book flights for passengers. Returns booking confirmation.",
        "properties": {},
        "required": [],
    },
]


def main():
    print("=" * 60)
    print("  Register MCP Gateway Targets")
    print("=" * 60)
    print(f"  Gateway ID: {GATEWAY_ID}")
    print()

    for t in TARGETS:
        lambda_arn = LAMBDA_ARNS[t["lambda_key"]]
        target_config = _tool_schema(lambda_arn, t["tool_name"], t["tool_description"], t["properties"], t["required"])
        try:
            resp = gateway_client.create_gateway_target(
                gatewayIdentifier=GATEWAY_ID,
                name=t["target_name"],
                description=t["description"],
                targetConfiguration=target_config,
                credentialProviderConfigurations=CREDENTIAL_CONFIG,
            )
            print(f"  ✅ Created target: {t['target_name']} (ID: {resp.get('targetId')})")
        except ClientError as e:
            if "ConflictException" in str(e):
                print(f"  📋 Target already exists: {t['target_name']}")
            else:
                raise

    print("\n" + "=" * 60)
    print("🎉 All targets registered!")
    print("=" * 60)


if __name__ == "__main__":
    main()
