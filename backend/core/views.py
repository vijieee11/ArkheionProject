import secrets
import string

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Count, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics
from rest_framework.generics import ListAPIView
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import AuditLog, Barangay, MedicineBooklet, MedicineBookletEntry, PensionRecord, SeniorCitizen
from .serializers import (
    BarangaySerializer,
    GenerateSeniorAccountsSerializer,
    MedicineBookletEntryCreateSerializer,
    MedicineBookletEntrySerializer,
    MedicineBookletIssueSerializer,
    MedicineBookletSerializer,
    PensionRecordSerializer,
    SeniorCitizenSerializer,
)


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


class IsSenior(BasePermission):
    def has_permission(self, request, view):
        return request.user.role == "senior" and bool(request.user.senior_citizen_id)


class IsSeniorOrOSCAStaff(BasePermission):
    def has_permission(self, request, view):
        return request.user.role in ["senior", "head_staff", "regular_staff"]


def booklets_for_user(user):
    booklets = MedicineBooklet.objects.select_related("senior_citizen", "senior_citizen__barangay").prefetch_related("backup_entries")
    if user.role == "head_staff":
        return booklets
    if user.role == "regular_staff":
        profile = getattr(user, "staff_profile", None)
        return booklets.filter(senior_citizen__barangay_id=profile.barangay_id) if profile else booklets.none()
    if user.role == "senior" and user.senior_citizen_id:
        return booklets.filter(senior_citizen_id=user.senior_citizen_id)
    return booklets.none()


class MedicineBookletListAPIView(ListAPIView):
    serializer_class = MedicineBookletSerializer
    permission_classes = [IsAuthenticated, IsSeniorOrOSCAStaff]

    def get_queryset(self):
        return booklets_for_user(self.request.user).order_by("-date_issued", "-id")


class MedicineBookletIssueAPIView(generics.CreateAPIView):
    serializer_class = MedicineBookletIssueSerializer
    permission_classes = [IsAuthenticated, IsOSCAStaff]

    def perform_create(self, serializer):
        booklet = serializer.save()
        record_action(self.request, "create", "medicine_booklet", booklet, "Issued original physical booklet and opened digital backup.")


class MedicineBookletEntryCreateAPIView(generics.CreateAPIView):
    serializer_class = MedicineBookletEntryCreateSerializer
    permission_classes = [IsAuthenticated, IsSenior]

    def perform_create(self, serializer):
        if serializer.validated_data["booklet"].pk != int(self.kwargs["pk"]):
            from rest_framework.exceptions import ValidationError
            raise ValidationError({"booklet": "The selected booklet does not match this request."})
        entry = serializer.save(uploaded_by=self.request.user)
        record_action(self.request, "upload", "booklet_backup", entry, "Uploaded a booklet backup image for staff review.")


class MedicineBookletEntryReviewAPIView(APIView):
    permission_classes = [IsAuthenticated, IsOSCAStaff]

    def post(self, request, pk):
        entry = get_object_or_404(
            MedicineBookletEntry.objects.select_related("booklet__senior_citizen__barangay"),
            pk=pk,
        )
        if request.user.role == "regular_staff":
            profile = getattr(request.user, "staff_profile", None)
            if not profile or entry.booklet.senior_citizen.barangay_id != profile.barangay_id:
                return Response({"detail": "You may only review booklet entries in your assigned barangay."}, status=403)
        if entry.review_status != "pending":
            return Response({"detail": "This upload has already been reviewed."}, status=400)

        decision = request.data.get("decision")
        if decision not in {"verified", "rejected"}:
            return Response({"decision": ["Choose verified or rejected."]}, status=400)
        entry.review_status = decision
        entry.review_note = str(request.data.get("review_note", "")).strip()[:300]
        entry.reviewed_by = request.user
        entry.reviewed_at = timezone.now()
        entry.save(update_fields=["review_status", "review_note", "reviewed_by", "reviewed_at"])
        record_action(request, "approve" if decision == "verified" else "edit", "booklet_backup", entry, f"Booklet backup upload {decision}.")
        return Response(MedicineBookletEntrySerializer(entry, context={"request": request}).data)


class MedicineBookletLossReportAPIView(APIView):
    permission_classes = [IsAuthenticated, IsSenior]

    def post(self, request, pk):
        booklet = get_object_or_404(booklets_for_user(request.user), pk=pk)
        if booklet.loss_status == "pending":
            return Response({"detail": "Your loss report is already awaiting OSCA review."}, status=400)
        if booklet.loss_status == "confirmed":
            return Response({"detail": "This booklet has already been reported and confirmed as lost."}, status=400)

        booklet.loss_status = "pending"
        booklet.loss_reported_at = timezone.now()
        booklet.loss_note = str(request.data.get("note", "")).strip()[:1000]
        booklet.loss_reviewed_by = None
        booklet.loss_reviewed_at = None
        booklet.save(update_fields=["loss_status", "loss_reported_at", "loss_note", "loss_reviewed_by", "loss_reviewed_at"])
        record_action(request, "edit", "medicine_booklet", booklet, "Senior citizen reported a physical booklet lost; awaiting OSCA review.")
        return Response(MedicineBookletSerializer(booklet, context={"request": request}).data)


