create table if not exists public.invoices_raw (
  invoice_id bigint primary key,
  creation_date timestamptz,
  work_description text,
  payment_status text,
  vendor_company_name text, vendor_first_name text, vendor_last_name text,
  vendor_address text, vendor_city text, vendor_postal_code text,
  vendor_province text, vendor_country text, vendor_phone_number text,
  vendor_cell_phone text, buyer_company_name text, buyer_first_name text,
  buyer_last_name text, buyer_address text, buyer_city text,
  buyer_postal_code text, buyer_province text, buyer_country text,
  buyer_phone_number text, buyer_cell_phone text,
  total_amount_without_taxes numeric, total_amount_with_taxes numeric,
  gst_qc numeric, qst_qc numeric, hst_on numeric, gst_ab numeric,
  gst_bc numeric, pst_bc numeric, hst_nb numeric, pst_mb numeric,
  gst_mb numeric, hst_nl numeric, gst_nt numeric, hst_ns numeric,
  gst_nu numeric, hst_pe numeric, pst_sk numeric, gst_sk numeric, gst_yt numeric,
  partial_payments_amount numeric not null default 0,
  partial_payments_count integer not null default 0,
  open_amount_with_taxes numeric not null default 0,
  created_at timestamptz not null default now()
);

create table if not exists public.invoice_creation_override (
  invoice_id bigint primary key,
  new_creation_date date not null
);

create index if not exists invoices_raw_payment_status_idx
  on public.invoices_raw (payment_status);

create or replace view public.invoices_v as
with normalized as (
  select r.*,
    coalesce(o.new_creation_date::timestamptz, r.creation_date) as effective_creation_date,
    regexp_replace(lower(coalesce(r.work_description, '')), '\s+', '', 'g') as work_desc_norm,
    lower(trim(coalesce(r.buyer_company_name, ''))) as buyer_name_lc,
    (now() at time zone 'America/Toronto')::date as today_local
  from public.invoices_raw r
  left join public.invoice_creation_override o using (invoice_id)
), classified as (
  select n.*,
    case
      when n.invoice_id in (4057, 3208, 3200, 3199, 3198, 3197, 3350) then 'Regular'
      when position('janitorial' in n.work_desc_norm) > 0 then 'Regular'
      else 'One Shot'
    end as invoice_type,
    case when n.buyer_name_lc like '%controlnet%'
           or n.buyer_name_lc like '%allen maintenance%' then 60 else 30 end as past_due_days
  from normalized n
), dated as (
  select c.*,
    case when c.invoice_type = 'Regular'
      then (date_trunc('month', c.effective_creation_date) + interval '1 month - 1 day')::date
      else c.effective_creation_date::date end as issue_date
  from classified c
)
select
  d.invoice_id, d.work_description, d.payment_status,
  d.vendor_company_name, d.vendor_first_name, d.vendor_last_name,
  d.vendor_address, d.vendor_city, d.vendor_postal_code, d.vendor_province,
  d.vendor_country, d.vendor_phone_number, d.vendor_cell_phone,
  d.buyer_company_name, d.buyer_first_name, d.buyer_last_name,
  d.buyer_address, d.buyer_city, d.buyer_postal_code, d.buyer_province,
  d.buyer_country, d.buyer_phone_number, d.buyer_cell_phone,
  d.total_amount_without_taxes, d.total_amount_with_taxes,
  d.gst_qc, d.qst_qc, d.hst_on, d.gst_ab, d.gst_bc, d.pst_bc,
  d.hst_nb, d.pst_mb, d.gst_mb, d.hst_nl, d.gst_nt, d.hst_ns,
  d.gst_nu, d.hst_pe, d.pst_sk, d.gst_sk, d.gst_yt,
  d.created_at, d.effective_creation_date as creation_date,
  d.work_desc_norm, d.today_local, d.buyer_name_lc, d.invoice_type,
  d.issue_date, (d.today_local - d.issue_date) as days_since_issue_original,
  d.past_due_days,
  (d.today_local - d.issue_date - d.past_due_days) as days_since_issue,
  (d.today_local - d.issue_date - d.past_due_days) > 0 as past_due,
  d.partial_payments_amount, d.partial_payments_count, d.open_amount_with_taxes
from dated d;
