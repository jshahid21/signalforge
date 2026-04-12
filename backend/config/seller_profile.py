"""Seller profile read/write helpers."""
from __future__ import annotations

from typing import Optional

from .loader import SellerIntelligence, SellerProfileConfig, load_config, save_config


def get_seller_profile() -> SellerProfileConfig:
    """Return the current seller profile from config."""
    return load_config().seller_profile


def update_seller_profile(
    company_name: str,
    portfolio_summary: str,
    portfolio_items: list[str],
    website_url: Optional[str] = None,
    seller_intelligence: Optional[SellerIntelligence] = None,
) -> SellerProfileConfig:
    """Update and persist the seller profile."""
    config = load_config()
    config.seller_profile.company_name = company_name
    config.seller_profile.portfolio_summary = portfolio_summary
    config.seller_profile.portfolio_items = portfolio_items
    if website_url is not None:
        config.seller_profile.website_url = website_url
    if seller_intelligence is not None:
        config.seller_profile.seller_intelligence = seller_intelligence
    save_config(config)
    return config.seller_profile
