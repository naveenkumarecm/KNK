"""
Purpose of Payment Analysis Lambda
Responsibilities:
- NLP classification of payment purpose
- Scam pattern detection
- Behaviour comparison with user history
- Confidence scoring

This Lambda evaluates the declared purpose/reference of a payment
to detect social engineering scams and misleading payment narratives.
"""

import json
import os
import re
import time
import boto3
from botocore.exceptions import ClientError

# Configuration
REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
PURPOSE_HISTORY_TABLE = os.environ.get("PURPOSE_HISTORY_TABLE", "purpose_history_store")

# ─────────────────────────────────────────────────────────────────────────────
# Scam Pattern Definitions
# ─────────────────────────────────────────────────────────────────────────────

# Investment scam keywords
INVESTMENT_SCAM_KEYWORDS = [
    "crypto", "bitcoin", "btc", "eth", "ethereum", "trading platform",
    "forex", "binary option", "guaranteed return", "high yield",
    "double your money", "investment opportunity", "passive income",
    "nft", "token sale", "ico", "defi", "mining pool",
    "portfolio manager", "fund manager", "broker account",
]

# Romance scam keywords
ROMANCE_SCAM_KEYWORDS = [
    "stuck abroad", "hospital bill", "customs fee", "travel emergency",
    "need help urgently", "stranded", "visa fee", "release funds",
    "gold shipment", "inheritance release", "diplomatic bag",
    "military deployment", "oil rig",
]

# Impersonation scam keywords
IMPERSONATION_SCAM_KEYWORDS = [
    "hmrc", "tax refund", "inland revenue", "irs", "tax office",
    "police fine", "court order", "arrest warrant", "debt collection",
    "amazon refund", "microsoft support", "apple security",
    "bank security team", "fraud department", "account suspended",
    "verify identity", "security check",
]

# Invoice redirection keywords
INVOICE_REDIRECTION_KEYWORDS = [
    "updated bank details", "new account number", "changed bank",
    "payment details updated", "revised invoice", "new sort code",
    "supplier change", "vendor update", "account migration",
    "banking partner change",
]

# Urgency indicators (amplifiers)
URGENCY_KEYWORDS = [
    "urgent", "immediately", "asap", "right now", "today only",
    "expires", "deadline", "last chance", "final notice",
    "act now", "time sensitive", "limited time",
]

# Purpose category keyword mapping
CATEGORY_KEYWORDS = {
    "PERSONAL_TRANSFER": [
        "gift", "birthday", "family", "friend", "rent", "allowance",
        "pocket money", "loan repayment", "personal",
    ],
    "BILL_PAYMENT": [
        "utility", "electricity", "gas", "water", "phone bill",
        "internet", "broadband", "council tax", "insurance",
        "subscription", "membership", "monthly payment",
    ],
    "PURCHASE": [
        "purchase", "order", "buying", "payment for goods",
        "marketplace", "ebay", "product", "delivery",
        "shopping", "items", "merchandise",
    ],
    "INVESTMENT": [
        "investment", "shares", "stocks", "trading", "portfolio",
        "fund", "savings plan", "pension", "isa", "bonds",
        "crypto", "bitcoin", "forex",
    ],
    "CHARITY": [
        "donation", "charity", "fundraiser", "gofundme",
        "disaster relief", "humanitarian", "nonprofit",
        "church", "mosque", "temple", "tithe",
    ],
}


# ─────────────────────────────────────────────────────────────────────────────
# Classification Functions
# ─────────────────────────────────────────────────────────────────────────────

def classify_purpose_category(text):
    """
    Classify payment purpose into a category using keyword matching.
    Returns (category, confidence_score).
    """
    text_lower = text.lower()
    scores = {}

    for category, keywords in CATEGORY_KEYWORDS.items():
        match_count = sum(1 for kw in keywords if kw in text_lower)
        if match_count > 0:
            scores[category] = match_count / len(keywords)

    if not scores:
        return "UNKNOWN", 0.3

    best_category = max(scores, key=scores.get)
    confidence = min(scores[best_category] * 5, 0.95)  # Scale up, cap at 0.95

    return best_category, round(confidence, 2)


