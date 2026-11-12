"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { Icon } from "@/components/icons";
import { api } from "@/lib/api/client";
import { managedAuth, managedAuthEnabled } from "@/lib/auth/client";

export default function LoginPage() {
  const router = useRouter();
  const auth = useAuth();
  const [token, setToken] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [codeSent, setCodeSent] = useState(false);
  async function submitManaged(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (!codeSent) {
        const result = await managedAuth.emailOtp.sendVerificationOtp({ email: email.trim(), type: "sign-in" });
        if (result.error) throw new Error("Unable to send a sign-in code. Check your invitation and try again.");
        setCodeSent(true);
      } else {
        const result = await managedAuth.signIn.emailOtp({ email: email.trim(), otp: code.trim() });
        if (result.error) throw new Error("That code is invalid or expired. Please try again.");
        try { await api.session(); }
        catch { throw new Error("Your identity is verified, but this account has not been granted workspace access."); }
        await auth.refresh();
        router.push("/dashboard");
        router.refresh();
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Sign-in could not be completed.");
    } finally { setBusy(false); }
  }
  if (managedAuthEnabled) {
    return <main className="login-page">
      <section className="login-story">
        <div className="brand"><span className="brand-mark"><Icon name="shield" width="22" height="22" /></span><span><strong>AI Risk Intelligence</strong><small>Enterprise architecture workspace</small></span></div>
        <div><span className="eyebrow">Governed by design</span><h1>Make the architecture decision—and its evidence—visible.</h1><p>One operational view from enterprise context through risk gating, human review, and attributed audit history.</p></div>
      </section>
      <section className="login-form-wrap"><form className="login-form" onSubmit={(event) => void submitManaged(event)}>
        <span className="eyebrow">Workspace access</span><h2>Sign in to your workspace</h2>
        <p>Use your invited email address. We&apos;ll send a verification code to your inbox.</p>
        <div className="field"><label htmlFor="email">Email address</label><input id="email" type="email" autoComplete="email" required value={email} disabled={codeSent || busy} onChange={(event) => setEmail(event.target.value)} /></div>
        {codeSent && <><p role="status">Check your inbox for your sign-in code.</p><div className="field"><label htmlFor="code">Verification code</label><input id="code" inputMode="numeric" autoComplete="one-time-code" required value={code} onChange={(event) => setCode(event.target.value)} /></div></>}
        {error && <p className="inline-error" role="alert">{error}</p>}
        <button className="button primary" style={{ width: "100%", marginTop: 14 }} disabled={busy}>{busy ? "Please wait…" : codeSent ? "Enter workspace" : "Send sign-in code"}</button>
        {codeSent && <button type="button" className="button secondary" style={{ marginTop: 12 }} disabled={busy} onClick={() => { setCodeSent(false); setCode(""); setError(null); }}>Use another email or resend</button>}
        <div className="login-security"><strong>Invited users only</strong><br />Signing in verifies your identity. Workspace roles are assigned separately by the owner.</div>
      </form></section>
    </main>;
  }
  async function submit(event: FormEvent) { event.preventDefault(); if (!token.trim()) { setError("Enter a signed bearer token."); return; } setBusy(true); setError(null); const valid = await auth.signIn(token); setBusy(false); if (valid) router.push("/dashboard"); else setError("The API rejected this token or is unavailable."); }
  return <main className="login-page"><section className="login-story"><div className="brand"><span className="brand-mark"><Icon name="shield" width="22" height="22" /></span><span><strong>AI Risk Intelligence</strong><small>Enterprise architecture workspace</small></span></div><div><span className="eyebrow">Governed by design</span><h1>Make the architecture decision—and its evidence—visible.</h1><p>One operational view from enterprise context through risk gating, human review, and attributed audit history.</p></div><div className="login-flow"><span>Evidence</span><span>→</span><span>Architecture</span><span>→</span><span>Risk</span><span>→</span><span>Decision</span><span>→</span><span>Review</span></div></section><section className="login-form-wrap"><form className="login-form" onSubmit={(event) => void submit(event)}><span className="eyebrow">Authenticated access</span><h2>Connect your identity</h2><p>Use a signed JWT issued for this API. The backend validates signature, issuer, audience, expiry, subject, and role.</p><div className="field"><label htmlFor="token">Bearer token</label><textarea id="token" required value={token} onChange={(event) => setToken(event.target.value)} placeholder="Paste a signed development or enterprise token" autoComplete="off" spellCheck={false} /></div>{error && <p className="inline-error" role="alert">{error}</p>}<button className="button primary" style={{ width: "100%", marginTop: 14 }} disabled={busy}>{busy ? "Validating identity…" : "Enter workspace"}</button><div className="login-security"><strong>Session boundary</strong><br />The token is kept only in this browser tab&apos;s session storage, attached to API requests, and never printed or sent to application logs. Production SSO and managed sessions remain a V8D concern.</div></form></section></main>;
}
