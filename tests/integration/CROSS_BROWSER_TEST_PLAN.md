# Cross-Browser Test Plan

## HOTEL COMMAND - Phase 2 Testing
## Command Dashboard Cross-Browser Compatibility

---

## Target Browsers

| Browser | Version | Priority | Platform |
|---------|---------|----------|----------|
| Chrome | Latest | P0 | Desktop/Mobile |
| Safari | Latest | P0 | Desktop/iOS |
| Firefox | Latest | P1 | Desktop |
| Edge | Latest | P1 | Desktop |
| Chrome | Mobile | P0 | Android |
| Safari | Mobile | P0 | iOS |

---

## Test Scenarios

### 1. Login Page (`login.html`)

| Test ID | Scenario | Expected Result |
|---------|----------|-----------------|
| LOGIN-001 | Page loads without errors | No console errors, all assets load |
| LOGIN-002 | Form validation works | Invalid email shows error |
| LOGIN-003 | Password visibility toggle | Eye icon toggles password visibility |
| LOGIN-004 | "Remember me" checkbox | Persists across sessions |
| LOGIN-005 | Forgot password link | Navigates to forgot-password.html |
| LOGIN-006 | Google SSO button | Opens OAuth popup |
| LOGIN-007 | Error messages display | Red alert box appears on failure |
| LOGIN-008 | Mobile responsive layout | Single column on mobile viewports |

### 2. Dashboard Main (`index.html`)

| Test ID | Scenario | Expected Result |
|---------|----------|-----------------|
| DASH-001 | Dashboard loads after login | All tabs visible, stats load |
| DASH-002 | Tab navigation works | Clicking tabs switches content |
| DASH-003 | Data refresh indicator | "Live" pulse animation works |
| DASH-004 | User menu dropdown | Shows user info and logout |
| DASH-005 | Notification bell | Shows notification count badge |
| DASH-006 | Reports dropdown | Daily/Weekly report buttons work |
| DASH-007 | Charts render | Chart.js graphs display correctly |
| DASH-008 | Mobile hamburger menu | Navigation collapses on mobile |

### 3. Command Center Tab

| Test ID | Scenario | Expected Result |
|---------|----------|-----------------|
| CMD-001 | Mission status cards load | 4 cards with icons and counts |
| CMD-002 | Quick actions panel | Action buttons are clickable |
| CMD-003 | Activity feed | Recent items display with timestamps |
| CMD-004 | Status indicators | Green/yellow/red dots animate |

### 4. Executive Summary View

| Test ID | Scenario | Expected Result |
|---------|----------|-----------------|
| EXEC-001 | Key metrics display | FR, Bills, Hearings, State, Vehicles |
| EXEC-002 | Trend arrows | Up/down arrows with colors |
| EXEC-003 | Impact heat map | 4-quadrant grid renders |
| EXEC-004 | Upcoming decisions | Calendar items with dates |
| EXEC-005 | Critical items list | Top 5 with severity badges |
| EXEC-006 | Print layout | Print media query applied |

### 5. CEO Brief Viewer

| Test ID | Scenario | Expected Result |
|---------|----------|-----------------|
| BRIEF-001 | Brief selector dropdown | Lists available briefs |
| BRIEF-002 | Brief content renders | Markdown formatted correctly |
| BRIEF-003 | Evidence links | Clickable, open in new tab |
| BRIEF-004 | Print button | Opens print dialog |
| BRIEF-005 | PDF export | Generates PDF file |

### 6. Audit Log Viewer (COMMANDER)

| Test ID | Scenario | Expected Result |
|---------|----------|-----------------|
| AUDIT-001 | Log table loads | Paginated table displays |
| AUDIT-002 | Filter by user | Dropdown filters results |
| AUDIT-003 | Filter by action | Dropdown filters results |
| AUDIT-004 | Date range picker | Date inputs filter results |
| AUDIT-005 | Export to CSV | Downloads CSV file |
| AUDIT-006 | Role restriction | Non-COMMANDER sees nothing |

### 7. Mobile Responsiveness

| Test ID | Scenario | Viewport | Expected Result |
|---------|----------|----------|-----------------|
| MOB-001 | Login page | 375x667 | Single column, no horizontal scroll |
| MOB-002 | Dashboard | 375x667 | Hamburger menu, stacked cards |
| MOB-003 | Tables | 375x667 | Horizontal scroll or card view |
| MOB-004 | Charts | 375x667 | Responsive resize |
| MOB-005 | Touch targets | 375x667 | Min 44x44px tap areas |
| MOB-006 | Landscape | 667x375 | Layout adapts gracefully |

### 8. Accessibility

| Test ID | Scenario | Expected Result |
|---------|----------|-----------------|
| A11Y-001 | Keyboard navigation | Tab order logical |
| A11Y-002 | Focus indicators | Visible focus ring on all interactive |
| A11Y-003 | Screen reader | Labels and ARIA attributes present |
| A11Y-004 | Color contrast | WCAG AA compliance |
| A11Y-005 | Form labels | All inputs have labels |

---

## Browser-Specific Issues to Check

### Safari
- [ ] CSS Grid/Flexbox gaps
- [ ] Date input styling
- [ ] Backdrop filter support
- [ ] Position: sticky behavior

### Firefox
- [ ] Scrollbar styling
- [ ] Input placeholder colors
- [ ] Custom select styling

### Mobile Safari (iOS)
- [ ] 100vh viewport issue
- [ ] Input zoom on focus
- [ ] Safe area insets
- [ ] Rubber band scrolling

### Chrome Mobile (Android)
- [ ] Bottom navigation overlap
- [ ] Pull-to-refresh interference
- [ ] Back button behavior

---

## Test Execution Checklist

### Pre-Test Setup
- [ ] Clear browser cache
- [ ] Disable extensions
- [ ] Set viewport to target size
- [ ] Enable DevTools console

### Test Execution
- [ ] Execute all scenarios per browser
- [ ] Screenshot any failures
- [ ] Note console errors/warnings
- [ ] Record network failures

### Post-Test
- [ ] Compile test results
- [ ] Document browser-specific bugs
- [ ] Prioritize fixes by severity
- [ ] Update SITREP with results

---

## Automated Testing Tools

### Recommended
- **Playwright**: Cross-browser E2E automation
- **Cypress**: Chrome/Firefox/Edge testing
- **BrowserStack**: Cloud cross-browser testing
- **Lighthouse**: Performance and accessibility audits

### Command to Run Local Tests
```bash
# Run E2E tests
pytest tests/integration/test_e2e_scenarios.py -v

# Run with coverage
pytest tests/integration/ --cov=src --cov-report=html
```

---

## Sign-Off

| Browser | Tester | Date | Result |
|---------|--------|------|--------|
| Chrome Desktop | | | |
| Safari Desktop | | | |
| Firefox Desktop | | | |
| Chrome Mobile | | | |
| Safari Mobile | | | |

---

*Document: HOTEL COMMAND - Cross-Browser Test Plan*
*Operation: COMMAND POST (OPLAN 002)*
