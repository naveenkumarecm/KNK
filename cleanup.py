#!/usr/bin/env python3
"""
Cleans up ALL resources deployed by sample-travel-assistant-workshop/ scripts.

Deletion order respects dependencies:
  1. AgentCore agent runtime endpoints → agent runtimes (supervisor first, then flight)
  2. SSM parameters (agent ARNs)
  2b. Secrets Manager secrets (Cognito credentials)
  3. Gateway targets → gateway
  4. Cognito client → resource server → user pool domain → user pool
  5. Lambda functions → Lambda IAM role
  6. Agent IAM roles (inline policies detached first)
  7. Gateway IAM role
  8. ECR repositories
  9. Local staging directory

Usage:
    python cleanup.py           # delete everything
    python cleanup.py --dry-run # show what would be deleted
"""

import boto3
import json
import os
import sys
import shutil
import time
from botocore.exceptions import ClientError

REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PREFIX = "exec"
DRY_RUN = "--dry-run" in sys.argv

# Clients
iam = boto3.client("iam", region_name=REGION)
ssm = boto3.client("ssm", region_name=REGION)
lam = boto3.client("lambda", region_name=REGION)
cognito = boto3.client("cognito-idp", region_name=REGION)
ecr = boto3.client("ecr", region_name=REGION)
agentcore = boto3.client("bedrock-agentcore-control", region_name=REGION)
secretsmanager = boto3.client("secretsmanager", region_name=REGION)

# Resource names (must match deploy scripts)
LAMBDA_NAMES = [
    f"{PREFIX}_search_flights_lambda", f"{PREFIX}_book_flight_lambda",
]
AGENT_ROLE_NAMES = [
    f"agentcore-{PREFIX}-flight_agent-role",
    f"agentcore-{PREFIX}-supervisor_agent-role",
]
GATEWAY_ROLE_NAME = f"agentcore-{PREFIX}-lambdagateway-role"
LAMBDA_ROLE_NAME = f"{PREFIX}_gateway_lambda_iamrole"
COGNITO_POOL_NAME = f"{PREFIX}-agentcore-gateway-pool"
COGNITO_RESOURCE_SERVER_ID = f"{PREFIX}-agentcore-gateway-id"
COGNITO_CLIENT_NAME = f"{PREFIX}-agentcore-gateway-client"
GATEWAY_NAME = f"{PREFIX}-TravellerAppGwforLambda"
SSM_PARAMS = ["/agents/flight_agent_arn", "/agents/supervisor_agent_arn"]
AGENT_NAMES = [f"{PREFIX}_flight_agent", f"{PREFIX}_supervisor_agent"]
COGNITO_SECRET_NAME = "travel-assistant/cognito-credentials"
STAGING_DIR = os.path.join(SCRIPT_DIR, "_agent_staging")


def safe(fn, *args, **kwargs):
    """Call fn, swallow NotFound/NoSuchEntity errors, print others."""
    try:
        if not DRY_RUN:
            return fn(*args, **kwargs)
        return None
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code in ("ResourceNotFoundException", "NoSuchEntity", "ResourceNotFoundFault",
                     "NotFoundException", "NoSuchEntityException", "ParameterNotFound",
                     "ResourceNotFoundException", "RepositoryNotFoundException",
                     "ConflictException"):
            print(f"    ⚠️  Already gone ({code})")
        else:
            print(f"    ❌ Error: {e}")
    return None


# ---------------------------------------------------------------------------
# 1. Delete AgentCore agent runtimes (endpoints first, then runtimes)
# ---------------------------------------------------------------------------
def delete_agent_runtimes():
    print("\n🤖 Step 1: Deleting AgentCore agent runtimes...")
    deleted_ids = set()

    # Find agent runtime IDs by name
    try:
        runtimes = agentcore.list_agent_runtimes(maxResults=100).get("agentRuntimes", [])
    except Exception as e:
        print(f"    ❌ Could not list runtimes: {e}")
        runtimes = []

    for name in reversed(AGENT_NAMES):  # supervisor first, then flight
        matches = [r for r in runtimes if r.get("agentRuntimeName") == name]
        if not matches:
            print(f"  ⏭️  Runtime '{name}' not found, skipping")
            continue
        for rt in matches:
            rt_id = rt["agentRuntimeId"]
            print(f"  Deleting runtime: {name} ({rt_id})")
            # Delete endpoints first
            try:
                endpoints = agentcore.list_agent_runtime_endpoints(
                    agentRuntimeId=rt_id, maxResults=100
                ).get("runtimeEndpoints", [])
                for ep in endpoints:
                    ep_name = ep.get("name", ep.get("endpointName", "DEFAULT"))
                    print(f"    Deleting endpoint: {ep_name}")
                    safe(agentcore.delete_agent_runtime_endpoint,
                         agentRuntimeId=rt_id, endpointName=ep_name)
                if endpoints and not DRY_RUN:
                    print("    ⏳ Waiting for endpoint deletion...")
                    time.sleep(15)
            except ClientError:
                pass
            safe(agentcore.delete_agent_runtime, agentRuntimeId=rt_id)
            deleted_ids.add(rt_id)
            print(f"    ✅ Deleted runtime: {name}")

    # Fallback: try from config.json for any runtimes not found by list
    config_path = os.path.join(SCRIPT_DIR, "config.json")
    if os.path.exists(config_path):
        with open(config_path) as f:
            cfg = json.load(f)
        for key in ["supervisor_agent_arn", "flight_agent_arn"]:
            arn = cfg.get(key, "")
            if not arn:
                continue
            rt_id = arn.split("/")[-1] if "/" in arn else ""
            if rt_id and rt_id not in deleted_ids:
                print(f"  Deleting runtime from config: {rt_id}")
                try:
                    endpoints = agentcore.list_agent_runtime_endpoints(
                        agentRuntimeId=rt_id, maxResults=100
                    ).get("runtimeEndpoints", [])
                    for ep in endpoints:
                        ep_name = ep.get("name", ep.get("endpointName", "DEFAULT"))
                        safe(agentcore.delete_agent_runtime_endpoint,
                             agentRuntimeId=rt_id, endpointName=ep_name)
                except ClientError:
                    pass
                safe(agentcore.delete_agent_runtime, agentRuntimeId=rt_id)


