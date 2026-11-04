import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
import httpx

# Catálogo Institucional de Activos Estables: Divisas / Monedas Fiat, Oro y Petróleo.
# Criptomonedas eliminadas al 100% para máxima estabilidad patrimonial.
ASSET_CATALOG: Dict[str, Dict[str, str]] = {
    # 1. Divisas & Monedas (Forex / Fiat institucional contra Peso Mexicano MXN)
    "usd_mxn": {"name": "Dólar Estadounidense", "symbol": "USD", "pair": "USD/MXN", "category": "Divisas & Monedas", "quote": "MXN", "source": "bitso"},
    "eur_mxn": {"name": "Euro", "symbol": "EUR", "pair": "EUR/MXN*", "category": "Divisas & Monedas", "quote": "MXN", "source": "yahoo", "yf_ticker": "EURMXN=X"},
    "gbp_mxn": {"name": "Libra Esterlina", "symbol": "GBP", "pair": "GBP/MXN*", "category": "Divisas & Monedas", "quote": "MXN", "source": "yahoo", "yf_ticker": "GBPMXN=X"},
    "cad_mxn": {"name": "Dólar Canadiense", "symbol": "CAD", "pair": "CAD/MXN*", "category": "Divisas & Monedas", "quote": "MXN", "source": "yahoo", "yf_ticker": "CADMXN=X"},
    "chf_mxn": {"name": "Franco Suizo", "symbol": "CHF", "pair": "CHF/MXN*", "category": "Divisas & Monedas", "quote": "MXN", "source": "yahoo", "yf_ticker": "CHFMXN=X"},
    "jpy_mxn": {"name": "Yen Japonés", "symbol": "JPY", "pair": "JPY/MXN*", "category": "Divisas & Monedas", "quote": "MXN", "source": "yahoo", "yf_ticker": "JPYMXN=X"},

    # 2. Oro & Metales de Reserva Refugio (COMEX / Bóvedas de Oro Físico)
    "gc_fut": {"name": "Futuros Oro COMEX", "symbol": "ORO", "pair": "ORO/MXN*", "category": "Oro & Metales Refugio", "quote": "USD", "source": "yahoo", "yf_ticker": "GC=F"},
    "paxg_usd": {"name": "PAX Gold (Oro Físico Bóveda)", "symbol": "PAXG", "pair": "PAXG/MXN*", "category": "Oro & Metales Refugio", "quote": "USD", "source": "bitso"},
    "si_fut": {"name": "Futuros Plata COMEX", "symbol": "PLATA", "pair": "PLATA/MXN*", "category": "Oro & Metales Refugio", "quote": "USD", "source": "yahoo", "yf_ticker": "SI=F"},

    # 3. Petróleo & Energía Global (NYMEX / ICE)
    "cl_fut": {"name": "Futuros Petróleo WTI", "symbol": "PETROLEO-WTI", "pair": "WTI/MXN*", "category": "Petróleo & Energía", "quote": "USD", "source": "yahoo", "yf_ticker": "CL=F"},
    "brent_fut": {"name": "Futuros Petróleo Brent", "symbol": "PETROLEO-BRENT", "pair": "BRENT/MXN*", "category": "Petróleo & Energía", "quote": "USD", "source": "yahoo", "yf_ticker": "BZ=F"},
    "ng_fut": {"name": "Futuros Gas Natural", "symbol": "GAS-NATURAL", "pair": "NGAS/MXN*", "category": "Petróleo & Energía", "quote": "USD", "source": "yahoo", "yf_ticker": "NG=F"},
}

SUPPORTED_BOOKS: List[str] = list(ASSET_CATALOG.keys())
BITSO_BOOKS: List[str] = [b for b, m in ASSET_CATALOG.items() if m.get("source") == "bitso"]
YAHOO_BOOKS: List[str] = [b for b, m in ASSET_CATALOG.items() if m.get("source") == "yahoo"]


