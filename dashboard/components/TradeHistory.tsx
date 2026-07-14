import { money, shortDate } from "@/lib/format";
import { ROLE_META, type TradeEvent } from "@/lib/types";

export function TradeHistory({ events, selectedDate, onSelectDate }: { events: TradeEvent[]; selectedDate: string; onSelectDate: (date: string) => void }) {
  return (
    <details className="tradeHistory">
      <summary><span><b>체결 내역</b><small>총 {events.length.toLocaleString("ko-KR")}건 · 눌러서 펼치기</small></span><span aria-hidden="true">＋</span></summary>
      <div className="tableScroll">
        <table>
          <thead><tr><th>날짜</th><th>사이클</th><th>체결 종류</th><th>수량</th><th>체결가</th><th>수수료</th></tr></thead>
          <tbody>{events.map((event, index) => { const meta = ROLE_META[event.role]; const newCycle = index === 0 || events[index - 1].cycle_id !== event.cycle_id; return <tr key={`${event.date}-${event.role}-${index}`} className={`${selectedDate === event.date ? "selected" : ""} ${newCycle ? "cycleStart" : ""}`} onClick={() => onSelectDate(event.date)} tabIndex={0} onKeyDown={(keyboardEvent) => { if (keyboardEvent.key === "Enter" || keyboardEvent.key === " ") onSelectDate(event.date); }}><td>{shortDate(event.date)}</td><td>{event.cycle_id.replace("cycle-", "#")}</td><td><span className={`tradeBadge ${meta.tone}`}>{meta.symbol}</span><b>{meta.label}</b></td><td>{event.quantity}주</td><td>{money.format(event.price)}</td><td>{money.format(event.fee)}</td></tr>; })}</tbody>
        </table>
      </div>
    </details>
  );
}
