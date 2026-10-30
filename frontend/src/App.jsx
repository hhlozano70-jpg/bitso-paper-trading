import React, { useEffect, useState, useMemo, useRef } from 'react'
import {
  Activity,
  Bot,
  TrendingUp,
  TrendingDown,
  Wallet,
  RefreshCw,
  Play,
  Pause,
  Zap,
  BarChart2,
  BookOpen,
  Code2,
  Award,
  ArrowUpRight,
  ArrowDownRight,
  CheckCircle2,
  AlertCircle,
  Compass,
  Flame,
  Scale,
  Layers,
} from 'lucide-react'

const isLocalVite =
  typeof window !== 'undefined' && window.location.port === '5173'
const API_BASE = isLocalVite ? 'http://127.0.0.1:8000' : ''
const WS_URL = isLocalVite
  ? 'ws://127.0.0.1:8000/ws'
  : `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws`

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

const fmtNum = (val, decimals = 6) => {
  const num = Number(val || 0)
  return num.toLocaleString('es-MX', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })
}

function InteractiveChart({ data, mode, activeMeta }) {
  const [hoverIdx, setHoverIdx] = useState(null)
  const width = 820
  const height = 275
  const padLeft = 68
  const padRight = 18
  const padTop = 20
  const padBottom = 28

  const plotW = width - padLeft - padRight
  const plotH = height - padTop - padBottom

  const chartPoints = useMemo(() => {
    if (!data || data.length === 0) return []
    return data
  }, [data])

  if (chartPoints.length < 2) {
    return (
      <div style={{ height: 275, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#94a3b8' }}>
        Cargando historial de transacciones reales de Bitso...
      </div>
    )
  }

  const values = []
  chartPoints.forEach((pt) => {
    if (mode === 'price') {
      if (pt.price) values.push(pt.price)
      if (pt.sma5) values.push(pt.sma5)
      if (pt.sma18) values.push(pt.sma18)
    } else {
      if (pt.equity) values.push(pt.equity)
      if (pt.benchmark) values.push(pt.benchmark)
    }
  })

  const minVal = Math.min(...values)
  const maxVal = Math.max(...values)
  const span = maxVal - minVal > 0 ? maxVal - minVal : maxVal * 0.002 || 1
  const yMin = minVal - span * 0.12
  const yMax = maxVal + span * 0.12

  const getX = (idx) => padLeft + (idx / Math.max(1, chartPoints.length - 1)) * plotW
  const getY = (val) => padTop + plotH - ((val - yMin) / (yMax - yMin)) * plotH

  const buildPath = (key) =>
    chartPoints
      .map((pt, i) => `${i === 0 ? 'M' : 'L'} ${getX(i).toFixed(1)} ${getY(pt[key] ?? pt.price).toFixed(1)}`)
      .join(' ')

  const mainKey = mode === 'price' ? 'price' : 'equity'
  const mainLine = buildPath(mainKey)
  const areaPath = `${mainLine} L ${getX(chartPoints.length - 1).toFixed(1)} ${(padTop + plotH).toFixed(1)} L ${padLeft} ${(padTop + plotH).toFixed(1)} Z`

  const yTicks = [0, 0.25, 0.5, 0.75, 1].map((t) => yMin + t * (yMax - yMin))
  const hoveredPoint =
    hoverIdx !== null && chartPoints[hoverIdx] ? chartPoints[hoverIdx] : chartPoints[chartPoints.length - 1]

  return (
    <div style={{ position: 'relative' }}>
      <div
        className="mono"
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          justifyContent: 'space-between',
          gap: 12,
          fontSize: '0.76rem',
          marginBottom: 8,
          padding: '6px 10px',
          background: '#0b111e',
          borderRadius: 8,
          border: '1px solid rgba(255,255,255,0.05)',
        }}
      >
        {mode === 'price' ? (
          <>
            <div style={{ display: 'flex', gap: 14, alignItems: 'center' }}>
              <span style={{ color: '#38bdf8', fontWeight: 700 }}>
                ● Precio {activeMeta?.pair}: {fmtMXN(hoveredPoint?.price)}
              </span>
              <span style={{ color: '#10b981' }}>― SMA(5): {fmtMXN(hoveredPoint?.sma5)}</span>
              <span style={{ color: '#f59e0b' }}>-- SMA(18): {fmtMXN(hoveredPoint?.sma18)}</span>
            </div>
            <span style={{ color: '#94a3b8' }}>Hora: {hoveredPoint?.time}</span>
          </>
        ) : (
          <>
            <div style={{ display: 'flex', gap: 14, alignItems: 'center' }}>
              <span style={{ color: '#10b981', fontWeight: 700 }}>
                ● Tu Portafolio (Equity): {fmtMXN(hoveredPoint?.equity)}
              </span>
              <span style={{ color: '#a855f7' }}>-- Benchmark Buy & Hold: {fmtMXN(hoveredPoint?.benchmark)}</span>
            </div>
            <span style={{ color: '#94a3b8' }}>Hora: {hoveredPoint?.time}</span>
          </>
        )}
      </div>

      <svg
        viewBox={`0 0 ${width} ${height}`}
        style={{ width: '100%', height: 'auto', display: 'block', userSelect: 'none' }}
        onMouseLeave={() => setHoverIdx(null)}
      >
        <defs>
          <linearGradient id="chartGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={mode === 'price' ? '#38bdf8' : '#10b981'} stopOpacity="0.28" />
            <stop offset="100%" stopColor={mode === 'price' ? '#38bdf8' : '#10b981'} stopOpacity="0.0" />
          </linearGradient>
        </defs>

        {yTicks.map((val, i) => {
          const y = getY(val)
          return (
            <g key={i}>
              <line
                x1={padLeft}
                y1={y}
                x2={width - padRight}
                y2={y}
                stroke="rgba(255,255,255,0.06)"
                strokeDasharray="3 3"
              />
              <text
                x={padLeft - 8}
                y={y + 4}
                textAnchor="end"
                fill="#64748b"
                fontSize="10"
                fontFamily="JetBrains Mono, monospace"
              >
                {val >= 1000 ? `$${(val / 1000).toFixed(1)}k` : val < 0.1 ? `$${val.toFixed(5)}` : `$${val.toFixed(2)}`}
              </text>
            </g>
          )
        })}

        <path d={areaPath} fill="url(#chartGrad)" />
        <path d={mainLine} fill="none" stroke={mode === 'price' ? '#38bdf8' : '#10b981'} strokeWidth="2.3" />

        {mode === 'price' && (
          <>
            <path d={buildPath('sma5')} fill="none" stroke="#10b981" strokeWidth="1.5" strokeOpacity="0.85" />
            <path
              d={buildPath('sma18')}
              fill="none"
              stroke="#f59e0b"
              strokeWidth="1.5"
              strokeDasharray="4 4"
              strokeOpacity="0.85"
            />
          </>
        )}

        {mode === 'equity' && (
          <path d={buildPath('benchmark')} fill="none" stroke="#a855f7" strokeWidth="1.7" strokeDasharray="4 4" />
        )}

        {chartPoints.length > 0 && (
          <circle
            cx={getX(chartPoints.length - 1)}
            cy={getY(chartPoints[chartPoints.length - 1][mainKey])}
            r="4.5"
            fill={mode === 'price' ? '#38bdf8' : '#10b981'}
            stroke="#090d16"
            strokeWidth="2"
          />
        )}

        {hoverIdx !== null && chartPoints[hoverIdx] && (
          <g>
            <line
              x1={getX(hoverIdx)}
              y1={padTop}
              x2={getX(hoverIdx)}
              y2={padTop + plotH}
              stroke="rgba(255,255,255,0.28)"
              strokeDasharray="2 2"
            />
            <circle
              cx={getX(hoverIdx)}
              cy={getY(chartPoints[hoverIdx][mainKey])}
              r="5"
              fill="#fff"
              stroke="#38bdf8"
              strokeWidth="2"
            />
          </g>
        )}

        {[0, Math.floor(chartPoints.length / 2), chartPoints.length - 1].map((idx) => {
          const pt = chartPoints[idx]
          if (!pt) return null
          return (
            <text
              key={idx}
              x={getX(idx)}
              y={height - 7}
              textAnchor="middle"
              fill="#64748b"
              fontSize="10"
              fontFamily="JetBrains Mono, monospace"
            >
              {pt.time}
            </text>
          )
        })}

        {chartPoints.map((_, idx) => (
          <rect
            key={idx}
            x={getX(idx) - plotW / chartPoints.length / 2}
            y={padTop}
            width={plotW / chartPoints.length}
            height={plotH}
            fill="transparent"
            onMouseEnter={() => setHoverIdx(idx)}
          />
        ))}
      </svg>
    </div>
  )
}

