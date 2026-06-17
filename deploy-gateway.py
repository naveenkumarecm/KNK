#!/usr/bin/env python3
"""
Deploys the AgentCore MCP Gateway infrastructure:
  1. Deploy Lambda functions (search_flights, book_flights)
  2. Create IAM role for the gateway
  3. Set up Cognito auth (user pool, resource server, M2M client)
  4. Create the AgentCore Gateway with Cognito JWT authorizer

Outputs config.json with all IDs/ARNs for downstream use (e.g., register-target.py).
"""

import boto3
import json
import os
import time
from botocore.exceptions import ClientError

REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
LAMBDA_ZIP_DIR = os.path.join(os.path.dirname(__file__), "lambdas")
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")

# Secrets Manager
COGNITO_SECRET_NAME = "travel-assistant/cognito-credentials"

# Naming
PREFIX = "exec"
GATEWAY_NAME = f"{PREFIX}-TravellerAppGwforLambda"
GATEWAY_ROLE_NAME = f"agentcore-{PREFIX}-lambdagateway-role"
LAMBDA_ROLE_NAME = f"{PREFIX}_gateway_lambda_iamrole"
COGNITO_POOL_NAME = f"{PREFIX}-agentcore-gateway-pool"
COGNITO_RESOURCE_SERVER_ID = f"{PREFIX}-agentcore-gateway-id"
COGNITO_RESOURCE_SERVER_NAME = f"{PREFIX}-agentcore-gateway-name"
COGNITO_CLIENT_NAME = f"{PREFIX}-agentcore-gateway-client"
COGNITO_SCOPES = [
    {"ScopeName": "gateway:read", "ScopeDescription": "Read access"},
    {"ScopeName": "gateway:write", "ScopeDescription": "Write access"},
]

# Lambda definitions: (zip_file, function_name, handler)
LAMBDAS = [
    ("search_flights_deploy.zip", f"{PREFIX}_search_flights_lambda", "search_flights.lambda_handler"),
    ("book_flights_lambda.zip", f"{PREFIX}_book_flight_lambda", "book_flights_lambda.lambda_handler"),
]

iam = boto3.client("iam", region_name=REGION)
lam = boto3.client("lambda", region_name=REGION)
cognito = boto3.client("cognito-idp", region_name=REGION)
gateway_client = boto3.client("bedrock-agentcore-control", region_name=REGION)
secretsmanager = boto3.client("secretsmanager", region_name=REGION)
account_id = boto3.client("sts", region_name=REGION).get_caller_identity()["Account"]


# ---------------------------------------------------------------------------
# 1. Deploy Lambda functions
# ---------------------------------------------------------------------------

def ensure_lambda_role():
    """Create the shared IAM role for all Lambda functions."""
    trust = json.dumps({
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": "lambda.amazonaws.com"},
            "Action": "sts:AssumeRole",
        }],
    })
    try:
        resp = iam.create_role(
            RoleName=LAMBDA_ROLE_NAME,
            AssumeRolePolicyDocument=trust,
            Description="IAM role for gateway Lambda functions",
        )
        arn = resp["Role"]["Arn"]
        iam.attach_role_policy(
            RoleName=LAMBDA_ROLE_NAME,
            PolicyArn="arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole",
        )
        print(f"  ✅ Created Lambda role: {LAMBDA_ROLE_NAME}")
        print("  ⏳ Waiting for role propagation...")
        time.sleep(10)
    except ClientError as e:
        if e.response["Error"]["Code"] == "EntityAlreadyExists":
            arn = iam.get_role(RoleName=LAMBDA_ROLE_NAME)["Role"]["Arn"]
            print(f"  📋 Lambda role already exists: {LAMBDA_ROLE_NAME}")
        else:
            raise
    return arn


def deploy_lambda(zip_file, func_name, handler, role_arn):
    """Deploy a single Lambda function from a zip file."""
    zip_path = os.path.join(LAMBDA_ZIP_DIR, zip_file)
    with open(zip_path, "rb") as f:
        code = f.read()
    try:
        resp = lam.create_function(
            FunctionName=func_name,
            Role=role_arn,
            Runtime="python3.12",
            Handler=handler,
            Code={"ZipFile": code},
            Description=f"AgentCore Gateway Lambda: {func_name}",
            PackageType="Zip",
            Timeout=30,
        )
        arn = resp["FunctionArn"]
        print(f"  ✅ Created Lambda: {func_name}")
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceConflictException":
            arn = lam.get_function(FunctionName=func_name)["Configuration"]["FunctionArn"]
            print(f"  📋 Lambda already exists: {func_name}")
        else:
            raise
    return arn


def deploy_all_lambdas():
    print("\n🛫 Step 1: Deploying Lambda functions...")
    role_arn = ensure_lambda_role()
    arns = {}
    for zip_file, func_name, handler in LAMBDAS:
        arns[func_name] = deploy_lambda(zip_file, func_name, handler, role_arn)
    return arns


# ---------------------------------------------------------------------------
# 2. Create IAM role for the gateway
# ---------------------------------------------------------------------------

