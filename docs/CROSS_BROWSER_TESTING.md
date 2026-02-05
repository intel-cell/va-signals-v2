# Cross-Browser Testing Scenarios

## VA Signals Dashboard - Browser Compatibility Matrix

### Supported Browsers

| Browser | Minimum Version | Status |
|---------|----------------|--------|
| Chrome | 100+ | Primary |
| Firefox | 100+ | Supported |
| Safari | 15+ | Supported |
| Edge | 100+ | Supported |
| Mobile Safari | iOS 15+ | Supported |
| Chrome Mobile | Android 10+ | Supported |

---

## Test Scenarios

### 1. Authentication & Authorization

#### 1.1 Firebase Auth Flow
- [ ] Google Sign-In popup opens correctly
- [ ] OAuth redirect works without CORS errors
- [ ] Session persists after page refresh
- [ ] Session expires correctly after timeout
- [ ] Logout clears all session data
- [ ] Protected routes redirect to login

#### 1.2 Role-Based Access
- [ ] Viewer can access dashboard views
- [ ] Analyst can access detailed data endpoints
- [ ] Leadership can access CEO briefs
- [ ] Commander can access admin functions
- [ ] Unauthorized access shows proper error

---

### 2. Dashboard Core Features

#### 2.1 Main Dashboard
- [ ] Dashboard loads within 3 seconds
- [ ] All cards render correctly
- [ ] Stats update on refresh
- [ ] Navigation works between sections
- [ ] Responsive layout on mobile

#### 2.2 Data Tables
- [ ] Tables render with proper columns
- [ ] Sorting works (ascending/descending)
- [ ] Filtering updates results
- [ ] Pagination works correctly
- [ ] Empty states display properly

#### 2.3 Charts & Visualizations
- [ ] Charts render without JavaScript errors
- [ ] Tooltips display on hover
- [ ] Legend toggles work
- [ ] Charts resize on window change
- [ ] Data updates reflect in charts

---

### 3. Real-Time Features

#### 3.1 WebSocket Connection
- [ ] WebSocket connects on page load
- [ ] Connection status indicator shows state
- [ ] Reconnection happens on disconnect
- [ ] Messages received and displayed
- [ ] Subscription changes work

#### 3.2 Live Updates
- [ ] New signals appear without refresh
- [ ] Alerts display with notification
- [ ] Counters update in real-time
- [ ] No memory leaks over time

---

### 4. API Integration

#### 4.1 REST Endpoints
- [ ] GET requests return data correctly
- [ ] POST requests submit data
- [ ] Error responses handled gracefully
- [ ] Loading states display during fetch
- [ ] Timeout handling works

#### 4.2 Error Handling
- [ ] Network errors show user message
- [ ] 401 errors redirect to login
- [ ] 403 errors show access denied
- [ ] 404 errors show not found
- [ ] 500 errors show server error message

---

### 5. Forms & Input

#### 5.1 Form Validation
- [ ] Required fields show validation
- [ ] Email format validation works
- [ ] Date pickers work correctly
- [ ] Dropdown selections persist
- [ ] Form submission works

#### 5.2 Input Types
- [ ] Text inputs work
- [ ] Number inputs restrict to numbers
- [ ] Date inputs use native picker
- [ ] File uploads work
- [ ] Textarea expands correctly

---

### 6. Responsive Design

#### 6.1 Desktop (1920x1080)
- [ ] Full layout displays
- [ ] Sidebar visible
- [ ] Tables show all columns
- [ ] Charts full size

#### 6.2 Laptop (1366x768)
- [ ] Layout adapts
- [ ] Tables horizontally scrollable
- [ ] Charts resize appropriately

#### 6.3 Tablet (768x1024)
- [ ] Mobile navigation appears
- [ ] Cards stack vertically
- [ ] Touch interactions work
- [ ] Landscape/portrait transitions

#### 6.4 Mobile (375x667)
- [ ] Hamburger menu works
- [ ] Content readable without zoom
- [ ] Touch targets large enough
- [ ] No horizontal scroll on body

