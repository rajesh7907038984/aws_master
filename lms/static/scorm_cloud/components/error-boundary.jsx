import React from 'react';

class ErrorBoundary extends React.Component {
    constructor(props) {
        super(props);
        this.state = { hasError: false, error: null };
    }

    static getDerivedStateFromError(error) {
        return { hasError: true, error };
    }

    componentDidCatch(error, errorInfo) {
        console.error('SCORM Component Error:', error, errorInfo);
        
        // Send error to your error tracking service if needed
        if (window.onerror) {
            window.onerror('SCORM Component Error', window.location.href, 0, 0, error);
        }
    }

    render() {
        if (this.state.hasError) {
            return (
                <div className="bg-red-500 bg-opacity-10 border border-red-500 rounded-lg p-4 m-4">
                    <h2 className="text-lg font-semibold text-red-500 mb-2">
                        Something went wrong
                    </h2>
                    <p className="text-gray-200 mb-4">
                        There was an error loading the content. Please try refreshing the page.
                    </p>
                    <button
                        onClick={() => window.location.reload()}
                        className="px-4 py-2 bg-red-500 text-white rounded hover:bg-red-600 transition-colors"
                    >
                        Refresh Page
                    </button>
                </div>
            );
        }

        return this.props.children;
    }
}

export default ErrorBoundary;