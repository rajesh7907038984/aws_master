"""
Custom validators for enhanced Session in the LMS platform
"""

import re
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _


class ComplexPasswordValidator:
    """
    Enhanced password validator that requires:
    - At least one uppercase letter
    - At least one lowercase letter  
    - At least one digit
    - At least one special character
    - No common patterns
    """
    
    def __init__(self):
        self.min_uppercase = 1
        self.min_lowercase = 1
        self.min_digits = 1
        self.min_special = 1
        
        # Common weak patterns to reject
        self.weak_patterns = [
            r'123456',
            r'password',
            r'qwerty',
            r'abc123',
            r'admin',
            r'letmein',
            r'welcome',
            r'monkey',
            r'dragon',
            r'master',
        ]
        
        # System-generated password patterns
        self.system_password_patterns = [
            # Safari auto-generated passwords (e.g., ABC-def-123-ghi)
            r'^[A-Z]{3}-[a-z]{3}-[0-9]{3}-[a-z]{3}$',
            # Chrome/Edge patterns (15+ chars with high complexity)
            r'^(?=.*[A-Z])(?=.*[a-z])(?=.*[0-9])(?=.*[!@#$%^&*(),.?":{}|<>]).{15,}$',
            # Common auto-generated patterns with high entropy
            r'^(?=.*[A-Z].*[A-Z])(?=.*[a-z].*[a-z])(?=.*[0-9].*[0-9])(?=.*[!@#$%^&*(),.?":{}|<>].*[!@#$%^&*(),.?":{}|<>]).{12,}$'
        ]

    def _is_system_generated_password(self, password):
        """
        Detect if password appears to be system/auto-generated
        """
        # Check for Safari-style patterns (ABC-def-123-ghi)
        if re.match(r'^[A-Z]{3}-[a-z]{3}-[0-9]{3}-[a-z]{3}$', password):
            return True
            
        # Check for other common auto-generated patterns
        # Chrome/Edge style: mixed case + numbers, no obvious words
        if len(password) >= 12:
            has_upper = len(re.findall(r'[A-Z]', password)) >= 2
            has_lower = len(re.findall(r'[a-z]', password)) >= 2
            has_digit = len(re.findall(r'[0-9]', password)) >= 2
            has_special = len(re.findall(r'[!@#$%^&*(),.?":{}|<>-]', password)) >= 1
            
            # Check if it has high complexity characteristics
            if has_upper and has_lower and has_digit:
                # Check for randomness patterns typical of auto-generated passwords
                if self._has_auto_generated_characteristics(password):
                    return True
                    
        return False
    
    def _has_auto_generated_characteristics(self, password):
        """
        Check if password has characteristics typical of auto-generated passwords
        """
        # Avoid passwords with obvious consecutive repeated characters
        if re.search(r'(.)\1{2,}', password):
            return False
            
        # Check for common human-readable words/patterns
        common_words = ['password', 'admin', 'user', 'login', 'welcome', 'qwerty', 
                       'hello', 'world', 'test', 'name', 'email', 'phone']
        password_lower = password.lower()
        for word in common_words:
            if word in password_lower:
                return False
                
        # Check for obvious human patterns
        human_patterns = [
            r'\d{4}',  # Year patterns like 2024
            r'(abc|xyz|123)',  # Sequential patterns
            r'([a-z])\1{2,}',  # Repeated letters
        ]
        for pattern in human_patterns:
            if re.search(pattern, password_lower):
                return False
        
        # Check for characteristics of auto-generated passwords
        
        # 1. Mixed case throughout (not just first letter capitalized)
        upper_count = len(re.findall(r'[A-Z]', password))
        lower_count = len(re.findall(r'[a-z]', password))
        digit_count = len(re.findall(r'[0-9]', password))
        
        # Auto-generated passwords typically have uppercase not just at start
        has_mixed_case = upper_count >= 2 and lower_count >= 2
        
        # 2. Numbers distributed throughout, not just at end
        numbers_at_end = re.search(r'\d+$', password)
        has_distributed_numbers = digit_count >= 2 and (not numbers_at_end or len(numbers_at_end.group()) < digit_count)
        
        # 3. Character alternation patterns (common in auto-generated passwords)
        alternation_score = 0
        for i in range(len(password) - 1):
            curr_type = self._get_char_type(password[i])
            next_type = self._get_char_type(password[i + 1])
            if curr_type != next_type:
                alternation_score += 1
        
        # High alternation suggests auto-generation
        alternation_ratio = alternation_score / (len(password) - 1) if len(password) > 1 else 0
        has_high_alternation = alternation_ratio > 0.6
        
        # Return True if it has auto-generated characteristics
        return has_mixed_case and (has_distributed_numbers or has_high_alternation)
    
    def _get_char_type(self, char):
        """Get character type for alternation analysis"""
        if char.isupper():
            return 'upper'
        elif char.islower():
            return 'lower'
        elif char.isdigit():
            return 'digit'
        else:
            return 'special'

    def validate(self, password, user=None):
        """Validate password complexity"""
        errors = []
        
        # Check for system-generated passwords first
        if self._is_system_generated_password(password):
            errors.append(_(
                "Oops! It looks like you have used your system to generate the password. "
                "According to our Session policy, we cannot secure your data if the password "
                "doesn't meet our Session policy. Please review your password policies as per "
                "the password guidelines."
            ))
            # Return early to show only this message for system-generated passwords
            raise ValidationError(errors)
        
        # Check for uppercase letters
        if len(re.findall(r'[A-Z]', password)) < self.min_uppercase:
            errors.append(_('Password must contain at least %(min)d uppercase letter.') % {'min': self.min_uppercase})
        
        # Check for lowercase letters
        if len(re.findall(r'[a-z]', password)) < self.min_lowercase:
            errors.append(_('Password must contain at least %(min)d lowercase letter.') % {'min': self.min_lowercase})
        
        # Check for digits
        if len(re.findall(r'[0-9]', password)) < self.min_digits:
            errors.append(_('Password must contain at least %(min)d digit.') % {'min': self.min_digits})
        
        # Check for special characters
        if len(re.findall(r'[!@#$%^&*(),.?":{}|<>]', password)) < self.min_special:
            special_chars = '!@#$%^&*(),.?":{}|<>'
            errors.append(_('Password must contain at least {min} special character ({chars}).').format(min=self.min_special, chars=special_chars))
        
        # Check for weak patterns
        password_lower = password.lower()
        for pattern in self.weak_patterns:
            if re.search(pattern, password_lower):
                errors.append(_('Password contains a common weak pattern: %(pattern)s') % {'pattern': pattern})
                break
        
        # Check for keyboard patterns
        keyboard_patterns = [
            'qwerty', 'asdf', 'zxcv', '1234', 'abcd'
        ]
        for pattern in keyboard_patterns:
            if pattern in password_lower:
                errors.append(_('Password should not contain keyboard patterns like "%(pattern)s".') % {'pattern': pattern})
                break
        
        # Check for repeated characters
        if re.search(r'(.)\1{2,}', password):
            errors.append(_('Password should not contain more than 2 repeated characters in a row.'))
        
        # Check if password is based on user information
        if user:
            user_info = []
            if hasattr(user, 'username') and user.username:
                user_info.append(user.username.lower())
            if hasattr(user, 'email') and user.email:
                user_info.append(user.email.split('@')[0].lower())
            if hasattr(user, 'first_name') and user.first_name:
                user_info.append(user.first_name.lower())
            if hasattr(user, 'last_name') and user.last_name:
                user_info.append(user.last_name.lower())
            
            for info in user_info:
                if len(info) > 3 and info in password_lower:
                    errors.append(_('Password should not be based on your personal information.'))
                    break
        
        if errors:
            raise ValidationError(errors)

    def get_help_text(self):
        return _(
            "Your password must contain at least one uppercase letter, "
            "one lowercase letter, one digit, and one special character. "
            "Avoid common patterns and personal information. "
            "System-generated passwords (like Safari auto-suggest) are not allowed - "
            "please create your own password following these guidelines."
        )