class BitsoClient:
    """
    Cliente híbrido asíncrono que consume en tiempo real:
      1) Los mercados de Cripto, Oro (PAXG), RWA y Divisas desde Bitso API v3
      2) Las Acciones (Wall Street) y Futuros (CME/NYMEX/COMEX) desde Yahoo Finance API v8
    Convirtiendo todas las cotizaciones en vivo a Pesos Mexicanos (MXN).
    """

    BASE_URL = "https://api.bitso.com/v3"
    YF_BASE_URL = "https://query1.finance.yahoo.com/v8/finance/chart"

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            timeout=9.0,
            headers={"User-Agent": "BitsoPaperTraderMultiAsset/3.0"},
        )
        self._yf_client = httpx.AsyncClient(
            timeout=8.0,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        )
        self.usd_mxn_rate: float = 18.85
        self._yf_cache: Dict[str, Dict[str, Any]] = {}
        self._yf_series_cache: Dict[str, List[Tuple[str, float]]] = {}
        self._candles_cache: Dict[str, Dict[str, Any]] = {}
        self._last_yf_fetch_ts: float = 0.0

    async def close(self) -> None:
        await self._client.aclose()
        await self._yf_client.aclose()

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
                "source": "bitso",
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
            "source": meta.get("source", "bitso"),
            "fx_rate": round(mult, 4),
            "last_native": round(last_native, 6 if last_native < 1 else 2),
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
            "spread_bps": round(max(0.2, spread_bps), 2),
            "timestamp": raw.get("created_at") or datetime.now(timezone.utc).isoformat(),
        }

    async def _fetch_single_yahoo_asset(self, book: str) -> Optional[Dict[str, Any]]:
        meta = ASSET_CATALOG.get(book)
        if not meta or "yf_ticker" not in meta:
            return None
        yf_sym = meta["yf_ticker"]
        try:
            resp = await self._yf_client.get(
                f"{self.YF_BASE_URL}/{yf_sym}",
                params={"interval": "2m", "range": "1d"},
            )
            resp.raise_for_status()
            data = resp.json()
            res_list = data.get("chart", {}).get("result", [])
            if not res_list:
                return None
            res0 = res_list[0]
            ymeta = res0.get("meta", {})
            timestamps = res0.get("timestamp", []) or []
            quotes = (res0.get("indicators", {}).get("quote") or [{}])[0]
            closes = quotes.get("close", []) or []
            volumes = quotes.get("volume", []) or []

            valid_pts: List[Tuple[int, float, float]] = []
            for ts, c, v in zip(timestamps, closes, volumes):
                if c is not None and float(c) > 0:
                    valid_pts.append((int(ts), float(c), float(v or 0.0)))

            last_usd = float(ymeta.get("regularMarketPrice") or (valid_pts[-1][1] if valid_pts else 0.0))
            if last_usd <= 0:
                return None

            prev_close = float(ymeta.get("chartPreviousClose") or ymeta.get("previousClose") or last_usd)
            high_usd = float(ymeta.get("regularMarketDayHigh") or max((p[1] for p in valid_pts), default=last_usd))
            low_usd = float(ymeta.get("regularMarketDayLow") or min((p[1] for p in valid_pts), default=last_usd))

            # Calcular VWAP real del día con los bloques de 2m
            total_pv = sum(p[1] * max(1.0, p[2]) for p in valid_pts)
            total_v = sum(max(1.0, p[2]) for p in valid_pts)
            vwap_usd = (total_pv / total_v) if total_v > 0 else ((high_usd + low_usd + last_usd) / 3.0)

            # Simular spread institucional realista para Acciones (2.5 bps) y Futuros CME (1.8 bps)
            sim_spread_bps = 1.8 if meta["category"] == "Futuros" else 2.5
            half_spread = last_usd * (sim_spread_bps / 20000.0)
            bid_usd = last_usd - half_spread
            ask_usd = last_usd + half_spread

            fx = self.usd_mxn_rate
            # Guardar serie histórica en MXN para poblar el gráfico inmediatamente
            series_mxn: List[Tuple[str, float]] = []
            for ts, c_usd, _ in valid_pts[-35:]:
                lbl = datetime.fromtimestamp(ts).strftime("%H:%M:%S")
                series_mxn.append((lbl, round(c_usd * fx, 2)))
            if series_mxn:
                self._yf_series_cache[book] = series_mxn

            raw_equiv = {
                "book": book,
                "last": last_usd,
                "bid": bid_usd,
                "ask": ask_usd,
                "high": max(high_usd, last_usd),
                "low": min(low_usd, last_usd),
                "vwap": vwap_usd,
                "volume": float(ymeta.get("regularMarketVolume") or total_v),
                "change_24": last_usd - prev_close,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            tk = self._normalize_ticker(raw_equiv, fx)
            self._yf_cache[book] = tk
            return tk
        except Exception as exc:
            # Si hay caché previo, actualizarlo con el tipo de cambio actual
            if book in self._yf_cache:
                return self._yf_cache[book]
            print(f"[BitsoClient] Error obteniendo activo Yahoo ({book}): {exc}")
            return None

    async def refresh_yahoo_assets(self, force: bool = False) -> Dict[str, Dict[str, Any]]:
        now_ts = asyncio.get_event_loop().time()
        # Consultar Yahoo Finance cada 6 segundos (o si force=True) para velocidad óptima sin rate-limit
        if not force and self._yf_cache and (now_ts - self._last_yf_fetch_ts) < 6.0:
            return self._yf_cache

        self._last_yf_fetch_ts = now_ts
        results = await asyncio.gather(*(self._fetch_single_yahoo_asset(b) for b in YAHOO_BOOKS), return_exceptions=True)
        for b, res in zip(YAHOO_BOOKS, results):
            if isinstance(res, dict) and res is not None:
                self._yf_cache[b] = res
        return self._yf_cache

    async def get_all_tickers_snapshot(self) -> Dict[str, Any]:
        """
        Descarga en paralelo todos los mercados de Bitso + Acciones de Wall Street + Futuros CME.
        """
        normalized: Dict[str, Dict[str, Any]] = {}
        raw_by_book: Dict[str, Dict[str, Any]] = {}
        try:
            resp = await self._client.get("/ticker/")
            resp.raise_for_status()
            data = resp.json()
            if data.get("success") and isinstance(data.get("payload"), list):
                raw_by_book = {item["book"]: item for item in data["payload"] if "book" in item}
                if "usd_mxn" in raw_by_book and float(raw_by_book["usd_mxn"].get("last") or 0) > 0:
                    self.usd_mxn_rate = float(raw_by_book["usd_mxn"]["last"])

                for book in BITSO_BOOKS:
                    if book in raw_by_book:
                        normalized[book] = self._normalize_ticker(raw_by_book[book], self.usd_mxn_rate)
        except Exception as exc:
            print(f"[BitsoClient] Error obteniendo snapshot de Bitso: {exc}")

        yf_tickers = await self.refresh_yahoo_assets(force=not bool(self._yf_cache))
        normalized.update(yf_tickers)

        return {
            "tickers": normalized,
            "raw_by_book": raw_by_book,
            "usd_mxn_rate": self.usd_mxn_rate,
            "yf_series": self._yf_series_cache,
        }

    async def get_ticker(self, book: str = "btc_mxn") -> Optional[Dict[str, Any]]:
        meta = ASSET_CATALOG.get(book, {})
        if meta.get("source") == "yahoo":
            return await self._fetch_single_yahoo_asset(book)
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
        meta = ASSET_CATALOG.get(book, {})
        if meta.get("source") == "yahoo":
            if book not in self._yf_series_cache:
                await self._fetch_single_yahoo_asset(book)
            pts = self._yf_series_cache.get(book, [])
            return [
                {"tid": idx, "price": px, "amount": 1.0, "maker_side": "buy", "timestamp": lbl}
                for idx, (lbl, px) in enumerate(pts[-limit:])
            ]

        try:
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

    async def get_order_book(self, book: str = "usd_mxn", top_n: int = 10) -> Dict[str, Any]:
        meta = ASSET_CATALOG.get(book, {})
        if meta.get("source") == "yahoo":
            tk = self._yf_cache.get(book) or await self._fetch_single_yahoo_asset(book)
            if not tk:
                return {"bids": [], "asks": [], "bid_volume": 0.0, "ask_volume": 0.0, "imbalance": 0.5}
            bid0 = float(tk["bid"])
            ask0 = float(tk["ask"])
            dec = 4 if bid0 < 1 else 2
            step = max(0.0001 if bid0 < 1 else 0.01, bid0 * 0.0002)
            bids = [{"price": round(bid0 - i * step, dec), "amount": round(12.0 - i * 0.8, 2)} for i in range(top_n)]
            asks = [{"price": round(ask0 + i * step, dec), "amount": round(10.5 - i * 0.7, 2)} for i in range(top_n)]
            return {"bids": bids, "asks": asks, "bid_volume": 84.0, "ask_volume": 73.5, "imbalance": 0.533}

        try:
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

    async def get_multi_timeframe_ohlc(self, book: str = "usd_mxn") -> Dict[str, List[Dict[str, float]]]:
        """
        Obtiene series de velas OHLC en dos temporalidades nativas: H1 (1 hora) y M15 (15 minutos).
        Convierte automáticamente a Pesos Mexicanos (MXN).
        Incluye caché en memoria de 45 segundos para alto rendimiento sin rate-limiting.
        """
        import time
        now = time.time()
        cached = self._candles_cache.get(book)
        if cached and (now - cached.get("ts", 0)) < 45.0:
            return {"h1": cached.get("h1", []), "m15": cached.get("m15", [])}

        meta = ASSET_CATALOG.get(book, {})
        mult = self.usd_mxn_rate if meta.get("quote") == "USD" else 1.0

        h1_candles: List[Dict[str, float]] = []
        m15_candles: List[Dict[str, float]] = []

        if meta.get("source") == "yahoo":
            yf_sym = meta.get("yf_ticker", "")
            if yf_sym:
                try:
                    # 1. H1 de Yahoo (range=3mo, interval=60m para calcular EMA 200)
                    resp_h1 = await self._yf_client.get(
                        f"{self.YF_BASE_URL}/{yf_sym}",
                        params={"interval": "60m", "range": "3mo"},
                    )
                    if resp_h1.status_code == 200:
                        d1 = resp_h1.json()
                        res_list = d1.get("chart", {}).get("result", [])
                        if res_list:
                            r0 = res_list[0]
                            ts_list = r0.get("timestamp", []) or []
                            q = (r0.get("indicators", {}).get("quote") or [{}])[0]
                            op = q.get("open", []) or []
                            hi = q.get("high", []) or []
                            lo = q.get("low", []) or []
                            cl = q.get("close", []) or []
                            vo = q.get("volume", []) or []
                            for t, o, h, l, c, v in zip(ts_list, op, hi, lo, cl, vo):
                                if c is not None and float(c) > 0:
                                    h1_candles.append({
                                        "time": int(t),
                                        "open": round(float(o or c) * mult, 2),
                                        "high": round(float(h or c) * mult, 2),
                                        "low": round(float(l or c) * mult, 2),
                                        "close": round(float(c) * mult, 2),
                                        "volume": float(v or 0.0),
                                    })

                    # 2. M15 de Yahoo (range=5d, interval=15m)
                    resp_m15 = await self._yf_client.get(
                        f"{self.YF_BASE_URL}/{yf_sym}",
                        params={"interval": "15m", "range": "5d"},
                    )
                    if resp_m15.status_code == 200:
                        d15 = resp_m15.json()
                        res_list15 = d15.get("chart", {}).get("result", [])
                        if res_list15:
                            r0 = res_list15[0]
                            ts_list = r0.get("timestamp", []) or []
                            q = (r0.get("indicators", {}).get("quote") or [{}])[0]
                            op = q.get("open", []) or []
                            hi = q.get("high", []) or []
                            lo = q.get("low", []) or []
                            cl = q.get("close", []) or []
                            vo = q.get("volume", []) or []
                            for t, o, h, l, c, v in zip(ts_list, op, hi, lo, cl, vo):
                                if c is not None and float(c) > 0:
                                    m15_candles.append({
                                        "time": int(t),
                                        "open": round(float(o or c) * mult, 2),
                                        "high": round(float(h or c) * mult, 2),
                                        "low": round(float(l or c) * mult, 2),
                                        "close": round(float(c) * mult, 2),
                                        "volume": float(v or 0.0),
                                    })
                except Exception as exc:
                    print(f"[BitsoClient] Error obteniendo OHLC Yahoo ({book}): {exc}")
        else:
            # Bitso Native OHLC API v3
            try:
                # 1. H1 (time_bucket=3600)
                resp_h1 = await self._client.get("/ohlc/", params={"book": book, "time_bucket": 3600})
                if resp_h1.status_code == 200:
                    d = resp_h1.json()
                    if d.get("success") and isinstance(d.get("payload"), list):
                        for c in d["payload"]:
                            o = float(c.get("first_rate") or 0.0)
                            cl = float(c.get("last_rate") or 0.0)
                            hi = float(c.get("max_rate") or max(o, cl))
                            lo = float(c.get("min_rate") or min(o, cl))
                            v = float(c.get("volume") or 0.0)
                            t = int(c.get("bucket_start_time", 0)) // 1000
                            if cl > 0:
                                h1_candles.append({
                                    "time": t,
                                    "open": round(o * mult, 6 if (o * mult) < 1 else 2),
                                    "high": round(hi * mult, 6 if (hi * mult) < 1 else 2),
                                    "low": round(lo * mult, 6 if (lo * mult) < 1 else 2),
                                    "close": round(cl * mult, 6 if (cl * mult) < 1 else 2),
                                    "volume": v,
                                })

                # 2. M15 (time_bucket=900)
                resp_m15 = await self._client.get("/ohlc/", params={"book": book, "time_bucket": 900})
                if resp_m15.status_code == 200:
                    d = resp_m15.json()
                    if d.get("success") and isinstance(d.get("payload"), list):
                        for c in d["payload"]:
                            o = float(c.get("first_rate") or 0.0)
                            cl = float(c.get("last_rate") or 0.0)
                            hi = float(c.get("max_rate") or max(o, cl))
                            lo = float(c.get("min_rate") or min(o, cl))
                            v = float(c.get("volume") or 0.0)
                            t = int(c.get("bucket_start_time", 0)) // 1000
                            if cl > 0:
                                m15_candles.append({
                                    "time": t,
                                    "open": round(o * mult, 6 if (o * mult) < 1 else 2),
                                    "high": round(hi * mult, 6 if (hi * mult) < 1 else 2),
                                    "low": round(lo * mult, 6 if (lo * mult) < 1 else 2),
                                    "close": round(cl * mult, 6 if (cl * mult) < 1 else 2),
                                    "volume": v,
                                })
            except Exception as exc:
                print(f"[BitsoClient] Error obteniendo OHLC Bitso ({book}): {exc}")

        # Guardar en caché si obtuvimos resultados
        if h1_candles or m15_candles:
            self._candles_cache[book] = {
                "ts": now,
                "h1": h1_candles,
                "m15": m15_candles,
            }

        return {"h1": h1_candles, "m15": m15_candles}
