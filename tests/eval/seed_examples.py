"""Seed dataset examples for LangSmith evaluation (spec §3.4).

Each example contains only inputs: {company_name, signal_summary, persona_title, role_type}.
No draft content is stored here — drafts are loaded at eval time from local JSON files.

These examples cover diverse signal types and persona role types to ensure
breadth of quality measurement across the signalforge-draft-quality dataset.
"""
from __future__ import annotations

SEED_EXAMPLES: list[dict] = [
    {
        "company_name": "DataStream Inc",
        "signal_summary": (
            "DataStream Inc posted 12 new senior ML engineering roles in the past 30 days, "
            "with job descriptions referencing real-time feature stores and model serving infrastructure."
        ),
        "persona_title": "VP of Engineering",
        "role_type": "technical_buyer",
    },
    {
        "company_name": "NovaPay",
        "signal_summary": (
            "NovaPay announced a $45M Series B funding round to expand their embedded payments "
            "platform into Europe, with a stated focus on compliance infrastructure."
        ),
        "persona_title": "CFO",
        "role_type": "economic_buyer",
    },
    {
        "company_name": "CloudBridge Labs",
        "signal_summary": (
            "CloudBridge Labs published a technical blog post describing their migration from "
            "on-premises Hadoop to a cloud-native lakehouse architecture using Apache Iceberg."
        ),
        "persona_title": "Senior Data Engineer",
        "role_type": "influencer",
    },
    {
        "company_name": "RetailForce",
        "signal_summary": (
            "RetailForce is hiring a Director of Platform Engineering and two Staff DevOps "
            "engineers focused on Kubernetes fleet management and multi-cloud cost optimization."
        ),
        "persona_title": "CTO",
        "role_type": "economic_buyer",
    },
    {
        "company_name": "HealthTrack Systems",
        "signal_summary": (
            "HealthTrack Systems launched a new product line for clinical workflow automation, "
            "announcing SOC 2 Type II certification and HIPAA compliance for their data pipeline."
        ),
        "persona_title": "Head of Infrastructure",
        "role_type": "technical_buyer",
    },
]
