import React, { useState, useEffect, useRef } from 'react';
import ErrorBoundary from './error-boundary';
import './scorm-player.css';

const SCORMPlayer = ({
    launchUrl,
    topicId,
    courseId,
    csrfToken,
    initialStatus = {},
    onExit,
    debug = false
}) => {
    const iframeRef = useRef(null);
    const [status, setStatus] = useState(initialStatus);
    const [error, setError] = useState(null);
    const [loading, setLoading] = useState(true);
    const [initialized, setInitialized] = useState(false);
    const [pendingSaves, setPendingSaves] = useState([]);
    const [saveInProgress, setSaveInProgress] = useState(false);

    // Debug logging function
    const logDebug = (message, data) => {
        if (debug) {
            console.log(`[SCORM Debug] ${message}`, data || '');
        }
    };

    useEffect(() => {
        const handleMessage = (event) => {
            try {
                // Handle SCORM communication messages
                if (event.data && typeof event.data === 'object') {
                    if (event.data.command === 'scormContentLoaded') {
                        setLoading(false);
                        setInitialized(true);
                        logDebug('SCORM content loaded and initialized');
                    } else if (event.data.command === 'saveProgress') {
                        logDebug('Received saveProgress message', event.data.progress);
                        saveProgress(event.data.progress);
                    } else if (event.data.command === 'contentCompleted') {
                        logDebug('Received contentCompleted message', event.data);
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

    // Process pending saves from queue
    useEffect(() => {
        const processPendingSaves = async () => {
            if (pendingSaves.length > 0 && !saveInProgress) {
                setSaveInProgress(true);
                const progressData = pendingSaves[0];
                logDebug('Processing pending save', progressData);
                
                try {
                    await saveSCORMProgress(progressData);
                    // Remove the processed item
                    setPendingSaves(prev => prev.slice(1));
                } catch (err) {
                    logDebug('Error processing pending save', err);
                    // Keep in queue to retry later
                }
                
                setSaveInProgress(false);
            }
        };
        
        processPendingSaves();
    }, [pendingSaves, saveInProgress]);

    const saveProgress = (progressData) => {
        // Ensure data is in the correct format and normalization
        const normalizedData = {
            status: progressData.status || 'incomplete',
            score: typeof progressData.score === 'number' ? progressData.score : null,
            progress: typeof progressData.progress === 'number' ? progressData.progress : 0,
            timeSpent: typeof progressData.timeSpent === 'number' ? progressData.timeSpent : 0
        };
        
        logDebug('Queueing progress data', normalizedData);
        
        // Add to pending saves queue to handle sequentially
        setPendingSaves(prev => [...prev, normalizedData]);
        
        // Update local status
        setStatus(prev => ({
            ...prev,
            ...normalizedData
        }));
    };

    const saveSCORMProgress = async (progressData) => {
        let retries = 3;
        let delay = 1000;
        
        while (retries > 0) {
            try {
                logDebug('Sending SCORM progress to server', progressData);
                
                const response = await fetch(`/scorm/topic/${topicId}/tracking/update/`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': csrfToken
                    },
                    body: JSON.stringify(progressData)
                });

                if (!response.ok) {
                    const errorText = await response.text();
                    throw new Error(`Failed to save progress: ${response.status} ${errorText}`);
                }

                const data = await response.json();
                logDebug('Server response', data);
                
                // Handle completion if needed
                if (data.completed && data.next_topic_url) {
                    window.location.href = data.next_topic_url;
                }
                
                return data;
            } catch (err) {
                console.error('Error saving progress:', err);
                retries--;
                
                if (retries > 0) {
                    logDebug(`Retrying save after ${delay}ms...`);
                    await new Promise(resolve => setTimeout(resolve, delay));
                    delay *= 2; // Exponential backoff
                } else {
                    setError('Failed to save progress after multiple attempts');
                    throw err;
                }
            }
        }
    };

    const handleCompletion = async (completionData) => {
        try {
            logDebug('Handling completion', completionData);
            
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
            logDebug('Auto-saving progress', status);
            saveProgress({
                ...status,
                timeSpent: 30 // 30 seconds since last save
            });
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