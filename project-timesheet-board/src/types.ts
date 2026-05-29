export type StatusCode =
  | "present"
  | "off"
  | "vacation"
  | "absent"
  | "half"
  | "";

export type StatusMeta = {
  code: StatusCode;
  short: string;
  label: string;
  color: string;
};

export type Employee = {
  id: number;
  project_employee_id?: number;
  full_name: string;
  position: string;
  status: "active" | "inactive" | string;
  status_display: string;
};

export type EmployeeFormData = {
  full_name: string;
  position: string;
  status: "active" | "inactive";
};

export type Analytics = {
  total_workers: number;
  on_site_today: number;
  absent_today: number;
  attendance_pct: number;
};

export type ChangeLog = {
  id: number;
  employee_name: string;
  date: string;
  old_short: string;
  new_short: string;
  edited_by: string;
  edited_at: string;
};

export type MonthPayload = {
  ok: boolean;
  can_edit: boolean;
  year: number;
  month: number;
  days_in_month: number;
  employees: Employee[];
  entries: Record<string, string>;
  statuses: StatusMeta[];
  analytics: Analytics;
  today: string;
};
