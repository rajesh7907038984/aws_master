def _extract_score_from_data(decoded_data):
    """Extract score using proper SCORM CMI data - NO CUSTOM CALCULATIONS"""
    try:
        # PRIMARY: Look for CMI score data first
        cmi_score_patterns = [
            r'cmi\.core\.score\.raw["\s:]*(\d+(?:\.\d+)?)',  # SCORM 1.2 score
            r'cmi\.score\.raw["\s:]*(\d+(?:\.\d+)?)',        # SCORM 2004 score
            r'cmi\.core\.score\.scaled["\s:]*(\d+(?:\.\d+)?)', # SCORM 1.2 scaled
            r'cmi\.score\.scaled["\s:]*(\d+(?:\.\d+)?)',     # SCORM 2004 scaled
        ]
        
        for pattern in cmi_score_patterns:
            score_match = re.search(pattern, decoded_data, re.IGNORECASE)
            if score_match:
                score = float(score_match.group(1))
                if 0 <= score <= 100:
                    logger.info(f"SCORM CMI: Found CMI score {score}% using pattern {pattern}")
                    return score
        
        # SECONDARY: Look for CMI completion status for pass/fail
        cmi_completion_patterns = [
            r'cmi\.completion_status["\s:]*["\']?(completed|passed|failed)["\']?',
            r'cmi\.core\.lesson_status["\s:]*["\']?(completed|passed|failed)["\']?',
            r'cmi\.success_status["\s:]*["\']?(passed|failed)["\']?',
        ]
        
        for pattern in cmi_completion_patterns:
            status_match = re.search(pattern, decoded_data, re.IGNORECASE)
            if status_match:
                status = status_match.group(1).lower()
                if status in ['completed', 'passed']:
                    logger.info(f"SCORM CMI: Found completion status '{status}' - scoring as 100%")
                    return 100.0
                elif status == 'failed':
                    logger.info(f"SCORM CMI: Found completion status '{status}' - scoring as 0%")
                    return 0.0
        
        # TERTIARY: Look for actual quiz scores (not calculated)
        actual_score_patterns = [
            r'scors(\d+)',                    # Storyline: scors88
            r'scor["\s]*(\d+)',              # Storyline: scor"88 
            r'quiz_score["\s:]*(\d+)',       # quiz_score:88
            r'final_score["\s:]*(\d+)',      # final_score:88
            r'user_score["\s:]*(\d+)',       # user_score:88
        ]
        
        for pattern in actual_score_patterns:
            score_match = re.search(pattern, decoded_data, re.IGNORECASE)
            if score_match:
                score = float(score_match.group(1))
                if 0 <= score <= 100:
                    logger.info(f"SCORM CMI: Found actual quiz score {score}% using pattern {pattern}")
                    return score
        
        # NO CUSTOM CALCULATIONS - Only use SCORM CMI data
        logger.info(f"SCORM CMI: No valid CMI data found for score extraction")
        return None
        
    except Exception as e:
        logger.error(f"SCORM CMI: Error extracting score: {str(e)}")
        return None
