import math
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


def calc_ema(values: List[float], period: int) -> List[float]:
    """Calcula la media móvil exponencial (EMA) para una lista de valores."""
    if not values:
        return []
    if len(values) < period:
        # Si no hay suficientes datos para el periodo completo, retornar SMA progresiva
        res = []
        acc = 0.0
        for i, v in enumerate(values):
            acc += v
            res.append(acc / (i + 1))
        return res

    multiplier = 2.0 / (period + 1.0)
    ema_list = []
    # Semilla inicial con la media simple de los primeros `period` valores
    sma = sum(values[:period]) / period
    ema_list.extend([sma] * period)
    curr_ema = sma

    for v in values[period:]:
        curr_ema = (v - curr_ema) * multiplier + curr_ema
        ema_list.append(curr_ema)

    return ema_list


def calc_rsi(values: List[float], period: int = 14) -> List[float]:
    """Calcula el índice de fuerza relativa (RSI) estándar de Wilder."""
    if len(values) < period + 1:
        return [50.0] * len(values)

    deltas = [values[i] - values[i - 1] for i in range(1, len(values))]
    rsi_list = [50.0] * period

    gains = [max(0.0, d) for d in deltas[:period]]
    losses = [max(0.0, -d) for d in deltas[:period]]

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    if avg_loss == 0.0:
        rsi_list.append(100.0 if avg_gain > 0.0 else 50.0)
    else:
        rs = avg_gain / avg_loss
        rsi_list.append(100.0 - (100.0 / (1.0 + rs)))

    for d in deltas[period:]:
        gain = max(0.0, d)
        loss = max(0.0, -d)
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period

        if avg_loss == 0.0:
            rsi_list.append(100.0 if avg_gain > 0.0 else 50.0)
        else:
            rs = avg_gain / avg_loss
            rsi_list.append(100.0 - (100.0 / (1.0 + rs)))

    return rsi_list


