"""Utility helpers for subscription sales, pricing, and blockchain verification."""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass
from decimal import Decimal, ROUND_UP
from typing import Dict, Optional
from urllib.parse import parse_qs, unquote, urlparse

import aiohttp

from utils import database

BITPIN_MARKETS_URL = "https://api.bitpin.org/v1/mkt/markets/"
BITPIN_CACHE_TTL = 120  # seconds


@dataclass(frozen=True)
class CurrencyMeta:
    code: str
    display_name: str
    bitpin_code: str
    decimals: int
    explorer_base: str
    instructions: str


CURRENCIES: Dict[str, CurrencyMeta] = {
    "TRX": CurrencyMeta(
        code="TRX",
        display_name="ترون (TRX)",
        bitpin_code="TRX_IRT",
        decimals=6,
        explorer_base="https://tronscan.org/#/transaction/",
        instructions="لطفاً پس از پرداخت لینک تراکنش از سایت Tronscan را ارسال کنید.",
    ),
    "USDT_TRON": CurrencyMeta(
        code="USDT_TRON",
        display_name="تتر (شبکه ترون)",
        bitpin_code="USDT_IRT",
        decimals=6,
        explorer_base="https://tronscan.org/#/transaction/",
        instructions="پرداخت‌های تتر (TRC20) در Tronscan قابل پیگیری هستند.",
    ),
    "TON": CurrencyMeta(
        code="TON",
        display_name="تون‌کوین (TON)",
        bitpin_code="TON_IRT",
        decimals=9,
        explorer_base="https://tonviewer.com/transaction/",
        instructions="برای بررسی تراکنش از لینک tonviewer.com/transaction/... استفاده کنید.",
    ),
    "DOGE": CurrencyMeta(
        code="DOGE",
        display_name="دوج‌کوین (DOGE)",
        bitpin_code="DOGE_IRT",
        decimals=8,
        explorer_base="https://blockchair.com/dogecoin/transaction/",
        instructions="می‌توانید لینک تراکنش خود را از Blockchair یا Dogechain ارسال کنید.",
    ),
}


class PricingCache:
    __slots__ = ("data", "fetched_at", "lock")

    def __init__(self) -> None:
        self.data: Dict[str, Decimal] | None = None
        self.fetched_at: float = 0.0
        self.lock = asyncio.Lock()

    async def get_prices(self) -> Dict[str, Decimal]:
        async with self.lock:
            now = time.monotonic()
            if self.data is not None and (now - self.fetched_at) < BITPIN_CACHE_TTL:
                return self.data

            async with aiohttp.ClientSession() as session:
                async with session.get(BITPIN_MARKETS_URL, timeout=15) as response:
                    response.raise_for_status()
                    payload = await response.json()

            market_prices: Dict[str, Decimal] = {}
            for entry in payload.get("results", []):
                code = entry.get("code")
                price = entry.get("price")
                if not code or price is None:
                    continue
                try:
                    market_prices[code] = Decimal(str(price))
                except Exception:
                    continue

            self.data = market_prices
            self.fetched_at = now
            return market_prices


_pricing_cache = PricingCache()


async def get_currency_price_toman(currency_code: str) -> Decimal:
    currency = CURRENCIES.get(currency_code)
    if not currency:
        raise ValueError("Unsupported currency code")

    prices = await _pricing_cache.get_prices()
    price = prices.get(currency.bitpin_code)
    if price is None:
        raise RuntimeError(f"قیمت لحظه‌ای برای {currency.display_name} در دسترس نیست.")
    return price


def calculate_crypto_amount(price_toman: Decimal, toman_amount: int, decimals: int) -> Decimal:
    if price_toman <= 0:
        raise ValueError("قیمت معتبر نیست")
    raw_amount = Decimal(toman_amount) / price_toman
    quant = Decimal("1") / (Decimal(10) ** decimals)
    return raw_amount.quantize(quant, rounding=ROUND_UP)


@dataclass
class VerificationResult:
    success: bool
    amount: Optional[Decimal]
    tx_hash: Optional[str]
    message: str


