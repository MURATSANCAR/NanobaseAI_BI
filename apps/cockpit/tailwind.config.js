/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        page: '#F8F1EC',
        rail: '#F3E8E1',
        card: '#FFFFFF',
        line: '#EAD9CE',
        ink: { DEFAULT: '#2A1912', muted: '#7C6259', faint: '#B39A90' },
        brand: { DEFAULT: '#B34630', deep: '#8F3521', soft: '#F4DCD3', accent: '#D64B2F' },
        ok: '#3C7D4E',
        warn: '#C98A1E',
      },
      fontFamily: {
        display: ['Fraunces', 'Georgia', 'serif'],
        sans: ['Manrope', 'system-ui', 'sans-serif'],
      },
      boxShadow: {
        card: '0 1px 0 rgba(42,25,18,0.04), 0 6px 20px -12px rgba(42,25,18,0.18)',
      },
      borderRadius: { xl2: '1.25rem' },
    },
  },
  plugins: [],
};
