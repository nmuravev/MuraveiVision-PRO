export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        dv: {
          bg: 'var(--dv-bg)',
          deep: 'var(--dv-bg-deep)',
          panel: 'var(--dv-panel)',
          header: 'var(--dv-panel-header)',
          border: 'var(--dv-border)',
          soft: 'var(--dv-border-soft)',
          text: 'var(--dv-text)',
          muted: 'var(--dv-text-muted)',
          accent: 'var(--dv-accent)',
          hot: 'var(--dv-accent-hot)',
          playhead: 'var(--dv-playhead)',
          selection: 'var(--dv-selection)',
          surface: 'var(--dv-surface-2)',
          hover: 'var(--dv-hover)',
          danger: 'var(--dv-danger)',
          success: 'var(--dv-success)',
        },
      },
      boxShadow: {
        'dv-focus': '0 0 0 2px var(--dv-focus-ring)',
      },
      transitionDuration: {
        modal: '180ms',
      },
    },
  },
  plugins: [],
};
