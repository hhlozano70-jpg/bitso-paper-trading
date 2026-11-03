import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from trend_pullback_engine import TrendPullbackEngine


class TradingBot:
    """
    Bot Institucional de Trading para Bitso Paper Trading.
    Estrategia Principal: 'trend_pullback_h1_m15' (Tendencia H1 + Retroceso M15 + Ratio 1:2)
    Reglas de Compra: 6/6
    Reglas de Venta: 6/6
    Filtros de Exclusión (No operar): 5
    Ratio Riesgo/Beneficio: 1:2 Estricto
    """

    SUPPORTED_STRATEGIES = (
        "trend_pullback_h1_m15",
        "ai_custom",
        "orderbook_imbalance",
        "sma_rsi",
    )

    def __init__(self) -> None:
        self.enabled: bool = True
        self.multi_asset_auto: bool = True  # Escaneo automático de oportunidades
        self.auto_tp_sl_by_coin: bool = True  # Gestión dinámica 1:2 R:R
        self.strategy: str = "trend_pullback_h1_m15"  # Estrategia por defecto
        self.book: str = "btc_mxn"
        self.trade_size_pct: float = 40.0  # Asignación por operación (2 posiciones principales)
        self.take_profit_pct: float = 1.00  # TP base 1:2 (+1.00% meta)
        self.stop_loss_pct: float = 0.50    # SL base 1:2 (-0.50% riesgo)
        self.risk_reward_ratio: float = 2.0  # Exactamente 1:2
        self.trailing_arm_pct: float = 0.0   # Desactivado para no cortar ganancias prematuramente
        self.trailing_drop_pct: float = 0.0
        self.min_hold_seconds: int = 180    # Tiempo mínimo de maduración de la posición
        self.cooldown_seconds: int = 60     # Cooldown entre órdenes
        self.last_trade_ts: float = 0.0
        self.trend_engine = TrendPullbackEngine()
        self.last_checklist: Dict[str, Any] = {}
        self.last_signal: Dict[str, Any] = {
            "action": "HOLD",
            "confidence": 0.5,
            "reason": "Iniciando motor de tendencia H1 / retroceso M15...",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "features": {},
            "checklist": {},
            "risk_reward": {"ratio": "1:2", "sl_pct": 0.50, "tp_pct": 1.00},
        }
        self.decision_log: List[Dict[str, Any]] = []

    def update_config(self, cfg: Dict[str, Any]) -> Dict[str, Any]:
        if "enabled" in cfg:
            self.enabled = bool(cfg["enabled"])
        if "multi_asset_auto" in cfg:
            self.multi_asset_auto = bool(cfg["multi_asset_auto"])
        if "auto_tp_sl_by_coin" in cfg:
            self.auto_tp_sl_by_coin = bool(cfg["auto_tp_sl_by_coin"])
        if "strategy" in cfg and cfg["strategy"] in self.SUPPORTED_STRATEGIES:
            self.strategy = cfg["strategy"]
        if "book" in cfg:
            self.book = str(cfg["book"])
        if "trade_size_pct" in cfg:
            self.trade_size_pct = max(2.0, min(100.0, float(cfg["trade_size_pct"])))
        if "stop_loss_pct" in cfg:
            self.stop_loss_pct = max(0.15, float(cfg["stop_loss_pct"]))
            # Mantener relación 1:2 estricta
            self.take_profit_pct = round(self.stop_loss_pct * self.risk_reward_ratio, 2)
        if "take_profit_pct" in cfg and "stop_loss_pct" not in cfg:
            self.take_profit_pct = max(0.30, float(cfg["take_profit_pct"]))
        if "cooldown_seconds" in cfg:
            self.cooldown_seconds = max(2, int(cfg["cooldown_seconds"]))
        return self.get_config()

    def get_config(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "multi_asset_auto": self.multi_asset_auto,
            "auto_tp_sl_by_coin": self.auto_tp_sl_by_coin,
            "strategy": self.strategy,
            "book": self.book,
            "trade_size_pct": self.trade_size_pct,
            "take_profit_pct": self.take_profit_pct,
            "stop_loss_pct": self.stop_loss_pct,
            "risk_reward_ratio": "1:2",
            "cooldown_seconds": self.cooldown_seconds,
            "last_signal": self.last_signal,
            "last_checklist": self.last_checklist,
            "decision_log": self.decision_log[-30:],
        }

    @staticmethod
    def compute_rsi(prices: List[float], period: int = 14) -> float:
        if len(prices) < period + 1:
            return 50.0
        deltas = [prices[i] - prices[i - 1] for i in range(-period, 0)]
        gains = [d for d in deltas if d > 0]
        losses = [-d for d in deltas if d < 0]
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        if avg_loss == 0:
            return 100.0 if avg_gain > 0 else 50.0
        rs = avg_gain / avg_loss
        return round(100.0 - (100.0 / (1.0 + rs)), 2)

    def extract_features(
        self,
        price_history: List[Dict[str, Any]],
        ticker: Dict[str, Any],
        order_book: Dict[str, Any],
        position: Dict[str, Any],
        cash_mxn: float,
    ) -> Dict[str, float]:
        prices = [float(p["price"]) for p in price_history if p.get("price", 0) > 0]
        last_price = float(ticker.get("last") or (prices[-1] if prices else 0.0))
        if not prices and last_price > 0:
            prices = [last_price]

        sma_short = sum(prices[-5:]) / len(prices[-5:]) if prices else last_price
        sma_long = sum(prices[-18:]) / len(prices[-18:]) if prices else last_price
        rsi_14 = self.compute_rsi(prices, period=min(14, max(3, len(prices) - 1)))

        sma_diff_bps = ((sma_short - sma_long) / sma_long * 10000.0) if sma_long > 0 else 0.0
        momentum_5_bps = (
            ((last_price - prices[-5]) / prices[-5] * 10000.0)
            if len(prices) >= 5 and prices[-5] > 0
            else 0.0
        )

        ob_imbalance = float(order_book.get("imbalance", 0.5))
        spread_bps = float(ticker.get("spread_bps", 0.0))

        pos_amount = float(position.get("amount", 0.0))
        pos_val_mxn = pos_amount * last_price
        total_eq = cash_mxn + pos_val_mxn
        exposure_ratio = (pos_val_mxn / total_eq) if total_eq > 0 else 0.0
        unrealized_pnl_pct = float(position.get("unrealized_pnl_pct", 0.0))

        return {
            "last_price": round(last_price, 2),
            "sma_short_5": round(sma_short, 2),
            "sma_long_18": round(sma_long, 2),
            "sma_diff_bps": round(sma_diff_bps, 2),
            "rsi_14": round(rsi_14, 2),
            "momentum_5_bps": round(momentum_5_bps, 2),
            "ob_imbalance": round(ob_imbalance, 4),
            "spread_bps": round(spread_bps, 2),
            "exposure_ratio": round(exposure_ratio, 4),
            "unrealized_pnl_pct": round(unrealized_pnl_pct, 3),
        }

    def predict_with_ai(self, features: Dict[str, float]) -> Dict[str, Any]:
        """Punto de integración para modelos de ML adicionales."""
        rsi_norm = (50.0 - features["rsi_14"]) / 50.0
        ob_norm = (features["ob_imbalance"] - 0.5) * 2.0
        trend_norm = max(-1.0, min(1.0, features["sma_diff_bps"] / 25.0))
        mom_norm = max(-1.0, min(1.0, features["momentum_5_bps"] / 30.0))

        alpha_score = (0.35 * ob_norm) + (0.30 * rsi_norm) + (0.20 * trend_norm) + (0.15 * mom_norm)
        confidence = min(0.98, round(0.50 + abs(alpha_score) * 0.48, 2))

        if alpha_score >= 0.16 and features["exposure_ratio"] < 0.85:
            return {
                "action": "BUY",
                "confidence": confidence,
                "reason": f"[IA Score={alpha_score:+.2f}] Señal alcista: OB={features['ob_imbalance']*100:.1f}%, RSI={features['rsi_14']:.1f}",
            }
        elif alpha_score <= -0.16 and features["exposure_ratio"] > 0.02:
            return {
                "action": "SELL",
                "confidence": confidence,
                "reason": f"[IA Score={alpha_score:+.2f}] Señal bajista: OB={features['ob_imbalance']*100:.1f}%, RSI={features['rsi_14']:.1f}",
            }

        return {
            "action": "HOLD",
            "confidence": confidence,
            "reason": f"[IA Neutral={alpha_score:+.2f}] Esperando configuración de alta certeza",
        }

    def evaluate(
        self,
        price_history: List[Dict[str, Any]],
        ticker: Dict[str, Any],
        order_book: Dict[str, Any],
        position: Dict[str, Any],
        cash_mxn: float,
        candles_h1: Optional[List[Dict[str, float]]] = None,
        candles_m15: Optional[List[Dict[str, float]]] = None,
        force: bool = False,
    ) -> Dict[str, Any]:
        """
        Evalúa el estado del mercado utilizando la estrategia configurada.
        Por defecto evalúa la Estrategia Institucional de Tendencia H1 + Retroceso M15 con R:R 1:2.
        """
        features = self.extract_features(price_history, ticker, order_book, position, cash_mxn)
        now_ts = time.time()
        now_iso = datetime.now(timezone.utc).isoformat()
        has_position = features["exposure_ratio"] > 0.02
        unr_pnl = features["unrealized_pnl_pct"]
        book = ticker.get("book", self.book)
        last_price = float(ticker.get("last", 0.0))
        spread_bps = float(ticker.get("spread_bps", 0.0))

        # 1. EVALUACIÓN CON LA ESTRATEGIA PRINCIPAL: 'trend_pullback_h1_m15'
        if self.strategy == "trend_pullback_h1_m15" and candles_h1 and candles_m15:
            analysis = self.trend_engine.evaluate_strategy(
                book=book,
                current_price=last_price,
                candles_h1=candles_h1,
                candles_m15=candles_m15,
                spread_bps=spread_bps,
                available_cash_mxn=cash_mxn,
                position_exposure=features["exposure_ratio"],
            )
            self.last_checklist = {
                "book": book,
                "h1": analysis.get("h1"),
                "m15": analysis.get("m15"),
                "checklist_buy": analysis.get("checklist_buy"),
                "checklist_sell": analysis.get("checklist_sell"),
                "exclusion_filters": analysis.get("exclusion_filters"),
                "risk_reward": analysis.get("risk_reward"),
            }

            # Si ya tenemos posición abierta en este activo, gestionar salida 1:2
            if has_position:
                sl_target = float(position.get("auto_sl_pct") or self.stop_loss_pct)
                tp_target = float(position.get("auto_tp_pct") or (sl_target * 2.0))

                # Salida por Take Profit 1:2
                if unr_pnl >= tp_target:
                    decision = {
                        "action": "SELL",
                        "confidence": 0.98,
                        "reason": f"[Take Profit 1:2 Alcanzado] {book.upper()} ganó +{unr_pnl:+.2f}% (Meta 1:2: +{tp_target:.2f}%)",
                    }
                # Salida por Stop Loss estructural
                elif unr_pnl <= -sl_target:
                    decision = {
                        "action": "SELL",
                        "confidence": 0.98,
                        "reason": f"[Stop Loss Estructural] {book.upper()} cortó en {unr_pnl:+.2f}% (SL: -{sl_target:.2f}%)",
                    }
                # Salida por señal de quiebre bajista M15
                elif analysis["signal"] == "SELL":
                    decision = {
                        "action": "SELL",
                        "confidence": analysis["confidence"],
                        "reason": f"[Salida Técnica M15] {analysis['reason']}",
                    }
                else:
                    decision = {
                        "action": "HOLD",
                        "confidence": 0.50,
                        "reason": f"Manteniendo posición abierta en {book.upper()} (PnL: {unr_pnl:+.2f}% | TP: +{tp_target:.2f}% | SL: -{sl_target:.2f}%)",
                    }
            else:
                # Sin posición: evaluar entrada según señal 6/6
                decision = {
                    "action": analysis["signal"],
                    "confidence": analysis["confidence"],
                    "reason": analysis["reason"],
                }

        else:
            # Estrategias alternativas / secundarias
            if has_position:
                if unr_pnl >= self.take_profit_pct:
                    decision = {
                        "action": "SELL",
                        "confidence": 0.94,
                        "reason": f"Take Profit ejecutado ({unr_pnl:+.2f}% >= +{self.take_profit_pct:.2f}%)",
                    }
                elif unr_pnl <= -self.stop_loss_pct:
                    decision = {
                        "action": "SELL",
                        "confidence": 0.96,
                        "reason": f"Stop Loss ejecutado ({unr_pnl:+.2f}% <= -{self.stop_loss_pct:.2f}%)",
                    }
                else:
                    decision = self._run_strategy(features, has_position, force=force)
            else:
                decision = self._run_strategy(features, has_position, force=force)

        # Respetar tiempo de enfriamiento (salvo cuando force=True)
        if not force and decision["action"] in ("BUY", "SELL"):
            elapsed = now_ts - self.last_trade_ts
            if elapsed < self.cooldown_seconds:
                remaining = int(self.cooldown_seconds - elapsed)
                decision = {
                    "action": "HOLD",
                    "confidence": decision["confidence"],
                    "reason": f"En enfriamiento ({remaining}s restantes) — Señal previa: {decision['reason']}",
                }

        signal = {
            "action": decision["action"],
            "confidence": decision["confidence"],
            "reason": decision["reason"],
            "strategy": self.strategy,
            "timestamp": now_iso,
            "features": features,
            "checklist": self.last_checklist,
            "risk_reward": {
                "ratio": "1:2",
                "sl_pct": self.stop_loss_pct,
                "tp_pct": self.take_profit_pct,
            },
        }
        self.last_signal = signal
        self.decision_log.append(signal)
        if len(self.decision_log) > 40:
            self.decision_log = self.decision_log[-40:]

        return signal

    def _run_strategy(self, features: Dict[str, float], has_position: bool, force: bool = False) -> Dict[str, Any]:
        if self.strategy == "ai_custom":
            return self.predict_with_ai(features)
        elif self.strategy == "orderbook_imbalance":
            imb = features["ob_imbalance"]
            spread = features["spread_bps"]
            if imb >= 0.58 and spread < 25.0:
                return {
                    "action": "BUY",
                    "confidence": 0.88,
                    "reason": f"Fuerte presión compradora en OrderBook ({imb*100:.1f}% bids)",
                }
            elif imb <= 0.42 and has_position:
                return {
                    "action": "SELL",
                    "confidence": 0.88,
                    "reason": f"Presión vendedora en OrderBook ({(1-imb)*100:.1f}% asks)",
                }
            return {
                "action": "HOLD",
                "confidence": 0.50,
                "reason": f"OrderBook equilibrado ({imb*100:.1f}% bids)",
            }
        else:
            # sma_rsi
            rsi = features["rsi_14"]
            sma_diff = features["sma_diff_bps"]
            if rsi < 35.0 and sma_diff > 0:
                return {
                    "action": "BUY",
                    "confidence": 0.80,
                    "reason": f"Rebote de sobreventa RSI ({rsi:.1f}) con SMA alineada",
                }
            elif rsi > 70.0 and has_position:
                return {
                    "action": "SELL",
                    "confidence": 0.85,
                    "reason": f"Toma de ganancia por sobrecompra RSI ({rsi:.1f})",
                }
            return {
                "action": "HOLD",
                "confidence": 0.50,
                "reason": f"RSI={rsi:.1f}, SMA Diff={sma_diff:+.1f} bps",
            }
