#!/bin/bash

# Certificate Template S3 Permissions Verification Script
# This script helps diagnose S3 permission issues

echo "========================================"
echo "S3 Permissions Verification Script"
echo "========================================"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get bucket name from environment or use default
BUCKET_NAME="${AWS_STORAGE_BUCKET_NAME:-elasticbeanstalk-eu-west-2-006619321740}"
REGION="${AWS_S3_REGION_NAME:-eu-west-2}"

echo "Bucket: $BUCKET_NAME"
echo "Region: $REGION"
echo ""

# Check 1: IAM Role attached to instance
echo "1. Checking IAM Role attached to this EC2 instance..."
ROLE_NAME=$(curl -s http://169.254.169.254/latest/meta-data/iam/security-credentials/ 2>/dev/null)
if [ -z "$ROLE_NAME" ]; then
    echo -e "${RED}✗ No IAM role attached to this instance${NC}"
    echo "  Using IAM user credentials from environment variables"
else
    echo -e "${GREEN}✓ IAM Role: $ROLE_NAME${NC}"
fi
echo ""

# Check 2: AWS CLI availability
echo "2. Checking AWS CLI installation..."
if command -v aws &> /dev/null; then
    echo -e "${GREEN}✓ AWS CLI is installed${NC}"
    AWS_VERSION=$(aws --version 2>&1)
    echo "  Version: $AWS_VERSION"
else
    echo -e "${RED}✗ AWS CLI is not installed${NC}"
    echo "  Install with: pip install awscli"
    exit 1
fi
echo ""

# Check 3: AWS credentials
echo "3. Checking AWS credentials..."
if [ -n "$AWS_ACCESS_KEY_ID" ]; then
    echo -e "${YELLOW}⚠ Using AWS_ACCESS_KEY_ID from environment${NC}"
    echo "  Key ID: ${AWS_ACCESS_KEY_ID:0:10}..."
elif [ -n "$ROLE_NAME" ]; then
    echo -e "${GREEN}✓ Using IAM role credentials${NC}"
else
    echo -e "${RED}✗ No AWS credentials found${NC}"
    exit 1
fi
echo ""

# Check 4: List bucket (requires s3:ListBucket)
echo "4. Testing s3:ListBucket permission..."
if aws s3 ls "s3://$BUCKET_NAME/media/" --region "$REGION" &>/dev/null; then
    echo -e "${GREEN}✓ s3:ListBucket permission is working${NC}"
else
    echo -e "${RED}✗ s3:ListBucket permission denied or bucket doesn't exist${NC}"
fi
echo ""

# Check 5: List certificate templates folder
echo "5. Checking certificate_templates folder..."
CERT_FOLDER="s3://$BUCKET_NAME/media/certificate_templates/"
if aws s3 ls "$CERT_FOLDER" --region "$REGION" 2>/dev/null | head -5; then
    echo -e "${GREEN}✓ Certificate templates folder is accessible${NC}"
else
    echo -e "${YELLOW}⚠ Certificate templates folder is empty or not accessible${NC}"
fi
echo ""

# Check 6: Test HeadObject on a specific file (if exists)
echo "6. Testing s3:HeadObject permission..."
# Get first file from certificate templates
FIRST_FILE=$(aws s3 ls "$CERT_FOLDER" --recursive --region "$REGION" 2>/dev/null | head -1 | awk '{print $4}')

if [ -n "$FIRST_FILE" ]; then
    # Extract just the file path after bucket name
    FILE_KEY="$FIRST_FILE"
    echo "  Testing with file: $FILE_KEY"
    
    if aws s3api head-object --bucket "$BUCKET_NAME" --key "$FILE_KEY" --region "$REGION" &>/dev/null; then
        echo -e "${GREEN}✓ s3:HeadObject permission is working${NC}"
    else
        echo -e "${RED}✗ s3:HeadObject permission denied (THIS IS THE BUG)${NC}"
        echo "  This is the permission causing the 403 error"
    fi
else
    echo -e "${YELLOW}⚠ No files found in certificate_templates to test${NC}"
    echo "  Creating a test file to verify permissions..."
    
    # Create a test file
    TEST_KEY="media/certificate_templates/test_permissions.txt"
    echo "test" | aws s3 cp - "s3://$BUCKET_NAME/$TEST_KEY" --region "$REGION" 2>/dev/null
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ s3:PutObject permission is working${NC}"
        
        # Now test HeadObject on the test file
        if aws s3api head-object --bucket "$BUCKET_NAME" --key "$TEST_KEY" --region "$REGION" &>/dev/null; then
            echo -e "${GREEN}✓ s3:HeadObject permission is working${NC}"
        else
            echo -e "${RED}✗ s3:HeadObject permission denied (THIS IS THE BUG)${NC}"
        fi
        
        # Clean up test file
        aws s3 rm "s3://$BUCKET_NAME/$TEST_KEY" --region "$REGION" 2>/dev/null
    else
        echo -e "${RED}✗ s3:PutObject permission denied${NC}"
    fi
fi
echo ""

# Check 7: Summary
echo "========================================"
echo "Summary"
echo "========================================"
echo ""
echo "Required S3 permissions for certificate templates:"
echo "  - s3:GetObject (read files)"
echo "  - s3:PutObject (upload files)"
echo "  - s3:DeleteObject (delete files)"
echo "  - s3:ListBucket (list bucket contents)"
echo "  - s3:HeadObject (check file existence - REQUIRED FOR URL GENERATION)"
echo ""
echo "To fix 403 HeadObject errors, add this to your IAM policy:"
echo ""
echo '{
    "Effect": "Allow",
    "Action": [
        "s3:HeadObject",
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject"
    ],
    "Resource": "arn:aws:s3:::'"$BUCKET_NAME"'/*"
}'
echo ""
echo "========================================"

# Check 8: Application-level fix verification
echo ""
echo "8. Checking application-level fixes..."
if grep -q "get_image_url" /home/ec2-user/lms/certificates/models.py 2>/dev/null; then
    echo -e "${GREEN}✓ Model-level safe URL method is implemented${NC}"
else
    echo -e "${RED}✗ Model-level safe URL method is missing${NC}"
fi

if grep -q "get_image_url" /home/ec2-user/lms/certificates/views.py 2>/dev/null; then
    echo -e "${GREEN}✓ Views are using safe URL method${NC}"
else
    echo -e "${YELLOW}⚠ Views may not be using safe URL method${NC}"
fi

if grep -q "S3 permission error when generating URL" /home/ec2-user/lms/core/s3_storage.py 2>/dev/null; then
    echo -e "${GREEN}✓ S3 storage backend has error handling${NC}"
else
    echo -e "${YELLOW}⚠ S3 storage backend may lack error handling${NC}"
fi

echo ""
echo "========================================"
echo "Next Steps:"
echo "========================================"
echo "1. If HeadObject permission is denied, update IAM role/user permissions"
echo "2. The code-level fixes provide graceful degradation"
echo "3. Test by accessing: https://staging.nexsy.io/certificates/templates/1/update/"
echo "4. Monitor logs: tail -f /home/ec2-user/lmslogs/production.log"
echo ""

