/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        /* Shadcn 语义 token。深色为默认，浅色主题未来在 .dark 之外再加一组变量即可。
           注意 accent 语义（hover 背景）此处不定义——accent 已被占用为冷青蓝主色 */
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        success: "hsl(var(--success))",
        warning: "hsl(var(--warning))",
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
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
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
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
