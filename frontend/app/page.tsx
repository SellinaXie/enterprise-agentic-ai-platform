import type { Metadata } from "next";

import { PublicLanding } from "@/components/public-landing";

export const metadata: Metadata = {
  // The root page shares its segment with the root layout, so Next.js does not apply the
  // layout's `title.template` here — write the full title explicitly to match every other route.
  title: "Overview | Enterprise AI Risk Intelligence",
  description:
    "A portfolio showcase of the Enterprise AI Architecture & Risk Intelligence Platform: a guided demo, the architecture rationale, and the authenticated product — no backend or login required to browse.",
};

export default function HomePage() {
  return <PublicLanding />;
}
