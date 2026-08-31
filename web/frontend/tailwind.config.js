/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // 深色主题主色：冷青蓝，贴合"数据看板"气质
        ink: {
          950: "#0a0f1a",
          900: "#0e1526",
          850: "#131c30",
          800: "#1a2438",
          700: "#24314d",
          600: "#32426a",
        },
        accent: {
          DEFAULT: "#38bdf8",
          soft: "#7dd3fc",
          dim: "#0ea5e9",
        },
        good: "#34d399",
        warn: "#fbbf24",
        bad: "#f87171",
      },
      fontFamily: {
        sans: [
          "Inter",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Microsoft YaHei",
          "sans-serif",
        ],
        mono: ["JetBrains Mono", "Consolas", "monospace"],
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
};
