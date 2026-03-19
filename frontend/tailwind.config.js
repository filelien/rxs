/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        display: ['Syne', 'sans-serif'],
        mono: ['DM Mono', 'monospace'],
        sans: ['DM Sans', 'sans-serif'],
      },
      colors: {
        raxus: {
          bg0: '#05080f',
          bg1: '#080d18',
          bg2: '#0d1425',
          bg3: '#111b30',
          border: '#1a2640',
          blue: '#3b8ef3',
          teal: '#00d4aa',
          purple: '#8b5cf6',
        },
      },
    },
  },
  plugins: [],
}
