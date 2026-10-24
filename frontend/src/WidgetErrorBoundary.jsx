import React from 'react';

export default class WidgetErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { failed: false };
  }
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch(error, info) {
    // Log a sanitized widget-level diagnostic; the rest of the workspace stays mounted.
    console.error('Datasource widget failed:', this.props.label || 'Dashboard widget', error?.message, info?.componentStack);
  }
  render() {
    if (this.state.failed) {
      return <div className="widget-error" role="alert">
        <strong>{this.props.label || 'This widget'} is temporarily unavailable</strong>
        <span>Other workspace panels remain available. Refresh to try this panel again.</span>
        <button type="button" className="button-secondary" onClick={() => this.setState({ failed: false })}>Retry widget</button>
      </div>;
    }
    return this.props.children;
  }
}
