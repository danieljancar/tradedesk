import { Component, type ReactNode } from "react";
import { Button } from "@/components/ui/button";

/** Keeps one broken page from blanking the whole dashboard. */
type Props = { children: ReactNode; reset?: unknown };
type State = { error: Error | null; reset?: unknown };

export class Crash extends Component<Props, State> {
  state: State = { error: null, reset: this.props.reset };
  static getDerivedStateFromError(error: Error) { return { error }; }
  // a new page clears the error
  static getDerivedStateFromProps(props: Props, state: State) {
    return props.reset !== state.reset ? { error: null, reset: props.reset } : null;
  }
  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="mx-auto max-w-md space-y-3 p-8 text-center">
        <p className="font-medium">This page hit an error.</p>
        <p className="font-mono text-xs break-words text-dim">{this.state.error.message}</p>
        <Button size="sm" onClick={() => this.setState({ error: null })}>Try again</Button>
      </div>
    );
  }
}
