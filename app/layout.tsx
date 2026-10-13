import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "June v0.3 · Your local assistant",
  description: "A local text assistant with browser listening and a female speaking voice.",
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return <html lang="en"><body>{children}</body></html>;
}
