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
  Repeat,
  ShieldAlert,
  Sliders,
  DollarSign,
  Maximize2,
  ShieldCheck,
  Columns,
  Grid,
  Square
} from 'lucide-react'
import ProChartStudio from './ProChartStudio'

const isLocalVite = typeof window !== 'undefined' && window.location.port === '5173'
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

// Mini Gráfico SVG optimizado para la vista de 4 Activos
function MiniChart({ data, color = '#38bdf8', height = 110 }) {
  const width = 360
  const padLeft = 46
  const padRight = 10
  const padTop = 12
  const padBottom = 20

  const plotW = width - padLeft - padRight
  const plotH = height - padTop - padBottom

  const points = useMemo(() => {
    if (!data || data.length === 0) return []
    return data
  }, [data])

  if (points.length < 2) {
    return (
      <div style={{ height, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.72rem', color: '#64748b' }}>
        Sincronizando ticks en vivo...
      </div>
    )
  }

  const values = points.map(p => p.price || 0).filter(v => v > 0)
  const minVal = Math.min(...values)
  const maxVal = Math.max(...values)
  const span = maxVal - minVal > 0 ? maxVal - minVal : maxVal * 0.002 || 1
  const yMin = minVal - span * 0.1
  const yMax = maxVal + span * 0.1

  const getX = (idx) => padLeft + (idx / Math.max(1, points.length - 1)) * plotW
  const getY = (val) => padTop + plotH - ((val - yMin) / (yMax - yMin)) * plotH

  const linePath = points
    .map((pt, i) => `${i === 0 ? 'M' : 'L'} ${getX(i).toFixed(1)} ${getY(pt.price).toFixed(1)}`)
    .join(' ')
  const areaPath = `${linePath} L ${getX(points.length - 1).toFixed(1)} ${(padTop + plotH).toFixed(1)} L ${padLeft} ${(padTop + plotH).toFixed(1)} Z`

  return (
    <svg viewBox={`0 0 ${width} ${height}`} style={{ width: '100%', height: 'auto', display: 'block' }}>
      <defs>
        <linearGradient id={`grad-${color.replace('#','')}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.25" />
          <stop offset="100%" stopColor={color} stopOpacity="0.0" />
        </linearGradient>
      </defs>
      <path d={areaPath} fill={`url(#grad-${color.replace('#','')})`} />
      <path d={linePath} fill="none" stroke={color} strokeWidth="1.8" />
      <circle
        cx={getX(points.length - 1)}
        cy={getY(points[points.length - 1].price)}
        r="3.5"
        fill={color}
      />
      <text x={padLeft - 4} y={getY(maxVal) + 3} textAnchor="end" fill="#64748b" fontSize="9" fontFamily="monospace">
        ${maxVal >= 1000 ? (maxVal/1000).toFixed(1)+'k' : maxVal.toFixed(1)}
      </text>
      <text x={padLeft - 4} y={getY(minVal) + 3} textAnchor="end" fill="#64748b" fontSize="9" fontFamily="monospace">
        ${minVal >= 1000 ? (minVal/1000).toFixed(1)+'k' : minVal.toFixed(1)}
      </text>
    </svg>
  )
}

export default function App() {
  const [state, setState] = useState(null)
  const [wsConnected, setWsConnected] = useState(false)
  const [scannerFilter, setScannerFilter] = useState('ALL')
  const [statusBanner, setStatusBanner] = useState(null)
  const [busy, setBusy] = useState(false)
  const [workspaceLayout, setWorkspaceLayout] = useState('quad') // 'quad' | 'dual' | 'focus'
  const [focusedAssetIndex, setFocusedAssetIndex] = useState(0)
  const [showRiskCalculator, setShowRiskCalculator] = useState(false)
  const [riskAmountMXN, setRiskAmountMXN] = useState(150)
  const wsRef = useRef(null)

  const showToast = (type, message) => {
    setStatusBanner({ type, message })
    setTimeout(() => {
      setStatusBanner((prev) => (prev?.message === message ? null : prev))
    }, 4500)
  }

  const fetchState = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/state`)
      if (res.ok) {
        const data = await res.json()
        setState(data)
      }
    } catch (err) {
      console.error('Error al actualizar estado:', err)
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
        <span style={{ fontWeight: 600 }}>Cargando Panel Autónomo de 4 Activos (Cripto, Acciones, Futuros)...</span>
      </div>
    )
  }

  const catalog = state.asset_catalog || {}
  const portfolio = state.portfolio || {}
  const managed4 = state.managed_4_assets || []
  const pnlBalance = portfolio.pnl_balance || {
    total_transactions: 0,
    winning_count: 0,
    losing_count: 0,
    win_rate_pct: 0,
    gross_profit_mxn: 0,
    gross_loss_mxn: 0,
    net_realized_pnl_mxn: 0,
    profit_factor: 0,
    by_book: [],
  }
  const bot = state.bot || {}
  const opportunities = state.opportunities || []
  const openPositionsList = Object.values(portfolio.positions || {}).filter((p) => p.amount > 1e-8)

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

  const handleRotateAsset = async (book) => {
    setBusy(true)
    try {
      const res = await fetch(`${API_BASE}/api/rotate/${book}`, { method: 'POST' })
      if (res.ok) {
        const data = await res.json()
        setState(data)
        showToast('info', `Rotación forzada de ${catalog[book]?.symbol || book} completada`)
      }
    } catch (err) {
      showToast('error', 'Error al solicitar rotación')
    } finally {
      setBusy(false)
    }
  }

  const handleQuickBuy = async (book, mxnAmount) => {
    setBusy(true)
    try {
      const res = await fetch(`${API_BASE}/api/order`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          book,
          side: 'BUY',
          mxn_amount: mxnAmount,
          reason: 'Orden manual ejecutada desde el Gráfico Pro (Trade from Chart)',
        }),
      })
      if (res.ok) {
        showToast('success', `Compra ejecutada en ${catalog[book]?.symbol || book}: ${fmtMXN(mxnAmount, 0)}`)
        fetchState()
      } else {
        const err = await res.json()
        showToast('error', err.detail || 'Error ejecutando compra rápida')
      }
    } catch (e) {
      showToast('error', 'Error de conexión al enviar orden')
    } finally {
      setBusy(false)
    }
  }

  const handleQuickSell = async (book) => {
    setBusy(true)
    try {
      const res = await fetch(`${API_BASE}/api/order`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          book,
          side: 'SELL',
          reason: 'Cierre manual ejecutado desde el Gráfico Pro (Trade from Chart)',
        }),
      })
      if (res.ok) {
        showToast('info', `Posición en ${catalog[book]?.symbol || book} cerrada exitosamente`)
        fetchState()
      } else {
        const err = await res.json()
        showToast('error', err.detail || 'Error al cerrar posición')
      }
    } catch (e) {
      showToast('error', 'Error de conexión al cerrar posición')
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
        showToast('info', 'Portafolio reiniciado con $100,000 MXN')
      }
    } finally {
      setBusy(false)
    }
  }

  const filteredOpportunities = opportunities.filter((opp) => {
    if (scannerFilter === 'ALL') return true
    if (scannerFilter === 'PREMIER') return opp.is_premier
    if (scannerFilter === 'SNIPER') return opp.opportunity_score >= 76
    if (scannerFilter === 'OVERSOLD') return opp.rsi_14 < 40
    if (scannerFilter === 'POSITIONS') return opp.has_position
    return opp.category === scannerFilter
  })

  return (
    <div className="app-shell">
      {/* BARRA SUPERIOR */}
      <header className="topbar">
        <div className="brand">
          <div className="brand-logo mono">4X</div>
          <div>
            <div className="brand-title">
              Autonomous 4-Asset Portfolio Rotator & Scalper
              <span className="badge-live">
                <span className="pulse-dot" />
                39 ACTIVOS GLOBALES (CRIPTO, ACCIONES, FUTUROS, ORO)
              </span>
            </div>
            <div style={{ fontSize: '0.76rem', color: '#94a3b8' }}>
              Rotación 100% automatizada por comportamiento • Sin preguntas • Auto-TP y Auto-SL dinámicos por moneda
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          <div
            style={{
              padding: '6px 12px',
              borderRadius: 8,
              background: bot.enabled ? 'rgba(16,185,129,0.15)' : 'rgba(244,63,94,0.15)',
              border: `1px solid ${bot.enabled ? '#10b981' : '#f43f5e'}`,
              color: bot.enabled ? '#10b981' : '#f43f5e',
              fontSize: '0.8rem',
              fontWeight: 700,
              display: 'flex',
              alignItems: 'center',
              gap: 6
            }}
          >
            <Bot size={16} />
            {bot.enabled ? 'AUTO-PILOT ACTIVO' : 'PAUSADO'}
          </div>

          <button
            className={`btn ${bot.enabled ? 'btn-sell' : 'btn-buy'}`}
            style={{ padding: '7px 14px' }}
            onClick={() => handleUpdateBot({ enabled: !bot.enabled })}
          >
            {bot.enabled ? <><Pause size={14} /> Pausar</> : <><Play size={14} /> Encender</>}
          </button>

          <button
            className="btn btn-secondary"
            style={{
              padding: '7px 12px',
              background: showRiskCalculator ? 'rgba(56,189,248,0.2)' : undefined,
              borderColor: showRiskCalculator ? '#38bdf8' : undefined,
            }}
            onClick={() => setShowRiskCalculator(!showRiskCalculator)}
            title="Calculadora de Gestión de Riesgo y Tamaño de Posición (ProRealTime)"
          >
            <ShieldCheck size={14} color="#38bdf8" /> Gestión de Riesgo Pro
          </button>

          <a
            href={`${API_BASE}/api/trades/export`}
            target="_blank"
            rel="noreferrer"
            className="btn btn-secondary"
            style={{ textDecoration: 'none', padding: '7px 12px' }}
          >
            <Download size={14} color="#10b981" /> CSV
          </a>

          <button className="btn btn-secondary" style={{ padding: '7px 12px' }} onClick={handleResetPortfolio} disabled={busy}>
            <RefreshCw size={14} /> Reiniciar $100k
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
          {statusBanner.type === 'error' ? <AlertCircle size={17} color="#f43f5e" /> : <CheckCircle2 size={17} color="#10b981" />}
          <span>{statusBanner.message}</span>
        </div>
      )}

      {/* PANEL DE GESTIÓN MONETARIA PROREALTIME */}
      {showRiskCalculator && (
        <section className="card" style={{ background: '#0a101f', borderColor: '#38bdf8', padding: '16px 20px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <ShieldCheck size={20} color="#38bdf8" />
              <div>
                <strong style={{ fontSize: '1rem', color: '#fff' }}>Calculadora de Gestión Monetaria & Riesgo Asimétrico (ProRealTime Money Management)</strong>
                <div style={{ fontSize: '0.74rem', color: '#94a3b8' }}>
                  Define tu tolerancia máxima de pérdida por operación y calcula el tamaño exacto de posición con Stop Loss estricto (-0.35%) y Take Profit (+0.55%).
                </div>
              </div>
            </div>
            <button className="btn btn-secondary" style={{ padding: '4px 10px', fontSize: '0.72rem' }} onClick={() => setShowRiskCalculator(false)}>
              Cerrar
            </button>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 14 }}>
            <div style={{ background: '#0d1527', padding: 12, borderRadius: 10, border: '1px solid rgba(255,255,255,0.06)' }}>
              <span style={{ fontSize: '0.74rem', color: '#94a3b8' }}>Pérdida Máxima Tolerable por Trade:</span>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 6 }}>
                <span className="mono" style={{ fontSize: '1.25rem', fontWeight: 800, color: '#f43f5e' }}>
                  -${riskAmountMXN} MXN
                </span>
              </div>
              <div style={{ display: 'flex', gap: 6, marginTop: 8 }}>
                {[100, 150, 250, 400].map((amt) => (
                  <button
                    key={amt}
                    style={{
                      background: riskAmountMXN === amt ? 'rgba(244,63,94,0.25)' : '#070b14',
                      color: riskAmountMXN === amt ? '#f43f5e' : '#94a3b8',
                      border: `1px solid ${riskAmountMXN === amt ? '#f43f5e' : 'rgba(255,255,255,0.08)'}`,
                      borderRadius: 5,
                      padding: '3px 8px',
                      fontSize: '0.7rem',
                      fontWeight: 700,
                      cursor: 'pointer',
                    }}
                    onClick={() => setRiskAmountMXN(amt)}
                  >
                    ${amt}
                  </button>
                ))}
              </div>
            </div>

            <div style={{ background: '#0d1527', padding: 12, borderRadius: 10, border: '1px solid rgba(255,255,255,0.06)' }}>
              <span style={{ fontSize: '0.74rem', color: '#94a3b8' }}>Tamaño de Posición Sugerido:</span>
              <div className="mono" style={{ fontSize: '1.25rem', fontWeight: 800, color: '#38bdf8', marginTop: 6 }}>
                {fmtMXN(Math.round(riskAmountMXN / 0.0035), 0)}
              </div>
              <span style={{ fontSize: '0.7rem', color: '#64748b' }}>
                Fórmula: Riesgo / 0.35% SL = {( (riskAmountMXN / 0.0035) / Math.max(1, portfolio.total_equity_mxn || 100000) * 100 ).toFixed(1)}% del capital
              </span>
            </div>

            <div style={{ background: '#0d1527', padding: 12, borderRadius: 10, border: '1px solid rgba(255,255,255,0.06)' }}>
              <span style={{ fontSize: '0.74rem', color: '#94a3b8' }}>Ganancia Proyectada al Take Profit (+0.55%):</span>
              <div className="mono" style={{ fontSize: '1.25rem', fontWeight: 800, color: '#10b981', marginTop: 6 }}>
                +{fmtMXN(Math.round((riskAmountMXN / 0.0035) * 0.0055), 0)}
              </div>
              <span style={{ fontSize: '0.7rem', color: '#10b981' }}>
                Ratio Riesgo/Recompensa: 1 : 1.57 (Asimétrico Favorable)
              </span>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 6 }}>
              <button
                className="btn btn-primary"
                style={{
                  padding: '9px 14px',
                  fontWeight: 800,
                  fontSize: '0.78rem',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 6,
                }}
                onClick={() => {
                  const targetPct = Math.min(60, Math.max(15, Math.round(((riskAmountMXN / 0.0035) / Math.max(1, portfolio.total_equity_mxn || 100000)) * 100)))
                  handleUpdateBot({ trade_size_pct: targetPct })
                  showToast('success', `Tamaño del Bot fijado a ${targetPct}% ($${riskAmountMXN} MXN riesgo máx)`)
                }}
              >
                <Sliders size={15} /> Aplicar Tamaño al Auto-Pilot ({Math.min(60, Math.max(15, Math.round(((riskAmountMXN / 0.0035) / Math.max(1, portfolio.total_equity_mxn || 100000)) * 100)))}%)
              </button>
            </div>
          </div>
        </section>
      )}

      {/* KPI STRIP */}
      <section className="kpi-grid">
        <div className="card kpi-card">
          <div className="kpi-label">
            <span>Valor Total Cartera (Equity)</span>
            <Wallet size={16} color="#38bdf8" />
          </div>
          <div className="kpi-value mono">{fmtMXN(portfolio.total_equity_mxn)}</div>
          <div className="kpi-sub">
            <span className={`pos-pill ${portfolio.total_return_mxn >= 0 ? 'up' : 'down'} mono`}>
              {portfolio.total_return_mxn >= 0 ? '+' : ''}
              {fmtMXN(portfolio.total_return_mxn)} ({portfolio.total_return_pct >= 0 ? '+' : ''}
              {portfolio.total_return_pct}%)
            </span>
            <span>Efectivo libre: {fmtMXN(portfolio.cash_mxn, 0)}</span>
          </div>
        </div>

        <div className="card kpi-card">
          <div className="kpi-label">
            <span>Ganancias Brutas Realizadas</span>
            <TrendingUp size={16} color="#10b981" />
          </div>
          <div className="kpi-value mono" style={{ color: '#10b981' }}>
            +{fmtMXN(pnlBalance.gross_profit_mxn)}
          </div>
          <div className="kpi-sub">
            <span className="pos-pill up">{pnlBalance.winning_count} ventas ganadoras</span>
            <span>Win Rate: {pnlBalance.win_rate_pct}%</span>
          </div>
        </div>

        <div className="card kpi-card">
          <div className="kpi-label">
            <span>Pérdidas Brutas Controladas</span>
            <TrendingDown size={16} color="#f43f5e" />
          </div>
          <div className="kpi-value mono" style={{ color: '#f43f5e' }}>
            {fmtMXN(pnlBalance.gross_loss_mxn)}
          </div>
          <div className="kpi-sub">
            <span className="pos-pill down">{pnlBalance.losing_count} ventas defensivas</span>
            <span>Profit Factor: {pnlBalance.profit_factor}x</span>
          </div>
        </div>

        <div className="card kpi-card">
          <div className="kpi-label">
            <span>Balance Neto Cerrado (PnL)</span>
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
            <span>Transacciones totales: {pnlBalance.total_transactions}</span>
          </div>
        </div>
      </section>

      {/* =====================================================================
          MONITOR MULTI-LAYOUT ESTILO PROREALTIME WEB (STUDIO PROFESIONAL)
         ===================================================================== */}
      <section className="card" style={{ borderColor: 'rgba(56,189,248,0.5)', background: '#0c1322' }}>
        <div className="card-header" style={{ flexWrap: 'wrap', gap: 12 }}>
          <div>
            <div className="card-title" style={{ fontSize: '1.08rem' }}>
              <Layers size={20} color="#38bdf8" />
              <span>Studio de Trading Profesional (Estilo ProRealTime Web)</span>
            </div>
            <div style={{ fontSize: '0.78rem', color: '#94a3b8', marginTop: 2 }}>
              Velas Japonesas en tiempo real, Overlays de Trading from Chart (TP / SL en pantalla), Indicadores (VWAP, EMA, RSI) y Ejecución Rápida 1-Click.
            </div>
          </div>

          {/* Selector de Layouts ProRealTime */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, background: '#070b14', padding: 3, borderRadius: 8, border: '1px solid rgba(255,255,255,0.08)' }}>
            <button
              style={{
                background: workspaceLayout === 'quad' ? '#38bdf8' : 'transparent',
                color: workspaceLayout === 'quad' ? '#04121e' : '#94a3b8',
                border: 'none',
                borderRadius: 6,
                padding: '4px 10px',
                fontSize: '0.74rem',
                fontWeight: 700,
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: 5,
              }}
              onClick={() => setWorkspaceLayout('quad')}
              title="Layout Cuádruple (4 Gráficos Simultáneos)"
            >
              <Grid size={13} /> Cuádruple (4)
            </button>
            <button
              style={{
                background: workspaceLayout === 'dual' ? '#38bdf8' : 'transparent',
                color: workspaceLayout === 'dual' ? '#04121e' : '#94a3b8',
                border: 'none',
                borderRadius: 6,
                padding: '4px 10px',
                fontSize: '0.74rem',
                fontWeight: 700,
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: 5,
              }}
              onClick={() => setWorkspaceLayout('dual')}
              title="Layout Dual (2 Gráficos en Paralelo)"
            >
              <Columns size={13} /> Dual (2)
            </button>
            <button
              style={{
                background: workspaceLayout === 'focus' ? '#38bdf8' : 'transparent',
                color: workspaceLayout === 'focus' ? '#04121e' : '#94a3b8',
                border: 'none',
                borderRadius: 6,
                padding: '4px 10px',
                fontSize: '0.74rem',
                fontWeight: 700,
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: 5,
              }}
              onClick={() => setWorkspaceLayout('focus')}
              title="Layout Foco Total (1 Gráfico Grande con Libro DOM)"
            >
              <Square size={13} /> Foco Total (1)
            </button>
          </div>
        </div>

        {/* SI ESTÁ EN FOCO TOTAL: PESTAÑAS PARA CAMBIAR RÁPIDAMENTE DE ACTIVO */}
        {workspaceLayout === 'focus' && (
          <div style={{ display: 'flex', gap: 8, marginBottom: 12, overflowX: 'auto', paddingBottom: 4 }}>
            {managed4.map((ast, idx) => (
              <button
                key={ast.book}
                className={`book-tab ${focusedAssetIndex === idx ? 'active' : ''}`}
                style={{ padding: '5px 12px', fontSize: '0.76rem', display: 'flex', alignItems: 'center', gap: 6 }}
                onClick={() => setFocusedAssetIndex(idx)}
              >
                <strong>{ast.symbol}</strong>
                <span className="mono" style={{ fontSize: '0.7rem', color: ast.is_active_position ? '#10b981' : '#94a3b8' }}>
                  {ast.is_active_position ? 'EN CARTERA' : fmtMXN(ast.last_price, 1)}
                </span>
              </button>
            ))}
          </div>
        )}

        {/* RENDERIZADO SEGÚN EL LAYOUT SELECCIONADO */}
        {workspaceLayout === 'focus' ? (
          <div>
            {managed4[focusedAssetIndex] && (
              <ProChartStudio
                asset={managed4[focusedAssetIndex]}
                orderBook={state.order_book}
                onQuickBuy={handleQuickBuy}
                onQuickSell={handleQuickSell}
                onRotate={handleRotateAsset}
                availableCash={portfolio.cash_mxn}
                isFocusMode={true}
                onToggleFocus={() => setWorkspaceLayout('quad')}
              />
            )}
          </div>
        ) : workspaceLayout === 'dual' ? (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(440px, 1fr))', gap: 14 }}>
            {managed4.slice(0, 2).map((asset) => (
              <ProChartStudio
                key={asset.book}
                asset={asset}
                orderBook={state.order_book}
                onQuickBuy={handleQuickBuy}
                onQuickSell={handleQuickSell}
                onRotate={handleRotateAsset}
                availableCash={portfolio.cash_mxn}
                isFocusMode={true}
                onToggleFocus={() => {
                  setFocusedAssetIndex(managed4.findIndex((m) => m.book === asset.book))
                  setWorkspaceLayout('focus')
                }}
              />
            ))}
          </div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 14 }}>
            {managed4.map((asset, idx) => (
              <ProChartStudio
                key={asset.book}
                asset={asset}
                orderBook={state.order_book}
                onQuickBuy={handleQuickBuy}
                onQuickSell={handleQuickSell}
                onRotate={handleRotateAsset}
                availableCash={portfolio.cash_mxn}
                isFocusMode={false}
                onToggleFocus={() => {
                  setFocusedAssetIndex(idx)
                  setWorkspaceLayout('focus')
                }}
              />
            ))}
          </div>
        )}
      </section>

      {/* =====================================================================
          RADAR DE OPORTUNIDADES EXPANDIDO: 39 ACTIVOS (CRIPTO, ACCIONES, FUTUROS, ORO)
         ===================================================================== */}
      <section className="card" style={{ borderColor: 'rgba(16,185,129,0.35)' }}>
        <div className="card-header">
          <div>
            <div className="card-title">
              <Compass size={19} color="#10b981" />
              <span>Radar Cuantitativo Global: 39 Activos Evaluados para Rotación de Cartera</span>
            </div>
            <div style={{ fontSize: '0.76rem', color: '#94a3b8', marginTop: 2 }}>
              Acciones de Wall Street (NVDA, TSLA, AAPL, MSFT...), Futuros CME (Nasdaq, S&P 500, Petróleo WTI, Oro COMEX) y Cripto Bitso
            </div>
          </div>
        </div>

        {/* Pestañas de Filtro ProRealScreener */}
        <div className="book-tabs" style={{ marginBottom: 12 }}>
          {[
            { id: 'ALL', label: `🌐 Todos (${opportunities.length})` },
            { id: 'PREMIER', label: '⭐ Líderes Premier (7)' },
            { id: 'SNIPER', label: '⚡ Sniper (Score ≥ 76)' },
            { id: 'OVERSOLD', label: '📉 Sobreventa (RSI < 40)' },
            { id: 'Acciones', label: '📈 Acciones (Wall Street)' },
            { id: 'Futuros', label: '⚡ Futuros (CME / NYMEX)' },
            { id: 'Cripto MXN', label: '🪙 Cripto MXN' },
            { id: 'POSITIONS', label: `💼 En Cartera (${openPositionsList.length})` },
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

        {/* Tabla de Activos */}
        <div className="table-wrap" style={{ maxHeight: 310 }}>
          <table>
            <thead>
              <tr>
                <th>Activo</th>
                <th>Mercado / Categoría</th>
                <th>Precio (MXN)</th>
                <th>vs VWAP</th>
                <th>RSI(14)</th>
                <th>Auto-TP</th>
                <th>Auto-SL</th>
                <th>Score IA</th>
                <th>Diagnóstico y Setup</th>
              </tr>
            </thead>
            <tbody className="mono">
              {filteredOpportunities.map((opp) => {
                const isBuy = opp.signal === 'BUY' || opp.signal === 'STRONG_BUY'
                return (
                  <tr key={opp.book}>
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                        <strong style={{ color: '#fff' }}>{opp.symbol}</strong>
                        <span style={{ fontSize: '0.72rem', color: '#94a3b8', fontFamily: 'Inter, sans-serif' }}>
                          {opp.name}
                        </span>
                        {opp.is_premier && (
                          <span
                            style={{
                              fontSize: '0.62rem',
                              padding: '1px 5px',
                              borderRadius: 4,
                              background: 'rgba(56,189,248,0.18)',
                              color: '#38bdf8',
                              fontWeight: 700,
                            }}
                          >
                            PREMIER
                          </span>
                        )}
                        {opp.macro_status && opp.macro_status !== 'Alineado' && (
                          <span
                            style={{
                              fontSize: '0.62rem',
                              padding: '1px 5px',
                              borderRadius: 4,
                              background: opp.macro_status.includes('Bloqueado') ? 'rgba(244,63,94,0.18)' : 'rgba(234,179,8,0.18)',
                              color: opp.macro_status.includes('Bloqueado') ? '#f43f5e' : '#eab308',
                              fontWeight: 700,
                            }}
                          >
                            {opp.macro_status}
                          </span>
                        )}
                        {opp.has_position && (
                          <span
                            style={{
                              fontSize: '0.64rem',
                              padding: '1px 5px',
                              borderRadius: 4,
                              background: 'rgba(16,185,129,0.2)',
                              color: '#10b981',
                              fontWeight: 700,
                            }}
                          >
                            SLOT ACTIVO
                          </span>
                        )}
                      </div>
                    </td>
                    <td style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.74rem', color: '#94a3b8' }}>
                      {opp.category}
                    </td>
                    <td style={{ fontWeight: 700 }}>{fmtMXN(opp.last)}</td>
                    <td style={{ color: opp.vwap_diff_pct <= 0 ? '#10b981' : '#cbd5e1' }}>
                      {opp.vwap_diff_pct > 0 ? `+${opp.vwap_diff_pct}%` : `${opp.vwap_diff_pct}%`}
                    </td>
                    <td style={{ color: opp.rsi_14 < 40 ? '#10b981' : opp.rsi_14 > 65 ? '#f43f5e' : '#cbd5e1' }}>
                      {opp.rsi_14}
                    </td>
                    <td style={{ color: '#10b981', fontWeight: 700 }}>+{opp.auto_tp_pct}%</td>
                    <td style={{ color: '#f43f5e', fontWeight: 700 }}>-{opp.auto_sl_pct}%</td>
                    <td>
                      <span
                        style={{
                          padding: '2px 7px',
                          borderRadius: 6,
                          fontWeight: 800,
                          background: isBuy ? 'rgba(16,185,129,0.18)' : 'rgba(148,163,184,0.12)',
                          color: isBuy ? '#10b981' : '#cbd5e1',
                        }}
                      >
                        {opp.opportunity_score}
                      </span>
                    </td>
                    <td style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.74rem' }}>
                      <strong>{opp.setup_type}</strong> • <span style={{ color: '#94a3b8' }}>{opp.rationale}</span>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </section>

      {/* HISTORIAL Y BALANCE CONTABLE */}
      <section className="card">
        <div className="card-header">
          <div className="card-title">
            <PieChart size={18} color="#a855f7" />
            <span>Balance de Ganancias vs Pérdidas & Desglose por Activo</span>
          </div>
          <span className="mono" style={{ fontSize: '0.8rem', color: '#94a3b8' }}>
            Base de datos SQLite persistente ({portfolio.total_trades} operaciones)
          </span>
        </div>

        {pnlBalance.by_book && pnlBalance.by_book.length > 0 ? (
          <div className="table-wrap" style={{ maxHeight: 220 }}>
            <table>
              <thead>
                <tr>
                  <th>Activo</th>
                  <th>Operaciones</th>
                  <th>Ganadoras / Perdedoras</th>
                  <th>Win Rate</th>
                  <th>Ganancia Bruta</th>
                  <th>Pérdida Bruta</th>
                  <th>Balance Neto Cerrado</th>
                </tr>
              </thead>
              <tbody className="mono">
                {pnlBalance.by_book.map((row) => {
                  const meta = catalog[row.book] || { symbol: row.book.toUpperCase() }
                  return (
                    <tr key={row.book}>
                      <td><strong>{meta.symbol}</strong></td>
                      <td>{row.total_trades} ({row.buys} C / {row.sells} V)</td>
                      <td>
                        <span style={{ color: '#10b981' }}>{row.wins}G</span> / <span style={{ color: '#f43f5e' }}>{row.losses}P</span>
                      </td>
                      <td>{row.win_rate_pct}%</td>
                      <td style={{ color: '#10b981' }}>+{fmtMXN(row.gross_profit_mxn)}</td>
                      <td style={{ color: '#f43f5e' }}>{fmtMXN(row.gross_loss_mxn)}</td>
                      <td style={{ fontWeight: 800, color: row.net_pnl_mxn >= 0 ? '#10b981' : '#f43f5e' }}>
                        {row.net_pnl_mxn >= 0 ? '+' : ''}{fmtMXN(row.net_pnl_mxn)}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div style={{ textAlign: 'center', padding: 20, color: '#64748b', fontSize: '0.8rem' }}>
            Aún no hay transacciones cerradas en el nuevo balance.
          </div>
        )}
      </section>
    </div>
  )
}