class SecureFilenameValidator:
    """
    Validator for secure filenames to prevent path traversal and other attacks
    """
    
    def __init__(self):
        # Dangerous characters and patterns
        self.dangerous_chars = ['..', '/', '\\', ':', '*', '?', '"', '<', '>', '|']
        self.dangerous_extensions = [
            '.exe', '.bat', '.cmd', '.com', '.pif', '.scr',
            '.vbs', '.js', '.jar', '.php', '.asp', '.aspx',
            '.jsp', '.py', '.rb', '.pl', '.sh', '.ps1'
        ]
    
    def validate(self, filename):
        """Validate filename for Session"""
        errors = []
        
        # Check for dangerous characters
        for char in self.dangerous_chars:
            if char in filename:
                errors.append(_('Filename contains dangerous character: %(char)s') % {'char': char})
        
        # Check for dangerous extensions
        filename_lower = filename.lower()
        for ext in self.dangerous_extensions:
            if filename_lower.endswith(ext):
                errors.append(_('File extension %(ext)s is not allowed') % {'ext': ext})
        
        # Check for double extensions
        parts = filename.split('.')
        if len(parts) > 2:
            for i, part in enumerate(parts[1:-1], 1):
                if f'.{part.lower()}' in self.dangerous_extensions:
                    errors.append(_('Double extension detected with dangerous type: .%(ext)s') % {'ext': part})
        
        # Check filename length
        if len(filename) > 255:
            errors.append(_('Filename is too long (maximum 255 characters)'))
        
        # Check for empty filename
        if not filename.strip():
            errors.append(_('Filename cannot be empty'))
        
        # Check for hidden files (starting with .)
        if filename.startswith('.'):
            errors.append(_('Hidden files (starting with .) are not allowed'))
        
        # Check for control characters
        if any(ord(char) < 32 for char in filename):
            errors.append(_('Filename contains control characters'))
        
        if errors:
            raise ValidationError(errors)
    
    def get_help_text(self):
        return _(
            "Filename must not contain dangerous characters or extensions. "
            "Avoid path traversal characters (.. / \\) and executable file types."
        )


