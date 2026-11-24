from django.conf.urls import url

from geosight.h3grid.api import (
    H3IndicatorResolutionsAPI, H3IndicatorValuesAPI
)
from geosight.h3grid.api_layers import H3LayerListAPI, H3LayerDetailAPI
from geosight.h3grid.api_project_area import (
    H3LayerAreaAPI, H3ProjectAreaAPI
)

urlpatterns = [
    url(r'^h3/layers/$', H3LayerListAPI.as_view(), name='h3-layer-list'),
    url(
        r'^h3/layers/(?P<identifier>[0-9a-fA-F-]{36})/$',
        H3LayerDetailAPI.as_view(), name='h3-layer-detail'
    ),
    url(
        r'^h3/layers/(?P<identifier>[0-9a-fA-F-]{36})/area/$',
        H3LayerAreaAPI.as_view(), name='h3-layer-area'
    ),
    url(
        r'^h3/projects/(?P<slug>[^/]+)/area/$',
        H3ProjectAreaAPI.as_view(), name='h3-project-area'
    ),
    url(
        r'^indicators/(?P<pk>\d+)/h3/resolutions/$',
        H3IndicatorResolutionsAPI.as_view(),
        name='h3-indicator-resolutions'
    ),
    url(
        r'^indicators/(?P<pk>\d+)/h3/values/$',
        H3IndicatorValuesAPI.as_view(),
        name='h3-indicator-values'
    ),
]
