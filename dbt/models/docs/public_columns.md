{#
  Column descriptions of the PUBLIC interface (access: public): the published layer, the data-health mart
  and the incident report. Written once here as doc blocks and referenced with {{ doc('col_...') }} from
  every model that exposes the column, so the same column never carries two different explanations.
#}

{# ------------------------------------------------------------------------------- keys and grain #}

{% docs col_micro_row_id %}Surrogate key of the Micro grid: hash of (delivery_date, pointer_id, market).{% enddocs %}
{% docs col_macro_row_id %}Surrogate key: hash of (report_month, market, macro_category).{% enddocs %}
{% docs col_macro_global_row_id %}Surrogate key: hash of (report_month, macro_category).{% enddocs %}
{% docs col_catalogue_row_id %}Surrogate key: hash of (as_of_date, object_id).{% enddocs %}
{% docs col_price_change_id %}Surrogate key of the price period that started with this change.{% enddocs %}
{% docs col_object_id %}Product-market id `Balenciaga_<market>_<normalized sku>`: one product in one market.{% enddocs %}
{% docs col_sku %}Brand reference of the product, normalized (one SKU is sold in every market).{% enddocs %}
{% docs col_market %}ISO-3 market code (FRA, JPN, USA ...).{% enddocs %}
{% docs col_pointer_id %}Client tracking id of a hero product (HERO-01 ... HERO-08), from the micro_pointers seed.{% enddocs %}

{# ------------------------------------------------------------------------------- dates #}

{% docs col_as_of_date %}Reporting date of a delivery: the date the point-in-time catalogue is read "as of". Micro = the Tuesday after each Monday crawl, Macro = month-end.{% enddocs %}
{% docs col_delivery_date %}Tuesday of the weekly Micro delivery.{% enddocs %}
{% docs col_report_month %}First day of the month a Macro delivery reports on.{% enddocs %}
{% docs col_crawl_date_used %}Crawl the row reflects, including for not_found / page_error rows (the crawl in which the product was looked for).{% enddocs %}
{% docs col_price_crawl_date %}Crawl the price comes from. Earlier than the presence crawl when the last valid price was carried forward.{% enddocs %}
{% docs col_presence_crawl_date %}Latest crawl on or before as_of_date in which the product was present in this market.{% enddocs %}
{% docs col_presence_age_days %}Days between the presence crawl and as_of_date.{% enddocs %}
{% docs col_changed_on_crawl_date %}Crawl in which the new price was first observed.{% enddocs %}
{% docs col_first_seen_date %}First crawl date in which the SKU appeared, in any market.{% enddocs %}
{% docs col_last_seen_date %}Last crawl date in which the SKU appeared, in any market.{% enddocs %}

{# ------------------------------------------------------------------------------- prices #}

{% docs col_currency_code %}ISO 4217 currency of the prices on the row. Prices are never converted: compare them within one market only.{% enddocs %}
{% docs col_price_local %}Shelf price in local currency, parsed from the delivered text.{% enddocs %}
{% docs col_previous_price_local %}Price of the same hero in the same market at the previous Micro delivery.{% enddocs %}
{% docs col_change_vs_previous_pct %}price_local / previous_price_local - 1 (0.0500 = +5%). Null on the first delivery or without a price.{% enddocs %}
{% docs col_price_status %}first_delivery, unchanged, price_increase, price_decrease, no_valid_price, not_found (absent from the crawl) or page_error (page unreadable: not a delisting).{% enddocs %}
{% docs col_has_price %}True when a valid price is available on as_of_date (observed or carried forward).{% enddocs %}
{% docs col_is_price_carried_forward %}True when the latest crawl had no valid price and the last valid one is reused.{% enddocs %}
{% docs col_is_stale_crawl %}The crawl used is more than 7 days older than the delivery (e.g. the market was missing from this week's crawl).{% enddocs %}
{% docs col_price_before %}Price before the change, local currency.{% enddocs %}
{% docs col_price_after %}Price after the change, local currency.{% enddocs %}
{% docs col_change_pct %}price_after / price_before - 1 (0.0500 = +5%).{% enddocs %}
{% docs col_change_direction %}increase or decrease.{% enddocs %}

{# ------------------------------------------------------------------------------- Macro statistics #}

{% docs col_n_products %}Products with a valid price in this market and category at month-end.{% enddocs %}
{% docs col_min_price %}Lowest price of the category in this market, local currency.{% enddocs %}
{% docs col_median_price %}Median price of the category in this market, local currency.{% enddocs %}
{% docs col_mean_price %}Mean price of the category in this market, local currency.{% enddocs %}
{% docs col_max_price %}Highest price of the category in this market, local currency.{% enddocs %}
{% docs col_lfl_n_products %}Like-for-like basket: products priced at both this and the previous month-end.{% enddocs %}
{% docs col_lfl_mean_change %}Like-for-like change: mean of each basket product's own % change. Each product counts once. The headline figure.{% enddocs %}
{% docs col_lfl_ratio_of_means %}Like-for-like change of the basket: sum(new prices) / sum(old prices) - 1. Expensive products weigh more.{% enddocs %}
{% docs col_lfl_share_increased %}Share of basket products whose price went up (0.2500 = 25%).{% enddocs %}
{% docs col_n_markets %}Markets with a like-for-like basket for this category and month.{% enddocs %}
{% docs col_lfl_n_product_markets %}Product-market pairs in the like-for-like baskets of all markets.{% enddocs %}
{% docs col_market_weighted_lfl_change %}Mean of the markets' like-for-like changes: every market counts once (mean of means). The global headline.{% enddocs %}
{% docs col_product_weighted_lfl_change %}Like-for-like change pooled over all product-market pairs: markets with more products weigh more.{% enddocs %}
{% docs col_min_market_lfl_change %}Lowest market like-for-like change for this category and month.{% enddocs %}
{% docs col_max_market_lfl_change %}Highest market like-for-like change for this category and month.{% enddocs %}
{% docs col_market_with_highest_change %}Market with the highest like-for-like change.{% enddocs %}

{# ------------------------------------------------------------------------------- catalogue flags #}

{% docs col_is_micro_date %}as_of_date is a Micro delivery date (a Tuesday).{% enddocs %}
{% docs col_is_macro_date %}as_of_date is a Macro delivery date (a month-end).{% enddocs %}

{# ------------------------------------------------------------------------------- products and markets #}

{% docs col_product_label %}Display name of the hero product used in client deliverables.{% enddocs %}
{% docs col_product_name %}Product name, cleaned (HTML entities, whitespace and case drift repaired).{% enddocs %}
{% docs col_color %}Colour as published by the brand.{% enddocs %}
{% docs col_collection %}Collection or product line as published by the brand.{% enddocs %}
{% docs col_ly_category_code %}Code of the harmonized category (ly_category_tree seed), assigned by the categorization rules.{% enddocs %}
{% docs col_ly_category_name %}Name of the harmonized category.{% enddocs %}
{% docs col_ly_level_1 %}Level 1 of the harmonized category tree (e.g. Leather Goods).{% enddocs %}
{% docs col_ly_level_2 %}Level 2 of the harmonized category tree (e.g. Bags).{% enddocs %}
{% docs col_macro_category %}Macro reporting category: Bags, Small Leather Goods, Shoes or Accessories. Null = out of Macro scope.{% enddocs %}
{% docs col_is_in_macro_scope %}True when the product belongs to a Macro category.{% enddocs %}
{% docs col_categorized_by_rule %}rule_id of the ly_category_rules row that categorized the product (e.g. R010), for traceability.{% enddocs %}
{% docs col_brand_macro_category %}The brand's own macro tag, as crawled (kept for traceability, not used for reporting).{% enddocs %}
{% docs col_brand_super_micro_category %}The brand's own finest tag, as crawled (kept for traceability).{% enddocs %}
{% docs col_n_markets_seen %}Number of markets in which the SKU was ever seen.{% enddocs %}
{% docs col_is_micro_pointer %}True when a client tracks this product as a hero (Micro).{% enddocs %}
{% docs col_micro_pointer_id %}Hero tracking id (HERO-01 ...) when the product is a Micro pointer.{% enddocs %}
{% docs col_micro_product_label %}Hero display name when the product is a Micro pointer.{% enddocs %}
{% docs col_market_name %}Market name in English.{% enddocs %}
{% docs col_region %}Region used to group markets (Europe, Americas, Middle East, Greater China, Asia Pacific).{% enddocs %}
{% docs col_crawl_cadence %}weekly (feeds Micro and Macro) or monthly (feeds Macro only).{% enddocs %}
{% docs col_is_in_micro_scope %}True for weekly-crawled markets, the only ones a Micro delivery covers.{% enddocs %}
{% docs col_display_order %}Sort order of the market in deliverables.{% enddocs %}

{# ------------------------------------------------------------------------------- delivery gate #}

{% docs col_scope %}Deliverable: micro (weekly hero prices) or macro (monthly category statistics).{% enddocs %}
{% docs col_decision %}Latest release decision of the delivery: PASS, WARN, or BLOCK when a human forced it.{% enddocs %}
{% docs col_is_forced %}True when a human released the delivery despite a BLOCK (with a written reason).{% enddocs %}
{% docs col_first_released_at %}When the delivery first became visible to BI.{% enddocs %}
{% docs col_dataset %}marts = what clients receive; legacy_replay = the old shared-catalogue design, audited for comparison.{% enddocs %}
{% docs col_run_id %}Gate run that produced the latest verdict on this delivery.{% enddocs %}
{% docs col_checked_at %}When that gate run audited the delivery.{% enddocs %}
{% docs col_n_results %}Check results of that run (one per check and subject).{% enddocs %}
{% docs col_n_pass %}Results that passed.{% enddocs %}
{% docs col_n_warn %}Results above a warning threshold.{% enddocs %}
{% docs col_n_fail %}Results above a failure threshold.{% enddocs %}
{% docs col_n_skip %}Results skipped (not enough history, check not applicable).{% enddocs %}
{% docs col_n_blocking_failures %}Failures of checks with severity block. One is enough to stop the release.{% enddocs %}
{% docs col_checks_not_passing %}Ids of the checks that warned or failed, sorted.{% enddocs %}
{% docs col_gate_decision %}Verdict of the latest run: BLOCK (a blocking failure), WARN (any warning or failure), PASS.{% enddocs %}
{% docs col_is_published %}True when the delivery is released to BI (marts dataset only).{% enddocs %}
{% docs col_is_forced_release %}True when the release was forced by a human (marts dataset only).{% enddocs %}
{% docs col_released_at %}Latest release time of the delivery (marts dataset only).{% enddocs %}

{# ------------------------------------------------------------------------------- incident replay #}

{% docs col_point_in_time_crawl_date %}Crawl the point-in-time design serves for this date and market.{% enddocs %}
{% docs col_legacy_crawl_date %}Crawl the old shared, mutable catalogue would have served.{% enddocs %}
{% docs col_legacy_file %}File whose import left the old catalogue in that state.{% enddocs %}
{% docs col_n_products_point_in_time %}Products present in the point-in-time catalogue.{% enddocs %}
{% docs col_n_products_legacy %}Products present in the old catalogue.{% enddocs %}
{% docs col_n_missing_in_legacy %}Products the old catalogue would have dropped.{% enddocs %}
{% docs col_n_extra_in_legacy %}Products the old catalogue would have kept by mistake.{% enddocs %}
{% docs col_n_price_differences %}Products present in both whose price differs.{% enddocs %}
{% docs col_share_prices_different %}n_price_differences / products present in both.{% enddocs %}
{% docs col_legacy_would_be_wrong %}True when the old design would have delivered a different crawl, product list or price.{% enddocs %}