# ---------------------------------------------------------------------------
# 2. Delete SSM parameters
# ---------------------------------------------------------------------------
def delete_ssm_params():
    print("\n📝 Step 2: Deleting SSM parameters...")
    for param in SSM_PARAMS:
        print(f"  Deleting: {param}")
        safe(ssm.delete_parameter, Name=param)
        print(f"    ✅ Deleted")


# ---------------------------------------------------------------------------
# 2b. Delete Secrets Manager secret
# ---------------------------------------------------------------------------
def delete_secrets():
    print("\n🔐 Step 2b: Deleting Secrets Manager secrets...")
    print(f"  Deleting: {COGNITO_SECRET_NAME}")
    safe(secretsmanager.delete_secret, SecretId=COGNITO_SECRET_NAME, ForceDeleteWithoutRecovery=True)
    print(f"    ✅ Deleted")


# ---------------------------------------------------------------------------
# 3. Delete gateway targets → gateway
# ---------------------------------------------------------------------------
def delete_gateway():
    print("\n🌐 Step 3: Deleting gateway targets and gateway...")
    # Find gateway ID
    gateway_id = None
    config_path = os.path.join(SCRIPT_DIR, "config.json")
    if os.path.exists(config_path):
        with open(config_path) as f:
            gateway_id = json.load(f).get("gateway_id")

    if not gateway_id:
        try:
            gateways = agentcore.list_gateways(maxResults=100).get("items", [])
            for gw in gateways:
                if gw.get("name") == GATEWAY_NAME:
                    gateway_id = gw["gatewayId"]
                    break
        except Exception as e:
            print(f"    ❌ Could not list gateways: {e}")

    if not gateway_id:
        print("  ⏭️  Gateway not found, skipping")
        return

    # Delete all targets first
    try:
        targets = agentcore.list_gateway_targets(
            gatewayIdentifier=gateway_id, maxResults=100
        ).get("items", [])
        for t in targets:
            tid = t["targetId"]
            print(f"  Deleting target: {t.get('name', tid)}")
            safe(agentcore.delete_gateway_target, gatewayIdentifier=gateway_id, targetId=tid)
            print(f"    ✅ Deleted")
        if targets and not DRY_RUN:
            print("  ⏳ Waiting for target deletion to propagate...")
            time.sleep(10)
    except ClientError as e:
        print(f"    ⚠️  Could not list targets: {e}")

    # Delete gateway
    print(f"  Deleting gateway: {GATEWAY_NAME} ({gateway_id})")
    safe(agentcore.delete_gateway, gatewayIdentifier=gateway_id)
    print(f"    ✅ Deleted")


# ---------------------------------------------------------------------------
# 4. Delete Cognito resources (client → resource server → domain → pool)
# ---------------------------------------------------------------------------
def delete_cognito():
    print("\n🔑 Step 4: Deleting Cognito resources...")
    pool_id = None
    for pool in cognito.list_user_pools(MaxResults=60).get("UserPools", []):
        if pool["Name"] == COGNITO_POOL_NAME:
            pool_id = pool["Id"]
            break
    if not pool_id:
        print("  ⏭️  User pool not found, skipping")
        return

    # Delete client
    for client in cognito.list_user_pool_clients(UserPoolId=pool_id, MaxResults=60).get("UserPoolClients", []):
        if client["ClientName"] == COGNITO_CLIENT_NAME:
            print(f"  Deleting client: {COGNITO_CLIENT_NAME}")
            safe(cognito.delete_user_pool_client, UserPoolId=pool_id, ClientId=client["ClientId"])
            print(f"    ✅ Deleted")

    # Delete resource server
    print(f"  Deleting resource server: {COGNITO_RESOURCE_SERVER_ID}")
    safe(cognito.delete_resource_server, UserPoolId=pool_id, Identifier=COGNITO_RESOURCE_SERVER_ID)
    print(f"    ✅ Deleted")

    # Delete domain
    try:
        desc = cognito.describe_user_pool(UserPoolId=pool_id)
        domain = desc.get("UserPool", {}).get("Domain")
        if domain:
            print(f"  Deleting domain: {domain}")
            safe(cognito.delete_user_pool_domain, UserPoolId=pool_id, Domain=domain)
            print(f"    ✅ Deleted")
    except ClientError:
        pass

    # Delete pool
    print(f"  Deleting user pool: {pool_id}")
    safe(cognito.delete_user_pool, UserPoolId=pool_id)
    print(f"    ✅ Deleted")


