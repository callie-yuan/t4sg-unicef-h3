from django.conf.urls import url

from geosight.h3grid.api import (
    H3IndicatorResolutionsAPI, H3IndicatorValuesAPI
)

urlpatterns = [
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
