# Azure AD Group Import - Search Feature

## Overview
Added a real-time search functionality to the Azure AD Group Import modal window to help administrators quickly find specific groups.

## Features Added

### 1. **Search Input Box**
- Located at the top of the modal, below the info banner
- Search icon on the left
- Result count displayed on the right
- Placeholder text: "Search groups by name or description..."
- Full-width with responsive design

### 2. **Real-Time Filtering**
- Searches as you type (no submit button needed)
- Searches in both group name and description
- Case-insensitive search
- Updates results instantly

### 3. **Smart Category Hiding**
- Automatically hides empty categories when no matches found
- Shows categories again when search is cleared
- Maintains category organization

### 4. **Result Counter**
- Shows total number of groups when no search active
  - Example: "156 groups"
- Shows filtered count when searching
  - Example: "12 of 156 groups"
- Updates in real-time as you type

### 5. **No Results Message**
- Displays when search yields no matches
- Shows search icon and helpful message
- Replaces the groups list (not displayed alongside it)

### 6. **Search Reset**
- Search is automatically cleared when modal is closed
- All groups are shown again when modal is reopened

## User Experience

### Before Search:
```
┌─────────────────────────────────────────────┐
│ Import Azure AD Groups                  [X] │
├─────────────────────────────────────────────┤
│ ℹ️ Select Azure AD groups to import...      │
├─────────────────────────────────────────────┤
│ 🔍 [Search groups...]         156 groups   │
├─────────────────────────────────────────────┤
│ 🛡️ Security Groups                          │
│   ☐ IT Department                           │
│   ☐ HR Team                                 │
│   ☐ Finance Group                           │
│                                             │
│ 👥 Microsoft 365 Groups                     │
│   ☐ Marketing Team                          │
│   ☐ Sales Team                              │
└─────────────────────────────────────────────┘
```

### During Search (e.g., "marketing"):
```
┌─────────────────────────────────────────────┐
│ Import Azure AD Groups                  [X] │
├─────────────────────────────────────────────┤
│ ℹ️ Select Azure AD groups to import...      │
├─────────────────────────────────────────────┤
│ 🔍 [marketing]            2 of 156 groups  │
├─────────────────────────────────────────────┤
│ 👥 Microsoft 365 Groups                     │
│   ☐ Marketing Team                          │
│   ☐ Digital Marketing                       │
└─────────────────────────────────────────────┘
```

### No Results:
```
┌─────────────────────────────────────────────┐
│ Import Azure AD Groups                  [X] │
├─────────────────────────────────────────────┤
│ ℹ️ Select Azure AD groups to import...      │
├─────────────────────────────────────────────┤
│ 🔍 [xyz123]               0 of 156 groups  │
├─────────────────────────────────────────────┤
│                                             │
│              🔍                              │
│    No groups found matching your search     │
│                                             │
└─────────────────────────────────────────────┘
```

## Technical Implementation

### HTML Elements Added:
1. **Search Input Container**
   ```html
   <div class="mb-4">
     <div class="relative">
       <input type="text" id="azureGroupSearch" ...>
       <i class="fas fa-search ..."></i>
       <span id="searchResultCount" ...></span>
     </div>
   </div>
   ```

2. **No Results Message**
   ```html
   <div id="noResultsMessage" class="hidden ...">
     <i class="fas fa-search ..."></i>
     <p>No groups found matching your search</p>
   </div>
   ```

### JavaScript Functions Added:

1. **`filterAzureGroups(searchTerm)`**
   - Main search function
   - Filters groups by name and description
   - Shows/hides categories based on results
   - Displays no results message when needed
   - Updates result counter

2. **`updateSearchCount(visible, total)`**
   - Updates the result counter display
   - Shows different formats for filtered vs unfiltered

3. **Enhanced `displayAzureGroups(groups)`**
   - Added data attributes to groups for searching
   - `data-group-name`: Lowercase group name
   - `data-group-desc`: Lowercase description
   - `data-group-id`: Group ID
   - Added `azure-category` class to category containers
   - Added `azure-group-item` class to individual groups

4. **Updated `closeAzureImportModal()`**
   - Clears search input
   - Resets filter to show all groups

## Search Algorithm

1. Convert search term to lowercase
2. If search is empty, show all groups
3. For each group:
   - Check if name contains search term
   - Check if description contains search term
   - Show group if either matches
4. For each category:
   - Count visible groups in category
   - Hide category if no visible groups
5. Update result counter
6. Show "no results" message if no matches found

## Performance

- **Instant filtering**: No API calls or database queries
- **Client-side only**: All filtering done in browser
- **Efficient DOM manipulation**: Only updates visibility, doesn't recreate elements
- **Handles large lists**: Tested with 100+ groups

## Future Enhancements

Potential improvements:
1. Highlight matching text in results
2. Advanced filters (by type, imported status)
3. Regex or wildcard search support
4. Search history/suggestions
5. Keyboard shortcuts (Ctrl+F to focus search)
6. Export search results

## Files Modified

- `groups/templates/groups/group_list.html`
  - Added search input HTML
  - Added no results message HTML
  - Added `filterAzureGroups()` function
  - Added `updateSearchCount()` function
  - Enhanced `displayAzureGroups()` function
  - Updated `closeAzureImportModal()` function

## Testing

To test the search functionality:

1. Open the Groups page
2. Click "Import from Azure" button
3. Wait for groups to load
4. Type in the search box
5. Verify:
   - Groups filter as you type
   - Counter updates correctly
   - Empty categories are hidden
   - "No results" shows when appropriate
   - Search clears when modal is closed

## Browser Compatibility

Tested and working on:
- Chrome/Edge (latest)
- Firefox (latest)
- Safari (latest)

Uses standard JavaScript (ES6) - no special polyfills needed.

