import type { RuntimeStatus } from "@/lib/api/types";
import { titleCase } from "@/lib/format";

import { StatusBadge } from "./ui";

export function RuntimeDecisionCard({ runtime }: Readonly<{ runtime: RuntimeStatus }>) {
  return (
    <section className={`decision-card ${runtime.gate_result.decision}`}>
      <div><span className="eyebrow">Runtime governance decision</span><h2>{titleCase(runtime.gate_result.decision)}</h2><p>The deterministic gate evaluated risk, evidence, provenance, execution health, and required oversight.</p></div>
      <div className="decision-meta"><StatusBadge value={runtime.gate_result.risk_level} /><StatusBadge value={runtime.review_status} /></div>
      {runtime.gate_result.reason_codes.length > 0 && <div className="reason-list"><span>Reason codes</span><ul>{runtime.gate_result.reason_codes.map((reason) => <li key={reason}>{titleCase(reason)}</li>)}</ul></div>}
    </section>
  );
}
