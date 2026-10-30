import asyncio
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

import httpx
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from bitso_client import ASSET_CATALOG, SUPPORTED_BOOKS, BitsoClient
from opportunity_scanner import OpportunityScanner
from paper_engine import PaperTradingEngine
from trading_bot import TradingBot


class OrderRequest(BaseModel):
    book: str = "btc_mxn"
    side: str  # "BUY" | "SELL"
    mxn_amount: Optional[float] = None
    crypto_amount: Optional[float] = None
    reason: Optional[str] = "Orden manual desde terminal"


class BotConfigRequest(BaseModel):
    enabled: Optional[bool] = None
    multi_asset_auto: Optional[bool] = None
    auto_tp_sl_by_coin: Optional[bool] = None
    strategy: Optional[str] = None
    book: Optional[str] = None
    trade_size_pct: Optional[float] = None
    take_profit_pct: Optional[float] = None
    stop_loss_pct: Optional[float] = None
    cooldown_seconds: Optional[int] = None


class ResetPortfolioRequest(BaseModel):
    initial_cash_mxn: float = 100_000.0
    fee_rate: float = 0.0003
    clear_history: bool = True


class SwitchBookRequest(BaseModel):
    book: str


class ForceBotStepRequest(BaseModel):
    force_trade_side: Optional[str] = None
    target_book: Optional[str] = None


ALLOWED_AUTO_BOOKS = {
    "btc_mxn", "eth_mxn", "sol_mxn", "xrp_mxn",
    "nvda_stk", "aapl_stk", "nq_fut"
}

bitso = BitsoClient()
engine = PaperTradingEngine(initial_cash_mxn=100_000.0, fee_rate=0.0003)
bot = TradingBot()
bot.enabled = True
bot.multi_asset_auto = True
bot.auto_tp_sl_by_coin = True
bot.trade_size_pct = 45.0
bot.cooldown_seconds = 75

scanner = OpportunityScanner()

active_book: str = "btc_mxn"
tickers_cache: Dict[str, Dict[str, Any]] = {}
raw_books_cache: Dict[str, Dict[str, Any]] = {}
order_book_cache: Dict[str, Dict[str, Any]] = {}
price_history_by_book: Dict[str, List[Dict[str, Any]]] = {b: [] for b in SUPPORTED_BOOKS}
opportunities_cache: List[Dict[str, Any]] = []
arbitrage_cache: List[Dict[str, Any]] = []
ws_clients: Set[WebSocket] = set()


def _append_price_point(book: str, price: float, timestamp_label: Optional[str] = None) -> None:
    if price <= 0:
        return
    hist = price_history_by_book.setdefault(book, [])
    label = timestamp_label or datetime.now().strftime("%H:%M:%S")

    if hist and hist[-1]["time"] == label and abs(hist[-1]["price"] - price) < 1e-8:
        return

    recent_prices = [p["price"] for p in hist[-17:]] + [price]
    sma_5 = sum(recent_prices[-5:]) / len(recent_prices[-5:])
    sma_18 = sum(recent_prices[-18:]) / len(recent_prices[-18:])

    decimals = 6 if price < 1 else 2
    hist.append({
        "time": label,
        "price": round(price, decimals),
        "sma5": round(sma_5, decimals),
        "sma18": round(sma_18, decimals),
    })
    if len(hist) > 90:
        price_history_by_book[book] = hist[-90:]


def _sync_yahoo_histories(yf_series: Dict[str, List[Tuple[str, float]]]) -> None:
    for book, pts in yf_series.items():
        if len(price_history_by_book.get(book, [])) < 5:
            for lbl, px in pts:
                _append_price_point(book, px, lbl)


async def _seed_book_history(book: str) -> None:
    trades = await bitso.get_recent_trades(book, limit=35)
    for t in trades:
        raw_ts = str(t.get("timestamp", ""))
        if ":" in raw_ts and len(raw_ts) <= 10:
            label = raw_ts
        else:
            try:
                dt = datetime.fromisoformat(raw_ts.replace("Z", "+00:00")).astimezone()
                label = dt.strftime("%H:%M:%S")
            except Exception:
                label = datetime.now().strftime("%H:%M:%S")
        _append_price_point(book, float(t["price"]), label)


