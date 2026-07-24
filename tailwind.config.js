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
        // Brand palette for Vintazk 360.
        brand: {
          DEFAULT: '#4f46e5',
          dark: '#4338ca',
          light: '#6366f1',
        },
      },
    },
  },
  plugins: [],
};
