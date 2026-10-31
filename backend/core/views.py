import secrets
import string
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics
from rest_framework.generics import ListAPIView, ListCreateAPIView
from rest_framework.permissions import AllowAny, BasePermission, IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    AuditLog,
    BookletReturn,
    Barangay,
    DeathRecord,
    Document,
    GroceryClaim,
    GroceryDistribution,
    PensionRecord,
    ResidenceTransferRecord,
    SeniorCitizen,
    StaffProfile,
    StaffRegistrationRequest,
)
from .serializers import (
    BarangaySerializer,
    BookletReturnSerializer,
    DeathRecordSerializer,
    DocumentSerializer,
    GenerateSeniorAccountsSerializer,
    GroceryClaimReportSerializer,
    GroceryClaimWriteSerializer,
    GroceryDistributionSerializer,
    PensionRecordSerializer,
    ResidenceTransferRecordSerializer,
    SeniorCitizenSerializer,
)
from .document_classifier import classify_document, classifier_artifact_path, classifier_source, extract_document_entities, extract_document_text


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

class AuditedTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        request = self.context.get("request")
        if getattr(self.user, "role", None) in {"head_staff", "regular_staff"}:
            AuditLog.objects.create(
                user=self.user,
                action="login",
                module="auth",
                description="Staff user signed in successfully.",
                ip_address=request.META.get("REMOTE_ADDR") if request else None,
            )
        return data


class AuditedTokenObtainPairView(TokenObtainPairView):
    serializer_class = AuditedTokenObtainPairSerializer

class BarangayListAPIView(ListAPIView):
    serializer_class = BarangaySerializer
    permission_classes = [AllowAny]
    queryset = Barangay.objects.filter(is_active=True).order_by("name")


def is_registration_reviewer(user):
    return user.is_authenticated and (user.is_superuser or getattr(user, "role", None) in {"head_staff", "admin"})


