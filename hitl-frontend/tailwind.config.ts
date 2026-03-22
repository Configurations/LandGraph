import type { Config } from 'tailwindcss';

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        surface: {
          primary: '#0a0a0c',
          secondary: '#111114',
          tertiary: '#1a1a1f',
          hover: '#1e1e24',
          active: '#24242c',
        },
        content: {
          primary: '#e8e8ec',
          secondary: '#9898a4',
          tertiary: '#6b6b78',
          quaternary: '#45454f',
        },
        accent: {
          blue: '#5b8def',
          green: '#3ecf8e',
          orange: '#f0a050',
          yellow: '#e8c44a',
          red: '#ef5555',
          purple: '#a78bfa',
        },
        border: { DEFAULT: '#1e1e24', strong: '#2a2a34' },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
    },
  },
  plugins: [],
} satisfies Config;
