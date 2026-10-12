import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "June v0.2 · Your local assistant",
  description: "A local assistant with an animated, audio-reactive face.",
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return <html lang="en"><body>{children}</body></html>;
}