class HeadStaffOnly(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and (request.user.is_superuser or request.user.role == "head_staff")


class AuditLogPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100


class AuditLogListAPIView(APIView):
    permission_classes = [HeadStaffOnly]
    pagination_class = AuditLogPagination

    def get(self, request):
        entries = AuditLog.objects.select_related("user").order_by("-timestamp", "-id")
        action = request.query_params.get("action", "").strip().lower()
        username = request.query_params.get("user", "").strip()
        date = request.query_params.get("date", "").strip()
        search = request.query_params.get("search", "").strip()
        valid_actions = {choice[0] for choice in AuditLog.ACTION_CHOICES}
        if action and action in valid_actions:
            entries = entries.filter(action=action)
        if username:
            entries = entries.filter(user__username=username)
        if date:
            entries = entries.filter(timestamp__date=date)
        if search:
            entries = entries.filter(
                Q(user__username__icontains=search)
                | Q(user__first_name__icontains=search)
                | Q(user__last_name__icontains=search)
                | Q(module__icontains=search)
                | Q(description__icontains=search)
            )
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(entries, request, view=self)
        rows = [{
            "id": entry.pk,
            "timestamp": entry.timestamp,
            "username": entry.user.get_username() if entry.user else "Deleted user",
            "staff_name": (entry.user.get_full_name().strip() or entry.user.get_username()) if entry.user else "Deleted user",
            "action": entry.action,
            "module": entry.module,
            "record_id": entry.record_id,
            "description": entry.description,
            "ip_address": entry.ip_address or "",
        } for entry in page]
        return paginator.get_paginated_response(rows)


class StaffDirectoryAPIView(ListAPIView):
    permission_classes = [HeadStaffOnly]

    def get(self, request):
        User = get_user_model()
        users = User.objects.filter(role__in=["head_staff", "regular_staff"]).select_related(
            "staff_profile__barangay"
        ).order_by("last_name", "first_name", "username")
        rows = []
        for user in users:
            profile = getattr(user, "staff_profile", None)
            rows.append({
                "id": user.pk,
                "username": user.username,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "email": user.email,
                "role": user.role,
                "is_active": user.is_active,
                "date_joined": user.date_joined,
                "last_login": user.last_login,
                "barangay": {"id": profile.barangay_id, "name": profile.barangay.name} if profile else None,
            })
        return Response(rows)


class StaffRegistrationAPIView(APIView):
    """Public staff sign-up; accounts stay inactive until OSCA approves them."""
    permission_classes = [AllowAny]

    def post(self, request):
        from rest_framework.exceptions import ValidationError

        username = str(request.data.get("username", "")).strip()
        first_name = str(request.data.get("first_name", "")).strip()
        last_name = str(request.data.get("last_name", "")).strip()
        email = str(request.data.get("email", "")).strip()
        contact_number = str(request.data.get("contact_number", "")).strip()
        password = request.data.get("password", "")
        password_confirm = request.data.get("password_confirm", "")
        barangay_id = request.data.get("barangay")

        errors = {}
        if not username:
            errors["username"] = ["Enter a username."]
        elif len(username) > 150:
            errors["username"] = ["Username must be 150 characters or fewer."]
        if not first_name:
            errors["first_name"] = ["Enter your first name."]
        if not last_name:
            errors["last_name"] = ["Enter your last name."]
        if not email:
            errors["email"] = ["Enter an email address for account follow-up."]
        else:
            try:
                validate_email(email)
            except DjangoValidationError:
                errors["email"] = ["Enter a valid email address."]
        if len(email) > 254:
            errors["email"] = ["Email address must be 254 characters or fewer."]
        if len(contact_number) > 20:
            errors["contact_number"] = ["Contact number must be 20 characters or fewer."]
        if not isinstance(password, str):
            password = ""
        if not isinstance(password_confirm, str):
            password_confirm = ""
        if password != password_confirm:
            errors["password_confirm"] = ["The passwords do not match."]
        if not password:
            errors["password"] = ["Choose a password."]
        try:
            barangay_id = int(barangay_id)
        except (TypeError, ValueError):
            errors["barangay"] = ["Choose your requested barangay assignment."]
        if errors:
            raise ValidationError(errors)

        User = get_user_model()
        if User.objects.filter(username__iexact=username).exists():
            raise ValidationError({"username": ["This username is already in use."]})
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError({"email": ["This email is already in use."]})
        barangay = get_object_or_404(Barangay, pk=barangay_id, is_active=True)

        account = User(username=username, first_name=first_name, last_name=last_name,
                       email=email, contact_number=contact_number,
                       role="regular_staff", is_active=False, must_change_password=False)
        try:
            validate_password(password, user=account)
        except DjangoValidationError as error:
            raise ValidationError({"password": error.messages})

        with transaction.atomic():
            account.set_password(password)
            account.save()
            registration = StaffRegistrationRequest.objects.create(
                user=account, requested_barangay=barangay,
            )
        return Response({
            "detail": "Staff account request submitted. You can sign in after OSCA Admin approves it.",
            "request_id": registration.pk,
            "status": registration.status,
        }, status=201)


class StaffRegistrationReviewAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not is_registration_reviewer(request.user):
            return Response({"detail": "Only OSCA Admin can review staff account requests."}, status=403)
        status_filter = request.query_params.get("status", "pending")
        requests = StaffRegistrationRequest.objects.select_related(
            "user", "requested_barangay", "reviewed_by"
        )
        if status_filter != "all":
            if status_filter not in {"pending", "approved", "rejected"}:
                return Response({"detail": "Invalid status filter."}, status=400)
            requests = requests.filter(status=status_filter)
        return Response([{
            "id": item.pk,
            "username": item.user.username,
            "first_name": item.user.first_name,
            "last_name": item.user.last_name,
            "email": item.user.email,
            "contact_number": item.user.contact_number,
            "requested_barangay": {"id": item.requested_barangay_id, "name": item.requested_barangay.name},
            "status": item.status,
            "review_note": item.review_note,
            "created_at": item.created_at,
            "reviewed_at": item.reviewed_at,
            "reviewed_by": item.reviewed_by.get_username() if item.reviewed_by else None,
        } for item in requests])

    def post(self, request, pk):
        from rest_framework.exceptions import ValidationError

        if not is_registration_reviewer(request.user):
            return Response({"detail": "Only OSCA Admin can review staff account requests."}, status=403)
        registration = get_object_or_404(
            StaffRegistrationRequest.objects.select_related("user", "requested_barangay"), pk=pk
        )
        if registration.status != "pending":
            return Response({"detail": "This request has already been reviewed."}, status=400)

        decision = request.data.get("decision")
        note = str(request.data.get("review_note", "")).strip()[:500]
        if decision not in {"approve", "reject"}:
            raise ValidationError({"decision": ["Choose approve or reject."]})

        with transaction.atomic():
            registration.reviewed_by = request.user
            registration.reviewed_at = timezone.now()
            registration.review_note = note
            if decision == "approve":
                raw_barangay_id = request.data.get("barangay") or registration.requested_barangay_id
                try:
                    barangay_id = int(raw_barangay_id)
                except (TypeError, ValueError):
                    raise ValidationError({"barangay": ["Choose a valid barangay assignment."]})
                barangay = get_object_or_404(Barangay, pk=barangay_id, is_active=True)
                registration.status = "approved"
                registration.user.role = "regular_staff"
                registration.user.is_active = True
                registration.user.save(update_fields=["role", "is_active"])
                StaffProfile.objects.update_or_create(
                    user=registration.user, defaults={"barangay": barangay}
                )
                action_description = f"Approved staff registration and assigned {barangay.name}."
            else:
                registration.status = "rejected"
                registration.user.is_active = False
                registration.user.save(update_fields=["is_active"])
                action_description = "Rejected staff registration request."
            registration.save(update_fields=["status", "review_note", "reviewed_by", "reviewed_at", "updated_at"])
            record_action(request, "approve" if decision == "approve" else "edit",
                          "staff_registration", registration, action_description)

        return Response({"detail": f"Staff registration {registration.status}.", "status": registration.status})


class IsOSCAStaff(BasePermission):
    def has_permission(self, request, view):
        return request.user.role in ["head_staff", "regular_staff"]


def is_ising_staff_user(user):
    if getattr(user, "role", None) != "regular_staff":
        return False
    profile = getattr(user, "staff_profile", None)
    return bool(profile and profile.barangay.name.strip().casefold() == "ising")


class GroceryDashboardSummaryAPIView(APIView):
    """Share aggregate grocery progress on every OSCA staff dashboard."""
    permission_classes = [IsAuthenticated, IsOSCAStaff]

    def get(self, request):
        today = timezone.localdate()
        distributions = GroceryDistribution.objects.filter(
            distribution_date__year=today.year,
            distribution_date__month=today.month,
        )
        totals = distributions.aggregate(beneficiaries=Sum("total_beneficiaries"))
        released = GroceryClaim.objects.filter(
            distribution__in=distributions,
            claimed=True,
        ).count()
        beneficiaries = totals["beneficiaries"] or 0
        return Response({
            "period": today.strftime("%Y-%m"),
            "distribution_count": distributions.count(),
            "total_beneficiaries": beneficiaries,
            "total_released": released,
            "total_pending": max(beneficiaries - released, 0),
        })


class GroceryDistributionListCreateAPIView(ListCreateAPIView):
    serializer_class = GroceryDistributionSerializer
    permission_classes = [IsAuthenticated, IsOSCAStaff]

    def get_queryset(self):
        distributions = GroceryDistribution.objects.all().order_by("-distribution_date", "-id")
        if self.request.user.role == "head_staff":
            return distributions
        profile = getattr(self.request.user, "staff_profile", None)
        return distributions.filter(barangay=profile.barangay.name) if profile else distributions.none()

    def create(self, request, *args, **kwargs):
        if not is_ising_staff_user(request.user):
            return Response({"detail": "Only the Ising barangay staff account may schedule grocery distributions."}, status=403)
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        profile = getattr(self.request.user, "staff_profile", None)
        total = SeniorCitizen.objects.filter(barangay_id=profile.barangay_id, is_active=True).count() if profile else 0
        distribution = serializer.save(total_beneficiaries=total)
        record_action(self.request, "create", "grocery_distribution", distribution, "Scheduled a grocery distribution.")


class GroceryClaimListAPIView(ListCreateAPIView):
    serializer_class = GroceryClaimReportSerializer
    permission_classes = [IsAuthenticated, IsOSCAStaff]

    def get_queryset(self):
        claims = GroceryClaim.objects.select_related(
            "distribution", "senior_citizen", "senior_citizen__barangay"
        )
        if self.request.user.role == "head_staff":
            queryset = claims
        else:
            profile = getattr(self.request.user, "staff_profile", None)
            queryset = claims.filter(distribution__barangay=profile.barangay.name) if profile else claims.none()
        distribution_id = self.request.query_params.get("distribution")
        senior_id = self.request.query_params.get("senior")
        if distribution_id and distribution_id.isdigit():
            queryset = queryset.filter(distribution_id=int(distribution_id))
        if senior_id and senior_id.isdigit():
            queryset = queryset.filter(senior_citizen_id=int(senior_id))
        return queryset.order_by("-distribution__distribution_date", "senior_citizen__last_name", "senior_citizen__first_name")

    def get_serializer_class(self):
        return GroceryClaimWriteSerializer if self.request.method == "POST" else GroceryClaimReportSerializer

    def create(self, request, *args, **kwargs):
        if not is_ising_staff_user(request.user):
            return Response({"detail": "Only the Ising barangay staff account may record grocery claims."}, status=403)
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        claim = serializer.save()
        GroceryDistribution.objects.filter(pk=claim.distribution_id).update(
            total_released=GroceryClaim.objects.filter(distribution_id=claim.distribution_id, claimed=True).count()
        )
        record_action(self.request, "create", "grocery_claim", claim, "Recorded a grocery claim.")


class GroceryClaimDetailAPIView(generics.UpdateAPIView):
    serializer_class = GroceryClaimWriteSerializer
    permission_classes = [IsAuthenticated, IsOSCAStaff]
    http_method_names = ["patch", "put", "options", "head"]

    def get_queryset(self):
        claims = GroceryClaim.objects.select_related("distribution", "senior_citizen", "senior_citizen__barangay")
        if self.request.user.role != "regular_staff":
            return claims.none()
        profile = getattr(self.request.user, "staff_profile", None)
        return claims.filter(distribution__barangay=profile.barangay.name) if profile else claims.none()

    def update(self, request, *args, **kwargs):
        if not is_ising_staff_user(request.user):
            return Response({"detail": "Only the Ising barangay staff account may update grocery claims."}, status=403)
        response = super().update(request, *args, **kwargs)
        claim = self.get_object()
        GroceryDistribution.objects.filter(pk=claim.distribution_id).update(
            total_released=GroceryClaim.objects.filter(distribution_id=claim.distribution_id, claimed=True).count()
        )
        record_action(request, "edit", "grocery_claim", claim, "Updated a grocery claim.")
        return response


class IsIsingStaff(BasePermission):
    def has_permission(self, request, view):
        if not request.user.is_authenticated or request.user.role != "regular_staff":
            return False
        profile = getattr(request.user, "staff_profile", None)
        return bool(profile and profile.barangay.name.strip().casefold() == "ising")


class BookletReturnListCreateAPIView(ListCreateAPIView):
    serializer_class = BookletReturnSerializer
    permission_classes = [IsAuthenticated, IsIsingStaff]

    def get_queryset(self):
        profile = self.request.user.staff_profile
        returns = BookletReturn.objects.select_related(
            "senior_citizen", "senior_citizen__barangay", "recorded_by"
        ).filter(senior_citizen__barangay_id=profile.barangay_id)
        month = self.request.query_params.get("month")
        year = self.request.query_params.get("year")
        barangay_id = self.request.query_params.get("barangay")
        if month:
            parts = month.split("-")
            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                returns = returns.filter(date_returned__year=int(parts[0]), date_returned__month=int(parts[1]))
        elif year and year.isdigit():
            returns = returns.filter(date_returned__year=int(year))
        if barangay_id and barangay_id.isdigit():
            returns = returns.filter(senior_citizen__barangay_id=int(barangay_id))
        return returns.order_by("-date_returned", "senior_citizen__last_name")

    def perform_create(self, serializer):
        serializer.save(recorded_by=self.request.user)

class SeniorCitizenListAPIView(ListCreateAPIView):
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

    def perform_create(self, serializer):
        from django.utils import timezone

        with transaction.atomic():
            placeholder = secrets.token_hex(5).upper()
            senior = serializer.save(
                osca_id=f"P-{placeholder}",
                registration_cert_no=f"P-{placeholder}",
            )
            year = timezone.localdate().year
            sequence = senior.pk
            osca_id = f"{year}-{sequence:03d}"
            while SeniorCitizen.objects.exclude(pk=senior.pk).filter(osca_id=osca_id).exists():
                sequence += 1
                osca_id = f"{year}-{sequence:03d}"
            certificate = f"CERT-{year}-{senior.pk:06d}"
            while SeniorCitizen.objects.exclude(pk=senior.pk).filter(registration_cert_no=certificate).exists():
                certificate = f"CERT-{year}-{secrets.token_hex(4).upper()}"
            senior.osca_id = osca_id
            senior.registration_cert_no = certificate
            senior.save(update_fields=["osca_id", "registration_cert_no", "updated_at"])
            record_action(self.request, "create", "senior", senior, "Registered a senior citizen record.")


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


class DocumentListCreateAPIView(generics.ListCreateAPIView):
    serializer_class = DocumentSerializer
    permission_classes = [IsAuthenticated, IsOSCAStaff]

    def create(self, request, *args, **kwargs):
        self.ocr_result = {}
        response = super().create(request, *args, **kwargs)
        if response.status_code == 201:
            # OCR text is returned only to the authenticated uploader; it is not
            # stored in the database or included in the normal document list.
            response.data = {**response.data, **self.ocr_result}
        return response

    def get_queryset(self):
        documents = Document.objects.select_related("senior_citizen", "senior_citizen__barangay", "uploaded_by")
        if self.request.user.role == "head_staff":
            return documents.order_by("-created_at")
        profile = getattr(self.request.user, "staff_profile", None)
        if not profile:
            return documents.none()
        return documents.filter(senior_citizen__barangay_id=profile.barangay_id).order_by("-created_at")

    def perform_create(self, serializer):
        original_name = Path(serializer.validated_data["file"].name).name[:200]
        with transaction.atomic():
            document = serializer.save(uploaded_by=self.request.user, file_name=original_name)
            extracted_text, ocr_status = extract_document_text(document)
            prediction = classify_document(document, extracted_text)
            if prediction:
                predicted_label, confidence = prediction
                document.nlp_classification = predicted_label
                document.nlp_confidence = confidence
                document.classifier_source = classifier_source(classifier_artifact_path())
                document.save(update_fields=["nlp_classification", "nlp_confidence", "classifier_source"])
            self.ocr_result = {
                "ocr_status": ocr_status,
                "ocr_text": extracted_text[:10_000],
                "extracted_entities_draft": extract_document_entities(extracted_text),
                "entity_extraction_note": "Unverified OCR suggestions only. Review against the source document before using or saving them.",
            }
            record_action(self.request, "upload", "document", document, "Uploaded a senior citizen document.")


class DocumentDownloadAPIView(APIView):
    permission_classes = [IsAuthenticated, IsOSCAStaff]

    def get(self, request, pk):
        documents = Document.objects.select_related("senior_citizen", "senior_citizen__barangay")
        if request.user.role == "regular_staff":
            profile = getattr(request.user, "staff_profile", None)
            if not profile:
                return Response({"detail": "This staff account has no assigned barangay."}, status=403)
            documents = documents.filter(senior_citizen__barangay_id=profile.barangay_id)
        document = get_object_or_404(documents, pk=pk)
        try:
            return FileResponse(document.file.open("rb"), as_attachment=True, filename=document.file_name)
        except (FileNotFoundError, OSError):
            return Response({"detail": "The stored document file could not be found."}, status=404)


class DocumentReviewAPIView(APIView):
    """Allow OSCA staff to record a manual document review or remove an upload."""
    permission_classes = [IsAuthenticated, IsOSCAStaff]

    def get_document(self, request, pk):
        documents = Document.objects.select_related("senior_citizen", "senior_citizen__barangay")
        if request.user.role == "regular_staff":
            profile = getattr(request.user, "staff_profile", None)
            if not profile:
                return None
            documents = documents.filter(senior_citizen__barangay_id=profile.barangay_id)
        return get_object_or_404(documents, pk=pk)

    def patch(self, request, pk):
        from rest_framework.exceptions import ValidationError

        document = self.get_document(request, pk)
        if document is None:
            return Response({"detail": "This staff account has no assigned barangay."}, status=403)
        decision = request.data.get("decision")
        if decision not in {"verify", "reject"}:
            raise ValidationError({"decision": ["Choose verify or reject."]})

        corrected_type = request.data.get("document_type")
        if corrected_type is not None:
            corrected_type = str(corrected_type).strip()
            if not corrected_type or len(corrected_type) > 100:
                raise ValidationError({"document_type": ["Enter a document type of 1 to 100 characters."]})
            document.document_type = corrected_type

        document.is_verified = decision == "verify"
        document.review_status = "verified" if document.is_verified else "rejected"
        document.review_note = str(request.data.get("review_note", "")).strip()[:500]
        document.reviewed_by = request.user
        document.reviewed_at = timezone.now()
        document.save(update_fields=[
            "document_type", "is_verified", "review_status", "review_note",
            "reviewed_by", "reviewed_at",
        ])
        record_action(
            request,
            "approve" if document.is_verified else "edit",
            "document_review",
            document,
            f"Manually {document.review_status} uploaded document; document type set to {document.document_type}.",
        )
        return Response(DocumentSerializer(document, context={"request": request}).data)

    def delete(self, request, pk):
        document = self.get_document(request, pk)
        if document is None:
            return Response({"detail": "This staff account has no assigned barangay."}, status=403)
        file_name = document.file_name
        record_action(request, "delete", "document", document, "Deleted an uploaded senior citizen document.")
        stored_file = document.file
        document.delete()
        if stored_file:
            stored_file.delete(save=False)
        return Response({"detail": f"Deleted {file_name}."}, status=200)


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


class PensionRecordDetailAPIView(generics.RetrieveUpdateAPIView):
    serializer_class = PensionRecordSerializer
    permission_classes = [IsAuthenticated, IsOSCAStaff]

    def get_queryset(self):
        records = PensionRecord.objects.select_related("senior_citizen", "senior_citizen__barangay")
        if self.request.user.role == "head_staff":
            return records
        profile = getattr(self.request.user, "staff_profile", None)
        return records.filter(senior_citizen__barangay_id=profile.barangay_id) if profile else records.none()

    def perform_update(self, serializer):
        record = serializer.save()
        record_action(self.request, "edit", "pension", record, "Updated pension claim record.")


class DeathRecordListCreateAPIView(generics.ListCreateAPIView):
    serializer_class = DeathRecordSerializer
    permission_classes = [IsAuthenticated, IsOSCAStaff]

    def get_queryset(self):
        records = DeathRecord.objects.select_related("senior_citizen", "senior_citizen__barangay", "recorded_by")
        user = self.request.user
        if user.role == "head_staff":
            return records.all()
        profile = getattr(user, "staff_profile", None)
        return records.filter(senior_citizen__barangay_id=profile.barangay_id) if profile else records.none()

    def perform_create(self, serializer):
        record = serializer.save(recorded_by=self.request.user, review_status="pending")
        record_action(self.request, "create", "death_record", record, "Submitted a death report for Head Staff review.")


class DeathRecordDetailAPIView(generics.RetrieveUpdateAPIView):
    serializer_class = DeathRecordSerializer
    permission_classes = [IsAuthenticated, IsOSCAStaff]

    def get_queryset(self):
        records = DeathRecord.objects.select_related(
            "senior_citizen", "senior_citizen__barangay", "recorded_by", "reviewed_by"
        )
        if self.request.user.role == "head_staff":
            return records
        profile = getattr(self.request.user, "staff_profile", None)
        return records.filter(
            senior_citizen__barangay_id=profile.barangay_id,
            review_status="needs_correction",
        ) if profile else records.none()

    def update(self, request, *args, **kwargs):
        from rest_framework.exceptions import PermissionDenied

        if request.user.role != "regular_staff":
            raise PermissionDenied("Only the reporting barangay staff may resubmit a returned death report.")
        return super().update(request, *args, **kwargs)

    def perform_update(self, serializer):
        record = serializer.save(
            review_status="pending",
            review_note="",
            reviewed_by=None,
            reviewed_at=None,
        )
        record_action(self.request, "edit", "death_record", record, "Corrected and resubmitted a death report for review.")


class DeathRecordReviewAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        from rest_framework.exceptions import PermissionDenied, ValidationError

        if request.user.role != "head_staff":
            raise PermissionDenied("Only Head Staff may review death reports.")
        decision = request.data.get("decision")
        if decision not in {"verify", "return"}:
            raise ValidationError({"decision": ["Choose verify or return."]})
        note = str(request.data.get("review_note", "")).strip()[:1000]
        if decision == "return" and not note:
            raise ValidationError({"review_note": ["A correction note is required when returning a report."]})

        with transaction.atomic():
            record = get_object_or_404(
                DeathRecord.objects.select_for_update().select_related("senior_citizen"), pk=pk
            )
            if record.review_status in {"verified", "cancelled"}:
                raise ValidationError({"detail": "This death report is already closed and cannot be reviewed."})
            record.review_status = "verified" if decision == "verify" else "needs_correction"
            record.review_note = note
            record.reviewed_by = request.user
            record.reviewed_at = timezone.now()
            record.save(update_fields=["review_status", "review_note", "reviewed_by", "reviewed_at"])
            if decision == "verify":
                senior = record.senior_citizen
                senior.is_active = False
                senior.save(update_fields=["is_active", "updated_at"])
                senior.portal_users.update(is_active=False)
            record_action(
                request,
                "approve" if decision == "verify" else "edit",
                "death_record_review",
                record,
                "Verified death report and deactivated senior access." if decision == "verify" else "Returned death report for correction.",
            )

        return Response(DeathRecordSerializer(record, context={"request": request}).data)


class DeathRecordCancelAPIView(APIView):
    permission_classes = [IsAuthenticated, IsOSCAStaff]

    def post(self, request, pk):
        from rest_framework.exceptions import PermissionDenied, ValidationError

        if request.user.role != "regular_staff":
            raise PermissionDenied("Only the reporting barangay staff may cancel an unverified death report.")
        profile = getattr(request.user, "staff_profile", None)
        if not profile:
            raise PermissionDenied("This staff account has no assigned barangay.")

        reason = str(request.data.get("reason", "")).strip()
        if not reason:
            raise ValidationError({"reason": ["Enter why this death report is being cancelled."]})
        if len(reason) > 1000:
            raise ValidationError({"reason": ["Cancellation reason must be 1000 characters or fewer."]})

        with transaction.atomic():
            record = get_object_or_404(
                DeathRecord.objects.select_for_update().select_related(
                    "senior_citizen"
                ),
                pk=pk,
                recorded_by=request.user,
                senior_citizen__barangay_id=profile.barangay_id,
            )
            if record.review_status not in {"pending", "needs_correction"}:
                raise ValidationError({"detail": "Only an unverified death report can be cancelled."})
            record.review_status = "cancelled"
            record.cancellation_reason = reason
            record.cancelled_by = request.user
            record.cancelled_at = timezone.now()
            record.save(update_fields=["review_status", "cancellation_reason", "cancelled_by", "cancelled_at"])
            record_action(request, "edit", "death_record_cancellation", record, "Cancelled an unverified death report.")
        return Response(DeathRecordSerializer(record, context={"request": request}).data)


class ResidenceTransferListCreateAPIView(generics.ListCreateAPIView):
    serializer_class = ResidenceTransferRecordSerializer
    permission_classes = [IsAuthenticated, IsOSCAStaff]

    def get_queryset(self):
        records = ResidenceTransferRecord.objects.select_related(
            "senior_citizen", "from_barangay", "to_barangay", "recorded_by"
        )
        user = self.request.user
        if user.role == "head_staff":
            return records.all()
        profile = getattr(user, "staff_profile", None)
        if not profile:
            return records.none()
        return records.filter(Q(from_barangay_id=profile.barangay_id) | Q(to_barangay_id=profile.barangay_id))

    def perform_create(self, serializer):
        senior = serializer.validated_data["senior_citizen"]
        with transaction.atomic():
            source_barangay = senior.barangay
            destination = serializer.validated_data.get("to_barangay")
            record = serializer.save(from_barangay=source_barangay, recorded_by=self.request.user)
            senior.barangay = destination
            if record.destination_address:
                senior.address = record.destination_address
            senior.save(update_fields=["barangay", "address", "updated_at"])
            record_action(self.request, "create", "residence_transfer", record, "Recorded residence transfer and updated the senior's current barangay/address.")


class AnalyticsAPIView(APIView):
    permission_classes = [IsAuthenticated, IsOSCAStaff]

    def get(self, request):
        seniors = SeniorCitizen.objects.all()
        pensions = PensionRecord.objects.select_related("senior_citizen")
        deaths = DeathRecord.objects.select_related("senior_citizen").exclude(review_status="cancelled")
        transfers = ResidenceTransferRecord.objects.all()
        if request.user.role == "regular_staff":
            profile = getattr(request.user, "staff_profile", None)
            if not profile:
                return Response({"detail": "No barangay is assigned to this staff account."}, status=403)
            seniors = seniors.filter(barangay_id=profile.barangay_id)
            pensions = pensions.filter(senior_citizen__barangay_id=profile.barangay_id)
            deaths = deaths.filter(senior_citizen__barangay_id=profile.barangay_id)
            transfers = transfers.filter(Q(from_barangay_id=profile.barangay_id) | Q(to_barangay_id=profile.barangay_id))
        today = timezone.localdate()
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
            "deaths": {
                "total": deaths.count(),
                "this_month": deaths.filter(date_of_death__year=today.year, date_of_death__month=today.month).count(),
                "this_year": deaths.filter(date_of_death__year=today.year).count(),
            },
            "transfers": {
                "total": transfers.count(),
                "this_month": transfers.filter(transfer_date__year=today.year, transfer_date__month=today.month).count(),
                "this_year": transfers.filter(transfer_date__year=today.year).count(),
            },
            "note": "Booklet and age-group analytics will be added when their agreed summary data is available.",
        }
        return Response(result)


class CurrentUserAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        result = {
            "username": user.get_username(),
            "first_name": user.first_name,
            "last_name": user.last_name,
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


from django.db.models.functions import TruncMonth  # noqa: E402
from .models import MedicineRelease  # noqa: E402
from .serializers import MedicineReleaseSerializer  # noqa: E402


def scoped_medicine_releases(user):
    """Head Staff sees every barangay; Regular Staff sees only their own."""
    releases = MedicineRelease.objects.select_related(
        "senior_citizen", "senior_citizen__barangay", "recorded_by"
    )
    if user.role == "head_staff":
        return releases
    profile = getattr(user, "staff_profile", None)
    return releases.filter(senior_citizen__barangay_id=profile.barangay_id) if profile else releases.none()


def filter_medicine_releases(releases, params):
    senior = params.get("senior")
    month = params.get("month")
    year = params.get("year")
    barangay = params.get("barangay")
    if senior and senior.isdigit():
        releases = releases.filter(senior_citizen_id=int(senior))
    if month:
        parts = month.split("-")
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            releases = releases.filter(date_released__year=int(parts[0]), date_released__month=int(parts[1]))
    elif year and year.isdigit():
        releases = releases.filter(date_released__year=int(year))
    if barangay and barangay.isdigit():
        releases = releases.filter(senior_citizen__barangay_id=int(barangay))
    return releases


class MedicineReleaseListCreateAPIView(ListCreateAPIView):
    serializer_class = MedicineReleaseSerializer
    permission_classes = [IsAuthenticated, IsOSCAStaff]

