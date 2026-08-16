import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import Sidebar from "@/components/layout/Sidebar";
import AppMain from "@/components/layout/AppMain";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Loom Dashboard",
  description: "AI-native automation workflow engine",
  viewport: "width=device-width, initial-scale=1, maximum-scale=1",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className={inter.className}>
        <Sidebar />
        <AppMain>{children}</AppMain>
      </body>
    </html>
  );
}
