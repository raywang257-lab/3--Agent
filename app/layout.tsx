import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "TrendScope 热点决策台",
  description: "从公开信息源发现、验证并整理高价值热点的智能分析工作台。",
  openGraph: {
    title: "TrendScope 热点决策台",
    description: "从热点发现，到行动决策。",
    images: [{ url: "/og.png", width: 1200, height: 630 }],
  },
  twitter: {
    card: "summary_large_image",
    title: "TrendScope 热点决策台",
    description: "趋势、证据、传播路径与建议动作。",
    images: ["/og.png"],
  },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="zh-CN"><body>{children}</body></html>;
}