    def get_queryset(self):
        releases = scoped_medicine_releases(self.request.user)
        return filter_medicine_releases(releases, self.request.query_params).order_by(
            "-date_released", "-id"
        )

    def perform_create(self, serializer):
        release = serializer.save(recorded_by=self.request.user)
        record_action(self.request, "create", "medicine", release, "Recorded a medicine release.")


class MedicineSummaryAPIView(APIView):
    """Monthly and yearly medicine release counts per barangay (no per-senior details)."""
    permission_classes = [IsAuthenticated, IsOSCAStaff]

    def get(self, request):
        releases = filter_medicine_releases(
            scoped_medicine_releases(request.user), request.query_params
        )
        monthly = (
            releases.annotate(month=TruncMonth("date_released"))
            .values("month", "senior_citizen__barangay__name")
            .annotate(
                release_count=Count("id"),
                seniors_served=Count("senior_citizen", distinct=True),
                total_quantity=Sum("quantity"),
            )
            .order_by("month", "senior_citizen__barangay__name")
        )
        yearly = (
            releases.values("date_released__year")
            .annotate(
                release_count=Count("id"),
                seniors_served=Count("senior_citizen", distinct=True),
                total_quantity=Sum("quantity"),
            )
            .order_by("date_released__year")
        )
        return Response({
            "scope": "all_barangays" if request.user.role == "head_staff" else "assigned_barangay",
            "monthly": [
                {
                    "month": row["month"].strftime("%Y-%m"),
                    "barangay": row["senior_citizen__barangay__name"],
                    "release_count": row["release_count"],
                    "seniors_served": row["seniors_served"],
                    "total_quantity": row["total_quantity"] or 0,
                }
                for row in monthly
            ],
            "yearly": [
                {
                    "year": row["date_released__year"],
                    "release_count": row["release_count"],
                    "seniors_served": row["seniors_served"],
                    "total_quantity": row["total_quantity"] or 0,
                }
                for row in yearly
            ],
        })
