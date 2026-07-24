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
      },
    },
  },
  plugins: [],
};
