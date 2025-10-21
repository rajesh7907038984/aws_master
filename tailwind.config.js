/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./templates/**/*.html",
    "./**/templates/**/*.html",
    "./static/**/*.js",
    "./**/static/**/*.js",
    "./**/templates/**/*.html",
    "./**/static/**/*.css",
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          50: '#EBF3FE',
          100: '#7EB6F7',
          200: '#4262FF',
          300: '#2F80ED',
          400: '#050c50',
          500: '#050c50',
          600: '#050c50',
          700: '#02071e',
          800: '#02071e',
          900: '#02071e',
        },
        secondary: {
          50: '#f8fafc',
          100: '#f1f5f9',
          200: '#e2e8f0',
          300: '#cbd5e1',
          400: '#94a3b8',
          500: '#64748b',
          600: '#475569',
          700: '#334155',
          800: '#1e293b',
          900: '#0f172a',
        }
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
      spacing: {
        '18': '4.5rem',
        '88': '22rem',
      }
    },
  },
  plugins: [],
}