class MedicineBookletActionAPIView(APIView):
    permission_classes = [IsAuthenticated, IsOSCAStaff]

    def post(self, request, pk):
        booklet = get_object_or_404(booklets_for_user(request.user), pk=pk)
        action = request.data.get("action")
        now = timezone.now()

        if action == "mark_full":
            if booklet.status != "issued":
                return Response({"detail": "Only an issued booklet can be marked full."}, status=400)
            booklet.status = "full"
            booklet.full_at = now
            booklet.is_active = False
            description = "Marked physical medicine booklet as full."
        elif action == "confirm_loss":
            if booklet.loss_status != "pending":
                return Response({"detail": "There is no pending loss report to confirm."}, status=400)
            booklet.status = "lost"
            booklet.is_active = False
            booklet.loss_status = "confirmed"
            booklet.loss_reviewed_by = request.user
            booklet.loss_reviewed_at = now
            description = "Confirmed a lost booklet report."
        elif action == "reject_loss":
            if booklet.loss_status != "pending":
                return Response({"detail": "There is no pending loss report to reject."}, status=400)
            booklet.loss_status = "rejected"
            booklet.loss_reviewed_by = request.user
            booklet.loss_reviewed_at = now
            description = "Rejected a lost booklet report."
        elif action == "issue_digital_replacement":
            if booklet.loss_status != "confirmed" or booklet.status != "lost":
                return Response({"detail": "Confirm the loss report before issuing the digital replacement."}, status=400)
            if booklet.digital_replacement_issued_at:
                return Response({"detail": "The digital replacement has already been issued."}, status=400)
            booklet.digital_replacement_issued_at = now
            description = "Issued digital booklet replacement after confirmed loss."
        else:
            return Response({"action": ["Choose mark_full, confirm_loss, reject_loss, or issue_digital_replacement."]}, status=400)

        booklet.save()
        record_action(request, "edit", "medicine_booklet", booklet, description)
        return Response(MedicineBookletSerializer(booklet, context={"request": request}).data)


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


class SeniorAccountGenerationAPIView(APIView):
    """Create one-time-displayed portal credentials for existing senior records."""
    permission_classes = [IsAuthenticated, IsOSCAStaff]

    @staticmethod
    def make_temporary_password():
        alphabet = string.ascii_letters + string.digits
        while True:
            password = "".join(secrets.choice(alphabet) for _ in range(14))
            try:
                validate_password(password)
            except DjangoValidationError:
                continue
            return password

    def post(self, request):
        payload = GenerateSeniorAccountsSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        senior_ids = list(dict.fromkeys(payload.validated_data["senior_ids"]))

        queryset = SeniorCitizen.objects.select_related("barangay").filter(
            id__in=senior_ids,
            is_active=True,
        )
        if request.user.role == "regular_staff":
            profile = getattr(request.user, "staff_profile", None)
            if not profile:
                return Response({"detail": "This staff account has no assigned barangay."}, status=403)
            queryset = queryset.filter(barangay_id=profile.barangay_id)

        seniors = list(queryset)
        if len(seniors) != len(senior_ids):
            return Response(
                {"detail": "One or more selected seniors are missing, inactive, or outside your assigned barangay."},
                status=400,
            )

        User = get_user_model()
        created_accounts = []
        with transaction.atomic():
            for senior in seniors:
                if senior.portal_users.exists() or User.objects.filter(username=senior.osca_id).exists():
                    return Response(
                        {"detail": f"A portal account already exists for OSCA ID {senior.osca_id}. No accounts were created."},
                        status=400,
                    )

            for senior in seniors:
                temporary_password = self.make_temporary_password()
                user = User(
                    username=senior.osca_id,
                    first_name=senior.first_name,
                    last_name=senior.last_name,
                    role="senior",
                    must_change_password=True,
                    senior_citizen=senior,
                    is_active=True,
                )
                user.set_password(temporary_password)
                user.save()
                created_accounts.append({
                    "senior_id": senior.id,
                    "osca_id": senior.osca_id,
                    "name": f"{senior.first_name} {senior.last_name}".strip(),
                    "barangay": senior.barangay.name if senior.barangay else "",
                    "username": user.username,
                    "temporary_password": temporary_password,
                })
                record_action(request, "create", "senior_portal_account", senior, "Generated a senior portal account.")

        return Response({"created": created_accounts}, status=201)


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