export default function App() {
  const [state, setState] = useState(null)
  const [wsConnected, setWsConnected] = useState(false)
  const [chartMode, setChartMode] = useState('price')
  const [scannerFilter, setScannerFilter] = useState('TOP_BUY') // TOP_BUY | ALL | Cripto MXN | Oro & RWA | Divisas & FX | Layer-1 & DeFi | Alta Volatilidad | ARBITRAGE | POSITIONS
  const [orderSide, setOrderSide] = useState('BUY')
  const [orderAmountMxn, setOrderAmountMxn] = useState('15000')
  const [orderCryptoQty, setOrderCryptoQty] = useState('')
  const [statusBanner, setStatusBanner] = useState(null)
  const [showAiCodeModal, setShowAiCodeModal] = useState(false)
  const [busy, setBusy] = useState(false)
  const wsRef = useRef(null)

  const showToast = (type, message) => {
    setStatusBanner({ type, message })
    setTimeout(() => {
      setStatusBanner((prev) => (prev?.message === message ? null : prev))
    }, 4800)
  }

  const fetchState = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/state`)
      if (res.ok) {
        const data = await res.json()
        setState(data)
      }
    } catch (err) {
      console.error('Error consultando estado:', err)
    }
  }

  useEffect(() => {
    fetchState()
    let reconnectTimer = null
    const connectWs = () => {
      const ws = new WebSocket(WS_URL)
      wsRef.current = ws
      ws.onopen = () => setWsConnected(true)
      ws.onmessage = (evt) => {
        try {
          const payload = JSON.parse(evt.data)
          setState(payload)
        } catch (e) {
          console.error(e)
        }
      }
      ws.onclose = () => {
        setWsConnected(false)
        reconnectTimer = setTimeout(connectWs, 3000)
      }
      ws.onerror = () => ws.close()
    }
    connectWs()
    const pollInterval = setInterval(fetchState, 4000)
    return () => {
      clearInterval(pollInterval)
      if (reconnectTimer) clearTimeout(reconnectTimer)
      if (wsRef.current) wsRef.current.close()
    }
  }, [])

  if (!state) {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 12 }}>
        <RefreshCw size={22} color="#10b981" />
        <span style={{ fontWeight: 600 }}>Escaneando 24 mercados y activos en tiempo real desde Bitso...</span>
      </div>
    )
  }

  const catalog = state.asset_catalog || {}
  const activeBook = state.active_book || 'btc_mxn'
  const bookMeta = catalog[activeBook] || {
    name: activeBook.toUpperCase(),
    symbol: activeBook.split('_')[0].toUpperCase(),
    pair: activeBook.toUpperCase(),
    category: 'Cripto',
  }
  const ticker = state.active_ticker || {}
  const portfolio = state.portfolio || {}
  const activePos = portfolio.positions?.[activeBook] || {
    amount: 0,
    avg_buy_price: 0,
    market_value_mxn: 0,
    unrealized_pnl_mxn: 0,
    unrealized_pnl_pct: 0,
  }
  const bot = state.bot || {}
  const lastSignal = bot.last_signal || {}
  const features = lastSignal.features || {}
  const orderBook = state.order_book || { bids: [], asks: [], imbalance: 0.5 }
  const opportunities = state.opportunities || []
  const arbitrage = state.arbitrage || []

  const openPositionsList = Object.values(portfolio.positions || {}).filter((p) => p.amount > 1e-8)

  const filteredOpportunities = opportunities.filter((opp) => {
    if (scannerFilter === 'TOP_BUY') return opp.opportunity_score >= 58
    if (scannerFilter === 'ALL') return true
    if (scannerFilter === 'POSITIONS') return opp.has_position
    return opp.category === scannerFilter
  })

  const top3Opportunities = opportunities.slice(0, 3)

  const handleSwitchBook = async (book) => {
    setBusy(true)
    try {
      const res = await fetch(`${API_BASE}/api/book`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ book }),
      })
      if (res.ok) {
        const data = await res.json()
        setState(data)
      }
    } finally {
      setBusy(false)
    }
  }

  const handleQuickOrder = async (book, side, mxnAmount = null, cryptoAmount = null, customReason = null) => {
    setBusy(true)
    try {
      const meta = catalog[book] || { symbol: book.toUpperCase(), pair: book.toUpperCase() }
      const payload = {
        book,
        side,
        mxn_amount: mxnAmount,
        crypto_amount: cryptoAmount,
        reason: customReason || `Orden rápida (${side}) desde Radar en ${meta.pair}`,
      }
      const res = await fetch(`${API_BASE}/api/order`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      const data = await res.json()
      if (!res.ok) {
        showToast('error', data.detail || 'No se pudo ejecutar la orden')
      } else {
        setState(data.state)
        const tr = data.result.trade
        showToast(
          'success',
          `${tr.side} ejecutado en ${meta.symbol}: ${tr.amount} a ${fmtMXN(tr.price)} (Total: ${fmtMXN(tr.total_mxn)})`
        )
      }
    } catch (err) {
      showToast('error', 'Error de red al enviar orden')
    } finally {
      setBusy(false)
    }
  }

  const handleManualOrder = async (e) => {
    e.preventDefault()
    if (orderSide === 'BUY') {
      await handleQuickOrder(
        activeBook,
        'BUY',
        parseFloat(orderAmountMxn),
        null,
        `Orden manual (BUY) en ${bookMeta.pair}`
      )
    } else {
      await handleQuickOrder(
        activeBook,
        'SELL',
        null,
        parseFloat(orderCryptoQty || activePos.amount),
        `Orden manual (SELL) en ${bookMeta.pair}`
      )
    }
  }

  const handleUpdateBot = async (patch) => {
    try {
      const res = await fetch(`${API_BASE}/api/bot/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(patch),
      })
      if (res.ok) {
        const data = await res.json()
        setState(data)
      }
    } catch (err) {
      showToast('error', 'Error actualizando configuración del bot')
    }
  }

  const handleStepBot = async (forceSide = null, targetBook = null) => {
    setBusy(true)
    try {
      const res = await fetch(`${API_BASE}/api/bot/step`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ force_trade_side: forceSide, target_book: targetBook }),
      })
      if (res.ok) {
        const data = await res.json()
        setState(data.state)
        const tr = data.step_result?.executed_trade
        const sig = data.step_result?.signal
        if (tr) {
          const sym = catalog[tr.book]?.symbol || tr.book.toUpperCase()
          showToast(
            'success',
            `Bot ejecutó ${tr.side} en ${sym}: ${tr.amount} @ ${fmtMXN(tr.price)} — ${tr.reason}`
          )
        } else if (sig) {
          showToast('info', `Señal evaluada (${sig.action}): ${sig.reason}`)
        }
      }
    } finally {
      setBusy(false)
    }
  }

  const handleResetPortfolio = async () => {
    setBusy(true)
    try {
      const res = await fetch(`${API_BASE}/api/portfolio/reset`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ initial_cash_mxn: 100000, fee_rate: portfolio.fee_rate ?? 0.0015 }),
      })
      if (res.ok) {
        const data = await res.json()
        setState(data)
        showToast('info', 'Portafolio virtual reiniciado a $100,000.00 MXN')
      }
    } finally {
      setBusy(false)
    }
  }

  const applyQuickPct = (pct) => {
    if (orderSide === 'BUY') {
      const mxn = Math.floor((portfolio.cash_mxn || 0) * (pct / 100))
      setOrderAmountMxn(String(mxn))
    } else {
      const qty = ((activePos.amount || 0) * (pct / 100)).toFixed(8)
      setOrderCryptoQty(String(qty))
    }
  }

  const maxObVol = Math.max(
    ...[...(orderBook.bids || []), ...(orderBook.asks || [])].map((x) => x.amount || 0.001),
    0.001
  )

  return (
    <div className="app-shell">
      {/* TOP BAR */}
      <header className="topbar">
        <div className="brand">
          <div className="brand-logo mono">B⚡</div>
          <div>
            <div className="brand-title">
              Bitso Multi-Asset Scanner & AI Paper Trader
              <span className="badge-live">
                <span className="pulse-dot" />
                24 ACTIVOS EN VIVO • FX USD/MXN: ${state.usd_mxn_rate}
              </span>
            </div>
            <div style={{ fontSize: '0.77rem', color: '#94a3b8' }}>
              Detectando oportunidades en Cripto MXN, Oro Físico (PAXG), RWA (ONDO), Divisas (USD/EUR), DeFi y Arbitraje
            </div>
          </div>
        </div>

        {/* Selector Rápido de Activo en Gráfico */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <span style={{ fontSize: '0.76rem', color: '#94a3b8', fontWeight: 600 }}>Activo en Terminal:</span>
          <select
            className="select-field mono"
            style={{ width: 250, fontWeight: 700, borderColor: '#38bdf8' }}
            value={activeBook}
            onChange={(e) => handleSwitchBook(e.target.value)}
          >
            {opportunities.map((opp) => (
              <option key={opp.book} value={opp.book}>
                [{opp.category}] {opp.symbol} ({opp.pair}) — Score: {opp.opportunity_score}
              </option>
            ))}
          </select>

          <button className="btn btn-secondary" onClick={() => setShowAiCodeModal((v) => !v)}>
            <Code2 size={15} color="#a855f7" />
            {showAiCodeModal ? 'Ocultar Guía IA' : 'Conectar tu IA'}
          </button>
          <button className="btn btn-secondary" onClick={handleResetPortfolio} disabled={busy}>
            <RefreshCw size={14} />
            Reiniciar $100k MXN
          </button>
        </div>
      </header>

      {/* TOAST BANNER */}
      {statusBanner && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            padding: '10px 16px',
            borderRadius: 10,
            background:
              statusBanner.type === 'error'
                ? 'rgba(244,63,94,0.16)'
                : statusBanner.type === 'success'
                ? 'rgba(16,185,129,0.16)'
                : 'rgba(56,189,248,0.15)',
            border: `1px solid ${
              statusBanner.type === 'error'
                ? '#f43f5e'
                : statusBanner.type === 'success'
                ? '#10b981'
                : '#38bdf8'
            }`,
            fontSize: '0.85rem',
            fontWeight: 600,
          }}
        >
          {statusBanner.type === 'error' ? (
            <AlertCircle size={17} color="#f43f5e" />
          ) : (
            <CheckCircle2 size={17} color="#10b981" />
          )}
          <span>{statusBanner.message}</span>
        </div>
      )}

      {/* KPI STRIP */}
      <section className="kpi-grid">
        <div className="card kpi-card">
          <div className="kpi-label">
            <span>Valor Total Portafolio (Equity)</span>
            <Wallet size={16} color="#38bdf8" />
          </div>
          <div className="kpi-value mono">{fmtMXN(portfolio.total_equity_mxn)}</div>
          <div className="kpi-sub">
            <span className={`pos-pill ${portfolio.total_return_mxn >= 0 ? 'up' : 'down'} mono`}>
              {portfolio.total_return_mxn >= 0 ? '+' : ''}
              {fmtMXN(portfolio.total_return_mxn)} ({portfolio.total_return_pct >= 0 ? '+' : ''}
              {portfolio.total_return_pct}%)
            </span>
            <span>vs inicial {fmtMXN(portfolio.initial_cash_mxn, 0)}</span>
          </div>
        </div>

        <div className="card kpi-card">
          <div className="kpi-label">
            <span>Efectivo Disponible (MXN Virtual)</span>
            <Activity size={16} color="#10b981" />
          </div>
          <div className="kpi-value mono">{fmtMXN(portfolio.cash_mxn)}</div>
          <div className="kpi-sub">
            <span>Invertido en {openPositionsList.length} activos: {fmtMXN(portfolio.holdings_value_mxn)}</span>
          </div>
        </div>

        <div className="card kpi-card">
          <div className="kpi-label">
            <span>Mejor Oportunidad Ahora (#1 Radar)</span>
            <Flame size={16} color="#f59e0b" />
          </div>
          {top3Opportunities[0] ? (
            <>
              <div className="kpi-value mono" style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <span style={{ color: '#10b981' }}>{top3Opportunities[0].symbol}</span>
                <span style={{ fontSize: '1.05rem', color: '#f3f6fc' }}>
                  Score {top3Opportunities[0].opportunity_score}/100
                </span>
              </div>
              <div className="kpi-sub">
                <span className="pos-pill up">{top3Opportunities[0].setup_type}</span>
                <span>VWAP: {top3Opportunities[0].vwap_diff_pct}%</span>
              </div>
            </>
          ) : (
            <div className="kpi-value">Escaneando...</div>
          )}
        </div>

        <div className="card kpi-card">
          <div className="kpi-label">
            <span>PnL Cerrado & Win Rate</span>
            <Award size={16} color="#a855f7" />
          </div>
          <div className="kpi-value mono" style={{ color: portfolio.realized_pnl_mxn >= 0 ? '#10b981' : '#f43f5e' }}>
            {portfolio.realized_pnl_mxn >= 0 ? '+' : ''}
            {fmtMXN(portfolio.realized_pnl_mxn)}
          </div>
          <div className="kpi-sub">
            <span>Win Rate: {portfolio.win_rate_pct}%</span>
            <span>•</span>
            <span>Trades: {portfolio.total_trades}</span>
            <span>•</span>
            <span>PnL Abierto: {fmtMXN(portfolio.unrealized_pnl_mxn)}</span>
          </div>
        </div>
      </section>

      {/* =====================================================================
          RADAR CUANTITATIVO DE OPORTUNIDADES MULTI-ACTIVO (24 MONEDAS Y ACTIVOS)
         ===================================================================== */}
      <section className="card" style={{ borderColor: 'rgba(56,189,248,0.4)' }}>
        <div className="card-header">
          <div>
            <div className="card-title" style={{ fontSize: '1.04rem' }}>
              <Compass size={20} color="#38bdf8" />
              <span>Radar Cuantitativo de Oportunidades Multi-Activo en Bitso (24 Monedas, Oro, RWA y Divisas)</span>
            </div>
            <div style={{ fontSize: '0.78rem', color: '#94a3b8', marginTop: 2 }}>
              Clasificación en vivo por Descuento vs. VWAP Institucional, Posición en Canal 24h (Soporte/Rebote), RSI(14) y Liquidez Bid-Ask
            </div>
          </div>

          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <button
              className="btn btn-buy"
              onClick={() =>
                top3Opportunities[0] && handleStepBot(null, top3Opportunities[0].book)
              }
              disabled={busy || !top3Opportunities[0]}
            >
              <Zap size={15} />
              Operar #1 Oportunidad con Bot ({top3Opportunities[0]?.symbol})
            </button>
          </div>
        </div>

        {/* DESTACADOS TOP 3 OPORTUNIDADES */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
            gap: 12,
            marginBottom: 14,
          }}
        >
          {top3Opportunities.map((opp, idx) => (
            <div
              key={opp.book}
              style={{
                background: 'linear-gradient(180deg, rgba(16,185,129,0.09) 0%, rgba(15,23,42,0.9) 100%)',
                border: '1px solid rgba(16,185,129,0.35)',
                borderRadius: 12,
                padding: 13,
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
                gap: 8,
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span
                    className="mono"
                    style={{
                      background: '#10b981',
                      color: '#042219',
                      fontWeight: 800,
                      padding: '2px 7px',
                      borderRadius: 6,
                      fontSize: '0.74rem',
                    }}
                  >
                    TOP #{idx + 1}
                  </span>
                  <strong style={{ fontSize: '0.96rem' }}>
                    {opp.name} ({opp.symbol})
                  </strong>
                  <span
                    style={{
                      fontSize: '0.7rem',
                      padding: '2px 7px',
                      borderRadius: 999,
                      background: 'rgba(56,189,248,0.14)',
                      color: '#38bdf8',
                    }}
                  >
                    {opp.category}
                  </span>
                </div>
                <span className="mono" style={{ fontWeight: 800, color: '#10b981', fontSize: '0.95rem' }}>
                  Score {opp.opportunity_score}/100
                </span>
              </div>

              <div className="mono" style={{ fontSize: '0.82rem', display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                <span>
                  Precio: <strong>{fmtMXN(opp.last)}</strong>
                </span>
                <span style={{ color: opp.vwap_diff_pct <= 0 ? '#10b981' : '#f59e0b' }}>
                  vs VWAP: <strong>{opp.vwap_diff_pct > 0 ? `+${opp.vwap_diff_pct}` : opp.vwap_diff_pct}%</strong>
                </span>
                <span>
                  Rango 24h: <strong>{opp.range_pos_pct}%</strong>
                </span>
                <span>
                  RSI: <strong>{opp.rsi_14}</strong>
                </span>
              </div>

              <div style={{ fontSize: '0.77rem', color: '#cbd5e1' }}>
                <strong style={{ color: '#38bdf8' }}>{opp.setup_type}:</strong> {opp.rationale}
              </div>

              <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
                <button
                  className="btn btn-secondary"
                  style={{ flex: 1, padding: '6px 10px', fontSize: '0.78rem' }}
                  onClick={() => handleSwitchBook(opp.book)}
                >
                  Analizar Gráfico
                </button>
                <button
                  className="btn btn-buy"
                  style={{ flex: 1, padding: '6px 10px', fontSize: '0.78rem' }}
                  disabled={busy}
                  onClick={() =>
                    handleQuickOrder(
                      opp.book,
                      'BUY',
                      10000,
                      null,
                      `[Compra Radar Top #${idx + 1}] ${opp.setup_type} (Score ${opp.opportunity_score})`
                    )
                  }
                >
                  Comprar $10,000 MXN
                </button>
              </div>
            </div>
          ))}
        </div>

        {/* PESTAÑAS DE FILTRO POR CATEGORÍA DE ACTIVO */}
        <div className="book-tabs" style={{ marginBottom: 12 }}>
          {[
            { id: 'TOP_BUY', label: '🔥 Top Oportunidades' },
            { id: 'ALL', label: `🌐 Todos (${opportunities.length})` },
            { id: 'Cripto MXN', label: '🇲🇽 Cripto MXN' },
            { id: 'Oro & RWA', label: '🪙 Oro Físico & RWA' },
            { id: 'Divisas & FX', label: '💱 Divisas & Stablecoins' },
            { id: 'Layer-1 & DeFi', label: '⚡ Layer-1 & DeFi' },
            { id: 'Alta Volatilidad', label: '🚀 Memes & Volatilidad' },
            { id: 'ARBITRAGE', label: '⚖️ Arbitraje MXN vs USD' },
            { id: 'POSITIONS', label: `💼 Mis Posiciones (${openPositionsList.length})` },
          ].map((tab) => (
            <button
              key={tab.id}
              className={`book-tab ${scannerFilter === tab.id ? 'active' : ''}`}
              onClick={() => setScannerFilter(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* TABLA DE ARBITRAJE TRIANGULAR O TABLA DE ESCÁNER MULTI-ACTIVO */}
        {scannerFilter === 'ARBITRAGE' ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Activo</th>
                  <th>Precio Directo en MXN</th>
                  <th>Precio en USD (Bitso)</th>
                  <th>Tipo de Cambio Spot</th>
                  <th>Precio Implícito (USD × MXN)</th>
                  <th>Spread Arbitraje</th>
                  <th>Diagnóstico de Paridad / Oportunidad</th>
                  <th>Acción</th>
                </tr>
              </thead>
              <tbody className="mono">
                {arbitrage.map((a) => (
                  <tr key={a.symbol}>
                    <td>
                      <strong>{a.name}</strong> ({a.symbol})
                    </td>
                    <td>{fmtMXN(a.direct_mxn_price)}</td>
                    <td>${a.usd_price.toLocaleString('en-US')} USD</td>
                    <td>{fmtMXN(a.usd_mxn_spot, 4)}</td>
                    <td>{fmtMXN(a.implied_mxn_price)}</td>
                    <td
                      style={{
                        fontWeight: 700,
                        color: a.abs_spread_bps >= 10 ? '#10b981' : '#38bdf8',
                      }}
                    >
                      {a.spread_bps > 0 ? `+${a.spread_bps}` : a.spread_bps} bps
                    </td>
                    <td style={{ fontFamily: 'Inter, sans-serif', color: '#e2e8f0' }}>{a.direction}</td>
                    <td>
                      <button
                        className="btn btn-secondary"
                        style={{ padding: '5px 10px', fontSize: '0.75rem' }}
                        onClick={() => handleSwitchBook(a.recommended_book)}
                      >
                        Abrir {a.symbol}/MXN
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="table-wrap" style={{ maxHeight: 330 }}>
            <table>
              <thead>
                <tr>
                  <th>Activo</th>
                  <th>Categoría</th>
                  <th>Precio Actual (MXN)</th>
                  <th>Cambio 24h</th>
                  <th>vs VWAP</th>
                  <th>Posición Rango 24h</th>
                  <th>RSI(14)</th>
                  <th>Score IA</th>
                  <th>Señal & Setup Detectado</th>
                  <th>Acción Rápida</th>
                </tr>
              </thead>
              <tbody className="mono">
                {filteredOpportunities.map((opp) => {
                  const isStrong = opp.signal === 'STRONG_BUY'
                  const isBuy = opp.signal === 'BUY' || isStrong
                  const isSell = opp.signal === 'SELL'
                  return (
                    <tr
                      key={opp.book}
                      style={{
                        background: opp.book === activeBook ? 'rgba(56,189,248,0.07)' : 'transparent',
                      }}
                    >
                      <td>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                          <strong style={{ color: '#fff' }}>{opp.symbol}</strong>
                          <span style={{ fontSize: '0.73rem', color: '#94a3b8', fontFamily: 'Inter, sans-serif' }}>
                            {opp.name}
                          </span>
                          {opp.has_position && (
                            <span
                              style={{
                                fontSize: '0.66rem',
                                padding: '1px 5px',
                                borderRadius: 4,
                                background: 'rgba(168,85,247,0.25)',
                                color: '#e9d5ff',
                              }}
                            >
                              EN CARTERA
                            </span>
                          )}
                        </div>
                      </td>
                      <td style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.75rem', color: '#94a3b8' }}>
                        {opp.category}
                      </td>
                      <td style={{ fontWeight: 700 }}>{fmtMXN(opp.last)}</td>
                      <td style={{ color: opp.change_24_pct >= 0 ? '#10b981' : '#f43f5e', fontWeight: 600 }}>
                        {opp.change_24_pct >= 0 ? `+${opp.change_24_pct}%` : `${opp.change_24_pct}%`}
                      </td>
                      <td style={{ color: opp.vwap_diff_pct <= 0 ? '#10b981' : '#cbd5e1' }}>
                        {opp.vwap_diff_pct > 0 ? `+${opp.vwap_diff_pct}%` : `${opp.vwap_diff_pct}%`}
                      </td>
                      <td>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                          <div
                            style={{
                              width: 54,
                              height: 6,
                              background: '#1e293b',
                              borderRadius: 99,
                              overflow: 'hidden',
                            }}
                          >
                            <div
                              style={{
                                width: `${opp.range_pos_pct}%`,
                                height: '100%',
                                background: opp.range_pos_pct < 35 ? '#10b981' : opp.range_pos_pct > 80 ? '#f59e0b' : '#38bdf8',
                              }}
                            />
                          </div>
                          <span style={{ fontSize: '0.73rem' }}>{opp.range_pos_pct}%</span>
                        </div>
                      </td>
                      <td
                        style={{
                          color: opp.rsi_14 < 38 ? '#10b981' : opp.rsi_14 > 68 ? '#f43f5e' : '#cbd5e1',
                          fontWeight: 600,
                        }}
                      >
                        {opp.rsi_14}
                      </td>
                      <td>
                        <span
                          style={{
                            padding: '3px 8px',
                            borderRadius: 6,
                            fontWeight: 800,
                            background: isBuy
                              ? 'rgba(16,185,129,0.18)'
                              : isSell
                              ? 'rgba(244,63,94,0.18)'
                              : 'rgba(148,163,184,0.12)',
                            color: isBuy ? '#10b981' : isSell ? '#f43f5e' : '#cbd5e1',
                          }}
                        >
                          {opp.opportunity_score}
                        </span>
                      </td>
                      <td style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.76rem' }}>
                        <div style={{ fontWeight: 700, color: isBuy ? '#10b981' : isSell ? '#f43f5e' : '#94a3b8' }}>
                          {opp.signal_label} — {opp.setup_type}
                        </div>
                        <div style={{ color: '#94a3b8', fontSize: '0.72rem' }}>{opp.rationale}</div>
                      </td>
                      <td>
                        <div style={{ display: 'flex', gap: 6 }}>
                          <button
                            className="btn btn-secondary"
                            style={{ padding: '4px 8px', fontSize: '0.73rem' }}
                            onClick={() => handleSwitchBook(opp.book)}
                          >
                            Gráfico
                          </button>
                          <button
                            className="btn btn-buy"
                            style={{ padding: '4px 8px', fontSize: '0.73rem' }}
                            disabled={busy}
                            onClick={() =>
                              handleQuickOrder(
                                opp.book,
                                'BUY',
                                10000,
                                null,
                                `[Radar Multi-Activo] ${opp.setup_type} (Score ${opp.opportunity_score})`
                              )
                            }
                          >
                            +$10k
                          </button>
                          {opp.has_position && (
                            <button
                              className="btn btn-sell"
                              style={{ padding: '4px 8px', fontSize: '0.73rem' }}
                              disabled={busy}
                              onClick={() =>
                                handleQuickOrder(
                                  opp.book,
                                  'SELL',
                                  null,
                                  opp.held_amount,
                                  `[Cierre desde Radar] Liquidación total de ${opp.symbol}`
                                )
                              }
                            >
                              Vender
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* WORKSPACE DETALLADO DEL ACTIVO SELECCIONADO + BOT IA */}
      <div className="workspace-grid">
        <div className="left-col">
          {/* GRÁFICO EN TIEMPO REAL */}
          <div className="card">
            <div className="card-header">
              <div>
                <div className="card-title">
                  <BarChart2 size={18} color="#38bdf8" />
                  <span>
                    {bookMeta.name} ({bookMeta.pair}) — Categoría: {bookMeta.category}
                  </span>
                  <span className="mono" style={{ color: '#38bdf8', marginLeft: 6 }}>
                    {fmtMXN(ticker.last)}
                  </span>
                </div>
                <div className="mono" style={{ fontSize: '0.75rem', color: '#94a3b8', marginTop: 3 }}>
                  Bid: <strong style={{ color: '#10b981' }}>{fmtMXN(ticker.bid)}</strong> | Ask:{' '}
                  <strong style={{ color: '#f43f5e' }}>{fmtMXN(ticker.ask)}</strong> | VWAP:{' '}
                  <strong>{fmtMXN(ticker.vwap)}</strong> | Spread: <strong>{ticker.spread_bps || 0} bps</strong>
                </div>
              </div>

              <div style={{ display: 'flex', gap: 6 }}>
                <button
                  className={`btn ${chartMode === 'price' ? 'btn-purple' : 'btn-secondary'}`}
                  onClick={() => setChartMode('price')}
                >
                  Precio + Medias SMA
                </button>
                <button
                  className={`btn ${chartMode === 'equity' ? 'btn-purple' : 'btn-secondary'}`}
                  onClick={() => setChartMode('equity')}
                >
                  Curva de Capital vs Hold
                </button>
              </div>
            </div>

            <InteractiveChart
              data={chartMode === 'price' ? state.price_history : portfolio.equity_curve}
              mode={chartMode}
              activeMeta={bookMeta}
            />
          </div>

          {/* ORDER BOOK EN VIVO */}
          <div className="card">
            <div className="card-header">
              <div className="card-title">
                <BookOpen size={17} color="#10b981" />
                <span>Libro de Órdenes Real de Bitso ({bookMeta.pair}) & Presión de Liquidez</span>
              </div>
              <div className="mono" style={{ fontSize: '0.78rem' }}>
                Bids: <strong style={{ color: '#10b981' }}>{((orderBook.imbalance || 0.5) * 100).toFixed(1)}%</strong>{' '}
                | Asks:{' '}
                <strong style={{ color: '#f43f5e' }}>{((1 - (orderBook.imbalance || 0.5)) * 100).toFixed(1)}%</strong>
              </div>
            </div>

            <div
              style={{
                height: 8,
                borderRadius: 999,
                background: '#f43f5e',
                overflow: 'hidden',
                marginBottom: 14,
              }}
            >
              <div
                style={{
                  width: `${((orderBook.imbalance || 0.5) * 100).toFixed(1)}%`,
                  height: '100%',
                  background: '#10b981',
                  transition: 'width 0.35s ease',
                }}
              />
            </div>

            <div className="ob-grid mono">
              <div>
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    fontSize: '0.72rem',
                    color: '#94a3b8',
                    marginBottom: 6,
                  }}
                >
                  <span>CANTIDAD ({bookMeta.symbol})</span>
                  <span>PRECIO COMPRA (BID MXN)</span>
                </div>
                {(orderBook.bids || []).slice(0, 6).map((b, idx) => (
                  <div key={idx} className="ob-row">
                    <div
                      className="ob-bar-bid"
                      style={{ width: `${Math.min(100, (b.amount / maxObVol) * 100)}%` }}
                    />
                    <span style={{ color: '#cbd5e1' }}>{fmtNum(b.amount, 4)}</span>
                    <span style={{ color: '#10b981', fontWeight: 600 }}>{fmtMXN(b.price)}</span>
                  </div>
                ))}
              </div>

              <div>
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    fontSize: '0.72rem',
                    color: '#94a3b8',
                    marginBottom: 6,
                  }}
                >
                  <span>PRECIO VENTA (ASK MXN)</span>
                  <span>CANTIDAD ({bookMeta.symbol})</span>
                </div>
                {(orderBook.asks || []).slice(0, 6).map((a, idx) => (
                  <div key={idx} className="ob-row">
                    <div
                      className="ob-bar-ask"
                      style={{ width: `${Math.min(100, (a.amount / maxObVol) * 100)}%` }}
                    />
                    <span style={{ color: '#f43f5e', fontWeight: 600 }}>{fmtMXN(a.price)}</span>
                    <span style={{ color: '#cbd5e1' }}>{fmtNum(a.amount, 4)}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* HISTORIAL DE OPERACIONES */}
          <div className="card">
            <div className="card-header">
              <div className="card-title">
                <Activity size={17} color="#38bdf8" />
                <span>Bitácora de Operaciones Ejecutadas (Multi-Activo + Bot IA)</span>
              </div>
              <span style={{ fontSize: '0.78rem', color: '#94a3b8' }}>
                {portfolio.recent_trades?.length || 0} ejecuciones registradas
              </span>
            </div>

            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Hora</th>
                    <th>Origen</th>
                    <th>Activo</th>
                    <th>Lado</th>
                    <th>Precio (MXN)</th>
                    <th>Cantidad</th>
                    <th>Total MXN</th>
                    <th>PnL Neto</th>
                    <th>Motivo / Señal</th>
                  </tr>
                </thead>
                <tbody className="mono">
                  {(!portfolio.recent_trades || portfolio.recent_trades.length === 0) ? (
                    <tr>
                      <td colSpan={9} style={{ textAlign: 'center', padding: 24, color: '#64748b' }}>
                        Sin operaciones aún. Haz clic en "+$10k" en cualquier activo del Radar o activa el Bot.
                      </td>
                    </tr>
                  ) : (
                    portfolio.recent_trades.map((t) => {
                      const timeStr = new Date(t.timestamp).toLocaleTimeString('es-MX')
                      const isBuy = t.side === 'BUY'
                      const isBot = t.source && t.source.startsWith('BOT')
                      const sym = catalog[t.book]?.symbol || t.book?.toUpperCase()
                      return (
                        <tr key={t.id}>
                          <td style={{ color: '#94a3b8' }}>{timeStr}</td>
                          <td>
                            <span
                              style={{
                                padding: '2px 7px',
                                borderRadius: 6,
                                fontSize: '0.7rem',
                                background: isBot ? 'rgba(168,85,247,0.18)' : 'rgba(56,189,248,0.15)',
                                color: isBot ? '#d8b4fe' : '#7dd3fc',
                                fontWeight: 600,
                              }}
                            >
                              {t.source}
                            </span>
                          </td>
                          <td>
                            <strong>{sym}</strong>
                          </td>
                          <td>
                            <span
                              style={{
                                color: isBuy ? '#10b981' : '#f43f5e',
                                fontWeight: 700,
                                display: 'inline-flex',
                                alignItems: 'center',
                                gap: 3,
                              }}
                            >
                              {isBuy ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}
                              {t.side}
                            </span>
                          </td>
                          <td>{fmtMXN(t.price)}</td>
                          <td>{t.amount}</td>
                          <td>{fmtMXN(t.total_mxn)}</td>
                          <td
                            style={{
                              fontWeight: 700,
                              color:
                                t.pnl_mxn === null
                                  ? '#64748b'
                                  : t.pnl_mxn >= 0
                                  ? '#10b981'
                                  : '#f43f5e',
                            }}
                          >
                            {t.pnl_mxn === null
                              ? '—'
                              : `${t.pnl_mxn >= 0 ? '+' : ''}${fmtMXN(t.pnl_mxn)} (${t.pnl_pct >= 0 ? '+' : ''}${t.pnl_pct}%)`}
                          </td>
                          <td style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.75rem', color: '#cbd5e1' }}>
                            {t.reason}
                          </td>
                        </tr>
                      )
                    })
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        {/* COLUMNA DERECHA: BOT CAZADOR MULTI-ACTIVO + CARTERA ABIERTA + ORDEN MANUAL */}
        <div className="right-col">
          {/* PANEL DEL BOT DE TRADING / IA */}
          <div
            className="card"
            style={{
              borderColor: bot.enabled ? '#10b981' : 'var(--border-color)',
              boxShadow: bot.enabled ? '0 0 25px rgba(16,185,129,0.12)' : 'none',
            }}
          >
            <div className="card-header">
              <div className="card-title">
                <Bot size={20} color={bot.enabled ? '#10b981' : '#a855f7'} />
                <span>Bot Cazador Multi-Activo & IA</span>
                <span
                  style={{
                    fontSize: '0.72rem',
                    padding: '2px 8px',
                    borderRadius: 999,
                    background: bot.enabled ? 'rgba(16,185,129,0.2)' : 'rgba(148,163,184,0.15)',
                    color: bot.enabled ? '#10b981' : '#94a3b8',
                  }}
                >
                  {bot.enabled ? 'ESCANEANDO Y OPERANDO' : 'EN PAUSA'}
                </span>
              </div>

              <button
                className={`btn ${bot.enabled ? 'btn-sell' : 'btn-buy'}`}
                onClick={() => handleUpdateBot({ enabled: !bot.enabled, book: activeBook })}
              >
                {bot.enabled ? (
                  <>
                    <Pause size={15} /> Pausar Bot
                  </>
                ) : (
                  <>
                    <Play size={15} /> Activar Bot
                  </>
                )}
              </button>
            </div>

            {/* Switch de Rotación Multi-Activo */}
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '9px 12px',
                background: 'rgba(56,189,248,0.09)',
                border: '1px solid rgba(56,189,248,0.25)',
                borderRadius: 9,
                marginBottom: 12,
                fontSize: '0.8rem',
              }}
            >
              <div>
                <strong style={{ color: '#38bdf8' }}>Modo Cazador Multi-Activo (24 Monedas)</strong>
                <div style={{ fontSize: '0.73rem', color: '#94a3b8' }}>
                  Compra automáticamente las mejores oportunidades del Radar y cierra por Take Profit / Stop Loss
                </div>
              </div>
              <input
                type="checkbox"
                checked={bot.multi_asset_auto ?? true}
                onChange={(e) => handleUpdateBot({ multi_asset_auto: e.target.checked })}
                style={{ width: 18, height: 18, accentColor: '#10b981', cursor: 'pointer' }}
              />
            </div>

            {/* Última Señal */}
            <div
              style={{
                background: '#0b111e',
                border: '1px solid rgba(255,255,255,0.08)',
                borderRadius: 10,
                padding: 12,
                marginBottom: 14,
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                <span style={{ fontSize: '0.75rem', color: '#94a3b8', fontWeight: 600 }}>
                  ÚLTIMA DECISIÓN DEL BOT
                </span>
                <span
                  className="mono"
                  style={{
                    padding: '2px 9px',
                    borderRadius: 6,
                    fontWeight: 700,
                    fontSize: '0.78rem',
                    background:
                      lastSignal.action === 'BUY'
                        ? 'rgba(16,185,129,0.2)'
                        : lastSignal.action === 'SELL'
                        ? 'rgba(244,63,94,0.2)'
                        : 'rgba(148,163,184,0.15)',
                    color:
                      lastSignal.action === 'BUY'
                        ? '#10b981'
                        : lastSignal.action === 'SELL'
                        ? '#f43f5e'
                        : '#cbd5e1',
                  }}
                >
                  {lastSignal.action || 'HOLD'} ({Math.round((lastSignal.confidence || 0.5) * 100)}% conf.)
                </span>
              </div>
              <div style={{ fontSize: '0.81rem', color: '#e2e8f0' }}>{lastSignal.reason}</div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div className="input-group">
                <label className="input-label">Algoritmo Base</label>
                <select
                  className="select-field"
                  value={bot.strategy || 'sma_rsi'}
                  onChange={(e) => handleUpdateBot({ strategy: e.target.value })}
                >
                  <option value="ai_custom">🧠 IA Multifactorial (predict_with_ai)</option>
                  <option value="sma_rsi">📈 Cruce de Medias (SMA 5/18) + RSI (14)</option>
                  <option value="orderbook_imbalance">⚡ Microestructura: Order Book Imbalance</option>
                </select>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10 }}>
                <div className="input-group">
                  <label className="input-label">% Cash / Orden</label>
                  <input
                    type="number"
                    className="input-field mono"
                    min="2"
                    max="100"
                    step="1"
                    value={bot.trade_size_pct ?? 15}
                    onChange={(e) => handleUpdateBot({ trade_size_pct: parseFloat(e.target.value) || 15 })}
                  />
                </div>
                <div className="input-group">
                  <label className="input-label">Take Profit (%)</label>
                  <input
                    type="number"
                    className="input-field mono"
                    min="0.05"
                    max="25"
                    step="0.05"
                    value={bot.take_profit_pct ?? 0.45}
                    onChange={(e) => handleUpdateBot({ take_profit_pct: parseFloat(e.target.value) || 0.45 })}
                  />
                </div>
                <div className="input-group">
                  <label className="input-label">Stop Loss (%)</label>
                  <input
                    type="number"
                    className="input-field mono"
                    min="0.05"
                    max="25"
                    step="0.05"
                    value={bot.stop_loss_pct ?? 0.3}
                    onChange={(e) => handleUpdateBot({ stop_loss_pct: parseFloat(e.target.value) || 0.3 })}
                  />
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginTop: 4 }}>
                <button
                  className="btn btn-buy"
                  onClick={() => handleStepBot(null, null)}
                  disabled={busy}
                >
                  <Zap size={14} /> Cazar Mejor Oportunidad Ahora
                </button>
                <button
                  className="btn btn-secondary"
                  onClick={() => handleStepBot('BUY', activeBook)}
                  disabled={busy}
                >
                  <ArrowUpRight size={14} color="#10b981" /> Test Compra ({bookMeta.symbol})
                </button>
              </div>
            </div>
          </div>

          {/* RESUMEN DE POSICIONES ABIERTAS EN CARTERA */}
          <div className="card">
            <div className="card-header">
              <div className="card-title">
                <Layers size={18} color="#a855f7" />
                <span>Posiciones Abiertas en Cartera ({openPositionsList.length})</span>
              </div>
            </div>

            {openPositionsList.length === 0 ? (
              <div style={{ fontSize: '0.82rem', color: '#64748b', textAlign: 'center', padding: '14px 0' }}>
                No tienes posiciones abiertas actualmente. Todo tu capital está en MXN líquido.
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {openPositionsList.map((pos) => {
                  const meta = catalog[pos.book] || { symbol: pos.book.toUpperCase(), name: pos.book }
                  return (
                    <div
                      key={pos.book}
                      className="mono"
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        padding: '9px 11px',
                        background: '#0b111e',
                        borderRadius: 9,
                        border: '1px solid rgba(255,255,255,0.06)',
                        fontSize: '0.78rem',
                      }}
                    >
                      <div>
                        <strong style={{ color: '#fff', fontSize: '0.86rem' }}>{meta.symbol}</strong>{' '}
                        <span style={{ color: '#94a3b8' }}>({fmtNum(pos.amount, 5)})</span>
                        <div style={{ fontSize: '0.72rem', color: '#94a3b8' }}>
                          Valuación: {fmtMXN(pos.market_value_mxn)}
                        </div>
                      </div>
                      <div style={{ textAlign: 'right' }}>
                        <div
                          style={{
                            color: pos.unrealized_pnl_mxn >= 0 ? '#10b981' : '#f43f5e',
                            fontWeight: 700,
                          }}
                        >
                          {pos.unrealized_pnl_mxn >= 0 ? '+' : ''}
                          {fmtMXN(pos.unrealized_pnl_mxn)} ({pos.unrealized_pnl_pct >= 0 ? '+' : ''}
                          {pos.unrealized_pnl_pct}%)
                        </div>
                        <div style={{ display: 'flex', gap: 5, justifyContent: 'flex-end', marginTop: 4 }}>
                          <button
                            className="btn btn-secondary"
                            style={{ padding: '3px 7px', fontSize: '0.7rem' }}
                            onClick={() => handleSwitchBook(pos.book)}
                          >
                            Ver
                          </button>
                          <button
                            className="btn btn-sell"
                            style={{ padding: '3px 7px', fontSize: '0.7rem' }}
                            disabled={busy}
                            onClick={() =>
                              handleQuickOrder(
                                pos.book,
                                'SELL',
                                null,
                                pos.amount,
                                `Liquidación manual de posición en ${meta.symbol}`
                              )
                            }
                          >
                            Cerrar 100%
                          </button>
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>

          {/* TERMINAL DE TRADING MANUAL */}
          <div className="card">
            <div className="card-header">
              <div className="card-title">
                <Wallet size={18} color="#10b981" />
                <span>Orden Manual: {bookMeta.name} ({bookMeta.symbol})</span>
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 14 }}>
              <button
                type="button"
                className={`btn ${orderSide === 'BUY' ? 'btn-buy' : 'btn-secondary'}`}
                onClick={() => setOrderSide('BUY')}
              >
                COMPRAR {bookMeta.symbol}
              </button>
              <button
                type="button"
                className={`btn ${orderSide === 'SELL' ? 'btn-sell' : 'btn-secondary'}`}
                onClick={() => setOrderSide('SELL')}
              >
                VENDER {bookMeta.symbol}
              </button>
            </div>

            <form onSubmit={handleManualOrder} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {orderSide === 'BUY' ? (
                <div className="input-group">
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <label className="input-label">Monto a Invertir (MXN Virtual)</label>
                    <span className="mono" style={{ fontSize: '0.74rem', color: '#94a3b8' }}>
                      Disp: {fmtMXN(portfolio.cash_mxn)}
                    </span>
                  </div>
                  <input
                    type="number"
                    step="any"
                    min="10"
                    className="input-field mono"
                    value={orderAmountMxn}
                    onChange={(e) => setOrderAmountMxn(e.target.value)}
                    required
                  />
                  <div className="quick-pct-row">
                    {[25, 50, 75, 100].map((pct) => (
                      <button key={pct} type="button" className="pct-btn" onClick={() => applyQuickPct(pct)}>
                        {pct}% Cash
                      </button>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="input-group">
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <label className="input-label">Cantidad a Vender ({bookMeta.symbol})</label>
                    <span className="mono" style={{ fontSize: '0.74rem', color: '#94a3b8' }}>
                      Disp: {fmtNum(activePos.amount, 6)} {bookMeta.symbol}
                    </span>
                  </div>
                  <input
                    type="number"
                    step="any"
                    className="input-field mono"
                    value={orderCryptoQty}
                    onChange={(e) => setOrderCryptoQty(e.target.value)}
                    required
                  />
                  <div className="quick-pct-row">
                    {[25, 50, 75, 100].map((pct) => (
                      <button key={pct} type="button" className="pct-btn" onClick={() => applyQuickPct(pct)}>
                        {pct}% Posición
                      </button>
                    ))}
                  </div>
                </div>
              )}

              <button
                type="submit"
                disabled={busy || (orderSide === 'SELL' && activePos.amount <= 0)}
                className={`btn ${orderSide === 'BUY' ? 'btn-buy' : 'btn-sell'}`}
                style={{ padding: '12px', fontSize: '0.9rem' }}
              >
                {orderSide === 'BUY'
                  ? `Simular Compra de ${bookMeta.symbol} (${fmtMXN(orderAmountMxn)})`
                  : `Simular Venta de ${bookMeta.symbol}`}
              </button>
            </form>
          </div>
        </div>
      </div>
    </div>
  )
}
