"""
Risk Scoring Engine with IP Intelligence and Purpose Analysis Integration.

Updated formula:
    riskScore = amountScore + copScore + behaviouralScore + channelScore + ipRiskScore + purposeRiskScore

This module integrates IP-based scoring and purpose-of-payment analysis
into the overall fraud risk decisioning while maintaining the <300ms SLA requirement.
"""

import json
import time
from typing import Dict, Any, Optional


class RiskScoringEngine:
    """
    Unified risk scoring engine that combines multiple risk signals
    including IP intelligence for fraud detection.
    """

    # Score thresholds
    LOW_RISK_THRESHOLD = 30
    MEDIUM_RISK_THRESHOLD = 60
    HIGH_RISK_THRESHOLD = 80

    def __init__(self):
        self.start_time = None

    def calculate_amount_score(self, amount: float) -> int:
        """Score based on transaction amount."""
        if amount > 10000:
            return 40
        elif amount > 5000:
            return 30
        elif amount > 1000:
            return 20
        elif amount > 500:
            return 10
        return 0

    def calculate_cop_score(self, confirmation_of_payee: dict) -> int:
        """Score based on Confirmation of Payee result."""
        if not confirmation_of_payee:
            return 0

        match_status = confirmation_of_payee.get("matchStatus", "")
        if match_status == "NO_MATCH":
            return 35
        elif match_status == "PARTIAL_MATCH":
            return 20
        elif match_status == "CLOSE_MATCH":
            return 10
        return 0

    def calculate_behavioural_score(self, behavioural_signals: dict) -> int:
        """Score based on behavioural signals."""
        if not behavioural_signals:
            return 0

        score = 0
        if behavioural_signals.get("unusualTime"):
            score += 10
        if behavioural_signals.get("rapidSequence"):
            score += 15
        if behavioural_signals.get("newPayee"):
            score += 10
        if behavioural_signals.get("deviationFromPattern"):
            score += 15
        return score

    def calculate_channel_score(self, channel_info: dict) -> int:
        """Score based on channel information."""
        if not channel_info:
            return 0

        score = 0
        channel_type = channel_info.get("type", "")
        if channel_type == "mobile":
            score += 5
        elif channel_type == "web":
            score += 10

        if channel_info.get("newDevice"):
            score += 15
        if channel_info.get("rootedDevice"):
            score += 25

        return score

    def calculate_ip_risk_score(self, ip_intelligence: dict) -> int:
        """
        Calculate IP-based risk score.

        Signal                  | Condition              | Score Impact
        VPN / Proxy detected    | isVpn or isProxy       | +25
        TOR usage               | isTor = true           | +40
        High-risk country       | isHighRiskGeo = true   | +20
        IP reputation           | score > 70             | +30
        Velocity anomaly        | repeated requests      | +20
        New/unseen IP           | not in user history    | +15
        """
        if not ip_intelligence:
            return 0

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

    def calculate_purpose_risk_score(self, purpose_analysis: dict) -> int:
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
        if not purpose_analysis:
            return 0

        score = 0
        scam_indicator = purpose_analysis.get("scamIndicator", "NONE")
        category = purpose_analysis.get("purposeCategory", "UNKNOWN")
        confidence = purpose_analysis.get("confidenceScore", 0)
        has_deviation = purpose_analysis.get("historicalDeviation", False)
        has_urgency = purpose_analysis.get("urgencyDetected", False)

        if scam_indicator == "INVOICE_REDIRECTION":
            score += 50
        elif scam_indicator in ("INVESTMENT_SCAM", "ROMANCE_SCAM", "IMPERSONATION"):
            score += 30

        if category in ("INVESTMENT", "UNKNOWN"):
            score += 25

        if has_deviation:
            score += 25

        if confidence < 0.5 and category != "UNKNOWN":
            score += 10

        if has_urgency:
            score += 15

        return score

    def calculate_total_risk_score(
        self,
        amount: float = 0,
        confirmation_of_payee: dict = None,
        behavioural_signals: dict = None,
        channel_info: dict = None,
        ip_intelligence: dict = None,
        purpose_analysis: dict = None,
    ) -> Dict[str, Any]:
        """
        Calculate the total risk score combining all risk signals.

        riskScore = amountScore + copScore + behaviouralScore + channelScore + ipRiskScore + purposeRiskScore

        Returns a comprehensive risk assessment within <300ms SLA.
        """
        self.start_time = time.time()

        # Calculate individual scores
        amount_score = self.calculate_amount_score(amount)
        cop_score = self.calculate_cop_score(confirmation_of_payee or {})
        behavioural_score = self.calculate_behavioural_score(behavioural_signals or {})
        channel_score = self.calculate_channel_score(channel_info or {})
        ip_risk_score = self.calculate_ip_risk_score(ip_intelligence or {})
        purpose_risk_score = self.calculate_purpose_risk_score(purpose_analysis or {})

        # Total score (capped at 100)
        total_score = min(
            amount_score + cop_score + behavioural_score + channel_score + ip_risk_score + purpose_risk_score,
            100
        )

        # Determine risk level
        if total_score >= self.HIGH_RISK_THRESHOLD:
            risk_level = "HIGH"
        elif total_score >= self.MEDIUM_RISK_THRESHOLD:
            risk_level = "MEDIUM"
        elif total_score >= self.LOW_RISK_THRESHOLD:
            risk_level = "LOW_MEDIUM"
        else:
            risk_level = "LOW"

        # Determine decision
        decision = self._determine_decision(
            risk_level, ip_intelligence or {}, amount, purpose_analysis or {}
        )

        # Collect risk factors
        risk_factors = self._collect_risk_factors(ip_intelligence or {}, purpose_analysis or {})

        elapsed_ms = (time.time() - self.start_time) * 1000

        return {
            "totalRiskScore": total_score,
            "riskLevel": risk_level,
            "decision": decision,
            "scoreBreakdown": {
                "amountScore": amount_score,
                "copScore": cop_score,
                "behaviouralScore": behavioural_score,
                "channelScore": channel_score,
                "ipRiskScore": ip_risk_score,
                "purposeRiskScore": purpose_risk_score,
            },
            "riskFactors": risk_factors,
            "processingTimeMs": round(elapsed_ms, 2),
            "withinSla": elapsed_ms < 300,
        }

    def _determine_decision(
        self, risk_level: str, ip_intelligence: dict, amount: float, purpose_analysis: dict = None
    ) -> str:
        """Determine the action/decision based on risk assessment."""
        purpose_analysis = purpose_analysis or {}

        # TOR usage -> Block or manual review
        if ip_intelligence.get("isTor"):
            return "BLOCK"

        # Invoice redirection + high amount -> Block
        if purpose_analysis.get("scamIndicator") == "INVOICE_REDIRECTION" and amount > 5000:
            return "BLOCK"

        # Scam detected -> Step-up
        if purpose_analysis.get("scamIndicator") in ("INVESTMENT_SCAM", "ROMANCE_SCAM", "IMPERSONATION"):
            return "STEP_UP_AUTH"

        # VPN + high-value payment -> Step-up authentication
        if (ip_intelligence.get("isVpn") or ip_intelligence.get("isProxy")) and amount > 1000:
            return "STEP_UP_AUTH"

        # Purpose deviation -> Confirm
        if purpose_analysis.get("historicalDeviation") and purpose_analysis.get("purposeCategory") != "PERSONAL_TRANSFER":
            return "CONFIRM"

        # High-risk geo + velocity -> Delay
        if ip_intelligence.get("isHighRiskGeo") and ip_intelligence.get("velocityFlag"):
            return "DELAY"

        # Based on risk level
        if risk_level == "HIGH":
            return "BLOCK"
        elif risk_level == "MEDIUM":
            return "REVIEW"
        elif risk_level == "LOW_MEDIUM":
            return "MONITOR"
        else:
            return "ALLOW"

    def _collect_risk_factors(self, ip_intelligence: dict, purpose_analysis: dict = None) -> list:
        """Collect all triggered risk factors for audit/explainability."""
        purpose_analysis = purpose_analysis or {}
        factors = []

        # IP factors
        if ip_intelligence.get("isVpn"):
            factors.append("VPN_DETECTED")
        if ip_intelligence.get("isProxy"):
            factors.append("PROXY_DETECTED")
        if ip_intelligence.get("isTor"):
            factors.append("TOR_DETECTED")
        if ip_intelligence.get("isHighRiskGeo"):
            factors.append("HIGH_RISK_GEO")
        if ip_intelligence.get("ipReputationScore", 0) > 70:
            factors.append("HIGH_REPUTATION_RISK")
        if ip_intelligence.get("velocityFlag"):
            factors.append("VELOCITY_ANOMALY")
        if ip_intelligence.get("isNewIp"):
            factors.append("NEW_UNSEEN_IP")

        # Purpose factors
        scam = purpose_analysis.get("scamIndicator", "NONE")
        if scam == "INVESTMENT_SCAM":
            factors.append("INVESTMENT_SCAM_PATTERN")
        elif scam == "ROMANCE_SCAM":
            factors.append("ROMANCE_SCAM_PATTERN")
        elif scam == "IMPERSONATION":
            factors.append("IMPERSONATION_PATTERN")
        elif scam == "INVOICE_REDIRECTION":
            factors.append("INVOICE_REDIRECTION_PATTERN")

        if purpose_analysis.get("historicalDeviation"):
            factors.append("PURPOSE_DEVIATION")
        if purpose_analysis.get("purposeCategory") in ("INVESTMENT", "UNKNOWN"):
            factors.append("HIGH_RISK_CATEGORY")
        if purpose_analysis.get("urgencyDetected"):
            factors.append("URGENCY_DETECTED")

        return factors