class TrendPullbackEngine:
    """
    Motor Profesional de Estrategia de Tendencia y Retroceso Multi-Temporal (H1 / M15)
    con Ratio Riesgo/Beneficio Estricto de 1:2.

    Reglas para COMPRAR (BUY):
      1. En H1, el precio debe estar por encima de EMA 200.
      2. EMA 20 debe mostrar pendiente ascendente.
      3. En M15, esperar que el precio retroceda hacia EMA 20.
      4. RSI debe recuperar el nivel 50.
      5. Esperar una vela alcista de confirmación, preferiblemente envolvente.
      6. Entrar al superar el máximo de la vela de confirmación.

    Reglas para VENDER (SELL):
      1. En H1, el precio debe estar por debajo de EMA 200.
      2. EMA 20 debe mostrar pendiente descendente.
      3. En M15, esperar un retroceso hacia EMA 20.
      4. RSI debe perder el nivel 50.
      5. Esperar una vela bajista de confirmación.
      6. Entrar al romper el mínimo de la vela de confirmación.

    Cuándo NO operar (Filtros de Bloqueo):
      - Precio cruzando repetidamente EMA 200 en H1 (choppy market / whipsaw).
      - Mercado lateral sin dirección (pendiente plana de EMA 20 / compresión ATR).
      - Noticias económicas importantes próximas.
      - Spread anormalmente alto (> 5.0 bps).
      - Stop Loss demasiado grande para el capital disponible.

    Stop Loss y Take Profit:
      - Relación estricta 1:2.
      - SL estructural debajo/arriba de la vela de confirmación y soporte/resistencia del retroceso.
      - TP = 2.0 * SL.
    """

    def __init__(self) -> None:
        self.news_blackout: bool = False
        self.news_blackout_reason: str = ""

    def set_news_blackout(self, active: bool, reason: str = "") -> None:
        self.news_blackout = active
        self.news_blackout_reason = reason

    def detect_candle_pattern(self, candles: List[Dict[str, float]]) -> Dict[str, Any]:
        """
        Analiza las últimas velas de M15 para identificar velas de confirmación:
        - Envolvente Alcista / Bajista (Bullish/Bearish Engulfing)
        - Martillo / Pinbar de rechazo (Hammer / Shooting Star)
        - Vela impulsiva de quiebre
        """
        if len(candles) < 2:
            return {
                "pattern": "INSUFFICIENT_DATA",
                "is_bullish": False,
                "is_bearish": False,
                "confirmation_candle": None,
                "high": 0.0,
                "low": 0.0,
                "description": "Datos insuficientes en M15",
            }

        prev = candles[-2]
        curr = candles[-1]

        prev_open = float(prev.get("open", 0.0))
        prev_close = float(prev.get("close", 0.0))
        prev_high = float(prev.get("high", max(prev_open, prev_close)))
        prev_low = float(prev.get("low", min(prev_open, prev_close)))

        curr_open = float(curr.get("open", 0.0))
        curr_close = float(curr.get("close", 0.0))
        curr_high = float(curr.get("high", max(curr_open, curr_close)))
        curr_low = float(curr.get("low", min(curr_open, curr_close)))

        curr_body = abs(curr_close - curr_open)
        curr_range = max(1e-9, curr_high - curr_low)
        lower_wick = (curr_open - curr_low) if curr_close >= curr_open else (curr_close - curr_low)
        upper_wick = (curr_high - curr_close) if curr_close >= curr_open else (curr_high - curr_open)

        # 1. Envolvente Alcista: vela anterior bajista y vela actual alcista envolviendo el cuerpo previo
        is_bullish_engulfing = (
            prev_close < prev_open
            and curr_close > curr_open
            and curr_close >= prev_open
            and curr_open <= prev_close * 1.002
        )

        # 2. Martillo alcista con rechazo en soporte (mecha inferior >= 1.8x el cuerpo y vela verde o neutral)
        is_bullish_hammer = (
            lower_wick >= 1.8 * curr_body
            and upper_wick <= 0.35 * curr_range
            and curr_close >= curr_open
        )

        # 3. Vela alcista sólida (cierre en el tercio superior)
        is_strong_bullish = (
            curr_close > curr_open
            and (curr_close - curr_low) / curr_range >= 0.70
            and curr_close > prev_high * 0.999
        )

        is_bullish_conf = is_bullish_engulfing or is_bullish_hammer or is_strong_bullish

        # 4. Envolvente Bajista: vela anterior alcista y vela actual bajista envolviendo el cuerpo previo
        is_bearish_engulfing = (
            prev_close > prev_open
            and curr_close < curr_open
            and curr_close <= prev_open
            and curr_open >= prev_close * 0.998
        )

        # 5. Estrella fugaz bajista (Shooting star / mecha superior >= 1.8x el cuerpo)
        is_bearish_star = (
            upper_wick >= 1.8 * curr_body
            and lower_wick <= 0.35 * curr_range
            and curr_close <= curr_open
        )

        # 6. Vela bajista sólida (cierre en el tercio inferior)
        is_strong_bearish = (
            curr_close < curr_open
            and (curr_high - curr_close) / curr_range >= 0.70
            and curr_close < prev_low * 1.001
        )

        is_bearish_conf = is_bearish_engulfing or is_bearish_star or is_strong_bearish

        pattern_name = "NEUTRAL"
        desc = "Vela neutral / consolidación"
        if is_bullish_engulfing:
            pattern_name = "BULLISH_ENGULFING"
            desc = "Vela Envolvente Alcista institucional"
        elif is_bullish_hammer:
            pattern_name = "BULLISH_HAMMER"
            desc = "Martillo con fuerte rechazo inferior en soporte"
        elif is_strong_bullish:
            pattern_name = "STRONG_BULLISH"
            desc = "Vela impulsiva alcista con cierre en máximos"
        elif is_bearish_engulfing:
            pattern_name = "BEARISH_ENGULFING"
            desc = "Vela Envolvente Bajista"
        elif is_bearish_star:
            pattern_name = "BEARISH_SHOOTING_STAR"
            desc = "Estrella fugaz con rechazo superior en resistencia"
        elif is_strong_bearish:
            pattern_name = "STRONG_BEARISH"
            desc = "Vela impulsiva bajista con quiebre de soporte"

        return {
            "pattern": pattern_name,
            "is_bullish": is_bullish_conf,
            "is_bearish": is_bearish_conf,
            "confirmation_candle": curr,
            "high": curr_high,
            "low": curr_low,
            "description": desc,
        }

    def check_ema200_whipsaw(self, closes_h1: List[float], ema200_h1: List[float], lookback: int = 20) -> Tuple[bool, int]:
        """
        Filtro de Exclusión 1: Detecta si el precio ha cruzado repetidamente la EMA 200 en H1.
        Si hay más de 2 cruces en las últimas 20 velas de H1, el mercado está oscilando sin rumbo fijo.
        """
        if len(closes_h1) < lookback or len(ema200_h1) < lookback:
            return False, 0

        sub_closes = closes_h1[-lookback:]
        sub_ema = ema200_h1[-lookback:]

        cross_count = 0
        prev_side = sub_closes[0] >= sub_ema[0]
        for c, e in zip(sub_closes[1:], sub_ema[1:]):
            curr_side = c >= e
            if curr_side != prev_side:
                cross_count += 1
                prev_side = curr_side

        is_whipsaw = cross_count >= 3
        return is_whipsaw, cross_count

    def check_lateral_market(self, closes_m15: List[float], ema20_m15: List[float], lookback: int = 8) -> Tuple[bool, float]:
        """
        Filtro de Exclusión 2: Detecta mercado lateral sin dirección clara (pendiente casi cero).
        """
        if len(ema20_m15) < lookback:
            return False, 0.0

        recent_ema = ema20_m15[-lookback:]
        # Pendiente porcentual por vela en las últimas velas
        slope_pct = (recent_ema[-1] - recent_ema[0]) / max(1e-9, recent_ema[0]) * 100.0 / lookback
        # Si la variación de la EMA 20 es inferior a 0.012% por vela, se considera mercado plano/lateral
        is_lateral = abs(slope_pct) < 0.012
        return is_lateral, round(slope_pct, 4)

    def evaluate_strategy(
        self,
        book: str,
        current_price: float,
        candles_h1: List[Dict[str, float]],
        candles_m15: List[Dict[str, float]],
        spread_bps: float,
        available_cash_mxn: float,
        position_exposure: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Evalúa integralmente las 6 reglas de COMPRA, 6 reglas de VENTA,
        los 5 filtros de exclusión y calcula el ratio R:R 1:2.
        """
        if len(candles_h1) < 15 or len(candles_m15) < 15:
            return {
                "book": book,
                "current_price": current_price,
                "signal": "HOLD",
                "confidence": 0.0,
                "reason": "Recopilando velas suficientes de H1 y M15...",
                "rules_passed_count": 0,
                "checklist_buy": {},
                "checklist_sell": {},
                "exclusion_filters": {},
                "risk_reward": {"ratio": "1:2", "sl_pct": 0.50, "tp_pct": 1.00},
            }

        closes_h1 = [float(c["close"]) for c in candles_h1]
        closes_m15 = [float(c["close"]) for c in candles_m15]

        # 1. Medias Móviles en H1 (EMA 200 y EMA 20)
        ema200_h1_series = calc_ema(closes_h1, 200)
        ema20_h1_series = calc_ema(closes_h1, 20)
        curr_ema200_h1 = ema200_h1_series[-1]
        curr_ema20_h1 = ema20_h1_series[-1]
        prev_ema20_h1 = ema20_h1_series[-2] if len(ema20_h1_series) >= 2 else curr_ema20_h1
        h1_ema20_slope_asc = curr_ema20_h1 > prev_ema20_h1
        h1_ema20_slope_desc = curr_ema20_h1 < prev_ema20_h1

        # 2. Medias Móviles y RSI en M15 (EMA 20 y RSI 14)
        ema20_m15_series = calc_ema(closes_m15, 20)
        rsi_m15_series = calc_rsi(closes_m15, 14)
        curr_ema20_m15 = ema20_m15_series[-1]
        prev_ema20_m15 = ema20_m15_series[-2] if len(ema20_m15_series) >= 2 else curr_ema20_m15
        curr_rsi_m15 = rsi_m15_series[-1]
        prev_rsi_m15 = rsi_m15_series[-2] if len(rsi_m15_series) >= 2 else curr_rsi_m15

        m15_ema20_slope_asc = curr_ema20_m15 >= prev_ema20_m15
        m15_ema20_slope_desc = curr_ema20_m15 <= prev_ema20_m15

        # Retroceso hacia EMA 20 en M15 (distancia porcentual entre precio y EMA 20)
        pullback_dist_pct = abs(current_price - curr_ema20_m15) / max(1e-9, curr_ema20_m15) * 100.0
        # En compra: pullback hacia EMA 20 significa que el precio está cerca de la EMA 20 (<= 0.55%)
        # o que la vela reciente tocó o testeó la EMA 20
        last_m15 = candles_m15[-1]
        low_m15 = float(last_m15.get("low", current_price))
        high_m15 = float(last_m15.get("high", current_price))
        pullback_buy_valid = (
            pullback_dist_pct <= 0.60
            or (low_m15 <= curr_ema20_m15 * 1.002 and current_price >= curr_ema20_m15 * 0.995)
        )
        pullback_sell_valid = (
            pullback_dist_pct <= 0.60
            or (high_m15 >= curr_ema20_m15 * 0.998 and current_price <= curr_ema20_m15 * 1.005)
        )

        # RSI recupera / pierde nivel 50
        rsi_recovering_50 = (curr_rsi_m15 >= 50.0) or (prev_rsi_m15 < 50.0 and curr_rsi_m15 >= 48.5)
        rsi_losing_50 = (curr_rsi_m15 <= 50.0) or (prev_rsi_m15 > 50.0 and curr_rsi_m15 <= 51.5)

        # Detección de patrones de velas en M15
        candle_pattern = self.detect_candle_pattern(candles_m15)
        conf_high = candle_pattern["high"]
        conf_low = candle_pattern["low"]

        # Superación de máximo / quiebre de mínimo
        breakout_buy = current_price >= (conf_high * 0.9995)
        breakout_sell = current_price <= (conf_low * 1.0005)

        # -------------------------------------------------------------
        # EVALUACIÓN DE FILTROS DE EXCLUSIÓN (Cuándo NO operar)
        # -------------------------------------------------------------
        is_whipsaw, whipsaw_count = self.check_ema200_whipsaw(closes_h1, ema200_h1_series, lookback=20)
        is_lateral, slope_val = self.check_lateral_market(closes_m15, ema20_m15_series, lookback=8)
        is_spread_high = spread_bps > 5.0
        # Stop Loss técnico estructural
        structural_sl_distance_buy = max(0.0035, (current_price - conf_low) / max(1e-9, current_price))
        structural_sl_distance_sell = max(0.0035, (conf_high - current_price) / max(1e-9, current_price))
        is_sl_too_large_buy = (structural_sl_distance_buy * 100.0) > 1.35
        is_sl_too_large_sell = (structural_sl_distance_sell * 100.0) > 1.35

        exclusions = {
            "ema200_whipsaw": {
                "blocked": is_whipsaw,
                "desc": f"{whipsaw_count} cruces repetidos de EMA 200 en H1 (Mercado oscilante)",
            },
            "lateral_market": {
                "blocked": is_lateral,
                "desc": f"Mercado lateral sin dirección (Pendiente EMA 20 M15: {slope_val:+.4f}%/vela)",
            },
            "economic_news": {
                "blocked": self.news_blackout,
                "desc": self.news_blackout_reason or "Sin alertas de noticias macro",
            },
            "abnormal_spread": {
                "blocked": is_spread_high,
                "desc": f"Spread de {spread_bps:.1f} bps {'(Anormalmente alto > 5.0 bps)' if is_spread_high else '(Líquido y óptimo)'}",
            },
            "excessive_sl": {
                "blocked": is_sl_too_large_buy,
                "desc": f"Stop Loss estructural: {structural_sl_distance_buy*100:.2f}% {'(Demasiado amplio)' if is_sl_too_large_buy else '(Dentro de límites)'}",
            },
        }

        any_exclusion_active_buy = (
            is_whipsaw or is_lateral or self.news_blackout or is_spread_high or is_sl_too_large_buy
        )
        any_exclusion_active_sell = (
            is_whipsaw or is_lateral or self.news_blackout or is_spread_high or is_sl_too_large_sell
        )

        # -------------------------------------------------------------
        # CHECKLIST REGLAS DE COMPRA (BUY)
        # -------------------------------------------------------------
        buy_r1 = current_price > curr_ema200_h1
        buy_r2 = h1_ema20_slope_asc and m15_ema20_slope_asc
        buy_r3 = pullback_buy_valid
        buy_r4 = rsi_recovering_50
        buy_r5 = candle_pattern["is_bullish"]
        buy_r6 = breakout_buy

        checklist_buy = {
            "r1_h1_above_ema200": {
                "passed": buy_r1,
                "name": "1. H1 por encima de EMA 200",
                "detail": f"Precio (${current_price:,.2f}) {'>' if buy_r1 else '<='} EMA 200 H1 (${curr_ema200_h1:,.2f})",
            },
            "r2_ema20_slope_up": {
                "passed": buy_r2,
                "name": "2. EMA 20 con pendiente ascendente",
                "detail": f"Pendiente H1 ({'Ascendente' if h1_ema20_slope_asc else 'Descendente'}) y M15 ({'Alcista' if m15_ema20_slope_asc else 'Bajista'})",
            },
            "r3_m15_pullback_ema20": {
                "passed": buy_r3,
                "name": "3. M15 retrocede hacia EMA 20",
                "detail": f"Distancia a EMA 20 M15: {pullback_dist_pct:.2f}% (EMA 20: ${curr_ema20_m15:,.2f})",
            },
            "r4_rsi_recovers_50": {
                "passed": buy_r4,
                "name": "4. RSI M15 recupera nivel 50",
                "detail": f"RSI M15 actual = {curr_rsi_m15:.1f} (Umbral >= 50)",
            },
            "r5_bullish_confirmation_candle": {
                "passed": buy_r5,
                "name": "5. Vela alcista de confirmación",
                "detail": f"{candle_pattern['description']} [{candle_pattern['pattern']}]",
            },
            "r6_breakout_candle_high": {
                "passed": buy_r6,
                "name": "6. Entrada al superar máximo de vela",
                "detail": f"Precio (${current_price:,.2f}) {'>=' if breakout_buy else '<'} Máximo (${conf_high:,.2f})",
            },
        }

        # -------------------------------------------------------------
        # CHECKLIST REGLAS DE VENTA (SELL)
        # -------------------------------------------------------------
        sell_r1 = current_price < curr_ema200_h1
        sell_r2 = h1_ema20_slope_desc
        sell_r3 = pullback_sell_valid
        sell_r4 = rsi_losing_50
        sell_r5 = candle_pattern["is_bearish"]
        sell_r6 = breakout_sell

        checklist_sell = {
            "r1_h1_below_ema200": {
                "passed": sell_r1,
                "name": "1. H1 por debajo de EMA 200",
                "detail": f"Precio (${current_price:,.2f}) {'<' if sell_r1 else '>='} EMA 200 H1 (${curr_ema200_h1:,.2f})",
            },
            "r2_ema20_slope_down": {
                "passed": sell_r2,
                "name": "2. EMA 20 con pendiente descendente",
                "detail": f"Pendiente H1 ({'Descendente' if h1_ema20_slope_desc else 'Ascendente'})",
            },
            "r3_m15_pullback_ema20": {
                "passed": sell_r3,
                "name": "3. M15 retroceso a resistencia EMA 20",
                "detail": f"Distancia a EMA 20 M15: {pullback_dist_pct:.2f}%",
            },
            "r4_rsi_loses_50": {
                "passed": sell_r4,
                "name": "4. RSI M15 pierde nivel 50",
                "detail": f"RSI M15 actual = {curr_rsi_m15:.1f} (Pierde nivel 50)",
            },
            "r5_bearish_confirmation_candle": {
                "passed": sell_r5,
                "name": "5. Vela bajista de confirmación",
                "detail": f"{candle_pattern['description']} [{candle_pattern['pattern']}]",
            },
            "r6_breakdown_candle_low": {
                "passed": sell_r6,
                "name": "6. Entrada al romper mínimo de vela",
                "detail": f"Precio (${current_price:,.2f}) {'<=' if breakout_sell else '>'} Mínimo (${conf_low:,.2f})",
            },
        }

        buy_passed_count = sum(1 for v in checklist_buy.values() if v["passed"])
        sell_passed_count = sum(1 for v in checklist_sell.values() if v["passed"])

        # -------------------------------------------------------------
        # CÁLCULO ESTRICTO DE RISK/REWARD 1:2
        # -------------------------------------------------------------
        # Stop loss estructural basado en la vela de confirmación y el soporte/resistencia
        sl_pct_buy = max(0.40, min(1.10, round(structural_sl_distance_buy * 100.0, 2)))
        tp_pct_buy = round(sl_pct_buy * 2.0, 2)  # ¡EXACTO 1:2!

        sl_pct_sell = max(0.40, min(1.10, round(structural_sl_distance_sell * 100.0, 2)))
        tp_pct_sell = round(sl_pct_sell * 2.0, 2)  # ¡EXACTO 1:2!

        target_sl_price_buy = round(current_price * (1.0 - sl_pct_buy / 100.0), 2)
        target_tp_price_buy = round(current_price * (1.0 + tp_pct_buy / 100.0), 2)

        target_sl_price_sell = round(current_price * (1.0 + sl_pct_sell / 100.0), 2)
        target_tp_price_sell = round(current_price * (1.0 - tp_pct_sell / 100.0), 2)

        # Determinación de Señal
        signal = "HOLD"
        reason = "Esperando alineación completa de las 6 reglas institucionales"
        confidence = 0.50

        if buy_passed_count == 6:
            if any_exclusion_active_buy:
                signal = "HOLD"
                blocked_reasons = [v["desc"] for v in exclusions.values() if v["blocked"]]
                reason = f"Señal de COMPRA 6/6 bloqueada por filtro de seguridad: {', '.join(blocked_reasons)}"
                confidence = 0.65
            else:
                signal = "BUY"
                reason = (
                    f"¡SEÑAL ALCISTA CONFIRMADA 6/6! H1 > EMA 200, Pullback M15 en EMA 20 superado, "
                    f"RSI {curr_rsi_m15:.1f} >= 50, Vela {candle_pattern['pattern']}. "
                    f"Objetivo 1:2 -> TP: +{tp_pct_buy}% (${target_tp_price_buy:,.2f}) / SL: -{sl_pct_buy}% (${target_sl_price_buy:,.2f})"
                )
                confidence = 0.96
        elif sell_passed_count >= 5 and position_exposure > 0.02:
            signal = "SELL"
            reason = (
                f"SEÑAL DE SALIDA / VENTA {sell_passed_count}/6: H1 < EMA 200, EMA 20 descendente, "
                f"RSI perdió nivel 50 ({curr_rsi_m15:.1f}) y confirmación bajista {candle_pattern['pattern']}."
            )
            confidence = 0.94
        else:
            # Resumen de estado actual
            if buy_passed_count >= 4:
                reason = f"Configuración alcista en desarrollo ({buy_passed_count}/6 reglas activas). Esperando confirmación final."
                confidence = round(0.50 + buy_passed_count * 0.06, 2)
            elif sell_passed_count >= 4:
                reason = f"Presión bajista en desarrollo ({sell_passed_count}/6 reglas). Monitoreando soporte."
                confidence = round(0.50 + sell_passed_count * 0.06, 2)
            else:
                reason = f"Mercado en espera | H1 vs EMA200: {'Alcista' if buy_r1 else 'Bajista'} | Reglas Buy: {buy_passed_count}/6 | Reglas Sell: {sell_passed_count}/6"
                confidence = 0.50

        return {
            "book": book,
            "current_price": current_price,
            "signal": signal,
            "confidence": confidence,
            "reason": reason,
            "h1": {
                "price": current_price,
                "ema200": round(curr_ema200_h1, 2),
                "ema20": round(curr_ema20_h1, 2),
                "ema20_slope": "ASCENDENTE" if h1_ema20_slope_asc else "DESCENDENTE",
                "trend": "BULLISH" if buy_r1 else "BEARISH",
            },
            "m15": {
                "price": current_price,
                "ema20": round(curr_ema20_m15, 2),
                "rsi_14": round(curr_rsi_m15, 1),
                "pullback_dist_pct": round(pullback_dist_pct, 2),
                "pattern": candle_pattern["pattern"],
                "pattern_desc": candle_pattern["description"],
                "candle_high": round(conf_high, 2),
                "candle_low": round(conf_low, 2),
            },
            "rules_passed_count": buy_passed_count if buy_r1 else sell_passed_count,
            "checklist_buy": checklist_buy,
            "checklist_sell": checklist_sell,
            "exclusion_filters": exclusions,
            "risk_reward": {
                "ratio": "1:2",
                "sl_pct": sl_pct_buy,
                "tp_pct": tp_pct_buy,
                "target_sl_price": target_sl_price_buy,
                "target_tp_price": target_tp_price_buy,
            },
        }
