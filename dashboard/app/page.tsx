"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { BacktestChart } from "@/components/BacktestChart";
import { BacktestForm } from "@/components/BacktestForm";
import { ChartLegend } from "@/components/ChartLegend";
import { ResultSummary } from "@/components/ResultSummary";
import { RegimeWeather } from "@/components/RegimeWeather";
import { SelectedDateDetails } from "@/components/SelectedDateDetails";
import { TradeHistory } from "@/components/TradeHistory";
import { money } from "@/lib/format";
import { ROLE_META, type ApiError, type BacktestRequest, type BacktestResult, type MarketDataCollection, type TradeRole } from "@/lib/types";

const TODAY = dateInSeoul();

const DEFAULT_REQUEST: BacktestRequest = {
  symbol: "TQQQ",
  division_count: 40,
  capital: 3000,
  start_date: yearsBefore(TODAY, 5),
  end_date: TODAY,
};

export default function DashboardPage() {
  const [request, setRequest] = useState(DEFAULT_REQUEST);
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [selectedDate, setSelectedDate] = useState("");
  const [running, setRunning] = useState(false);
  const [collecting, setCollecting] = useState(false);
  const [collectionStatus, setCollectionStatus] = useState("");
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState("");
  const [visibleRoles, setVisibleRoles] = useState<ReadonlySet<TradeRole>>(() => new Set(["initial_buy", "target_sell"]));

  const toggleRole = useCallback((role: TradeRole) => {
    setVisibleRoles((current) => {
      const next = new Set(current);
      if (next.has(role)) next.delete(role);
      else next.add(role);
      return next;
    });
  }, []);
  const showAllRoles = useCallback(() => setVisibleRoles(new Set(Object.keys(ROLE_META) as TradeRole[])), []);
  const hideAllRoles = useCallback(() => setVisibleRoles(new Set()), []);

  const run = useCallback(async (override?: BacktestRequest) => {
    if (running) return;
    const activeRequest = override ?? request;
    setRunning(true);
    setProgress(0);
    setError("");
    const timers = [window.setTimeout(() => setProgress(1), 280), window.setTimeout(() => setProgress(2), 620)];
    const minimumDelay = new Promise((resolve) => window.setTimeout(resolve, 800));
    try {
      const response = await fetch("/api/backtest", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(activeRequest) });
      const payload = (await response.json()) as BacktestResult | ApiError;
      await minimumDelay;
      if (!response.ok || "error" in payload) throw new Error("error" in payload ? payload.error.message : "백테스트를 완료하지 못했습니다.");
      setResult(payload);
      setSelectedDate(payload.daily[payload.daily.length - 1]?.date ?? "");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "백테스트를 완료하지 못했습니다.");
    } finally {
      timers.forEach(window.clearTimeout);
      setRunning(false);
    }
  }, [request, running]);

  const collect = useCallback(async () => {
    if (collecting || running) return;
    setCollecting(true);
    setCollectionStatus("최근 완료된 미국 거래일까지 확인하고 있습니다…");
    setError("");
    try {
      const response = await fetch("/api/market-data/collect", { method: "POST" });
      const payload = (await response.json()) as MarketDataCollection | ApiError;
      if (!response.ok || "error" in payload) throw new Error("error" in payload ? payload.error.message : "캔들 수집에 실패했습니다.");
      const nextRequest = { ...request, end_date: payload.latest_completed_session };
      setRequest(nextRequest);
      setCollectionStatus(
        payload.updated
          ? `TQQQ·SOXL·QQQ 캔들 ${payload.added.toLocaleString()}건을 추가해 ${payload.latest_completed_session}까지 채웠습니다.`
          : `이미 최신 상태입니다. 마지막 완료 거래일은 ${payload.latest_completed_session}입니다.`,
      );
      await run(nextRequest);
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "캔들 수집에 실패했습니다.";
      setCollectionStatus("");
      setError(message);
    } finally {
      setCollecting(false);
    }
  }, [collecting, request, run, running]);

  useEffect(() => { void run(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const selectedDay = useMemo(() => result?.daily.find((day) => day.date === selectedDate) ?? result?.daily.at(-1), [result, selectedDate]);
  const selectedEvents = useMemo(() => result?.events.filter((event) => event.date === selectedDay?.date) ?? [], [result, selectedDay]);
  const selectedWeather = useMemo(() => {
    if (!result || !selectedDay) return undefined;
    for (let index = result.weather_daily.length - 1; index >= 0; index -= 1) {
      if (result.weather_daily[index].date <= selectedDay.date) return result.weather_daily[index];
    }
    return undefined;
  }, [result, selectedDay]);

  const downloadJson = () => result && downloadBlob(JSON.stringify(result, null, 2), `${result.request.symbol.toLowerCase()}-backtest-${result.request.start_date}-${result.request.end_date}.json`, "application/json;charset=utf-8");
  const downloadCsv = () => {
    if (!result) return;
    const headers = ["date", "cycle_id", "side", "role", "quantity", "price", "fee", "reason_code"];
    const rows = result.events.map((event) => headers.map((key) => csvCell(String(event[key as keyof typeof event]))).join(","));
    downloadBlob(`\ufeff${headers.join(",")}\r\n${rows.join("\r\n")}`, `${result.request.symbol.toLowerCase()}-trades-${result.request.start_date}-${result.request.end_date}.csv`, "text/csv;charset=utf-8");
  };

  return (
    <main>
      <header className="hero">
        <div className="heroInner">
          <div className="brand"><span className="brandMark">∞</span><span>INFINITE BUYING LAB</span></div>
          <div className="heroCopy"><p className="heroEyebrow">PURE V4 · BEGINNER BACKTEST</p><h1>숫자보다 먼저,<br /><em>흐름을 이해하는 백테스트</em></h1><p>순수 무한매수 V4가 언제 사고팔았는지, 내 자산이 어떻게 움직였는지 한 화면에서 차근차근 확인하세요.</p></div>
          <div className="safetyBadge"><span aria-hidden="true">●</span><div><b>안전한 로컬 분석</b><small>오프라인 데이터 · 실주문 없음</small></div></div>
        </div>
      </header>

      <div className="pageContent">
        <BacktestForm value={request} maxDate={TODAY} onChange={setRequest} onSubmit={() => void run()} onCollect={() => void collect()} running={running} collecting={collecting} collectionStatus={collectionStatus} progress={progress} />
        {error && <div className="errorBanner" role="alert"><b>실행할 수 없습니다.</b><span>{error}</span></div>}

        {result && !running && (
          <div className="results">
            <div className="assumptionStrip"><span><b>{result.request.symbol}</b></span><span>{result.assumptions.effective_dates.start} → {result.assumptions.effective_dates.end}</span><span>{result.request.division_count}분할</span><span>{money.format(result.request.capital)}</span><span>수수료 {(result.assumptions.fee_rate * 100).toFixed(2)}%</span><span>수정 OHLC</span></div>
            <RegimeWeather
              weather={selectedWeather}
              symbol={result.request.symbol}
              selectedDate={selectedDay?.date ?? ""}
              latestAvailableDate={result.weather_daily.at(-1)?.date ?? ""}
            />
            <ResultSummary summary={result.summary} />

            <section className="chartSection" aria-labelledby="chart-title">
              <div className="sectionTitleRow"><div><p className="sectionKicker">THE FULL STORY</p><h2 id="chart-title">가격과 내 자산의 흐름</h2></div><div className="downloadActions"><button type="button" onClick={downloadJson}>결과 JSON ↓</button><button type="button" onClick={downloadCsv}>체결 CSV ↓</button></div></div>
              <div className="chartGuide"><span className="guideIcon">i</span><div><b>차트 읽는 법</b><ol><li>초록·빨강 막대는 그날의 가격 움직임입니다.</li><li>파란 선은 내가 산 평균가격, 별표는 별지점 주문이 발생한 날입니다.</li><li>마우스는 툴팁만, 클릭은 날씨와 상세 날짜를 바꿉니다.</li></ol></div></div>
              <ChartLegend visibleRoles={visibleRoles} onToggleRole={toggleRole} onShowAll={showAllRoles} onHideAll={hideAllRoles} />
              <BacktestChart daily={result.daily} events={result.events} visibleRoles={visibleRoles} selectedDate={selectedDay?.date ?? ""} capital={result.request.capital} onSelectDate={setSelectedDate} />
            </section>

            {selectedDay && <SelectedDateDetails day={selectedDay} events={selectedEvents} capital={result.request.capital} />}
            <TradeHistory events={result.events} selectedDate={selectedDay?.date ?? ""} onSelectDate={setSelectedDate} />
          </div>
        )}

        <aside className="riskNotice"><span aria-hidden="true">!</span><p><b>투자 유의사항</b> 과거의 백테스트 결과는 미래의 수익이나 성과를 보장하지 않습니다. 수수료 0.04%를 제외한 슬리피지와 세금은 반영되지 않았습니다.</p></aside>
        <footer><span>순수 무한매수 V4 · 로컬 백테스트</span><span>차트 제공: <a href="https://www.tradingview.com/lightweight-charts/" target="_blank" rel="noreferrer">TradingView Lightweight Charts</a></span></footer>
      </div>
    </main>
  );
}

function downloadBlob(content: string, filename: string, type: string) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

function csvCell(value: string) {
  return /[",\n]/.test(value) ? `"${value.replaceAll('"', '""')}"` : value;
}

function dateInSeoul() {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${values.year}-${values.month}-${values.day}`;
}

function yearsBefore(value: string, years: number) {
  const date = new Date(`${value}T00:00:00Z`);
  date.setUTCFullYear(date.getUTCFullYear() - years);
  return date.toISOString().slice(0, 10);
}
