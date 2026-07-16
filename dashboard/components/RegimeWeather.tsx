import { percent, shortDate } from "@/lib/format";
import type { RegimeWeatherRow, WeatherResearch, WeatherState } from "@/lib/types";

const WEATHER_ORDER: WeatherState[] = ["strong_green", "early_thaw", "green", "yellow", "orange", "red"];

const WEATHER_META: Record<WeatherState, { icon: string; label: string; regime: string; action: string; summary: string }> = {
  strong_green: {
    icon: "☀",
    label: "아주 좋은 날",
    regime: "strong_green",
    action: "정상 무한매수 후보",
    summary: "추세, 모멘텀, 상대강도, 과열도와 유동성이 모두 강한 구간입니다.",
  },
  early_thaw: {
    icon: "🌤",
    label: "좋은 날",
    regime: "early thaw",
    action: "1분할 탐색, 최대 2분할",
    summary: "폭풍 뒤 50일선을 회복하고 모멘텀과 상대강도가 막 양전환한 구간입니다.",
  },
  green: {
    icon: "⛅",
    label: "괜찮은 날",
    regime: "green",
    action: "정상 신규 진입은 대기",
    summary: "기본 추세 조건은 통과했지만 strong_green의 강한 수치 기준에는 아직 못 미칩니다.",
  },
  yellow: {
    icon: "☁",
    label: "조심스러운 날",
    regime: "yellow",
    action: "추가매수는 절반 크기",
    summary: "큰 추세 붕괴는 아니지만 과열, 모멘텀 또는 상대강도 경고가 남아 있습니다.",
  },
  orange: {
    icon: "☂",
    label: "안 좋은 날",
    regime: "orange",
    action: "신규와 추가매수 중단",
    summary: "50일선, 추세 템플릿, 52주 위치 또는 유동성 조건이 무너진 스트레스 구간입니다.",
  },
  red: {
    icon: "⚡",
    label: "매우 안 좋은 날",
    regime: "red",
    action: "기존 원칙에 따라 청산",
    summary: "200일선과 장기 이동평균 구조가 무너진 하드 브레이크 구간입니다.",
  },
};

type Props = {
  weather?: RegimeWeatherRow;
  research?: WeatherResearch;
  symbol: "TQQQ" | "SOXL";
  selectedDate: string;
  latestAvailableDate: string;
};