async def verify_transaction(
    currency_code: str,
    wallet_address: str,
    link: str,
) -> VerificationResult:
    currency = CURRENCIES.get(currency_code)
    if not currency:
        return VerificationResult(False, None, None, "ارز انتخابی پشتیبانی نمی‌شود.")

    try:
        if currency_code in {"TRX", "USDT_TRON"}:
            tx_hash = _extract_tron_transaction_hash(link)
            if not tx_hash:
                return VerificationResult(False, None, None, "لینک تراکنش ترون نامعتبر است.")
            token_filter = "USDT" if currency_code == "USDT_TRON" else None
            amount = await _verify_tron_transaction(tx_hash, wallet_address, token_filter)
            if amount is None:
                return VerificationResult(False, None, tx_hash, "واریزی معتبر به این ولت یافت نشد یا تراکنش تایید نشده است.")
            return VerificationResult(True, amount, tx_hash, "تراکنش با موفقیت تایید شد.")

        if currency_code == "TON":
            parsed = _extract_ton_parameters(link)
            if not parsed:
                return VerificationResult(False, None, None, "لینک تراکنش تون‌کوین نامعتبر است.")
            amount = await _verify_ton_transaction(wallet_address, parsed["lt"], parsed["hash"])
            if amount is None:
                return VerificationResult(False, None, parsed["hash"], "تراکنش یافت نشد یا هنوز تایید نشده است.")
            return VerificationResult(True, amount, parsed["hash"], "تراکنش با موفقیت تایید شد.")

        if currency_code == "DOGE":
            tx_hash = _extract_hex_hash(link)
            if not tx_hash:
                return VerificationResult(False, None, None, "لینک تراکنش دوج‌کوین نامعتبر است.")
            amount = await _verify_doge_transaction(tx_hash, wallet_address)
            if amount is None:
                return VerificationResult(False, None, tx_hash, "تراکنشی با این آدرس یافت نشد یا تایید نشده است.")
            return VerificationResult(True, amount, tx_hash, "تراکنش با موفقیت تایید شد.")
    except aiohttp.ClientError:
        return VerificationResult(False, None, None, "عدم دسترسی به سرویس بررسی تراکنش. لطفاً بعداً تلاش کنید.")
    except Exception as exc:
        return VerificationResult(False, None, None, f"خطای غیرمنتظره در بررسی تراکنش: {exc}")

    return VerificationResult(False, None, None, "امکان بررسی این ارز وجود ندارد.")


def _extract_tron_transaction_hash(link: str) -> Optional[str]:
    parsed = urlparse(link)
    candidates = [parsed.path or ""]
    if parsed.fragment:
        candidates.append(parsed.fragment)
    pattern = re.compile(r"(?:transaction|tx)/([0-9a-fA-F]{64})")
    for candidate in candidates:
        match = pattern.search(candidate)
        if match:
            return match.group(1)
    query_hash = parse_qs(parsed.query).get("hash")
    if query_hash:
        value = query_hash[0]
        if re.fullmatch(r"[0-9a-fA-F]{64}", value):
            return value
    return None


def _extract_hex_hash(link: str) -> Optional[str]:
    parsed = urlparse(link)
    candidates = [parsed.path or "", parsed.fragment or ""]
    pattern = re.compile(r"([0-9a-fA-F]{64})")
    for candidate in candidates:
        match = pattern.search(candidate)
        if match:
            return match.group(1)
    query_hash = parse_qs(parsed.query).get("hash")
    if query_hash:
        value = query_hash[0]
        if re.fullmatch(r"[0-9a-fA-F]{64}", value):
            return value
    return None


def _extract_ton_parameters(link: str) -> Optional[Dict[str, str]]:
    parsed = urlparse(link)
    path = unquote(parsed.path or "")
    fragment = unquote(parsed.fragment or "")
    combined = f"{path} {fragment}".strip()
    pattern = re.compile(r"transaction/([0-9]+):([A-Za-z0-9+/=]+)")
    match = pattern.search(combined)
    if match:
        return {"lt": match.group(1), "hash": match.group(2)}

    query = parse_qs(parsed.query)
    if "lt" in query and "hash" in query:
        return {"lt": query["lt"][0], "hash": query["hash"][0]}
    return None


