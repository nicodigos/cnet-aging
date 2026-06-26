alter table public.invoices_raw
  add column if not exists partial_payments_amount numeric,
  add column if not exists partial_payments_count integer,
  add column if not exists open_amount_with_taxes numeric;
