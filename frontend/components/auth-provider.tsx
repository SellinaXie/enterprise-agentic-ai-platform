"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { ApiError, api, setAccessToken } from "@/lib/api/client";
import type { Principal, Role } from "@/lib/api/types";

type AuthStatus = "loading" | "authenticated" | "unauthenticated" | "error";

export interface AuthContextValue {
  principal: Principal | null;
  status: AuthStatus;
  error: string | null;
  signIn: (token: string) => Promise<boolean>;
  signOut: () => void;
  refresh: () => Promise<void>;
  hasRole: (...roles: Role[]) => boolean;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: Readonly<{ children: React.ReactNode }>) {
  const [principal, setPrincipal] = useState<Principal | null>(null);
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [error, setError] = useState<string | null>(null);

  const loadPrincipal = useCallback(async (): Promise<boolean> => {
    setStatus("loading");
    setError(null);
    try {
      const response = await api.session();
      setPrincipal(response.data);
      setStatus("authenticated");
      return true;
    } catch (caught) {
      setPrincipal(null);
      if (caught instanceof ApiError && caught.status === 401) {
        setStatus("unauthenticated");
      } else {
        setStatus("error");
        setError(caught instanceof Error ? caught.message : "Unable to reach the API.");
      }
      return false;
    }
  }, []);

  const refresh = useCallback(async () => {
    await loadPrincipal();
  }, [loadPrincipal]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const signIn = useCallback(
    async (token: string) => {
      setAccessToken(token.trim());
      const authenticated = await loadPrincipal();
      if (!authenticated) setAccessToken(null);
      return authenticated;
    },
    [loadPrincipal],
  );

  const signOut = useCallback(() => {
    setAccessToken(null);
    setPrincipal(null);
    setStatus("unauthenticated");
    setError(null);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      principal,
      status,
      error,
      signIn,
      signOut,
      refresh,
      hasRole: (...roles: Role[]) =>
        principal !== null && roles.some((role) => principal.roles.includes(role)),
    }),
    [error, principal, refresh, signIn, signOut, status],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
