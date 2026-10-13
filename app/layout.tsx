import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "June v0.3.5 · Your local assistant",
  description: "A local assistant with a Python backend, Whisper voice input and a female system voice.",
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return <html lang="en"><body>{children}</body></html>;
}
