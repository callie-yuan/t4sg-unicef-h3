# Onboarding — Abinet

## Setup

- OS: Windows 11 Pro, everything run inside Ubuntu 24.04 on WSL 2, Docker Desktop with the WSL 2 backend
- Machine: 7.6 GB RAM, 12 cores
- How long setup took: spread over two days (Oct 11–12). Tool installs and the clone were quick; almost all the time went into getting `make dev` to finish. Once the memory issue was fixed, the first webpack compile took about 15 minutes and `make dev-initialize` + `make load-test-data` took a few minutes each.

| Step | Exact error | Fix |
|---|---|---|
| Install / disk space | C: drive had only ~2.5 GB free, so Docker images and the build had no room | Cleared old installers and unused apps to free ~35 GB |
| `make dev` | Ran for a very long time and never finished; `geosight_dev` stayed at `Created` while `geosight_webpack` was stuck at `health: starting` | `dev` waits for webpack to be healthy, and the first webpack compile was starving for memory (see next row). Fixed by the memory change below |
| `make dev` (cause) | Containers died with `Exited (137)` (killed for out-of-memory); `wsl: Unknown key 'wsl2.autoMemoryReclaim' in C:\Users\Abine\.wslconfig:5` | `.wslconfig` gave WSL `memory=8GB` on a machine with only 7.6 GB RAM, so Windows ran out of memory. Changed to `memory=5GB`, `swap=8GB`, and moved `autoMemoryReclaim` under `[experimental]` |
| `make dev` (after a crash) | `The command 'docker' could not be found in this WSL 2 distro. We recommend to activate the WSL integration in Docker Desktop settings.` | Not actually an integration problem: the Docker Desktop engine had crashed. Restarting Docker Desktop fixed it (WSL integration for Ubuntu was already on) |
| `make dev-initialize` / `make load-test-data` | Only `System check identified some issues` / `WARNINGS` lines | Normal, no fix needed. Superuser `admin/admin` created; demo data loaded (1 project, 5 indicators, 1,055 values) |

## Glossary

- Project: Basically a dashboard. It's the map you open in GeoSight, where indicators, context layers, and the boundaries all come together so you can explore the data (like the "Demo GeoSight Project").
- Indicator: The thing being measured, like number of schools or population. It has a value for each place and each date.
- Reference dataset: The set of boundaries the data sits on, like Somalia or Kenya split into regions and districts. These are the shapes that get colored on the map.
- Context layer: An extra layer on the map that just gives background info, like roads or health facilities. It isn't the indicator data itself.
- PCode / geo code: A unique ID for each area (for example `SOM_0013_V1`). It's how GeoSight knows which area a value belongs to, so it can color the right shape.

## What I found

5.b: What identifies where each value applies?

Each indicator value is stored with a geo code, the `geom_id` field (e.g. `SOM_0013_V1`), along with its `date` and `admin_level`. A sample row from the demo data: Sample Indicator B, `geom_id = SOM_0013_V1`, admin level 1, date 2026-02-17, value 150. The model is `IndicatorValue` in `django_project/geosight/data/models/indicator/indicator_value.py`. So a value is tied to a place only through that code, not through a shape or coordinates.

5.c: Fields the indicator-data upload asks for (Admin sidebar → Data Management, `/en-us/admin/importer/data-management`; the upload form itself is `/en-us/admin/importer/`, using Excel/CSV "long format" indicator values):

- The file/sheet, plus which column holds the geo code (`key_administration_code`) and what type of code it is (PCode / ucode / concept UUID)
- The reference dataset and admin level: either one fixed level for the whole file or a column that holds it (`admin_level_type`, `admin_level_value` / `admin_level_field`)
- The date: either one fixed date or a date column, plus its format (`date_time_data_type`, `date_time_data_value` / `date_time_data_field`, `date_time_data_format`)
- Which indicator the values belong to (one fixed indicator, or an indicator column for multiple indicators)
- The value column (`key_value`)
- Optional aggregation rules for multiple values in the same area and for rolling values up to higher admin levels

5.d: Where the reference datasets (boundary sets) are listed:

Admin → Reference Datasets (`/en-us/admin/reference-datasets/`). The demo data has three: Somalia, Kenya, and Kenya (Latest).

## Video comments

Posted on each teammate's video in the Week 1 Delivs (Videos) Drive folder:

- Andrew (H3 + Django): Really great presentation! The county map vs H3 map comparison was really cool, it showed really well why hexagons are better than district boundaries for this project. Your Django explanation was also clear and easy to follow.
- Edison (H3 + Redis/Celery): This is very awesome! The resolution table made H3 really easy to picture. The Celery part was super clear too, it helped me understand what the worker containers are actually doing when we run GeoSight.
- Grace (H3 + PostgreSQL/PostGIS): It is a really nice presentation! Your explanations of PostgreSQL and PostGIS were really easy to follow, especially the indexing part. It's cool to see how H3 could make some of the spatial work simpler for us.
- Amy (MapLibre): A very great presentation! I liked how you walked through the whole process of getting H3 data onto the map. I believe it is probably what we'll need to build for the frontend, so it was really helpful to see it all together.

## My question about the project

Every value is tied to an admin area through a single `geom_id` geo code, and the map joins on that code. When we add H3, should an H3 cell ID go into that same `geom_id` field, with H3 treated as just another reference dataset? Or does UNICEF want H3 values stored separately, so one indicator can have both PCode-based and H3-based values at the same time?
