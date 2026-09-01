import { Component, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/**
 * 组件崩溃兜底。此前任何页面抛出运行时异常会卸载整棵组件树，
 * 深色主题下只剩纯背景——用户看到的就是"黑屏"，且无任何线索。
 * 有此边界后，崩溃会显示具体错误与恢复按钮。
 */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  render() {
    if (this.state.error) {
      return (
        <div className="rounded-2xl border border-bad/40 bg-bad/10 p-6">
          <p className="text-sm font-semibold text-bad">页面渲染出错</p>
          <p className="mt-2 font-mono text-xs leading-relaxed text-slate-300">
            {this.state.error.message}
          </p>
          <div className="mt-4 flex gap-2">
            <button
              onClick={() => this.setState({ error: null })}
              className="cursor-pointer rounded-lg bg-accent px-3 py-1.5 text-xs font-medium text-ink-950 transition-colors hover:bg-accent-soft"
            >
              重试
            </button>
            <button
              onClick={() => window.location.reload()}
              className="cursor-pointer rounded-lg border border-white/15 px-3 py-1.5 text-xs text-slate-300 transition-colors hover:bg-white/5"
            >
              强制刷新（清除缓存）
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