# ---------------------------------------------------------------------------
# 5. Delete Lambda functions → Lambda IAM role
# ---------------------------------------------------------------------------
def delete_lambdas():
    print("\n⚡ Step 5: Deleting Lambda functions...")
    for fn in LAMBDA_NAMES:
        print(f"  Deleting: {fn}")
        safe(lam.delete_function, FunctionName=fn)
        print(f"    ✅ Deleted")

    # Delete Lambda role
    print(f"  Deleting Lambda role: {LAMBDA_ROLE_NAME}")
    delete_iam_role(LAMBDA_ROLE_NAME)


# ---------------------------------------------------------------------------
# 6. Delete agent IAM roles
# ---------------------------------------------------------------------------
def delete_iam_role(role_name):
    """Delete an IAM role after removing all inline and attached policies."""
    try:
        # Remove inline policies
        for p in iam.list_role_policies(RoleName=role_name).get("PolicyNames", []):
            safe(iam.delete_role_policy, RoleName=role_name, PolicyName=p)
        # Detach managed policies
        for p in iam.list_attached_role_policies(RoleName=role_name).get("AttachedPolicies", []):
            safe(iam.detach_role_policy, RoleName=role_name, PolicyArn=p["PolicyArn"])
        safe(iam.delete_role, RoleName=role_name)
        print(f"    ✅ Deleted role: {role_name}")
    except ClientError as e:
        if e.response["Error"]["Code"] == "NoSuchEntity":
            print(f"    ⏭️  Role not found: {role_name}")
        else:
            print(f"    ❌ Error: {e}")


def delete_agent_roles():
    print("\n🔐 Step 6: Deleting agent IAM roles...")
    for role in AGENT_ROLE_NAMES:
        print(f"  Deleting: {role}")
        delete_iam_role(role)


# ---------------------------------------------------------------------------
# 7. Delete gateway IAM role
# ---------------------------------------------------------------------------
def delete_gateway_role():
    print("\n🔐 Step 7: Deleting gateway IAM role...")
    print(f"  Deleting: {GATEWAY_ROLE_NAME}")
    delete_iam_role(GATEWAY_ROLE_NAME)


# ---------------------------------------------------------------------------
# 8. Delete ECR repositories (created by starter toolkit with auto_create_ecr)
# ---------------------------------------------------------------------------
def delete_ecr_repos():
    print("\n📦 Step 8: Deleting ECR repositories...")
    try:
        repos = ecr.describe_repositories(maxResults=100).get("repositories", [])
        for repo in repos:
            name = repo["repositoryName"]
            # Starter toolkit names repos after the agent name
            if any(agent_name in name for agent_name in AGENT_NAMES):
                print(f"  Deleting ECR repo: {name}")
                safe(ecr.delete_repository, repositoryName=name, force=True)
                print(f"    ✅ Deleted")
    except ClientError as e:
        print(f"    ⚠️  Could not list ECR repos: {e}")


# ---------------------------------------------------------------------------
# 9. Clean up local files
# ---------------------------------------------------------------------------
def delete_local_files():
    print("\n🧹 Step 9: Cleaning up local files...")
    for path in [STAGING_DIR]:
        if os.path.exists(path):
            print(f"  Removing: {path}")
            if not DRY_RUN:
                shutil.rmtree(path)
            print(f"    ✅ Removed")

    for f in ["config.json"]:
        fp = os.path.join(SCRIPT_DIR, f)
        if os.path.exists(fp):
            print(f"  Removing: {fp}")
            if not DRY_RUN:
                os.remove(fp)
            print(f"    ✅ Removed")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    if DRY_RUN:
        print("🔍 DRY RUN — no resources will be deleted\n")

    print("=" * 60)
    print("  AnyCompany AI Travel Assistant Cleanup")
    print("=" * 60)
    print(f"  Region: {REGION}")
    print(f"  Prefix: {PREFIX}")

    delete_agent_runtimes()     # 1. agents (endpoints → runtimes)
    delete_ssm_params()         # 2. SSM params
    delete_secrets()            # 2b. Secrets Manager secrets
    delete_gateway()            # 3. gateway targets → gateway
    delete_cognito()            # 4. cognito client → server → domain → pool
    delete_lambdas()            # 5. Lambda functions → Lambda role
    delete_agent_roles()        # 6. agent IAM roles
    delete_gateway_role()       # 7. gateway IAM role
    delete_ecr_repos()          # 8. ECR repos
    delete_local_files()        # 9. local staging + config files

    print("\n" + "=" * 60)
    if DRY_RUN:
        print("🔍 DRY RUN complete — nothing was deleted")
    else:
        print("🧹 Cleanup complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
