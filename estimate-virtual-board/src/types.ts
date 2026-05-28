export type BootstrapBanner = {
  kind: "banner";
  /** stable key inside section */
  key: string;
  title: string;
};

export type BootstrapItem = {
  kind: "item";
  /** stable key inside section */
  key: string;
  id: number;
  /** display index among data rows in section */
  ordinal: number;
  type: "material" | "labor" | "equipment" | "delivery" | string;
  name: string;
  unit: string;
  quantity: string;
  cost_price: string;
  markup_percent: string;
  sell_price: string;
  total_cost: string;
  total_price: string;
  urls: {
    save: string;
    delete: string;
    supply: string;
  };
};

export type BootstrapFlatRow = BootstrapBanner | BootstrapItem;

export type BootstrapSection = {
  id: number;
  order: number;
  name: string;
  displayBadge: number;
  item_count: number;
  section_total_cost: string;
  section_total_price: string;
  save_url: string;
  delete_url: string;
  quick_add_action: string;
  rows: BootstrapFlatRow[];
};

export type EstimateVirtualPayload = {
  project_id: number;
  csrf_token: string;
  sections: BootstrapSection[];
};
