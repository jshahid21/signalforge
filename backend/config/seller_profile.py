"""Seller profile read/write helpers."""
from __future__ import annotations

from .loader import SellerProfileConfig, load_config, save_config


def get_seller_profile() -> SellerProfileConfig:
    """Return the current seller profile from config."""
    return load_config().seller_profile


def update_seller_profile(
    company_name: str,
    portfolio_summary: str,
    portfolio_items: list[str],
) -> SellerProfileConfig:
    """Update and persist the seller profile."""
    config = load_config()
    config.seller_profile = SellerProfileConfig(
        company_name=company_name,
        portfolio_summary=portfolio_summary,
        portfolio_items=portfolio_items,
    )
    save_config(config)
    return config.seller_profile
