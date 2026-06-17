"""
IP Intelligence Lambda
Responsibilities:
- Geo-location lookup
- VPN/Proxy/TOR detection
- IP reputation scoring
- Velocity detection (via DynamoDB)

This Lambda evaluates the risk profile of an IP address in real-time
and returns enriched IP intelligence attributes for fraud scoring.
"""

import json
import os
import time
import hashlib
import boto3
from decimal import Decimal
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

# Configuration
REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
VELOCITY_TABLE = os.environ.get("IP_VELOCITY_TABLE", "ip_velocity_tracking")
IP_REPUTATION_TABLE = os.environ.get("IP_REPUTATION_TABLE", "ip_reputation_store")
VELOCITY_WINDOW_SECONDS = int(os.environ.get("VELOCITY_WINDOW_SECONDS", "300"))  # 5 minutes
VELOCITY_THRESHOLD = int(os.environ.get("VELOCITY_THRESHOLD", "5"))  # max requests per window

# High-risk countries (ISO 3166-1 alpha-2)
HIGH_RISK_COUNTRIES = {
    "NG", "GH", "CM", "KE", "PH", "RO", "UA", "RU", "BY", "KP",
    "IR", "SY", "YE", "SO", "LY", "SD", "VE", "MM", "AF", "IQ"
}

# Known VPN/Proxy/TOR IP ranges (sample data for demonstration)
KNOWN_VPN_RANGES = [
    "10.8.", "10.9.", "172.16.", "198.51.100.",  # Sample VPN ranges
]

KNOWN_PROXY_RANGES = [
    "203.0.113.", "192.0.2.",  # Sample proxy ranges
]

KNOWN_TOR_EXIT_NODES = set([
    "185.220.100.240", "185.220.100.241", "185.220.100.242",
    "185.220.100.243", "185.220.100.244", "185.220.100.245",
    "104.244.76.13", "104.244.76.14", "104.244.76.15",
    "199.249.230.87", "199.249.230.88", "199.249.230.89",
])

# Sample geo-location database (in production, use MaxMind GeoIP2 or similar)
GEO_DATABASE = {
    "192.168.1.": {"country": "US", "region": "California", "city": "San Francisco"},
    "10.0.0.": {"country": "US", "region": "New York", "city": "New York"},
    "172.16.0.": {"country": "RU", "region": "Moscow", "city": "Moscow"},
    "203.0.113.": {"country": "NG", "region": "Lagos", "city": "Lagos"},
    "198.51.100.": {"country": "CN", "region": "Beijing", "city": "Beijing"},
    "185.220.100.": {"country": "DE", "region": "Bavaria", "city": "Munich"},
    "104.244.76.": {"country": "NL", "region": "North Holland", "city": "Amsterdam"},
}


def get_dynamodb_resource():
    """Get DynamoDB resource."""
    return boto3.resource("dynamodb", region_name=REGION)


def get_geo_location(ip_address):
    """
    Lookup geo-location for an IP address.
    In production, integrate with MaxMind GeoIP2, IP2Location, or ipinfo.io.
    """
    for prefix, geo in GEO_DATABASE.items():
        if ip_address.startswith(prefix):
            return geo

    # Default fallback - unknown location
    return {"country": "UNKNOWN", "region": "UNKNOWN", "city": "UNKNOWN"}


def detect_vpn(ip_address):
    """Detect if IP is from a known VPN provider."""
    for vpn_range in KNOWN_VPN_RANGES:
        if ip_address.startswith(vpn_range):
            return True
    return False


def detect_proxy(ip_address):
    """Detect if IP is from a known proxy service."""
    for proxy_range in KNOWN_PROXY_RANGES:
        if ip_address.startswith(proxy_range):
            return True
    return False


def detect_tor(ip_address):
    """Detect if IP is a known TOR exit node."""
    return ip_address in KNOWN_TOR_EXIT_NODES


def is_high_risk_geo(country_code):
    """Check if the country is in the high-risk list."""
    return country_code.upper() in HIGH_RISK_COUNTRIES


