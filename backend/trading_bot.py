import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class TradingBot:
    """
    Bot de Trading Modular para Bitso Paper Trading.
    Incluye cálculo de indicadores técnicos en tiempo real (SMA, RSI, OrderBook Imbalance)
    y un punto de extensión limpio (`predict_with_ai`) listo para conectar tu propio modelo
    de Machine Learning / Deep Learning / RL / LLM.
    """

    def __init__(self) -> None:
        self.enabled: bool = True
        self.multi_asset_auto: bool = True  # Escanea las mejores oportunidades
        self.auto_tp_sl_by_coin: bool = True  # TP y SL dinámicos automatizados
        self.strategy: str = "ai_custom"
        self.book: str = "btc_mxn"
        self.trade_size_pct: float = 45.0  # Asignación concentrada (máx 2 posiciones de ~45k cada una)
        self.take_profit_pct: float = 0.55  # Meta de Take Profit sustancial (+0.55% = ~$250 MXN)
        self.stop_loss_pct: float = 0.35    # SL estricto máximo (-0.35% = ~$155 MXN)
        self.trailing_arm_pct: float = 0.30 # Activa candado de ganancia al tocar +0.30%
        self.trailing_drop_pct: float = 0.08 # Asegura ganancia manteniendo al menos +0.22%
        self.min_hold_seconds: int = 240    # Periodo de maduración obligatorio (4 minutos anti-churn)
        self.cooldown_seconds: int = 75     # Cooldown entre órdenes del bot (elimina sobre-operación)
        self.last_trade_ts: float = 0.0
        self.last_signal: Dict[str, Any] = {
            "action": "HOLD",
            "confidence": 0.5,
            "reason": "Esperando activación o datos suficientes...",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "features": {},
        }
        self.decision_log: List[Dict[str, Any]] = []

    def update_config(self, cfg: Dict[str, Any]) -> Dict[str, Any]:
        if "enabled" in cfg:
            self.enabled = bool(cfg["enabled"])
        if "multi_asset_auto" in cfg:
            self.multi_asset_auto = bool(cfg["multi_asset_auto"])
        if "auto_tp_sl_by_coin" in cfg:
            self.auto_tp_sl_by_coin = bool(cfg["auto_tp_sl_by_coin"])
        if "strategy" in cfg and cfg["strategy"] in ("sma_rsi", "orderbook_imbalance", "ai_custom"):
            self.strategy = cfg["strategy"]
        if "book" in cfg:
            self.book = str(cfg["book"])
        if "trade_size_pct" in cfg:
            self.trade_size_pct = max(2.0, min(100.0, float(cfg["trade_size_pct"])))
        if "take_profit_pct" in cfg:
            self.take_profit_pct = max(0.05, float(cfg["take_profit_pct"]))
        if "stop_loss_pct" in cfg:
            self.stop_loss_pct = max(0.05, float(cfg["stop_loss_pct"]))
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
            "cooldown_seconds": self.cooldown_seconds,
            "last_signal": self.last_signal,
            "decision_log": self.decision_log[-25:],
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
        """
        Construye el vector de características (features) normalizadas en tiempo real
        que alimenta tanto a las estrategias clásicas como a tu futura IA.
        """
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

    # =========================================================================
    # PUNTO DE INTEGRACIÓN PARA TU IA (PyTorch / Scikit-Learn / XGBoost / LLM)
    # =========================================================================
    def predict_with_ai(self, features: Dict[str, float]) -> Dict[str, Any]:
        """
        Reemplaza el cuerpo de este método con tu propio modelo de IA entrenado:
            ejemplo:
                x = np.array([[features['rsi_14'], features['sma_diff_bps'], features['ob_imbalance']]])
                probs = self.model.predict_proba(x)[0]  # [p_hold, p_buy, p_sell]
        Por defecto ejecuta un modelo de scoring multifactorial ponderado (Neurona Lineal + Sigmoid).
        """
        # Score direccional combinando tendencia, reversión RSI y presión en libro de órdenes
        rsi_norm = (50.0 - features["rsi_14"]) / 50.0  # Positivo cuando está sobrevendido (<50)
        ob_norm = (features["ob_imbalance"] - 0.5) * 2.0  # [-1, +1] presión de compra en OrderBook
        trend_norm = max(-1.0, min(1.0, features["sma_diff_bps"] / 25.0))
        mom_norm = max(-1.0, min(1.0, features["momentum_5_bps"] / 30.0))

        # Pesos del ensemble de ejemplo
        alpha_score = (0.35 * ob_norm) + (0.30 * rsi_norm) + (0.20 * trend_norm) + (0.15 * mom_norm)
        confidence = min(0.98, round(0.50 + abs(alpha_score) * 0.48, 2))

        # Gestión automática de Take Profit / Stop Loss si tenemos posición abierta
        if features["exposure_ratio"] > 0.02:
            if features["unrealized_pnl_pct"] >= self.take_profit_pct:
                return {
                    "action": "SELL",
                    "confidence": 0.92,
                    "reason": f"[IA Risk Manager] Take Profit alcanzado ({features['unrealized_pnl_pct']:+.2f}% >= +{self.take_profit_pct:.2f}%)",
                }
            if features["unrealized_pnl_pct"] <= -self.stop_loss_pct:
                return {
                    "action": "SELL",
                    "confidence": 0.95,
                    "reason": f"[IA Risk Manager] Stop Loss activado ({features['unrealized_pnl_pct']:+.2f}% <= -{self.stop_loss_pct:.2f}%)",
                }

        if alpha_score >= 0.14 and features["exposure_ratio"] < 0.85:
            return {
                "action": "BUY",
                "confidence": confidence,
                "reason": (
                    f"[IA Score={alpha_score:+.2f}] Señal alcista: OB Imbalance={features['ob_imbalance']*100:.1f}%, "
                    f"RSI={features['rsi_14']:.1f}, ΔSMA={features['sma_diff_bps']:+.1f} bps"
                ),
            }
        elif alpha_score <= -0.14 and features["exposure_ratio"] > 0.02:
            return {
                "action": "SELL",
                "confidence": confidence,
                "reason": (
                    f"[IA Score={alpha_score:+.2f}] Señal bajista: OB Imbalance={features['ob_imbalance']*100:.1f}%, "
                    f"RSI={features['rsi_14']:.1f}, ΔSMA={features['sma_diff_bps']:+.1f} bps"
                ),
            }

        return {
            "action": "HOLD",
            "confidence": confidence,
            "reason": (
                f"[IA Score={alpha_score:+.2f}] Neutral (umbral ±0.14) | "
                f"RSI={features['rsi_14']:.1f}, OB={features['ob_imbalance']*100:.1f}%"
            ),
        }

    def evaluate(
        self,
        price_history: List[Dict[str, Any]],
        ticker: Dict[str, Any],
        order_book: Dict[str, Any],
        position: Dict[str, Any],
        cash_mxn: float,
        force: bool = False,
    ) -> Dict[str, Any]:
        """Evalúa el estado del mercado y devuelve la decisión del bot."""
        features = self.extract_features(price_history, ticker, order_book, position, cash_mxn)
        now_ts = time.time()
        now_iso = datetime.now(timezone.utc).isoformat()

        has_position = features["exposure_ratio"] > 0.02
        unr_pnl = features["unrealized_pnl_pct"]

        # 1. Reglas universales de protección (Take Profit / Stop Loss)
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

        # Verificar cooldown salvo cuando el usuario presiona "Forzar Paso del Bot"
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
        }
        self.last_signal = signal
        self.decision_log.append(signal)
        if len(self.decision_log) > 40:
            self.decision_log = self.decision_log[-40:]

        return signal

    def _run_strategy(self, features: Dict[str, float], has_position: bool, force: bool = False) -> Dict[str, Any]:
        if self.strategy == "ai_custom":
            res = self.predict_with_ai(features)
            if force and res["action"] == "HOLD":
                # Si el usuario fuerza evaluación manual y el score es moderado, mostrar acción demostrativa
                if features["ob_imbalance"] >= 0.48 and not has_position:
                    return {
                        "action": "BUY",
                        "confidence": 0.68,
                        "reason": f"[Paso Forzado IA] Entrada exploratoria con RSI={features['rsi_14']:.1f} y OB={features['ob_imbalance']*100:.1f}%",
                    }
            return res

        elif self.strategy == "orderbook_imbalance":
            imb = features["ob_imbalance"]
            spread = features["spread_bps"]
            if imb >= 0.56 and spread < 35.0:
                return {
                    "action": "BUY",
                    "confidence": round(min(0.95, imb + 0.15), 2),
                    "reason": f"Fuerte presión de compra en OrderBook Bitso ({imb*100:.1f}% bids vs asks, spread {spread:.1f} bps)",
                }
            elif imb <= 0.42 and has_position:
                return {
                    "action": "SELL",
                    "confidence": round(min(0.95, (1.0 - imb) + 0.15), 2),
                    "reason": f"Presión vendedora en OrderBook Bitso ({(1-imb)*100:.1f}% asks dominando)",
                }
            return {
                "action": "HOLD",
                "confidence": 0.55,
                "reason": f"OrderBook equilibrado (Bids: {imb*100:.1f}% / Asks: {(1-imb)*100:.1f}%)",
            }

        # Estrategia por defecto: "sma_rsi" (Cruce de Medias + RSI)
        rsi = features["rsi_14"]
        sma_diff = features["sma_diff_bps"]
        if rsi < 38.0 or (sma_diff > 1.5 and rsi < 62.0):
            return {
                "action": "BUY",
                "confidence": 0.78 if rsi < 38.0 else 0.72,
                "reason": (
                    f"Señal de Compra SMA+RSI: RSI={rsi:.1f} "
                    f"({'Sobreventa' if rsi < 38 else 'Tendencia Alcista'}), ΔSMA={sma_diff:+.1f} bps"
                ),
            }
        elif has_position and (rsi > 65.0 or sma_diff < -2.5):
            return {
                "action": "SELL",
                "confidence": 0.80,
                "reason": f"Señal de Venta SMA+RSI: RSI={rsi:.1f}, ΔSMA={sma_diff:+.1f} bps",
            }

        return {
            "action": "HOLD",
            "confidence": 0.52,
            "reason": f"Esperando cruce óptimo (RSI={rsi:.1f}, ΔSMA={sma_diff:+.1f} bps)",
        }
