# Azure AD Group Import & Sync Feature Implementation

## Overview
This document describes the implementation of the Azure AD Group Import and Sync feature for the LMS. This feature allows branch administrators to import Azure AD groups and automatically register their members into the LMS.

## Features Implemented

### 1. **Azure AD Group Import**
- Branch admins can view and select Azure AD groups from their tenant
- Groups are categorized by type (Security Groups, Microsoft 365 Groups, Distribution Lists, Other)
- For each group, admin assigns an LMS role (Learner or Instructor)
- Users from selected groups are automatically registered in the LMS
- Users are assigned to the branch admin's branch
- Already imported groups are marked and cannot be imported again

### 2. **Azure AD Group Sync**
- Branch admins can sync previously imported Azure AD groups
- Sync automatically detects new members added to Azure AD groups
- New members are automatically registered and added to corresponding LMS groups
- Maintains the role assignment made during initial import
- Updates last sync timestamp for tracking

### 3. **Automatic User Registration**
- Users are automatically created when importing/syncing groups
- Username is generated from email address
- Secure random passwords are auto-generated
- User information (email, first name, last name) is populated from Azure AD
- Users are assigned to the same branch as the importing admin

## Technical Implementation

### Models Created

#### `AzureADGroupImport`
Tracks imported Azure AD groups and their mapping to LMS groups.

**Fields:**
- `azure_group_id`: Azure AD Group ID
- `azure_group_name`: Azure AD Group Name
- `lms_group`: Foreign key to BranchGroup
- `branch`: Foreign key to Branch
- `assigned_role`: Role assigned to imported users (learner/instructor)
- `imported_by`: User who performed the import
- `imported_at`: Timestamp of import
- `last_synced_at`: Last sync timestamp
- `is_active`: Whether this import is active for syncing

#### `AzureADUserMapping`
Tracks Azure AD users imported to LMS.

**Fields:**
- `azure_user_id`: Azure AD User ID
- `azure_email`: Azure AD User Email
- `lms_user`: Foreign key to CustomUser
- `azure_group_import`: Foreign key to AzureADGroupImport
- `created_at`: Creation timestamp

### API Utilities (`groups/azure_ad_utils.py`)

#### `AzureADGroupAPI`
Client for interacting with Microsoft Graph API.

**Methods:**
- `get_access_token()`: Obtains OAuth2 access token using Teams Integration credentials
- `get_all_groups()`: Retrieves all Azure AD groups
- `get_group_members(group_id)`: Retrieves members of a specific group
- `get_groups_by_type()`: Categorizes groups by type

### Views Added (`groups/views.py`)

1. **`azure_groups_list`**: 
   - Fetches and returns Azure AD groups as JSON
   - Marks already imported groups
   - Requires branch admin role and Teams integration

2. **`azure_group_import`**:
   - Handles group import POST requests
   - Creates LMS groups and user accounts
   - Maps Azure AD groups/users to LMS entities
   - Returns import results

3. **`azure_group_sync`**:
   - Syncs previously imported groups
   - Detects new members in Azure AD
   - Creates new user accounts and adds to groups
   - Returns sync results

### URLs Added (`groups/urls.py`)
- `/groups/azure/list/` - Fetch Azure AD groups
- `/groups/azure/import/` - Import selected groups
- `/groups/azure/sync/` - Sync imported groups

### Template Updates (`groups/templates/groups/group_list.html`)

#### Buttons Added
1. **"Import from Azure"**: Opens modal to select and import Azure AD groups
2. **"Sync Azure Groups"**: Syncs all previously imported groups

#### Modal Window
- Displays Azure AD groups categorized by type
- Allows selection of groups to import
- Role selector (Learner/Instructor) for each group
- Shows already imported groups
- Import button with progress indication

#### JavaScript Functions
- `openAzureImportModal()`: Fetches and displays Azure groups
- `displayAzureGroups()`: Renders groups by category
- `toggleGroupSelection()`: Manages group selection
- `updateGroupRole()`: Updates role assignment
- `executeImport()`: Sends import request
- `syncAzureGroups()`: Sends sync request

### Admin Interface (`groups/admin.py`)

Added admin panels for:
- `AzureADGroupImport`: View imported groups, manage active status
- `AzureADUserMapping`: View user mappings

**Permissions:**
- Manual creation disabled (use import feature)
- Only viewable/editable by branch admins for their branch
- Superusers can manage all

## Prerequisites

### 1. Microsoft Teams Integration Configuration
Branch admins must first configure Microsoft Teams Integration at:
`/account/?tab=integrations&integration=teams`

**Required credentials:**
- Client ID
- Client Secret
- Tenant ID

### 2. Required Permissions
The Azure AD application must have the following Microsoft Graph API permissions:
- `Group.Read.All` - Read all groups
- `GroupMember.Read.All` - Read group memberships
- `User.Read.All` - Read user profiles

### 3. Branch Configuration
- Teams integration must be enabled for the branch
- Branch admin role required

## User Flow

