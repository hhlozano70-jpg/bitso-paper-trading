import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

STATE_FILE = os.path.join(os.path.dirname(__file__), "portfolio_state.json")


class PaperTradingEngine:
    """
    Motor de simulación financiera (Paper Trading) con precios reales de Bitso.
    Ejecuta compras al precio 'ask' real y ventas al precio 'bid' real, aplicando
    comisiones configurables y calculando PnL realizado y no realizado en tiempo real.
    """

    def __init__(self, initial_cash_mxn: float = 100_000.0, fee_rate: float = 0.0015) -> None:
        self.initial_cash_mxn = initial_cash_mxn
        self.cash_mxn = initial_cash_mxn
        self.fee_rate = fee_rate  # 0.15% por defecto (ajustable en la UI)
        self.positions: Dict[str, Dict[str, float]] = {}
        self.trades: List[Dict[str, Any]] = []
        self.equity_curve: List[Dict[str, Any]] = []
        self.benchmark_initial_prices: Dict[str, float] = {}
        self._load_state()

    def _ensure_book(self, book: str) -> Dict[str, float]:
        if book not in self.positions:
            self.positions[book] = {
                "amount": 0.0,
                "avg_buy_price": 0.0,
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
                "trades": self.trades[-200:],
                "equity_curve": self.equity_curve[-150:],
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
            self.fee_rate = float(data.get("fee_rate", 0.0015))
            self.positions = data.get("positions", {})
            self.trades = data.get("trades", [])
            self.equity_curve = data.get("equity_curve", [])
            self.benchmark_initial_prices = data.get("benchmark_initial_prices", {})
        except Exception as exc:
            print(f"[PaperTradingEngine] Error cargando estado: {exc}")

    def reset(self, initial_cash_mxn: float = 100_000.0, fee_rate: Optional[float] = None) -> Dict[str, Any]:
        self.initial_cash_mxn = initial_cash_mxn
        self.cash_mxn = initial_cash_mxn
        if fee_rate is not None:
            self.fee_rate = fee_rate
        self.positions = {}
        self.trades = []
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
    ) -> Dict[str, Any]:
        """
        Ejecuta una orden simulada contra los precios reales de Bitso:
        - BUY usa el precio 'ask' de Bitso (precio al que los vendedores ofrecen).
        - SELL usa el precio 'bid' de Bitso (precio al que los compradores pagan).
        """
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
            self._save_state()
            return {"success": True, "trade": trade}

        return {"success": False, "error": f"Lado de orden no soportado: {side}"}

    def get_summary(self, tickers: Dict[str, Dict[str, Any]], active_book: str = "btc_mxn") -> Dict[str, Any]:
        """Calcula la valuación en tiempo real del portafolio usando los precios 'bid' actuales de Bitso."""
        holdings_value_mxn = 0.0
        unrealized_pnl_total = 0.0
        realized_pnl_total = 0.0
        detailed_positions: Dict[str, Dict[str, Any]] = {}

        for book, pos in self.positions.items():
            ticker = tickers.get(book, {})
            mark_price = float(ticker.get("bid") or ticker.get("last") or pos["avg_buy_price"] or 0.0)
            qty = pos["amount"]
            avg_buy = pos["avg_buy_price"]
            mkt_val = qty * mark_price
            cost_basis = qty * avg_buy
            unr_pnl = (mkt_val * (1.0 - self.fee_rate) - cost_basis) if qty > 0 else 0.0
            unr_pnl_pct = (unr_pnl / cost_basis * 100.0) if cost_basis > 0 else 0.0

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
                "realized_pnl_mxn": round(pos.get("realized_pnl", 0.0), 2),
            }

        # Asegurar que el libro activo siempre aparezca aunque tenga posición 0
        if active_book not in detailed_positions:
            t = tickers.get(active_book, {})
            mp = float(t.get("bid") or t.get("last") or 0.0)
            detailed_positions[active_book] = {
                "book": active_book,
                "amount": 0.0,
                "avg_buy_price": 0.0,
                "mark_price": round(mp, 2),
                "market_value_mxn": 0.0,
                "unrealized_pnl_mxn": 0.0,
                "unrealized_pnl_pct": 0.0,
                "realized_pnl_mxn": 0.0,
            }

        total_equity = self.cash_mxn + holdings_value_mxn
        total_return_mxn = total_equity - self.initial_cash_mxn
        total_return_pct = (total_return_mxn / self.initial_cash_mxn * 100.0) if self.initial_cash_mxn > 0 else 0.0

        # Benchmark Buy & Hold en el libro activo
        active_ticker = tickers.get(active_book, {})
        active_last = float(active_ticker.get("last") or 0.0)
        if active_last > 0 and active_book not in self.benchmark_initial_prices:
            self.benchmark_initial_prices[active_book] = active_last

        bench_start = self.benchmark_initial_prices.get(active_book, active_last)
        benchmark_equity = (
            self.initial_cash_mxn * (active_last / bench_start) if bench_start > 0 else self.initial_cash_mxn
        )

        # Estadísticas de trades cerrados (SELL)
        sell_trades = [t for t in self.trades if t.get("side") == "SELL" and t.get("pnl_mxn") is not None]
        winning_trades = [t for t in sell_trades if float(t["pnl_mxn"]) > 0]
        win_rate = (len(winning_trades) / len(sell_trades) * 100.0) if sell_trades else 0.0
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
            "realized_pnl_mxn": round(realized_pnl_total, 2),
            "total_fees_mxn": round(total_fees, 2),
            "fee_rate": self.fee_rate,
            "win_rate_pct": round(win_rate, 1),
            "total_trades": len(self.trades),
            "closed_trades": len(sell_trades),
            "positions": detailed_positions,
            "recent_trades": list(reversed(self.trades[-50:])),
            "equity_curve": self.equity_curve,
        }
