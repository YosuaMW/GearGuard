import type { Metadata } from "next";
import "./globals.css";
import { Header } from "@/components/Header";
import { PlantProvider } from "@/lib/plant";

export const metadata: Metadata = {
  title: "SiagaMesin",
  description: "Machine downtime logging and predictive maintenance for small factories",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full">
        <PlantProvider>
          <Header />
          <main className="mx-auto w-full max-w-[1280px] px-4 pb-12 sm:px-6">{children}</main>
        </PlantProvider>
      </body>
    </html>
  );
}