export function RegimeWeather({ weather, research, symbol, selectedDate, latestAvailableDate }: Props) {
  if (!weather) return <MissingWeather selectedDate={selectedDate} symbol={symbol} />;

  const meta = WEATHER_META[weather.weather_state];
  const isLatestWeather = weather.date === latestAvailableDate;
  const isFallback = weather.date !== selectedDate;
  const chaseWarning = weather.regime === "strong_green" && (weather.signal_distance_50 ?? 0) >= 0.05;
  const signal = weather.signal_symbol;
  const benchmark = weather.benchmark_symbol ?? "SPY";
  const reasonLabels = weather.reasons.map((reason) => reasonLabel(reason, signal, symbol, benchmark));

  return (
    <section className={`weatherSection weatherTone-${weather.weather_state}`} aria-labelledby="weather-title">
      <div className="weatherHeading">
        <div>
          <h2 id="weather-title">선택한 날짜의 무한매수 날씨</h2>
          <p>{isFallback
            ? `${shortDate(selectedDate)} 날씨 데이터가 없어 ${shortDate(weather.date)} 기준 최신 날씨를 유지합니다. ${shortDate(weather.signal_date)} 종가 신호를 사용합니다.`
            : `${shortDate(weather.date)} 매매에 쓸 수 있었던 ${shortDate(weather.signal_date)} 종가 신호입니다.`}</p>
        </div>
        <div className="weatherHeadingBadges">
          {isFallback && <span className="weatherDate">최근 날씨 유지</span>}
          {!isFallback && isLatestWeather && <span className="weatherDate">최신 날씨</span>}
          <span className="weatherDate">D-1 판정</span>
        </div>
      </div>

      <div className="historyCaveat" role="note">
        <b>과거 관측 기록이지 미래 예보가 아닙니다.</b>
        <span>이 날씨는 그날까지의 가격으로 과거 구간을 분류한 연구용 표시입니다. 과거에 이런 경향이 있었을 뿐, 다음 날씨와 실제 수익은 알 수 없습니다.</span>
      </div>

      <div className="weatherCurrent">
        <div className="weatherHero">
          <span className="weatherIcon" aria-hidden="true">{meta.icon}</span>
          <div>
            <span className="weatherRegime">{meta.regime}</span>
            <h3>{meta.label}</h3>
            <b>{chaseWarning ? "좋지만 추격은 줄일 때" : meta.action}</b>
            <p>{chaseWarning ? `${symbol}이 50일선 위 5-8% 구간이면 과거 평균이 둔화되어 첫 주문 0.5배 또는 보류 후보입니다.` : meta.summary}</p>
          </div>
        </div>

        <dl className="weatherMetrics">
          <Metric label="레짐 점수" value={weather.score.toFixed(3)} note="strong 기준 0.200" pass={weather.score >= 0.2} />
          <Metric label={`${signal} 3개월`} value={formatPercent(weather.signal_return_3m)} note="strong 기준 +8%" pass={(weather.signal_return_3m ?? -1) >= 0.08} />
          <Metric label={`${signal} 6개월`} value={formatPercent(weather.signal_return_6m)} note="strong 기준 +12%" pass={(weather.signal_return_6m ?? -1) >= 0.12} />
          <Metric label={`${benchmark} 대비 RS`} value={formatPercent(weather.signal_rs)} note="strong 기준 +8%" pass={(weather.signal_rs ?? -1) >= 0.08} />
          <Metric label="50일선 이격" value={formatPercent(weather.signal_distance_50)} note="strong 상한 +8%" pass={(weather.signal_distance_50 ?? 1) <= 0.08} />
        </dl>
      </div>

      {reasonLabels.length > 0 && (
        <div className="weatherReasons">
          <b>오늘 이 날씨가 된 핵심 이유</b>
          <div>{reasonLabels.map((reason) => <span key={reason}>{reason}</span>)}</div>
        </div>
      )}

      <div className="weatherScale" aria-label="무한매수 날씨 단계">
        {WEATHER_ORDER.map((state) => {
          const item = WEATHER_META[state];
          const active = state === weather.weather_state;
          return (
            <div className={active ? "weatherStep active" : "weatherStep"} aria-current={active ? "step" : undefined} key={state}>
              <span aria-hidden="true">{item.icon}</span>
              <b>{item.label}</b>
              <small>{item.regime}</small>
            </div>
          );
        })}
      </div>

      <div className="weatherMethod">
        <details>
          <summary>레짐 점수는 어떻게 계산하나요?</summary>
          <p><code>0.70 × (3개월×0.50 + 6개월×0.30 + 12개월×0.20) + RS×0.35 - 50일선 상방이격×0.15 + 유동성 보너스</code></p>
          <p>유동성 보너스는 {symbol} 달러 거래대금을 1억 달러로 나눈 값에 0.05를 곱하며 최대 0.05입니다. 현재 거래대금은 기본 하한의 {weather.trade_dollar_volume_multiple?.toFixed(1) ?? "?"}배입니다.</p>
        </details>

        <div className="regimeAccordion">
          {WEATHER_ORDER.map((state) => <RegimeExplanation key={state} state={state} current={state === weather.weather_state} symbol={symbol} signal={signal} benchmark={benchmark} />)}
        </div>
      </div>

      <div className="historyNotes">
        {research && research.sample_count > 0
          ? <div><b>{symbol} {meta.regime} 진입 표본</b><span>{research.through_date}까지 완료된 {research.sample_count}건의 {research.horizon_sessions}거래일 평균 {formatPercent(research.average_return)}, 승률 {formatPercent(research.win_rate)}, 최악 {formatPercent(research.worst_return)}입니다.</span></div>
          : <div><b>{symbol} 표본 부족</b><span>선택한 종료일까지 {weather.weather_state} 진입 후 60거래일이 모두 지난 독립 표본이 없습니다.</span></div>}
        <div><b>표본 계산 원칙</b><span>{symbol}의 해당 날씨 진입일 종가부터 60거래일 뒤 종가까지 계산하며, 다른 레버리지 ETF의 수익률을 대신 사용하지 않습니다.</span></div>
      </div>
    </section>
  );
}

