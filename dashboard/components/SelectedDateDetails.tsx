import { money, number, percent, shortDate } from "@/lib/format";
import { ROLE_META, type DailyRow, type TradeEvent } from "@/lib/types";

export function SelectedDateDetails({ day, events, capital }: { day: DailyRow; events: TradeEvent[]; capital: number }) {
  return (
    <section className="selectedDetails" aria-labelledby="selected-date-title">
      <div className="detailHeading"><div><p className="sectionKicker">SELECTED DATE</p><h3 id="selected-date-title">{shortDate(day.date)} 상세</h3></div><span>{day.cycle_id.replace("cycle-", "사이클 ")}</span></div>
      <div className="detailColumns">
        <div><h4>가격</h4><dl><div><dt>시가</dt><dd>{money.format(day.open)}</dd></div><div><dt>고가</dt><dd>{money.format(day.high)}</dd></div><div><dt>저가</dt><dd>{money.format(day.low)}</dd></div><div><dt>종가</dt><dd>{money.format(day.close)}</dd></div></dl></div>
        <div><h4>내 상태</h4><dl><div><dt>평균가격</dt><dd>{day.avg_cost == null ? "-" : money.format(day.avg_cost)}</dd></div><div><dt>별가격</dt><dd>{day.star_price == null ? "-" : money.format(day.star_price)}</dd></div><div><dt>목표가격</dt><dd>{day.target_price == null ? "-" : money.format(day.target_price)}</dd></div><div><dt>T · 보유수량</dt><dd>{number.format(day.t)} · {day.quantity}주</dd></div><div><dt>현금 · 총자산</dt><dd>{money.format(day.cash)} · {money.format(day.equity)}</dd></div></dl></div>
        <div><h4>비교</h4><dl><div><dt>전략 수익률</dt><dd>{percent(day.equity / capital - 1)}</dd></div>{Object.entries(day.benchmark_equities).map(([symbol, equity]) => <div key={symbol}><dt>{symbol} 매수·보유</dt><dd>{percent(equity / capital - 1)}</dd></div>)}<div><dt>현재 낙폭</dt><dd>{percent(day.drawdown)}</dd></div></dl></div>
        <div><h4>오늘의 체결</h4>{events.length ? <div className="eventCells">{events.map((event, index) => { const meta = ROLE_META[event.role]; return <span className="eventCell" key={`${event.role}-${index}`}><i className={`tradeBadge ${meta.tone}`}>{meta.symbol}</i><b>{meta.label}</b><small>{event.quantity}주 · {money.format(event.price)}</small></span>; })}</div> : <p className="emptyEvents">체결이 없는 날입니다.</p>}</div>
      </div>
    </section>
  );
}