async def _verify_tron_transaction(
    tx_hash: str,
    wallet_address: str,
    token_symbol: Optional[str],
) -> Optional[Decimal]:
    url = f"https://apilist.tronscanapi.com/api/transaction-info?hash={tx_hash}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=15) as response:
            if response.status != 200:
                return None
            payload = await response.json()

    if payload.get("contractRet") != "SUCCESS":
        return None

    if token_symbol:
        transfers = payload.get("trc20TransferInfo") or payload.get("tokenTransferInfo")
        if not transfers:
            return None
        if isinstance(transfers, dict):
            transfers = [transfers]
        total_amount = Decimal("0")
        for transfer in transfers:
            to_address = transfer.get("to_address") or transfer.get("toAddress")
            if not to_address or to_address.strip() != wallet_address.strip():
                continue
            symbol = transfer.get("symbol") or transfer.get("tokenAbbr")
            if symbol and symbol.upper() != token_symbol.upper():
                continue
            amount_raw = transfer.get("amount_str") or transfer.get("amount") or transfer.get("quant")
            decimals = transfer.get("decimals") or transfer.get("tokenDecimal") or 6
            if amount_raw is None:
                continue
            total_amount += Decimal(str(amount_raw)) / (Decimal(10) ** int(decimals))
        return total_amount if total_amount > 0 else None

    contract_data = payload.get("contractData") or {}
    to_address = contract_data.get("to_address") or contract_data.get("toAddress") or payload.get("toAddress")
    if not to_address or to_address.strip() != wallet_address.strip():
        return None
    amount_raw = contract_data.get("amount")
    if amount_raw is None:
        return None
    return Decimal(amount_raw) / Decimal(1_000_000)


async def _verify_ton_transaction(
    wallet_address: str,
    lt: str,
    tx_hash: str,
) -> Optional[Decimal]:
    url = f"https://toncenter.com/api/v2/getTransactions?address={wallet_address}&limit=50"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=15) as response:
            if response.status != 200:
                return None
            payload = await response.json()

    if not payload.get("ok"):
        return None
    for tx in payload.get("result", []):
        tx_id = tx.get("transaction_id") or {}
        if tx_id.get("lt") != lt or tx_id.get("hash") != tx_hash:
            continue
        in_msg = tx.get("in_msg") or {}
        destination = in_msg.get("destination")
        if destination and destination.strip() != wallet_address.strip():
            continue
        value = in_msg.get("value")
        if value is None:
            continue
        try:
            amount = Decimal(str(value)) / Decimal(1_000_000_000)
        except Exception:
            continue
        return amount if amount > 0 else None
    return None


async def _verify_doge_transaction(tx_hash: str, wallet_address: str) -> Optional[Decimal]:
    url = f"https://api.blockchair.com/dogecoin/dashboards/transaction/{tx_hash}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=15) as response:
            if response.status != 200:
                return None
            payload = await response.json()

    data = payload.get("data") or {}
    if not data:
        return None
    entry = next(iter(data.values()), None)
    if not entry:
        return None
    if entry.get("transaction", {}).get("time") is None:
        return None
    outputs = entry.get("outputs") or []
    total_value = Decimal("0")
    for output in outputs:
        if output.get("recipient") != wallet_address:
            continue
        value = output.get("value")
        if value is None:
            continue
        total_value += Decimal(str(value)) / Decimal(100_000_000)
    return total_value if total_value > 0 else None


async def list_active_currencies_with_wallets(session) -> Dict[str, CurrencyMeta]:
    wallets = await database.get_wallet_settings_map(session)
    available: Dict[str, CurrencyMeta] = {}
    for code, meta in CURRENCIES.items():
        if code in wallets:
            available[code] = meta
    return available
