import type { BacktestRequest } from "@/lib/types";

type Props = {
  value: BacktestRequest;
  maxDate: string;
  onChange: (next: BacktestRequest) => void;
  onSubmit: () => void;
  onCollect: () => void;
  running: boolean;
  collecting: boolean;
  collectionStatus: string;
  progress: number;
};

const steps = ["데이터 확인", "전략 계산", "결과 준비"];
const MAX_CAPITAL = 3000;

export function BacktestForm({ value, maxDate, onChange, onSubmit, onCollect, running, collecting, collectionStatus, progress }: Props) {
  const update = (field: keyof BacktestRequest, next: string | number) => onChange({ ...value, [field]: next });
  const capitalInvalid = !Number.isFinite(value.capital) || value.capital < 1 || value.capital > MAX_CAPITAL;
  return (
    <section className="controlPanel" aria-labelledby="control-title">
      <div className="panelHeading">
        <div>
          <p className="sectionKicker">BACKTEST SETUP</p>
          <h2 id="control-title">조건을 정해 보세요</h2>
        </div>
        <p>추천 기본값이 입력되어 있어 바로 실행할 수 있습니다.</p>
      </div>
      <div className="formGrid">
        <label>
          <span>종목</span>
          <select value={value.symbol} aria-label="종목" onChange={(event) => update("symbol", event.target.value)}>
            <option value="TQQQ">TQQQ</option>
            <option value="SOXL">SOXL</option>
          </select>
        </label>
        <label>
          <span>분할 수</span>
          <select value={value.division_count} onChange={(event) => update("division_count", Number(event.target.value))}>
            <option value={20}>20분할</option>
            <option value={30}>30분할</option>
            <option value={40}>40분할</option>
          </select>
        </label>
        <label>
          <span>초기 자본 (USD)</span>
          <div className="currencyInput"><b>$</b><input type="number" min={1} max={MAX_CAPITAL} step={100} value={value.capital} aria-invalid={capitalInvalid} aria-describedby="capital-help" onChange={(event) => update("capital", Number(event.target.value))} /></div>
          <small id="capital-help" className={capitalInvalid ? "fieldHelp error" : "fieldHelp"}>{capitalInvalid ? "$1~$3,000 사이로 입력해 주세요." : "최대 $3,000"}</small>
        </label>
        <label>
          <span>시작일</span>
          <input type="date" value={value.start_date} max={value.end_date} onChange={(event) => update("start_date", event.target.value)} />
        </label>
        <label>
          <span>종료일</span>
          <input type="date" value={value.end_date} min={value.start_date} max={maxDate} onChange={(event) => update("end_date", event.target.value)} />
        </label>
        <div className="actionButtons">
          <button className="collectButton" type="button" onClick={onCollect} disabled={running || collecting}>
            <span>{collecting ? "수집 중…" : "최신 캔들 수집"}</span>
            <span aria-hidden="true">↻</span>
          </button>
          <button className="runButton" type="button" onClick={onSubmit} disabled={running || collecting || capitalInvalid}>
            <span>{running ? "계산 중" : "백테스트 실행"}</span>
            <span aria-hidden="true">{running ? "···" : "→"}</span>
          </button>
        </div>
      </div>
      {collectionStatus && <p className="collectionStatus" role="status" aria-live="polite">{collectionStatus}</p>}
      {running && (
        <div className="progress" role="status" aria-live="polite">
          {steps.map((step, index) => (
            <div className={index <= progress ? "progressStep active" : "progressStep"} key={step}>
              <span>{index < progress ? "✓" : index + 1}</span>{step}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
