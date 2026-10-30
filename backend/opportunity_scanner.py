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

    PREMIER_LIQUID_PAIRS = {
        "btc_mxn", "eth_mxn", "sol_mxn", "xrp_mxn",
        "nvda_stk", "aapl_stk", "nq_fut"
    }

    @staticmethod
    def detect_market_regimes(
        tickers: Dict[str, Dict[str, Any]],
        price_history_by_book: Dict[str, List[Dict[str, Any]]],
    ) -> Dict[str, str]:
        """
        Detecta el régimen macro de mercado para filtrar operaciones contra-tendencia:
          - crypto_regime: 'BULLISH', 'BEARISH' o 'NEUTRAL' según BTC/MXN
          - equities_regime: 'BULLISH', 'BEARISH' o 'NEUTRAL' según NQ-FUT / ES-FUT
        """
        # 1. Régimen Cripto (Benchmark: BTC)
        btc = tickers.get("btc_mxn")
        crypto_regime = "NEUTRAL"
        if btc:
            btc_last = float(btc.get("last") or 0.0)
            btc_vwap = float(btc.get("vwap") or btc_last)
            btc_change = float(btc.get("change_24_pct") or 0.0)
            btc_hist = price_history_by_book.get("btc_mxn", [])
            btc_sma_diff = 0.0
            if len(btc_hist) >= 4:
                p_short = sum(p["price"] for p in btc_hist[-4:]) / 4
                p_long = sum(p["price"] for p in btc_hist[-12:]) / min(12, len(btc_hist))
                btc_sma_diff = (p_short - p_long) / p_long * 10000.0 if p_long > 0 else 0.0

            if (btc_last >= btc_vwap * 0.999 or btc_change >= 0.3) and btc_sma_diff >= -0.8:
                crypto_regime = "BULLISH"
            elif (btc_last < btc_vwap * 0.995 or btc_change <= -1.2) and btc_sma_diff < -1.5:
                crypto_regime = "BEARISH"
            else:
                crypto_regime = "NEUTRAL"

        # 2. Régimen Bursátil (Benchmark: NQ-FUT / ES-FUT)
        nq = tickers.get("nq_fut") or tickers.get("es_fut")
        equities_regime = "NEUTRAL"
        if nq:
            nq_last = float(nq.get("last") or 0.0)
            nq_vwap = float(nq.get("vwap") or nq_last)
            nq_change = float(nq.get("change_24_pct") or 0.0)
            if nq_last >= nq_vwap or nq_change >= 0.2:
                equities_regime = "BULLISH"
            elif nq_last < nq_vwap * 0.997 or nq_change <= -0.6:
                equities_regime = "BEARISH"

        return {
            "crypto_regime": crypto_regime,
            "equities_regime": equities_regime,
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

        # 3. Volatilidad combinada y targets realistas
        scalp_move_pct = max(tick_atr_pct * 2.2, volatility_24h_pct * 0.06)

        # Asimetría Quirúrgica: Take Profit debe superar con creces al Stop Loss
        # Comisiones roundtrip (0.06%) + spread (~0.04%) = ~0.10% costo base
        base_tp = max(0.48, min(0.80, friction_floor_pct + scalp_move_pct * 1.15))
        base_sl = 0.35  # Stop Loss rígido e inamovible en 0.35%

        auto_tp = round(base_tp, 2)
        auto_sl = 0.35

        # Trailing Stop se activa únicamente al alcanzar +0.30% y protege al menos +0.22%
        auto_trail_arm = 0.30
        auto_trail_drop = 0.08

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
        regimes = self.detect_market_regimes(tickers, price_history_by_book)
        crypto_regime = regimes.get("crypto_regime", "NEUTRAL")
        equities_regime = regimes.get("equities_regime", "NEUTRAL")

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

            # Filtro 1: Alineación con Régimen Macro (Evitar comprar contra tendencia general)
            is_crypto = category in ("Cripto MXN", "Layer-1 & DeFi", "Alta Volatilidad")
            is_equity_futures = category in ("Acciones", "Futuros")
            macro_status = "Alineado"

            if is_crypto:
                if crypto_regime == "BEARISH":
                    if book != "btc_mxn":
                        score -= 26.0
                        macro_status = "BTC Bajista (Bloqueado)"
                        reasons.append("Filtro Macro: BTC en tendencia bajista (altcoin bloqueada)")
                    else:
                        score -= 12.0
                        macro_status = "BTC en Caída"
                elif crypto_regime == "BULLISH":
                    score += 6.0
                    macro_status = "Cripto Alcista"
            elif is_equity_futures:
                if equities_regime == "BEARISH":
                    score -= 24.0
                    macro_status = "NQ/ES Bajista (Bloqueado)"
                    reasons.append("Filtro Macro: Índices NQ/ES en tendencia bajista")
                elif equities_regime == "BULLISH":
                    score += 6.0
                    macro_status = "Bolsa Alcista"

            # Filtro 2: Estricta preferencia por Activos Líquidos Premier (Excluye divisas fiat, memes e ilíquidos)
            is_premier = book in self.PREMIER_LIQUID_PAIRS
            if is_premier:
                score += 15.0
                reasons.append("Activo Líquido Premier")
            else:
                score -= 35.0
                reasons.append("Excluido de auto-scalper (Falta de liquidez o spread amplio)")

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