def create_gateway_role():
    print("\n🔐 Step 2: Creating gateway IAM role...")
    trust = json.dumps({
        "Version": "2012-10-17",
        "Statement": [{
            "Sid": "AssumeRolePolicy",
            "Effect": "Allow",
            "Principal": {"Service": "bedrock-agentcore.amazonaws.com"},
            "Action": "sts:AssumeRole",
            "Condition": {
                "StringEquals": {"aws:SourceAccount": account_id},
                "ArnLike": {"aws:SourceArn": f"arn:aws:bedrock-agentcore:{REGION}:{account_id}:*"},
            },
        }],
    })
    policy = json.dumps({
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "bedrock-agentcore:InvokeGateway",
                    "bedrock-agentcore:GetGateway",
                    "bedrock-agentcore:ListGatewayTargets",
                ],
                "Resource": [f"arn:aws:bedrock-agentcore:{REGION}:{account_id}:gateway/*"],
            },
            {
                "Effect": "Allow",
                "Action": ["lambda:InvokeFunction"],
                "Resource": [f"arn:aws:lambda:{REGION}:{account_id}:function:{PREFIX}_*"],
            },
            {
                "Effect": "Allow",
                "Action": ["secretsmanager:GetSecretValue"],
                "Resource": [f"arn:aws:secretsmanager:{REGION}:{account_id}:secret:{COGNITO_SECRET_NAME}-*"],
            },
            {
                "Effect": "Allow",
                "Action": ["iam:PassRole"],
                "Resource": [f"arn:aws:iam::{account_id}:role/agentcore-{PREFIX}-*"],
            },
        ],
    })
    try:
        resp = iam.create_role(RoleName=GATEWAY_ROLE_NAME, AssumeRolePolicyDocument=trust)
        print(f"  ✅ Created gateway role: {GATEWAY_ROLE_NAME}")
        time.sleep(10)
    except ClientError as e:
        if e.response["Error"]["Code"] == "EntityAlreadyExists":
            for p in iam.list_role_policies(RoleName=GATEWAY_ROLE_NAME)["PolicyNames"]:
                iam.delete_role_policy(RoleName=GATEWAY_ROLE_NAME, PolicyName=p)
            iam.delete_role(RoleName=GATEWAY_ROLE_NAME)
            resp = iam.create_role(RoleName=GATEWAY_ROLE_NAME, AssumeRolePolicyDocument=trust)
            print(f"  ✅ Recreated gateway role: {GATEWAY_ROLE_NAME}")
            time.sleep(10)
        else:
            raise
    iam.put_role_policy(RoleName=GATEWAY_ROLE_NAME, PolicyName="AgentCorePolicy", PolicyDocument=policy)
    return resp["Role"]["Arn"]


# ---------------------------------------------------------------------------
# 3. Set up Cognito auth
# ---------------------------------------------------------------------------

def get_or_create_user_pool():
    for pool in cognito.list_user_pools(MaxResults=60)["UserPools"]:
        if pool["Name"] == COGNITO_POOL_NAME:
            print(f"  📋 User pool already exists: {pool['Id']}")
            return pool["Id"]
    resp = cognito.create_user_pool(PoolName=COGNITO_POOL_NAME)
    pool_id = resp["UserPool"]["Id"]
    domain = pool_id.replace("_", "").lower()
    cognito.create_user_pool_domain(Domain=domain, UserPoolId=pool_id)
    print(f"  ✅ Created user pool: {pool_id}")
    return pool_id


def ensure_resource_server(pool_id):
    try:
        cognito.describe_resource_server(UserPoolId=pool_id, Identifier=COGNITO_RESOURCE_SERVER_ID)
        print(f"  📋 Resource server already exists")
    except cognito.exceptions.ResourceNotFoundException:
        cognito.create_resource_server(
            UserPoolId=pool_id,
            Identifier=COGNITO_RESOURCE_SERVER_ID,
            Name=COGNITO_RESOURCE_SERVER_NAME,
            Scopes=COGNITO_SCOPES,
        )
        print(f"  ✅ Created resource server")


def get_or_create_m2m_client(pool_id):
    for client in cognito.list_user_pool_clients(UserPoolId=pool_id, MaxResults=60)["UserPoolClients"]:
        if client["ClientName"] == COGNITO_CLIENT_NAME:
            desc = cognito.describe_user_pool_client(UserPoolId=pool_id, ClientId=client["ClientId"])
            print(f"  📋 M2M client already exists: {client['ClientId']}")
            return client["ClientId"], desc["UserPoolClient"]["ClientSecret"]
    scopes = [f"{COGNITO_RESOURCE_SERVER_ID}/gateway:read", f"{COGNITO_RESOURCE_SERVER_ID}/gateway:write"]
    resp = cognito.create_user_pool_client(
        UserPoolId=pool_id,
        ClientName=COGNITO_CLIENT_NAME,
        GenerateSecret=True,
        AllowedOAuthFlows=["client_credentials"],
        AllowedOAuthScopes=scopes,
        AllowedOAuthFlowsUserPoolClient=True,
        SupportedIdentityProviders=["COGNITO"],
        ExplicitAuthFlows=["ALLOW_REFRESH_TOKEN_AUTH"],
    )
    client_id = resp["UserPoolClient"]["ClientId"]
    client_secret = resp["UserPoolClient"]["ClientSecret"]
    print(f"  ✅ Created M2M client: {client_id}")
    return client_id, client_secret


