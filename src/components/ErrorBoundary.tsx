import React from 'react';
import { LAYOUT_STORAGE_KEY } from '../layout/layoutStorage';

type Props = { children: React.ReactNode };
type State = { error: string | null };

export class ErrorBoundary extends React.Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error: error.stack || error.message };
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div
        style={{
          minHeight: '100vh',
          background: '#1a1a1a',
          color: '#e8e8e8',
          padding: 24,
          fontFamily: 'Segoe UI, sans-serif',
        }}
      >
        <h1 style={{ color: '#e87d0d', fontSize: 18, marginBottom: 12 }}>
          Интерфейс не смог отрисоваться
        </h1>
        <pre
          style={{
            whiteSpace: 'pre-wrap',
            fontSize: 12,
            background: '#0f0f0f',
            padding: 12,
            border: '1px solid #3a3a3a',
            maxHeight: '50vh',
            overflow: 'auto',
          }}
        >
          {this.state.error}
        </pre>
        <button
          type="button"
          style={{
            marginTop: 16,
            padding: '8px 14px',
            background: '#e87d0d',
            color: '#000',
            border: 0,
            cursor: 'pointer',
          }}
          onClick={() => {
            localStorage.removeItem(LAYOUT_STORAGE_KEY);
            window.location.reload();
          }}
        >
          Сбросить layout и перезагрузить
        </button>
      </div>
    );
  }
}
