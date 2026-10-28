from django.contrib import admin
from django.urls import include, path
from rest_framework_simplejwt.views import TokenRefreshView
from core.views import AuditedTokenObtainPairView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/token/", AuditedTokenObtainPairView.as_view(), name="token-obtain-pair"),
    path("api/token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("api/", include("core.urls")),
]
