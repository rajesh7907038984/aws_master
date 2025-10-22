/**
 * Disable console logs in production environment
 * This prevents development debugging messages from appearing in the browser console
 */
(function() {
    // Always disable logs in production - check multiple environments
    // Disabled for development - only disable logs in true production
    const isProduction = false; // Disabled for development
    
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
        // console.error and console.warn are not overridden
    }
})(); 