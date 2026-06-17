"""
DynamoDB Table Setup for IP Intelligence Feature.

Creates the required tables:
1. ip_velocity_tracking - Tracks request frequency per IP for velocity detection
2. ip_reputation_store  - Stores IP-to-user history for new IP detection

Usage:
    python ip_intelligence/dynamodb_setup.py
"""

import boto3
import os
import json
import sys

REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")


def create_velocity_table(dynamodb_client):
    """
    Create the ip_velocity_tracking table.

    Schema:
    - Partition Key: ip_address (String)
    - Sort Key: timestamp (Number)
    - TTL: ttl field for automatic cleanup
    """
    table_name = "ip_velocity_tracking"

    try:
        dynamodb_client.create_table(
            TableName=table_name,
            KeySchema=[
                {"AttributeName": "ip_address", "KeyType": "HASH"},
                {"AttributeName": "timestamp", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "ip_address", "AttributeType": "S"},
                {"AttributeName": "timestamp", "AttributeType": "N"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        print(f"  ✅ Created table: {table_name}")

        # Wait for table to become active
        waiter = dynamodb_client.get_waiter("table_exists")
        waiter.wait(TableName=table_name)

        # Enable TTL
        dynamodb_client.update_time_to_live(
            TableName=table_name,
            TimeToLiveSpecification={
                "Enabled": True,
                "AttributeName": "ttl"
            }
        )
        print(f"  ✅ Enabled TTL on: {table_name}")

    except dynamodb_client.exceptions.ResourceInUseException:
        print(f"  ℹ️  Table already exists: {table_name}")


def create_reputation_table(dynamodb_client):
    """
    Create the ip_reputation_store table.

    Schema:
    - Partition Key: ip_address (String)
    - Sort Key: user_id (String)

    Stores:
    {
        "ipAddress": "192.168.1.10",
        "userId": "user-123",
        "ipRiskScore": 45,
        "ipFlags": ["VPN", "HIGH_RISK_GEO"],
        "ipReputationScore": 80,
        "velocityFlag": true,
        "firstSeen": "2026-06-01T...",
        "lastSeen": "2026-06-17T..."
    }
    """
    table_name = "ip_reputation_store"

    try:
        dynamodb_client.create_table(
            TableName=table_name,
            KeySchema=[
                {"AttributeName": "ip_address", "KeyType": "HASH"},
                {"AttributeName": "user_id", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "ip_address", "AttributeType": "S"},
                {"AttributeName": "user_id", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        print(f"  ✅ Created table: {table_name}")

        waiter = dynamodb_client.get_waiter("table_exists")
        waiter.wait(TableName=table_name)

    except dynamodb_client.exceptions.ResourceInUseException:
        print(f"  ℹ️  Table already exists: {table_name}")


def main():
    print("=" * 60)
    print("  IP Intelligence - DynamoDB Table Setup")
    print("=" * 60)
    print(f"  Region: {REGION}")
    print()

    dynamodb_client = boto3.client("dynamodb", region_name=REGION)

    print("📦 Creating DynamoDB tables...")
    create_velocity_table(dynamodb_client)
    create_reputation_table(dynamodb_client)

    print("\n✅ DynamoDB setup complete!")
    print("\nTables created:")
    print("  - ip_velocity_tracking (IP request frequency tracking with TTL)")
    print("  - ip_reputation_store  (IP-to-user history)")


if __name__ == "__main__":
    main()
