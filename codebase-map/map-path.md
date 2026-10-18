Geometry data fetched under frontend/src/pages/maplibre/layers/referencelayer/index.tsx -saves vector tile information from reference layer data
With frontend/src/pages/maplibre/utils/DatasetGeometryData/index.jsx handling geometry data
In geosight/georepo tasks.py, fetch data sets from geosight.georepo.request.request import GeorepoRequest
Saves reference layer (view and indicator) and indicator defined in data.models - See how reference layer and entities defined under georepo/models/reference_layer
All data is saved under flattened table when static methodassign flat table called under indicator value
Coordinates actually stored in entity.py centroid, here could introduce h3.latlng to hexagon to draw hexagons


Math done in zonal analysis could change with hexagons
utils/raster.py - rater zonal analysis
tasks/cogclassification and zonal analysis

Indicators defined within Country/under admin levels so might be difficult to extend indicator data past borders into hexagons

Not entirely sure what unicef codes are but could break code

# Question 
Do they want h3 to be the overlaid on map/what we have now, or do they want them to replace the borders we have now or should we be able to switch btn seeing both and just one