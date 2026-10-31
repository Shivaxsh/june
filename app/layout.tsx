import { JUNE_VERSION } from "@/lib/version";
import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: `June v${JUNE_VERSION} · Your local assistant`,
  description: "Your local assistant with hands-free wake phrases, Whisper voice input and a female system voice.",
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return <html lang="en"><body>{children}</body></html>;
}
