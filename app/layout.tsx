import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "June v0.4 · Your local assistant",
  description: "Your local assistant with hands-free wake phrases, Whisper voice input and a female system voice.",
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return <html lang="en"><body>{children}</body></html>;
}
