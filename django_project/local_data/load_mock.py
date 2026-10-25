# to load Jan's mock Somalia H3 data into the local database
import csv
from datetime import date

import h3
from geosight.data.models.indicator import Indicator, IndicatorValue

indicators = {
    i.shortcode: i
    for i in Indicator.objects.filter(shortcode__in=["SCHOOL_COUNT", "STUDENT_COUNT"])
}
print("Indicators found:", list(indicators.keys()))

path = "/home/web/django_project/local_data/somalia_mock_h3_all.csv"
rows = []
for row in csv.DictReader(open(path, encoding="utf-8")):
    cell = row["H3ID"].strip().lower()
    rows.append(IndicatorValue(
        indicator=indicators[row["indicator"]],
        date=date.fromisoformat(row["date"]),
        geom_id=cell,
        value=float(row["value"]),
        admin_level=h3.get_resolution(cell),
    ))
print("Rows read:", len(rows)) # expect 17498

IndicatorValue.objects.bulk_create(rows, batch_size=1000, ignore_conflicts=True)
print("Done")