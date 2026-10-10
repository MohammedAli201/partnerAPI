export default {
 content: ['./index.html', './src/**/*.{js,jsx}'],
 theme: { extend: {
  colors: {
   void: '#ffffff', canvas: '#ffffff', surface: '#f5f6f7', mist: '#eef0f2', line: '#e2e6ea', elevated: '#ffffff',
   espresso: '#16202f', cream: '#efe9dc', brass: '#c9a45c', stroke: '#16202f26',
   gold: { DEFAULT: '#7c2434', glow: '#96303f', dark: '#64202e' }, accent: { DEFAULT: '#7c2434', glow: '#64202e' },
   ink: { light: '#1b2432', strong: '#1b2432', dim: '#58606b', muted: '#8a94a3' },
   border: 'hsl(var(--border))',
  },
  fontFamily: { sans: ['Manrope','sans-serif'], display: ['Manrope','sans-serif'], mono: ['Space Mono','monospace'] },
  keyframes: { marquee: { '0%': { transform: 'translate3d(0,0,0)' }, '100%': { transform: 'translate3d(-50%,0,0)' } } },
  animation: { 'spin-slower': 'spin 40s linear infinite', marquee: 'marquee 50s linear infinite' },
 } },
};
