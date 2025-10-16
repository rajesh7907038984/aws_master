/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './templates/**/*.html',
    './**/templates/**/*.html',
    './static/**/*.js',
    './**/static/**/*.js',
  ],
  theme: {
    extend: {
      colors: {
        'primary': '#1C2260',
        'primary-hover': '#232a75',
        'accent': '#02f711',
        'link': '#2F80ED',
      },
      spacing: {
        '18': '4.5rem',
        '88': '22rem',
      },
      width: {
        'calc-200': 'calc(100% - 200px)',
        'calc-16rem': 'calc(100% - 16rem)',
        'calc-36rem': 'calc(100% - 36rem)',
      },
      margin: {
        'calc-16rem': 'calc(100% - 16rem)',
      }
    },
  },
  plugins: [],
  safelist: [
    'bg-primary',
    'bg-primary-hover',
    'border-accent',
    'text-link',
    'w-calc-200',
    'w-calc-16rem',
    'w-calc-36rem',
    'md:w-calc-200',
    'md:w-calc-16rem',
    'md:w-calc-36rem',
  ]
}
