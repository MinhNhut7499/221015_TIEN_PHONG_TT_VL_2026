import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';

const AppContext = createContext(null);

const THEME_KEY = 'archi_theme';
const LANG_KEY = 'archi_lang';

/**
 * Global UI-preference provider for theme (dark/light) and language (en/vi).
 *
 * Lives above the router so every page — Landing, Login, User, Admin — shares
 * one source of truth. Switching theme or language on any page updates all of
 * them and survives navigation. Both values persist to localStorage.
 */
export function AppProvider({ children }) {
    const [theme, setTheme] = useState(() => localStorage.getItem(THEME_KEY) || 'dark');
    const [lang, setLang] = useState(() => localStorage.getItem(LANG_KEY) || 'en');

    useEffect(() => {
        localStorage.setItem(THEME_KEY, theme);
        document.documentElement.classList.toggle('dark', theme === 'dark');
    }, [theme]);

    useEffect(() => {
        localStorage.setItem(LANG_KEY, lang);
    }, [lang]);

    const toggleTheme = useCallback(() => setTheme((p) => (p === 'dark' ? 'light' : 'dark')), []);
    const toggleLang = useCallback(() => setLang((p) => (p === 'en' ? 'vi' : 'en')), []);

    return (
        <AppContext.Provider value={{ theme, lang, setTheme, setLang, toggleTheme, toggleLang }}>
            {children}
        </AppContext.Provider>
    );
}

/** Access the global theme/language preferences. */
export function useApp() {
    const ctx = useContext(AppContext);
    if (!ctx) throw new Error('useApp must be used within AppProvider');
    return ctx;
}