def detect_scam_indicator(text):
    """
    Detect scam patterns in payment reference/purpose.
    Returns (scam_indicator, confidence, matched_patterns).
    """
    text_lower = text.lower()
    detections = []

    # Check investment scam
    investment_matches = [kw for kw in INVESTMENT_SCAM_KEYWORDS if kw in text_lower]
    if investment_matches:
        detections.append(("INVESTMENT_SCAM", len(investment_matches), investment_matches))

    # Check romance scam
    romance_matches = [kw for kw in ROMANCE_SCAM_KEYWORDS if kw in text_lower]
    if romance_matches:
        detections.append(("ROMANCE_SCAM", len(romance_matches), romance_matches))

    # Check impersonation
    impersonation_matches = [kw for kw in IMPERSONATION_SCAM_KEYWORDS if kw in text_lower]
    if impersonation_matches:
        detections.append(("IMPERSONATION", len(impersonation_matches), impersonation_matches))

    # Check invoice redirection
    invoice_matches = [kw for kw in INVOICE_REDIRECTION_KEYWORDS if kw in text_lower]
    if invoice_matches:
        detections.append(("INVOICE_REDIRECTION", len(invoice_matches), invoice_matches))

    if not detections:
        return "NONE", 0.0, []

    # Return highest-confidence detection
    detections.sort(key=lambda x: x[1], reverse=True)
    best = detections[0]
    confidence = min(best[1] * 0.25, 0.98)  # Scale match count to confidence

    return best[0], round(confidence, 2), best[2]


def check_urgency(text):
    """Check for urgency indicators that amplify scam risk."""
    text_lower = text.lower()
    matches = [kw for kw in URGENCY_KEYWORDS if kw in text_lower]
    return len(matches) > 0, matches


def check_historical_deviation(purpose_category, user_id, dynamodb=None):
    """
    Check if this payment purpose deviates from the user's historical patterns.
    Returns True if this is a first-time or unusual pattern for this user.
    """
    if not user_id:
        return True  # No user context = treat as deviation

    if dynamodb is None:
        dynamodb = boto3.resource("dynamodb", region_name=REGION)

    try:
        table = dynamodb.Table(PURPOSE_HISTORY_TABLE)
        response = table.get_item(
            Key={"user_id": user_id, "purpose_category": purpose_category}
        )
        if "Item" not in response:
            return True  # Never seen this category from this user

        # Check frequency - if very infrequent, still flag
        item = response["Item"]
        count = int(item.get("transaction_count", 0))
        return count < 3  # Less than 3 prior transactions = still unusual

    except ClientError:
        return True  # Error = conservative approach


def calculate_purpose_risk_score(purpose_analysis):
    """
    Calculate purpose-based risk score.

    Signal                      | Condition                    | Score Impact
    Scam keywords               | crypto, urgent, investment   | +30
    High-risk category          | INVESTMENT / UNKNOWN         | +25
    Known scam pattern          | invoice redirection          | +50
    Behaviour deviation         | first-time pattern           | +25
    Low confidence              | ambiguous intent             | +10
    Urgency amplifier           | urgent language detected     | +15
    """
    score = 0

    scam_indicator = purpose_analysis.get("scamIndicator", "NONE")
    category = purpose_analysis.get("purposeCategory", "UNKNOWN")
    confidence = purpose_analysis.get("confidenceScore", 0)
    has_deviation = purpose_analysis.get("historicalDeviation", False)
    has_urgency = purpose_analysis.get("urgencyDetected", False)

    # Scam keywords / pattern detected
    if scam_indicator == "INVOICE_REDIRECTION":
        score += 50
    elif scam_indicator in ("INVESTMENT_SCAM", "ROMANCE_SCAM", "IMPERSONATION"):
        score += 30

    # High-risk category
    if category in ("INVESTMENT", "UNKNOWN"):
        score += 25

    # Behaviour deviation
    if has_deviation:
        score += 25

    # Low confidence classification
    if confidence < 0.5 and category != "UNKNOWN":
        score += 10

    # Urgency amplifier
    if has_urgency:
        score += 15

    return min(score, 100)


