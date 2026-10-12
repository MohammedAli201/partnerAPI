import { HUBAAL_COLORS } from './src/palette.js';
export default {
 content: ['./index.html', './src/**/*.{js,jsx}'],
 theme: { extend: {
  colors: {
   brand: HUBAAL_COLORS,
   void: HUBAAL_COLORS.ivory, canvas: HUBAAL_COLORS.ivory, surface: '#EDF4EF', mist: HUBAAL_COLORS.mint,
   line: { DEFAULT: '#D5E1DB', strong: '#A8C4BA' }, elevated: '#ffffff',
   espresso: HUBAAL_COLORS.ink, cream: HUBAAL_COLORS.ivory, brass: HUBAAL_COLORS.mint, stroke: '#142D3026',
   gold: { DEFAULT: HUBAAL_COLORS.teal, glow: '#0B6E73', dark: '#064C50' }, accent: { DEFAULT: HUBAAL_COLORS.teal, glow: '#064C50' },
   ink: { DEFAULT: HUBAAL_COLORS.ink, 2: '#2D4B46', 3: '#48645F', 4: '#58716C', light: HUBAAL_COLORS.ink, strong: HUBAAL_COLORS.ink, dim: '#48645F', muted: '#58716C' },
   teal: { 50: '#EFF8F3', 100: '#E7F5EE', 200: HUBAAL_COLORS.mint, 300: HUBAAL_COLORS.mint, 400: '#0B6E73', 500: HUBAAL_COLORS.teal, 600: HUBAAL_COLORS.teal, 700: HUBAAL_COLORS.teal, 800: '#064C50', 900: HUBAAL_COLORS.ink },
   cobalt: { 50: '#EFF8F3', 100: '#E7F5EE', 200: HUBAAL_COLORS.mint, 300: HUBAAL_COLORS.mint, 500: HUBAAL_COLORS.teal, 600: HUBAAL_COLORS.teal, 700: HUBAAL_COLORS.teal },
   slate: { 50: HUBAAL_COLORS.ivory, 100: '#E7F5EE', 200: HUBAAL_COLORS.mint, 300: '#BDD8CE', 400: '#A8C4BA', 500: '#9BB9AE', 600: '#8CAEA1', 700: '#48645F', 800: '#2D4B46', 900: HUBAAL_COLORS.ink },
   border: 'hsl(var(--border))',
  },
  fontFamily: { sans: ['Inter','sans-serif'], display: ['League Spartan','sans-serif'], mono: ['Roboto Mono','monospace'] },
  boxShadow: { soft: '0 2px 12px rgba(20,45,48,.05)', lift: '0 16px 36px -12px rgba(20,45,48,.14)', glow: '0 0 30px rgba(7,94,99,.18)' },
  keyframes: { dash: { to: { strokeDashoffset: '-32' } }, float: { '0%,100%': { transform: 'translateY(0)' }, '50%': { transform: 'translateY(-6px)' } }, pulseRing: { '0%,100%': { opacity: '.5', transform: 'scale(1)' }, '50%': { opacity: '1', transform: 'scale(1.15)' } }, marquee: { '0%': { transform: 'translate3d(0,0,0)' }, '100%': { transform: 'translate3d(-50%,0,0)' } } },
  animation: { float: 'float 6s ease-in-out infinite', pulseRing: 'pulseRing 3s ease-in-out infinite', 'spin-slower': 'spin 40s linear infinite', marquee: 'marquee 50s linear infinite' },
 } },
};
