/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        authentik: {
          orange: {
            DEFAULT: '#fd7e14',
            light: '#ff922b',
            dark: '#ea580c',
            50: '#fff7ed',
            100: '#ffedd5',
            200: '#fed7aa',
            300: '#fdba74',
            400: '#fb923c',
            500: '#f97316',
            600: '#ea580c',
            700: '#c2410c',
          },
          blue: {
            DEFAULT: '#0066cc',
            light: '#0284c7',
            dark: '#1d4ed8',
            500: '#0284c7',
            600: '#2563eb',
          },
          navy: {
            950: '#0b0f17',
            900: '#111827',
            850: '#16202e',
            800: '#1e2c3f',
            750: '#25354b',
            700: '#2c3f58',
            600: '#3e5675',
          }
        },
      }
    },
  },
  plugins: [],
}
