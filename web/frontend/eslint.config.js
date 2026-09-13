import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'

export default tseslint.config(
  { ignores: ['dist'] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
    },
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      // 变量/常量在声明前使用 = 运行期 TDZ 崩溃（`Cannot access 'status' before
      // initialization`）。tsc 与默认 lint 都不查这个，只有真正打开那一页才会炸
      // ——2026-09-12 的冒烟在岗位池页实测（Jobs.tsx 把 statusLabelKey 放在了
      // status 声明之前）。函数声明不受影响：提升是合法的。
      '@typescript-eslint/no-use-before-define': [
        'error',
        {
          functions: false,
          classes: false,
          variables: true,
          enums: true,
          typedefs: false,
          ignoreTypeReferences: true,
        },
      ],
      'react-refresh/only-export-components': [
        'warn',
        { allowConstantExport: true },
      ],
    },
  },
  {
    // shadcn/ui 产物文件按上游惯例同时导出组件与 variants 生成器（cva 的
    // 类名工厂，本来就不是组件）。拆文件只会偏离上游模板、给后续升级添堵，
    // 这里对齐惯例整体豁免；业务组件文件的同类问题则逐个挪走（badgeVariants.ts）
    files: ['src/components/ui/**/*.{ts,tsx}'],
    rules: {
      'react-refresh/only-export-components': 'off',
    },
  },
)
