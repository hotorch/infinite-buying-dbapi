"use client";

import { useState } from "react";
import { ROLE_META, type TradeRole } from "@/lib/types";

type Props = {
  visibleRoles: ReadonlySet<TradeRole>;
  onToggleRole: (role: TradeRole) => void;
  onShowAll: () => void;
  onHideAll: () => void;
};

const basics = [
  { symbol: "▥", label: "하루 가격", description: "초록은 상승일, 빨강은 하락일", className: "candle" },
  { symbol: "━", label: "내 평균가격", description: "현재 보유 주식의 평균 매수가", className: "average" },
  { symbol: "★", label: "별가격", description: "별지점 주문을 계산하는 기준 가격", className: "star" },
  { symbol: "B", label: "매수", description: "주식을 산 날", className: "buy" },
  { symbol: "S", label: "매도", description: "주식을 판 날", className: "sell" },
  { symbol: "↻", label: "사이클 완료", description: "한 사이클이 끝난 날짜와 순번", className: "cycle" },
];

const roles = Object.keys(ROLE_META) as TradeRole[];

export function ChartLegend({ visibleRoles, onToggleRole, onShowAll, onHideAll }: Props) {
  const [hint, setHint] = useState("표시할 체결 종류를 선택하면 차트에 해당 마커만 나타납니다.");
  return (
    <div className="legendWrap">
      <div className="legendHeader"><strong>차트 표시</strong><span>{visibleRoles.size}개 체결 마커 표시 중</span></div>
      <div className="legendList">
        {basics.map((item) => <button type="button" className="legendItem" key={item.label} onMouseEnter={() => setHint(item.description)} onFocus={() => setHint(item.description)}><span className={`legendSymbol ${item.className}`}>{item.symbol}</span><span><b>{item.label}</b><small>{item.description}</small></span></button>)}
      </div>
      <div className="markerHeader"><div><strong>체결 마커 선택</strong><small>선택한 종류만 그래프에 표시됩니다.</small></div><div><button type="button" onClick={onShowAll}>전체 선택</button><button type="button" onClick={onHideAll}>모두 해제</button></div></div>
      <div className="detailLegend">{roles.map((role) => { const item = ROLE_META[role]; const selected = visibleRoles.has(role); return <button type="button" className={selected ? "roleLegend selected" : "roleLegend"} aria-pressed={selected} key={role} onClick={() => onToggleRole(role)} onMouseEnter={() => setHint(item.description)} onFocus={() => setHint(item.description)}><span className="markerCheck" aria-hidden="true">{selected ? "✓" : ""}</span><span className={`tradeBadge ${item.tone}`}>{item.symbol}</span><span><b>{item.label}</b><small>{item.description}</small></span></button>; })}</div>
      <p className="legendHint" aria-live="polite">{hint}</p>
    </div>
  );
}
