"use client";

import Link from "next/link";
import { useState } from "react";

import { Icon } from "./icons";
import { architectureJourney, demoStages } from "@/lib/demo-data";

const appUrl = process.env.NEXT_PUBLIC_APP_URL?.trim() || "/";

export function DemoExperience() {
  const [activeIndex, setActiveIndex] = useState(0);
  const active = demoStages[activeIndex];
  const isLast = activeIndex === demoStages.length - 1;

  return (
    <div className="demo-page">
      <header className="demo-nav">
        <Link className="demo-brand" href="/demo" aria-label="Enterprise AI Risk Intelligence demo">
          <span className="brand-mark"><Icon name="shield" width="22" height="22" /></span>
          <span><strong>AI Risk Intelligence</strong><small>Public architecture showcase</small></span>
        </Link>
        <div className="demo-nav-actions">
          <span className="demo-synthetic-pill">Synthetic data only</span>
          <a className="button secondary compact" href={appUrl}>Open authenticated app</a>
        </div>
      </header>

      <main id="main-content">
        <section className="demo-hero">
          <div className="demo-hero-copy">
            <span className="eyebrow">Enterprise AI Architecture &amp; Risk Intelligence</span>
            <h1>See one AI decision move from idea to governed operation.</h1>
            <p>
              A guided, non-operational walkthrough of architecture judgment, grounded evidence,
              risk controls, runtime governance, and human review—built entirely from fictional data.
            </p>
            <button className="button primary" onClick={() => setActiveIndex(0)}>
              Start guided demo <Icon name="arrow" width="17" height="17" />
            </button>
          </div>
          <aside className="demo-case-card" aria-label="Synthetic demonstration case">
            <span className="eyebrow">Fictional scenario</span>
            <h2>Retail lending support assistant</h2>
            <p>Recommend next-best actions to trained staff using internal policy and customer context.</p>
            <dl>
              <div><dt>Impact</dt><dd>High</dd></div>
              <div><dt>Data</dt><dd>Customer PII</dd></div>
              <div><dt>Authority</dt><dd>Advisory only</dd></div>
            </dl>
          </aside>
        </section>

        <section className="demo-workbench" aria-labelledby="guided-demo-title">
          <div className="demo-section-heading">
            <div><span className="eyebrow">One-click guided demo</span><h2 id="guided-demo-title">Explore the governed workflow</h2></div>
            <span className="demo-progress">{activeIndex + 1} / {demoStages.length}</span>
          </div>

          <div className="demo-stepper" role="tablist" aria-label="Demo stages">
            {demoStages.map((stage, index) => (
              <button
                key={stage.id}
                id={`demo-tab-${stage.id}`}
                role="tab"
                aria-selected={active.id === stage.id}
                aria-controls={`demo-panel-${stage.id}`}
                className={active.id === stage.id ? "active" : ""}
                onClick={() => setActiveIndex(index)}
              >
                <span>{String(index + 1).padStart(2, "0")}</span>{stage.shortLabel}
              </button>
            ))}
          </div>

          <article
            className="demo-stage"
            id={`demo-panel-${active.id}`}
            role="tabpanel"
            aria-labelledby={`demo-tab-${active.id}`}
          >
            <div className="demo-stage-copy">
              <span className="eyebrow">{active.eyebrow}</span>
              <h3>{active.title}</h3>
              <p>{active.summary}</p>
              <div className="demo-outcome"><span>Outcome</span><strong>{active.outcome}</strong></div>
            </div>
            <dl className="demo-detail-list">
              {active.details.map((detail) => <div key={detail.label}><dt>{detail.label}</dt><dd>{detail.value}</dd></div>)}
            </dl>
          </article>

          <div className="demo-controls">
            <button className="button secondary" disabled={activeIndex === 0} onClick={() => setActiveIndex((index) => Math.max(0, index - 1))}>Previous</button>
            <button className="button primary" onClick={() => setActiveIndex(isLast ? 0 : activeIndex + 1)}>
              {isLast ? "Restart walkthrough" : "Next stage"}
              <Icon name="arrow" width="17" height="17" />
            </button>
          </div>
        </section>

        <section className="demo-journey" aria-labelledby="journey-title">
          <div className="demo-section-heading">
            <div><span className="eyebrow">V0–V8 architecture journey</span><h2 id="journey-title">Capability grew only when the problem earned it</h2></div>
          </div>
          <div className="journey-grid">
            {architectureJourney.map((item) => (
              <article key={item.version}><span>{item.version}</span><h3>{item.label}</h3><p>{item.detail}</p></article>
            ))}
          </div>
        </section>

        <section className="demo-boundary">
          <div><span className="eyebrow">Trust boundary</span><h2>A showcase—not a privileged application session</h2></div>
          <p>
            This route makes no backend request, stores no token, and grants no analyst, reviewer,
            or admin authority. The authenticated product remains separately protected by OIDC/JWKS and RBAC.
          </p>
        </section>
      </main>

      <footer className="demo-footer">
        <span>Enterprise AI Architecture &amp; Risk Intelligence Platform</span>
        <a href="https://github.com/SellinaXie/enterprise-agentic-ai-platform">View source on GitHub</a>
      </footer>
    </div>
  );
}
