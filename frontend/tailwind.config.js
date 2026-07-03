/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        surface: {
          DEFAULT: '#0c0c0d',
          secondary: '#141415',
          tertiary: '#1c1c1e',
          elevated: '#242426',
        },
        border: {
          DEFAULT: '#2a2a2d',
          subtle: '#1c1c1e',
          strong: '#3a3a3e',
        },
        accent: {
          DEFAULT: '#6366f1',
          light: '#818cf8',
          dark: '#4f46e5',
        },
        muted: '#888892',
        success: '#22c55e',
        warning: '#eab308',
        danger: '#ef4444',
        info: '#3b82f6',
      },
    },
  },
  plugins: [],
};
