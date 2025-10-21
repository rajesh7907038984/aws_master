/**
 * Disable console logs in production environment
 * This prevents development debugging messages from appearing in the browser console
 */
(function() {
    // Check if we're in production environment
    const isProduction = !window.location.hostname.includes('localhost') && 
                        !window.location.hostname.includes('127.0.0.1') &&
                        !window.location.hostname.includes('localhost:') &&
                        !window.location.hostname.includes('dev.') &&
                        !window.location.hostname.includes('.dev');
    
    // Only disable logs in production
    if (isProduction) {
        // Store original console methods
        const originalConsole = {
            log: console.log,
            debug: console.debug,
            info: console.info
        };
        
        // Override non-critical console methods
        console.log = function() {
            // You can optionally keep certain critical logs by checking arguments
            // For example: if (arguments[0].includes('CRITICAL:')) originalConsole.log.apply(console, arguments);
        };
        
        console.debug = function() {
            // Suppress debug messages
        };
        
        console.info = function() {
            // Suppress info messages
        };
        
        // Keep error and warn methods intact for troubleshooting
    }
})(); 