def determine_action(purpose_risk_score, purpose_analysis, transaction_amount=0):
    """
    Determine appropriate action based on purpose analysis.

    Scenario                              | Action
    Investment scam detected              | Warning + step-up
    Purpose mismatch                      | Customer confirmation
    Invoice redirection pattern           | Delay / review
    High-risk purpose + high amount       | Block
    """
    actions = []
    risk_factors = []
    warnings = []

    scam_indicator = purpose_analysis.get("scamIndicator", "NONE")
    category = purpose_analysis.get("purposeCategory", "UNKNOWN")
    has_deviation = purpose_analysis.get("historicalDeviation", False)

    if scam_indicator == "INVESTMENT_SCAM":
        risk_factors.append("INVESTMENT_SCAM_PATTERN")
        actions.append("WARNING_AND_STEP_UP")
        warnings.append(
            "This payment matches patterns seen in investment scams. "
            "Are you being pressured to act quickly?"
        )

    if scam_indicator == "ROMANCE_SCAM":
        risk_factors.append("ROMANCE_SCAM_PATTERN")
        actions.append("WARNING_AND_STEP_UP")
        warnings.append(
            "This payment matches patterns associated with romance scams. "
            "Please verify you know this person in real life."
        )

    if scam_indicator == "IMPERSONATION":
        risk_factors.append("IMPERSONATION_PATTERN")
        actions.append("WARNING_AND_STEP_UP")
        warnings.append(
            "This payment reference resembles known impersonation scams. "
            "Legitimate organisations will never ask you to transfer money urgently."
        )

    if scam_indicator == "INVOICE_REDIRECTION":
        risk_factors.append("INVOICE_REDIRECTION_PATTERN")
        actions.append("DELAY_AND_REVIEW")
        warnings.append(
            "This payment mentions changed bank details. "
            "Please verify directly with the supplier using a known phone number."
        )

    if has_deviation:
        risk_factors.append("PURPOSE_DEVIATION")
        if "WARNING_AND_STEP_UP" not in actions:
            actions.append("CUSTOMER_CONFIRMATION")
            warnings.append(
                "You have not previously made payments of this type. "
                "Please confirm the purpose."
            )

    if category in ("INVESTMENT", "UNKNOWN"):
        risk_factors.append("HIGH_RISK_CATEGORY")

    # High-risk purpose + high amount -> Block
    if purpose_risk_score > 60 and transaction_amount > 5000:
        actions.append("BLOCK")

    # Determine overall decision
    if "BLOCK" in actions:
        decision = "BLOCK"
    elif "DELAY_AND_REVIEW" in actions:
        decision = "DELAY"
    elif "WARNING_AND_STEP_UP" in actions:
        decision = "STEP_UP_AUTH"
    elif "CUSTOMER_CONFIRMATION" in actions:
        decision = "CONFIRM"
    elif purpose_risk_score > 40:
        decision = "REVIEW"
    else:
        decision = "ALLOW"

    return {
        "decision": decision,
        "actions": actions,
        "riskFactors": risk_factors,
        "purposeRiskScore": purpose_risk_score,
        "customerWarnings": warnings,
    }


def lambda_handler(event, context):
    """
    Purpose Analysis Lambda Handler.

    Input:
    {
        "paymentReference": "Investment in crypto trading platform",
        "purposeCode": "INVESTMENT",
        "userId": "user-123",
        "transactionAmount": 5000.00
    }

    Output:
    {
        "statusCode": 200,
        "body": {
            "purposeAnalysis": { ... },
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

    payment_reference = body.get("paymentReference", "").strip()
    purpose_code = body.get("purposeCode", "").strip()
    user_id = body.get("userId", "")
    transaction_amount = float(body.get("transactionAmount", 0))

    if not payment_reference and not purpose_code:
        return {
            "statusCode": 400,
            "body": json.dumps({
                "error": "Missing required parameter: paymentReference or purposeCode"
            })
        }

    # Combine reference and purpose code for analysis
    analysis_text = f"{payment_reference} {purpose_code}".strip()

    # --- Perform Purpose Analysis ---

    # 1. Classify purpose category
    category, category_confidence = classify_purpose_category(analysis_text)

    # 2. Detect scam indicators
    scam_indicator, scam_confidence, matched_patterns = detect_scam_indicator(analysis_text)

    # 3. Check urgency
    has_urgency, urgency_matches = check_urgency(analysis_text)

    # 4. Check historical deviation
    historical_deviation = check_historical_deviation(category, user_id)

    # 5. Overall confidence (blend of category and scam confidence)
    if scam_indicator != "NONE":
        overall_confidence = max(category_confidence, scam_confidence)
    else:
        overall_confidence = category_confidence

    # Build purpose analysis object (matches API schema)
    purpose_analysis = {
        "declaredPurpose": payment_reference or purpose_code,
        "purposeCategory": category,
        "scamIndicator": scam_indicator,
        "confidenceScore": overall_confidence,
        "historicalDeviation": historical_deviation,
        "urgencyDetected": has_urgency,
        "matchedPatterns": matched_patterns,
        "urgencyPatterns": urgency_matches,
        "analysisTimestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    # 6. Calculate purpose risk score
    purpose_risk_score = calculate_purpose_risk_score(purpose_analysis)

    # 7. Determine action
    risk_assessment = determine_action(purpose_risk_score, purpose_analysis, transaction_amount)

    # Build response
    response_body = {
        "purposeAnalysis": purpose_analysis,
        "riskAssessment": risk_assessment,
    }

    return {
        "statusCode": 200,
        "body": json.dumps(response_body, default=str)
    }
