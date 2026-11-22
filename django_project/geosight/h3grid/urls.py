from django.conf.urls import url

from geosight.h3grid.api import (
    H3IndicatorResolutionsAPI, H3IndicatorValuesAPI
)
from geosight.h3grid.api_layers import H3LayerListAPI, H3LayerDetailAPI

urlpatterns = [
    url(r'^h3/layers/$', H3LayerListAPI.as_view(), name='h3-layer-list'),
    url(
        r'^h3/layers/(?P<identifier>[0-9a-fA-F-]{36})/$',
        H3LayerDetailAPI.as_view(), name='h3-layer-detail'
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
