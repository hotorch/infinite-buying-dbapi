import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "순수 무한매수 V4 백테스트",
  description: "TQQQ·SOXL 순수 무한매수 V4를 오프라인 수정주가 데이터로 이해하기 쉽게 확인하는 로컬 대시보드",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
