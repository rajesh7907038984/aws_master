#!/usr/bin/env python
"""
Diagnostic script to identify the issue with score=100 not being saved to database
"""
import os
import sys
import django
import json
import re
from decimal import Decimal

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings')
django.setup()

from scorm.models import ScormAttempt
from django.utils import timezone
from datetime import timedelta


def decode_storyline_suspend_data(suspend_data):
    """Properly decode Storyline compressed suspend_data"""
    try:
        data = json.loads(suspend_data)
        if 'v' in data and 'd' in data:
            chars = data['d']
            decoded = ''
            for i, char in enumerate(chars):
                if char > 255:
                    # Reference to previous character (compression)
                    ref_index = char - 256
                    if ref_index < len(decoded):
                        decoded += decoded[ref_index]
                else:
                    # New character
                    decoded += chr(char)
            return decoded
        return str(data)
    except Exception as e:
        print(f"Error decoding: {e}")
        return suspend_data


def extract_score_from_suspend_data(decoded_data):
    """Extract score from decoded suspend data"""
    scores_found = []
    
    # Pattern 1: scors followed by number (Storyline format)
    pattern1 = re.search(r'scors(\d+)', decoded_data)
    if pattern1:
        scores_found.append(('scors pattern', pattern1.group(1)))
    
    # Pattern 2: scor" followed by number
    pattern2 = re.search(r'scor["\s]*(\d+)', decoded_data)
    if pattern2:
        scores_found.append(('scor" pattern', pattern2.group(1)))
    
    # Pattern 3: score field in JSON-like format
    pattern3 = re.search(r'"score"[:\s]*(\d+)', decoded_data)
    if pattern3:
        scores_found.append(('score field', pattern3.group(1)))
    
    # Pattern 4: quiz_score
    pattern4 = re.search(r'quiz_score[:\s]*(\d+)', decoded_data)
    if pattern4:
        scores_found.append(('quiz_score', pattern4.group(1)))
    
    # Pattern 5: Look for 100 specifically
    if '100' in decoded_data:
        # Find context around 100
        pos = decoded_data.find('100')
        context = decoded_data[max(0, pos-30):min(len(decoded_data), pos+30)]
        scores_found.append(('100 found in context', context))
    
    return scores_found


def check_score_100_issue():
    """Main diagnostic function"""
    print("=" * 80)
    print("SCORM Score 100 Diagnostic Report")
    print("=" * 80)
    
    # Check for any attempts with score >= 95
    high_scores = ScormAttempt.objects.filter(score_raw__gte=95).order_by('-score_raw')
    print(f"\n1. High Scores in Database (>= 95):")
    print(f"   Found: {high_scores.count()} attempts")
    for attempt in high_scores[:5]:
        print(f"   - User: {attempt.user.username}, Score: {attempt.score_raw}, Status: {attempt.lesson_status}")
    
    # Check for attempts with score = 100
    perfect_scores = ScormAttempt.objects.filter(score_raw=100)
    print(f"\n2. Perfect Scores (100) in Database:")
    print(f"   Found: {perfect_scores.count()} attempts")
    
    # Check recent attempts that might have score 100 in suspend_data
    print("\n3. Analyzing Recent Attempts for Hidden Score 100:")
    recent = timezone.now() - timedelta(days=7)
    recent_attempts = ScormAttempt.objects.filter(
        last_accessed__gte=recent,
        suspend_data__isnull=False
    ).exclude(suspend_data='').order_by('-last_accessed')
    
    potential_100_scores = []
    
    for attempt in recent_attempts[:50]:  # Check last 50 attempts
        if attempt.suspend_data:
            decoded = decode_storyline_suspend_data(attempt.suspend_data)
            scores = extract_score_from_suspend_data(decoded)
            
            # Check if any score is 100
            for pattern, score in scores:
                try:
                    score_val = int(score) if not isinstance(score, str) or score.isdigit() else None
                    if score_val == 100:
                        potential_100_scores.append({
                            'attempt_id': attempt.id,
                            'user': attempt.user.username,
                            'db_score': attempt.score_raw,
                            'status': attempt.lesson_status,
                            'pattern': pattern,
                            'extracted_score': score_val
                        })
                        print(f"\n   ⚠️ FOUND SCORE 100 in suspend_data!")
                        print(f"      Attempt ID: {attempt.id}")
                        print(f"      User: {attempt.user.username}")
                        print(f"      DB Score: {attempt.score_raw}")
                        print(f"      Status: {attempt.lesson_status}")
                        print(f"      Pattern: {pattern}")
                except:
                    pass
    
    if not potential_100_scores:
        print("   No score=100 found in suspend_data of recent attempts")
    
    # Check if the issue is with score extraction patterns
    print("\n4. Testing Score Extraction Patterns:")
    
    # Get a few recent attempts with scores
    test_attempts = ScormAttempt.objects.filter(
        score_raw__isnull=False,
        suspend_data__isnull=False
    ).exclude(suspend_data='').order_by('-last_accessed')[:10]
    
    for attempt in test_attempts:
        decoded = decode_storyline_suspend_data(attempt.suspend_data)
        scores = extract_score_from_suspend_data(decoded)
        
        print(f"\n   Attempt {attempt.id} (User: {attempt.user.username}):")
        print(f"   DB Score: {attempt.score_raw}")
        print(f"   Extracted scores from suspend_data:")
        for pattern, score in scores:
            if pattern != '100 found in context':
                print(f"     - {pattern}: {score}")
    
    # Check for the specific problematic attempt
    print("\n5. Checking Specific Attempt 78 (mentioned as problematic):")
    try:
        attempt_78 = ScormAttempt.objects.get(id=78)
        print(f"   User: {attempt_78.user.username}")
        print(f"   Score in DB: {attempt_78.score_raw}")
        print(f"   Status: {attempt_78.lesson_status}")
        
        if attempt_78.suspend_data:
            decoded = decode_storyline_suspend_data(attempt_78.suspend_data)
            
            # Check for quiz completion
            if 'qd"true' in decoded:
                print("   ✓ Quiz marked as complete (qd\"true found)")
            
            # Look for score
            scores = extract_score_from_suspend_data(decoded)
            if scores:
                print("   Scores found in suspend_data:")
                for pattern, score in scores:
                    print(f"     - {pattern}: {score}")
            else:
                print("   ⚠️ No score found in suspend_data despite quiz completion!")
                
                # Check if there's a malformed score pattern
                if 'scor' in decoded:
                    scor_pos = decoded.find('scor')
                    context = decoded[scor_pos:min(len(decoded), scor_pos+20)]
                    print(f"   Context after 'scor': {context}")
                    
                    # Check if score might be 100 but encoded differently
                    if 'scor"100' in decoded or 'scors100' in decoded:
                        print("   🔴 FOUND: Score 100 in suspend_data but not extracted!")
                    elif 'scor"' in decoded and decoded[decoded.find('scor"')+5:decoded.find('scor"')+8] == '100':
                        print("   🔴 FOUND: Score 100 in suspend_data but not extracted!")
    except ScormAttempt.DoesNotExist:
        print("   Attempt 78 not found")
    
    print("\n" + "=" * 80)
    print("DIAGNOSTIC COMPLETE")
    print("=" * 80)
    
    return potential_100_scores


if __name__ == "__main__":
    check_score_100_issue()
