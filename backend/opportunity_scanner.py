from typing import Any, Dict, List


class OpportunityScanner:
    """
    Escáner Cuantitativo Multi-Activo y Detector de Arbitraje para Bitso.
    Evalúa en tiempo real 24 monedas y activos (Cripto MXN, Oro Físico PAXG, RWA ONDO,
    Divisas USD/EUR, Layer-1/DeFi y Memes) para clasificar oportunidades por:
      1. Descuento institucional respecto al VWAP (Volume-Weighted Average Price)
      2. Posición dentro del canal de 24h (Soporte / Rebote vs. Breakout Alcista)
      3. Impulso intradía (RSI + Cruce de Medias SMA)
      4. Eficiencia de liquidez (Spread Bid-Ask en puntos base)
      5. Arbitraje Triangular entre libros MXN y USD (ej. BTC/MXN vs BTC/USD * USD/MXN)
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
        # Filtrar precios consecutivos idénticos para calcular cambios reales de ticks
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

    def scan_all_assets(
        self,
        tickers: Dict[str, Dict[str, Any]],
        price_history_by_book: Dict[str, List[Dict[str, Any]]],
        positions: Dict[str, Dict[str, Any]],
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

            span_24h = high - low
            range_pos_pct = ((last - low) / span_24h * 100.0) if span_24h > 0 else 50.0
            range_pos_pct = max(0.0, min(100.0, range_pos_pct))
            volatility_24h_pct = (span_24h / low * 100.0) if low > 0 else 0.0

            vwap_diff_pct = ((last - vwap) / vwap * 100.0) if vwap > 0 else 0.0

            hist = price_history_by_book.get(book, [])
            prices = [float(p["price"]) for p in hist if float(p.get("price", 0)) > 0]
            rsi_14 = self._compute_rsi(prices, range_pos_pct)

            if len(prices) >= 3:
                sma_short = sum(prices[-5:]) / len(prices[-5:])
                sma_long = sum(prices[-18:]) / len(prices[-18:])
                sma_diff_bps = ((sma_short - sma_long) / sma_long * 10000.0) if sma_long > 0 else 0.0
            else:
                sma_diff_bps = round(-vwap_diff_pct * 8.0, 2)

            # Cálculo del Score Cuantitativo de Oportunidad (0 a 100)
            score = 50.0
            reasons: List[str] = []
            setup_type = "Seguimiento de Mercado"

            # 1. Oportunidad por Descuento frente a VWAP institucional
            if vwap_diff_pct <= -0.35:
                bonus = min(18.0, abs(vwap_diff_pct) * 9.5)
                score += bonus
                setup_type = "Descuento bajo VWAP"
                reasons.append(f"Cotiza {vwap_diff_pct:.2f}% bajo su VWAP institucional")
            elif vwap_diff_pct >= 0.85 and change_24_pct > 2.0:
                score += 10.0
                setup_type = "Breakout Alcista con Volumen"
                reasons.append(f"Fuerte impulso (+{change_24_pct:.2f}% 24h) superando VWAP")

            # 2. Posición en el canal de 24h (Soporte / Sobreventa vs Resistencia)
            if range_pos_pct <= 28.0:
                support_bonus = (30.0 - range_pos_pct) * 0.65
                score += support_bonus
                if setup_type == "Descuento bajo VWAP":
                    setup_type = "Doble Confluencia: Soporte 24h + Bajo VWAP"
                else:
                    setup_type = "Zona de Soporte 24h (Rebote)"
                reasons.append(f"En piso del canal 24h ({range_pos_pct:.0f}% del rango)")
            elif range_pos_pct >= 84.0 and change_24_pct > 1.5:
                score += 11.0
                setup_type = "Momentum Breakout 24h"
                reasons.append(f"Rompiendo techo de 24h ({range_pos_pct:.0f}% del rango)")
            elif range_pos_pct >= 88.0 and change_24_pct <= 0.5:
                score -= 14.0
                setup_type = "Resistencia / Posible Toma de Utilidad"
                reasons.append(f"Agotamiento cerca del máximo 24h ({range_pos_pct:.0f}%)")

            # 3. RSI y Momentum de Corto Plazo
            if rsi_14 <= 38.0:
                score += (40.0 - rsi_14) * 0.7
                reasons.append(f"RSI en sobreventa ({rsi_14:.1f})")
            elif rsi_14 >= 72.0:
                score -= (rsi_14 - 70.0) * 0.8
                reasons.append(f"RSI en sobrecompra ({rsi_14:.1f})")

            if sma_diff_bps > 2.0:
                score += min(8.0, sma_diff_bps * 0.8)
                reasons.append(f"Cruce alcista SMA ({sma_diff_bps:+.1f} bps)")

            # 4. Penalización por Spread alto (iliquidez) o premio por liquidez institucional
            if spread_bps <= 12.0:
                score += 5.0
                reasons.append(f"Liquidez óptima (spread {spread_bps:.1f} bps)")
            elif spread_bps > 45.0:
                score -= min(18.0, (spread_bps - 40.0) * 0.25)

            # Ajuste para activos de refugio (Oro PAXG / Divisas) cuando el mercado cripto cae
            if tk.get("category") in ("Oro & RWA", "Divisas & FX") and change_24_pct >= 0:
                score += 6.0
                if setup_type == "Seguimiento de Mercado":
                    setup_type = "Refugio Defensivo / Cobertura Cambiaria"
                reasons.append("Fuerza relativa positiva como activo refugio")

            score = round(max(12.0, min(98.0, score)), 1)

            if score >= 73.0:
                signal = "STRONG_BUY"
                signal_label = "COMPRA FUERTE"
            elif score >= 61.0:
                signal = "BUY"
                signal_label = "OPORTUNIDAD COMPRA"
            elif score <= 36.0:
                signal = "SELL"
                signal_label = "TOMA UTILIDAD / VENTA"
            else:
                signal = "NEUTRAL"
                signal_label = "OBSERVAR / HOLD"

            if not reasons:
                reasons.append(
                    f"Rango 24h al {range_pos_pct:.0f}% | VWAP {vwap_diff_pct:+.2f}% | RSI {rsi_14:.1f}"
                )

            pos_info = positions.get(book, {})
            held_qty = float(pos_info.get("amount", 0.0))

            opportunities.append({
                "book": book,
                "name": tk.get("name", book),
                "symbol": tk.get("symbol", book),
                "pair": tk.get("pair", book),
                "category": tk.get("category", "Cripto"),
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
                "opportunity_score": score,
                "signal": signal,
                "signal_label": signal_label,
                "setup_type": setup_type,
                "rationale": " • ".join(reasons[:3]),
                "has_position": held_qty > 1e-8,
                "held_amount": held_qty,
                "unrealized_pnl_pct": pos_info.get("unrealized_pnl_pct", 0.0),
            })

        # Ordenar de mayor a menor Score de Oportunidad
        opportunities.sort(key=lambda x: x["opportunity_score"], reverse=True)
        return opportunities

    def scan_triangular_arbitrage(
        self, raw_by_book: Dict[str, Dict[str, Any]], usd_mxn_rate: float
    ) -> List[Dict[str, Any]]:
        """
        Detecta diferenciales de arbitraje entre comprar un activo directamente en MXN (`btc_mxn`)
        vs comprarlo en USD (`btc_usd`) multiplicado por el tipo de cambio spot `usd_mxn` de Bitso.
        """
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
