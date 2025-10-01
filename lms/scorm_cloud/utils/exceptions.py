class SCORMCloudError(Exception):
    """Base exception for SCORM Cloud errors"""
    pass

class SCORMCloudAuthError(SCORMCloudError):
    """Authentication related errors"""
    pass

class SCORMCloudUploadError(SCORMCloudError):
    """Upload related errors"""
    pass

class SCORMCloudImportError(SCORMCloudError):
    """Import job related errors"""
    pass