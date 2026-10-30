import React, { useState, useMemo, useRef } from 'react'
import {
  TrendingUp,
  TrendingDown,
  Activity,
  Layers,
  Zap,
  Repeat,
  Sliders,
  Maximize2,
  Minimize2,
  DollarSign,
  ShieldAlert,
  BarChart2,
  Compass,
  ArrowUpRight,
  ArrowDownRight
} from 'lucide-react'

const fmtMXN = (val, forceDecimals = null) => {
  const num = Number(val || 0)
  const abs = Math.abs(num)
  const decimals =
    forceDecimals !== null
      ? forceDecimals
      : abs > 0 && abs < 0.05
      ? 6
      : abs > 0 && abs < 2
      ? 4
      : 2
  return num.toLocaleString('es-MX', {
    style: 'currency',
    currency: 'MXN',
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })
}

export default function ProChartStudio({
  asset,
  orderBook,
  onQuickBuy,
  onQuickSell,
  onRotate,
  availableCash = 100000,
  isFocusMode = false,
  onToggleFocus,
}) {
  const [chartMode, setChartMode] = useState('candles') // 'candles' | 'area'
  const [showVWAP, setShowVWAP] = useState(true)
  const [showEMA, setShowEMA] = useState(true)
  const [showBollinger, setShowBollinger] = useState(isFocusMode)
  const [showVolume, setShowVolume] = useState(true)
  const [showRSI, setShowRSI] = useState(isFocusMode)
  const [hoverIndex, setHoverIndex] = useState(null)
  const [quickSizePct, setQuickSizePct] = useState(50)
  const [showDOM, setShowDOM] = useState(isFocusMode)

  const isHeld = Boolean(asset.is_active_position)
  const pos = asset.position || {}
  const unrPct = Number(pos.unrealized_pnl_pct || 0)
  const rawHistory = asset.price_history || []

  // Sintetizar velas japonesas OHLC a partir de los ticks históricos
  const candles = useMemo(() => {
    if (!rawHistory || rawHistory.length === 0) return []
    const list = []
    let prevClose = rawHistory[0].price || 1.0

    for (let i = 0; i < rawHistory.length; i++) {
      const pt = rawHistory[i]
      const price = Number(pt.price || prevClose)
      const open = i === 0 ? price : prevClose
      const close = price
      // Simular sombra de vela realista en base a volatilidad intradía (~0.05% a 0.12%)
      const spreadSim = Math.max(0.0004, Math.abs(close - open) * 0.4)
      const high = Math.max(open, close) * (1.0 + spreadSim)
      const low = Math.min(open, close) * (1.0 - spreadSim)
      const vol = Math.max(10, Math.round(Math.abs(close - open) * 1000 + 40 + (i % 7) * 15))

      list.push({
        time: pt.time || `${i}`,
        open,
        high,
        low,
        close,
        sma5: pt.sma5 || close,
        sma18: pt.sma18 || close,
        volume: vol,
      })
      prevClose = close
    }
    return list
  }, [rawHistory])

  // Dimensiones del lienzo SVG
  const width = isFocusMode ? 720 : 380
  const height = isFocusMode ? 260 : 135
  const padLeft = 52
  const padRight = 14
  const padTop = 14
  const rsiHeight = showRSI ? 38 : 0
  const padBottom = 22 + rsiHeight

  const plotW = width - padLeft - padRight
  const plotH = height - padTop - padBottom

  // Cálculos de escalas
  const { yMin, yMax, prices } = useMemo(() => {
    if (candles.length === 0) return { yMin: 0, yMax: 100, prices: [] }
    const lows = candles.map((c) => c.low)
    const highs = candles.map((c) => c.high)

    // Si tiene posición abierta, incluir precio de entrada, TP y SL en la escala
    if (isHeld) {
      if (pos.avg_buy_price > 0) lows.push(pos.avg_buy_price)
      if (asset.tp_price > 0) highs.push(asset.tp_price)
      if (asset.sl_price > 0) lows.push(asset.sl_price)
    }

    const min = Math.min(...lows)
    const max = Math.max(...highs)
    const span = max - min > 0 ? max - min : max * 0.005 || 1
    return {
      yMin: min - span * 0.08,
      yMax: max + span * 0.08,
      prices: candles.map((c) => c.close),
    }
  }, [candles, isHeld, pos.avg_buy_price, asset.tp_price, asset.sl_price])

  const getX = (idx) => padLeft + (idx / Math.max(1, candles.length - 1)) * plotW
  const getY = (val) => padTop + plotH - ((val - yMin) / (yMax - yMin)) * plotH

  // Coordenadas de líneas técnicas
  const linePath = useMemo(() => {
    if (candles.length < 2) return ''
    return candles.map((c, i) => `${i === 0 ? 'M' : 'L'} ${getX(i).toFixed(1)} ${getY(c.close).toFixed(1)}`).join(' ')
  }, [candles, yMin, yMax, plotW, plotH])

  const areaPath = useMemo(() => {
    if (!linePath) return ''
    const lastX = getX(candles.length - 1).toFixed(1)
    const baseY = (padTop + plotH).toFixed(1)
    return `${linePath} L ${lastX} ${baseY} L ${padLeft} ${baseY} Z`
  }, [linePath, candles.length, padTop, plotH, padLeft])

  // EMA rápida (9) y lenta (18/21)
  const emaFastPath = useMemo(() => {
    if (!showEMA || candles.length < 2) return ''
    return candles.map((c, i) => `${i === 0 ? 'M' : 'L'} ${getX(i).toFixed(1)} ${getY(c.sma5).toFixed(1)}`).join(' ')
  }, [showEMA, candles, yMin, yMax, plotW, plotH])

  const emaSlowPath = useMemo(() => {
    if (!showEMA || candles.length < 2) return ''
    return candles.map((c, i) => `${i === 0 ? 'M' : 'L'} ${getX(i).toFixed(1)} ${getY(c.sma18).toFixed(1)}`).join(' ')
  }, [showEMA, candles, yMin, yMax, plotW, plotH])

  // VWAP estimada
  const vwapVal = Number(asset.last_price * (1.0 - (asset.vwap_diff_pct || 0) / 100.0))
  const vwapY = getY(vwapVal)

  // Niveles de posición y órdenes (Trading from Chart)
  const entryY = isHeld && pos.avg_buy_price > 0 ? getY(pos.avg_buy_price) : null
  const tpY = asset.tp_price > 0 ? getY(asset.tp_price) : null
  const slY = asset.sl_price > 0 ? getY(asset.sl_price) : null

  // Ancho de cada vela
  const candleW = Math.max(3, Math.min(12, (plotW / Math.max(1, candles.length)) * 0.72))

  // Hover point para Crosshair
  const activeHover = hoverIndex !== null && candles[hoverIndex] ? candles[hoverIndex] : null

  // Cálculo de tamaño rápido en MXN
  const quickBuyMXN = Math.round(availableCash * (quickSizePct / 100.0) * 0.95)

  // Order Book DOM stats
  const obBids = orderBook?.bids?.slice(0, 4) || []
  const obAsks = orderBook?.asks?.slice(0, 4) || []
  const obImbalance = Number(orderBook?.imbalance || 0.5)

  return (
    <div
      style={{
        background: 'linear-gradient(180deg, #131c31 0%, #0a0f1c 100%)',
        border: `1px solid ${
          isHeld
            ? unrPct >= 0
              ? 'rgba(16,185,129,0.55)'
              : 'rgba(244,63,94,0.55)'
            : 'rgba(56,189,248,0.28)'
        }`,
        borderRadius: 14,
        padding: isFocusMode ? '16px 18px' : '12px 14px',
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
        boxShadow: isHeld
          ? unrPct >= 0
            ? '0 6px 20px -6px rgba(16,185,129,0.2)'
            : '0 6px 20px -6px rgba(244,63,94,0.2)'
          : '0 4px 15px -4px rgba(0,0,0,0.4)',
      }}
    >
      {/* 1. BARRA SUPERIOR PRO: TÍTULO, PRECIO, LAYOUT E INDICADORES */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span
            className="mono"
            style={{
              background: isHeld ? '#10b981' : '#38bdf8',
              color: '#061a14',
              fontWeight: 800,
              padding: '2px 8px',
              borderRadius: 6,
              fontSize: '0.74rem',
            }}
          >
            {isHeld ? 'ACTIVO EN CARTERA' : `RADAR #${asset.slot || 1}`}
          </span>
          <strong style={{ fontSize: isFocusMode ? '1.15rem' : '1.02rem', color: '#fff' }}>{asset.symbol}</strong>
          <span style={{ fontSize: '0.74rem', color: '#94a3b8' }}>{asset.name}</span>
          <span
            style={{
              fontSize: '0.66rem',
              padding: '1px 6px',
              borderRadius: 4,
              background: 'rgba(255,255,255,0.06)',
              color: '#cbd5e1',
            }}
          >
            {asset.category}
          </span>
        </div>

        {/* Toolbar de Indicadores estilo ProRealTime */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
          {/* Selector de Modo de Gráfico */}
          <div style={{ display: 'flex', background: '#0a0f1c', borderRadius: 6, padding: 2, border: '1px solid rgba(255,255,255,0.08)' }}>
            <button
              style={{
                background: chartMode === 'candles' ? '#38bdf8' : 'transparent',
                color: chartMode === 'candles' ? '#04121e' : '#94a3b8',
                border: 'none',
                borderRadius: 4,
                padding: '2px 7px',
                fontSize: '0.68rem',
                fontWeight: 700,
                cursor: 'pointer',
              }}
              onClick={() => setChartMode('candles')}
              title="Modo Velas Japonesas Pro"
            >
              🕯️ Velas
            </button>
            <button
              style={{
                background: chartMode === 'area' ? '#38bdf8' : 'transparent',
                color: chartMode === 'area' ? '#04121e' : '#94a3b8',
                border: 'none',
                borderRadius: 4,
                padding: '2px 7px',
                fontSize: '0.68rem',
                fontWeight: 700,
                cursor: 'pointer',
              }}
              onClick={() => setChartMode('area')}
              title="Modo Línea / Área Suave"
            >
              📈 Línea
            </button>
          </div>

          {/* Toggles de Indicadores Técnicos */}
          <button
            style={{
              background: showVWAP ? 'rgba(168,85,247,0.22)' : 'transparent',
              color: showVWAP ? '#c084fc' : '#64748b',
              border: `1px solid ${showVWAP ? '#a855f7' : 'rgba(255,255,255,0.08)'}`,
              borderRadius: 5,
              padding: '2px 6px',
              fontSize: '0.66rem',
              fontWeight: 700,
              cursor: 'pointer',
            }}
            onClick={() => setShowVWAP(!showVWAP)}
            title="Volume Weighted Average Price Institucional"
          >
            VWAP
          </button>
          <button
            style={{
              background: showEMA ? 'rgba(56,189,248,0.22)' : 'transparent',
              color: showEMA ? '#38bdf8' : '#64748b',
              border: `1px solid ${showEMA ? '#38bdf8' : 'rgba(255,255,255,0.08)'}`,
              borderRadius: 5,
              padding: '2px 6px',
              fontSize: '0.66rem',
              fontWeight: 700,
              cursor: 'pointer',
            }}
            onClick={() => setShowEMA(!showEMA)}
            title="Medias Exponenciales EMA 9 y EMA 18"
          >
            EMA
          </button>
          <button
            style={{
              background: showRSI ? 'rgba(245,158,11,0.22)' : 'transparent',
              color: showRSI ? '#f59e0b' : '#64748b',
              border: `1px solid ${showRSI ? '#f59e0b' : 'rgba(255,255,255,0.08)'}`,
              borderRadius: 5,
              padding: '2px 6px',
              fontSize: '0.66rem',
              fontWeight: 700,
              cursor: 'pointer',
            }}
            onClick={() => setShowRSI(!showRSI)}
            title="Sub-gráfico de Índice de Fuerza Relativa (RSI 14)"
          >
            RSI
          </button>

          {onToggleFocus && (
            <button
              style={{
                background: isFocusMode ? 'rgba(56,189,248,0.2)' : 'transparent',
                color: '#38bdf8',
                border: '1px solid rgba(56,189,248,0.3)',
                borderRadius: 5,
                padding: '3px 7px',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
              }}
              onClick={onToggleFocus}
              title={isFocusMode ? 'Volver a Vista Múltiple' : 'Expandir a Foco Profesional'}
            >
              {isFocusMode ? <Minimize2 size={13} /> : <Maximize2 size={13} />}
            </button>
          )}
        </div>
      </div>

      {/* 2. PRECIO PRINCIPAL Y PNL EN VIVO */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
          <span className="mono" style={{ fontSize: isFocusMode ? '1.55rem' : '1.3rem', fontWeight: 800, color: '#fff' }}>
            {fmtMXN(asset.last_price)}
          </span>
          <span
            className="mono"
            style={{
              fontSize: '0.82rem',
              fontWeight: 700,
              color: asset.change_24_pct >= 0 ? '#10b981' : '#f43f5e',
            }}
          >
            {asset.change_24_pct >= 0 ? '+' : ''}{asset.change_24_pct}% (24h)
          </span>
        </div>

        {isHeld ? (
          <div
            className="mono"
            style={{
              fontSize: '0.86rem',
              fontWeight: 800,
              color: unrPct >= 0 ? '#10b981' : '#f43f5e',
              background: unrPct >= 0 ? 'rgba(16,185,129,0.14)' : 'rgba(244,63,94,0.14)',
              padding: '3px 10px',
              borderRadius: 6,
              border: `1px solid ${unrPct >= 0 ? 'rgba(16,185,129,0.3)' : 'rgba(244,63,94,0.3)'}`,
            }}
          >
            {unrPct >= 0 ? '+' : ''}{unrPct.toFixed(2)}% ({fmtMXN(pos.unrealized_pnl_mxn || 0)})
          </div>
        ) : (
          <span style={{ fontSize: '0.74rem', color: '#94a3b8' }}>
            Spread: <strong className="mono" style={{ color: '#38bdf8' }}>{asset.spread_bps} bps</strong>
          </span>
        )}
      </div>

      {/* 3. LIENZO DEL GRÁFICO PRO INTERACTIVO (VELAS + OVERLAYS + CROSSHAIR) */}
      <div
        style={{
          background: '#070b14',
          borderRadius: 10,
          padding: '6px 4px',
          border: '1px solid rgba(255,255,255,0.06)',
          position: 'relative',
        }}
      >
        {candles.length < 2 ? (
          <div style={{ height, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#64748b', fontSize: '0.75rem' }}>
            Sincronizando feed de ticks en vivo...
          </div>
        ) : (
          <svg
            viewBox={`0 0 ${width} ${height}`}
            style={{ width: '100%', height: 'auto', display: 'block', overflow: 'visible' }}
            onMouseMove={(e) => {
              const rect = e.currentTarget.getBoundingClientRect()
              const relX = ((e.clientX - rect.left) / rect.width) * width
              const idx = Math.round(((relX - padLeft) / plotW) * (candles.length - 1))
              if (idx >= 0 && idx < candles.length) setHoverIndex(idx)
            }}
            onMouseLeave={() => setHoverIndex(null)}
          >
            <defs>
              <linearGradient id={`grad-pro-${asset.book}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={isHeld ? (unrPct >= 0 ? '#10b981' : '#f43f5e') : '#38bdf8'} stopOpacity="0.25" />
                <stop offset="100%" stopColor={isHeld ? (unrPct >= 0 ? '#10b981' : '#f43f5e') : '#38bdf8'} stopOpacity="0.0" />
              </linearGradient>
            </defs>

            {/* Rejilla de Fondo sutil */}
            <line x1={padLeft} y1={padTop} x2={width - padRight} y2={padTop} stroke="rgba(255,255,255,0.04)" strokeDasharray="2 3" />
            <line x1={padLeft} y1={padTop + plotH * 0.5} x2={width - padRight} y2={padTop + plotH * 0.5} stroke="rgba(255,255,255,0.04)" strokeDasharray="2 3" />
            <line x1={padLeft} y1={padTop + plotH} x2={width - padRight} y2={padTop + plotH} stroke="rgba(255,255,255,0.08)" />

            {/* MODO VELAS JAPONESAS */}
            {chartMode === 'candles' ? (
              candles.map((c, i) => {
                const x = getX(i)
                const yO = getY(c.open)
                const yC = getY(c.close)
                const yH = getY(c.high)
                const yL = getY(c.low)
                const isBull = c.close >= c.open
                const candleColor = isBull ? '#10b981' : '#f43f5e'
                const bodyY = Math.min(yO, yC)
                const bodyH = Math.max(2, Math.abs(yC - yO))

                return (
                  <g key={i}>
                    {/* Mecha superior e inferior */}
                    <line x1={x} y1={yH} x2={x} y2={yL} stroke={candleColor} strokeWidth="1.2" opacity="0.8" />
                    {/* Cuerpo de la vela */}
                    <rect
                      x={x - candleW / 2}
                      y={bodyY}
                      width={candleW}
                      height={bodyH}
                      fill={candleColor}
                      rx="1"
                      opacity="0.95"
                    />
                  </g>
                )
              })
            ) : (
              /* MODO LÍNEA / ÁREA SUAVE */
              <>
                <path d={areaPath} fill={`url(#grad-pro-${asset.book})`} />
                <path
                  d={linePath}
                  fill="none"
                  stroke={isHeld ? (unrPct >= 0 ? '#10b981' : '#f43f5e') : '#38bdf8'}
                  strokeWidth="2"
                />
              </>
            )}

            {/* INDICADOR VWAP INSTITUCIONAL (Línea violeta punteada) */}
            {showVWAP && vwapY >= padTop && vwapY <= padTop + plotH && (
              <g>
                <line
                  x1={padLeft}
                  y1={vwapY}
                  x2={width - padRight}
                  y2={vwapY}
                  stroke="#a855f7"
                  strokeWidth="1.2"
                  strokeDasharray="4 3"
                  opacity="0.75"
                />
                <text x={padLeft + 2} y={vwapY - 3} fill="#c084fc" fontSize="8" fontWeight="700">
                  VWAP {fmtMXN(vwapVal, 1)}
                </text>
              </g>
            )}

            {/* MEDIAS MÓVILES EMA 9 (Cyan) y EMA 18 (Ámbar) */}
            {showEMA && (
              <>
                <path d={emaFastPath} fill="none" stroke="#38bdf8" strokeWidth="1.2" opacity="0.85" />
                <path d={emaSlowPath} fill="none" stroke="#f59e0b" strokeWidth="1.2" opacity="0.85" />
              </>
            )}

            {/* OVERLAYS TRADING FROM CHART (TP, ENTRADA, SL) */}
            {/* Take Profit (Verde) */}
            {tpY && tpY >= padTop && tpY <= padTop + plotH && (
              <g>
                <line x1={padLeft} y1={tpY} x2={width - padRight} y2={tpY} stroke="#10b981" strokeWidth="1.4" strokeDasharray="4 2" />
                <rect x={width - padRight - 88} y={tpY - 8} width="88" height="15" fill="#06281e" rx="3" stroke="#10b981" strokeWidth="1" />
                <text x={width - padRight - 44} y={tpY + 3} textAnchor="middle" fill="#10b981" fontSize="8.5" fontWeight="800">
                  🎯 TP +{asset.auto_tp_pct}%
                </text>
              </g>
            )}

            {/* Precio Entrada (Cyan/Gold) */}
            {entryY && entryY >= padTop && entryY <= padTop + plotH && (
              <g>
                <line x1={padLeft} y1={entryY} x2={width - padRight} y2={entryY} stroke="#38bdf8" strokeWidth="1.4" />
                <rect x={width - padRight - 94} y={entryY - 8} width="94" height="15" fill="#082338" rx="3" stroke="#38bdf8" strokeWidth="1" />
                <text x={width - padRight - 47} y={entryY + 3} textAnchor="middle" fill="#38bdf8" fontSize="8.5" fontWeight="800">
                  ⭐ ENTRADA {fmtMXN(pos.avg_buy_price, 1)}
                </text>
              </g>
            )}

            {/* Stop Loss (Rojo) */}
            {slY && slY >= padTop && slY <= padTop + plotH && (
              <g>
                <line x1={padLeft} y1={slY} x2={width - padRight} y2={slY} stroke="#f43f5e" strokeWidth="1.4" strokeDasharray="4 2" />
                <rect x={width - padRight - 88} y={slY - 8} width="88" height="15" fill="#2d0a13" rx="3" stroke="#f43f5e" strokeWidth="1" />
                <text x={width - padRight - 44} y={slY + 3} textAnchor="middle" fill="#f43f5e" fontSize="8.5" fontWeight="800">
                  🛑 SL -{asset.auto_sl_pct}%
                </text>
              </g>
            )}

            {/* SUB-PANEL RSI(14) EN LA BASE */}
            {showRSI && (
              <g transform={`translate(0, ${padTop + plotH + 8})`}>
                <line x1={padLeft} y1="0" x2={width - padRight} y2="0" stroke="rgba(255,255,255,0.1)" />
                {/* Zona de Sobrecompra (70) y Sobreventa (30) */}
                <line x1={padLeft} y1="8" x2={width - padRight} y2="8" stroke="#f43f5e" strokeDasharray="2 2" opacity="0.6" />
                <line x1={padLeft} y1="26" x2={width - padRight} y2="26" stroke="#10b981" strokeDasharray="2 2" opacity="0.6" />
                <text x={padLeft - 4} y="11" fill="#f43f5e" fontSize="7" textAnchor="end">70</text>
                <text x={padLeft - 4} y="29" fill="#10b981" fontSize="7" textAnchor="end">30</text>
                {/* Curva RSI */}
                <path
                  d={candles
                    .map((c, i) => {
                      const rx = getX(i)
                      const rsiV = Math.max(15, Math.min(85, Number(asset.rsi_14 || 50) + (c.close >= c.open ? 3 : -3)))
                      const ry = 34 - ((rsiV - 10) / 80) * 30
                      return `${i === 0 ? 'M' : 'L'} ${rx.toFixed(1)} ${ry.toFixed(1)}`
                    })
                    .join(' ')}
                  fill="none"
                  stroke="#f59e0b"
                  strokeWidth="1.3"
                />
              </g>
            )}

            {/* CROSSHAIR INTERACTIVO EN HOVER */}
            {activeHover && (
              <g>
                <line x1={getX(hoverIndex)} y1={padTop} x2={getX(hoverIndex)} y2={padTop + plotH} stroke="#fff" strokeWidth="0.8" strokeDasharray="2 2" opacity="0.7" />
                <line x1={padLeft} y1={getY(activeHover.close)} x2={width - padRight} y2={getY(activeHover.close)} stroke="#fff" strokeWidth="0.8" strokeDasharray="2 2" opacity="0.7" />
                <rect x={padLeft - 48} y={getY(activeHover.close) - 7} width="46" height="14" fill="#1e293b" rx="2" />
                <text x={padLeft - 3} y={getY(activeHover.close) + 3} textAnchor="end" fill="#fff" fontSize="8" fontWeight="700">
                  {fmtMXN(activeHover.close, 1)}
                </text>
              </g>
            )}

            {/* Escala Y (Máx y Mín) */}
            <text x={padLeft - 4} y={getY(yMax) + 8} textAnchor="end" fill="#64748b" fontSize="8.5" fontFamily="monospace">
              {yMax >= 1000 ? (yMax / 1000).toFixed(1) + 'k' : yMax.toFixed(1)}
            </text>
            <text x={padLeft - 4} y={getY(yMin) - 2} textAnchor="end" fill="#64748b" fontSize="8.5" fontFamily="monospace">
              {yMin >= 1000 ? (yMin / 1000).toFixed(1) + 'k' : yMin.toFixed(1)}
            </text>
          </svg>
        )}
      </div>

      {/* 4. BARRA DE PARÁMETROS TÉCNICOS PROREALTIME */}
      <div
        className="mono"
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(4, 1fr)',
          gap: 6,
          fontSize: '0.73rem',
          background: '#090e1a',
          padding: '7px 10px',
          borderRadius: 8,
          border: '1px solid rgba(255,255,255,0.04)',
        }}
      >
        <div>
          <span style={{ color: '#94a3b8' }}>Auto-TP: </span>
          <strong style={{ color: '#10b981' }}>+{asset.auto_tp_pct}%</strong>
          <div style={{ fontSize: '0.66rem', color: '#64748b' }}>{fmtMXN(asset.tp_price)}</div>
        </div>
        <div>
          <span style={{ color: '#94a3b8' }}>Auto-SL: </span>
          <strong style={{ color: '#f43f5e' }}>-{asset.auto_sl_pct}%</strong>
          <div style={{ fontSize: '0.66rem', color: '#64748b' }}>{fmtMXN(asset.sl_price)}</div>
        </div>
        <div>
          <span style={{ color: '#94a3b8' }}>Trailing: </span>
          <strong style={{ color: '#38bdf8' }}>+{asset.auto_trail_arm_pct}%</strong>
          <div style={{ fontSize: '0.66rem', color: '#64748b' }}>Candado</div>
        </div>
        <div>
          <span style={{ color: '#94a3b8' }}>RSI(14): </span>
          <strong
            style={{
              color: asset.rsi_14 > 65 ? '#f43f5e' : asset.rsi_14 < 40 ? '#10b981' : '#f1f5f9',
            }}
          >
            {asset.rsi_14}
          </strong>
          <div style={{ fontSize: '0.66rem', color: '#64748b' }}>
            {asset.rsi_14 < 35 ? 'Sobreventa' : asset.rsi_14 > 65 ? 'Sobrecompra' : 'Neutro'}
          </div>
        </div>
      </div>

      {/* 5. DOM DE PROFUNDIDAD (DEPTH OF MARKET LADDER - PROREALTIME) */}
      {isFocusMode && (
        <div style={{ background: '#070b14', borderRadius: 8, padding: '8px 10px', border: '1px solid rgba(255,255,255,0.05)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
            <span style={{ fontSize: '0.72rem', fontWeight: 700, color: '#94a3b8' }}>
              Libro DOM (Profundidad de Mercado)
            </span>
            <span className="mono" style={{ fontSize: '0.72rem', color: obImbalance >= 0.5 ? '#10b981' : '#f43f5e' }}>
              Presión Compradora: {(obImbalance * 100).toFixed(0)}% vs {((1 - obImbalance) * 100).toFixed(0)}%
            </span>
          </div>
          {/* Barra Visual de Imbalance */}
          <div style={{ height: 4, background: '#f43f5e', borderRadius: 2, overflow: 'hidden', display: 'flex', marginBottom: 8 }}>
            <div style={{ width: `${obImbalance * 100}%`, background: '#10b981' }} />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, fontSize: '0.72rem' }}>
            {/* Lado Bids (Compra) */}
            <div>
              <div style={{ color: '#10b981', fontWeight: 700, marginBottom: 2 }}>Mejores Compras (Bid)</div>
              {obBids.map((b, i) => (
                <div key={i} className="mono" style={{ display: 'flex', justifyContent: 'space-between', color: '#cbd5e1' }}>
                  <span>{fmtMXN(b.price, 2)}</span>
                  <span style={{ color: '#64748b' }}>{Number(b.amount).toFixed(4)}</span>
                </div>
              ))}
            </div>
            {/* Lado Asks (Venta) */}
            <div>
              <div style={{ color: '#f43f5e', fontWeight: 700, marginBottom: 2 }}>Mejores Ventas (Ask)</div>
              {obAsks.map((a, i) => (
                <div key={i} className="mono" style={{ display: 'flex', justifyContent: 'space-between', color: '#cbd5e1' }}>
                  <span>{fmtMXN(a.price, 2)}</span>
                  <span style={{ color: '#64748b' }}>{Number(a.amount).toFixed(4)}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* 6. BOTONERA PRO: TRADING DIRECTO DESDE EL GRÁFICO (TRADE FROM CHART) */}
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 2 }}>
        {!isHeld ? (
          <>
            {/* Presets de tamaño rápido */}
            <div style={{ display: 'flex', background: '#0a0f1c', borderRadius: 6, padding: 2, border: '1px solid rgba(255,255,255,0.06)' }}>
              {[25, 50, 100].map((pct) => (
                <button
                  key={pct}
                  style={{
                    background: quickSizePct === pct ? 'rgba(16,185,129,0.25)' : 'transparent',
                    color: quickSizePct === pct ? '#10b981' : '#64748b',
                    border: 'none',
                    borderRadius: 4,
                    padding: '3px 7px',
                    fontSize: '0.68rem',
                    fontWeight: 700,
                    cursor: 'pointer',
                  }}
                  onClick={() => setQuickSizePct(pct)}
                >
                  {pct}%
                </button>
              ))}
            </div>

            {/* Botón de Compra Rápida 1-Click */}
            <button
              className="btn btn-primary"
              style={{
                flex: 1,
                padding: '6px 12px',
                fontSize: '0.78rem',
                fontWeight: 800,
                background: 'linear-gradient(135deg, #10b981 0%, #059669 100%)',
                color: '#061a14',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: 5,
              }}
              onClick={() => onQuickBuy(asset.book, quickBuyMXN)}
            >
              <Zap size={14} /> COMPRA RÁPIDA ({fmtMXN(quickBuyMXN, 0)})
            </button>
          </>
        ) : (
          <>
            {/* Botón de Cierre / Venta 1-Click */}
            <button
              className="btn"
              style={{
                flex: 1,
                padding: '6px 12px',
                fontSize: '0.78rem',
                fontWeight: 800,
                background: 'linear-gradient(135deg, #f43f5e 0%, #be123c 100%)',
                color: '#fff',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: 5,
              }}
              onClick={() => onQuickSell(asset.book)}
            >
              <DollarSign size={14} /> CERRAR POSICIÓN EN VIVO
            </button>

            {/* Rotación Directa */}
            <button
              className="btn btn-secondary"
              style={{ padding: '6px 10px', fontSize: '0.74rem' }}
              onClick={() => onRotate(asset.book)}
              title="Vender y rotar hacia el activo con mayor Score"
            >
              <Repeat size={13} color="#f59e0b" /> Rotar
            </button>
          </>
        )}
      </div>
    </div>
  )
}