### Import Flow
1. Branch admin navigates to `/groups/`
2. Clicks "Import from Azure" button
3. System fetches Azure AD groups using Teams Integration credentials
4. Admin selects groups and assigns roles
5. Clicks "Import Selected Groups"
6. System:
   - Creates LMS groups
   - Fetches group members from Azure AD
   - Creates user accounts (or updates existing)
   - Adds users to groups
   - Creates tracking records

### Sync Flow
1. Branch admin navigates to `/groups/`
2. Clicks "Sync Azure Groups" button
3. Confirms sync action
4. System:
   - Fetches current members for all imported groups
   - Compares with existing mappings
   - Creates accounts for new members
   - Adds new members to groups
   - Updates last sync timestamp

## Security Features

1. **Role-based Access Control**: Only branch admins can import/sync
2. **Branch Isolation**: Users can only see/import groups for their branch
3. **Secure Password Generation**: Random 16-character passwords for new users
4. **OAuth2 Authentication**: Secure token-based API access
5. **Unique Constraints**: Prevents duplicate imports

## Error Handling

- Connection errors to Azure AD are caught and displayed
- Invalid credentials show clear error messages
- Already imported groups cannot be re-imported
- Missing emails in Azure AD profiles are skipped
- Partial failures are reported (groups imported successfully vs errors)

## Database Migration

**Migration File**: `groups/migrations/0003_azure_ad_import_models.py`

**To apply migration:**
```bash
python manage.py migrate groups
```

## Testing the Feature

### 1. Configure Teams Integration
- Log in as branch admin
- Go to Account Settings → Integrations → Teams
- Enter Azure AD app credentials

### 2. Import Groups
- Navigate to Groups page
- Click "Import from Azure"
- Select one or more groups
- Assign roles
- Click Import

### 3. Verify Import
- Check User Groups tab for new groups
- Verify users are created and added to groups
- Check user roles match assigned roles

### 4. Test Sync
- Add new user to Azure AD group
- Click "Sync Azure Groups"
- Verify new user is added to LMS

## Monitoring & Troubleshooting

### Log Files
Check `/home/ec2-user/lmslogs/lms.log` for:
- Azure AD API calls
- Import/sync operations
- User creation events
- Error messages

### Admin Panel
Monitor imports at:
- Django Admin → Groups → Azure AD Group Imports
- Django Admin → Groups → Azure AD User Mappings

### Common Issues

1. **"Teams integration not enabled"**
   - Solution: Enable Teams integration for branch at Account Settings

2. **"Failed to get access token"**
   - Solution: Verify Azure AD app credentials
   - Check app permissions in Azure Portal

3. **"No groups found"**
   - Solution: Verify app has Group.Read.All permission
   - Check Azure AD has groups available

4. **Users not receiving login credentials**
   - Note: Auto-generated passwords are not emailed
   - Recommendation: Implement password reset email or SSO

## Future Enhancements

Potential improvements:
1. Email notifications with login credentials
2. Scheduled automatic syncs
3. Group removal detection (deactivate removed users)
4. Custom role mapping beyond Learner/Instructor
5. Import history and audit logs
6. Bulk group selection by category
7. Import preview before execution

## Files Modified/Created

### Created Files:
- `groups/azure_ad_utils.py` - Azure AD API utilities
- `groups/migrations/0003_azure_ad_import_models.py` - Database migration
- `AZURE_AD_GROUP_IMPORT_IMPLEMENTATION.md` - This documentation

### Modified Files:
- `groups/models.py` - Added AzureADGroupImport and AzureADUserMapping models
- `groups/views.py` - Added azure_groups_list, azure_group_import, azure_group_sync views
- `groups/urls.py` - Added Azure import/sync URL patterns
- `groups/admin.py` - Added admin interfaces for Azure models
- `groups/templates/groups/group_list.html` - Added UI buttons, modal, and JavaScript

## API Endpoints

### GET `/groups/azure/list/`
**Purpose**: Fetch Azure AD groups for import
**Auth**: Branch admin only
**Response**: JSON with categorized groups
```json
{
  "success": true,
  "groups": {
    "security": [...],
    "microsoft365": [...],
    "distribution": [...],
    "other": [...]
  },
  "branch_name": "Branch Name"
}
```

### POST `/groups/azure/import/`
**Purpose**: Import selected Azure AD groups
**Auth**: Branch admin only
**Request Body**:
```json
{
  "group_mappings": [
    {
      "azure_group_id": "...",
      "azure_group_name": "...",
      "assigned_role": "learner"
    }
  ]
}
```
**Response**: Import results with count of imported groups and users

### POST `/groups/azure/sync/`
**Purpose**: Sync imported Azure AD groups
**Auth**: Branch admin only
**Response**: Sync results with count of new members added

## Conclusion

This implementation provides a seamless way for branch administrators to import and manage Azure AD groups in the LMS. It automates user registration, maintains group memberships, and keeps the LMS synchronized with Azure AD changes.

The feature is production-ready and includes proper error handling, security controls, and audit tracking.

