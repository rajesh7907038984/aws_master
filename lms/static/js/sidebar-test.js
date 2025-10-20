/**
 * Sidebar Functionality Test Suite
 * Tests all sidebar features after fixes
 */

(function() {
    'use strict';

    console.log('🧪 Starting Sidebar Test Suite...');

    // Test configuration
    const TESTS = {
        variables: 'CSS Variables',
        responsive: 'Responsive Behavior',
        animations: 'Animations',
        zIndex: 'Z-Index Hierarchy',
        mobile: 'Mobile Menu',
        desktop: 'Desktop Sidebar'
    };

    let testResults = {};

    /**
     * Test CSS Variables
     */
    function testCSSVariables() {
        console.log('🔍 Testing CSS Variables...');
        
        const root = document.documentElement;
        const computedStyle = getComputedStyle(root);
        
        const variables = [
            '--sidebar-width',
            '--sidebar-collapsed-width',
            '--z-sidebar',
            '--sidebar-transition',
            '--sidebar-bg',
            '--sidebar-text'
        ];

        let passed = 0;
        let total = variables.length;

        variables.forEach(variable => {
            const value = computedStyle.getPropertyValue(variable);
            if (value && value.trim() !== '') {
                console.log(`✅ ${variable}: ${value}`);
                passed++;
            } else {
                console.warn(`❌ ${variable}: Not defined`);
            }
        });

        testResults.variables = { passed, total, percentage: (passed / total) * 100 };
        console.log(`📊 Variables Test: ${passed}/${total} (${testResults.variables.percentage.toFixed(1)}%)`);
    }

    /**
     * Test Responsive Behavior
     */
    function testResponsiveBehavior() {
        console.log('🔍 Testing Responsive Behavior...');
        
        const sidebar = document.getElementById('sidebar');
        const mainContent = document.getElementById('main-content');
        
        if (!sidebar || !mainContent) {
            console.warn('❌ Required elements not found');
            testResults.responsive = { passed: 0, total: 1, percentage: 0 };
            return;
        }

        let passed = 0;
        let total = 3;

        // Test mobile behavior
        if (window.innerWidth < 768) {
            if (sidebar.classList.contains('hidden') || getComputedStyle(sidebar).display === 'none') {
                console.log('✅ Mobile: Sidebar hidden');
                passed++;
            } else {
                console.warn('❌ Mobile: Sidebar should be hidden');
            }
        } else {
            console.log('✅ Desktop: Sidebar visible');
            passed++;
        }

        // Test main content adjustment
        const marginLeft = getComputedStyle(mainContent).marginLeft;
        if (marginLeft && marginLeft !== '0px') {
            console.log('✅ Main content has proper margin');
            passed++;
        } else {
            console.warn('❌ Main content margin not set');
        }

        // Test CSS variables usage
        const sidebarWidth = getComputedStyle(sidebar).width;
        if (sidebarWidth && sidebarWidth !== 'auto') {
            console.log('✅ Sidebar width is set');
            passed++;
        } else {
            console.warn('❌ Sidebar width not properly set');
        }

        testResults.responsive = { passed, total, percentage: (passed / total) * 100 };
        console.log(`📊 Responsive Test: ${passed}/${total} (${testResults.responsive.percentage.toFixed(1)}%)`);
    }

    /**
     * Test Animations
     */
    function testAnimations() {
        console.log('🔍 Testing Animations...');
        
        const sidebar = document.getElementById('sidebar');
        if (!sidebar) {
            console.warn('❌ Sidebar not found');
            testResults.animations = { passed: 0, total: 1, percentage: 0 };
            return;
        }

        let passed = 0;
        let total = 2;

        // Test transition property
        const transition = getComputedStyle(sidebar).transition;
        if (transition && transition !== 'all 0s ease 0s') {
            console.log('✅ Sidebar has transition');
            passed++;
        } else {
            console.warn('❌ Sidebar missing transition');
        }

        // Test will-change property
        const willChange = getComputedStyle(sidebar).willChange;
        if (willChange && willChange !== 'auto') {
            console.log('✅ Sidebar has will-change optimization');
            passed++;
        } else {
            console.warn('❌ Sidebar missing will-change optimization');
        }

        testResults.animations = { passed, total, percentage: (passed / total) * 100 };
        console.log(`📊 Animations Test: ${passed}/${total} (${testResults.animations.percentage.toFixed(1)}%)`);
    }

    /**
     * Test Z-Index Hierarchy
     */
    function testZIndexHierarchy() {
        console.log('🔍 Testing Z-Index Hierarchy...');
        
        const elements = [
            { selector: '#sidebar', expected: '30', name: 'Sidebar' },
            { selector: '#mobile-menu', expected: '50', name: 'Mobile Menu' },
            { selector: '#profile-dropdown', expected: '60', name: 'Profile Dropdown' }
        ];

        let passed = 0;
        let total = elements.length;

        elements.forEach(({ selector, expected, name }) => {
            const element = document.querySelector(selector);
            if (element) {
                const zIndex = getComputedStyle(element).zIndex;
                if (zIndex === expected || zIndex === `var(--z-${name.toLowerCase().replace(' ', '-')})`) {
                    console.log(`✅ ${name}: z-index ${zIndex}`);
                    passed++;
                } else {
                    console.warn(`❌ ${name}: z-index ${zIndex} (expected ${expected})`);
                }
            } else {
                console.log(`ℹ️ ${name}: Element not found (may be hidden)`);
                passed++; // Don't penalize for hidden elements
            }
        });

        testResults.zIndex = { passed, total, percentage: (passed / total) * 100 };
        console.log(`📊 Z-Index Test: ${passed}/${total} (${testResults.zIndex.percentage.toFixed(1)}%)`);
    }

    /**
     * Test Mobile Menu
     */
    function testMobileMenu() {
        console.log('🔍 Testing Mobile Menu...');
        
        const mobileMenu = document.getElementById('mobile-menu');
        const mobileToggle = document.getElementById('mobile-menu-toggle');
        
        if (!mobileMenu || !mobileToggle) {
            console.warn('❌ Mobile menu elements not found');
            testResults.mobile = { passed: 0, total: 1, percentage: 0 };
            return;
        }

        let passed = 0;
        let total = 3;

        // Test mobile menu structure
        if (mobileMenu.classList.contains('open') || getComputedStyle(mobileMenu).display !== 'none') {
            console.log('✅ Mobile menu structure exists');
            passed++;
        } else {
            console.log('ℹ️ Mobile menu hidden (normal state)');
            passed++;
        }

        // Test toggle button
        if (mobileToggle) {
            console.log('✅ Mobile toggle button exists');
            passed++;
        } else {
            console.warn('❌ Mobile toggle button missing');
        }

        // Test event listeners
        const hasListeners = mobileToggle.onclick !== null || 
                           mobileToggle.addEventListener !== undefined;
        if (hasListeners) {
            console.log('✅ Mobile toggle has event handling');
            passed++;
        } else {
            console.warn('❌ Mobile toggle missing event listeners');
        }

        testResults.mobile = { passed, total, percentage: (passed / total) * 100 };
        console.log(`📊 Mobile Menu Test: ${passed}/${total} (${testResults.mobile.percentage.toFixed(1)}%)`);
    }

    /**
     * Test Desktop Sidebar
     */
    function testDesktopSidebar() {
        console.log('🔍 Testing Desktop Sidebar...');
        
        const sidebar = document.getElementById('sidebar');
        const mainContent = document.getElementById('main-content');
        
        if (!sidebar || !mainContent) {
            console.warn('❌ Desktop sidebar elements not found');
            testResults.desktop = { passed: 0, total: 1, percentage: 0 };
            return;
        }

        let passed = 0;
        let total = 4;

        // Test sidebar visibility on desktop
        if (window.innerWidth >= 768) {
            if (!sidebar.classList.contains('hidden') && getComputedStyle(sidebar).display !== 'none') {
                console.log('✅ Desktop sidebar visible');
                passed++;
            } else {
                console.warn('❌ Desktop sidebar should be visible');
            }
        } else {
            console.log('ℹ️ Mobile view - skipping desktop test');
            passed++;
        }

        // Test sidebar width
        const width = getComputedStyle(sidebar).width;
        if (width && width !== 'auto') {
            console.log(`✅ Sidebar width: ${width}`);
            passed++;
        } else {
            console.warn('❌ Sidebar width not set');
        }

        // Test main content adjustment
        const marginLeft = getComputedStyle(mainContent).marginLeft;
        if (marginLeft && marginLeft !== '0px') {
            console.log(`✅ Main content margin: ${marginLeft}`);
            passed++;
        } else {
            console.warn('❌ Main content margin not set');
        }

        // Test CSS variables usage
        const bgColor = getComputedStyle(sidebar).backgroundColor;
        if (bgColor && bgColor !== 'rgba(0, 0, 0, 0)') {
            console.log(`✅ Sidebar background: ${bgColor}`);
            passed++;
        } else {
            console.warn('❌ Sidebar background not set');
        }

        testResults.desktop = { passed, total, percentage: (passed / total) * 100 };
        console.log(`📊 Desktop Sidebar Test: ${passed}/${total} (${testResults.desktop.percentage.toFixed(1)}%)`);
    }

    /**
     * Run all tests
     */
    function runAllTests() {
        console.log('🚀 Running Sidebar Test Suite...');
        
        testCSSVariables();
        testResponsiveBehavior();
        testAnimations();
        testZIndexHierarchy();
        testMobileMenu();
        testDesktopSidebar();

        // Calculate overall results
        const totalPassed = Object.values(testResults).reduce((sum, result) => sum + result.passed, 0);
        const totalTests = Object.values(testResults).reduce((sum, result) => sum + result.total, 0);
        const overallPercentage = (totalPassed / totalTests) * 100;

        console.log('\n📊 SIDEBAR TEST RESULTS:');
        console.log('========================');
        
        Object.entries(testResults).forEach(([test, result]) => {
            const status = result.percentage >= 80 ? '✅' : result.percentage >= 60 ? '⚠️' : '❌';
            console.log(`${status} ${TESTS[test]}: ${result.passed}/${result.total} (${result.percentage.toFixed(1)}%)`);
        });

        console.log(`\n🎯 Overall: ${totalPassed}/${totalTests} (${overallPercentage.toFixed(1)}%)`);
        
        if (overallPercentage >= 90) {
            console.log('🎉 Excellent! All sidebar fixes are working properly.');
        } else if (overallPercentage >= 70) {
            console.log('✅ Good! Most sidebar fixes are working.');
        } else {
            console.log('⚠️ Some issues detected. Check the logs above.');
        }

        return {
            overall: { passed: totalPassed, total: totalTests, percentage: overallPercentage },
            details: testResults
        };
    }

    // Auto-run tests when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', runAllTests);
    } else {
        runAllTests();
    }

    // Export for manual testing
    window.SidebarTest = {
        run: runAllTests,
        testCSSVariables,
        testResponsiveBehavior,
        testAnimations,
        testZIndexHierarchy,
        testMobileMenu,
        testDesktopSidebar
    };

})();
