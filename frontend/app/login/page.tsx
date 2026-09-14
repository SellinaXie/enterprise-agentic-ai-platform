"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { Icon } from "@/components/icons";

export default function LoginPage() {
  const router = useRouter();
  const auth = useAuth();
  const [token, setToken] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent) { event.preventDefault(); if (!token.trim()) { setError("Enter a signed bearer token."); return; } setBusy(true); setError(null); const valid = await auth.signIn(token); setBusy(false); if (valid) router.push("/"); else setError("The API rejected this token or is unavailable."); }
  return <main className="login-page"><section className="login-story"><div className="brand"><span className="brand-mark"><Icon name="shield" width="22" height="22" /></span><span><strong>AI Risk Intelligence</strong><small>Enterprise architecture workspace</small></span></div><div><span className="eyebrow">Governed by design</span><h1>Make the architecture decision—and its evidence—visible.</h1><p>One operational view from enterprise context through risk gating, human review, and attributed audit history.</p></div><div className="login-flow"><span>Evidence</span><span>→</span><span>Architecture</span><span>→</span><span>Risk</span><span>→</span><span>Decision</span><span>→</span><span>Review</span></div></section><section className="login-form-wrap"><form className="login-form" onSubmit={(event) => void submit(event)}><span className="eyebrow">Authenticated access</span><h2>Connect your identity</h2><p>Use a signed JWT issued for this API. The backend validates signature, issuer, audience, expiry, subject, and role.</p><div className="field"><label htmlFor="token">Bearer token</label><textarea id="token" required value={token} onChange={(event) => setToken(event.target.value)} placeholder="Paste a signed development or enterprise token" autoComplete="off" spellCheck={false} /></div>{error && <p className="inline-error" role="alert">{error}</p>}<button className="button primary" style={{ width: "100%", marginTop: 14 }} disabled={busy}>{busy ? "Validating identity…" : "Enter workspace"}</button><div className="login-security"><strong>Session boundary</strong><br />The token is kept only in this browser tab&apos;s session storage, attached to API requests, and never printed or sent to application logs. Production SSO and managed sessions remain a V8D concern.</div></form></section></main>;
}
