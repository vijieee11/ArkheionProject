from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count, Sum
from rest_framework import generics
from rest_framework.generics import ListAPIView
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import AuditLog, Barangay, PensionRecord, SeniorCitizen
from .serializers import BarangaySerializer, PensionRecordSerializer, SeniorCitizenSerializer


def record_action(request, action, module, record=None, description=""):
    """Write a compact audit event without copying sensitive record contents."""
    AuditLog.objects.create(
        user=request.user if request.user.is_authenticated else None,
        action=action,
        module=module,
        record_id=getattr(record, "pk", None),
        description=description,
        ip_address=request.META.get("REMOTE_ADDR"),
    )

class BarangayListAPIView(ListAPIView):
    serializer_class = BarangaySerializer
    permission_classes = [IsAuthenticated]
    queryset = Barangay.objects.filter(is_active=True).order_by("name")


class IsOSCAStaff(BasePermission):
    def has_permission(self, request, view):
        return request.user.role in ["head_staff", "regular_staff"]


class SeniorCitizenListAPIView(ListAPIView):
    serializer_class = SeniorCitizenSerializer
    permission_classes = [IsAuthenticated, IsOSCAStaff]

    def get_queryset(self):
        user = self.request.user
        seniors = SeniorCitizen.objects.select_related("barangay")

        if user.role == "head_staff":
            return seniors.order_by("last_name", "first_name")

        staff_profile = getattr(user, "staff_profile", None)
        if staff_profile is None:
            return SeniorCitizen.objects.none()

        return seniors.filter(
            barangay=staff_profile.barangay
        ).order_by("last_name", "first_name")


class SeniorCitizenDetailAPIView(generics.RetrieveUpdateAPIView):
    serializer_class = SeniorCitizenSerializer
    permission_classes = [IsAuthenticated]

    def update(self, request, *args, **kwargs):
        if request.user.role == "senior":
            return Response({"detail": "Senior portal accounts may view their record but cannot edit OSCA records."}, status=403)
        return super().update(request, *args, **kwargs)

    def get_queryset(self):
        user = self.request.user
        queryset = SeniorCitizen.objects.select_related("barangay")
        if user.role == "head_staff":
            return queryset
        if user.role == "regular_staff":
            profile = getattr(user, "staff_profile", None)
            return queryset.filter(barangay_id=profile.barangay_id) if profile else queryset.none()
        if user.role == "senior" and user.senior_citizen_id:
            return queryset.filter(pk=user.senior_citizen_id)
        return queryset.none()

    def perform_update(self, serializer):
        instance = serializer.save()
        record_action(self.request, "edit", "senior", instance, "Updated senior citizen record.")


class PensionHistoryAPIView(ListAPIView):
    serializer_class = PensionRecordSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        records = PensionRecord.objects.select_related("senior_citizen", "senior_citizen__barangay")
        if user.role == "head_staff":
            queryset = records
        elif user.role == "regular_staff":
            profile = getattr(user, "staff_profile", None)
            queryset = records.filter(senior_citizen__barangay_id=profile.barangay_id) if profile else records.none()
        elif user.role == "senior" and user.senior_citizen_id:
            queryset = records.filter(senior_citizen_id=user.senior_citizen_id)
        else:
            return records.none()
        senior_id = self.request.query_params.get("senior")
        if senior_id:
            queryset = queryset.filter(senior_citizen_id=senior_id)
        return queryset.order_by("-period", "-id")


class PensionRecordCreateAPIView(generics.CreateAPIView):
    serializer_class = PensionRecordSerializer
    permission_classes = [IsAuthenticated, IsOSCAStaff]
    queryset = PensionRecord.objects.all()

    def perform_create(self, serializer):
        record = serializer.save()
        record_action(self.request, "create", "pension", record, "Created pension history record.")


class AnalyticsAPIView(APIView):
    permission_classes = [IsAuthenticated, IsOSCAStaff]

    def get(self, request):
        seniors = SeniorCitizen.objects.all()
        pensions = PensionRecord.objects.select_related("senior_citizen")
        if request.user.role == "regular_staff":
            profile = getattr(request.user, "staff_profile", None)
            if not profile:
                return Response({"detail": "No barangay is assigned to this staff account."}, status=403)
            seniors = seniors.filter(barangay_id=profile.barangay_id)
            pensions = pensions.filter(senior_citizen__barangay_id=profile.barangay_id)
        result = {
            "scope": "all_barangays" if request.user.role == "head_staff" else "assigned_barangay",
            "senior_citizens": {
                "total": seniors.count(),
                "active": seniors.filter(is_active=True).count(),
                "inactive": seniors.filter(is_active=False).count(),
                "by_barangay": list(seniors.values("barangay__name").annotate(total=Count("id")).order_by("barangay__name")),
            },
            "pensions": {
                "records": pensions.count(),
                "claimed": pensions.filter(claimed=True).count(),
                "unclaimed": pensions.filter(claimed=False).count(),
                "amount_total": pensions.aggregate(total=Sum("amount"))["total"] or 0,
            },
            "note": "Death, transfer, booklet and age-group analytics will be added when their agreed record models are available.",
        }
        return Response(result)


class CurrentUserAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        result = {
            "username": user.get_username(),
            "role": user.role,
            "must_change_password": user.must_change_password,
            "barangay": None,
            "senior_citizen": None,
        }

        staff_profile = getattr(user, "staff_profile", None)
        if staff_profile:
            result["barangay"] = {
                "id": staff_profile.barangay_id,
                "code": staff_profile.barangay.code,
                "name": staff_profile.barangay.name,
            }

        senior = getattr(user, "senior_citizen", None)
        if senior:
            result["senior_citizen"] = {
                "id": senior.id,
                "osca_id": senior.osca_id,
                "first_name": senior.first_name,
                "last_name": senior.last_name,
            }

        return Response(result)


class ChangePasswordAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        current_password = request.data.get("current_password", "")
        new_password = request.data.get("new_password", "")

        if not current_password or not new_password:
            return Response(
                {"detail": "Enter your current password and a new password."},
                status=400,
            )
        if not request.user.check_password(current_password):
            return Response(
                {"current_password": ["The current password is incorrect."]},
                status=400,
            )

        try:
            validate_password(new_password, user=request.user)
        except DjangoValidationError as error:
            return Response({"new_password": error.messages}, status=400)

        if current_password == new_password:
            return Response(
                {"new_password": ["Choose a password different from your current one."]},
                status=400,
            )

        request.user.set_password(new_password)
        request.user.must_change_password = False
        request.user.save(update_fields=["password", "must_change_password"])
        return Response({"detail": "Password changed successfully."})
