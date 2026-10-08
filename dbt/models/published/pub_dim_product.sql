{{ config(materialized='view') }}

-- Reference / event table: not tied to one delivery, published as is so BI reads one schema only.
select * from {{ ref('dim_product') }}