def calculate_ip_reputation_score(ip_address, is_vpn, is_proxy, is_tor, is_high_risk, velocity_flag):
    """
    Calculate IP reputation score (0-100, higher = riskier).
    Combines multiple signals into a single reputation score.
    """
    score = 0

    if is_vpn:
        score += 25
    if is_proxy:
        score += 20
    if is_tor:
        score += 40
    if is_high_risk:
        score += 20
    if velocity_flag:
        score += 20

    # Cap at 100
    return min(score, 100)


def check_velocity(ip_address, dynamodb=None):
    """
    Check request velocity from this IP address.
    Returns True if velocity exceeds threshold (suspicious).
    Uses DynamoDB for tracking with TTL-based cleanup.
    """
    if dynamodb is None:
        dynamodb = get_dynamodb_resource()

    current_time = int(time.time())
    window_start = current_time - VELOCITY_WINDOW_SECONDS

    try:
        table = dynamodb.Table(VELOCITY_TABLE)

        # Record this request
        table.put_item(
            Item={
                "ip_address": ip_address,
                "timestamp": current_time,
                "ttl": current_time + (VELOCITY_WINDOW_SECONDS * 2),  # Auto-expire
            }
        )

        # Query recent requests from this IP
        response = table.query(
            KeyConditionExpression=(
                Key("ip_address").eq(ip_address) &
                Key("timestamp").gte(window_start)
            )
        )

        request_count = response.get("Count", 0)
        return request_count > VELOCITY_THRESHOLD

    except ClientError as e:
        # If table doesn't exist or other error, don't block - log and continue
        print(f"DynamoDB velocity check error: {e}")
        return False


def check_user_ip_history(ip_address, user_id, dynamodb=None):
    """
    Check if this IP has been seen before for this user.
    Returns True if IP is new/unseen for this user.
    """
    if not user_id:
        return True  # No user context = treat as new

    if dynamodb is None:
        dynamodb = get_dynamodb_resource()

    try:
        table = dynamodb.Table(IP_REPUTATION_TABLE)
        response = table.get_item(
            Key={"ip_address": ip_address, "user_id": user_id}
        )
        return "Item" not in response

    except ClientError:
        return True  # Error = treat as new (conservative)


def calculate_ip_risk_score(ip_intelligence):
    """
    Calculate the IP-specific risk score contribution.

    Signal                  | Condition              | Score Impact
    VPN / Proxy detected    | isVpn or isProxy       | +25
    TOR usage               | isTor = true           | +40
    High-risk country       | isHighRiskGeo = true   | +20
    IP reputation           | score > 70             | +30
    Velocity anomaly        | repeated requests      | +20
    New/unseen IP           | not in user history    | +15
    """
    score = 0

    if ip_intelligence.get("isVpn") or ip_intelligence.get("isProxy"):
        score += 25
    if ip_intelligence.get("isTor"):
        score += 40
    if ip_intelligence.get("isHighRiskGeo"):
        score += 20
    if ip_intelligence.get("ipReputationScore", 0) > 70:
        score += 30
    if ip_intelligence.get("velocityFlag"):
        score += 20
    if ip_intelligence.get("isNewIp"):
        score += 15

    return score


