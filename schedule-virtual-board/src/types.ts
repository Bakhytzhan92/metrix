export type ScheduleRowKind = "estimate_section" | "task" | "item";

export type SuccChoice = {
  id: number;
  label: string;
  section_id?: number;
  section_name?: string;
};

export type ScheduleRow = {
  kind: ScheduleRowKind;
  row_index: number;
  section_id: number;
  task_id?: number | null;
  item_id: number | null;
  name: string;
  number?: string | number;
  quantity?: string | number;
  unit?: string;
  type?: string;
  total_price?: string;
  schedule_start?: string | null;
  schedule_end?: string | null;
  duration_days?: number | null;
  status?: string;
  assignee_id?: number | null;
  predecessor_id?: number | null;
  successor_id?: number | null;
  succ_choices?: SuccChoice[];
  item_count?: number;
  total_volume?: string;
  total_cost?: string;
  suggested_days?: number | null;
};

export type Assignee = {
  id: number;
  username: string;
};

export type StatusChoice = [string, string];

export type ScheduleVirtualPayload = {
  project_id: number;
  csrf_token: string;
  today: string;
  api_url_template: string;
  rows: ScheduleRow[];
  succ_catalog: SuccChoice[];
  assignees: Assignee[];
  status_choices: StatusChoice[];
};

export type ZoomMode = "day" | "week" | "month";
