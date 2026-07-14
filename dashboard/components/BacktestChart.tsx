"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  AreaSeries,
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  createChart,
  createSeriesMarkers,
  LineSeries,
  LineStyle,
  type IChartApi,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type SeriesMarker,
  type Time,
} from "lightweight-charts";
import { money, number, percent, shortDate } from "@/lib/format";
import { ROLE_META, type DailyRow, type TradeEvent, type TradeRole } from "@/lib/types";

type Props = {
  daily: DailyRow[];
  events: TradeEvent[];
  visibleRoles: ReadonlySet<TradeRole>;
  selectedDate: string;
  capital: number;
  onSelectDate: (date: string) => void;
};

type Tooltip = { day: DailyRow; events: TradeEvent[]; x: number; y: number } | null;

export function BacktestChart({ daily, events, visibleRoles, selectedDate, capital, onSelectDate }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const markersRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  const selectRef = useRef(onSelectDate);
  const [tooltip, setTooltip] = useState<Tooltip>(null);
  selectRef.current = onSelectDate;

  const cycleBoundaries = useMemo(() => daily.flatMap((day, index) => {
    if (index === 0 || daily[index - 1].cycle_id === day.cycle_id) return [];
    return [{ date: day.date, number: Number(day.cycle_id.split("-")[1]) - 1 }];
  }), [daily]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const byDate = new Map(daily.map((day) => [day.date, day]));
    const eventsByDate = new Map<string, TradeEvent[]>();
    for (const event of events) eventsByDate.set(event.date, [...(eventsByDate.get(event.date) ?? []), event]);

    const chart = createChart(container, {
      autoSize: true,
      height: container.clientHeight,
      layout: { background: { type: ColorType.Solid, color: "#fffefb" }, textColor: "#687076", fontFamily: "Inter, Pretendard, Apple SD Gothic Neo, sans-serif", fontSize: 11, panes: { separatorColor: "#e6e7e2", separatorHoverColor: "#d2d5ce", enableResize: false } },
      grid: { vertLines: { color: "#eef0eb", style: LineStyle.Dotted }, horzLines: { color: "#eef0eb", style: LineStyle.Dotted } },
      crosshair: { mode: CrosshairMode.Normal, vertLine: { color: "#334155", width: 1, style: LineStyle.Dashed, labelBackgroundColor: "#172033" }, horzLine: { color: "#94a3b8", width: 1, style: LineStyle.Dotted, labelBackgroundColor: "#475569" } },
      rightPriceScale: { borderColor: "#dfe2dc", minimumWidth: 72 },
      timeScale: { borderColor: "#dfe2dc", timeVisible: false, rightOffset: 4, barSpacing: 7, minBarSpacing: 1.5, fixLeftEdge: true },
      localization: { locale: "ko-KR" },
    });
    chartRef.current = chart;

    const candles = chart.addSeries(CandlestickSeries, { upColor: "#1d9b72", downColor: "#dc5d5d", wickUpColor: "#1d9b72", wickDownColor: "#dc5d5d", borderVisible: false, priceLineVisible: false }, 0);
    candleRef.current = candles;
    const average = chart.addSeries(LineSeries, { color: "#2563eb", lineWidth: 2, priceLineVisible: false, lastValueVisible: false }, 0);
    const star = chart.addSeries(LineSeries, { color: "#e28a27", lineWidth: 2, lineStyle: LineStyle.Dashed, priceLineVisible: false, lastValueVisible: false }, 0);
    const target = chart.addSeries(LineSeries, { color: "#8b5cf6", lineWidth: 1, lineStyle: LineStyle.Dotted, priceLineVisible: false, lastValueVisible: false }, 0);
    const equity = chart.addSeries(LineSeries, { color: "#0f766e", lineWidth: 3, title: "내 자산", priceLineVisible: false }, 1);
    const benchmark = chart.addSeries(LineSeries, { color: "#94a3b8", lineWidth: 2, lineStyle: LineStyle.Dashed, title: "QQQ", priceLineVisible: false }, 1);
    const drawdown = chart.addSeries(AreaSeries, { lineColor: "#e05252", topColor: "rgba(224, 82, 82, 0.08)", bottomColor: "rgba(224, 82, 82, 0.34)", lineWidth: 2, priceLineVisible: false, lastValueVisible: false, priceFormat: { type: "percent", precision: 1, minMove: 0.1 } }, 2);

    candles.setData(daily.map((day) => ({ time: day.date, open: day.open, high: day.high, low: day.low, close: day.close })));
    average.setData(daily.map((day) => day.avg_cost == null ? ({ time: day.date }) : ({ time: day.date, value: day.avg_cost })));
    star.setData(daily.map((day) => day.star_price == null ? ({ time: day.date }) : ({ time: day.date, value: day.star_price })));
    target.setData(daily.map((day) => day.target_price == null ? ({ time: day.date }) : ({ time: day.date, value: day.target_price })));
    equity.setData(daily.map((day) => ({ time: day.date, value: day.equity })));
    benchmark.setData(daily.map((day) => ({ time: day.date, value: day.qqq_equity })));
    drawdown.setData(daily.map((day) => ({ time: day.date, value: day.drawdown * 100 })));

    markersRef.current = createSeriesMarkers(candles, []);
    const panes = chart.panes();
    panes[0]?.setStretchFactor(3.2);
    panes[1]?.setStretchFactor(1.45);
    panes[2]?.setStretchFactor(1);
    chart.timeScale().fitContent();

    const updateBoundaryPositions = () => {
      container.parentElement?.querySelectorAll<HTMLElement>("[data-cycle-date]").forEach((line) => {
        const x = chart.timeScale().timeToCoordinate(line.dataset.cycleDate as Time);
        line.style.display = x == null ? "none" : "block";
        if (x != null) line.style.left = `${x}px`;
      });
    };
    const crosshairHandler = (parameter: { time?: Time; point?: { x: number; y: number } }) => {
      if (!parameter.time || !parameter.point) {
        setTooltip(null);
        return;
      }
      const date = timeKey(parameter.time);
      const day = byDate.get(date);
      if (!day) return;
      setTooltip({ day, events: eventsByDate.get(date) ?? [], x: parameter.point.x, y: parameter.point.y });
    };
    const clickHandler = (parameter: { time?: Time }) => {
      if (!parameter.time) return;
      const date = timeKey(parameter.time);
      if (byDate.has(date)) selectRef.current(date);
    };
    chart.subscribeCrosshairMove(crosshairHandler);
    chart.subscribeClick(clickHandler);
    chart.timeScale().subscribeVisibleLogicalRangeChange(updateBoundaryPositions);
    requestAnimationFrame(updateBoundaryPositions);

    return () => {
      chart.unsubscribeCrosshairMove(crosshairHandler);
      chart.unsubscribeClick(clickHandler);
      chart.timeScale().unsubscribeVisibleLogicalRangeChange(updateBoundaryPositions);
      chart.remove();
      chartRef.current = null;
      candleRef.current = null;
      markersRef.current = null;
    };
  }, [daily, events]);

  useEffect(() => {
    const markers: SeriesMarker<Time>[] = events.filter((event) => visibleRoles.has(event.role)).map((event) => {
      const meta = ROLE_META[event.role];
      return {
        time: event.date,
        position: event.side === "BUY" ? "belowBar" : "aboveBar",
        color: event.side === "BUY" ? "#2563eb" : "#d94c4c",
        shape: event.side === "BUY" ? "circle" : "square",
        text: meta.symbol,
        size: 0.8,
      };
    });
    markersRef.current?.setMarkers(markers);
  }, [events, visibleRoles]);

  useEffect(() => {
    const chart = chartRef.current;
    const candles = candleRef.current;
    const day = daily.find((row) => row.date === selectedDate);
    if (chart && candles && day) chart.setCrosshairPosition(day.close, day.date, candles);
  }, [daily, selectedDate]);

  const moveDate = (direction: number) => {
    const current = Math.max(0, daily.findIndex((day) => day.date === selectedDate));
    const next = daily[Math.min(daily.length - 1, Math.max(0, current + direction))];
    if (next) onSelectDate(next.date);
  };

  return (
    <div className="chartShell">
      <div
        className="chartViewport"
        tabIndex={0}
        aria-label="백테스트 차트. 왼쪽과 오른쪽 화살표 키로 날짜를 이동할 수 있습니다."
        onKeyDown={(event) => {
          if (event.key === "ArrowLeft") { event.preventDefault(); moveDate(-1); }
          if (event.key === "ArrowRight") { event.preventDefault(); moveDate(1); }
          if (event.key === "Home") { event.preventDefault(); onSelectDate(daily[0].date); }
          if (event.key === "End") { event.preventDefault(); onSelectDate(daily[daily.length - 1].date); }
        }}
      >
        <div ref={containerRef} className="chartCanvas" />
        <div className="paneLabel priceLabel"><b>가격 · 체결</b><span>USD</span></div>
        <div className="paneLabel assetLabel"><b>자산 · QQQ</b><span>USD</span></div>
        <div className="paneLabel drawdownLabel"><b>낙폭</b><span>%</span></div>
        <div className="cycleLayer" aria-hidden="true">{cycleBoundaries.map((boundary) => <div className="cycleLine" data-cycle-date={boundary.date} key={boundary.date}><span>↻ {boundary.number}</span></div>)}</div>
        {tooltip && <ChartTooltip tooltip={tooltip} capital={capital} width={containerRef.current?.clientWidth ?? 1000} height={containerRef.current?.clientHeight ?? 700} />}
      </div>
      <p className="chartKeyboardHint">차트를 클릭하거나 <kbd>←</kbd><kbd>→</kbd> 키로 날짜 선택 · 마우스 이동은 툴팁만 보여줍니다.</p>
    </div>
  );
}

