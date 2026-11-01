# Andrew — Onboarding Notes

## 6.a Setup

**Machine:** Apple Silicon Mac
**Setup time:** roughly 30–40 minutes

> Unfortunately, I was not aware that we were documenting our errors. Therefore, I did not record my errors and my terminal does not have the history of errors. So, these next steps will be a recollection of these errors to the best of my ability.

| Command | Problem | Fix |
|---|---|---|
| `make dev` | Packages weren't able to be downloaded and the project could not run. | I needed to comment and uncomment 2 lines, as the default configuration is for Windows or Intel Macs. I needed to switch to the configuration for Apple Silicon Macs. |
| `make dev` | Packages weren't able to be downloaded and the project could not run. | I needed to use `gmake` instead of `make`. `make` is a default command on macOS, so I could not manually update it (maybe I can, but online it was recommended not to). I believe `make` only updates with OS updates. I used Homebrew to install a different version of GNU Make, which uses the command `gmake`. |

Besides these errors when creating the server, everything else went fine.

## 6.b Glossary

- **Project:** A saved map dashboard that sets which regions you see, which indicators and layers are on the map, and the widgets, filters and starting map view.
- **Indicator:** A measure that has a value for each region. Each row of data has a value, a date and a geo code indicating which region it belongs to.
- **Reference dataset:** The set of boundaries a project uses, organized by admin level (country → province/county → district). Indicator values will only be present on the map if their codes match regions in the project's reference dataset.
- **Context layer:** A background map layer pulled from an external source. This layer provides context on the state of a region, showing the region's roads, health facilities, flood areas, or satellite imagery.
- **PCode / geo code:** The ID that names a region and connects indicator values to the right region on the map. It contains the country, the region ID, and the version of this geo code.

## 6.c Exploring the App

**5.b** It seems that the geo code is what identifies where each value is applied. A geo code is in the format `{country}_{region}_{version}` (e.g. `KEN_0047_V1` for West Pokot, Kenya).

**5.c** An admin would go to the admin panel, click on the **Indicators** tab on the left-hand side, then click the **Create New Indicator** button in the top right. Fields marked with * are required:

- Name*
- Description
- Source
- Shortcode*
- Category*
- Unit
- Indicator type*
- Min value
- Max value

**5.d** You will find the reference datasets in the admin panel, on the left-hand side, in a tab called **Reference Datasets**.

## 6.d Comments

See Google Drive for comments.

## 6.e Questions

Will we be completely overhauling the current boundary system? That is, will we eliminate boundaries based on administrative borders when we implement H3, or will we add H3 alongside administrative borders as boundaries?

I am thinking about this because if we are eliminating administrative boundaries, then I think geo codes will no longer be necessary, since they are encoded according to the country and county/province they are in.
