import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "June v0.1 · Your local assistant",
  description: "A personal text assistant, built one phase at a time.",
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return <html lang="en"><body>{children}</body></html>;
}
