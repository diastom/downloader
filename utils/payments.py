import asyncio
import logging
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)

BITPIN_MARKETS_URL = "https://api.bitpin.ir/v1/mkt/markets/"
NOBITEX_STATS_URL = "https://api.nobitex.ir/market/stats"
NOWPAYMENTS_API_BASE = "https://sandbox.nowpayments.io/v1/invoice"


async def _async_request(method: str, url: str, **kwargs) -> requests.Response:
    timeout = kwargs.pop("timeout", 15)
    return await asyncio.to_thread(requests.request, method, url, timeout=timeout, **kwargs)


async def fetch_nobitex_price(symbol: str = "trx", currency: str = "rls") -> Optional[float]:
    params = {"srcCurrency": symbol, "dstCurrency": currency}
    try:
        response = await _async_request("get", NOBITEX_STATS_URL, params=params)
        response.raise_for_status()
        data = response.json()
        market_key = f"{symbol}-{currency}"
        stats = data.get("stats", {}).get(market_key)
        if not stats:
            return None
        latest_price = stats.get("latest")
        if not latest_price:
            return None
        price = float(latest_price)
        if currency.lower() == "rls":
            price /= 10  # Convert from Rial to Toman
        return price
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to fetch Nobitex price: %s", exc)
        return None


async def fetch_bitpin_price(symbol: str = "trx", currency: str = "irt") -> Optional[float]:
    try:
        response = await _async_request("get", BITPIN_MARKETS_URL)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to fetch Bitpin price: %s", exc)
        return None

    for market in payload.get("results", []):
        base = market.get("currency1", {}).get("code", "").lower()
        quote = market.get("currency2", {}).get("code", "").lower()
        if base == symbol.lower() and quote == currency.lower():
            try:
                return float(market.get("price"))
            except (TypeError, ValueError):
                return None
    return None


async def convert_toman_to_crypto(amount_toman: int, symbol: str = "trx") -> tuple[float, float]:
    if amount_toman <= 0:
        raise ValueError("Amount must be greater than zero")

    price = await get_live_price(symbol=symbol)

    crypto_amount = round(amount_toman / price, 6)
    return price, crypto_amount


async def get_live_price(symbol: str = "trx") -> float:
    price = await fetch_nobitex_price(symbol=symbol)
    if price is None:
        price = await fetch_bitpin_price(symbol=symbol)
    if price is None:
        raise RuntimeError("Unable to fetch live price data for the requested currency")
    return price


async def create_nowpayments_invoice(
    *,
    api_key: str,
    amount: float,
    currency: str,
    order_id: str,
    description: str,
) -> dict[str, Any]:
    headers = {"x-api-key": api_key, "Content-Type": "application/json"}
    payload = {
        "price_amount": amount,
        "price_currency": currency,
        "pay_currency": currency,
        "order_id": order_id,
        "order_description": description,
    }
    response = await _async_request("post", f"{NOWPAYMENTS_API_BASE}/invoice", json=payload, headers=headers)
    response.raise_for_status()
    return response.json()


async def get_nowpayments_invoice_status(*, api_key: str, invoice_id: str) -> dict[str, Any]:
    headers = {"x-api-key": api_key}
    response = await _async_request("get", f"{NOWPAYMENTS_API_BASE}/invoice/{invoice_id}", headers=headers)
    response.raise_for_status()
    return response.json()
