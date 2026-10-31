# Mapping H3 data in GeoSight

How to put H3 data on a GeoSight map: create an H3 layer, import the data, read the errors, and view the map.

## 1. Create an H3 layer

1. Go to the Django admin (`/en-us/django-admin/`).
2. Open H3 Grid › H3 reference layers › Add.
3. Fill in:
   - Name, for example `Somalia H3`.
   - Default resolution, Min resolution and Max resolution. These should cover the resolutions in your file (for example 5 to 7).
4. Click Save.

## 2. Import the data

Each row of your file needs an H3 ID and a value. For example (`geosight/h3grid/tests/data/somalia_format_sample.csv`):

| H3ID | indicator | value | date |
|---|---|---|---|
| 8752c8454ffffff | SCHOOL_COUNT | 1 | 2020-01-01 |
| 8752c8454ffffff | STUDENT_COUNT | 137 | 2020-01-01 |

1. The importer only takes Excel, so save a CSV as `.xlsx` first.
2. Make sure each indicator in the file exists (Admin › Indicators › Create). The shortcode must match the file, for example `SCHOOL_COUNT`.
3. Go to Admin › Data Management › Import Data.
4. General: choose Indicator Value and Excel Long Format.
5. Reference Layer & Time:
   - Reference Layer: choose your H3 layer. H3 layers show "Spatial index: H3" under the name.
   - Admin Level and Type of Geo Code are hidden for H3 layers. The resolution comes from each H3 ID.
   - Date Time Setting: use Selected Date for one date, or Data-Driven Date with your date column (for example `date`, format `Date (YYYY-MM-DD)`).
6. Attributes:
   - Excel file: upload your file.
   - H3 ID Column: picked automatically if the column is called H3ID, h3_id, h3_index or h3 (any case). Otherwise choose it.
   - Indicator: Selected Indicator for one indicator, or Data-Driven Indicator Column with your indicator column (for example `indicator`).
   - Value Column: your value column.
7. Click Submit. This opens the import log.
8. When the status is Success, click See the data, select all rows, and click Save.

## 3. Read the errors

Rows with a bad H3 ID are not saved. Every other row is.

- The import log lists each bad row with its row number, the value and the reason, for example:
  `Row 4, value "not-an-h3-id": Invalid H3 id`
- Row numbers match the spreadsheet (row 1 is the header).
- In See the data, bad rows have the status Error and the same reason.

Fix the bad rows in the file and import it again. Rows that were already saved are updated, not duplicated.

## 4. View the map

1. Go to Admin › Project › Create.
2. General:
   - View: choose your H3 layer. The form shows its H3 settings, for example "Default resolution 7, range 5-7".
   - Name: for example `Somalia H3 Test`.
3. Indicators: click Add Indicator, select your indicator (for example School Count), and click Update Selection.
4. Indicator Layers: click Add Indicator Layer › Single Indicator Layer, select the indicator, and click Apply Selections.
5. Click Save, then open the project.

The hexagons are drawn from the H3 IDs. Use H3 resolution at the top of the map to switch between the resolutions in your data.
