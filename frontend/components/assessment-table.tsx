import Link from "next/link";

import type { AssessmentListItem } from "@/lib/api/types";
import { formatDate, titleCase, truncate } from "@/lib/format";

import { StatusBadge } from "./ui";

export function AssessmentTable({ items }: Readonly<{ items: AssessmentListItem[] }>) {
  return (
    <div className="table-scroll">
      <table>
        <thead><tr><th>Initiative</th><th>Status</th><th>Decision</th><th>Mode</th><th>Created</th><th><span className="sr-only">Open</span></th></tr></thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.assessment_id}>
              <td><div className="table-primary"><strong>{item.company_name}</strong><span>{truncate(item.business_problem)}</span><small>{item.industry}</small></div></td>
              <td><StatusBadge value={item.status} /></td>
              <td><StatusBadge value={item.runtime_decision} /></td>
              <td>{titleCase(item.execution_mode)}</td>
              <td>{formatDate(item.created_at)}</td>
              <td><Link className="row-link" href={`/assessments/${item.assessment_id}`} aria-label={`Open assessment for ${item.company_name}`}>→</Link></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
