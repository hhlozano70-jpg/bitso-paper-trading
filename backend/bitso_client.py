from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import httpx

# Catálogo curado de 24 monedas y activos líquidos en Bitso clasificados por categoría
ASSET_CATALOG: Dict[str, Dict[str, str]] = {
    # Cripto directo en MXN
    "btc_mxn": {"name": "Bitcoin", "symbol": "BTC", "pair": "BTC/MXN", "category": "Cripto MXN", "quote": "MXN"},
    "eth_mxn": {"name": "Ethereum", "symbol": "ETH", "pair": "ETH/MXN", "category": "Cripto MXN", "quote": "MXN"},
    "sol_mxn": {"name": "Solana", "symbol": "SOL", "pair": "SOL/MXN", "category": "Cripto MXN", "quote": "MXN"},
    "xrp_mxn": {"name": "Ripple", "symbol": "XRP", "pair": "XRP/MXN", "category": "Cripto MXN", "quote": "MXN"},
    "ltc_mxn": {"name": "Litecoin", "symbol": "LTC", "pair": "LTC/MXN", "category": "Cripto MXN", "quote": "MXN"},
    "mana_mxn": {"name": "Decentraland", "symbol": "MANA", "pair": "MANA/MXN", "category": "Cripto MXN", "quote": "MXN"},
    # Materias Primas (Oro) & RWA
    "paxg_usd": {"name": "PAX Gold (Oro Físico)", "symbol": "PAXG", "pair": "PAXG/MXN*", "category": "Oro & RWA", "quote": "USD"},
    "ondo_usd": {"name": "Ondo Finance (RWA)", "symbol": "ONDO", "pair": "ONDO/MXN*", "category": "Oro & RWA", "quote": "USD"},
    # Divisas & Stablecoins (FX)
    "usd_mxn": {"name": "Dólar Estadounidense", "symbol": "USD", "pair": "USD/MXN", "category": "Divisas & FX", "quote": "MXN"},
    "usdt_mxn": {"name": "Tether USD", "symbol": "USDT", "pair": "USDT/MXN", "category": "Divisas & FX", "quote": "MXN"},
    "eur_usd": {"name": "Euro", "symbol": "EUR", "pair": "EUR/MXN*", "category": "Divisas & FX", "quote": "USD"},
    "pyusd_mxn": {"name": "PayPal USD", "symbol": "PYUSD", "pair": "PYUSD/MXN", "category": "Divisas & FX", "quote": "MXN"},
    "rlusd_mxn": {"name": "Ripple USD", "symbol": "RLUSD", "pair": "RLUSD/MXN", "category": "Divisas & FX", "quote": "MXN"},
    # Layer-1 & DeFi Globales
    "hype_usd": {"name": "Hyperliquid", "symbol": "HYPE", "pair": "HYPE/MXN*", "category": "Layer-1 & DeFi", "quote": "USD"},
    "avax_usd": {"name": "Avalanche", "symbol": "AVAX", "pair": "AVAX/MXN*", "category": "Layer-1 & DeFi", "quote": "USD"},
    "link_usd": {"name": "Chainlink", "symbol": "LINK", "pair": "LINK/MXN*", "category": "Layer-1 & DeFi", "quote": "USD"},
    "near_usd": {"name": "NEAR Protocol", "symbol": "NEAR", "pair": "NEAR/MXN*", "category": "Layer-1 & DeFi", "quote": "USD"},
    "uni_usd": {"name": "Uniswap", "symbol": "UNI", "pair": "UNI/MXN*", "category": "Layer-1 & DeFi", "quote": "USD"},
    "ada_usd": {"name": "Cardano", "symbol": "ADA", "pair": "ADA/MXN*", "category": "Layer-1 & DeFi", "quote": "USD"},
    "bch_usd": {"name": "Bitcoin Cash", "symbol": "BCH", "pair": "BCH/MXN*", "category": "Layer-1 & DeFi", "quote": "USD"},
    "xlm_usd": {"name": "Stellar", "symbol": "XLM", "pair": "XLM/MXN*", "category": "Layer-1 & DeFi", "quote": "USD"},
    "hbar_usd": {"name": "Hedera", "symbol": "HBAR", "pair": "HBAR/MXN*", "category": "Layer-1 & DeFi", "quote": "USD"},
    # Memes & Alta Volatilidad
    "doge_usd": {"name": "Dogecoin", "symbol": "DOGE", "pair": "DOGE/MXN*", "category": "Alta Volatilidad", "quote": "USD"},
    "pepe_usd": {"name": "Pepe", "symbol": "PEPE", "pair": "PEPE/MXN*", "category": "Alta Volatilidad", "quote": "USD"},
}

