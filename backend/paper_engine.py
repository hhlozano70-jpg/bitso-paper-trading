import csv
import io
import json
import os
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

STATE_FILE = os.path.join(os.path.dirname(__file__), "portfolio_state.json")
DB_FILE = os.path.join(os.path.dirname(__file__), "trades_history.db")


class PaperTradingEngine:
    """
    Motor de simulación financiera (Paper Trading) con precios reales de Bitso,
    almacenamiento persistente en SQLite + JSON, y Balance Contable de Ganancias vs. Pérdidas.
    """

    def __init__(self, initial_cash_mxn: float = 100_000.0, fee_rate: float = 0.0003) -> None:
        self.initial_cash_mxn = initial_cash_mxn
        self.cash_mxn = initial_cash_mxn
        self.fee_rate = fee_rate  # 0.03% modo Scalping de alta frecuencia
        self.positions: Dict[str, Dict[str, float]] = {}
        self.trades: List[Dict[str, Any]] = []
        self.equity_curve: List[Dict[str, Any]] = []
        self.benchmark_initial_prices: Dict[str, float] = {}
        self._init_db()
        self._load_state()

    def _init_db(self) -> None:
        try:
            with sqlite3.connect(DB_FILE) as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS trades (
                        id TEXT PRIMARY KEY,
                        timestamp TEXT,
                        book TEXT,
                        side TEXT,
                        price REAL,
                        amount REAL,
                        total_mxn REAL,
                        fee_mxn REAL,
                        pnl_mxn REAL,
                        pnl_pct REAL,
                        source TEXT,
                        reason TEXT,
                        confidence REAL
                    )
                    """
                )
                conn.commit()
        except Exception as exc:
            print(f"[PaperTradingEngine] Error inicializando SQLite: {exc}")

    def _insert_trade_db(self, trade: Dict[str, Any]) -> None:
        try:
            with sqlite3.connect(DB_FILE) as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO trades
                    (id, timestamp, book, side, price, amount, total_mxn, fee_mxn, pnl_mxn, pnl_pct, source, reason, confidence)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        trade["id"],
                        trade["timestamp"],
                        trade["book"],
                        trade["side"],
                        trade["price"],
                        trade["amount"],
                        trade["total_mxn"],
                        trade["fee_mxn"],
                        trade["pnl_mxn"],
                        trade["pnl_pct"],
                        trade["source"],
                        trade["reason"],
                        trade.get("confidence"),
                    ),
                )
                conn.commit()
        except Exception as exc:
            print(f"[PaperTradingEngine] Error guardando trade en SQLite: {exc}")

    def _ensure_book(self, book: str) -> Dict[str, float]:
        if book not in self.positions:
            self.positions[book] = {
                "amount": 0.0,
                "avg_buy_price": 0.0,
                "peak_pnl_pct": 0.0,
                "auto_tp_pct": 0.38,
                "auto_sl_pct": 0.36,
                "realized_pnl": 0.0,
                "total_bought_mxn": 0.0,
                "total_sold_mxn": 0.0,
            }
        return self.positions[book]

    def _save_state(self) -> None:
        try:
            payload = {
                "initial_cash_mxn": self.initial_cash_mxn,
                "cash_mxn": self.cash_mxn,
                "fee_rate": self.fee_rate,
                "positions": self.positions,
                "trades": self.trades[-500:],
                "equity_curve": self.equity_curve[-180:],
                "benchmark_initial_prices": self.benchmark_initial_prices,
            }
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
        except Exception as exc:
            print(f"[PaperTradingEngine] Error guardando estado: {exc}")

    def _load_state(self) -> None:
        if not os.path.exists(STATE_FILE):
            return
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.initial_cash_mxn = float(data.get("initial_cash_mxn", 100_000.0))
            self.cash_mxn = float(data.get("cash_mxn", self.initial_cash_mxn))
            self.fee_rate = float(data.get("fee_rate", 0.0003))
            self.positions = data.get("positions", {})
            self.trades = data.get("trades", [])
            self.equity_curve = data.get("equity_curve", [])
            self.benchmark_initial_prices = data.get("benchmark_initial_prices", {})
        except Exception as exc:
            print(f"[PaperTradingEngine] Error cargando estado: {exc}")

    def reset(self, initial_cash_mxn: float = 100_000.0, fee_rate: Optional[float] = None, clear_history: bool = True) -> Dict[str, Any]:
        self.initial_cash_mxn = initial_cash_mxn
        self.cash_mxn = initial_cash_mxn
        if fee_rate is not None:
            self.fee_rate = fee_rate
        self.positions = {}
        if clear_history:
            self.trades = []
            try:
                with sqlite3.connect(DB_FILE) as conn:
                    conn.execute("DELETE FROM trades")
                    conn.commit()
            except Exception:
                pass
        self.equity_curve = []
        self.benchmark_initial_prices = {}
        self._save_state()
        return {"status": "ok", "cash_mxn": self.cash_mxn}

    def execute_order(
        self,
        book: str,
        side: str,
        ticker: Dict[str, Any],
        mxn_amount: Optional[float] = None,
        crypto_amount: Optional[float] = None,
        source: str = "MANUAL",
        reason: str = "Orden manual del usuario",
        confidence: Optional[float] = None,
        auto_tp_pct: Optional[float] = None,
        auto_sl_pct: Optional[float] = None,
    ) -> Dict[str, Any]:
        side = side.upper()
        pos = self._ensure_book(book)
        now_iso = datetime.now(timezone.utc).isoformat()

        if side == "BUY":
            exec_price = float(ticker.get("ask") or ticker.get("last") or 0.0)
            if exec_price <= 0:
                return {"success": False, "error": "Precio de mercado inválido."}

            if mxn_amount is not None:
                gross_mxn = min(float(mxn_amount), self.cash_mxn)
            elif crypto_amount is not None:
                gross_mxn = float(crypto_amount) * exec_price / (1.0 - self.fee_rate)
                gross_mxn = min(gross_mxn, self.cash_mxn)
            else:
                return {"success": False, "error": "Debes especificar mxn_amount o crypto_amount."}

            if gross_mxn < 10.0:
                return {"success": False, "error": "Saldo MXN insuficiente (mínimo $10 MXN)."}

            fee_mxn = gross_mxn * self.fee_rate
            net_mxn = gross_mxn - fee_mxn
            qty = net_mxn / exec_price

            prev_qty = pos["amount"]
            prev_cost = prev_qty * pos["avg_buy_price"]
            new_qty = prev_qty + qty
            pos["avg_buy_price"] = (prev_cost + gross_mxn) / new_qty if new_qty > 0 else 0.0
            pos["amount"] = new_qty
            pos["peak_pnl_pct"] = 0.0
            pos["opened_ts"] = time.time()
            if auto_tp_pct is not None:
                pos["auto_tp_pct"] = float(auto_tp_pct)
            if auto_sl_pct is not None:
                pos["auto_sl_pct"] = float(auto_sl_pct)
            pos["total_bought_mxn"] += gross_mxn
            self.cash_mxn -= gross_mxn

            trade = {
                "id": str(uuid.uuid4())[:8],
                "timestamp": now_iso,
                "book": book,
                "side": "BUY",
                "price": round(exec_price, 6 if exec_price < 1 else 2),
                "amount": round(qty, 8),
                "total_mxn": round(gross_mxn, 2),
                "fee_mxn": round(fee_mxn, 2),
                "pnl_mxn": None,
                "pnl_pct": None,
                "source": source,
                "reason": reason,
                "confidence": confidence,
            }
            self.trades.append(trade)
            self._insert_trade_db(trade)
            self._save_state()
            return {"success": True, "trade": trade}

        elif side == "SELL":
            exec_price = float(ticker.get("bid") or ticker.get("last") or 0.0)
            if exec_price <= 0:
                return {"success": False, "error": "Precio de mercado inválido."}

            available_qty = pos["amount"]
            if available_qty <= 1e-9:
                return {"success": False, "error": f"No tienes posición abierta en {book.upper()}."}

            if crypto_amount is not None:
                qty = min(float(crypto_amount), available_qty)
            elif mxn_amount is not None:
                qty = min(float(mxn_amount) / exec_price, available_qty)
            else:
                qty = available_qty

            if qty * exec_price < 5.0 and qty < available_qty:
                return {"success": False, "error": "Monto de venta demasiado pequeño."}

            gross_mxn = qty * exec_price
            fee_mxn = gross_mxn * self.fee_rate
            net_mxn = gross_mxn - fee_mxn

            cost_basis = qty * pos["avg_buy_price"]
            realized_pnl = net_mxn - cost_basis
            pnl_pct = (realized_pnl / cost_basis * 100.0) if cost_basis > 0 else 0.0

            pos["amount"] = max(0.0, available_qty - qty)
            if pos["amount"] < 1e-9:
                pos["amount"] = 0.0
                pos["avg_buy_price"] = 0.0
                pos["peak_pnl_pct"] = 0.0
            pos["realized_pnl"] += realized_pnl
            pos["total_sold_mxn"] += net_mxn
            self.cash_mxn += net_mxn

            trade = {
                "id": str(uuid.uuid4())[:8],
                "timestamp": now_iso,
                "book": book,
                "side": "SELL",
                "price": round(exec_price, 6 if exec_price < 1 else 2),
                "amount": round(qty, 8),
                "total_mxn": round(net_mxn, 2),
                "fee_mxn": round(fee_mxn, 2),
                "pnl_mxn": round(realized_pnl, 2),
                "pnl_pct": round(pnl_pct, 2),
                "source": source,
                "reason": reason,
                "confidence": confidence,
            }
            self.trades.append(trade)
            self._insert_trade_db(trade)
            self._save_state()
            return {"success": True, "trade": trade}

        return {"success": False, "error": f"Lado de orden no soportado: {side}"}

    def compute_pnl_balance(self) -> Dict[str, Any]:
        """
        Genera el Balance Contable de Ganancias vs. Pérdidas (global y desglosado por moneda)
        sobre todo el historial de transacciones guardado.
        """
        sell_trades = [t for t in self.trades if t.get("side") == "SELL" and t.get("pnl_mxn") is not None]
        buy_trades = [t for t in self.trades if t.get("side") == "BUY"]

        wins = [t for t in sell_trades if float(t["pnl_mxn"]) > 0]
        losses = [t for t in sell_trades if float(t["pnl_mxn"]) < 0]
        breakeven = [t for t in sell_trades if float(t["pnl_mxn"]) == 0]

        gross_profit = sum(float(t["pnl_mxn"]) for t in wins)
        gross_loss = sum(float(t["pnl_mxn"]) for t in losses)  # negativo
        net_realized = gross_profit + gross_loss

        avg_win = (gross_profit / len(wins)) if wins else 0.0
        avg_loss = (gross_loss / len(losses)) if losses else 0.0
        profit_factor = (gross_profit / abs(gross_loss)) if abs(gross_loss) > 0 else (99.9 if gross_profit > 0 else 0.0)
        win_rate = (len(wins) / len(sell_trades) * 100.0) if sell_trades else 0.0

        best_trade = max(sell_trades, key=lambda x: float(x["pnl_mxn"])) if sell_trades else None
        worst_trade = min(sell_trades, key=lambda x: float(x["pnl_mxn"])) if sell_trades else None

        by_book_map: Dict[str, Dict[str, Any]] = {}
        for t in self.trades:
            b = t.get("book", "btc_mxn")
            entry = by_book_map.setdefault(
                b,
                {
                    "book": b,
                    "total_trades": 0,
                    "buys": 0,
                    "sells": 0,
                    "wins": 0,
                    "losses": 0,
                    "gross_profit_mxn": 0.0,
                    "gross_loss_mxn": 0.0,
                    "net_pnl_mxn": 0.0,
                    "volume_mxn": 0.0,
                },
            )
            entry["total_trades"] += 1
            entry["volume_mxn"] += float(t.get("total_mxn") or 0.0)
            if t.get("side") == "BUY":
                entry["buys"] += 1
            elif t.get("side") == "SELL":
                entry["sells"] += 1
                pnl = float(t.get("pnl_mxn") or 0.0)
                if pnl > 0:
                    entry["wins"] += 1
                    entry["gross_profit_mxn"] += pnl
                elif pnl < 0:
                    entry["losses"] += 1
                    entry["gross_loss_mxn"] += pnl
                entry["net_pnl_mxn"] += pnl

        by_book_list = []
        for b, d in by_book_map.items():
            sells = d["sells"]
            d["win_rate_pct"] = round((d["wins"] / sells * 100.0) if sells > 0 else 0.0, 1)
            d["gross_profit_mxn"] = round(d["gross_profit_mxn"], 2)
            d["gross_loss_mxn"] = round(d["gross_loss_mxn"], 2)
            d["net_pnl_mxn"] = round(d["net_pnl_mxn"], 2)
            d["volume_mxn"] = round(d["volume_mxn"], 2)
            by_book_list.append(d)

        by_book_list.sort(key=lambda x: x["net_pnl_mxn"], reverse=True)

        return {
            "total_transactions": len(self.trades),
            "buy_transactions": len(buy_trades),
            "sell_transactions": len(sell_trades),
            "winning_count": len(wins),
            "losing_count": len(losses),
            "breakeven_count": len(breakeven),
            "win_rate_pct": round(win_rate, 1),
            "gross_profit_mxn": round(gross_profit, 2),
            "gross_loss_mxn": round(gross_loss, 2),
            "net_realized_pnl_mxn": round(net_realized, 2),
            "avg_win_mxn": round(avg_win, 2),
            "avg_loss_mxn": round(avg_loss, 2),
            "profit_factor": round(profit_factor, 2),
            "best_trade": best_trade,
            "worst_trade": worst_trade,
            "by_book": by_book_list,
        }

    def export_trades_csv(self) -> str:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "ID",
            "Fecha_UTC",
            "Libro",
            "Lado",
            "Precio_MXN",
            "Cantidad_Cripto",
            "Total_MXN",
            "Comision_MXN",
            "Ganancia_Perdida_MXN",
            "Ganancia_Perdida_Pct",
            "Origen",
            "Motivo",
        ])
        for t in reversed(self.trades):
            writer.writerow([
                t.get("id"),
                t.get("timestamp"),
                t.get("book"),
                t.get("side"),
                t.get("price"),
                t.get("amount"),
                t.get("total_mxn"),
                t.get("fee_mxn"),
                t.get("pnl_mxn", ""),
                t.get("pnl_pct", ""),
                t.get("source"),
                t.get("reason"),
            ])
        return output.getvalue()

    def get_summary(
        self,
        tickers: Dict[str, Dict[str, Any]],
        active_book: str = "btc_mxn",
        opp_by_book: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        holdings_value_mxn = 0.0
        unrealized_pnl_total = 0.0
        realized_pnl_total = 0.0
        detailed_positions: Dict[str, Dict[str, Any]] = {}
        opp_map = opp_by_book or {}

        for book, pos in self.positions.items():
            ticker = tickers.get(book, {})
            mark_price = float(ticker.get("bid") or ticker.get("last") or pos["avg_buy_price"] or 0.0)
            qty = pos["amount"]
            avg_buy = pos["avg_buy_price"]
            mkt_val = qty * mark_price
            cost_basis = qty * avg_buy
            unr_pnl = (mkt_val * (1.0 - self.fee_rate) - cost_basis) if qty > 0 else 0.0
            unr_pnl_pct = (unr_pnl / cost_basis * 100.0) if cost_basis > 0 else 0.0
            if qty > 0:
                pos["peak_pnl_pct"] = max(float(pos.get("peak_pnl_pct", 0.0)), unr_pnl_pct)
            else:
                pos["peak_pnl_pct"] = 0.0

            opp_info = opp_map.get(book, {})
            auto_tp = float(opp_info.get("auto_tp_pct") or pos.get("auto_tp_pct") or 0.35)
            auto_sl = float(opp_info.get("auto_sl_pct") or pos.get("auto_sl_pct") or 0.65)
            auto_trail_arm = float(opp_info.get("auto_trail_arm_pct") or round(auto_tp * 0.48, 2))
            auto_trail_drop = float(opp_info.get("auto_trail_drop_pct") or round(auto_tp * 0.20, 2))

            pos["auto_tp_pct"] = auto_tp
            pos["auto_sl_pct"] = auto_sl

            holdings_value_mxn += mkt_val
            unrealized_pnl_total += unr_pnl
            realized_pnl_total += pos.get("realized_pnl", 0.0)

            detailed_positions[book] = {
                "book": book,
                "amount": round(qty, 8),
                "avg_buy_price": round(avg_buy, 6 if avg_buy < 1 else 2),
                "mark_price": round(mark_price, 6 if mark_price < 1 else 2),
                "market_value_mxn": round(mkt_val, 2),
                "unrealized_pnl_mxn": round(unr_pnl, 2),
                "unrealized_pnl_pct": round(unr_pnl_pct, 2),
                "peak_pnl_pct": round(float(pos.get("peak_pnl_pct", 0.0)), 2),
                "auto_tp_pct": auto_tp,
                "auto_sl_pct": auto_sl,
                "auto_trail_arm_pct": auto_trail_arm,
                "auto_trail_drop_pct": auto_trail_drop,
                "hold_seconds": int(time.time() - float(pos.get("opened_ts") or time.time())) if qty > 0 else 0,
                "realized_pnl_mxn": round(pos.get("realized_pnl", 0.0), 2),
            }

        if active_book not in detailed_positions:
            t = tickers.get(active_book, {})
            mp = float(t.get("bid") or t.get("last") or 0.0)
            opp_info = opp_map.get(active_book, {})
            detailed_positions[active_book] = {
                "book": active_book,
                "amount": 0.0,
                "avg_buy_price": 0.0,
                "mark_price": round(mp, 6 if mp < 1 else 2),
                "market_value_mxn": 0.0,
                "unrealized_pnl_mxn": 0.0,
                "unrealized_pnl_pct": 0.0,
                "peak_pnl_pct": 0.0,
                "auto_tp_pct": float(opp_info.get("auto_tp_pct", 0.35)),
                "auto_sl_pct": float(opp_info.get("auto_sl_pct", 0.65)),
                "auto_trail_arm_pct": float(opp_info.get("auto_trail_arm_pct", 0.16)),
                "auto_trail_drop_pct": float(opp_info.get("auto_trail_drop_pct", 0.07)),
                "realized_pnl_mxn": 0.0,
            }

        total_equity = self.cash_mxn + holdings_value_mxn
        total_return_mxn = total_equity - self.initial_cash_mxn
        total_return_pct = (total_return_mxn / self.initial_cash_mxn * 100.0) if self.initial_cash_mxn > 0 else 0.0

        active_ticker = tickers.get(active_book, {})
        active_last = float(active_ticker.get("last") or 0.0)
        if active_last > 0 and active_book not in self.benchmark_initial_prices:
            self.benchmark_initial_prices[active_book] = active_last

        bench_start = self.benchmark_initial_prices.get(active_book, active_last)
        benchmark_equity = (
            self.initial_cash_mxn * (active_last / bench_start) if bench_start > 0 else self.initial_cash_mxn
        )

        pnl_balance = self.compute_pnl_balance()
        total_fees = sum(float(t.get("fee_mxn", 0.0)) for t in self.trades)

        now_label = datetime.now().strftime("%H:%M:%S")
        if not self.equity_curve or self.equity_curve[-1]["time"] != now_label:
            self.equity_curve.append({
                "time": now_label,
                "equity": round(total_equity, 2),
                "benchmark": round(benchmark_equity, 2),
                "cash": round(self.cash_mxn, 2),
            })
            if len(self.equity_curve) > 120:
                self.equity_curve = self.equity_curve[-120:]

        return {
            "initial_cash_mxn": round(self.initial_cash_mxn, 2),
            "cash_mxn": round(self.cash_mxn, 2),
            "holdings_value_mxn": round(holdings_value_mxn, 2),
            "total_equity_mxn": round(total_equity, 2),
            "total_return_mxn": round(total_return_mxn, 2),
            "total_return_pct": round(total_return_pct, 2),
            "unrealized_pnl_mxn": round(unrealized_pnl_total, 2),
            "realized_pnl_mxn": round(pnl_balance["net_realized_pnl_mxn"], 2),
            "total_fees_mxn": round(total_fees, 2),
            "fee_rate": self.fee_rate,
            "win_rate_pct": pnl_balance["win_rate_pct"],
            "total_trades": len(self.trades),
            "closed_trades": pnl_balance["sell_transactions"],
            "pnl_balance": pnl_balance,
            "positions": detailed_positions,
            "recent_trades": list(reversed(self.trades[-150:])),
            "equity_curve": self.equity_curve,
        }
