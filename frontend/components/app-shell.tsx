"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { useAuth } from "./auth-provider";
import { Icon } from "./icons";

const navigation = [
  { href: "/", label: "Dashboard", icon: "dashboard" },
  { href: "/assessments", label: "Assessments", icon: "assessment" },
  { href: "/assessments/new", label: "New assessment", icon: "add" },
  { href: "/reviews", label: "Reviews", icon: "review", reviewOnly: true },
  { href: "/evaluation", label: "Evaluation", icon: "evaluation" },
  { href: "/operations", label: "Operations", icon: "operations" },
];

export function AppShell({ children }: Readonly<{ children: React.ReactNode }>) {
  const pathname = usePathname();
  const auth = useAuth();

  if (pathname === "/login") return <>{children}</>;

  const canReview = auth.hasRole("reviewer", "admin");
  const visibleNavigation = navigation.filter((item) => !item.reviewOnly || canReview);
  const identity = auth.principal?.display_name ?? auth.principal?.email ?? auth.principal?.subject;
  const role = auth.principal?.roles.at(-1);

  return (
    <div className="app-frame">
      <a className="skip-link" href="#main-content">Skip to content</a>
      <aside className="sidebar">
        <Link className="brand" href="/" aria-label="Enterprise AI platform dashboard">
          <span className="brand-mark"><Icon name="shield" width="22" height="22" /></span>
          <span><strong>AI Risk</strong><small>Architecture Intelligence</small></span>
        </Link>
        <nav className="primary-nav" aria-label="Primary navigation">
          {visibleNavigation.map((item) => {
            const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
            return (
              <Link key={item.href} href={item.href} className={active ? "nav-link active" : "nav-link"} aria-current={active ? "page" : undefined}>
                <Icon name={item.icon} width="19" height="19" />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>
        <div className="principle-card">
          <span className="eyebrow">Design principle</span>
          <strong>Complexity is earned, not assumed.</strong>
          <p>Use the simplest reliable architecture that the evidence supports.</p>
        </div>
      </aside>
      <div className="content-frame">
        <header className="topbar">
          <div>
            <span className="environment-dot" />
            <span className="topbar-label">Enterprise workspace</span>
          </div>
          <div className="identity">
            {auth.status === "authenticated" ? (
              <>
                <span className="avatar" aria-hidden="true">{identity?.slice(0, 1).toUpperCase()}</span>
                <span className="identity-copy"><strong>{identity}</strong><small>{role ?? "authenticated"}</small></span>
                <button className="icon-button" onClick={auth.signOut} aria-label="Sign out"><Icon name="logout" width="18" height="18" /></button>
              </>
            ) : (
              <Link className="button secondary compact" href="/login">Connect identity</Link>
            )}
          </div>
        </header>
        {auth.status === "unauthenticated" && (
          <div className="auth-banner" role="status">A signed bearer token is required by this API. <Link href="/login">Connect identity</Link></div>
        )}
        {auth.status === "error" && (
          <div className="auth-banner warning" role="status">API unavailable: {auth.error}</div>
        )}
        <main id="main-content" className="main-content">{children}</main>
      </div>
    </div>
  );
}
