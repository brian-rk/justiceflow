export type Role = "clerk" | "registrar" | "magistrate" | "management" | "admin";
export type RiskCategory = "Low" | "Medium" | "High";

export interface User {
  id: number;
  username: string;
  full_name: string;
  role: Role;
  court_station: string | null;
  magistrate_id: string | null;
  active: boolean;
}

export interface Risk {
  probability: number;
  model_category: RiskCategory;
  category: RiskCategory;
  overdue: boolean;
  driving_factors: string;
  delay_status: string;
  court_controllable: boolean;
  target_used: number;
  scored_at: string;
  review_status: "pending" | "approved" | "overridden";
  reviewed_category: RiskCategory | null;
  review_reason: string;
  reviewed_at: string | null;
}

export interface CaseRow {
  id: string;
  case_type: string;
  court_level: string;
  court_station: string;
  region: string;
  n_parties: number;
  represented: boolean;
  filing_date: string;
  status: string;
  age_days: number;
  assigned_magistrate_id: string | null;
  source: string;
  risk: Risk | null;
}

export interface HearingRow {
  hearing_no: number;
  hearing_date: string;
  outcome: string;
  adjournment_reason: string | null;
  flag_advocate: boolean;
  flag_prosecution: boolean;
  flag_forensic: boolean;
  notes: string;
  recorded_by: string | null;
}

export interface DecisionRow {
  cycle_id: string | null;
  action: string;
  by: string | null;
  timestamp: string;
  reason: string;
  risk_category: string | null;
  day: string | null;
  magistrate_id: string | null;
}

export interface CaseDetail extends CaseRow {
  resolution_date: string | null;
  active_flags: Record<string, boolean>;
  flag_labels: Record<string, string>;
  disposition_target_months: number;
  hearings: HearingRow[];
  latest_listing: { cycle_id: string; cycle_status: string; magistrate_id: string; day: string; date: string; position: number } | null;
  decisions: DecisionRow[];
  escalations: { cycle_id: string; note: string; acknowledged: boolean }[];
}

export interface Listing {
  case_id: string;
  magistrate_id: string;
  magistrate_name?: string;
  court_station?: string;
  day: string;
  date: string;
  position: number;
  priority: number;
  risk_category: RiskCategory;
  risk_probability: number;
  delay_status: string;
  driving_factors: string;
  decision: "approve" | "edit" | "remove" | null;
  decision_reason: string | null;
}

export interface Cycle {
  id: string;
  week_start: string;
  status: "PROPOSED" | "APPROVED";
  solver_info: { solver_status?: string; wall_time_s?: number };
  created_by: string | null;
  created_at: string;
  finalised_by: string | null;
  finalised_at: string | null;
  listings: number;
  decided: number;
  approved: number;
}

export interface CycleDetail extends Cycle {
  items: Listing[];
  magistrate_options: Record<string, { id: string; name: string; unavailable_days: string }[]>;
}

export interface Reference {
  case_types: string[];
  court_levels: string[];
  case_types_by_level: Record<string, string[]>;
  working_days: string[];
  stations: string[];
  station_region: Record<string, string>;
  adjournment_reasons: Record<string, string>;
  flag_labels: Record<string, string>;
}

export interface Magistrate {
  id: string;
  full_name: string;
  court_level: string;
  region: string;
  court_station: string;
  daily_capacity: number;
  unavailable_days: string;
  active: boolean;
  pending_cases: number;
}
