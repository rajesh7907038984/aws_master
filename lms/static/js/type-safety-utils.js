/**
 * Type Safety Utilities for LMS JavaScript
 * Provides comprehensive type checking and validation functions to prevent type-related bugs.
 */

(function() {
    'use strict';

    // Global LMS namespace
    window.LMS = window.LMS || {};
    
    // Type Safety Utilities
    window.LMS.TypeSafety = {
        
        /**
         * Check if value is a string
         * @param {*} value - Value to check
         * @returns {boolean} True if string, false otherwise
         */
        isString: function(value) {
            return typeof value === 'string';
        },
        
        /**
         * Check if value is a number
         * @param {*} value - Value to check
         * @returns {boolean} True if number, false otherwise
         */
        isNumber: function(value) {
            return typeof value === 'number' && !isNaN(value) && isFinite(value);
        },
        
        /**
         * Check if value is a boolean
         * @param {*} value - Value to check
         * @returns {boolean} True if boolean, false otherwise
         */
        isBoolean: function(value) {
            return typeof value === 'boolean';
        },
        
        /**
         * Check if value is an array
         * @param {*} value - Value to check
         * @returns {boolean} True if array, false otherwise
         */
        isArray: function(value) {
            return Array.isArray(value);
        },
        
        /**
         * Check if value is an object (not array or null)
         * @param {*} value - Value to check
         * @returns {boolean} True if object, false otherwise
         */
        isObject: function(value) {
            return value !== null && typeof value === 'object' && !Array.isArray(value);
        },
        
        /**
         * Check if value is null or undefined
         * @param {*} value - Value to check
         * @returns {boolean} True if null or undefined, false otherwise
         */
        isNullOrUndefined: function(value) {
            return value === null || value === undefined;
        },
        
        /**
         * Check if value is a function
         * @param {*} value - Value to check
         * @returns {boolean} True if function, false otherwise
         */
        isFunction: function(value) {
            return typeof value === 'function';
        },
        
        /**
         * Safely get a string value with default
         * @param {*} value - Value to convert
         * @param {string} defaultValue - Default value if conversion fails
         * @returns {string} String value or default
         */
        safeString: function(value, defaultValue = '') {
            if (this.isString(value)) {
                return value;
            }
            if (this.isNullOrUndefined(value)) {
                return defaultValue;
            }
            try {
                return String(value);
            } catch (e) {
                return defaultValue;
            }
        },
        
        /**
         * Safely get a number value with default
         * @param {*} value - Value to convert
         * @param {number} defaultValue - Default value if conversion fails
         * @returns {number} Number value or default
         */
        safeNumber: function(value, defaultValue = 0) {
            if (this.isNumber(value)) {
                return value;
            }
            if (this.isNullOrUndefined(value)) {
                return defaultValue;
            }
            
            const parsed = Number(value);
            if (this.isNumber(parsed)) {
                return parsed;
            }
            
            // Try parseInt for strings
            if (this.isString(value)) {
                const intParsed = parseInt(value, 10);
                if (this.isNumber(intParsed)) {
                    return intParsed;
                }
            }
            
            return defaultValue;
        },
        
        /**
         * Safely get a boolean value with default
         * @param {*} value - Value to convert
         * @param {boolean} defaultValue - Default value if conversion fails
         * @returns {boolean} Boolean value or default
         */
        safeBoolean: function(value, defaultValue = false) {
            if (this.isBoolean(value)) {
                return value;
            }
            if (this.isNullOrUndefined(value)) {
                return defaultValue;
            }
            
            // Handle string representations
            if (this.isString(value)) {
                const lower = value.toLowerCase().trim();
                if (lower === 'true' || lower === '1' || lower === 'yes' || lower === 'on') {
                    return true;
                }
                if (lower === 'false' || lower === '0' || lower === 'no' || lower === 'off' || lower === '') {
                    return false;
                }
            }
            
            // Handle numbers
            if (this.isNumber(value)) {
                return Boolean(value);
            }
            
            return defaultValue;
        },
        
        /**
         * Safely get an array value with default
         * @param {*} value - Value to convert
         * @param {Array} defaultValue - Default value if conversion fails
         * @returns {Array} Array value or default
         */
        safeArray: function(value, defaultValue = []) {
            if (this.isArray(value)) {
                return value;
            }
            if (this.isNullOrUndefined(value)) {
                return defaultValue;
            }
            
            // Convert single values to array
            try {
                return [value];
            } catch (e) {
                return defaultValue;
            }
        },
        
        /**
         * Safely get an object value with default
         * @param {*} value - Value to convert
         * @param {Object} defaultValue - Default value if conversion fails
         * @returns {Object} Object value or default
         */
        safeObject: function(value, defaultValue = {}) {
            if (this.isObject(value)) {
                return value;
            }
            return defaultValue;
        },
        
        /**
         * Safely parse JSON with error handling
         * @param {string} jsonString - JSON string to parse
         * @param {*} defaultValue - Default value if parsing fails
         * @returns {*} Parsed value or default
         */
        safeJsonParse: function(jsonString, defaultValue = null) {
            if (!this.isString(jsonString)) {
                return defaultValue;
            }
            
            try {
                return JSON.parse(jsonString);
            } catch (e) {
                console.warn('JSON parsing failed:', e);
                return defaultValue;
            }
        },
        
        /**
         * Safely access nested object properties
         * @param {Object} obj - Object to access
         * @param {string} path - Dot notation path (e.g., 'user.profile.name')
         * @param {*} defaultValue - Default value if path doesn't exist
         * @returns {*} Value at path or default
         */
        safeGet: function(obj, path, defaultValue = null) {
            if (!this.isObject(obj) || !this.isString(path)) {
                return defaultValue;
            }
            
            const keys = path.split('.');
            let current = obj;
            
            for (let i = 0; i < keys.length; i++) {
                const key = keys[i];
                if (current === null || current === undefined || !(key in current)) {
                    return defaultValue;
                }
                current = current[key];
            }
            
            return current;
        },
        
        /**
         * Validate form data with type checking
         * @param {FormData|Object} data - Form data to validate
         * @param {Object} schema - Validation schema
         * @returns {Object} Validation result with errors and valid data
         */
        validateFormData: function(data, schema) {
            const result = {
                valid: true,
                errors: {},
                data: {}
            };
            
            if (!this.isObject(schema)) {
                result.valid = false;
                result.errors._general = 'Invalid validation schema';
                return result;
            }
            
            // Convert FormData to object if needed
            let dataObj = {};
            if (data instanceof FormData) {
                for (let [key, value] of data.entries()) {
                    dataObj[key] = value;
                }
            } else if (this.isObject(data)) {
                dataObj = data;
            } else {
                result.valid = false;
                result.errors._general = 'Invalid data format';
                return result;
            }
            
            // Validate each field
            for (const [field, rules] of Object.entries(schema)) {
                const value = dataObj[field];
                const fieldErrors = [];
                
                // Check required
                if (rules.required && this.isNullOrUndefined(value)) {
                    fieldErrors.push(`${field} is required`);
                    continue;
                }
                
                // Skip further validation if field is not required and empty
                if (!rules.required && this.isNullOrUndefined(value)) {
                    continue;
                }
                
                // Type validation
                if (rules.type) {
                    let isValidType = false;
                    
                    switch (rules.type) {
                        case 'string':
                            isValidType = this.isString(value);
                            break;
                        case 'number':
                            isValidType = this.isNumber(value) || (this.isString(value) && !isNaN(Number(value)));
                            break;
                        case 'boolean':
                            isValidType = this.isBoolean(value) || this.isString(value);
                            break;
                        case 'array':
                            isValidType = this.isArray(value);
                            break;
                        case 'object':
                            isValidType = this.isObject(value);
                            break;
                    }
                    
                    if (!isValidType) {
                        fieldErrors.push(`${field} must be of type ${rules.type}`);
                    }
                }
                
                // Length validation for strings
                if (this.isString(value) && rules.minLength && value.length < rules.minLength) {
                    fieldErrors.push(`${field} must be at least ${rules.minLength} characters long`);
                }
                
                if (this.isString(value) && rules.maxLength && value.length > rules.maxLength) {
                    fieldErrors.push(`${field} must be no more than ${rules.maxLength} characters long`);
                }
                
                // Pattern validation
                if (this.isString(value) && rules.pattern && !rules.pattern.test(value)) {
                    fieldErrors.push(`${field} format is invalid`);
                }
                
                // Custom validator
                if (rules.validator && this.isFunction(rules.validator)) {
                    const customResult = rules.validator(value);
                    if (customResult !== true && this.isString(customResult)) {
                        fieldErrors.push(customResult);
                    }
                }
                
                // Store errors or validated data
                if (fieldErrors.length > 0) {
                    result.errors[field] = fieldErrors;
                    result.valid = false;
                } else {
                    // Convert to appropriate type
                    let convertedValue = value;
                    if (rules.type === 'number' && this.isString(value)) {
                        convertedValue = this.safeNumber(value);
                    } else if (rules.type === 'boolean') {
                        convertedValue = this.safeBoolean(value);
                    }
                    result.data[field] = convertedValue;
                }
            }
            
            return result;
        },
        
        /**
         * Safely access DOM elements with type checking
         * @param {string} selector - CSS selector
         * @param {Element} context - Context element (optional)
         * @returns {Element|null} DOM element or null
         */
        safeQuerySelector: function(selector, context = document) {
            if (!this.isString(selector)) {
                console.warn('safeQuerySelector: selector must be a string');
                return null;
            }
            
            if (!context || !this.isFunction(context.querySelector)) {
                console.warn('safeQuerySelector: invalid context');
                return null;
            }
            
            try {
                return context.querySelector(selector);
            } catch (e) {
                console.warn('safeQuerySelector: invalid selector', selector, e);
                return null;
            }
        },
        
        /**
         * Safely access DOM elements with type checking (multiple)
         * @param {string} selector - CSS selector
         * @param {Element} context - Context element (optional)
         * @returns {NodeList|Array} NodeList or empty array
         */
        safeQuerySelectorAll: function(selector, context = document) {
            if (!this.isString(selector)) {
                console.warn('safeQuerySelectorAll: selector must be a string');
                return [];
            }
            
            if (!context || !this.isFunction(context.querySelectorAll)) {
                console.warn('safeQuerySelectorAll: invalid context');
                return [];
            }
            
            try {
                return context.querySelectorAll(selector);
            } catch (e) {
                console.warn('safeQuerySelectorAll: invalid selector', selector, e);
                return [];
            }
        },
        
        /**
         * Safely get attribute value with type checking
         * @param {Element} element - DOM element
         * @param {string} attribute - Attribute name
         * @param {string} defaultValue - Default value
         * @returns {string} Attribute value or default
         */
        safeGetAttribute: function(element, attribute, defaultValue = '') {
            if (!element || !this.isFunction(element.getAttribute)) {
                return defaultValue;
            }
            
            if (!this.isString(attribute)) {
                return defaultValue;
            }
            
            try {
                const value = element.getAttribute(attribute);
                return this.safeString(value, defaultValue);
            } catch (e) {
                return defaultValue;
            }
        },
        
        /**
         * Safely set attribute value with type checking
         * @param {Element} element - DOM element
         * @param {string} attribute - Attribute name
         * @param {*} value - Attribute value
         * @returns {boolean} Success status
         */
        safeSetAttribute: function(element, attribute, value) {
            if (!element || !this.isFunction(element.setAttribute)) {
                return false;
            }
            
            if (!this.isString(attribute)) {
                return false;
            }
            
            try {
                element.setAttribute(attribute, this.safeString(value));
                return true;
            } catch (e) {
                console.warn('safeSetAttribute failed:', e);
                return false;
            }
        }
    };
    
    // Make utilities globally available
    window.TypeSafety = window.LMS.TypeSafety;

})();
