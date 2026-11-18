import { Component, type ErrorInfo, type ReactNode } from 'react';

/** Small reusable boundary so one bad panel never whites the page. */
export default class ErrorBoundary extends Component<
  { fallback: ReactNode; children: ReactNode; onCatch?: (error: unknown, info: ErrorInfo) => void },
  { hasError: boolean; message: string | null }
> {
  state = { hasError: false, message: null as string | null };

  static getDerivedStateFromError(error: unknown) {
    return { hasError: true, message: error instanceof Error ? error.message : String(error) };
  }

  componentDidCatch(error: unknown, info: ErrorInfo) {
    this.props.onCatch?.(error, info);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div role="alert" className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-200">
          <p className="font-semibold">A panel failed to render.</p>
          {this.state.message && <p className="mt-1 font-mono text-xs opacity-80">{this.state.message}</p>}
          <div className="mt-2">{this.props.fallback}</div>
        </div>
      );
    }
    return this.props.children;
  }
}
