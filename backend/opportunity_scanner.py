import math
from typing import Any, Dict, List


class OpportunityScanner:
    """
    Escáner Cuantitativo Multi-Activo de Alta Frecuencia (Scalping) y Cálculo Dinámico
    de Take Profit / Stop Loss por Moneda para Bitso.
    """

    ARBITRAGE_PAIRS = [
        {"symbol": "BTC", "name": "Bitcoin", "mxn_book": "btc_mxn", "usd_book": "btc_usd"},
        {"symbol": "ETH", "name": "Ethereum", "mxn_book": "eth_mxn", "usd_book": "eth_usd"},
        {"symbol": "SOL", "name": "Solana", "mxn_book": "sol_mxn", "usd_book": "sol_usd"},
        {"symbol": "XRP", "name": "Ripple", "mxn_book": "xrp_mxn", "usd_book": "xrp_usd"},
        {"symbol": "LTC", "name": "Litecoin", "mxn_book": "ltc_mxn", "usd_book": "ltc_usd"},
        {"symbol": "MANA", "name": "Decentraland", "mxn_book": "mana_mxn", "usd_book": "mana_usd"},
    ]

    @staticmethod
    def _compute_rsi(prices: List[float], fallback_range_pos: float) -> float:
        anchor = max(20.0, min(84.0, 26.0 + fallback_range_pos * 0.52))
        if len(prices) < 5:
            return round(anchor, 1)
        distinct_prices = [prices[0]]
        for p in prices[1:]:
            if abs(p - distinct_prices[-1]) > 1e-9:
                distinct_prices.append(p)
        if len(distinct_prices) < 4:
            return round(anchor, 1)

        period = min(14, len(distinct_prices) - 1)
        deltas = [distinct_prices[i] - distinct_prices[i - 1] for i in range(-period, 0)]
        gains = [d for d in deltas if d > 0]
        losses = [-d for d in deltas if d < 0]
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        if avg_loss == 0:
            return round(74.0 if avg_gain > 0 else anchor, 1)
        rs = avg_gain / avg_loss
        raw_rsi = 100.0 - (100.0 / (1.0 + rs))
        weight = min(1.0, len(distinct_prices) / 14.0)
        return round(raw_rsi * weight + anchor * (1.0 - weight), 1)

    @staticmethod
    def compute_dynamic_tp_sl(
        volatility_24h_pct: float,
        prices: List[float],
        spread_bps: float,
        vwap_diff_pct: float,
        rsi_14: float,
        category: str,
        fee_rate: float = 0.0003,
    ) -> Dict[str, float]:
        """
        Calcula automáticamente el Take Profit (%), Stop Loss (%) y Trailing Lock (%)
        específicos para cada moneda según sus últimos datos en tiempo real:
          - Volatilidad de los últimos ticks (ATR / desviación intradía)
          - Amplitud del rango de 24h (volatility_24h_pct)
          - Costo friccional real de esa moneda (spread_bps + comisiones de entrada/salida)
          - Distancia disponible hacia el VWAP o zona de resistencia
        """
        # 1. Volatilidad reciente de ticks (en %)
        if len(prices) >= 4:
            pct_changes = [
                abs((prices[i] - prices[i - 1]) / prices[i - 1] * 100.0)
                for i in range(max(1, len(prices) - 15), len(prices))
                if prices[i - 1] > 0
            ]
            nonzero_changes = [c for c in pct_changes if c > 0.0001]
            tick_atr_pct = (sum(nonzero_changes) / len(nonzero_changes)) if nonzero_changes else (volatility_24h_pct / 28.0)
        else:
            tick_atr_pct = max(0.05, volatility_24h_pct / 28.0)

        # 2. Piso mínimo de costo operativo (Spread + 2x Fee) en %
        roundtrip_fee_pct = fee_rate * 200.0  # ej. 0.0003 * 200 = 0.06%
        spread_pct = spread_bps / 100.0
        friction_floor_pct = roundtrip_fee_pct + (spread_pct * 0.65)

        # 3. Volatilidad combinada de corto plazo para Scalping
        scalp_move_pct = max(tick_atr_pct * 2.4, volatility_24h_pct * 0.065)

        # Ajustar según categoría del activo
        if category in ("Divisas & FX", "Oro & RWA"):
            base_tp = max(0.14, min(0.45, friction_floor_pct + scalp_move_pct * 0.8))
            base_sl = max(0.28, min(0.75, base_tp * 1.45))
        elif category in ("Acciones", "Futuros"):
            # Acciones de Wall Street y Futuros CME tienen spreads ultra bajos (1.8-2.5 bps) ideales para Scalping
            base_tp = max(0.18, min(0.65, friction_floor_pct + scalp_move_pct * 0.95))
            base_sl = max(0.32, min(0.85, base_tp * 1.35))
        elif category == "Alta Volatilidad":
            base_tp = max(0.32, min(1.25, friction_floor_pct + scalp_move_pct * 1.35))
            base_sl = max(0.55, min(1.50, base_tp * 1.30))
        else:
            # Cripto MXN y Layer-1 / DeFi
            base_tp = max(0.20, min(0.85, friction_floor_pct + scalp_move_pct * 1.10))
            base_sl = max(0.40, min(1.15, base_tp * 1.35))

        # Si la moneda está muy descontada bajo VWAP, hay mayor recorrido alcista potencial
        if vwap_diff_pct < -0.8:
            base_tp = min(1.20, base_tp * 1.15)
        # Si el RSI ya está arriba de 58, hacer un scalp ultra rápido antes de que se agote
        if rsi_14 >= 58.0:
            base_tp = max(friction_floor_pct + 0.10, base_tp * 0.80)

        auto_tp = round(base_tp, 2)
        auto_sl = round(base_sl, 2)
        # Trailing Stop se activa al alcanzar el 48% del recorrido hacia el Take Profit
        auto_trail_arm = round(max(0.09, auto_tp * 0.48), 2)
        auto_trail_drop = round(max(0.04, auto_tp * 0.20), 2)

        return {
            "auto_tp_pct": auto_tp,
            "auto_sl_pct": auto_sl,
            "auto_trail_arm_pct": auto_trail_arm,
            "auto_trail_drop_pct": auto_trail_drop,
            "tick_atr_pct": round(tick_atr_pct, 3),
        }

    def scan_all_assets(
        self,
        tickers: Dict[str, Dict[str, Any]],
        price_history_by_book: Dict[str, List[Dict[str, Any]]],
        positions: Dict[str, Dict[str, Any]],
        fee_rate: float = 0.0003,
    ) -> List[Dict[str, Any]]:
        opportunities: List[Dict[str, Any]] = []

        for book, tk in tickers.items():
            last = float(tk.get("last") or 0.0)
            if last <= 0:
                continue

            high = float(tk.get("high") or last)
            low = float(tk.get("low") or last)
            vwap = float(tk.get("vwap") or last)
            change_24_pct = float(tk.get("change_24_pct") or 0.0)
            spread_bps = float(tk.get("spread_bps") or 0.0)
            category = tk.get("category", "Cripto")

            span_24h = high - low
            range_pos_pct = ((last - low) / span_24h * 100.0) if span_24h > 0 else 50.0
            range_pos_pct = max(0.0, min(100.0, range_pos_pct))
            volatility_24h_pct = (span_24h / low * 100.0) if low > 0 else 0.0

            vwap_diff_pct = ((last - vwap) / vwap * 100.0) if vwap > 0 else 0.0

            hist = price_history_by_book.get(book, [])
            prices = [float(p["price"]) for p in hist if float(p.get("price", 0)) > 0]
            rsi_14 = self._compute_rsi(prices, range_pos_pct)

            if len(prices) >= 3:
                sma_short = sum(prices[-4:]) / len(prices[-4:])
                sma_long = sum(prices[-15:]) / len(prices[-15:])
                sma_diff_bps = ((sma_short - sma_long) / sma_long * 10000.0) if sma_long > 0 else 0.0
                tick_bounce_bps = ((last - prices[-3]) / prices[-3] * 10000.0) if prices[-3] > 0 else 0.0
            else:
                sma_diff_bps = 0.0
                tick_bounce_bps = 0.0

            # Calcular TP y SL automatizados para esta moneda según sus últimos datos
            dyn_targets = self.compute_dynamic_tp_sl(
                volatility_24h_pct=volatility_24h_pct,
                prices=prices,
                spread_bps=spread_bps,
                vwap_diff_pct=vwap_diff_pct,
                rsi_14=rsi_14,
                category=category,
                fee_rate=fee_rate,
            )

            # Score Cuantitativo para Scalping de Alta Frecuencia
            score = 52.0
            reasons: List[str] = []
            setup_type = "Scalp de Liquidez"

            is_bouncing = sma_diff_bps >= -1.2 and tick_bounce_bps >= -0.5

            if vwap_diff_pct <= -0.18 and is_bouncing:
                bonus = min(18.0, abs(vwap_diff_pct) * 10.0)
                score += bonus
                setup_type = "Scalp Rebote bajo VWAP"
                reasons.append(f"Descuento {vwap_diff_pct:.2f}% vs VWAP")
            elif vwap_diff_pct <= -0.60 and not is_bouncing:
                score -= 6.0
                setup_type = "Esperando Giro Alcista"
                reasons.append(f"Bajo VWAP ({vwap_diff_pct:.2f}%), vigilando piso")
            elif sma_diff_bps > 0.8:
                score += 13.0
                setup_type = "Scalp Micro-Tendencia Alcista"
                reasons.append(f"Impulso alcista (+{sma_diff_bps:.1f} bps SMA)")

            if range_pos_pct <= 40.0 and is_bouncing:
                support_bonus = (42.0 - range_pos_pct) * 0.45
                score += support_bonus
                if "VWAP" in setup_type:
                    setup_type = "Scalp Doble Confluencia"
                else:
                    setup_type = "Scalp en Soporte 24h"
                reasons.append(f"Soporte 24h ({range_pos_pct:.0f}%)")
            elif range_pos_pct >= 72.0 and change_24_pct > 0.4 and is_bouncing:
                score += 11.0
                setup_type = "Scalp Breakout Rápido"
                reasons.append(f"Breakout (+{change_24_pct:+.2f}% 24h)")

            if 28.0 <= rsi_14 <= 54.0 and is_bouncing:
                score += 9.0
                reasons.append(f"RSI óptimo ({rsi_14:.1f})")
            elif rsi_14 >= 74.0:
                score -= 12.0
                reasons.append(f"RSI alto ({rsi_14:.1f})")

            # Premio por spread estrecho para rotar rápido con ganancias
            if spread_bps <= 5.0:
                score += 10.0
                reasons.append(f"Spread ultra bajo ({spread_bps:.1f} bps)")
            elif spread_bps <= 14.0:
                score += 6.0
                reasons.append(f"Spread líquido ({spread_bps:.1f} bps)")
            elif spread_bps > 24.0:
                score -= min(22.0, (spread_bps - 20.0) * 0.55)

            if category in ("Oro & RWA", "Divisas & FX") and change_24_pct >= 0:
                score += 5.0
                if setup_type == "Scalp de Liquidez":
                    setup_type = "Scalp Refugio / FX"

            score = round(max(12.0, min(98.0, score)), 1)

            if score >= 70.0:
                signal = "STRONG_BUY"
                signal_label = "SCALP COMPRA FUERTE"
            elif score >= 58.0:
                signal = "BUY"
                signal_label = "SCALP COMPRA"
            elif score <= 36.0:
                signal = "SELL"
                signal_label = "TOMA UTILIDAD / VENTA"
            else:
                signal = "NEUTRAL"
                signal_label = "OBSERVAR"

            if not reasons:
                reasons.append(
                    f"TP Auto +{dyn_targets['auto_tp_pct']}% / SL -{dyn_targets['auto_sl_pct']}% | RSI {rsi_14:.1f}"
                )

            pos_info = positions.get(book, {})
            held_qty = float(pos_info.get("amount", 0.0))

            opportunities.append({
                "book": book,
                "name": tk.get("name", book),
                "symbol": tk.get("symbol", book),
                "pair": tk.get("pair", book),
                "category": category,
                "quote": tk.get("quote", "MXN"),
                "last": last,
                "last_native": tk.get("last_native", last),
                "bid": tk.get("bid", last),
                "ask": tk.get("ask", last),
                "vwap": vwap,
                "vwap_diff_pct": round(vwap_diff_pct, 2),
                "change_24_pct": round(change_24_pct, 2),
                "range_pos_pct": round(range_pos_pct, 1),
                "volatility_24h_pct": round(volatility_24h_pct, 2),
                "rsi_14": rsi_14,
                "sma_diff_bps": round(sma_diff_bps, 2),
                "spread_bps": round(spread_bps, 2),
                "volume_mxn_est": tk.get("volume_mxn_est", 0.0),
                "auto_tp_pct": dyn_targets["auto_tp_pct"],
                "auto_sl_pct": dyn_targets["auto_sl_pct"],
                "auto_trail_arm_pct": dyn_targets["auto_trail_arm_pct"],
                "auto_trail_drop_pct": dyn_targets["auto_trail_drop_pct"],
                "opportunity_score": score,
                "signal": signal,
                "signal_label": signal_label,
                "setup_type": setup_type,
                "rationale": " • ".join(reasons[:3]),
                "has_position": held_qty > 1e-8,
                "held_amount": held_qty,
                "unrealized_pnl_pct": pos_info.get("unrealized_pnl_pct", 0.0),
            })

        opportunities.sort(key=lambda x: x["opportunity_score"], reverse=True)
        return opportunities

    def scan_triangular_arbitrage(
        self, raw_by_book: Dict[str, Dict[str, Any]], usd_mxn_rate: float
    ) -> List[Dict[str, Any]]:
        arb_list: List[Dict[str, Any]] = []
        if usd_mxn_rate <= 0:
            return arb_list

        for item in self.ARBITRAGE_PAIRS:
            mxn_raw = raw_by_book.get(item["mxn_book"])
            usd_raw = raw_by_book.get(item["usd_book"])
            if not mxn_raw or not usd_raw:
                continue

            mxn_last = float(mxn_raw.get("last") or 0.0)
            usd_last = float(usd_raw.get("last") or 0.0)
            if mxn_last <= 0 or usd_last <= 0:
                continue

            implied_mxn = usd_last * usd_mxn_rate
            diff_mxn = implied_mxn - mxn_last
            spread_arb_bps = (diff_mxn / mxn_last) * 10000.0
            abs_bps = abs(spread_arb_bps)

            if spread_arb_bps > 8.0:
                direction = f"Más barato en {item['symbol']}/MXN directo (-{abs_bps:.1f} bps vs USD)"
                recommended_book = item["mxn_book"]
            elif spread_arb_bps < -8.0:
                direction = f"Más barato en {item['symbol']}/USD implícito (-{abs_bps:.1f} bps vs MXN)"
                recommended_book = item["mxn_book"]
            else:
                direction = "Paridad eficiente entre libros MXN y USD"
                recommended_book = item["mxn_book"]

            arb_list.append({
                "symbol": item["symbol"],
                "name": item["name"],
                "mxn_book": item["mxn_book"],
                "usd_book": item["usd_book"],
                "direct_mxn_price": round(mxn_last, 4 if mxn_last < 10 else 2),
                "usd_price": round(usd_last, 4 if usd_last < 10 else 2),
                "usd_mxn_spot": round(usd_mxn_rate, 4),
                "implied_mxn_price": round(implied_mxn, 4 if implied_mxn < 10 else 2),
                "spread_bps": round(spread_arb_bps, 1),
                "abs_spread_bps": round(abs_bps, 1),
                "direction": direction,
                "recommended_book": recommended_book,
            })

        arb_list.sort(key=lambda x: x["abs_spread_bps"], reverse=True)
        return arb_list
