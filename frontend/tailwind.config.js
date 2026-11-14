/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: { extend: { colors: { field: '#285d42', ink: '#1c3025', mist: '#f5f7f1', lime: '#d9ef8b' }, fontFamily: { sans: ['DM Sans', 'ui-sans-serif', 'system-ui'], display: ['Manrope', 'DM Sans', 'ui-sans-serif', 'system-ui'] } } },
  plugins: [],
}