SUPPORTED_BOOKS: List[str] = list(ASSET_CATALOG.keys())


class BitsoClient:
    """Cliente asíncrono para consumir todos los mercados reales desde la API pública v3 de Bitso."""

    BASE_URL = "https://api.bitso.com/v3"

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            timeout=10.0,
            headers={"User-Agent": "BitsoPaperTraderMultiAsset/2.0"},
        )
        self.usd_mxn_rate: float = 18.88

    async def close(self) -> None:
        await self._client.aclose()

    def _normalize_ticker(self, raw: Dict[str, Any], fx_rate: float) -> Dict[str, Any]:
        book = raw.get("book", "")
        meta = ASSET_CATALOG.get(
            book,
            {
                "name": book.upper(),
                "symbol": book.split("_")[0].upper(),
                "pair": book.upper().replace("_", "/"),
                "category": "Otros",
                "quote": "USD" if book.endswith("_usd") else "MXN",
            },
        )
        mult = fx_rate if meta["quote"] == "USD" else 1.0

        last_native = float(raw.get("last") or 0.0)
        bid_native = float(raw.get("bid") or last_native)
        ask_native = float(raw.get("ask") or last_native)
        high_native = float(raw.get("high") or last_native)
        low_native = float(raw.get("low") or last_native)
        vwap_native = float(raw.get("vwap") or last_native)
        change_24_native = float(raw.get("change_24") or 0.0)
        volume = float(raw.get("volume") or 0.0)

        last_mxn = last_native * mult
        bid_mxn = bid_native * mult
        ask_mxn = ask_native * mult
        high_mxn = high_native * mult
        low_mxn = low_native * mult
        vwap_mxn = vwap_native * mult
        change_24_mxn = change_24_native * mult

        prev_price = last_native - change_24_native
        change_24_pct = (change_24_native / prev_price * 100.0) if prev_price > 0 else 0.0
        spread_bps = ((ask_native - bid_native) / last_native * 10000.0) if last_native > 0 else 0.0

        return {
            "book": book,
            "name": meta["name"],
            "symbol": meta["symbol"],
            "pair": meta["pair"],
            "category": meta["category"],
            "quote": meta["quote"],
            "fx_rate": round(mult, 4),
            "last_native": last_native,
            "last": round(last_mxn, 6 if last_mxn < 1 else 2),
            "bid": round(bid_mxn, 6 if bid_mxn < 1 else 2),
            "ask": round(ask_mxn, 6 if ask_mxn < 1 else 2),
            "high": round(high_mxn, 6 if high_mxn < 1 else 2),
            "low": round(low_mxn, 6 if low_mxn < 1 else 2),
            "vwap": round(vwap_mxn, 6 if vwap_mxn < 1 else 2),
            "volume": volume,
            "volume_mxn_est": round(volume * last_mxn, 2),
            "change_24": round(change_24_mxn, 6 if abs(change_24_mxn) < 1 else 2),
            "change_24_pct": round(change_24_pct, 2),
            "spread_bps": round(max(0.0, spread_bps), 2),
            "timestamp": raw.get("created_at") or datetime.now(timezone.utc).isoformat(),
        }

    async def get_all_tickers_snapshot(self) -> Dict[str, Any]:
        """
        Descarga TODOS los libros de Bitso en una sola petición HTTP (`GET /v3/ticker/`),
        devolviendo tanto los 24 activos curados (en MXN) como el diccionario crudo para arbitraje.
        """
        try:
            resp = await self._client.get("/ticker/")
            resp.raise_for_status()
            data = resp.json()
            if data.get("success") and isinstance(data.get("payload"), list):
                raw_by_book: Dict[str, Dict[str, Any]] = {item["book"]: item for item in data["payload"] if "book" in item}
                if "usd_mxn" in raw_by_book and float(raw_by_book["usd_mxn"].get("last") or 0) > 0:
                    self.usd_mxn_rate = float(raw_by_book["usd_mxn"]["last"])

                normalized: Dict[str, Dict[str, Any]] = {}
                for book in SUPPORTED_BOOKS:
                    if book in raw_by_book:
                        normalized[book] = self._normalize_ticker(raw_by_book[book], self.usd_mxn_rate)
                return {"tickers": normalized, "raw_by_book": raw_by_book, "usd_mxn_rate": self.usd_mxn_rate}
        except Exception as exc:
            print(f"[BitsoClient] Error obteniendo snapshot global de tickers: {exc}")
        return {"tickers": {}, "raw_by_book": {}, "usd_mxn_rate": self.usd_mxn_rate}

    async def get_ticker(self, book: str = "btc_mxn") -> Optional[Dict[str, Any]]:
        try:
            resp = await self._client.get("/ticker/", params={"book": book})
            resp.raise_for_status()
            data = resp.json()
            if data.get("success") and "payload" in data:
                return self._normalize_ticker(data["payload"], self.usd_mxn_rate)
        except Exception as exc:
            print(f"[BitsoClient] Error obteniendo ticker ({book}): {exc}")
        return None

    async def get_recent_trades(self, book: str = "btc_mxn", limit: int = 40) -> List[Dict[str, Any]]:
        """Obtiene transacciones reales recientes de Bitso convertidas a MXN."""
        try:
            meta = ASSET_CATALOG.get(book, {})
            mult = self.usd_mxn_rate if meta.get("quote") == "USD" else 1.0
            resp = await self._client.get("/trades/", params={"book": book, "limit": limit})
            resp.raise_for_status()
            data = resp.json()
            if data.get("success") and "payload" in data:
                trades = []
                for t in reversed(data["payload"]):
                    px = float(t.get("price", 0)) * mult
                    trades.append({
                        "tid": t.get("tid"),
                        "price": round(px, 6 if px < 1 else 2),
                        "amount": float(t.get("amount", 0)),
                        "maker_side": t.get("maker_side", "buy"),
                        "timestamp": t.get("created_at"),
                    })
                return trades
        except Exception as exc:
            print(f"[BitsoClient] Error obteniendo trades ({book}): {exc}")
        return []

    async def get_order_book(self, book: str = "btc_mxn", top_n: int = 10) -> Dict[str, Any]:
        """Obtiene el libro de órdenes real (bids y asks) convertido a MXN y calcula el desbalance."""
        try:
            meta = ASSET_CATALOG.get(book, {})
            mult = self.usd_mxn_rate if meta.get("quote") == "USD" else 1.0
            resp = await self._client.get("/order_book/", params={"book": book})
            resp.raise_for_status()
            data = resp.json()
            if data.get("success") and "payload" in data:
                payload = data["payload"]
                bids = [
                    {
                        "price": round(float(b["price"]) * mult, 6 if float(b["price"]) * mult < 1 else 2),
                        "amount": float(b["amount"]),
                    }
                    for b in payload.get("bids", [])[:top_n]
                ]
                asks = [
                    {
                        "price": round(float(a["price"]) * mult, 6 if float(a["price"]) * mult < 1 else 2),
                        "amount": float(a["amount"]),
                    }
                    for a in payload.get("asks", [])[:top_n]
                ]
                bid_vol = sum(b["amount"] for b in bids)
                ask_vol = sum(a["amount"] for a in asks)
                total_vol = bid_vol + ask_vol
                imbalance = (bid_vol / total_vol) if total_vol > 0 else 0.5
                return {
                    "bids": bids,
                    "asks": asks,
                    "bid_volume": round(bid_vol, 6),
                    "ask_volume": round(ask_vol, 6),
                    "imbalance": round(imbalance, 4),
                }
        except Exception as exc:
            print(f"[BitsoClient] Error obteniendo order_book ({book}): {exc}")
        return {"bids": [], "asks": [], "bid_volume": 0.0, "ask_volume": 0.0, "imbalance": 0.5}
