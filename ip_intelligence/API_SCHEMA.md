# IP Intelligence API Schema

## Channel Object Extension

```json
{
  "ipIntelligence": {
    "type": "object",
    "properties": {
      "ipAddress": { "type": "string" },
      "country": { "type": "string" },
      "region": { "type": "string" },
      "city": { "type": "string" },
      "isVpn": { "type": "boolean" },
      "isProxy": { "type": "boolean" },
      "isTor": { "type": "boolean" },
      "ipReputationScore": {
        "type": "number",
        "minimum": 0,
        "maximum": 100
      },
      "isHighRiskGeo": { "type": "boolean" },
      "velocityFlag": {
        "type": "boolean",
        "description": "Multiple requests from same IP in short time"
      },
      "isNewIp": {
        "type": "boolean",
        "description": "IP not previously seen for this user"
      },
      "lastSeenTimestamp": {
        "type": "string",
        "format": "date-time"
      }
    }
  }
}
```

## API Endpoints

### POST /api/ip-intelligence

Evaluate IP address risk profile in real-time.

**Request:**
```json
{
  "ipAddress": "192.168.1.10",
  "userId": "user-123",
  "transactionAmount": 500.00,
  "channelInfo": {
    "type": "web",
    "newDevice": false
  },
  "behaviouralSignals": {
    "unusualTime": false,
    "rapidSequence": false,
    "newPayee": true
  }
}
```

**Response:**
```json
{
  "ipIntelligence": {
    "ipAddress": "192.168.1.10",
    "country": "US",
    "region": "California",
    "city": "San Francisco",
    "isVpn": false,
    "isProxy": false,
    "isTor": false,
    "ipReputationScore": 0,
    "isHighRiskGeo": false,
    "velocityFlag": false,
    "isNewIp": true,
    "lastSeenTimestamp": "2026-06-17T10:30:00Z"
  },
  "riskAssessment": {
    "decision": "LOW_RISK",
    "actions": [],
    "riskFactors": ["NEW_UNSEEN_IP"],
    "ipRiskScore": 15
  },
  "fullRiskAssessment": {
    "totalRiskScore": 35,
    "riskLevel": "LOW_MEDIUM",
    "decision": "MONITOR",
    "scoreBreakdown": {
      "amountScore": 10,
      "copScore": 0,
      "behaviouralScore": 10,
      "channelScore": 10,
      "ipRiskScore": 15
    },
    "riskFactors": ["NEW_UNSEEN_IP"],
    "processingTimeMs": 12.5,
    "withinSla": true
  }
}
```

### GET /api/ip-intelligence/check/{ip_address}

Quick IP lookup without full risk scoring.

**Response:**
```json
{
  "ipIntelligence": { ... },
  "riskAssessment": { ... }
}
```

## Risk Scoring Formula

```
riskScore = amountScore + copScore + behaviouralScore + channelScore + ipRiskScore
```

### IP Risk Scoring Logic

| Signal | Condition | Score Impact |
|--------|-----------|--------------|
| VPN / Proxy detected | isVpn or isProxy = true | +25 |
| TOR usage | isTor = true | +40 |
| High-risk country | isHighRiskGeo = true | +20 |
| IP reputation | score > 70 | +30 |
| Velocity anomaly | repeated requests | +20 |
| New/unseen IP | not in user history | +15 |

## Decisioning Rules

| Scenario | Action |
|----------|--------|
| VPN + high-value payment (>$1000) | Step-up authentication |
| TOR usage | Block or manual review |
| High-risk geo + velocity spike | Delay + warning |
| Velocity spike | Temporary throttle |

## DynamoDB Schema

### ip_velocity_tracking
```json
{
  "ip_address": "192.168.1.10",    // Partition Key (String)
  "timestamp": 1718630400,          // Sort Key (Number)
  "ttl": 1718631000                 // TTL for auto-cleanup
}
```

### ip_reputation_store
```json
{
  "ip_address": "192.168.1.10",    // Partition Key (String)
  "user_id": "user-123",           // Sort Key (String)
  "ipRiskScore": 45,
  "ipFlags": ["VPN", "HIGH_RISK_GEO"],
  "ipReputationScore": 80,
  "velocityFlag": true,
  "firstSeen": "2026-06-01T...",
  "lastSeen": "2026-06-17T..."
}
```
