import { redirect } from "next/navigation";

import { getManagedAuth } from "@/lib/auth/server";

export default async function WorkspaceAccess({ children }: { children: React.ReactNode }) {
  if (process.env.NEXT_PUBLIC_AUTH_MODE === "neon") {
    const { data } = await getManagedAuth().getSession();
    if (!data?.user) redirect("/login");
  }
  return children;
}
