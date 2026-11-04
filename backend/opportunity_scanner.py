import math
from typing import Any, Dict, List


class OpportunityScanner:
    """
    Escáner Cuantitativo Multi-Activo de Alta Frecuencia (Scalping) y Cálculo Dinámico
    de Take Profit / Stop Loss por Moneda para Bitso.
    """

    ARBITRAGE_PAIRS = [
        {"symbol": "ORO", "name": "Oro COMEX vs Físico", "mxn_book": "gc_fut", "usd_book": "paxg_usd"},
        {"symbol": "WTI", "name": "Petróleo WTI vs Brent", "mxn_book": "cl_fut", "usd_book": "brent_fut"},
        {"symbol": "USD", "name": "Dólar Estadounidense", "mxn_book": "usd_mxn", "usd_book": "usd_mxn"},
        {"symbol": "EUR", "name": "Euro FX", "mxn_book": "eur_mxn", "usd_book": "eur_mxn"},
    ]

    PREMIER_LIQUID_PAIRS = {
        "usd_mxn", "gc_fut", "cl_fut", "eur_mxn", "paxg_usd", "brent_fut",
        "gbp_mxn", "si_fut", "cad_mxn", "chf_mxn", "jpy_mxn", "ng_fut"
    }

    @staticmethod
    def detect_market_regimes(
        tickers: Dict[str, Dict[str, Any]],
        price_history_by_book: Dict[str, List[Dict[str, Any]]],
    ) -> Dict[str, str]:
        """
        Detecta el régimen macro de materias primas y divisas para filtrar operaciones contra-tendencia:
          - commodities_regime: 'BULLISH', 'BEARISH' o 'NEUTRAL' según Oro COMEX (GC=F)
          - oil_regime: 'BULLISH', 'BEARISH' o 'NEUTRAL' según Petróleo WTI (CL=F)
          - forex_regime: 'BULLISH', 'BEARISH' o 'NEUTRAL' según Dólar USD/MXN
        """
        # 1. Régimen Oro (Benchmark: GC_FUT)
        gold = tickers.get("gc_fut")
        commodities_regime = "NEUTRAL"
        if gold:
            g_last = float(gold.get("last") or 0.0)
            g_vwap = float(gold.get("vwap") or g_last)
            g_change = float(gold.get("change_24_pct") or 0.0)
            if g_last >= g_vwap or g_change >= 0.15:
                commodities_regime = "BULLISH"
            elif g_last < g_vwap * 0.998 or g_change <= -0.4:
                commodities_regime = "BEARISH"

        # 2. Régimen Petróleo (Benchmark: CL_FUT)
        oil = tickers.get("cl_fut")
        oil_regime = "NEUTRAL"
        if oil:
            o_last = float(oil.get("last") or 0.0)
            o_vwap = float(oil.get("vwap") or o_last)
            o_change = float(oil.get("change_24_pct") or 0.0)
            if o_last >= o_vwap or o_change >= 0.2:
                oil_regime = "BULLISH"
            elif o_last < o_vwap * 0.996 or o_change <= -0.8:
                oil_regime = "BEARISH"

        # 3. Régimen Divisas (Benchmark: USD_MXN)
        usd = tickers.get("usd_mxn")
        forex_regime = "NEUTRAL"
        if usd:
            u_last = float(usd.get("last") or 0.0)
            u_vwap = float(usd.get("vwap") or u_last)
            u_change = float(usd.get("change_24_pct") or 0.0)
            if u_last >= u_vwap or u_change >= 0.1:
                forex_regime = "BULLISH"
            elif u_last < u_vwap * 0.998 or u_change <= -0.3:
                forex_regime = "BEARISH"

        return {
            "commodities_regime": commodities_regime,
            "oil_regime": oil_regime,
            "forex_regime": forex_regime,
        }

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

        # 3. Volatilidad combinada y Ratio Riesgo/Beneficio Estricto 1:2
        scalp_move_pct = max(tick_atr_pct * 2.0, volatility_24h_pct * 0.05)
        # SL estructural adaptable (mínimo 0.40%, máximo 0.65% para absorber ruido natural)
        base_sl = max(0.40, min(0.65, round(friction_floor_pct + scalp_move_pct * 1.1, 2)))
        # TAKE PROFIT EXACTAMENTE AL DOBLE (1:2 R:R)
        base_tp = round(base_sl * 2.0, 2)

        return {
            "auto_tp_pct": base_tp,
            "auto_sl_pct": base_sl,
            "risk_reward_ratio": "1:2",
            "auto_trail_arm_pct": 0.0,
            "auto_trail_drop_pct": 0.0,
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
        regimes = self.detect_market_regimes(tickers, price_history_by_book)
        commodities_regime = regimes.get("commodities_regime", "NEUTRAL")
        oil_regime = regimes.get("oil_regime", "NEUTRAL")
        forex_regime = regimes.get("forex_regime", "NEUTRAL")

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

            # Score Cuantitativo Sniper (Alta Probabilidad de Acierto para Evitar Pérdidas)
            score = 50.0
            reasons: List[str] = []
            setup_type = "Monitoreo"

            # Confirmación de giro alcista: SMA en aceleración positiva y precio reciente rebotando
            is_bouncing = sma_diff_bps >= 0.1 and tick_bounce_bps >= 0.0

            if vwap_diff_pct <= -0.15 and is_bouncing:
                bonus = min(20.0, abs(vwap_diff_pct) * 12.0)
                score += bonus
                setup_type = "Rebote Confirmado en Descuento"
                reasons.append(f"Giro alcista con descuento {vwap_diff_pct:.2f}% vs VWAP")
            elif vwap_diff_pct <= -0.40 and not is_bouncing:
                score -= 10.0
                setup_type = "En Caída (Prohibido Comprar)"
                reasons.append(f"Cayendo sin freno ({vwap_diff_pct:.2f}% bajo VWAP)")
            elif sma_diff_bps >= 1.2 and is_bouncing:
                score += 15.0
                setup_type = "Impulso Alcista Confirmado"
                reasons.append(f"Aceleración de corto plazo (+{sma_diff_bps:.1f} bps SMA)")

            if range_pos_pct <= 38.0 and is_bouncing:
                score += 12.0
                setup_type = "Piso de 24h con Giro Alcista"
                reasons.append(f"Rebote en soporte ({range_pos_pct:.0f}% rango)")
            elif range_pos_pct >= 85.0 and change_24_pct > 0.6:
                score += 10.0
                setup_type = "Breakout Fuerte"
                reasons.append(f"Ruptura de máximos (+{change_24_pct:+.2f}%)")

            # Ventana óptima de entrada: RSI entre 32 y 48 (sobreventa con giro)
            if 30.0 <= rsi_14 <= 48.0 and is_bouncing:
                score += 14.0
                reasons.append(f"RSI en zona óptima de compra ({rsi_14:.1f})")
            elif rsi_14 >= 65.0:
                score -= 16.0
                reasons.append(f"RSI en zona de sobrecompra ({rsi_14:.1f})")

            # Filtro estricto de spread para asegurar que la comisión no coma la ganancia
            if spread_bps <= 3.2:
                score += 12.0
                reasons.append(f"Spread mínimo ({spread_bps:.1f} bps)")
            elif spread_bps <= 5.5:
                score += 6.0
            elif spread_bps <= 8.0:
                score -= 12.0
                reasons.append(f"Spread moderado ({spread_bps:.1f} bps penalizado)")
            else:
                score -= min(45.0, 20.0 + (spread_bps - 8.0) * 3.0)
                reasons.append(f"Spread alto ({spread_bps:.1f} bps bloqueado)")

            # Filtro 1: Alineación con Régimen Macro de Activos Estables
            is_gold_metal = category == "Oro & Metales Refugio"
            is_energy = category == "Petróleo & Energía"
            is_forex = category == "Divisas & Monedas"
            macro_status = "Alineado"

            if is_gold_metal:
                if commodities_regime == "BEARISH":
                    score -= 18.0
                    macro_status = "Oro Bajista"
                    reasons.append("Filtro Macro: Oro/Metales bajo presión vendedora")
                elif commodities_regime == "BULLISH":
                    score += 7.0
                    macro_status = "Oro Refugio Alcista"
            elif is_energy:
                if oil_regime == "BEARISH":
                    score -= 18.0
                    macro_status = "Petróleo Bajista"
                    reasons.append("Filtro Macro: Petróleo WTI bajo presión bajista")
                elif oil_regime == "BULLISH":
                    score += 7.0
                    macro_status = "Energía Alcista"
            elif is_forex:
                if forex_regime == "BEARISH" and book == "usd_mxn":
                    score -= 14.0
                    macro_status = "USD Bajo VWAP"
                elif forex_regime == "BULLISH":
                    score += 5.0
                    macro_status = "Divisa Fuerte"

            # Filtro 2: Estricta verificación de liquidez institucional
            is_premier = book in self.PREMIER_LIQUID_PAIRS
            if is_premier:
                score += 15.0
                reasons.append("Activo Estable Institucional")
            else:
                score -= 30.0
                reasons.append("Excluido de auto-trading (baja liquidez)")

            score = round(max(10.0, min(98.0, score)), 1)

            if score >= 78.0:
                signal = "STRONG_BUY"
                signal_label = "SNIPER COMPRA FUERTE"
            elif score >= 70.0:
                signal = "BUY"
                signal_label = "OPORTUNIDAD ALTA"
            elif score <= 40.0:
                signal = "SELL"
                signal_label = "VENTA / SALIDA"
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
                "is_premier": is_premier,
                "macro_status": macro_status,
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
