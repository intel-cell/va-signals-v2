/**
 * =============================================================================
 * LOGIN.JS - VA Signals Command Post Authentication
 * =============================================================================
 * Firebase Authentication with Google OAuth and Email/Password
 *
 * INTEGRATION NOTE: Firebase config will be provided by ECHO COMMAND schema.
 * For now, config is loaded from /api/auth/config endpoint.
 * =============================================================================
 */

(function() {
    'use strict';

    // =========================================================================
    // Configuration
    // =========================================================================

    const CONFIG = {
        apiBase: '/api',
        dashboardUrl: '/',
        forgotPasswordUrl: '/forgot-password.html',
        sessionCheckInterval: 60000, // 1 minute
        maxLoginAttempts: 5,
        lockoutDuration: 300000, // 5 minutes
    };

    // Firebase configuration - loaded dynamically from API
    let firebaseConfig = null;
    let auth = null;

    // =========================================================================
    // State
    // =========================================================================

    const state = {
        isLoading: false,
        loginAttempts: 0,
        lockoutUntil: null,
    };

    // =========================================================================
    // DOM Elements
    // =========================================================================

    const elements = {
        loginForm: null,
        emailInput: null,
        passwordInput: null,
        rememberMe: null,
        submitBtn: null,
        btnText: null,
        btnLoader: null,
        googleSignInBtn: null,
        togglePasswordBtn: null,
        errorMessage: null,
        errorText: null,
        successMessage: null,
        successText: null,
        sessionExpiredMessage: null,
        eyeOpen: null,
        eyeClosed: null,
    };

    // =========================================================================
    // Initialization
    // =========================================================================

    document.addEventListener('DOMContentLoaded', init);

    async function init() {
        cacheElements();
        bindEvents();
        checkSessionExpired();
        checkLockout();
        await initializeFirebase();
        checkExistingSession();
    }

    function cacheElements() {
        elements.loginForm = document.getElementById('login-form');
        elements.emailInput = document.getElementById('email');
        elements.passwordInput = document.getElementById('password');
        elements.rememberMe = document.getElementById('remember-me');
        elements.submitBtn = document.getElementById('submit-btn');
        elements.btnText = elements.submitBtn?.querySelector('.btn-text');
        elements.btnLoader = elements.submitBtn?.querySelector('.btn-loader');
        elements.googleSignInBtn = document.getElementById('google-signin-btn');
        elements.togglePasswordBtn = document.getElementById('toggle-password');
        elements.errorMessage = document.getElementById('error-message');
        elements.errorText = document.getElementById('error-text');
        elements.successMessage = document.getElementById('success-message');
        elements.successText = document.getElementById('success-text');
        elements.sessionExpiredMessage = document.getElementById('session-expired-message');
        elements.eyeOpen = document.getElementById('eye-open');
        elements.eyeClosed = document.getElementById('eye-closed');
    }

    function bindEvents() {
        // Form submission
        elements.loginForm?.addEventListener('submit', handleEmailLogin);

        // Google sign-in
        elements.googleSignInBtn?.addEventListener('click', handleGoogleLogin);

        // Toggle password visibility
        elements.togglePasswordBtn?.addEventListener('click', togglePasswordVisibility);

        // Clear errors on input
        elements.emailInput?.addEventListener('input', clearError);
        elements.passwordInput?.addEventListener('input', clearError);

        // Enter key in password field
        elements.passwordInput?.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                elements.loginForm?.dispatchEvent(new Event('submit'));
            }
        });
    }

    // =========================================================================
    // Firebase Initialization
    // =========================================================================

    async function initializeFirebase() {
        try {
            // Fetch Firebase config from backend
            const response = await fetch(`${CONFIG.apiBase}/auth/config`);

            if (!response.ok) {
                // If config endpoint not available, Firebase might not be set up yet
                // Allow form submission to go through API-only auth
                console.warn('Firebase config not available, using API-only auth');
                return;
            }

            firebaseConfig = await response.json();

            // Initialize Firebase
            if (typeof firebase !== 'undefined' && firebaseConfig.apiKey) {
                firebase.initializeApp(firebaseConfig);
                auth = firebase.auth();

                // Set persistence based on remember me (will be set on login)
                // Default to session persistence
                auth.setPersistence(firebase.auth.Auth.Persistence.SESSION);

                // Listen for auth state changes
                auth.onAuthStateChanged(handleAuthStateChange);
            }
        } catch (error) {
            console.warn('Firebase initialization skipped:', error.message);
            // Continue without Firebase - will fall back to API-only auth
        }
    }

    function handleAuthStateChange(user) {
        if (user && !state.isLoading) {
            // User is signed in, redirect to dashboard
            // But only if we're not in the middle of a login flow
            redirectToDashboard();
        }
    }

    // =========================================================================
    // Authentication Handlers
    // =========================================================================

    async function handleGoogleLogin(e) {
        e.preventDefault();

        if (state.isLoading || isLockedOut()) {
            return;
        }

        setLoading(true, elements.googleSignInBtn);
        clearMessages();

        try {
            if (auth) {
                // Firebase Google Sign-In
                const provider = new firebase.auth.GoogleAuthProvider();
                provider.addScope('email');
                provider.addScope('profile');

                // Set persistence based on remember me checkbox
                const persistence = elements.rememberMe?.checked
                    ? firebase.auth.Auth.Persistence.LOCAL
                    : firebase.auth.Auth.Persistence.SESSION;
                await auth.setPersistence(persistence);

                const result = await auth.signInWithPopup(provider);
                const idToken = await result.user.getIdToken();

                // Send token to backend to create session
                await createBackendSession(idToken, 'google');
            } else {
                // Fallback: Redirect to backend OAuth flow
                window.location.href = `${CONFIG.apiBase}/auth/google`;
            }
        } catch (error) {
            handleAuthError(error);
        } finally {
            setLoading(false, elements.googleSignInBtn);
        }
    }

    async function handleEmailLogin(e) {
        e.preventDefault();

        if (state.isLoading || isLockedOut()) {
            return;
        }

        const email = elements.emailInput?.value?.trim();
        const password = elements.passwordInput?.value;

        // Validate inputs
        if (!validateInputs(email, password)) {
            return;
        }

        setLoading(true, elements.submitBtn);
        clearMessages();

        try {
            if (auth) {
                // Firebase Email/Password Sign-In
                const persistence = elements.rememberMe?.checked
                    ? firebase.auth.Auth.Persistence.LOCAL
                    : firebase.auth.Auth.Persistence.SESSION;
                await auth.setPersistence(persistence);

                const result = await auth.signInWithEmailAndPassword(email, password);
                const idToken = await result.user.getIdToken();

                // Send token to backend to create session
                await createBackendSession(idToken, 'email');
            } else {
                // Fallback: Direct API authentication
                await apiLogin(email, password);
            }
        } catch (error) {
            handleAuthError(error);
            incrementLoginAttempts();
        } finally {
            setLoading(false, elements.submitBtn);
        }
    }

    async function createBackendSession(idToken, provider) {
        const response = await fetch(`${CONFIG.apiBase}/auth/session`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            credentials: 'include',
            body: JSON.stringify({
                idToken,
                provider,
                rememberMe: elements.rememberMe?.checked || false,
            }),
        });

        if (!response.ok) {
            const error = await response.json().catch(() => ({}));
            throw new Error(error.detail || 'Failed to create session');
        }

        const data = await response.json();

        // Store user info if needed
        if (data.user) {
            sessionStorage.setItem('user', JSON.stringify(data.user));
        }

        // Reset login attempts on success
        state.loginAttempts = 0;
        localStorage.removeItem('loginAttempts');
        localStorage.removeItem('lockoutUntil');

        // Redirect to dashboard
        redirectToDashboard();
    }

    async function apiLogin(email, password) {
        const response = await fetch(`${CONFIG.apiBase}/auth/login`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            credentials: 'include',
            body: JSON.stringify({
                email,
                password,
                rememberMe: elements.rememberMe?.checked || false,
            }),
        });

        if (!response.ok) {
            const error = await response.json().catch(() => ({}));
            throw new Error(error.detail || 'Invalid email or password');
        }

        const data = await response.json();

        if (data.user) {
            sessionStorage.setItem('user', JSON.stringify(data.user));
        }

        state.loginAttempts = 0;
        localStorage.removeItem('loginAttempts');
        localStorage.removeItem('lockoutUntil');

        redirectToDashboard();
    }

    // =========================================================================
    // Session Management
    // =========================================================================

    function checkExistingSession() {
        // Check if user already has a valid session
        fetch(`${CONFIG.apiBase}/auth/me`, {
            credentials: 'include',
        })
            .then(response => {
                if (response.ok) {
                    // Already logged in, redirect to dashboard
                    redirectToDashboard();
                }
            })
            .catch(() => {
                // Not logged in, stay on login page
            });
    }

    function checkSessionExpired() {
        // Check URL params for session expired flag
        const urlParams = new URLSearchParams(window.location.search);
        if (urlParams.get('expired') === 'true') {
            if (elements.sessionExpiredMessage) {
                elements.sessionExpiredMessage.style.display = 'flex';
            }
            // Clean URL
            const cleanUrl = window.location.pathname;
            window.history.replaceState({}, document.title, cleanUrl);
        }
    }

    function redirectToDashboard() {
        // Check for redirect URL in params
        const urlParams = new URLSearchParams(window.location.search);
        const redirectUrl = urlParams.get('redirect') || CONFIG.dashboardUrl;

        // Validate redirect URL to prevent open redirect
        if (redirectUrl.startsWith('/') && !redirectUrl.startsWith('//')) {
            window.location.href = redirectUrl;
        } else {
            window.location.href = CONFIG.dashboardUrl;
        }
    }

    // =========================================================================
    // Rate Limiting / Lockout
    // =========================================================================

    function checkLockout() {
        const lockoutUntil = localStorage.getItem('lockoutUntil');
        const attempts = parseInt(localStorage.getItem('loginAttempts') || '0', 10);

        state.loginAttempts = attempts;

        if (lockoutUntil) {
            const lockoutTime = parseInt(lockoutUntil, 10);
            if (Date.now() < lockoutTime) {
                state.lockoutUntil = lockoutTime;
                showLockoutMessage();
            } else {
                // Lockout expired, clear it
                localStorage.removeItem('lockoutUntil');
                localStorage.removeItem('loginAttempts');
                state.loginAttempts = 0;
                state.lockoutUntil = null;
            }
        }
    }

    function isLockedOut() {
        if (state.lockoutUntil && Date.now() < state.lockoutUntil) {
            showLockoutMessage();
            return true;
        }
        return false;
    }

    function incrementLoginAttempts() {
        state.loginAttempts++;
        localStorage.setItem('loginAttempts', state.loginAttempts.toString());

        if (state.loginAttempts >= CONFIG.maxLoginAttempts) {
            state.lockoutUntil = Date.now() + CONFIG.lockoutDuration;
            localStorage.setItem('lockoutUntil', state.lockoutUntil.toString());
            showLockoutMessage();
        }
    }

    function showLockoutMessage() {
        const remainingTime = Math.ceil((state.lockoutUntil - Date.now()) / 60000);
        showError(`Too many failed attempts. Please try again in ${remainingTime} minute${remainingTime !== 1 ? 's' : ''}.`);
        disableForm();
    }

    function disableForm() {
        if (elements.submitBtn) elements.submitBtn.disabled = true;
        if (elements.googleSignInBtn) elements.googleSignInBtn.disabled = true;
        if (elements.emailInput) elements.emailInput.disabled = true;
        if (elements.passwordInput) elements.passwordInput.disabled = true;
    }

    // =========================================================================
    // Validation
    // =========================================================================

    function validateInputs(email, password) {
        let isValid = true;

        // Email validation
        if (!email) {
            showFieldError(elements.emailInput, 'Email is required');
            isValid = false;
        } else if (!isValidEmail(email)) {
            showFieldError(elements.emailInput, 'Please enter a valid email address');
            isValid = false;
        }

        // Password validation
        if (!password) {
            showFieldError(elements.passwordInput, 'Password is required');
            isValid = false;
        } else if (password.length < 6) {
            showFieldError(elements.passwordInput, 'Password must be at least 6 characters');
            isValid = false;
        }

        return isValid;
    }

    function isValidEmail(email) {
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        return emailRegex.test(email);
    }

    function showFieldError(inputElement, message) {
        if (!inputElement) return;

        const wrapper = inputElement.closest('.input-wrapper');
        if (wrapper) {
            wrapper.classList.add('error');
        }

        // Remove existing error message
        const existingError = inputElement.closest('.form-group')?.querySelector('.field-error');
        if (existingError) {
            existingError.remove();
        }

        // Add error message
        const errorEl = document.createElement('div');
        errorEl.className = 'field-error';
        errorEl.textContent = message;
        inputElement.closest('.form-group')?.appendChild(errorEl);
    }

    function clearFieldError(inputElement) {
        if (!inputElement) return;

        const wrapper = inputElement.closest('.input-wrapper');
        if (wrapper) {
            wrapper.classList.remove('error');
        }

        const existingError = inputElement.closest('.form-group')?.querySelector('.field-error');
        if (existingError) {
            existingError.remove();
        }
    }

    // =========================================================================
    // Error Handling
    // =========================================================================

    function handleAuthError(error) {
        console.error('Auth error:', error);

        let message = 'An error occurred. Please try again.';

        // Firebase error codes
        if (error.code) {
            switch (error.code) {
                case 'auth/invalid-email':
                    message = 'Invalid email address format.';
                    break;
                case 'auth/user-disabled':
                    message = 'This account has been disabled.';
                    break;
                case 'auth/user-not-found':
                case 'auth/wrong-password':
                case 'auth/invalid-credential':
                    message = 'Invalid email or password.';
                    break;
                case 'auth/too-many-requests':
                    message = 'Too many failed attempts. Please try again later.';
                    break;
                case 'auth/popup-closed-by-user':
                    message = 'Sign-in was cancelled.';
                    break;
                case 'auth/popup-blocked':
                    message = 'Sign-in popup was blocked. Please allow popups for this site.';
                    break;
                case 'auth/network-request-failed':
                    message = 'Network error. Please check your connection.';
                    break;
                default:
                    message = error.message || message;
            }
        } else if (error.message) {
            message = error.message;
        }

        showError(message);
    }

    // =========================================================================
    // UI Helpers
    // =========================================================================

    function setLoading(isLoading, button = elements.submitBtn) {
        state.isLoading = isLoading;

        if (button === elements.submitBtn) {
            if (elements.btnText) {
                elements.btnText.style.display = isLoading ? 'none' : 'inline';
            }
            if (elements.btnLoader) {
                elements.btnLoader.style.display = isLoading ? 'flex' : 'none';
            }
        }

        if (button) {
            button.disabled = isLoading;
        }

        // Disable/enable all form elements
        if (elements.emailInput) elements.emailInput.disabled = isLoading;
        if (elements.passwordInput) elements.passwordInput.disabled = isLoading;
        if (elements.googleSignInBtn && button !== elements.googleSignInBtn) {
            elements.googleSignInBtn.disabled = isLoading;
        }
        if (elements.submitBtn && button !== elements.submitBtn) {
            elements.submitBtn.disabled = isLoading;
        }
    }

    function showError(message) {
        if (elements.errorMessage && elements.errorText) {
            elements.errorText.textContent = message;
            elements.errorMessage.style.display = 'flex';
        }
        hideSuccess();
    }

    function showSuccess(message) {
        if (elements.successMessage && elements.successText) {
            elements.successText.textContent = message;
            elements.successMessage.style.display = 'flex';
        }
        hideError();
    }

    function hideError() {
        if (elements.errorMessage) {
            elements.errorMessage.style.display = 'none';
        }
    }

    function hideSuccess() {
        if (elements.successMessage) {
            elements.successMessage.style.display = 'none';
        }
    }

    function clearMessages() {
        hideError();
        hideSuccess();
        if (elements.sessionExpiredMessage) {
            elements.sessionExpiredMessage.style.display = 'none';
        }
    }

    function clearError() {
        hideError();
        clearFieldError(elements.emailInput);
        clearFieldError(elements.passwordInput);
    }

    function togglePasswordVisibility() {
        const passwordInput = elements.passwordInput;
        if (!passwordInput) return;

        const isPassword = passwordInput.type === 'password';
        passwordInput.type = isPassword ? 'text' : 'password';

        if (elements.eyeOpen && elements.eyeClosed) {
            elements.eyeOpen.style.display = isPassword ? 'none' : 'block';
            elements.eyeClosed.style.display = isPassword ? 'block' : 'none';
        }
    }

})();
