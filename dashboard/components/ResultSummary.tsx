import { money, percent } from "@/lib/format";
import type { Summary } from "@/lib/types";

type SummaryCard = { label: string; technical?: string; value: string; note: string; tone: string };

export function ResultSummary({ summary }: { summary: Summary }) {
  const benchmarkCards: SummaryCard[] = summary.benchmarks.map((benchmark) => ({
    label: `${benchmark.symbol} 대비 성과`,
    value: percent(benchmark.excess_return),
    note: `${benchmark.symbol} 매수·보유 ${percent(benchmark.return)}`,
    tone: benchmark.excess_return >= 0 ? "positive" : "negative",
  }));
  const cards: SummaryCard[] = [
    { label: "총수익률", value: percent(summary.total_return), note: "시작 자본 대비", tone: summary.total_return >= 0 ? "positive" : "negative" },
    { label: "연평균 수익률", technical: "CAGR", value: percent(summary.cagr), note: "매년 같은 비율로 환산", tone: summary.cagr >= 0 ? "positive" : "negative" },
    { label: "최대 낙폭", technical: "MDD", value: percent(summary.mdd), note: "고점에서 가장 크게 하락", tone: "negative" },
    { label: "최종자산", value: money.format(summary.final_equity), note: `${summary.trading_days.toLocaleString("ko-KR")} 거래일`, tone: "plain" },
    ...benchmarkCards,
    { label: "완료 사이클", value: `${summary.cycle_count}회`, note: `매수 ${summary.buy_count} · 매도 ${summary.sell_count}`, tone: "plain" },
  ];
  return (
    <section aria-labelledby="summary-title">
      <div className="sectionTitleRow"><div><p className="sectionKicker">RESULT SNAPSHOT</p><h2 id="summary-title">핵심 결과</h2></div><p>전략과 동일 ETF·기초 ETF·시장 매수·보유를 같은 기간으로 비교합니다.</p></div>
      <div className="summaryGrid">
        {cards.map((card) => <article className="summaryCard" key={card.label}><div className="cardLabel">{card.label}{card.technical && <small>({card.technical})</small>}</div><strong className={card.tone}>{card.value}</strong><p>{card.note}</p></article>)}
      </div>
    </section>
  );
}
