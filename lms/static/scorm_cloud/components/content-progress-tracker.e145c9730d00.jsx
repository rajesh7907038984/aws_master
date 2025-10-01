import React, { useState, useEffect } from 'react';

const ContentProgressTracker = ({
    topicId,
    contentType,
    initialProgress = 0,
    csrfToken,
    onComplete
}) => {
    const [progress, setProgress] = useState(initialProgress);
    const [status, setStatus] = useState('in_progress');
    const [lastUpdated, setLastUpdated] = useState(null);
    const [score, setScore] = useState(null);
    const [error, setError] = useState(null);

    useEffect(() => {
        if (contentType === 'SCORM') {
            // Initial fetch
            fetchProgress();
            
            // Set up polling interval
            const interval = setInterval(fetchProgress, 5000);
            return () => clearInterval(interval);
        }
    }, [contentType]);

    const fetchProgress = async () => {
        try {
            const response = await fetch(`/scorm/topic/${topicId}/tracking/status/`, {
                headers: {
                    'X-CSRFToken': csrfToken
                }
            });

            if (!response.ok) {
                throw new Error('Failed to fetch progress');
            }

            const data = await response.json();
            
            setProgress(data.progress || 0);
            setStatus(data.status);
            setLastUpdated(data.last_accessed);
            setScore(data.score);

            if (data.status === 'completed' || data.status === 'passed') {
                onComplete?.();
            }
        } catch (err) {
            console.error('Error fetching progress:', err);
            setError('Failed to update progress');
        }
    };

    const getStatusColor = () => {
        switch (status) {
            case 'completed':
            case 'passed':
                return 'bg-green-500';
            case 'failed':
                return 'bg-red-500';
            case 'in_progress':
                return 'bg-blue-500';
            default:
                return 'bg-gray-500';
        }
    };

    return (
        <div className="w-full bg-gray-800 rounded-lg shadow-lg p-6">
            {error && (
                <div className="mb-4 text-sm text-red-500">
                    {error}
                </div>
            )}

            <div className="space-y-4">
                {/* Progress Bar */}
                <div>
                    <div className="flex justify-between items-center mb-2">
                        <h3 className="text-lg font-medium text-white">Progress</h3>
                        <span className="text-sm text-gray-400">
                            {progress.toFixed(0)}%
                        </span>
                    </div>
                    <div className="w-full bg-gray-700 rounded-full h-2">
                        <div
                            className={`h-2 rounded-full transition-all duration-300 ${getStatusColor()}`}
                            style={{ width: `${progress}%` }}
                        />
                    </div>
                </div>

                {/* Status Information */}
                <div className="grid grid-cols-2 gap-4">
                    <div>
                        <label className="block text-sm font-medium text-gray-400 mb-1">
                            Status
                        </label>
                        <span className="text-white capitalize">
                            {status.replace('_', ' ')}
                        </span>
                    </div>

                    {score !== null && (
                        <div>
                            <label className="block text-sm font-medium text-gray-400 mb-1">
                                Score
                            </label>
                            <span className="text-white">
                                {score.toFixed(1)}%
                            </span>
                        </div>
                    )}
                </div>

                {/* Last Updated */}
                {lastUpdated && (
                    <div className="text-xs text-gray-400">
                        Last updated: {new Date(lastUpdated).toLocaleString()}
                    </div>
                )}
            </div>
        </div>
    );
};

export default ContentProgressTracker;