def _refresh_opportunities() -> None:
    global opportunities_cache, arbitrage_cache
    portfolio_summary = engine.get_summary(tickers_cache, active_book=active_book)
    opportunities_cache = scanner.scan_all_assets(
        tickers=tickers_cache,
        price_history_by_book=price_history_by_book,
        positions=portfolio_summary.get("positions", {}),
        fee_rate=engine.fee_rate,
    )
    arbitrage_cache = scanner.scan_triangular_arbitrage(
        raw_by_book=raw_books_cache,
        usd_mxn_rate=bitso.usd_mxn_rate,
    )


def _build_managed_4_assets(
    portfolio_summary: Dict[str, Any], opp_by_book: Dict[str, Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Construye el paquete completo de los 4 Activos Manejados (con su serie histórica para gráfico
    y todos sus parámetros técnicos y de Auto-TP/SL) para el Monitor Cuádruple en Tiempo Real.
    """
    positions = portfolio_summary.get("positions", {})
    held_books = [
        b
        for b, p in sorted(
            positions.items(),
            key=lambda kv: float(kv[1].get("market_value_mxn", 0.0)),
            reverse=True,
        )
        if float(p.get("amount", 0.0)) > 1e-8
    ]

    selected_books: List[str] = list(held_books[:4])
    for opp in opportunities_cache:
        if len(selected_books) >= 4:
            break
        if opp["book"] not in selected_books:
            selected_books.append(opp["book"])

    managed_cards: List[Dict[str, Any]] = []
    for idx, b in enumerate(selected_books[:4]):
        meta = ASSET_CATALOG.get(b, {"name": b.upper(), "symbol": b.upper(), "pair": b.upper(), "category": "Activo"})
        tk = tickers_cache.get(b, {})
        pos = positions.get(
            b,
            {
                "book": b,
                "amount": 0.0,
                "avg_buy_price": 0.0,
                "mark_price": tk.get("last", 0.0),
                "market_value_mxn": 0.0,
                "unrealized_pnl_mxn": 0.0,
                "unrealized_pnl_pct": 0.0,
                "peak_pnl_pct": 0.0,
                "hold_seconds": 0,
            },
        )
        opp = opp_by_book.get(b, {})
        auto_tp = float(opp.get("auto_tp_pct") or pos.get("auto_tp_pct") or 0.55)
        auto_sl = float(opp.get("auto_sl_pct") or pos.get("auto_sl_pct") or 0.35)
        auto_trail = float(opp.get("auto_trail_arm_pct") or 0.30)

        avg_entry = float(pos.get("avg_buy_price") or tk.get("last") or 0.0)
        tp_price = round(avg_entry * (1.0 + auto_tp / 100.0), 6 if avg_entry < 1 else 2) if avg_entry > 0 else 0.0
        sl_price = round(avg_entry * (1.0 - auto_sl / 100.0), 6 if avg_entry < 1 else 2) if avg_entry > 0 else 0.0

        managed_cards.append({
            "slot": idx + 1,
            "book": b,
            "name": meta.get("name", b),
            "symbol": meta.get("symbol", b),
            "pair": meta.get("pair", b),
            "category": meta.get("category", "Activo"),
            "is_active_position": float(pos.get("amount", 0.0)) > 1e-8,
            "last_price": tk.get("last", 0.0),
            "change_24_pct": tk.get("change_24_pct", 0.0),
            "vwap_diff_pct": opp.get("vwap_diff_pct", 0.0),
            "rsi_14": opp.get("rsi_14", 50.0),
            "sma_diff_bps": opp.get("sma_diff_bps", 0.0),
            "spread_bps": tk.get("spread_bps", 0.0),
            "opportunity_score": opp.get("opportunity_score", 55.0),
            "setup_type": opp.get("setup_type", "Monitoreo Activo"),
            "rationale": opp.get("rationale", ""),
            "auto_tp_pct": auto_tp,
            "auto_trail_arm_pct": auto_trail,
            "auto_sl_pct": auto_sl,
            "tp_price": tp_price,
            "sl_price": sl_price,
            "position": pos,
            "price_history": price_history_by_book.get(b, []),
        })

    return managed_cards


def build_state_payload() -> Dict[str, Any]:
    opp_by_book = {o["book"]: o for o in opportunities_cache}
    portfolio_summary = engine.get_summary(tickers_cache, active_book=active_book, opp_by_book=opp_by_book)
    managed_4 = _build_managed_4_assets(portfolio_summary, opp_by_book)
    return {
        "active_book": active_book,
        "supported_books": SUPPORTED_BOOKS,
        "asset_catalog": ASSET_CATALOG,
        "usd_mxn_rate": round(bitso.usd_mxn_rate, 4),
        "tickers": tickers_cache,
        "active_ticker": tickers_cache.get(active_book, {}),
        "order_book": order_book_cache.get(
            active_book, {"bids": [], "asks": [], "bid_volume": 0.0, "ask_volume": 0.0, "imbalance": 0.5}
        ),
        "price_history": price_history_by_book.get(active_book, []),
        "managed_4_assets": managed_4,
        "portfolio": portfolio_summary,
        "opportunities": opportunities_cache,
        "arbitrage": arbitrage_cache,
        "bot": bot.get_config(),
        "server_time": datetime.now().strftime("%H:%M:%S"),
    }


async def broadcast_state() -> None:
    if not ws_clients:
        return
    payload = build_state_payload()
    dead_clients: List[WebSocket] = []
    for ws in list(ws_clients):
        try:
            await ws.send_json(payload)
        except Exception:
            dead_clients.append(ws)
    for ws in dead_clients:
        ws_clients.discard(ws)


async def run_bot_cycle(
    force: bool = False,
    force_trade_side: Optional[str] = None,
    target_book: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Motor Autónomo de Gestión y Rotación de 4 Activos (Cripto + Acciones + Futuros + FX/Oro):
      1. Ejecuta cobros automáticos de ganancia rápida (Auto-TP, Trailing Lock, Scalp en Verde)
         y cortes defensivos (Auto-SL) personalizados por activo.
      2. Rotación Dinámica por Comportamiento (Sin Preguntar): Si un activo en cartera pierde
         impulso o aparece una oportunidad mucho más fuerte en otro mercado, vende el activo
         débil y compra inmediatamente el nuevo líder para mantener los 4 slots optimizados.
      3. Si hay menos de 4 activos abiertos en cartera, toma automáticamente las mejores
         oportunidades hasta completar los 4 activos manejados.
    """
    opp_by_book = {o["book"]: o for o in opportunities_cache}
    portfolio = engine.get_summary(tickers_cache, active_book=active_book, opp_by_book=opp_by_book)
    positions = portfolio.get("positions", {})
    last_executed_trade = None

    # Identificar el mejor candidato libre del radar para evaluar rotaciones
    best_unheld_opp = None
    for opp in opportunities_cache:
        b = opp["book"]
        if float(positions.get(b, {}).get("amount", 0.0)) <= 1e-8 and float(opp.get("spread_bps", 99.0)) <= 18.0:
            best_unheld_opp = opp
            break

    if (bot.multi_asset_auto or target_book) and not force_trade_side:
        # A) Evaluar salidas: Auto-TP, Breakeven Shield, Trailing Lock, Auto-SL y Rotación Protegida
        for held_book, pos_data in list(positions.items()):
            qty = float(pos_data.get("amount", 0.0))
            if qty <= 1e-8 or held_book not in tickers_cache:
                continue

            unr_pct = float(pos_data.get("unrealized_pnl_pct", 0.0))
            peak_pct = float(pos_data.get("peak_pnl_pct", unr_pct))
            hold_sec = int(pos_data.get("hold_seconds", 0))
            opp_info = opp_by_book.get(held_book, {})
            asset_rsi = float(opp_info.get("rsi_14", 50.0))
            sma_diff = float(opp_info.get("sma_diff_bps", 0.0))
            current_score = float(opp_info.get("opportunity_score", 50.0))
            sym = ASSET_CATALOG.get(held_book, {}).get("symbol", held_book.upper())

            if bot.auto_tp_sl_by_coin:
                tp_target = float(opp_info.get("auto_tp_pct") or pos_data.get("auto_tp_pct") or 0.55)
                raw_sl = float(opp_info.get("auto_sl_pct") or pos_data.get("auto_sl_pct") or 0.35)
                sl_target = min(0.35, raw_sl)
                trail_arm = float(opp_info.get("auto_trail_arm_pct") or 0.30)
                trail_drop = float(opp_info.get("auto_trail_drop_pct") or 0.08)
            else:
                tp_target = bot.take_profit_pct
                sl_target = min(0.35, bot.stop_loss_pct)
                trail_arm = bot.trailing_arm_pct
                trail_drop = bot.trailing_drop_pct

            exit_reason = None

            # 1. Take Profit Principal Automatizado (+0.48% a +0.80% meta real)
            if unr_pct >= tp_target:
                exit_reason = f"[Sniper TP Ganador] {sym} alcanzó meta de +{unr_pct:.2f}% (Target: +{tp_target:.2f}%)"

            # 2. Trailing Profit Lock: Asegura ganancia cuando sube sobre +0.30% y retrocede 0.08%
            elif peak_pct >= trail_arm and (peak_pct - unr_pct) >= trail_drop and unr_pct >= 0.18:
                exit_reason = (
                    f"[Trailing Profit Asegurado] {sym} aseguró +{unr_pct:.2f}% "
                    f"(pico +{peak_pct:.2f}%)"
                )

            # 3. Breakeven Shield Firme: Si ya tocó +0.25%, asegura que no caiga a pérdidas (cierra en +0.08% min)
            elif peak_pct >= 0.25 and unr_pct <= 0.10 and unr_pct >= 0.02:
                exit_reason = f"[Breakeven Shield] {sym} protegido con ganancia (+{unr_pct:.2f}%)"

            # 4. Toma de ganancia en verde si llega a fuerte sobrecompra (RSI >= 70 y PnL >= +0.35%)
            elif unr_pct >= 0.35 and asset_rsi >= 70.0 and hold_sec >= 120:
                exit_reason = f"[Scalp Verde en Resistencia] {sym} cobró +{unr_pct:.2f}% al llegar a sobrecompra extrema (RSI={asset_rsi:.1f})"

            # 5. Stop Loss Estricto Capped (corte defensivo inquebrantable a -0.35% máx)
            elif unr_pct <= -sl_target:
                exit_reason = f"[Stop Loss Controlado] {sym} cortó pérdida en {unr_pct:+.2f}% (SL Máx: -{sl_target:.2f}%)"

            # 6. Rotación por Oportunidad Superior: Solo si la posición ya está en VERDE SUSTANCIAL (>= +0.35%)
            elif (
                unr_pct >= 0.35
                and hold_sec >= 360
                and best_unheld_opp
                and best_unheld_opp["book"] in ALLOWED_AUTO_BOOKS
                and (best_unheld_opp["opportunity_score"] - current_score) >= 20.0
                and best_unheld_opp["opportunity_score"] >= 80.0
            ):
                new_sym = best_unheld_opp["symbol"]
                exit_reason = (
                    f"[Rotación con Ganancia: {sym} → {new_sym}] Cobró +{unr_pct:.2f}% ({hold_sec}s) "
                    f"para entrar a nuevo líder {new_sym} (Score {best_unheld_opp['opportunity_score']:.1f})"
                )

            if exit_reason:
                res = engine.execute_order(
                    book=held_book,
                    side="SELL",
                    ticker=tickers_cache[held_book],
                    crypto_amount=qty,
                    source="BOT:SNIPER",
                    reason=exit_reason,
                    confidence=0.96,
                )
                if res.get("success"):
                    bot.last_trade_ts = time.time()
                    last_executed_trade = res["trade"]

        # B) Entradas Selectivas: Solo los 7 activos líderes ultra-líquidos, máx 2 posiciones abiertas
        portfolio = engine.get_summary(tickers_cache, active_book=active_book, opp_by_book=opp_by_book)
        positions = portfolio.get("positions", {})
        open_positions_count = sum(1 for p in positions.values() if float(p.get("amount", 0.0)) > 1e-8)

        if open_positions_count < 2 and engine.cash_mxn >= 500.0:
            chosen_opp = None
            if target_book and target_book in ALLOWED_AUTO_BOOKS:
                chosen_opp = next((o for o in opportunities_cache if o["book"] == target_book), None)
            elif opportunities_cache:
                for opp in opportunities_cache:
                    b = opp["book"]
                    # REGLA DE ORO: Solo los 7 activos líderes ultra-líquidos
                    if b not in ALLOWED_AUTO_BOOKS:
                        continue

                    already_held = float(positions.get(b, {}).get("amount", 0.0)) > 1e-8
                    spread_bps = float(opp.get("spread_bps", 99.0))
                    macro_status = str(opp.get("macro_status", ""))
                    rsi = float(opp.get("rsi_14", 50.0))

                    # 4 Pilares Quirúrgicos de Entrada:
                    # 1. Sin posición previa en este activo
                    # 2. Score >= 76.0 (Alta certeza)
                    # 3. Spread ultra-bajo <= 4.2 bps (Liquidez institucional)
                    # 4. Macro trend alineado (no bloqueado por BTC o Nasdaq)
                    # 5. Entrada en retroceso real: RSI <= 42.0 (no perseguir techos)
                    if (
                        not already_held
                        and opp["opportunity_score"] >= 76.0
                        and spread_bps <= 4.2
                        and "Bloqueado" not in macro_status
                        and rsi <= 42.0
                    ):
                        # Pilar 3: Confirmación de Libro de Órdenes (Bid Imbalance >= 49%)
                        ob = order_book_cache.get(b)
                        imbalance = float(ob.get("imbalance", 0.52)) if ob else 0.52
                        if imbalance >= 0.49:
                            chosen_opp = opp
                            break

            if chosen_opp:
                b = chosen_opp["book"]
                slots_remaining = max(1, 2 - open_positions_count)
                mxn_to_spend = min(
                    engine.cash_mxn * 0.95,
                    max(engine.cash_mxn / slots_remaining * 0.92, engine.cash_mxn * (bot.trade_size_pct / 100.0)),
                )
                if mxn_to_spend >= 100.0 and b in tickers_cache:
                    if len(price_history_by_book.get(b, [])) < 5:
                        await _seed_book_history(b)
                    conf = round(min(0.98, chosen_opp["opportunity_score"] / 100.0), 2)
                    auto_tp = chosen_opp["auto_tp_pct"]
                    auto_sl = chosen_opp["auto_sl_pct"]
                    reason = (
                        f"[Entrada Sniper ({chosen_opp['category']}) | Score {chosen_opp['opportunity_score']} | "
                        f"TP +{auto_tp}% / SL -{auto_sl}%] {chosen_opp['setup_type']}: {chosen_opp['rationale']}"
                    )
                    res = engine.execute_order(
                        book=b,
                        side="BUY",
                        ticker=tickers_cache[b],
                        mxn_amount=mxn_to_spend,
                        source="BOT:SNIPER",
                        reason=reason,
                        confidence=conf,
                        auto_tp_pct=auto_tp,
                        auto_sl_pct=auto_sl,
                    )
                    if res.get("success"):
                        bot.last_trade_ts = time.time()
                        bot.last_signal = {
                            "action": "BUY",
                            "confidence": conf,
                            "reason": reason,
                            "strategy": "sniper_scalper",
                            "timestamp": datetime.now().isoformat(),
                            "features": bot.extract_features(
                                price_history_by_book.get(b, []),
                                tickers_cache[b],
                                order_book_cache.get(b, {"imbalance": 0.5}),
                                positions.get(b, {}),
                                engine.cash_mxn,
                            ),
                        }
                        _refresh_opportunities()
                        return {"signal": bot.last_signal, "executed_trade": res["trade"]}

        if last_executed_trade:
            _refresh_opportunities()
            return {"signal": bot.last_signal, "executed_trade": last_executed_trade}

    # Evaluación sobre el libro activo
    book = target_book or bot.book
    ticker = tickers_cache.get(book) or await bitso.get_ticker(book)
    if not ticker:
        return {"executed": False, "error": "Ticker no disponible"}

    tickers_cache[book] = ticker
    ob = order_book_cache.get(book) or await bitso.get_order_book(book)
    order_book_cache[book] = ob

    pos = positions.get(book, {"amount": 0.0, "unrealized_pnl_pct": 0.0})
    hist = price_history_by_book.get(book, [])
    signal = bot.evaluate(
        price_history=hist,
        ticker=ticker,
        order_book=ob,
        position=pos,
        cash_mxn=engine.cash_mxn,
        force=force,
    )

    executed_trade = None
    if force_trade_side in ("BUY", "SELL"):
        action = force_trade_side.upper()
        opp_info = opp_by_book.get(book, {})
        if action == "BUY":
            mxn_to_spend = engine.cash_mxn * (bot.trade_size_pct / 100.0)
            res = engine.execute_order(
                book=book,
                side="BUY",
                ticker=ticker,
                mxn_amount=mxn_to_spend,
                source="BOT:MANUAL-STEP",
                reason=signal["reason"],
                confidence=signal["confidence"],
                auto_tp_pct=opp_info.get("auto_tp_pct"),
                auto_sl_pct=opp_info.get("auto_sl_pct"),
            )
            if res.get("success"):
                executed_trade = res["trade"]
        elif action == "SELL":
            qty_held = float(pos.get("amount", 0.0))
            if qty_held > 1e-8:
                res = engine.execute_order(
                    book=book,
                    side="SELL",
                    ticker=ticker,
                    crypto_amount=qty_held,
                    source="BOT:MANUAL-STEP",
                    reason=signal["reason"],
                    confidence=signal["confidence"],
                )
                if res.get("success"):
                    executed_trade = res["trade"]

    _refresh_opportunities()
    return {"signal": signal, "executed_trade": executed_trade}


async def market_polling_loop() -> None:
    """Bucle autónomo cada 2.0 segundos que escanea 39 activos (Cripto, Acciones, Futuros, FX, Oro)."""
    while True:
        try:
            snap = await bitso.get_all_tickers_snapshot()
            if snap["tickers"]:
                tickers_cache.update(snap["tickers"])
                raw_books_cache.update(snap["raw_by_book"])
                _sync_yahoo_histories(snap.get("yf_series", {}))
                for b, tk in snap["tickers"].items():
                    _append_price_point(b, float(tk["last"]))

            ob = await bitso.get_order_book(active_book, top_n=10)
            if ob["bids"] or ob["asks"]:
                order_book_cache[active_book] = ob

            _refresh_opportunities()

            if bot.enabled:
                await run_bot_cycle(force=False)

            # Asegurar que los 4 activos manejados tengan su historial poblado para mostrar los 4 gráficos
            opp_by_book = {o["book"]: o for o in opportunities_cache}
            portfolio_summary = engine.get_summary(tickers_cache, active_book=active_book, opp_by_book=opp_by_book)
            managed_4 = _build_managed_4_assets(portfolio_summary, opp_by_book)
            for item in managed_4:
                b = item["book"]
                if len(price_history_by_book.get(b, [])) < 5:
                    await _seed_book_history(b)

            await broadcast_state()
        except Exception as exc:
            print(f"[MarketLoop] Error en ciclo: {exc}")

        await asyncio.sleep(2.0)


async def keep_alive_loop() -> None:
    target_url = os.environ.get("RENDER_EXTERNAL_URL") or os.environ.get("PUBLIC_URL")
    if not target_url:
        return
    health_url = f"{target_url.rstrip('/')}/api/health"
    async with httpx.AsyncClient(timeout=10.0) as client:
        while True:
            await asyncio.sleep(240)
            try:
                await client.get(health_url)
            except Exception:
                pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    bot.enabled = True
    bot.multi_asset_auto = True
    bot.auto_tp_sl_by_coin = True

    snap = await bitso.get_all_tickers_snapshot()
    tickers_cache.update(snap["tickers"])
    raw_books_cache.update(snap["raw_by_book"])
    _sync_yahoo_histories(snap.get("yf_series", {}))
    for b, tk in snap["tickers"].items():
        _append_price_point(b, float(tk["last"]))

    # Sembrar historial de los primeros libros principales en paralelo
    await asyncio.gather(
        _seed_book_history("btc_mxn"),
        _seed_book_history("eth_mxn"),
        _seed_book_history("sol_mxn"),
        _seed_book_history("xrp_mxn"),
        return_exceptions=True,
    )
    order_book_cache["btc_mxn"] = await bitso.get_order_book("btc_mxn", top_n=10)
    _refresh_opportunities()

    # Seleccionar automáticamente las primeras 4 mejores oportunidades al arrancar
    for _ in range(4):
        await run_bot_cycle(force=True)

    task = asyncio.create_task(market_polling_loop())
    keep_alive_task = asyncio.create_task(keep_alive_loop())
    yield
    task.cancel()
    keep_alive_task.cancel()
    await bitso.close()


app = FastAPI(
    title="Bitso & Global Markets Autonomous 4-Asset Rotator",
    description="Gestión autónoma de 4 activos con rotación dinámica en Cripto, Acciones, Futuros, Oro y Divisas.",
    version="4.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/state")
async def get_state(book: Optional[str] = None) -> Dict[str, Any]:
    global active_book
    if book and book in SUPPORTED_BOOKS and book != active_book:
        active_book = book
        if len(price_history_by_book.get(book, [])) < 5:
            await _seed_book_history(book)
        if book not in order_book_cache:
            order_book_cache[book] = await bitso.get_order_book(book, top_n=10)
    return build_state_payload()


@app.get("/api/opportunities")
async def get_opportunities() -> Dict[str, Any]:
    _refresh_opportunities()
    return {
        "usd_mxn_rate": round(bitso.usd_mxn_rate, 4),
        "opportunities": opportunities_cache,
        "arbitrage": arbitrage_cache,
    }


@app.get("/api/trades/export")
async def export_trades() -> Response:
    csv_data = engine.export_trades_csv()
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=bitso_historial_transacciones.csv"},
    )


@app.post("/api/rotate/{book_to_sell}")
async def rotate_single_asset(book_to_sell: str) -> Dict[str, Any]:
    """Vende inmediatamente el activo indicado y lo reemplaza por la mejor oportunidad disponible."""
    opp_by_book = {o["book"]: o for o in opportunities_cache}
    portfolio = engine.get_summary(tickers_cache, active_book=active_book, opp_by_book=opp_by_book)
    pos = portfolio.get("positions", {}).get(book_to_sell, {})
    qty = float(pos.get("amount", 0.0))
    if qty > 1e-8 and book_to_sell in tickers_cache:
        sym = ASSET_CATALOG.get(book_to_sell, {}).get("symbol", book_to_sell.upper())
        engine.execute_order(
            book=book_to_sell,
            side="SELL",
            ticker=tickers_cache[book_to_sell],
            crypto_amount=qty,
            source="BOT:ROTADOR",
            reason=f"[Rotación Directa] Reemplazando {sym} por mejor oportunidad del radar",
            confidence=0.95,
        )
    await run_bot_cycle(force=True)
    await broadcast_state()
    return build_state_payload()


@app.post("/api/book")
async def switch_book(req: SwitchBookRequest) -> Dict[str, Any]:
    global active_book
    if req.book not in SUPPORTED_BOOKS:
        raise HTTPException(status_code=400, detail=f"Libro no soportado: {req.book}")
    active_book = req.book
    bot.book = req.book
    if len(price_history_by_book.get(req.book, [])) < 5:
        await _seed_book_history(req.book)
    order_book_cache[req.book] = await bitso.get_order_book(req.book, top_n=10)
    await broadcast_state()
    return build_state_payload()


@app.post("/api/order")
async def place_order(req: OrderRequest) -> Dict[str, Any]:
    book = req.book if req.book in SUPPORTED_BOOKS else active_book
    ticker = tickers_cache.get(book) or await bitso.get_ticker(book)
    if not ticker:
        raise HTTPException(status_code=503, detail="No se pudo obtener el precio actual.")

    opp_info = next((o for o in opportunities_cache if o["book"] == book), {})
    result = engine.execute_order(
        book=book,
        side=req.side,
        ticker=ticker,
        mxn_amount=req.mxn_amount,
        crypto_amount=req.crypto_amount,
        source="MANUAL",
        reason=req.reason or "Orden manual ejecutada por el usuario",
        auto_tp_pct=opp_info.get("auto_tp_pct"),
        auto_sl_pct=opp_info.get("auto_sl_pct"),
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Error al ejecutar orden"))

    _refresh_opportunities()
    await broadcast_state()
    return {"result": result, "state": build_state_payload()}


@app.post("/api/bot/config")
async def update_bot_config(req: BotConfigRequest) -> Dict[str, Any]:
    cfg = {k: v for k, v in req.model_dump().items() if v is not None}
    bot.update_config(cfg)
    if bot.enabled:
        await run_bot_cycle(force=False)
    await broadcast_state()
    return build_state_payload()


@app.post("/api/bot/step")
async def step_bot(req: ForceBotStepRequest) -> Dict[str, Any]:
    res = await run_bot_cycle(force=True, force_trade_side=req.force_trade_side, target_book=req.target_book)
    await broadcast_state()
    return {"step_result": res, "state": build_state_payload()}


@app.post("/api/portfolio/reset")
async def reset_portfolio(req: ResetPortfolioRequest) -> Dict[str, Any]:
    engine.reset(initial_cash_mxn=req.initial_cash_mxn, fee_rate=req.fee_rate, clear_history=req.clear_history)
    _refresh_opportunities()
    if bot.enabled and bot.multi_asset_auto:
        for _ in range(4):
            await run_bot_cycle(force=True)
    await broadcast_state()
    return build_state_payload()


@app.get("/api/health")
async def health_check() -> Dict[str, Any]:
    portfolio = engine.get_summary(tickers_cache, active_book=active_book)
    return {
        "status": "ok",
        "server_time": datetime.now().isoformat(),
        "bot_enabled": bot.enabled,
        "multi_asset_auto": bot.multi_asset_auto,
        "auto_tp_sl_by_coin": bot.auto_tp_sl_by_coin,
        "total_equity_mxn": portfolio.get("total_equity_mxn"),
        "total_trades": portfolio.get("total_trades"),
        "monitored_assets": len(tickers_cache),
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    ws_clients.add(websocket)
    try:
        await websocket.send_json(build_state_payload())
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_clients.discard(websocket)
    except Exception:
        ws_clients.discard(websocket)


FRONTEND_DIST = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend", "dist"))
if os.path.isdir(FRONTEND_DIST):
    assets_dir = os.path.join(FRONTEND_DIST, "assets")
    if os.path.isdir(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        file_path = os.path.join(FRONTEND_DIST, full_path)
        if full_path and os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(FRONTEND_DIST, "index.html"))
