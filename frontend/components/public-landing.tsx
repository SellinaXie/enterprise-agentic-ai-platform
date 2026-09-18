import Link from "next/link";

import { Icon } from "./icons";
import { architectureJourney } from "@/lib/demo-data";

const appUrl = process.env.NEXT_PUBLIC_APP_URL?.trim() || "/dashboard";

const links = [
  {
    href: "/demo",
    icon: "arrow",
    title: "Guided demo",
    description: "A one-click, seven-stage walkthrough — architecture, evidence, risk, evaluation, governance, human review, and operations — built from static synthetic data.",
    cta: "Start the walkthrough",
  },
  {
    href: "/architecture",
    icon: "assessment",
    title: "Architecture overview",
    description: "Why each major component exists, how a decision moves through the system end to end, and where the current, honest limitations are.",
    cta: "Read the rationale",
  },
  {
    href: appUrl,
    icon: "dashboard",
    title: "Authenticated workspace",
    description: "The real product: persisted assessments, evidence-grounded architecture and risk analysis, a runtime governance gate, and role-aware human review.",
    cta: "Open the workspace",
  },
];

export function PublicLanding() {
  return (
    <div className="demo-page">
      <header className="demo-nav">
        <Link className="demo-brand" href="/" aria-label="Enterprise AI Risk Intelligence">
          <span className="brand-mark"><Icon name="shield" width="22" height="22" /></span>
          <span><strong>AI Risk Intelligence</strong><small>Portfolio overview</small></span>
        </Link>
        <div className="demo-nav-actions">
          <span className="demo-synthetic-pill">Public · no login required</span>
          <a className="button secondary compact" href="https://github.com/SellinaXie/enterprise-agentic-ai-platform">View source</a>
        </div>
      </header>

      <main id="main-content">
        <section className="showcase-hero">
          <span className="eyebrow">Enterprise AI Architecture &amp; Risk Intelligence</span>
          <h1>A governed platform for AI architecture, risk, and human oversight.</h1>
          <p>
            This platform turns enterprise business context into evidence-grounded architecture
            assessments — with structured risk analysis, a runtime governance gate, and
            human-in-the-loop review before anything is treated as an approved decision. This page,
            the guided demo, and the architecture overview are all public and static: none of them
            call the backend or require signing in.
          </p>
          <div className="button-row">
            <Link className="button primary" href="/demo">Explore the guided demo <Icon name="arrow" width="16" height="16" /></Link>
            <Link className="button secondary" href="/architecture">Read the architecture overview</Link>
          </div>
        </section>

        <section className="showcase-section" aria-labelledby="entry-points-title">
          <div className="showcase-section-heading">
            <span className="eyebrow">Where to start</span>
            <h2 id="entry-points-title">Three ways to look at this project</h2>
          </div>
          <div className="link-grid">
            {links.map((link) => (
              <Link key={link.href} href={link.href} className="link-card">
                <span className="link-card-icon"><Icon name={link.icon} width="20" height="20" /></span>
                <h3>{link.title}</h3>
                <p>{link.description}</p>
                <span>{link.cta} <Icon name="arrow" width="14" height="14" /></span>
              </Link>
            ))}
          </div>
        </section>

        <section className="showcase-section" aria-labelledby="journey-title">
          <div className="showcase-section-heading">
            <span className="eyebrow">V0–V8 architecture journey</span>
            <h2 id="journey-title">Capability grew only when the problem earned it</h2>
          </div>
          <div className="journey-grid">
            {architectureJourney.map((item) => (
              <article key={item.version}><span>{item.version}</span><h3>{item.label}</h3><p>{item.detail}</p></article>
            ))}
          </div>
        </section>
      </main>

      <footer className="demo-footer">
        <span>Enterprise AI Architecture &amp; Risk Intelligence Platform</span>
        <a href="https://github.com/SellinaXie/enterprise-agentic-ai-platform">View source on GitHub</a>
      </footer>
    </div>
  );
}