function ChartTooltip({ tooltip, capital, width, height }: { tooltip: NonNullable<Tooltip>; capital: number; width: number; height: number }) {
  const { day, events, x, y } = tooltip;
  const left = Math.min(Math.max(12, x + 20), width - 300);
  const top = Math.min(Math.max(12, y + 18), height - 265);
  return (
    <div className="chartTooltip" style={{ left, top }}>
      <div className="tooltipDate"><b>{shortDate(day.date)}</b><span>{day.cycle_id.replace("cycle-", "사이클 ")}</span></div>
      <div className="tooltipGroup"><strong>가격</strong><p>시 {money.format(day.open)} · 고 {money.format(day.high)}</p><p>저 {money.format(day.low)} · 종 {money.format(day.close)}</p></div>
      <div className="tooltipGroup"><strong>내 상태</strong><p>평균 {day.avg_cost == null ? "-" : money.format(day.avg_cost)} · 별 {day.star_price == null ? "-" : money.format(day.star_price)}</p><p>T {number.format(day.t)} · {day.quantity}주 · 총 {money.format(day.equity)}</p></div>
      <div className="tooltipGroup"><strong>비교</strong><p>전략 {percent(day.equity / capital - 1)} · QQQ {percent(day.qqq_equity / capital - 1)} · 낙폭 {percent(day.drawdown)}</p></div>
      <div className="tooltipGroup"><strong>오늘의 체결</strong><p>{events.length ? events.map((event) => `${ROLE_META[event.role].symbol} ${ROLE_META[event.role].label}`).join(" · ") : "체결 없음"}</p></div>
    </div>
  );
}

function timeKey(time: Time) {
  if (typeof time === "string") return time;
  if (typeof time === "number") return new Date(time * 1000).toISOString().slice(0, 10);
  return `${time.year}-${String(time.month).padStart(2, "0")}-${String(time.day).padStart(2, "0")}`;
}
