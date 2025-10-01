import React, { useState, useEffect, useRef } from 'react';
import ErrorBoundary from './error-boundary';
import './scorm-player.css';

const SCORMPlayer = ({
    launchUrl,
    topicId,
    courseId,
    csrfToken,
    initialStatus = {},
    onExit
}) => {
    const iframeRef = useRef(null);
    const [status, setStatus] = useState(initialStatus);
    const [error, setError] = useState(null);
    const [loading, setLoading] = useState(true);
    const [initialized, setInitialized] = useState(false);

    useEffect(() => {
        const handleMessage = (event) => {
            try {
                // Handle SCORM communication messages
                if (event.data && typeof event.data === 'object') {
                    if (event.data.command === 'scormContentLoaded') {
                        setLoading(false);
                        setInitialized(true);
                    } else if (event.data.command === 'saveProgress') {
                        saveProgress(event.data.progress);
                    } else if (event.data.command === 'contentCompleted') {
                        handleCompletion(event.data);
                    }
                }
            } catch (err) {
                console.error('Error handling message:', err);
                setError('Error communicating with content');
            }
        };

        window.addEventListener('message', handleMessage);
        return () => window.removeEventListener('message', handleMessage);
    }, []);

    const saveProgress = async (progressData) => {
        try {
            const response = await fetch(`/courses/topic/${topicId}/scorm-tracking/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken
                },
                body: JSON.stringify({
                    status: progressData.status,
                    score: progressData.score,
                    progress: progressData.progress,
                    timeSpent: progressData.timeSpent
                })
            });

            if (!response.ok) {
                throw new Error('Failed to save progress');
            }

            const data = await response.json();
            setStatus(data);

            // Handle completion if needed
            if (data.completed && data.next_topic_url) {
                window.location.href = data.next_topic_url;
            }
        } catch (err) {
            console.error('Error saving progress:', err);
            setError('Failed to save progress');
        }
    };

    const handleCompletion = async (completionData) => {
        try {
            await saveProgress({
                ...completionData,
                status: 'completed'
            });

            if (onExit) {
                onExit(completionData);
            }
        } catch (err) {
            console.error('Error handling completion:', err);
            setError('Failed to record completion');
        }
    };

    // Auto-save progress periodically
    useEffect(() => {
        if (!initialized || !status.progress) return;

        const interval = setInterval(() => {
            saveProgress(status);
        }, 30000); // Save every 30 seconds

        return () => clearInterval(interval);
    }, [initialized, status]);

    return (
        <div className="w-full h-[320px] bg-gray-800 rounded-lg shadow-lg overflow-hidden">
            {error && (
                <div className="bg-red-500 text-white p-4 text-center">
                    {error}
                </div>
            )}
            
            {loading && (
                <div className="flex items-center justify-center h-full">
                    <div className="animate-spin rounded-full h-32 w-32 border-t-2 border-b-2 border-blue-500"></div>
                </div>
            )}

            <iframe
                ref={iframeRef}
                src={launchUrl}
                className="w-full h-full border-0"
                style={{ display: loading ? 'none' : 'block' }}
                onLoad={() => setLoading(false)}
                allow="accelerometer; autoplay; encrypted-media; gyroscope; picture-in-picture"
                allowFullScreen
            />
        </div>
    );
};

export default SCORMPlayer;