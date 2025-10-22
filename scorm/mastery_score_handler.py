"""
Comprehensive Mastery Score Handler for all SCORM authoring tools
Handles mastery scores from:
- Articulate Storyline
- Articulate Rise 360
- Adobe Captivate
- Lectora
- iSpring
- Generic SCORM packages
"""

import xml.etree.ElementTree as ET
import logging
from decimal import Decimal

logger = logging.getLogger(__name__)


class MasteryScoreExtractor:
    """Extract mastery scores from different SCORM package formats"""
    
    # Default passing scores by authoring tool (if not found in manifest)
    DEFAULT_SCORES = {
        'storyline': 80,      # Articulate Storyline typically uses 80%
        'rise': 80,           # Rise 360 often doesn't include mastery score
        'captivate': 70,      # Adobe Captivate default
        'lectora': 75,        # Lectora default
        'ispring': 70,        # iSpring default
        'generic': 70         # Generic SCORM default
    }
    
    @classmethod
    def extract_mastery_score(cls, manifest_content, package_filename=''):
        """
        Extract mastery score from SCORM manifest
        Returns: float (percentage 0-100) or None
        """
        try:
            root = ET.fromstring(manifest_content)
            
            # Detect authoring tool
            authoring_tool = cls._detect_authoring_tool(root, package_filename)
            logger.info(f"Detected authoring tool: {authoring_tool}")
            
            # Try various extraction methods
            score = None
            
            # Method 1: Standard SCORM 1.2 mastery score
            score = cls._extract_scorm12_mastery(root)
            
            # Method 2: SCORM 2004 passing score
            if score is None:
                score = cls._extract_scorm2004_mastery(root)
            
            # Method 3: Tool-specific extraction
            if score is None:
                score = cls._extract_tool_specific_mastery(root, authoring_tool)
            
            # Method 4: Search in metadata
            if score is None:
                score = cls._extract_from_metadata(root)
            
            # Method 5: Use default for the authoring tool
            if score is None and authoring_tool in cls.DEFAULT_SCORES:
                score = cls.DEFAULT_SCORES[authoring_tool]
                logger.info(f"Using default mastery score for {authoring_tool}: {score}%")
            
            return score
            
        except Exception as e:
            logger.error(f"Error extracting mastery score: {str(e)}")
            return None
    
    @classmethod
    def _detect_authoring_tool(cls, root, filename):
        """Detect which authoring tool created the package"""
        
        filename_lower = filename.lower()
        
        # Check filename patterns
        if 'storyline' in filename_lower:
            return 'storyline'
        elif 'rise' in filename_lower:
            return 'rise'
        elif 'captivate' in filename_lower:
            return 'captivate'
        elif 'lectora' in filename_lower:
            return 'lectora'
        elif 'ispring' in filename_lower:
            return 'ispring'
        
        # Check manifest metadata
        metadata = root.find('.//metadata')
        if metadata is not None:
            # Look for tool indicators in metadata
            metadata_text = ET.tostring(metadata, encoding='unicode').lower()
            
            if 'articulate' in metadata_text or 'storyline' in metadata_text:
                return 'storyline'
            elif 'rise' in metadata_text:
                return 'rise'
            elif 'adobe' in metadata_text or 'captivate' in metadata_text:
                return 'captivate'
            elif 'lectora' in metadata_text or 'trivantis' in metadata_text:
                return 'lectora'
            elif 'ispring' in metadata_text:
                return 'ispring'
        
        # Check for specific XML patterns
        # Articulate packages often have specific organization structures
        orgs = root.find('.//organizations')
        if orgs is not None:
            org = orgs.find('.//organization')
            if org is not None:
                # Articulate Storyline pattern
                if org.find('.//item[@identifier="6jQqYp2f5VT_course_id"]') is not None:
                    return 'storyline'
        
        return 'generic'
    
    @classmethod
    def _extract_scorm12_mastery(cls, root):
        """Extract SCORM 1.2 mastery score"""
        # Define namespaces
        namespaces = {
            'adlcp': 'http://www.adlnet.org/xsd/adlcp_rootv1p2',
            'imscp': 'http://www.imsproject.org/xsd/imscp_rootv1p1p2'
        }
        
        # Look for mastery score in various locations
        mastery_elements = [
            './/adlcp:masteryscore',
            './/adlcp:mastery_score',
            './/masteryscore',
            './/mastery_score',
            './/{http://www.adlnet.org/xsd/adlcp_rootv1p2}masteryscore',
            './/{http://www.adlnet.org/xsd/adlcp_rootv1p2}mastery_score'
        ]
        
        for xpath in mastery_elements:
            try:
                if xpath.startswith('.//adlcp:'):
                    element = root.find(xpath, namespaces)
                else:
                    element = root.find(xpath)
                
                if element is not None and element.text:
                    score = float(element.text)
                    # Convert to percentage if needed (0-1 to 0-100)
                    if 0 <= score <= 1:
                        score = score * 100
                    logger.info(f"Found SCORM 1.2 mastery score: {score}%")
                    return score
            except:
                continue
        
        return None
    
    @classmethod
    def _extract_scorm2004_mastery(cls, root):
        """Extract SCORM 2004 passing score"""
        namespaces = {
            'imsss': 'http://www.imsglobal.org/xsd/imsss',
            'adlseq': 'http://www.adlnet.org/xsd/adlseq_v1p3',
            'imscp': 'http://www.imsglobal.org/xsd/imscp_v1p1'
        }
        
        # Look for minNormalizedMeasure
        sequencing = root.find('.//imsss:sequencing', namespaces)
        if sequencing is not None:
            # Primary objective
            objectives = sequencing.find('.//imsss:objectives', namespaces)
            if objectives is not None:
                primary_obj = objectives.find('.//imsss:primaryObjective', namespaces)
                if primary_obj is not None:
                    min_normalized = primary_obj.find('.//imsss:minNormalizedMeasure', namespaces)
                    if min_normalized is not None and min_normalized.text:
                        try:
                            score = float(min_normalized.text)
                            # SCORM 2004 uses 0-1 scale
                            if 0 <= score <= 1:
                                score = score * 100
                            logger.info(f"Found SCORM 2004 mastery score: {score}%")
                            return score
                        except:
                            pass
        
        # Look for scaled passing score
        scaled_passing = root.find('.//{http://www.imsglobal.org/xsd/imsss}minNormalizedMeasure')
        if scaled_passing is not None and scaled_passing.text:
            try:
                score = float(scaled_passing.text)
                if 0 <= score <= 1:
                    score = score * 100
                return score
            except:
                pass
        
        return None
    
    @classmethod
    def _extract_tool_specific_mastery(cls, root, authoring_tool):
        """Extract mastery score using tool-specific patterns"""
        
        if authoring_tool == 'storyline':
            # Articulate Storyline specific patterns
            # Storyline often puts the score in the first item
            item = root.find('.//item')
            if item is not None:
                # Look for data attributes
                for attr in item.attrib:
                    if 'mastery' in attr.lower() or 'passing' in attr.lower():
                        try:
                            score = float(item.get(attr))
                            if 0 <= score <= 1:
                                score = score * 100
                            return score
                        except:
                            pass
        
        elif authoring_tool == 'rise':
            # Rise 360 often doesn't include mastery score in manifest
            # but might have it in custom metadata
            custom_data = root.find('.//customData')
            if custom_data is not None:
                passing_score = custom_data.find('.//passingScore')
                if passing_score is not None and passing_score.text:
                    try:
                        return float(passing_score.text)
                    except:
                        pass
        
        elif authoring_tool == 'captivate':
            # Adobe Captivate specific patterns
            # Look for quiz settings in metadata
            quiz_settings = root.find('.//quizSettings')
            if quiz_settings is not None:
                passing = quiz_settings.find('.//passingScore')
                if passing is not None and passing.text:
                    try:
                        return float(passing.text)
                    except:
                        pass
        
        return None
    
    @classmethod
    def _extract_from_metadata(cls, root):
        """Extract mastery score from general metadata"""
        metadata = root.find('.//metadata')
        if metadata is not None:
            # Convert metadata to string and search for patterns
            metadata_str = ET.tostring(metadata, encoding='unicode')
            
            import re
            patterns = [
                r'passing[_\s]*score["\s:]*(\d+)',
                r'mastery[_\s]*score["\s:]*(\d+)',
                r'pass[_\s]*mark["\s:]*(\d+)',
                r'minimum[_\s]*score["\s:]*(\d+)'
            ]
            
            for pattern in patterns:
                match = re.search(pattern, metadata_str, re.IGNORECASE)
                if match:
                    try:
                        score = float(match.group(1))
                        if 0 <= score <= 1:
                            score = score * 100
                        return score
                    except:
                        pass
        
        return None


def update_mastery_scores_from_manifest():
    """Update all SCORM packages with correct mastery scores from their manifests"""
    from scorm.models import ScormPackage
    
    updated = 0
    for package in ScormPackage.objects.all():
        try:
            # Get the manifest data
            if package.manifest_data and 'raw_manifest' in package.manifest_data:
                manifest_content = package.manifest_data['raw_manifest']
                filename = package.package_file.name if package.package_file else ''
                
                # Extract mastery score
                score = MasteryScoreExtractor.extract_mastery_score(
                    manifest_content.encode('utf-8'), 
                    filename
                )
                
                if score is not None:
                    old_score = package.mastery_score
                    package.mastery_score = Decimal(str(score))
                    package.save()
                    updated += 1
                    logger.info(f"Updated {package.title}: {old_score} -> {score}%")
        except Exception as e:
            logger.error(f"Error updating package {package.id}: {str(e)}")
    
    logger.info(f"Updated mastery scores for {updated} packages")
    return updated