function reasonLabel(reason: string, signal: "QQQ" | "SMH", symbol: "TQQQ" | "SOXL", benchmark: string) {
  const labels: Record<string, string> = {
    stage4_breakdown: "Stage 4 하락 구조",
    "50ma_below_150ma": "50일선이 150일선 아래",
    "200ma_not_rising": "200일선 상승 실패",
    close_below_200ma: "종가가 200일선 아래",
    signal_trend_template_failed: `${signal} 추세 템플릿 실패`,
    signal_200ma_not_rising: `${signal} 200일선 상승 실패`,
    not_30pct_above_52w_low: "52주 저점 대비 30% 미만",
    more_than_25pct_below_52w_high: "52주 고점 대비 25% 넘게 하락",
    close_below_50ma: "종가가 50일선 아래",
    leveraged_etf_liquidity_below_floor: `${symbol} 유동성 하한 미달`,
    extended_above_50ma: "50일선 상방 이격 과다",
    relative_strength_below_floor: `${benchmark} 대비 상대강도 부족`,
    three_month_momentum_not_positive: "3개월 모멘텀 비양수",
    six_month_momentum_not_positive: "6개월 모멘텀 비양수",
  };
  return labels[reason] ?? reason.replaceAll("_", " ");
}

function Metric({ label, value, note, pass }: { label: string; value: string; note: string; pass: boolean }) {
  return <div><dt>{label}</dt><dd>{value}</dd><small className={pass ? "metricPass" : ""}>{pass ? "기준 통과" : note}</small></div>;
}

function RegimeExplanation({ state, current, symbol, signal, benchmark }: { state: WeatherState; current: boolean; symbol: "TQQQ" | "SOXL"; signal: "QQQ" | "SMH"; benchmark: string }) {
  const meta = WEATHER_META[state];
  const criteria: Record<WeatherState, string> = {
    strong_green: `기본 추세 조건을 모두 통과하고 점수 0.20 이상, 3개월 +8% 이상, 6개월 +12% 이상, ${benchmark} 대비 RS +8% 이상, 50일선 상방 이격 +8% 이하, ${symbol} 거래대금이 기본 하한의 5배 이상일 때입니다.`,
    early_thaw: `green 또는 yellow에서 ${signal}이 상승 중인 50일선 위, 3개월 수익과 RS가 0-8%, 50일선 이격이 0-5%, 최근 60거래일 안에 orange 또는 red가 있었을 때입니다.`,
    green: "장단기 이동평균, 52주 위치, 유동성, 3개월과 6개월 모멘텀, RS 조건에 실패 이유가 없지만 strong_green의 강화 기준을 모두 채우지는 못한 상태입니다.",
    yellow: "red 하드 브레이크와 orange 추세 붕괴는 없지만, 과도한 50일선 이격이나 3개월·6개월 모멘텀 또는 RS 부족 같은 경고가 하나 이상 남은 상태입니다.",
    orange: `red 하드 브레이크는 아니지만 추세 템플릿, 200일선 상승, 52주 저·고점 위치, 50일선 방어 또는 ${symbol} 유동성 중 하나가 실패한 상태입니다.`,
    red: "Stage 4 구조, 50일선의 150일선 하향 이탈, 200일선 하락 또는 종가의 200일선 하향 이탈 중 하나가 발생한 상태입니다.",
  };
  return (
    <details open={current}>
      <summary><span aria-hidden="true">{meta.icon}</span><b>{meta.label}</b><small>{meta.action}</small></summary>
      <p>{criteria[state]}</p>
    </details>
  );
}

function MissingWeather({ selectedDate, symbol }: { selectedDate: string; symbol: "TQQQ" | "SOXL" }) {
  const message = `${selectedDate ? `${shortDate(selectedDate)}은` : "선택한 날짜는"} ${symbol === "SOXL" ? "SMH·SPY" : "QQQ·SPY"}를 포함한 220거래일 지표가 없어 날씨를 계산할 수 없습니다.`;
  return (
    <section className="weatherSection weatherMissing" aria-labelledby="weather-title">
      <div className="weatherHeading"><div><h2 id="weather-title">선택한 날짜의 무한매수 날씨</h2><p>{message}</p></div></div>
      <div className="historyCaveat"><b>미래를 채워 넣지 않습니다.</b><span>충분한 과거 데이터가 있는 날짜만 연구용 날씨를 표시합니다.</span></div>
    </section>
  );
}

function formatPercent(value: number | null) {
  return value == null ? "-" : percent(value, 1);
}
