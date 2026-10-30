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
  Download,
  PieChart,
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
  const height = 270
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
      <div style={{ height: 270, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#94a3b8' }}>
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
  const [scannerFilter, setScannerFilter] = useState('TOP_BUY')
  const [orderSide, setOrderSide] = useState('BUY')
  const [orderAmountMxn, setOrderAmountMxn] = useState('14000')
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
        reconnectTimer = setTimeout(connectWs, 2500)
      }
      ws.onerror = () => ws.close()
    }
    connectWs()
    const pollInterval = setInterval(fetchState, 3000)
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
        <span style={{ fontWeight: 600 }}>Iniciando Motor de Scalping Multi-Activo conectado a Bitso...</span>
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
  const pnlBalance = portfolio.pnl_balance || {
    total_transactions: 0,
    buy_transactions: 0,
    sell_transactions: 0,
    winning_count: 0,
    losing_count: 0,
    win_rate_pct: 0,
    gross_profit_mxn: 0,
    gross_loss_mxn: 0,
    net_realized_pnl_mxn: 0,
    avg_win_mxn: 0,
    avg_loss_mxn: 0,
    profit_factor: 0,
    by_book: [],
  }
  const activePos = portfolio.positions?.[activeBook] || {
    amount: 0,
    avg_buy_price: 0,
    market_value_mxn: 0,
    unrealized_pnl_mxn: 0,
    unrealized_pnl_pct: 0,
    auto_tp_pct: 0.35,
    auto_sl_pct: 0.65,
  }
  const bot = state.bot || {}
  const lastSignal = bot.last_signal || {}
  const orderBook = state.order_book || { bids: [], asks: [], imbalance: 0.5 }
  const opportunities = state.opportunities || []
  const arbitrage = state.arbitrage || []

  const openPositionsList = Object.values(portfolio.positions || {}).filter((p) => p.amount > 1e-8)

  const filteredOpportunities = opportunities.filter((opp) => {
    if (scannerFilter === 'TOP_BUY') return opp.opportunity_score >= 56
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
        body: JSON.stringify({ initial_cash_mxn: 100000, fee_rate: 0.0003, clear_history: true }),
      })
      if (res.ok) {
        const data = await res.json()
        setState(data)
        showToast('info', 'Portafolio y balance reiniciados a $100,000.00 MXN')
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

  const totalGrossAbs = Math.max(
    0.01,
    pnlBalance.gross_profit_mxn + Math.abs(pnlBalance.gross_loss_mxn)
  )
  const profitSharePct = Math.round((pnlBalance.gross_profit_mxn / totalGrossAbs) * 100)

  return (
    <div className="app-shell">
      {/* TOP BAR */}
      <header className="topbar">
        <div className="brand">
          <div className="brand-logo mono">B⚡</div>
          <div>
            <div className="brand-title">
              Bitso High-Frequency Scalper & Auto TP/SL por Moneda
              <span className="badge-live">
                <span className="pulse-dot" />
                SCALPING 24/7 • 24 ACTIVOS • FX USD/MXN: ${state.usd_mxn_rate}
              </span>
            </div>
            <div style={{ fontSize: '0.77rem', color: '#94a3b8' }}>
              Take Profit y Stop Loss calculados dinámicamente por moneda según volatilidad de últimos ticks y spread real
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <select
            className="select-field mono"
            style={{ width: 255, fontWeight: 700, borderColor: '#38bdf8' }}
            value={activeBook}
            onChange={(e) => handleSwitchBook(e.target.value)}
          >
            {opportunities.map((opp) => (
              <option key={opp.book} value={opp.book}>
                {opp.symbol} — TP +{opp.auto_tp_pct}% / SL -{opp.auto_sl_pct}% (Score {opp.opportunity_score})
              </option>
            ))}
          </select>

          <a
            href={`${API_BASE}/api/trades/export`}
            target="_blank"
            rel="noreferrer"
            className="btn btn-secondary"
            style={{ textDecoration: 'none' }}
          >
            <Download size={14} color="#10b981" />
            Exportar Historial CSV
          </a>

          <button className="btn btn-secondary" onClick={handleResetPortfolio} disabled={busy}>
            <RefreshCw size={14} />
            Reiniciar $100k
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
            <span>Efectivo: {fmtMXN(portfolio.cash_mxn, 0)}</span>
          </div>
        </div>

        <div className="card kpi-card">
          <div className="kpi-label">
            <span>Ganancias Brutas Acumuladas</span>
            <TrendingUp size={16} color="#10b981" />
          </div>
          <div className="kpi-value mono" style={{ color: '#10b981' }}>
            +{fmtMXN(pnlBalance.gross_profit_mxn)}
          </div>
          <div className="kpi-sub">
            <span className="pos-pill up">{pnlBalance.winning_count} ventas ganadoras</span>
            <span>Prom: +{fmtMXN(pnlBalance.avg_win_mxn)}</span>
          </div>
        </div>

        <div className="card kpi-card">
          <div className="kpi-label">
            <span>Pérdidas Brutas Acumuladas</span>
            <TrendingDown size={16} color="#f43f5e" />
          </div>
          <div className="kpi-value mono" style={{ color: '#f43f5e' }}>
            {fmtMXN(pnlBalance.gross_loss_mxn)}
          </div>
          <div className="kpi-sub">
            <span className="pos-pill down">{pnlBalance.losing_count} ventas con pérdida</span>
            <span>Prom: {fmtMXN(pnlBalance.avg_loss_mxn)}</span>
          </div>
        </div>

        <div className="card kpi-card">
          <div className="kpi-label">
            <span>Balance Neto (Ganancias vs Pérdidas)</span>
            <Award size={16} color="#f59e0b" />
          </div>
          <div
            className="kpi-value mono"
            style={{ color: pnlBalance.net_realized_pnl_mxn >= 0 ? '#10b981' : '#f43f5e' }}
          >
            {pnlBalance.net_realized_pnl_mxn >= 0 ? '+' : ''}
            {fmtMXN(pnlBalance.net_realized_pnl_mxn)}
          </div>
          <div className="kpi-sub">
            <span>Win Rate: {pnlBalance.win_rate_pct}%</span>
            <span>•</span>
            <span>Profit Factor: {pnlBalance.profit_factor}x</span>
            <span>•</span>
            <span>Trades: {pnlBalance.total_transactions}</span>
          </div>
        </div>
      </section>

      {/* =====================================================================
          PANEL DE BALANCE CONTABLE: GANANCIAS VS PÉRDIDAS POR MONEDA
         ===================================================================== */}
      <section className="card" style={{ borderColor: 'rgba(16,185,129,0.35)' }}>
        <div className="card-header">
          <div>
            <div className="card-title">
              <PieChart size={19} color="#10b981" />
              <span>Balance Contable de Ganancias vs. Pérdidas y Desglose por Moneda (Historial Persistente)</span>
            </div>
            <div style={{ fontSize: '0.77rem', color: '#94a3b8', marginTop: 2 }}>
              Comparativa en tiempo real de todas las transacciones cerradas ({pnlBalance.sell_transactions} cierres de{' '}
              {pnlBalance.total_transactions} operaciones totales guardadas en base de datos)
            </div>
          </div>

          <div className="mono" style={{ display: 'flex', gap: 16, fontSize: '0.82rem' }}>
            <span style={{ color: '#10b981', fontWeight: 700 }}>
              ▲ Ganancias: +{fmtMXN(pnlBalance.gross_profit_mxn)} ({pnlBalance.winning_count})
            </span>
            <span style={{ color: '#f43f5e', fontWeight: 700 }}>
              ▼ Pérdidas: {fmtMXN(pnlBalance.gross_loss_mxn)} ({pnlBalance.losing_count})
            </span>
            <span
              style={{
                color: pnlBalance.net_realized_pnl_mxn >= 0 ? '#10b981' : '#f43f5e',
                fontWeight: 800,
              }}
            >
              = Neto Cerrado: {pnlBalance.net_realized_pnl_mxn >= 0 ? '+' : ''}
              {fmtMXN(pnlBalance.net_realized_pnl_mxn)}
            </span>
          </div>
        </div>

        {/* Barra de proporción Ganancias vs Pérdidas */}
        <div
          style={{
            height: 10,
            borderRadius: 999,
            background: '#f43f5e',
            overflow: 'hidden',
            marginBottom: 14,
          }}
        >
          <div
            style={{
              width: `${pnlBalance.sell_transactions > 0 ? profitSharePct : 50}%`,
              height: '100%',
              background: '#10b981',
              transition: 'width 0.35s ease',
            }}
          />
        </div>

        {pnlBalance.by_book && pnlBalance.by_book.length > 0 && (
          <div className="table-wrap" style={{ maxHeight: 205 }}>
            <table>
              <thead>
                <tr>
                  <th>Moneda / Activo</th>
                  <th>Total Transacciones</th>
                  <th>Compras / Ventas</th>
                  <th>Ganadoras vs Perdedoras</th>
                  <th>Win Rate</th>
                  <th>Ganancia Bruta (+)</th>
                  <th>Pérdida Bruta (-)</th>
                  <th>Balance Neto Cerrado</th>
                  <th>Volumen Operado (MXN)</th>
                </tr>
              </thead>
              <tbody className="mono">
                {pnlBalance.by_book.map((row) => {
                  const meta = catalog[row.book] || { symbol: row.book.toUpperCase(), name: row.book }
                  return (
                    <tr key={row.book}>
                      <td>
                        <strong style={{ color: '#fff' }}>{meta.symbol}</strong>{' '}
                        <span style={{ fontSize: '0.73rem', color: '#94a3b8', fontFamily: 'Inter, sans-serif' }}>
                          {meta.name}
                        </span>
                      </td>
                      <td>{row.total_trades}</td>
                      <td>
                        {row.buys} C / {row.sells} V
                      </td>
                      <td>
                        <span style={{ color: '#10b981' }}>{row.wins}G</span> /{' '}
                        <span style={{ color: '#f43f5e' }}>{row.losses}P</span>
                      </td>
                      <td>{row.win_rate_pct}%</td>
                      <td style={{ color: '#10b981', fontWeight: 600 }}>+{fmtMXN(row.gross_profit_mxn)}</td>
                      <td style={{ color: '#f43f5e', fontWeight: 600 }}>{fmtMXN(row.gross_loss_mxn)}</td>
                      <td
                        style={{
                          fontWeight: 800,
                          color: row.net_pnl_mxn >= 0 ? '#10b981' : '#f43f5e',
                        }}
                      >
                        {row.net_pnl_mxn >= 0 ? '+' : ''}
                        {fmtMXN(row.net_pnl_mxn)}
                      </td>
                      <td style={{ color: '#94a3b8' }}>{fmtMXN(row.volume_mxn)}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* =====================================================================
          RADAR MULTI-ACTIVO CON TAKE PROFIT Y STOP LOSS AUTOMATIZADOS POR MONEDA
         ===================================================================== */}
      <section className="card" style={{ borderColor: 'rgba(56,189,248,0.4)' }}>
        <div className="card-header">
          <div>
            <div className="card-title" style={{ fontSize: '1.04rem' }}>
              <Compass size={20} color="#38bdf8" />
              <span>Radar de Scalping con Take Profit y Stop Loss Automatizados por Moneda (24 Activos)</span>
            </div>
            <div style={{ fontSize: '0.78rem', color: '#94a3b8', marginTop: 2 }}>
              Cada moneda calcula su propio Auto-TP %, Auto-SL % y Trailing Lock % en base a su volatilidad reciente de ticks y spread en Bitso
            </div>
          </div>

          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <button
              className="btn btn-buy"
              onClick={() => top3Opportunities[0] && handleStepBot(null, top3Opportunities[0].book)}
              disabled={busy || !top3Opportunities[0]}
            >
              <Zap size={15} />
              Scalp Rápido en #1 ({top3Opportunities[0]?.symbol})
            </button>
          </div>
        </div>

        {/* DESTACADOS TOP 3 OPORTUNIDADES CON SU AUTO-TP Y AUTO-SL */}
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
                </div>
                <span className="mono" style={{ fontWeight: 800, color: '#10b981', fontSize: '0.95rem' }}>
                  Score {opp.opportunity_score}/100
                </span>
              </div>

              <div className="mono" style={{ fontSize: '0.8rem', display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                <span>
                  Precio: <strong>{fmtMXN(opp.last)}</strong>
                </span>
                <span style={{ color: '#10b981' }}>
                  Auto-TP: <strong>+{opp.auto_tp_pct}%</strong>
                </span>
                <span style={{ color: '#38bdf8' }}>
                  Trailing: <strong>+{opp.auto_trail_arm_pct}%</strong>
                </span>
                <span style={{ color: '#f43f5e' }}>
                  Auto-SL: <strong>-{opp.auto_sl_pct}%</strong>
                </span>
              </div>

              <div style={{ fontSize: '0.76rem', color: '#cbd5e1' }}>
                <strong style={{ color: '#38bdf8' }}>{opp.setup_type}:</strong> {opp.rationale}
              </div>

              <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
                <button
                  className="btn btn-secondary"
                  style={{ flex: 1, padding: '6px 10px', fontSize: '0.78rem' }}
                  onClick={() => handleSwitchBook(opp.book)}
                >
                  Ver Gráfico
                </button>
                <button
                  className="btn btn-buy"
                  style={{ flex: 1, padding: '6px 10px', fontSize: '0.78rem' }}
                  disabled={busy}
                  onClick={() =>
                    handleQuickOrder(
                      opp.book,
                      'BUY',
                      12000,
                      null,
                      `[Scalp Manual Top #${idx + 1} | Auto-TP +${opp.auto_tp_pct}% / SL -${opp.auto_sl_pct}%] ${opp.setup_type}`
                    )
                  }
                >
                  Scalp $12,000 MXN
                </button>
              </div>
            </div>
          ))}
        </div>

        {/* PESTAÑAS DE FILTRO */}
        <div className="book-tabs" style={{ marginBottom: 12 }}>
          {[
            { id: 'TOP_BUY', label: '🔥 Top Scalps' },
            { id: 'ALL', label: `🌐 Todos (${opportunities.length})` },
            { id: 'Cripto MXN', label: '🇲🇽 Cripto MXN' },
            { id: 'Oro & RWA', label: '🪙 Oro & RWA' },
            { id: 'Divisas & FX', label: '💱 Divisas & FX' },
            { id: 'Layer-1 & DeFi', label: '⚡ Layer-1 & DeFi' },
            { id: 'Alta Volatilidad', label: '🚀 Memes' },
            { id: 'ARBITRAGE', label: '⚖️ Arbitraje MXN/USD' },
            { id: 'POSITIONS', label: `💼 Posiciones Activas (${openPositionsList.length})` },
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
                  <th>Diagnóstico de Paridad</th>
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
                    <td style={{ fontWeight: 700, color: a.abs_spread_bps >= 10 ? '#10b981' : '#38bdf8' }}>
                      {a.spread_bps > 0 ? `+${a.spread_bps}` : a.spread_bps} bps
                    </td>
                    <td style={{ fontFamily: 'Inter, sans-serif', color: '#e2e8f0' }}>{a.direction}</td>
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
                  <th>Precio (MXN)</th>
                  <th>vs VWAP</th>
                  <th>RSI(14)</th>
                  <th>Auto-TP / Trailing / Auto-SL (Por Moneda)</th>
                  <th>Score</th>
                  <th>Señal & Setup de Scalping</th>
                  <th>Acción Rápida</th>
                </tr>
              </thead>
              <tbody className="mono">
                {filteredOpportunities.map((opp) => {
                  const isBuy = opp.signal === 'BUY' || opp.signal === 'STRONG_BUY'
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
                          <span style={{ fontSize: '0.72rem', color: '#94a3b8', fontFamily: 'Inter, sans-serif' }}>
                            {opp.name}
                          </span>
                          {opp.has_position && (
                            <span
                              style={{
                                fontSize: '0.65rem',
                                padding: '1px 5px',
                                borderRadius: 4,
                                background: 'rgba(168,85,247,0.25)',
                                color: '#e9d5ff',
                              }}
                            >
                              ABIERTA
                            </span>
                          )}
                        </div>
                      </td>
                      <td style={{ fontWeight: 700 }}>{fmtMXN(opp.last)}</td>
                      <td style={{ color: opp.vwap_diff_pct <= 0 ? '#10b981' : '#cbd5e1' }}>
                        {opp.vwap_diff_pct > 0 ? `+${opp.vwap_diff_pct}%` : `${opp.vwap_diff_pct}%`}
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
                        <span style={{ color: '#10b981', fontWeight: 700 }}>TP +{opp.auto_tp_pct}%</span>
                        {' | '}
                        <span style={{ color: '#38bdf8' }}>Trail +{opp.auto_trail_arm_pct}%</span>
                        {' | '}
                        <span style={{ color: '#f43f5e' }}>SL -{opp.auto_sl_pct}%</span>
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
                      <td style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.75rem' }}>
                        <div style={{ fontWeight: 700, color: isBuy ? '#10b981' : isSell ? '#f43f5e' : '#94a3b8' }}>
                          {opp.signal_label} — {opp.setup_type}
                        </div>
                        <div style={{ color: '#94a3b8', fontSize: '0.71rem' }}>{opp.rationale}</div>
                      </td>
                      <td>
                        <div style={{ display: 'flex', gap: 6 }}>
                          <button
                            className="btn btn-secondary"
                            style={{ padding: '4px 8px', fontSize: '0.72rem' }}
                            onClick={() => handleSwitchBook(opp.book)}
                          >
                            Ver
                          </button>
                          <button
                            className="btn btn-buy"
                            style={{ padding: '4px 8px', fontSize: '0.72rem' }}
                            disabled={busy}
                            onClick={() =>
                              handleQuickOrder(
                                opp.book,
                                'BUY',
                                12000,
                                null,
                                `[Scalp Radar | Auto-TP +${opp.auto_tp_pct}% / SL -${opp.auto_sl_pct}%] ${opp.setup_type}`
                              )
                            }
                          >
                            +$12k
                          </button>
                          {opp.has_position && (
                            <button
                              className="btn btn-sell"
                              style={{ padding: '4px 8px', fontSize: '0.72rem' }}
                              disabled={busy}
                              onClick={() =>
                                handleQuickOrder(
                                  opp.book,
                                  'SELL',
                                  null,
                                  opp.held_amount,
                                  `[Cierre Manual Radar] Liquidación total de ${opp.symbol}`
                                )
                              }
                            >
                              Cerrar
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

      {/* WORKSPACE DETALLADO */}
      <div className="workspace-grid">
        <div className="left-col">
          {/* GRÁFICO EN TIEMPO REAL */}
          <div className="card">
            <div className="card-header">
              <div>
                <div className="card-title">
                  <BarChart2 size={18} color="#38bdf8" />
                  <span>
                    {bookMeta.name} ({bookMeta.pair}) — Auto-TP +{activePos.auto_tp_pct}% / Auto-SL -
                    {activePos.auto_sl_pct}%
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

          {/* HISTORIAL DE OPERACIONES PERSISTENTE */}
          <div className="card">
            <div className="card-header">
              <div className="card-title">
                <Activity size={17} color="#38bdf8" />
                <span>Historial Completo de Transacciones Guardadas ({portfolio.total_trades || 0} registros)</span>
              </div>
              <a
                href={`${API_BASE}/api/trades/export`}
                target="_blank"
                rel="noreferrer"
                className="btn btn-secondary"
                style={{ padding: '5px 10px', fontSize: '0.75rem', textDecoration: 'none' }}
              >
                <Download size={13} color="#10b981" /> Descargar CSV
              </a>
            </div>

            <div className="table-wrap" style={{ maxHeight: 380 }}>
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
                    <th>Ganancia / Pérdida</th>
                    <th>Motivo / Meta TP-SL</th>
                  </tr>
                </thead>
                <tbody className="mono">
                  {(!portfolio.recent_trades || portfolio.recent_trades.length === 0) ? (
                    <tr>
                      <td colSpan={9} style={{ textAlign: 'center', padding: 24, color: '#64748b' }}>
                        Esperando primeras ejecuciones de Scalping...
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
                          <td style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.74rem', color: '#cbd5e1' }}>
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

        {/* COLUMNA DERECHA: BOT SCALPER + POSICIONES ABIERTAS CON METAS AUTO-TP/SL */}
        <div className="right-col">
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
                <span>Motor Scalper de Alta Frecuencia</span>
                <span
                  style={{
                    fontSize: '0.72rem',
                    padding: '2px 8px',
                    borderRadius: 999,
                    background: bot.enabled ? 'rgba(16,185,129,0.2)' : 'rgba(148,163,184,0.15)',
                    color: bot.enabled ? '#10b981' : '#94a3b8',
                  }}
                >
                  {bot.enabled ? 'ACTIVO (CICLO 2s)' : 'EN PAUSA'}
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

            {/* Switch 1: Auto TP/SL por moneda */}
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '9px 12px',
                background: 'rgba(16,185,129,0.09)',
                border: '1px solid rgba(16,185,129,0.28)',
                borderRadius: 9,
                marginBottom: 8,
                fontSize: '0.8rem',
              }}
            >
              <div>
                <strong style={{ color: '#10b981' }}>TP y SL Automatizados por Moneda (Dinámico)</strong>
                <div style={{ fontSize: '0.72rem', color: '#94a3b8' }}>
                  Ajusta el Take Profit, Trailing Lock y Stop Loss de cada activo según su volatilidad y spread actual
                </div>
              </div>
              <input
                type="checkbox"
                checked={bot.auto_tp_sl_by_coin ?? true}
                onChange={(e) => handleUpdateBot({ auto_tp_sl_by_coin: e.target.checked })}
                style={{ width: 18, height: 18, accentColor: '#10b981', cursor: 'pointer' }}
              />
            </div>

            {/* Switch 2: Modo Cazador Multi-Activo */}
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
                <strong style={{ color: '#38bdf8' }}>Escáner Multi-Activo de Alta Rotación (Hasta 6 Posiciones)</strong>
                <div style={{ fontSize: '0.72rem', color: '#94a3b8' }}>
                  Opera automáticamente los mejores scalps cada {bot.cooldown_seconds || 6}s
                </div>
              </div>
              <input
                type="checkbox"
                checked={bot.multi_asset_auto ?? true}
                onChange={(e) => handleUpdateBot({ multi_asset_auto: e.target.checked })}
                style={{ width: 18, height: 18, accentColor: '#38bdf8', cursor: 'pointer' }}
              />
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
              <div className="input-group">
                <label className="input-label">% Cash por Operación</label>
                <input
                  type="number"
                  className="input-field mono"
                  min="5"
                  max="50"
                  step="1"
                  value={bot.trade_size_pct ?? 14}
                  onChange={(e) => handleUpdateBot({ trade_size_pct: parseFloat(e.target.value) || 14 })}
                />
              </div>
              <div className="input-group">
                <label className="input-label">Frecuencia Disparo (Segundos)</label>
                <input
                  type="number"
                  className="input-field mono"
                  min="2"
                  max="120"
                  step="1"
                  value={bot.cooldown_seconds ?? 6}
                  onChange={(e) => handleUpdateBot({ cooldown_seconds: parseInt(e.target.value, 10) || 6 })}
                />
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginTop: 10 }}>
              <button className="btn btn-buy" onClick={() => handleStepBot(null, null)} disabled={busy}>
                <Zap size={14} /> Ejecutar Ciclo Scalper Ahora
              </button>
              <button className="btn btn-secondary" onClick={() => handleStepBot('BUY', activeBook)} disabled={busy}>
                <ArrowUpRight size={14} color="#10b981" /> Comprar {bookMeta.symbol}
              </button>
            </div>
          </div>

          {/* POSICIONES ABIERTAS CON METAS AUTO-TP / TRAILING / AUTO-SL */}
          <div className="card">
            <div className="card-header">
              <div className="card-title">
                <Layers size={18} color="#a855f7" />
                <span>Posiciones Abiertas & Metas Automatizadas ({openPositionsList.length}/6)</span>
              </div>
            </div>

            {openPositionsList.length === 0 ? (
              <div style={{ fontSize: '0.82rem', color: '#64748b', textAlign: 'center', padding: '14px 0' }}>
                Sin posiciones abiertas en este segundo. El Scalper abrirá la siguiente oportunidad en automático.
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
                        padding: '10px 12px',
                        background: '#0b111e',
                        borderRadius: 9,
                        border: '1px solid rgba(255,255,255,0.06)',
                        fontSize: '0.77rem',
                      }}
                    >
                      <div>
                        <div>
                          <strong style={{ color: '#fff', fontSize: '0.88rem' }}>{meta.symbol}</strong>{' '}
                          <span style={{ color: '#94a3b8' }}>({fmtMXN(pos.market_value_mxn)})</span>
                        </div>
                        <div style={{ fontSize: '0.71rem', marginTop: 3 }}>
                          <span style={{ color: '#10b981' }}>Auto-TP: +{pos.auto_tp_pct}%</span>
                          {' • '}
                          <span style={{ color: '#38bdf8' }}>Trail: +{pos.auto_trail_arm_pct}%</span>
                          {' • '}
                          <span style={{ color: '#f43f5e' }}>Auto-SL: -{pos.auto_sl_pct}%</span>
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
                        <div style={{ fontSize: '0.69rem', color: '#94a3b8' }}>
                          Pico alcanzado: +{pos.peak_pnl_pct || 0}%
                        </div>
                        <div style={{ display: 'flex', gap: 5, justifyContent: 'flex-end', marginTop: 4 }}>
                          <button
                            className="btn btn-sell"
                            style={{ padding: '3px 8px', fontSize: '0.7rem' }}
                            disabled={busy}
                            onClick={() =>
                              handleQuickOrder(
                                pos.book,
                                'SELL',
                                null,
                                pos.amount,
                                `Toma manual de posición en ${meta.symbol}`
                              )
                            }
                          >
                            Cobrar / Cerrar
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