def setup_cognito():
    print("\n🔑 Step 3: Setting up Cognito auth...")
    pool_id = get_or_create_user_pool()
    ensure_resource_server(pool_id)
    client_id, client_secret = get_or_create_m2m_client(pool_id)
    discovery_url = f"https://cognito-idp.{REGION}.amazonaws.com/{pool_id}/.well-known/openid-configuration"
    scope_string = f"{COGNITO_RESOURCE_SERVER_ID}/gateway:read {COGNITO_RESOURCE_SERVER_ID}/gateway:write"
    print(f"  Discovery URL: {discovery_url}")

    # Store credentials in Secrets Manager
    store_cognito_credentials(client_id, client_secret)

    return {
        "user_pool_id": pool_id,
        "client_id": client_id,
        "discovery_url": discovery_url,
        "scope_string": scope_string,
    }


def store_cognito_credentials(client_id, client_secret):
    """Store Cognito client credentials in AWS Secrets Manager."""
    secret_value = json.dumps({
        "cognito_client_id": client_id,
        "cognito_client_secret": client_secret,
    })
    try:
        secretsmanager.create_secret(
            Name=COGNITO_SECRET_NAME,
            Description="Cognito M2M client credentials for travel assistant gateway",
            SecretString=secret_value,
        )
        print(f"  ✅ Stored credentials in Secrets Manager: {COGNITO_SECRET_NAME}")
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceExistsException":
            secretsmanager.put_secret_value(
                SecretId=COGNITO_SECRET_NAME,
                SecretString=secret_value,
            )
            print(f"  🔄 Updated credentials in Secrets Manager: {COGNITO_SECRET_NAME}")
        else:
            raise


# ---------------------------------------------------------------------------
# 4. Create the AgentCore Gateway
# ---------------------------------------------------------------------------

def create_gateway(gateway_role_arn, cognito_info):
    print("\n🌐 Step 4: Creating AgentCore Gateway...")
    auth_config = {
        "customJWTAuthorizer": {
            "allowedClients": [cognito_info["client_id"]],
            "discoveryUrl": cognito_info["discovery_url"],
        }
    }
    try:
        resp = gateway_client.create_gateway(
            name=GATEWAY_NAME,
            roleArn=gateway_role_arn,
            protocolType="MCP",
            authorizerType="CUSTOM_JWT",
            authorizerConfiguration=auth_config,
            description="AgentCore Gateway with AWS Lambda target type for AnyCompany AI Travel Assistant",
        )
        gateway_id = resp["gatewayId"]
        gateway_url = resp["gatewayUrl"]
        print(f"  ✅ Created gateway: {gateway_id}")
        print(f"  Gateway URL: {gateway_url}")
        return gateway_id, gateway_url
    except ClientError as e:
        if "ConflictException" in str(e):
            gateways = gateway_client.list_gateways(maxResults=100)
            for gw in gateways["items"]:
                if gw["name"] == GATEWAY_NAME:
                    gw_id = gw["gatewayId"]
                    print(f"  📋 Gateway already exists: {gw_id}")
                    # Fetch full details to get gatewayUrl
                    detail = gateway_client.get_gateway(gatewayIdentifier=gw_id)
                    # Update authorizer to match current Cognito credentials
                    gateway_client.update_gateway(
                        gatewayIdentifier=gw_id,
                        name=GATEWAY_NAME,
                        roleArn=gateway_role_arn,
                        authorizerType="CUSTOM_JWT",
                        authorizerConfiguration=auth_config,
                    )
                    print(f"  🔄 Updated gateway authorizer to current Cognito pool")
                    return gw_id, detail["gatewayUrl"]
        raise


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("  AgentCore MCP Gateway Deployment")
    print("=" * 60)

    lambda_arns = deploy_all_lambdas()
    gateway_role_arn = create_gateway_role()
    cognito_info = setup_cognito()
    gateway_id, gateway_url = create_gateway(gateway_role_arn, cognito_info)

    # Save config for downstream scripts (e.g., register-target.py)
    config = {
        "region": REGION,
        "gateway_id": gateway_id,
        "gateway_url": gateway_url,
        "gateway_role_arn": gateway_role_arn,
        "cognito_user_pool_id": cognito_info["user_pool_id"],
        "cognito_secret_name": COGNITO_SECRET_NAME,
        "cognito_discovery_url": cognito_info["discovery_url"],
        "cognito_scope_string": cognito_info["scope_string"],
        "lambda_arns": lambda_arns,
    }
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)

    print("\n" + "=" * 60)
    print("🎉 Deployment complete!")
    print(f"  Gateway ID:  {gateway_id}")
    print(f"  Gateway URL: {gateway_url}")
    print(f"  Config saved to: {CONFIG_PATH}")
    print("=" * 60)


if __name__ == "__main__":
    main()
