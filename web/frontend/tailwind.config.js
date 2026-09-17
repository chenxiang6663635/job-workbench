/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        /* Shadcn 语义 token。深色为默认，浅色主题未来在 .dark 之外再加一组变量即可。
           注意 accent 语义（hover 背景）此处不定义——由 secondary/muted 承担，主色统一走 primary */
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
        /* 中性叠层：卡片高光 / 骨架微光（配 /5、/10 等透明度使用）与弹窗遮罩 */
        highlight: "hsl(var(--highlight))",
        scrim: "hsl(var(--scrim))",
        border: {
          DEFAULT: "hsl(var(--border))",
          strong: "hsl(var(--border-strong))",
        },
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        /* 层级表面（批 4 三件套）：凹面 0 / 卡片 1 / 抬升 2 / 浮层 3 */
        surface: {
          0: "hsl(var(--elevation-0-surface))",
          1: "hsl(var(--elevation-1-surface))",
          2: "hsl(var(--elevation-2-surface))",
          3: "hsl(var(--elevation-3-surface))",
        },
      },
      /* 视觉升级：阴影、渐变与动画。全部走 CSS 变量，零运行时开销 */
      boxShadow: {
        card: "var(--shadow-card)",
        elevated: "var(--shadow-elevated)",
        "elev-1": "var(--elevation-1-shadow)",
        "elev-2": "var(--elevation-2-shadow)",
        "elev-3": "var(--elevation-3-shadow)",
        "glow-primary": "0 0 0 1px hsl(var(--glow-primary) / 0.35), 0 6px 20px -6px hsl(var(--glow-primary) / 0.5)",
      },
      backgroundImage: {
        "card-gradient": "var(--card-gradient)",
        "hero-glow": "var(--hero-glow)",
      },
      keyframes: {
        shimmer: {
          "100%": { transform: "translateX(100%)" },
        },
        "fade-in-up": {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        shimmer: "shimmer 1.6s infinite",
        "fade-in-up": "fade-in-up 0.25s cubic-bezier(0.16, 1, 0.3, 1)",
      },
      transitionTimingFunction: {
        /* expo-out（批 4 统一）：颜色 150ms / 位移与阴影 250ms，位移 1–2px 绝不 scale。
           2026-09-17：改引用 index.css 的 --ease-premium——消除"变量一处、字面量
           又一处"的双写（此前 --ease-premium 是死变量） */
        premium: "var(--ease-premium)",
      },
      /* 动效时长三档（2026-09-17 接入）：--duration-* 此前定义了但零消费者；
         新代码用 duration-fast/base/slow，历史数值类（150/200/300）保持不动 */
      transitionDuration: {
        fast: "var(--duration-fast)",
        base: "var(--duration-base)",
        slow: "var(--duration-slow)",
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      fontFamily: {
        /* 字体体系（批 4 4g → 2026-09-17）：栈本体在 index.css 的 CSS 变量里——
           界面字体 12 款（拉丁槽 --font-latin 组合中文系统栈）、等宽 6 款
           （--font-mono 独立槽）；设置页切换只改根属性，不重建、不改配置 */
        sans: ["var(--font-sans-stack)", "sans-serif"],
        mono: ["var(--font-mono-stack)", "monospace"],
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
};
