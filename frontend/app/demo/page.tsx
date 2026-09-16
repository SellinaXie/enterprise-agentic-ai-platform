import type { Metadata } from "next";

import { DemoExperience } from "@/components/demo-experience";

export const metadata: Metadata = {
  title: "Guided Demo",
  description:
    "A synthetic walkthrough of enterprise AI architecture, evidence, risk, governance, evaluation, human review, and operations.",
};

export default function DemoPage() {
  return <DemoExperience />;
}
