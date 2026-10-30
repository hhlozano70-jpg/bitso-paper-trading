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
  Maximize2
} from 'lucide-react'

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
          MONITOR CUÁDRUPLE: LOS 4 ACTIVOS MANEJADOS CON SUS GRÁFICOS Y PARÁMETROS
         ===================================================================== */}
      <section className="card" style={{ borderColor: 'rgba(56,189,248,0.5)', background: '#0e1628' }}>
        <div className="card-header">
          <div>
            <div className="card-title" style={{ fontSize: '1.08rem' }}>
              <Layers size={20} color="#38bdf8" />
              <span>Monitor Cuádruple: Los 4 Activos Manejados en Tiempo Real (Rotación Dinámica)</span>
            </div>
            <div style={{ fontSize: '0.78rem', color: '#94a3b8', marginTop: 2 }}>
              El algoritmo mantiene ocupados los 4 mejores slots combinando Cripto, Acciones de Wall Street, Futuros CME y Materias Primas/FX.
              Si un activo pierde impulso o aparece una mejor oportunidad, lo rota en automático sin preguntar.
            </div>
          </div>
        </div>

        {/* REJILLA DE LOS 4 ACTIVOS */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 14 }}>
          {managed4.map((asset) => {
            const isHeld = asset.is_active_position
            const pos = asset.position || {}
            const unrPct = pos.unrealized_pnl_pct || 0
            const cardBorder = isHeld ? (unrPct >= 0 ? 'rgba(16,185,129,0.5)' : 'rgba(244,63,94,0.5)') : 'rgba(56,189,248,0.25)'

            return (
              <div
                key={asset.book}
                style={{
                  background: 'linear-gradient(180deg, #131c31 0%, #0c1220 100%)',
                  border: `1px solid ${cardBorder}`,
                  borderRadius: 12,
                  padding: 13,
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 8,
                }}
              >
                {/* Cabecera del Slot */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span
                      className="mono"
                      style={{
                        background: isHeld ? '#10b981' : '#38bdf8',
                        color: '#061a14',
                        fontWeight: 800,
                        padding: '2px 7px',
                        borderRadius: 6,
                        fontSize: '0.72rem',
                      }}
                    >
                      SLOT #{asset.slot}
                    </span>
                    <strong style={{ fontSize: '0.98rem' }}>{asset.symbol}</strong>
                    <span
                      style={{
                        fontSize: '0.68rem',
                        padding: '2px 7px',
                        borderRadius: 999,
                        background: 'rgba(255,255,255,0.08)',
                        color: '#94a3b8',
                      }}
                    >
                      {asset.category}
                    </span>
                  </div>

                  <span
                    className="mono"
                    style={{
                      fontSize: '0.75rem',
                      fontWeight: 700,
                      color: isHeld ? (unrPct >= 0 ? '#10b981' : '#f43f5e') : '#38bdf8',
                    }}
                  >
                    {isHeld ? `${unrPct >= 0 ? '+' : ''}${unrPct.toFixed(2)}% (EN CARTERA)` : 'VIGILANCIA TOP'}
                  </span>
                </div>

                {/* Precio y Variación */}
                <div className="mono" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                  <span style={{ fontSize: '1.2rem', fontWeight: 800 }}>{fmtMXN(asset.last_price)}</span>
                  <span style={{ fontSize: '0.8rem', color: asset.change_24_pct >= 0 ? '#10b981' : '#f43f5e' }}>
                    {asset.change_24_pct >= 0 ? '+' : ''}{asset.change_24_pct}% (24h)
                  </span>
                </div>

                {/* Mini Gráfico en Tiempo Real */}
                <div style={{ background: '#080d16', borderRadius: 8, padding: '4px 6px', border: '1px solid rgba(255,255,255,0.05)' }}>
                  <MiniChart data={asset.price_history} color={isHeld ? (unrPct >= 0 ? '#10b981' : '#f43f5e') : '#38bdf8'} />
                </div>

                {/* Parámetros Técnicos y Metas Dinámicas */}
                <div
                  className="mono"
                  style={{
                    display: 'grid',
                    gridTemplateColumns: '1fr 1fr',
                    gap: 6,
                    fontSize: '0.74rem',
                    background: '#090e1a',
                    padding: 8,
                    borderRadius: 8,
                    border: '1px solid rgba(255,255,255,0.04)',
                  }}
                >
                  <div>
                    <span style={{ color: '#94a3b8' }}>Auto-TP: </span>
                    <strong style={{ color: '#10b981' }}>+{asset.auto_tp_pct}%</strong>
                    <div style={{ fontSize: '0.68rem', color: '#64748b' }}>Meta: {fmtMXN(asset.tp_price)}</div>
                  </div>
                  <div>
                    <span style={{ color: '#94a3b8' }}>Auto-SL: </span>
                    <strong style={{ color: '#f43f5e' }}>-{asset.auto_sl_pct}%</strong>
                    <div style={{ fontSize: '0.68rem', color: '#64748b' }}>Piso: {fmtMXN(asset.sl_price)}</div>
                  </div>
                  <div>
                    <span style={{ color: '#94a3b8' }}>Trailing Lock: </span>
                    <strong style={{ color: '#38bdf8' }}>+{asset.auto_trail_arm_pct}%</strong>
                  </div>
                  <div>
                    <span style={{ color: '#94a3b8' }}>RSI(14): </span>
                    <strong style={{ color: asset.rsi_14 > 65 ? '#f43f5e' : asset.rsi_14 < 38 ? '#10b981' : '#f1f5f9' }}>
                      {asset.rsi_14}
                    </strong>
                  </div>
                </div>

                {/* Estado y Diagnóstico */}
                <div style={{ fontSize: '0.73rem', color: '#cbd5e1' }}>
                  <strong style={{ color: '#38bdf8' }}>{asset.setup_type}:</strong> {asset.rationale}
                </div>

                {/* Botón de Rotación Directa */}
                {isHeld && (
                  <button
                    className="btn btn-secondary"
                    style={{ padding: '6px 10px', fontSize: '0.74rem', marginTop: 3 }}
                    onClick={() => handleRotateAsset(asset.book)}
                    disabled={busy}
                  >
                    <Repeat size={13} color="#f59e0b" /> Rotar este activo ahora
                  </button>
                )}
              </div>
            )
          })}
        </div>
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

        {/* Pestañas de Filtro */}
        <div className="book-tabs" style={{ marginBottom: 12 }}>
          {[
            { id: 'ALL', label: `🌐 Todos (${opportunities.length})` },
            { id: 'Acciones', label: '📈 Acciones (Wall Street)' },
            { id: 'Futuros', label: '⚡ Futuros (CME / NYMEX)' },
            { id: 'Cripto MXN', label: '🇲🇽 Cripto MXN' },
            { id: 'Oro & RWA', label: '🪙 Oro & RWA' },
            { id: 'Divisas & FX', label: '💱 Divisas & FX' },
            { id: 'Layer-1 & DeFi', label: '🚀 Layer-1 & DeFi' },
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
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <strong style={{ color: '#fff' }}>{opp.symbol}</strong>
                        <span style={{ fontSize: '0.72rem', color: '#94a3b8', fontFamily: 'Inter, sans-serif' }}>
                          {opp.name}
                        </span>
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
