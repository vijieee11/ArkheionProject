from django.urls import path
from .views import (
    BarangayListAPIView,
    ChangePasswordAPIView,
    CurrentUserAPIView,
    AnalyticsAPIView,
    PensionHistoryAPIView,
    PensionRecordCreateAPIView,
    SeniorCitizenDetailAPIView,
    SeniorCitizenListAPIView,
)

urlpatterns = [
    path("seniors/", SeniorCitizenListAPIView.as_view(), name="senior-list"),
    path("seniors/<int:pk>/", SeniorCitizenDetailAPIView.as_view(), name="senior-detail"),
    path("pensions/", PensionHistoryAPIView.as_view(), name="pension-history"),
    path("pensions/create/", PensionRecordCreateAPIView.as_view(), name="pension-create"),
    path("analytics/", AnalyticsAPIView.as_view(), name="analytics"),
    path("barangays/", BarangayListAPIView.as_view(), name="barangay-list"),
    path("me/", CurrentUserAPIView.as_view(), name="current-user"),
    path("password/change/", ChangePasswordAPIView.as_view(), name="password-change"),
]