---

### 7. Accessibility

#### 7.1 Keyboard Navigation
- [ ] Tab order is logical
- [ ] Focus indicators visible
- [ ] Skip links work
- [ ] Modals trap focus
- [ ] Escape closes modals

#### 7.2 Screen Reader
- [ ] Headings hierarchy correct
- [ ] Images have alt text
- [ ] Form labels associated
- [ ] ARIA labels present
- [ ] Live regions announce updates

#### 7.3 Visual
- [ ] Color contrast passes WCAG AA
- [ ] Text readable at 200% zoom
- [ ] No information by color alone
- [ ] Focus states visible

---

### 8. Performance

#### 8.1 Load Time
- [ ] First Contentful Paint < 1.5s
- [ ] Time to Interactive < 3s
- [ ] Largest Contentful Paint < 2.5s
- [ ] No layout shifts (CLS < 0.1)

#### 8.2 Runtime
- [ ] Smooth scrolling (60fps)
- [ ] No memory leaks
- [ ] Efficient re-renders
- [ ] Lazy loading works

---

### 9. Browser-Specific Tests

#### 9.1 Chrome
- [ ] DevTools console clear of errors
- [ ] Service worker registers (if applicable)
- [ ] LocalStorage persists
- [ ] WebSocket maintains connection

#### 9.2 Firefox
- [ ] CSS grid renders correctly
- [ ] WebSocket connects
- [ ] Date inputs work
- [ ] Flexbox layouts correct

#### 9.3 Safari
- [ ] Date picker native
- [ ] Position: sticky works
- [ ] WebSocket connects (may need polling fallback)
- [ ] LocalStorage available in private mode (fallback)

#### 9.4 Edge
- [ ] All Chrome tests pass
- [ ] PDF viewer works
- [ ] Downloads work correctly

---

### 10. Security Features

#### 10.1 CSRF Protection
- [ ] CSRF token included in forms
- [ ] Token validated on POST
- [ ] Token refreshes on session

#### 10.2 XSS Prevention
- [ ] User input sanitized in display
- [ ] No inline script execution
- [ ] CSP headers enforced

#### 10.3 Authentication Security
- [ ] Passwords not stored in localStorage
- [ ] Tokens have expiration
- [ ] Secure flag on cookies (HTTPS)
- [ ] HttpOnly on session cookies

---

## Test Execution Guide

### Local Testing Setup

```bash
# Start local server
cd /Users/xa/Work_VC/va-signals-v2
DATABASE_PATH=data/signals.db uvicorn src.dashboard_api:app --reload --port 8000

# Access at http://localhost:8000
```

### Browser DevTools Checklist

1. **Console**: Check for JavaScript errors
2. **Network**: Verify API calls succeed
3. **Application**: Check storage and cookies
4. **Performance**: Run Lighthouse audit
5. **Accessibility**: Run axe DevTools

### Testing Tools

- **BrowserStack**: Cross-browser cloud testing
- **Lighthouse**: Performance & accessibility audits
- **axe DevTools**: Accessibility testing
- **WebSocket King**: WebSocket debugging

---

## Bug Report Template

```markdown
### Bug Description
[Clear description of the issue]

### Browser & Version
[e.g., Chrome 120.0.6099.109]

### Operating System
[e.g., macOS 14.2]

### Steps to Reproduce
1. [Step 1]
2. [Step 2]
3. [Step 3]

### Expected Behavior
[What should happen]

### Actual Behavior
[What actually happens]

### Screenshots
[If applicable]

### Console Errors
[Copy any relevant errors]
```

---

## Sign-Off Checklist

| Browser | Tester | Date | Pass/Fail | Notes |
|---------|--------|------|-----------|-------|
| Chrome | | | | |
| Firefox | | | | |
| Safari | | | | |
| Edge | | | | |
| Mobile Safari | | | | |
| Chrome Mobile | | | | |

**Test Environment**: Production / Staging / Local
**Dashboard Version**: ___________
**Date Completed**: ___________
**Signed Off By**: ___________