def determine_action(ip_risk_score, ip_intelligence, transaction_amount=0):
    """
    Determine the appropriate action based on IP risk assessment.

    Scenario                          | Action
    VPN + high-value payment          | Step-up authentication
    TOR usage                         | Block or manual review
    High-risk geo + new payee         | Delay + warning
    Velocity spike                    | Temporary throttle
    """
    actions = []
    risk_factors = []

    if ip_intelligence.get("isVpn") or ip_intelligence.get("isProxy"):
        risk_factors.append("VPN_DETECTED" if ip_intelligence.get("isVpn") else "PROXY_DETECTED")
        if transaction_amount > 1000:
            actions.append("STEP_UP_AUTHENTICATION")

    if ip_intelligence.get("isTor"):
        risk_factors.append("TOR_DETECTED")
        actions.append("BLOCK_OR_MANUAL_REVIEW")

    if ip_intelligence.get("isHighRiskGeo"):
        risk_factors.append("HIGH_RISK_GEO")
        actions.append("DELAY_AND_WARNING")

    if ip_intelligence.get("velocityFlag"):
        risk_factors.append("VELOCITY_ANOMALY")
        actions.append("TEMPORARY_THROTTLE")

    if ip_intelligence.get("ipReputationScore", 0) > 70:
        risk_factors.append("HIGH_REPUTATION_RISK")

    if ip_intelligence.get("isNewIp"):
        risk_factors.append("NEW_UNSEEN_IP")

    # Determine overall decision
    if "BLOCK_OR_MANUAL_REVIEW" in actions:
        decision = "BLOCK"
    elif "STEP_UP_AUTHENTICATION" in actions:
        decision = "STEP_UP_AUTH"
    elif ip_risk_score > 60:
        decision = "HIGH_RISK"
    elif ip_risk_score > 30:
        decision = "MEDIUM_RISK"
    else:
        decision = "LOW_RISK"

    return {
        "decision": decision,
        "actions": actions,
        "riskFactors": risk_factors,
        "ipRiskScore": ip_risk_score,
    }


def lambda_handler(event, context):
    """
    IP Intelligence Lambda Handler.

    Input:
    {
        "ipAddress": "192.168.1.10",
        "userId": "user-123",          (optional)
        "transactionAmount": 500.00,   (optional)
        "channel": "web"               (optional)
    }

    Output:
    {
        "statusCode": 200,
        "body": {
            "ipIntelligence": { ... },
            "riskAssessment": { ... }
        }
    }
    """
    # Parse input
    if isinstance(event.get("body"), str):
        body = json.loads(event["body"])
    elif "body" in event:
        body = event["body"]
    else:
        body = event

    ip_address = body.get("ipAddress", "").strip()
    user_id = body.get("userId", "")
    transaction_amount = float(body.get("transactionAmount", 0))

    if not ip_address:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "Missing required parameter: ipAddress"})
        }

    # --- Perform IP Intelligence Analysis ---

    # 1. Geo-location lookup
    geo = get_geo_location(ip_address)

    # 2. VPN/Proxy/TOR detection
    is_vpn = detect_vpn(ip_address)
    is_proxy = detect_proxy(ip_address)
    is_tor = detect_tor(ip_address)

    # 3. High-risk geography check
    high_risk_geo = is_high_risk_geo(geo["country"])

    # 4. Velocity detection
    velocity_flag = check_velocity(ip_address)

    # 5. Check if IP is new for this user
    is_new_ip = check_user_ip_history(ip_address, user_id)

    # 6. Calculate reputation score
    reputation_score = calculate_ip_reputation_score(
        ip_address, is_vpn, is_proxy, is_tor, high_risk_geo, velocity_flag
    )

    # Build IP Intelligence object (matches API schema)
    ip_intelligence = {
        "ipAddress": ip_address,
        "country": geo["country"],
        "region": geo["region"],
        "city": geo.get("city", ""),
        "isVpn": is_vpn,
        "isProxy": is_proxy,
        "isTor": is_tor,
        "ipReputationScore": reputation_score,
        "isHighRiskGeo": high_risk_geo,
        "velocityFlag": velocity_flag,
        "isNewIp": is_new_ip,
        "lastSeenTimestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    # 7. Calculate IP risk score
    ip_risk_score = calculate_ip_risk_score(ip_intelligence)

    # 8. Determine action
    risk_assessment = determine_action(ip_risk_score, ip_intelligence, transaction_amount)

    # Build response
    response_body = {
        "ipIntelligence": ip_intelligence,
        "riskAssessment": risk_assessment,
    }

    return {
        "statusCode": 200,
        "body": json.dumps(response_body, default=str)
    }
