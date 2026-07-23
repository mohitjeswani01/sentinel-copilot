import React, { ReactNode } from 'react';
import { AlertCircle, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error?: Error;
}

export class ErrorBoundary extends React.Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error) {
    console.error('Error caught by boundary:', error);
  }

  handleReset = () => {
    this.setState({ hasError: false });
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="space-y-6 p-6">
          <div className="glass-panel glow-border rounded-xl p-6 border-destructive/50">
            <div className="flex items-start gap-4">
              <AlertCircle className="h-6 w-6 text-destructive flex-shrink-0 mt-1" />
              <div className="space-y-3 flex-1">
                <h2 className="text-lg font-semibold text-destructive">Component Error</h2>
                <p className="text-muted-foreground text-sm">
                  An error occurred while rendering this component.
                </p>
                {this.state.error && (
                  <details className="text-xs font-mono text-muted-foreground bg-secondary/50 p-3 rounded mt-3 max-h-24 overflow-auto">
                    <summary className="cursor-pointer font-semibold mb-2">Error Details</summary>
                    <pre className="whitespace-pre-wrap break-words">{this.state.error.message}</pre>
                  </details>
                )}
                <div className="flex gap-2 mt-4">
                  <Button
                    onClick={this.handleReset}
                    size="sm"
                    variant="outline"
                    className="gap-2"
                  >
                    <RefreshCw className="h-4 w-4" />
                    Try Again
                  </Button>
                  <Button
                    onClick={() => window.location.reload()}
                    size="sm"
                    variant="outline"
                  >
                    Reload Page
                  </Button>
                </div>
              </div>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