def validate_ip_address(ip_string):
    """
    Validate IP address format and check for private/reserved ranges
    """
    import ipaddress
    
    try:
        ip = ipaddress.ip_address(ip_string)
        
        # Check for private/reserved addresses that shouldn't be in logs
        if ip.is_private and not ip.is_loopback:
            raise ValidationError(_('Private IP addresses are not allowed in this context'))
        
        if ip.is_reserved:
            raise ValidationError(_('Reserved IP addresses are not allowed'))
        
        return str(ip)
    
    except ValueError:
        raise ValidationError(_('Invalid IP address format'))


def validate_secure_url(url):
    """
    Validate URL for Session issues
    """
    from urllib.parse import urlparse
    
    if not url:
        return url
    
    try:
        parsed = urlparse(url)
        
        # Only allow HTTP and HTTPS
        if parsed.scheme not in ['http', 'https']:
            raise ValidationError(_('Only HTTP and HTTPS URLs are allowed'))
        
        # Check for suspicious patterns
        suspicious_patterns = [
            'javascript:', 'data:', 'file:', 'ftp:',
            'vbscript:', 'about:', 'chrome:', 'jar:'
        ]
        
        url_lower = url.lower()
        for pattern in suspicious_patterns:
            if pattern in url_lower:
                raise ValidationError(_('URL contains suspicious protocol: %(pattern)s') % {'pattern': pattern})
        
        # Allow localhost and internal addresses in production
        # (Removed localhost restriction for production server)
        
        return url
    
    except Exception as e:
        raise ValidationError(_('Invalid URL format: %(error)s') % {'error': str(e)})
