import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { authApi, onUnauthorized, refreshCsrf, setCsrfToken } from './api.js';

const AuthContext = createContext(null);
const CACHED_USER_KEY = 'px_cached_user';

function getInitialUser() {
  try {
    const raw = localStorage.getItem(CACHED_USER_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(getInitialUser);
  const [loading, setLoading] = useState(() => !getInitialUser());

  const load = useCallback(async () => {
    try {
      const body = await authApi.me();
      const userData = body?.data || null;
      setUser(userData);
      if (userData) {
        localStorage.setItem(CACHED_USER_KEY, JSON.stringify(userData));
      } else {
        localStorage.removeItem(CACHED_USER_KEY);
      }
      await refreshCsrf();
      return userData;
    } catch (err) {
      // Only clear user session if the backend explicitly returns 401 Unauthorized.
      // If the server is restarting, offline, or experiencing network timeout, keep cached user session.
      if (err?.status === 401) {
        setUser(null);
        localStorage.removeItem(CACHED_USER_KEY);
        setCsrfToken(null);
      }
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    onUnauthorized(() => {
      localStorage.removeItem(CACHED_USER_KEY);
      setUser(null);
    });
    load();
  }, [load]);

  const login = useCallback(
    async ({ email, role = 'participant', fullName }) => {
      await authApi.login({ email, role, full_name: fullName });
      return load();
    },
    [load],
  );

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } finally {
      localStorage.removeItem(CACHED_USER_KEY);
      setCsrfToken(null);
      setUser(null);
    }
  }, []);

  const value = useMemo(() => {
    const roles = user?.roles?.map((grant) => grant.role) || [];
    const isStaff = roles.some((role) => role !== 'participant');
    return {
      user,
      loading,
      login,
      logout,
      reload: load,
      roles,
      isStaff,
      isSuperAdmin: roles.includes('super_admin') || roles.includes('owner'),
    };
  }, [user, loading, login, logout, load]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider');
  return ctx;
}
