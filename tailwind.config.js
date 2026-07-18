/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      borderRadius: {
        ui: '1rem',
        'ui-lg': '1.25rem',
        'ui-xl': '1.5rem',
      },
      spacing: {
        shell: '1.5rem',
        'nav-width': '16rem',
      },
      colors: {
        surface: {
          DEFAULT: 'rgba(255, 255, 255, 0.55)',
          raised: '#f5f3ff',
          overlay: 'rgba(255, 255, 255, 0.4)',
          border: 'rgba(255, 255, 255, 0.65)',
          muted: '#e2e8f0',
        },
        accent: {
          DEFAULT: '#7c3aed',
          muted: '#8b5cf6',
          dim: '#6d28d9',
          glow: '#a78bfa',
        },
        ai: {
          from: '#7c3aed',
          via: '#6366f1',
          to: '#0ea5e9',
        },
        status: {
          ok: '#059669',
          warn: '#d97706',
          fail: '#dc2626',
          run: '#7c3aed',
        },
      },
      fontFamily: {
        sans: ['"DM Sans"', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
      },
      boxShadow: {
        card: '0 4px 24px -6px rgba(124, 58, 237, 0.12)',
        glow: '0 8px 32px -8px rgba(124, 58, 237, 0.25)',
        'glow-lg': '0 12px 40px -10px rgba(124, 58, 237, 0.35)',
        'ai-ring': '0 0 0 3px rgba(139, 92, 246, 0.2)',
      },
      animation: {
        'fade-in': 'fadeIn 0.45s ease-out both',
        'slide-up': 'slideUp 0.55s ease-out both',
        'slide-down': 'slideDown 0.45s ease-out both',
        'slide-in-left': 'slideInLeft 0.4s ease-out both',
        'slide-in-right': 'slideInRight 0.4s ease-out both',
        'scale-in': 'scaleIn 0.35s ease-out both',
        float: 'float 4s ease-in-out infinite',
        'float-slow': 'float 7s ease-in-out infinite',
        'float-delayed': 'float 5s ease-in-out 1s infinite',
        'spin-slow': 'spin 12s linear infinite',
        'orbit': 'orbit 14s ease-in-out infinite',
        'orbit-reverse': 'orbitReverse 16s ease-in-out infinite',
        'sparkle': 'sparkle 3s ease-in-out infinite',
        'aurora': 'aurora 20s ease-in-out infinite',
        'aurora-reverse': 'auroraReverse 24s ease-in-out infinite',
        'orb-pulse': 'orbPulse 2.5s ease-in-out infinite',
        'neural-dash': 'neuralDash 4s linear infinite',
        'hero-glow': 'heroGlow 3s ease-in-out infinite',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { opacity: '0', transform: 'translateY(16px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        slideDown: {
          '0%': { opacity: '0', transform: 'translateY(-8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        slideInLeft: {
          '0%': { opacity: '0', transform: 'translateX(-12px)' },
          '100%': { opacity: '1', transform: 'translateX(0)' },
        },
        slideInRight: {
          '0%': { opacity: '0', transform: 'translateX(12px)' },
          '100%': { opacity: '1', transform: 'translateX(0)' },
        },
        scaleIn: {
          '0%': { opacity: '0', transform: 'scale(0.9)' },
          '100%': { opacity: '1', transform: 'scale(1)' },
        },
        float: {
          '0%, 100%': { transform: 'translateY(0) translateX(0)' },
          '33%': { transform: 'translateY(-8px) translateX(4px)' },
          '66%': { transform: 'translateY(4px) translateX(-4px)' },
        },
        drift: {
          '0%, 100%': { transform: 'translate(0, 0) scale(1)' },
          '25%': { transform: 'translate(30px, -20px) scale(1.05)' },
          '50%': { transform: 'translate(-20px, 15px) scale(0.95)' },
          '75%': { transform: 'translate(15px, 25px) scale(1.02)' },
        },
        driftReverse: {
          '0%, 100%': { transform: 'translate(0, 0) scale(1)' },
          '33%': { transform: 'translate(-25px, 20px) scale(1.08)' },
          '66%': { transform: 'translate(20px, -15px) scale(0.92)' },
        },
        orbit: {
          '0%, 100%': { transform: 'translate(0, 0) rotate(0deg)' },
          '25%': { transform: 'translate(12px, -18px) rotate(6deg)' },
          '50%': { transform: 'translate(-8px, -28px) rotate(-4deg)' },
          '75%': { transform: 'translate(-14px, -10px) rotate(3deg)' },
        },
        orbitReverse: {
          '0%, 100%': { transform: 'translate(0, 0) rotate(0deg)' },
          '25%': { transform: 'translate(-10px, 16px) rotate(-5deg)' },
          '50%': { transform: 'translate(14px, 22px) rotate(4deg)' },
          '75%': { transform: 'translate(18px, -8px) rotate(-3deg)' },
        },
        sparkle: {
          '0%, 100%': { opacity: '0', transform: 'scale(0.4)' },
          '50%': { opacity: '1', transform: 'scale(1)' },
        },
        aurora: {
          '0%, 100%': { transform: 'translate(0, 0) scale(1)' },
          '33%': { transform: 'translate(40px, -30px) scale(1.1)' },
          '66%': { transform: 'translate(-30px, 20px) scale(0.95)' },
        },
        auroraReverse: {
          '0%, 100%': { transform: 'translate(0, 0) scale(1)' },
          '50%': { transform: 'translate(-35px, 25px) scale(1.08)' },
        },
        orbPulse: {
          '0%, 100%': { opacity: '0.35', transform: 'scale(1)' },
          '50%': { opacity: '0.7', transform: 'scale(1.15)' },
        },
        neuralDash: {
          '0%': { strokeDashoffset: '120' },
          '100%': { strokeDashoffset: '0' },
        },
        heroGlow: {
          '0%, 100%': { boxShadow: '0 8px 32px -8px rgba(124, 58, 237, 0.35)' },
          '50%': { boxShadow: '0 12px 48px -6px rgba(14, 165, 233, 0.45)' },
        },
      },
    },
  },
  plugins: [],
};
