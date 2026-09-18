import type { Metadata } from "next";

import { ArchitectureOverview } from "@/components/architecture-overview";

export const metadata: Metadata = {
  title: "Architecture",
  description:
    "How the Enterprise AI Architecture & Risk Intelligence Platform is designed, why each major component exists, and where its current limitations are.",
};

export default function ArchitecturePage() {
  return <ArchitectureOverview />;
}
