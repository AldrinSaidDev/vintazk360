/** @type {import('tailwindcss').Config} */
module.exports = {
  // Scan every template across the project and all apps so used classes are
  // included in the compiled output.
  content: [
    './templates/**/*.html',
    './apps/**/templates/**/*.html',
  ],
  theme: {
    extend: {
      fontFamily: {
        // Default body font — Montserrat (vendored locally). Overrides Tailwind's
        // default `sans` stack so the whole app uses it without extra classes.
        sans: ['"Montserrat"', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        // Headings also use Montserrat — the app is single-typeface. The
        // `font-heading` class is kept (and used across the templates) purely as
        // a semantic hook, so a display face can be swapped back in here alone.
        heading: ['"Montserrat"', 'ui-sans-serif', 'system-ui', 'sans-serif'],
      },
      colors: {
        // Vintazk 360 brand palette.
        ink: '#040404',        // near-black — primary text
        brand: {
          DEFAULT: '#4F3D67',  // deep purple — primary
          dark: '#3d2f51',
          light: '#6a5486',
        },
        accent: {
          DEFAULT: '#B27FA0',  // mauve — secondary accent
          light: '#c799b6',
        },
        blush: '#DFADB6',      // dusty pink — soft highlight
        surface: '#202427',    // dark slate — sidebar / dark surfaces

        // Semantic status colors — muted to sit harmoniously with the brand
        // palette while still reading clearly as good / warning / bad.
        // On-track deliberately reuses the brand purple to stay on-brand.
        status: {
          good: '#4F3D67',   // = brand — on track
          warn: '#D9A441',   // muted amber — at risk
          bad:  '#C25B6E',   // muted rose — below target
        },
      },
      keyframes: {
        'fade-up': {
          '0%': { opacity: '0', transform: 'translateY(16px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'fade-in': {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        float: {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-14px)' },
        },
        'float-slow': {
          '0%, 100%': { transform: 'translateY(0) rotate(12deg)' },
          '50%': { transform: 'translateY(-18px) rotate(12deg)' },
        },
        'orbit-spin': {
          from: { transform: 'rotate(0deg)' },
          to: { transform: 'rotate(360deg)' },
        },
        'orbit-counter': {
          from: { transform: 'rotate(0deg)' },
          to: { transform: 'rotate(-360deg)' },
        },
        // Pulsing halo behind the CEO orb.
        halo: {
          '0%, 100%': { transform: 'scale(1)', opacity: '0.5' },
          '50%': { transform: 'scale(1.35)', opacity: '0' },
        },
        // Gentle glow pulse on department nodes.
        'node-pulse': {
          '0%, 100%': { transform: 'scale(1)', opacity: '1' },
          '50%': { transform: 'scale(1.25)', opacity: '0.75' },
        },
        // A pulse of light travelling along a spoke toward the CEO center
        // (an SVG stroke dash sweeping from the department into the hub).
        signalflow: {
          from: { 'stroke-dashoffset': '136' },
          to: { 'stroke-dashoffset': '0' },
        },
        // Expanding ring that radiates out from the CEO hub.
        'ring-ping': {
          '0%': { transform: 'scale(0.8)', opacity: '0.6' },
          '100%': { transform: 'scale(1.9)', opacity: '0' },
        },
        // Organic drifting for aurora mesh blobs (position + scale morph).
        'drift-a': {
          '0%, 100%': { transform: 'translate(0, 0) scale(1)' },
          '33%':  { transform: 'translate(6%, -8%) scale(1.12)' },
          '66%':  { transform: 'translate(-5%, 5%) scale(0.92)' },
        },
        'drift-b': {
          '0%, 100%': { transform: 'translate(0, 0) scale(1)' },
          '50%':  { transform: 'translate(-8%, -6%) scale(1.15)' },
        },
        // A slow conic sweep, like a radar/searchlight pass.
        sweep: {
          from: { transform: 'rotate(0deg)' },
          to: { transform: 'rotate(360deg)' },
        },
        // Particles rising and fading.
        rise: {
          '0%':   { transform: 'translateY(0) scale(1)', opacity: '0' },
          '10%':  { opacity: '0.9' },
          '90%':  { opacity: '0.4' },
          '100%': { transform: 'translateY(-160px) scale(0.4)', opacity: '0' },
        },
        // Stars twinkling (opacity + tiny scale).
        twinkle: {
          '0%, 100%': { opacity: '0.25', transform: 'scale(0.85)' },
          '50%':      { opacity: '1', transform: 'scale(1)' },
        },
        // The North Star's steady breathing glow.
        'star-glow': {
          '0%, 100%': { opacity: '0.7', transform: 'translate(-50%, -50%) scale(1)' },
          '50%':      { opacity: '1', transform: 'translate(-50%, -50%) scale(1.15)' },
        },
        // Slow rotation of the star's light rays.
        'ray-spin': {
          from: { transform: 'translate(-50%, -50%) rotate(0deg)' },
          to:   { transform: 'translate(-50%, -50%) rotate(360deg)' },
        },
        // A shooting star streaking across.
        shoot: {
          '0%':   { transform: 'translate(0,0) rotate(35deg) scaleX(0)', opacity: '0' },
          '8%':   { opacity: '1', transform: 'translate(0,0) rotate(35deg) scaleX(1)' },
          '22%':  { transform: 'translate(240px, 168px) rotate(35deg) scaleX(1)', opacity: '0' },
          '100%': { opacity: '0' },
        },
      },
      animation: {
        'fade-up': 'fade-up 0.6s ease-out both',
        'fade-in': 'fade-in 0.8s ease-out both',
        float: 'float 6s ease-in-out infinite',
        'float-slow': 'float-slow 8s ease-in-out infinite',
        'orbit-spin': 'orbit-spin 40s linear infinite',
        'orbit-counter': 'orbit-counter 40s linear infinite',
        halo: 'halo 3s ease-in-out infinite',
        'node-pulse': 'node-pulse 2.8s ease-in-out infinite',
        signalflow: 'signalflow 2.6s linear infinite',
        'ring-ping': 'ring-ping 3s ease-out infinite',
        'ring-ping-slow': 'ring-ping 3s ease-out infinite 1.5s',
        'drift-a': 'drift-a 18s ease-in-out infinite',
        'drift-b': 'drift-b 22s ease-in-out infinite',
        sweep: 'sweep 24s linear infinite',
        rise: 'rise 7s linear infinite',
        twinkle: 'twinkle 4s ease-in-out infinite',
        'star-glow': 'star-glow 4s ease-in-out infinite',
        'ray-spin': 'ray-spin 60s linear infinite',
        shoot: 'shoot 9s ease-in infinite',
      },
    },
  },
  plugins: [],
};
