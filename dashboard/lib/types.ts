export type BacktestRequest = {
  symbol: "TQQQ" | "SOXL";
  division_count: number;
  capital: number;
  start_date: string;
  end_date: string;
};

export type Summary = {
  total_return: number;
  cagr: number;
  mdd: number;
  final_equity: number;
  benchmark_return: number;
  excess_return: number;
  cycle_count: number;
  trading_days: number;
  buy_count: number;
  sell_count: number;
};

export type Assumptions = {
  ruleset_version: string;
  price_basis: string;
  fee_rate: number;
  slippage: number;
  tax: number;
  warmup_sessions: number;
  requested_dates: { start: string; end: string };
  effective_dates: { start: string; end: string };
  digest: string;
};

export type DailyRow = {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  avg_cost: number | null;
  star_price: number | null;
  target_price: number | null;
  t: number;
  quantity: number;
  cash: number;
  invested: number;
  equity: number;
  qqq_equity: number;
  drawdown: number;
  cycle_id: string;
};

export type TradeEvent = {
  date: string;
  side: "BUY" | "SELL";
  role: TradeRole;
  quantity: number;
  price: number;
  fee: number;
  reason_code: string;
  cycle_id: string;
};

export type Regime = "strong_green" | "green" | "yellow" | "orange" | "red";

export type WeatherState = Regime | "early_thaw";

export type RegimeWeatherRow = {
  date: string;
  signal_date: string;
  symbol: "TQQQ";
  signal_symbol: "QQQ";
  regime: Regime;
  weather_state: WeatherState;
  regime_age: number;
  strong_green_age: number;
  score: number;
  signal_return_3m: number | null;
  signal_return_6m: number | null;
  signal_rs: number | null;
  signal_distance_50: number | null;
  signal_sma50_rising_10d: boolean;
  sessions_since_stress: number | null;
  trade_dollar_volume_multiple: number | null;
  reasons: string[];
};

export type TradeRole =
  | "initial_buy"
  | "avg_half_buy"
  | "star_half_buy"
  | "star_full_buy"
  | "star_quarter_sell"
  | "target_sell"
  | "reverse_first_sell"
  | "reverse_sell"
  | "reverse_buy";

export type BacktestResult = {
  request: BacktestRequest;
  summary: Summary;
  assumptions: Assumptions;
  daily: DailyRow[];
  events: TradeEvent[];
  weather_daily: RegimeWeatherRow[];
};

export type ApiError = {
  error: { code: string; message: string; details?: Record<string, unknown> };
};

export type MarketDataCollection = {
  latest_completed_session: string;
  updated: boolean;
  added: number;
  symbols: Array<{
    symbol: "TQQQ" | "SOXL" | "QQQ";
    previous_last_date: string;
    last_date: string;
    added: number;
  }>;
};

export const ROLE_META: Record<TradeRole, { symbol: string; label: string; description: string; tone: "buy" | "sell" }> = {
  initial_buy: { symbol: "B", label: "첫 매수", description: "사이클을 시작한 매수", tone: "buy" },
  avg_half_buy: { symbol: "½", label: "평균가 매수", description: "절반 금액을 평균가격 기준으로 매수", tone: "buy" },
  star_half_buy: { symbol: "★½", label: "별지점 반 매수", description: "절반 금액을 별가격 기준으로 매수", tone: "buy" },
  star_full_buy: { symbol: "★", label: "별지점 전액 매수", description: "한 회분 전체를 별가격 기준으로 매수", tone: "buy" },
  star_quarter_sell: { symbol: "★¼", label: "별지점 일부 매도", description: "보유 수량 일부를 별가격 기준으로 매도", tone: "sell" },
  target_sell: { symbol: "T", label: "목표가 매도", description: "목표 수익 가격에서 나머지를 매도", tone: "sell" },
  reverse_first_sell: { symbol: "R", label: "역방향 첫 매도", description: "역방향 모드의 첫 매도", tone: "sell" },
  reverse_sell: { symbol: "R", label: "역방향 매도", description: "역방향 모드의 추가 매도", tone: "sell" },
  reverse_buy: { symbol: "R", label: "역방향 매수", description: "역방향 모드의 재매수", tone: "buy" },
};
