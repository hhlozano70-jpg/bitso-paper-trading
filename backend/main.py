import asyncio
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

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


bitso = BitsoClient()
engine = PaperTradingEngine(initial_cash_mxn=100_000.0, fee_rate=0.0003)
bot = TradingBot()
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


async def _seed_book_history(book: str) -> None:
    trades = await bitso.get_recent_trades(book, limit=35)
    for t in trades:
        raw_ts = t.get("timestamp", "")
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


def build_state_payload() -> Dict[str, Any]:
    opp_by_book = {o["book"]: o for o in opportunities_cache}
    portfolio_summary = engine.get_summary(tickers_cache, active_book=active_book, opp_by_book=opp_by_book)
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
    Motor de Scalping de Alta Frecuencia con TP y SL Automatizados por Moneda:
    - Evalúa primero todas las posiciones abiertas contra su Take Profit / Stop Loss / Trailing Lock
      dinámico específico de esa moneda (calculado con sus últimos ticks, volatilidad y spread).
    - Si hay espacio en cartera (hasta 6 posiciones simultáneas), ejecuta compras rápidas en las
      mejores oportunidades de alta liquidez.
    """
    opp_by_book = {o["book"]: o for o in opportunities_cache}
    portfolio = engine.get_summary(tickers_cache, active_book=active_book, opp_by_book=opp_by_book)
    positions = portfolio.get("positions", {})
    last_executed_trade = None

    if (bot.multi_asset_auto or target_book) and not force_trade_side:
        # A) Revisar TODAS las posiciones abiertas para cobrar ganancias rápidas o cortar pérdidas
        for held_book, pos_data in list(positions.items()):
            qty = float(pos_data.get("amount", 0.0))
            if qty <= 1e-8 or held_book not in tickers_cache:
                continue

            unr_pct = float(pos_data.get("unrealized_pnl_pct", 0.0))
            peak_pct = float(pos_data.get("peak_pnl_pct", unr_pct))
            opp_info = opp_by_book.get(held_book, {})
            asset_rsi = float(opp_info.get("rsi_14", 50.0))
            sma_diff = float(opp_info.get("sma_diff_bps", 0.0))

            # Usar TP y SL automatizados por moneda si está activo, o el global de respaldo
            if bot.auto_tp_sl_by_coin:
                tp_target = float(opp_info.get("auto_tp_pct") or pos_data.get("auto_tp_pct") or bot.take_profit_pct)
                sl_target = float(opp_info.get("auto_sl_pct") or pos_data.get("auto_sl_pct") or bot.stop_loss_pct)
                trail_arm = float(opp_info.get("auto_trail_arm_pct") or max(0.09, tp_target * 0.45))
                trail_drop = float(opp_info.get("auto_trail_drop_pct") or max(0.04, tp_target * 0.20))
            else:
                tp_target = bot.take_profit_pct
                sl_target = bot.stop_loss_pct
                trail_arm = bot.trailing_arm_pct
                trail_drop = bot.trailing_drop_pct

            exit_reason = None
            if unr_pct >= tp_target:
                exit_reason = (
                    f"[Auto-TP {held_book.split('_')[0].upper()} +{tp_target:.2f}%] "
                    f"Ganancia rápida cobrada en +{unr_pct:.2f}%"
                )
            elif peak_pct >= trail_arm and (peak_pct - unr_pct) >= trail_drop and unr_pct >= 0.04:
                exit_reason = (
                    f"[Trailing Scalp Lock] Aseguró +{unr_pct:.2f}% "
                    f"(pico +{peak_pct:.2f}%, umbral +{trail_arm:.2f}%)"
                )
            elif unr_pct >= 0.08 and (asset_rsi >= 60.0 or sma_diff < -1.0):
                exit_reason = (
                    f"[Scalp Rápido en Verde] Cobró +{unr_pct:.2f}% al frenarse impulso (RSI={asset_rsi:.1f})"
                )
            elif unr_pct <= -sl_target:
                exit_reason = (
                    f"[Auto-SL {held_book.split('_')[0].upper()} -{sl_target:.2f}%] "
                    f"Cierre defensivo en {unr_pct:+.2f}%"
                )

            if exit_reason:
                res = engine.execute_order(
                    book=held_book,
                    side="SELL",
                    ticker=tickers_cache[held_book],
                    crypto_amount=qty,
                    source="BOT:SCALPER",
                    reason=exit_reason,
                    confidence=0.96,
                )
                if res.get("success"):
                    bot.last_trade_ts = time.time()
                    last_executed_trade = res["trade"]

        if last_executed_trade and not force:
            _refresh_opportunities()
            return {"signal": bot.last_signal, "executed_trade": last_executed_trade}

        # B) Seleccionar el mejor activo del radar para abrir nueva operación de Scalping
        elapsed = time.time() - bot.last_trade_ts
        open_positions_count = sum(1 for p in positions.values() if float(p.get("amount", 0.0)) > 1e-8)
        total_eq = float(portfolio.get("total_equity_mxn", 100000.0))
        has_cash_reserve = engine.cash_mxn >= (total_eq * 0.14)

        if (force or elapsed >= bot.cooldown_seconds) and (force or (open_positions_count < 6 and has_cash_reserve)):
            chosen_opp = None
            if target_book:
                chosen_opp = next((o for o in opportunities_cache if o["book"] == target_book), None)
            elif opportunities_cache:
                for opp in opportunities_cache:
                    b = opp["book"]
                    already_held = float(positions.get(b, {}).get("amount", 0.0)) > 1e-8
                    if (
                        not already_held
                        and opp["opportunity_score"] >= 57.0
                        and float(opp.get("spread_bps", 99.0)) <= 18.0
                        and float(opp.get("sma_diff_bps", 0.0)) >= -1.2
                    ):
                        chosen_opp = opp
                        break

            if chosen_opp and engine.cash_mxn >= 100.0:
                b = chosen_opp["book"]
                mxn_to_spend = engine.cash_mxn * (bot.trade_size_pct / 100.0)
                if mxn_to_spend >= 50.0 and b in tickers_cache:
                    conf = round(min(0.98, chosen_opp["opportunity_score"] / 100.0), 2)
                    auto_tp = chosen_opp["auto_tp_pct"]
                    auto_sl = chosen_opp["auto_sl_pct"]
                    reason = (
                        f"[Scalp Score {chosen_opp['opportunity_score']} | Auto-TP +{auto_tp}% / SL -{auto_sl}%] "
                        f"{chosen_opp['setup_type']}: {chosen_opp['rationale']}"
                    )
                    res = engine.execute_order(
                        book=b,
                        side="BUY",
                        ticker=tickers_cache[b],
                        mxn_amount=mxn_to_spend,
                        source="BOT:SCALPER",
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
                            "strategy": "multi_asset_scalper",
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

    # 2. Evaluación sobre el libro seleccionado
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

    action = force_trade_side.upper() if force_trade_side in ("BUY", "SELL") else signal["action"]
    reason = (
        f"[Prueba Manual Bot ({bot.strategy})] {signal['reason']}"
        if force_trade_side
        else signal["reason"]
    )

    executed_trade = None
    if action == "BUY":
        mxn_to_spend = engine.cash_mxn * (bot.trade_size_pct / 100.0)
        if mxn_to_spend >= 15.0:
            opp_info = opp_by_book.get(book, {})
            res = engine.execute_order(
                book=book,
                side="BUY",
                ticker=ticker,
                mxn_amount=mxn_to_spend,
                source=f"BOT:{bot.strategy.upper()}",
                reason=reason,
                confidence=signal["confidence"],
                auto_tp_pct=opp_info.get("auto_tp_pct"),
                auto_sl_pct=opp_info.get("auto_sl_pct"),
            )
            if res.get("success"):
                bot.last_trade_ts = time.time()
                executed_trade = res["trade"]
    elif action == "SELL":
        qty_held = float(pos.get("amount", 0.0))
        if qty_held > 1e-8:
            res = engine.execute_order(
                book=book,
                side="SELL",
                ticker=ticker,
                crypto_amount=qty_held,
                source=f"BOT:{bot.strategy.upper()}",
                reason=reason,
                confidence=signal["confidence"],
            )
            if res.get("success"):
                bot.last_trade_ts = time.time()
                executed_trade = res["trade"]

    _refresh_opportunities()
    return {"signal": signal, "executed_trade": executed_trade}


async def market_polling_loop() -> None:
    """Bucle de alta frecuencia (cada 2.0 segundos) para Scalping rápido en 24 activos."""
    while True:
        try:
            snap = await bitso.get_all_tickers_snapshot()
            if snap["tickers"]:
                tickers_cache.update(snap["tickers"])
                raw_books_cache.update(snap["raw_by_book"])
                for b, tk in snap["tickers"].items():
                    _append_price_point(b, float(tk["last"]))

            ob = await bitso.get_order_book(active_book, top_n=10)
            if ob["bids"] or ob["asks"]:
                order_book_cache[active_book] = ob

            _refresh_opportunities()

            if bot.enabled:
                await run_bot_cycle(force=False)
            else:
                book = active_book
                if book in tickers_cache:
                    portfolio = engine.get_summary(tickers_cache, active_book=book)
                    pos = portfolio["positions"].get(book, {"amount": 0.0, "unrealized_pnl_pct": 0.0})
                    bot.evaluate(
                        price_history=price_history_by_book.get(book, []),
                        ticker=tickers_cache[book],
                        order_book=order_book_cache.get(book, {"imbalance": 0.5}),
                        position=pos,
                        cash_mxn=engine.cash_mxn,
                        force=False,
                    )

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
    if os.environ.get("AUTO_START_BOT", "true").lower() in ("1", "true", "yes"):
        bot.enabled = True
        bot.multi_asset_auto = True
        bot.auto_tp_sl_by_coin = True

    snap = await bitso.get_all_tickers_snapshot()
    tickers_cache.update(snap["tickers"])
    raw_books_cache.update(snap["raw_by_book"])
    for b, tk in snap["tickers"].items():
        _append_price_point(b, float(tk["last"]))

    await _seed_book_history("btc_mxn")
    order_book_cache["btc_mxn"] = await bitso.get_order_book("btc_mxn", top_n=10)
    _refresh_opportunities()

    task = asyncio.create_task(market_polling_loop())
    keep_alive_task = asyncio.create_task(keep_alive_loop())
    yield
    task.cancel()
    keep_alive_task.cancel()
    await bitso.close()


app = FastAPI(
    title="Bitso High-Frequency Scalping & Multi-Asset AI Scanner",
    description="Simulador de Scalping con TP/SL automatizados por moneda y Balance Contable de Ganancias vs Pérdidas.",
    version="3.0.0",
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
        raise HTTPException(status_code=503, detail="No se pudo obtener el precio actual de Bitso.")

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
