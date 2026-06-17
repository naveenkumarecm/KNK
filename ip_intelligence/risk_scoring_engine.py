"""
Risk Scoring Engine with IP Intelligence Integration.

Updated formula:
    riskScore = amountScore + copScore + behaviouralScore + channelScore + ipRiskScore

This module integrates IP-based scoring into the overall fraud risk decisioning
while maintaining the <300ms SLA requirement.
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

    def calculate_total_risk_score(
        self,
        amount: float = 0,
        confirmation_of_payee: dict = None,
        behavioural_signals: dict = None,
        channel_info: dict = None,
        ip_intelligence: dict = None,
    ) -> Dict[str, Any]:
        """
        Calculate the total risk score combining all risk signals.

        riskScore = amountScore + copScore + behaviouralScore + channelScore + ipRiskScore

        Returns a comprehensive risk assessment within <300ms SLA.
        """
        self.start_time = time.time()

        # Calculate individual scores
        amount_score = self.calculate_amount_score(amount)
        cop_score = self.calculate_cop_score(confirmation_of_payee or {})
        behavioural_score = self.calculate_behavioural_score(behavioural_signals or {})
        channel_score = self.calculate_channel_score(channel_info or {})
        ip_risk_score = self.calculate_ip_risk_score(ip_intelligence or {})

        # Total score (capped at 100)
        total_score = min(
            amount_score + cop_score + behavioural_score + channel_score + ip_risk_score,
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
            risk_level, ip_intelligence or {}, amount
        )

        # Collect risk factors
        risk_factors = self._collect_risk_factors(ip_intelligence or {})

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
            },
            "riskFactors": risk_factors,
            "processingTimeMs": round(elapsed_ms, 2),
            "withinSla": elapsed_ms < 300,
        }

    def _determine_decision(
        self, risk_level: str, ip_intelligence: dict, amount: float
    ) -> str:
        """Determine the action/decision based on risk assessment."""
        # TOR usage -> Block or manual review
        if ip_intelligence.get("isTor"):
            return "BLOCK"

        # VPN + high-value payment -> Step-up authentication
        if (ip_intelligence.get("isVpn") or ip_intelligence.get("isProxy")) and amount > 1000:
            return "STEP_UP_AUTH"

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

    def _collect_risk_factors(self, ip_intelligence: dict) -> list:
        """Collect all triggered risk factors for audit/explainability."""
        factors = []

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

        return factors
