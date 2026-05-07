# Demo Script — HCMC Delivery Operations Dashboard

**Duration:** ~8–10 min  
**Audience:** Business analysts, operations managers  
**App URL:** http://localhost:8501  
**Start command:** `source venv/bin/activate && streamlit run app/app.py -- --source local`

---

## 0 · Setup (before recording)

- Open the app and pre-load the Overview tab so there is no spinner on camera
- Set browser to full screen (F11)
- Close all notifications / Slack / calendar alerts
- Have a glass of water

---

## 1 · Opening hook (30 sec)

> "Every day our drivers make thousands of deliveries across Ho Chi Minh City.
> Some areas consistently run 20, 30, even 50 minutes late —
> and right now we have no systematic way to find them.
> This dashboard changes that."

*[Tab visible: Overview]*

---

## 2 · Overview tab (2 min)

Point to the five KPI cards across the top.

> "The top row gives us the city-wide pulse:
> total deliveries, average delay, what percentage are severely late,
> and — most importantly — the margin gap:
> the dollar amount of delay cost that our freight revenue does not cover."

Point to the left chart (avg delay by district):

> "This bar chart immediately tells us which districts are running hot.
> The longer the bar, the worse the delay.
> We can also filter to a single district using the dropdown if we want to drill in."

Point to the right chart (margin gap by district):

> "Red bars are districts where delay cost exceeds what we charged for shipping —
> meaning we are subsidising slow delivery out of company margin.
> Green bars are fine. Red bars are where we need to act."

---

## 3 · Problem Zones tab (3 min)

*[Click 'Problem Zones' tab]*

> "This is the core view. Every hexagon on this map is a real H3 cell —
> a ~0.1 km² area of the city.
> Green means deliveries arrive on time. Yellow means moderate delay.
> Orange and red mean the location itself is a structural problem."

*[Pause — let the map render and audience absorb it]*

> "Notice the clusters of orange and red in the centre —
> those are the inner-city districts: Quận 3, Quận 5, Quận 10.
> Narrow hẻm alleys, market traffic, no-through roads.
> The spatial index has found them automatically, without anyone having to draw a boundary."

Point to the KPIs above the map:

> "We have identified N high-risk zones covering $X in unrecovered margin."

*[Click one orange/red cell on the map]*

> "When I click a cell, I get its exact H3 identifier and the four metrics
> for that specific location:
> how late deliveries run there, what it costs us, how many deliveries we route through it,
> and the failure rate.
> This is the level of precision we could never get from a district-level report."

*[Point to the legend text below the map]*

---

## 4 · Districts tab (1.5 min)

*[Click 'Districts' tab]*

> "The Districts tab puts all eleven areas in a table you can sort and share.
> Colour coding highlights the outliers instantly — red delay, red margin gap.
> The two charts below let us ask whether high delay cost is actually translating
> into a margin problem, or whether freight pricing is absorbing it."

Point to the scatter plot:

> "Districts above the zero line are where we are losing money.
> Districts below it are healthy. This is where pricing conversations should start."

---

## 5 · High-Risk Areas tab (1.5 min)

*[Click 'High-Risk Areas' tab]*

> "The final tab is an actionable list — every individual H3 zone
> where average delay exceeds 15 minutes, sorted by severity.
> The primary key is the H3 cell ID, not a district name.
> That means operations can take this table directly into routing software
> and apply zone-specific rules."

Point to the recommendation banner at the bottom:

> "Based on the combined margin gap in flagged zones, we recommend
> a $1.50–$2.50 delivery surcharge for orders going into these cells.
> That recovers approximately $X per period in currently uncompensated delay cost
> without touching pricing for the rest of the city."

---

## 6 · Closing (30 sec)

> "To summarise:
> H3 spatial indexing lets us pinpoint delay at the sub-kilometre level.
> District-level reporting told us Quận 3 was slow —
> this tells us *which streets* in Quận 3 are slow,
> so we can route around them, surcharge them, or flag them for driver briefings.
> The pipeline runs end-to-end on DuckDB locally and on BigQuery in the cloud —
> same models, same output, no extra infrastructure."

---

## Q&A preparation

| Likely question | Answer |
|---|---|
| How fresh is the data? | Pipeline is batch; run `dbt run` to refresh. Cloud version can be scheduled via Dataform. |
| Can we filter by date range? | Not in this version; the mart aggregates all history. Easy to add a date dimension. |
| Why hexagons and not grid squares? | H3 hexagons have equal-area cells and equidistant neighbours — no diagonal distortion. The spatial comparison tab in the technical report quantifies this. |
| How many cells cover HCMC? | ~6,700 at resolution 9 (~0.1 km² each). We surface ~3,500 cells with delivery data. |
| Can drivers see this? | Currently a BI dashboard for ops/BA teams. Exporting flagged cell IDs to routing APIs is the next step. |
| What is the margin gap formula? | `delay_cost_usd − total_freight_usd` per delivery. Motorbike = $3/hr, van = $5/hr. |
