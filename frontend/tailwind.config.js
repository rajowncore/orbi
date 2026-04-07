/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['DM Sans', 'sans-serif'],
        mono: ['DM Mono', 'monospace'],
      },
      colors: {
        brand: {
          50:  '#EEF2FF',
          100: '#E0E7FF',
          500: '#1B4FD8',
          600: '#1339A8',
          700: '#0F2D8A',
        },
        sidebar: '#0F172A',
      }
    }
  },
  plugins: []
}
