import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import './index.css'

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }

  componentDidCatch(error, errorInfo) {
    console.error('CRITICAL APP ERROR:', error, errorInfo)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          minHeight: '100vh',
          backgroundColor: '#0a0f1d',
          color: '#f8fafc',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '24px',
          fontFamily: 'Inter, system-ui, sans-serif'
        }}>
          <div style={{
            background: '#131b2e',
            border: '1px solid #ef4444',
            borderRadius: '12px',
            padding: '28px',
            maxWidth: '600px',
            width: '100%',
            textAlign: 'center'
          }}>
            <h2 style={{ color: '#ef4444', marginTop: 0, marginBottom: '12px' }}>
              ⚠️ Error al Cargar la Interfaz
            </h2>
            <p style={{ color: '#94a3b8', fontSize: '14px', lineHeight: 1.6, marginBottom: '20px' }}>
              Ocurrió un detalle al renderizar la aplicación. Hemos guardado el reporte técnico para resolverlo.
            </p>
            <pre style={{
              background: '#090d16',
              padding: '12px',
              borderRadius: '8px',
              color: '#fca5a5',
              fontSize: '12px',
              textAlign: 'left',
              overflowX: 'auto',
              marginBottom: '20px'
            }}>
              {this.state.error?.toString()}
            </pre>
            <button
              onClick={() => window.location.reload()}
              style={{
                background: '#10b981',
                color: '#fff',
                border: 'none',
                borderRadius: '8px',
                padding: '10px 24px',
                fontWeight: 600,
                cursor: 'pointer',
                fontSize: '14px'
              }}
            >
              🔄 Recargar Aplicación
            </button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>,
)
