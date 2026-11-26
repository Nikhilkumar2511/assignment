import type { Metadata, Viewport } from "next";
import "./globals.css";
import SwRegister from "@/components/SwRegister";

export const metadata: Metadata = {
  title: "MindReader",
  description: "Think of a famous person or character. MindReader asks questions and guesses who it is. Free, no sign-up.",
  manifest: "/manifest.webmanifest",
  icons: { icon: "/icons/icon-192.png", apple: "/icons/apple-touch-icon.png" },
  appleWebApp: { capable: true, title: "MindReader", statusBarStyle: "black-translucent" },
};

export const viewport: Viewport = {
  themeColor: "#140a3a",
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  colorScheme: "dark",
};

// Applies saved language, contrast and motion before first paint, so nothing flashes.
const boot = `try{if(localStorage.getItem("mr.contrast")==="1")document.documentElement.dataset.contrast="high";
if(localStorage.getItem("mr.motion")==="0")document.documentElement.dataset.motion="off"}catch(e){}`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: boot }} />
      </head>
      <body>
        {children}
        <SwRegister />
      </body>
    </html>
  );
}
